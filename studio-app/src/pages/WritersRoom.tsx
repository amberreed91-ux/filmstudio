import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  Bold,
  Brain,
  CheckCircle2,
  ChevronDown,
  Copy,
  Edit3,
  FileText,
  Italic,
  Loader2,
  MemoryStick,
  Mic,
  Plus,
  UserCheck,
  Redo2,
  Save,
  Undo2,
  UploadCloud,
  Users,
} from 'lucide-react'
import StudioShell from '../components/StudioShell'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import CharacterLookApproval from '../components/CharacterLookApproval'
import { useCharacterLooks } from '../hooks/useCharacterLooks'
import { characterLookError } from '../lib/characterLookApi'
import VoicePicker from '../components/VoicePicker'
import { useStudio } from '../context/StudioContext'
import { resolveActiveProjectId, withProductionContext } from '../lib/projectContext'
import { createSceneDraftBuffer } from '../lib/sceneDrafts'
import { decideRoomHandoff, decideSceneSwitch, shouldFollowSceneLink } from './sceneSwitchGuard'
import DirectorDebatePanel from '../components/DirectorDebatePanel'
import WritersDebateModal from '../components/WritersDebateModal'
import { PageScene } from '../rooms/ThePage'
import {
  checkBackendHealth,
  createScene,
  createCharacterSkeleton,
  generateScenes,
  listCharacters,
  listScenes,
  saveCreativeDecisionMemory,
  simulateCharacterMind,
  triggerSceneDebate,
  updateCharacter,
  updateScene,
  uploadCharacterDescriptor,
  type CharacterRecord,
  type CoDirectorDebateEntry,
  type CreateScenePayload,
  type Scene,
} from '../lib/studioApi'

// ── Types ──────────────────────────────────────────────────────────────────

type ImportRow = {
  id: string
  name: string
  size: number
  sceneCount: number
  timestamp: Date
}

type ExportFormat = 'pdf' | 'fdx' | 'txt' | 'clipboard'

interface AiSuggestion {
  id: string
  text: string
  accepted?: boolean
  dismissed?: boolean
}

// ── Fountain prefixes ──────────────────────────────────────────────────────

const FOUNTAIN_PREFIXES: Array<{ label: string; prefix: string; shortcut: string }> = [
  { label: 'S.H.', prefix: '.\n', shortcut: 'Scene Heading' },
  { label: 'ACT', prefix: '!\n', shortcut: 'Action' },
  { label: 'CHR', prefix: '@', shortcut: 'Character' },
  { label: 'DLG', prefix: '', shortcut: 'Dialogue (double-spaced)' },
  { label: 'PAR', prefix: '^', shortcut: 'Paren' },
  { label: 'TRN', prefix: '> ', shortcut: 'Transition' },
]

// ── Helpers ────────────────────────────────────────────────────────────────

function estimateWordCount(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0
}

function timeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ago`
}

// Reversible, unsaved profile form state; never written to creative memory or storage.
const profileDrafts = new Map<string, Record<string, Partial<CharacterRecord>>>()

const scriptDrafts = createSceneDraftBuffer(async (projectId, sceneId, text) => {
  const result = await updateScene(projectId, sceneId, { text, description: text })
  if (result.error) throw new Error(result.error)
})

// ── Component ──────────────────────────────────────────────────────────────

export default function WritersRoom() {
  const navigate = useNavigate()
  const { projectId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const querySceneId = searchParams.get('scene') || searchParams.get('scene_id') || ''
  const { activeProjectId, activeProject, loadProject, createJob, submitJob } = useStudio()
  const effectiveProjectId = resolveActiveProjectId({ queryProjectId, routeProjectId: projectId, contextProjectId: activeProjectId })
  const currentProjectRef = useRef(effectiveProjectId)
  const [editorProjectId, setEditorProjectId] = useState('')

  // ── Core state ────────────────────────────────────────────────────────────
  const [scenes, setScenes] = useState<Scene[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [backendHealthy, setBackendHealthy] = useState(true)
  const [healthCheckLoading, setHealthCheckLoading] = useState(false)
  const [generationLoading, setGenerationLoading] = useState(false)

  // ── Editor state ──────────────────────────────────────────────────────────
  const [activeSceneId, setActiveSceneId] = useState<string | null>(null)
  const activeSceneIdRef = useRef<string | null>(null)
  const lastObservedQuerySceneIdRef = useRef('')
  const [scriptText, setScriptText] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null)
  const [isDirty, setIsDirty] = useState(false)
  const [showExportDropdown, setShowExportDropdown] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [aiSuggestion, setAiSuggestion] = useState<AiSuggestion | null>(null)

  // Undo/redo stack
  const [undoStack, setUndoStack] = useState<string[]>([])
  const [redoStack, setRedoStack] = useState<string[]>([])

  const fileInputRef = useRef<HTMLInputElement>(null)
  const exportRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<HTMLTextAreaElement>(null)

  // ── Intelligence state ────────────────────────────────────────────────────
  const [debateMode, setDebateMode] = useState(false)
  const [debateRunning, setDebateRunning] = useState(false)
  const [activeDebate, setActiveDebate] = useState<CoDirectorDebateEntry | null>(null)

  const [characterMindMode, setCharacterMindMode] = useState(false)
  const [selectedCharacter, setSelectedCharacter] = useState('')
  const [characterSimulating, setCharacterSimulating] = useState(false)
  const [characterMindResult, setCharacterMindResult] = useState<string | null>(null)

  const [sceneDebateResult, setSceneDebateResult] = useState<{ restraint: string; urgency: string; scene_id: string } | null>(null)

  const [memorySaving, setMemorySaving] = useState(false)
  const [memorySavedChip, setMemorySavedChip] = useState(false)

  // ── Character descriptions state ──────────────────────────────────────────
  const requestedStep = searchParams.get('step')
  const rightTab = requestedStep === 'looks' ? 'looks' : requestedStep === 'characters' ? 'characters' : 'scenes'
  const selectedLookCharacter = searchParams.get('character') || ''
  const characterLooks = useCharacterLooks(effectiveProjectId)
  const refreshCharacterLooks = characterLooks.refresh
  const setRightTab = (step: 'scenes' | 'characters' | 'looks') => {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      next.set('step', step)
      return next
    }, { replace: true })
    if (step === 'looks') void refreshCharacterLooks()
  }
  const [characters, setCharacters] = useState<CharacterRecord[]>([])
  const [charactersLoading, setCharactersLoading] = useState(false)
  const [charactersLoaded, setCharactersLoaded] = useState(false)
  const [charactersSaving, setCharactersSaving] = useState<Record<string, boolean>>({})
  const [creatingCharacters, setCreatingCharacters] = useState(false)
  const [characterUploading, setCharacterUploading] = useState<Record<string, boolean>>({})
  const [newCharacterNames, setNewCharacterNames] = useState<string[]>([])
  const [editDrafts, setEditDrafts] = useState<Record<string, Partial<CharacterRecord>>>({})
  const [characterDraftProjectId, setCharacterDraftProjectId] = useState('')
  const latestCharacterDirty = useRef(false)
  const [voicePickerChar, setVoicePickerChar] = useState<CharacterRecord | null>(null)
  const [voiceUpdates, setVoiceUpdates] = useState<Record<string, {
    voiceId: string
    voiceName: string
    provider?: CharacterRecord['voice_provider']
    sourceType?: string | null
    stylePrompt?: string | null
  }>>({})

  // ── Imports state ─────────────────────────────────────────────────────────
  const [recentImports, setRecentImports] = useState<ImportRow[]>([])
  const [uploadingScript, setUploadingScript] = useState(false)

  // ── Derived ───────────────────────────────────────────────────────────────
  const activeScene = useMemo(
    () => scenes.find((s) => s.scene_id === activeSceneId) || null,
    [scenes, activeSceneId],
  )

  const allCharacters = useMemo(() => {
    const chars = new Set<string>()
    for (const scene of scenes) {
      for (const char of scene.characters || []) {
        if (char.trim()) chars.add(char.trim())
      }
    }
    return Array.from(chars).sort()
  }, [scenes])

  useEffect(() => {
    latestCharacterDirty.current = Object.keys(editDrafts).length > 0
    if (!characterDraftProjectId || characterDraftProjectId !== effectiveProjectId) return
    if (latestCharacterDirty.current) profileDrafts.set(characterDraftProjectId, editDrafts)
    else profileDrafts.delete(characterDraftProjectId)
  }, [editDrafts, characterDraftProjectId, effectiveProjectId])

  // ── Close export dropdown on outside click ────────────────────────────────
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) {
        setShowExportDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // Explicit room links select their film before loading scene/editor state.
  useEffect(() => {
    currentProjectRef.current = effectiveProjectId
    setScenes([])
    activeSceneIdRef.current = null
    setActiveSceneId(null)
    setScriptText('')
    setEditorProjectId('')
    setIsDirty(false)
    setLastSavedAt(null)
    setCharacters([])
    setCharactersLoaded(false)
    setVoiceUpdates({})
    setRecentImports([])
    setEditDrafts(profileDrafts.get(effectiveProjectId) || {})
    setCharacterDraftProjectId(effectiveProjectId)
    setNewCharacterNames([])
    setUndoStack([])
    setRedoStack([])
  }, [effectiveProjectId])

  useEffect(() => {
    if (effectiveProjectId && activeProject?.project_id !== effectiveProjectId) {
      void loadProject(effectiveProjectId).catch((caught) => setError(caught instanceof Error ? caught.message : 'Could not open this film.'))
    }
  }, [activeProject?.project_id, effectiveProjectId, loadProject])

  // ── Load project and scenes ──────────────────────────────────────────────
  useEffect(() => {
    if (effectiveProjectId) {
      void checkHealth()
    }
  }, [effectiveProjectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const checkHealth = async () => {
    setHealthCheckLoading(true)
    const health = await checkBackendHealth()
    setBackendHealthy(health.healthy)
    setHealthCheckLoading(false)
    if (health.healthy) {
      void loadScenes()
    }
  }

  const retryHealthCheck = () => {
    void checkHealth()
  }

  const loadScenes = useCallback(async () => {
    if (!effectiveProjectId) return
    setLoading(true)
    setError('')
    try {
      const result = await listScenes(effectiveProjectId)
      if (currentProjectRef.current !== effectiveProjectId) return
      if (result.error) {
        setError(result.error)
      } else {
        setScenes(result.scenes)
        // Prefer the current URL/state selection over the first row. The
        // loader can finish after a user click (or run again during a data
        // refresh), so its closure must not reapply the initial scene.
        const currentSelectedSceneId = activeSceneIdRef.current
        const requestedSceneId = currentSelectedSceneId || querySceneId || activeSceneId
        const selected = result.scenes.find((scene) => scene.scene_id === requestedSceneId)
          || (!currentSelectedSceneId && !requestedSceneId ? result.scenes[0] : undefined)
        if (querySceneId && !selected) {
          activeSceneIdRef.current = null
          setActiveSceneId(null)
          setScriptText('')
          setError('The linked scene is not available in this film. Select a scene to continue.')
        } else if (selected && (editorProjectId !== effectiveProjectId || !currentSelectedSceneId || currentSelectedSceneId !== selected.scene_id || !isDirty)) {
          const draft = scriptDrafts.read(effectiveProjectId, selected.scene_id)
          activeSceneIdRef.current = selected.scene_id
          setActiveSceneId(selected.scene_id)
          setEditorProjectId(effectiveProjectId)
          setScriptText(draft ?? selected.text ?? selected.description ?? '')
          setIsDirty(draft !== undefined)
          if (draft !== undefined) setError('An unsaved script draft was recovered in this tab. Save it before continuing.')
          setSearchParams((params) => {
            const next = new URLSearchParams(params)
            next.set('scene', selected.scene_id)
            next.delete('scene_id')
            return next
          }, { replace: true })
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scenes')
    } finally {
      setLoading(false)
    }
  }, [
    activeSceneId,
    editorProjectId,
    effectiveProjectId,
    isDirty,
    querySceneId,
    setSearchParams,
  ])

  const loadCharacters = useCallback(async () => {
    if (!effectiveProjectId) return
    setCharactersLoading(true)
    try {
      const result = await listCharacters(effectiveProjectId)
      if (currentProjectRef.current !== effectiveProjectId) return
      if (result.error) throw new Error(result.error)
      setCharacters(result.characters)
      setCharactersLoaded(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load character profiles.')
    } finally {
      setCharactersLoading(false)
    }
  }, [effectiveProjectId])

  // Detect new characters from scenes vs DB
  useEffect(() => {
    if (charactersLoaded && scenes.length > 0) {
      const dbNames = new Set(characters.map((c) => c.name.toUpperCase()))
      const sceneNames = new Set<string>()
      for (const scene of scenes) {
        for (const char of scene.characters || []) {
          if (char.trim()) sceneNames.add(char.trim().toUpperCase())
        }
      }
      const unknown: string[] = []
      for (const name of sceneNames) {
        if (!dbNames.has(name)) unknown.push(name)
      }
      setNewCharacterNames(unknown)
    } else {
      setNewCharacterNames([])
    }
  }, [characters, charactersLoaded, scenes])

  // Load characters when scenes load
  useEffect(() => {
    if (effectiveProjectId) {
      void loadCharacters()
    }
  }, [effectiveProjectId, scenes.length]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Script saves and room handoffs ───────────────────────────────────────
  const latestEditor = useRef({ projectId: '', sceneId: '', text: '', dirty: false })
  const mountedEditor = useRef(false)
  useEffect(() => {
    latestEditor.current = { projectId: editorProjectId, sceneId: activeSceneId || '', text: scriptText, dirty: isDirty }
    if (isDirty && editorProjectId && activeSceneId) scriptDrafts.write(editorProjectId, activeSceneId, scriptText)
  }, [editorProjectId, activeSceneId, scriptText, isDirty])

  useEffect(() => {
    mountedEditor.current = true
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (latestEditor.current.dirty || latestCharacterDirty.current) {
        event.preventDefault()
        event.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => {
      mountedEditor.current = false
      window.removeEventListener('beforeunload', beforeUnload)
      const draft = latestEditor.current
      if (draft.dirty && draft.projectId && draft.sceneId) {
        // Flush on in-app navigation; a failed request keeps the in-tab buffer recoverable.
        void scriptDrafts.save(draft.projectId, draft.sceneId, draft.text).catch((caught) => {
          console.error('Script save is pending; draft retained in this tab:', caught)
        })
      }
    }
  }, [])

  useEffect(() => () => {
    const draft = latestEditor.current
    if (draft.dirty && draft.projectId === effectiveProjectId && draft.sceneId) {
      void scriptDrafts.save(draft.projectId, draft.sceneId, draft.text).catch((caught) => {
        console.error('Script save is pending; draft retained in this tab:', caught)
      })
    }
  }, [effectiveProjectId])

  const saveCurrentScene = useCallback(async (): Promise<boolean> => {
    const draft = latestEditor.current
    if (!draft.projectId || !draft.sceneId || !draft.dirty) return true
    setIsSaving(true)
    setError('')
    try {
      await scriptDrafts.save(draft.projectId, draft.sceneId, draft.text)
      if (!mountedEditor.current) return true
      const current = latestEditor.current
      if (current.projectId === draft.projectId && current.sceneId === draft.sceneId) {
        setScenes((previous) => previous.map((scene) => scene.scene_id === draft.sceneId ? { ...scene, text: draft.text, description: draft.text } : scene))
        setLastSavedAt(new Date())
        if (current.text === draft.text) {
          latestEditor.current = { ...current, dirty: false }
          setIsDirty(false)
          return true
        }
      }
      return false
    } catch (caught) {
      if (mountedEditor.current && latestEditor.current.projectId === draft.projectId) {
        setError(`Script not saved: ${caught instanceof Error ? caught.message : 'Please try again.'} Your draft is still here.`)
      }
      return false
    } finally {
      if (mountedEditor.current) setIsSaving(false)
    }
  }, [])

  const prepareRoomHandoff = useCallback(async (): Promise<boolean> => {
    const handoff = decideRoomHandoff({
      characterLooksBusy: characterLooks.busy,
      profileDraftCount: Object.keys(editDrafts).length,
    })
    if (!handoff.ok) {
      setError(handoff.message)
      return false
    }
    return saveCurrentScene()
  }, [editDrafts, saveCurrentScene, characterLooks.busy])

  const [switchingSceneId, setSwitchingSceneId] = useState<string | null>(null)

  const handleSelectScene = useCallback(async (sceneId: string) => {
    const draft = latestEditor.current
    const pendingScene = draft.dirty && isSaving ? draft.sceneId : ''
    const scene = scenes.find((candidate) => candidate.scene_id === sceneId)
    // An in-flight autosave must never strand the scene selector on the old
    // scene: when the pending save targets the scene we are leaving, switch
    // first and let the save finish in the background (the draft buffer is
    // per-scene, so the right text still lands on the right scene). A save
    // racing for a different scene keeps the previous guard.
    // (Decision logic lives in sceneSwitchGuard.ts, with regression tests.)
    if (!scene || decideSceneSwitch({
      activeSceneId: activeSceneId ?? '',
      requestedSceneId: sceneId,
      isSaving,
      pendingSaveSceneId: pendingScene,
      sceneExists: scene !== undefined,
    }) !== 'switch') return
    if (!pendingScene && !(await saveCurrentScene())) return
    if (pendingScene) {
      // The guard approved this switch because the in-flight save targets
      // the scene we are leaving. Awaiting saveCurrentScene() here would
      // dedupe onto that save's promise and silently delay the switch until
      // it settles — the selector would look dead in the meantime. Switch
      // now; the per-scene draft buffer lands the text in the background.
    }
    if (currentProjectRef.current !== effectiveProjectId) return
    const sceneDraft = scriptDrafts.read(effectiveProjectId, sceneId)
    setEditorProjectId(effectiveProjectId)
    activeSceneIdRef.current = sceneId
    setActiveSceneId(sceneId)
    setScriptText(sceneDraft ?? scene.text ?? scene.description ?? '')
    setIsDirty(sceneDraft !== undefined)
    setLastSavedAt(null)
    setUndoStack([])
    setRedoStack([])
    setSearchParams((params) => {
      const next = new URLSearchParams(params)
      next.set('scene', sceneId)
      next.delete('scene_id')
      return next
    }, { replace: true })
  }, [activeSceneId, isSaving, scenes, saveCurrentScene, effectiveProjectId, setSearchParams])

  // A scene switch can await an autosave; the list reports which row is in
  // flight and blocks a second switch until it settles.
  const selectSceneFromList = useCallback(async (sceneId: string) => {
    if (switchingSceneId) return
    setSwitchingSceneId(sceneId)
    try {
      await handleSelectScene(sceneId)
    } finally {
      setSwitchingSceneId(null)
    }
  }, [handleSelectScene, switchingSceneId])

  // Read incoming same-room scene links too (including legacy Production Board links).
  // (Decision logic lives in sceneSwitchGuard.ts, with regression tests.)
  useEffect(() => {
    const previousQuerySceneId = lastObservedQuerySceneIdRef.current
    lastObservedQuerySceneIdRef.current = querySceneId
    // setSearchParams is asynchronous. During the render between a user
    // selection and the URL update, querySceneId can still contain the old
    // scene. Treat that unchanged value as stale rather than switching the
    // editor back to it.
    if (querySceneId === previousQuerySceneId && activeSceneIdRef.current && querySceneId !== activeSceneIdRef.current) return
    if (shouldFollowSceneLink({
      querySceneId,
      activeSceneId,
      editorProjectId,
      effectiveProjectId,
      isDirty,
      isSaving,
    })) {
      void handleSelectScene(querySceneId)
    }
  }, [querySceneId, activeSceneId, editorProjectId, effectiveProjectId, isDirty, isSaving, handleSelectScene])

  useEffect(() => {
    if (!isDirty) return
    const timer = setTimeout(() => { void saveCurrentScene() }, 3000)
    return () => clearTimeout(timer)
  }, [scriptText, isDirty, saveCurrentScene])

  // ── Editor handlers ──────────────────────────────────────────────────────
  const handleTextChange = useCallback(
    (e: ChangeEvent<HTMLTextAreaElement>) => {
      setUndoStack((prev) => [...prev.slice(-49), scriptText])
      setRedoStack([])
      setScriptText(e.target.value)
      setIsDirty(true)
    },
    [scriptText],
  )

  const handleUndo = useCallback(() => {
    if (undoStack.length === 0) return
    const previous = undoStack[undoStack.length - 1]
    setRedoStack((prev) => [...prev, scriptText])
    setUndoStack((prev) => prev.slice(0, -1))
    setScriptText(previous)
    setIsDirty(true)
  }, [undoStack, scriptText])

  const handleRedo = useCallback(() => {
    if (redoStack.length === 0) return
    const next = redoStack[redoStack.length - 1]
    setUndoStack((prev) => [...prev, scriptText])
    setRedoStack((prev) => prev.slice(0, -1))
    setScriptText(next)
    setIsDirty(true)
  }, [redoStack, scriptText])

  const insertFountainPrefix = useCallback(
    (prefix: string) => {
      const textarea = editorRef.current
      if (!textarea) return
      const start = textarea.selectionStart
      const end = textarea.selectionEnd
      const before = scriptText.slice(0, start)
      const after = scriptText.slice(end)
      const newText = before + prefix + after
      setUndoStack((prev) => [...prev.slice(-49), scriptText])
      setRedoStack([])
      setScriptText(newText)
      setIsDirty(true)
      // Set cursor position after the prefix
      requestAnimationFrame(() => {
        textarea.focus()
        textarea.setSelectionRange(start + prefix.length, start + prefix.length)
      })
    },
    [scriptText],
  )

  const wrapSelection = useCallback(
    (before: string, after: string) => {
      const textarea = editorRef.current
      if (!textarea) return
      const start = textarea.selectionStart
      const end = textarea.selectionEnd
      const selected = scriptText.slice(start, end) || 'text'
      const newText = scriptText.slice(0, start) + before + selected + after + scriptText.slice(end)
      setUndoStack((prev) => [...prev.slice(-49), scriptText])
      setRedoStack([])
      setScriptText(newText)
      setIsDirty(true)
      requestAnimationFrame(() => {
        textarea.focus()
        textarea.setSelectionRange(start + before.length, start + before.length + selected.length)
      })
    },
    [scriptText],
  )

  // ── Export the current screenplay draft ─────────────────────────────────
  const handleGenerateScene = useCallback(async () => {
    if (!effectiveProjectId || !activeSceneId || generationLoading) return
    setGenerationLoading(true)
    setError('')
    setSuccess('')
    try {
      const job = await createJob(
        `${activeSceneId}_shot_001`,
        undefined,
        undefined,
        scriptText,
        undefined,
        { require_canonical_references: true },
      )
      await submitJob(job.id)
      setSuccess(`Generation started for ${activeScene?.scene_name || activeSceneId}.`)
    } catch (caught) {
      const raw = caught instanceof Error ? caught.message : String(caught)
      let message = raw
      try {
        const structured = JSON.parse(raw) as {
          message?: unknown
          metadata?: { recovery_action?: unknown }
        }
        if (structured && typeof structured === 'object' && typeof structured.message === 'string') {
          message = structured.message
          if (typeof structured.metadata?.recovery_action === 'string' && structured.metadata.recovery_action.trim()) {
            message += ` ${structured.metadata.recovery_action}`
          }
        }
      } catch {
        // The API may return a normal provider/network message; keep that
        // message visible without exposing an implementation stack trace.
      }
      setError(message.replace(/\\n?at .*/s, '').trim())
    } finally {
      setGenerationLoading(false)
    }
  }, [activeScene, activeSceneId, createJob, effectiveProjectId, generationLoading, scriptText, submitJob])

  // ── Export the current screenplay draft ─────────────────────────────────
  const handleExport = useCallback(async (format: ExportFormat) => {
    if (exporting) return
    setShowExportDropdown(false)
    setError('')
    setExporting(true)
    try {
      if (format === 'clipboard') {
        await navigator.clipboard.writeText(scriptText)
        setSuccess('Script draft copied to clipboard')
      } else if (format === 'txt') {
        const url = URL.createObjectURL(new Blob([scriptText], { type: 'text/plain;charset=utf-8' }))
        const link = document.createElement('a')
        link.href = url
        link.download = `${activeSceneId || 'screenplay'}-draft.txt`
        link.click()
        URL.revokeObjectURL(url)
        setSuccess('Script draft downloaded as text')
      } else {
        setError('Download a text draft to open in your screenplay editor for PDF or Final Draft export.')
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The script draft could not be exported.')
    } finally {
      setExporting(false)
    }
  }, [scriptText, activeSceneId, exporting])

  // ── AI suggestion handlers ───────────────────────────────────────────────
  const acceptSuggestion = useCallback(() => {
    if (!aiSuggestion) return
    setUndoStack((prev) => [...prev.slice(-49), scriptText])
    setRedoStack([])
    setScriptText((prev) => prev + '\n' + aiSuggestion.text)
    setIsDirty(true)
    setAiSuggestion((prev) => (prev ? { ...prev, accepted: true } : null))
    setTimeout(() => setAiSuggestion(null), 500)
  }, [aiSuggestion, scriptText])

  const dismissSuggestion = useCallback(() => {
    if (!aiSuggestion) return
    setAiSuggestion((prev) => (prev ? { ...prev, dismissed: true } : null))
    setTimeout(() => setAiSuggestion(null), 300)
  }, [aiSuggestion])

  // ── Script import ─────────────────────────────────────────────────────────
  const handleFileUpload = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (!file || !effectiveProjectId) return
      if (!/\.(txt|fountain)$/i.test(file.name)) {
        setError('Import a plain-text .txt or .fountain screenplay. Export PDF or Final Draft scripts to text first.')
        event.target.value = ''
        return
      }
      if (!(await saveCurrentScene())) return

      const reader = new FileReader()
      reader.onload = async (e) => {
        const text = e.target?.result
        if (typeof text !== 'string') return

        setUploadingScript(true)
        setError('')
        setSuccess('')
        try {
          const result = await generateScenes(effectiveProjectId, text.trim())
          if (result.error) {
            setError(result.error)
            return
          }
          const summary = result.project?.execution_summary as Record<string, unknown> | undefined
          const scenesArray = Array.isArray(summary?.scenes) ? summary.scenes : []
          const sceneCount = scenesArray.length

          setRecentImports((prev) => [
            {
              id: `${file.name}-${Date.now()}`,
              name: file.name,
              size: file.size,
              sceneCount,
              timestamp: new Date(),
            },
            ...prev.slice(0, 19),
          ])

          setSuccess(`Imported "${file.name}" — found ${sceneCount} scene${sceneCount !== 1 ? 's' : ''}`)
          await loadScenes()
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Failed to import script')
        } finally {
          setUploadingScript(false)
        }
      }
      reader.onerror = () => setError('The script file could not be read. Please try again.')
      reader.readAsText(file)
      // Reset file input so same file can be re-uploaded
      event.target.value = ''
    },
    [effectiveProjectId, loadScenes, saveCurrentScene],
  )

  // ── Add scene ─────────────────────────────────────────────────────────────
  const handleAddScene = useCallback(async () => {
    if (!effectiveProjectId) return
    setLoading(true)
    setError('')
    try {
      const payload: CreateScenePayload = {
        scene_name: `Scene ${scenes.length + 1}`,
        description: '',
        location: '',
        time_of_day: 'DAY',
        emotional_tone: 'neutral',
        characters: [],
        notes: '',
      }
      const result = await createScene(effectiveProjectId, payload)
      if (result.error) {
        setError(result.error)
      } else if (result.scene) {
        setSuccess('Scene created')
        await loadScenes()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create scene')
    } finally {
      setLoading(false)
    }
  }, [effectiveProjectId, scenes.length, loadScenes])

  // ── Intelligence handlers ─────────────────────────────────────────────────
  const handleStartDebate = useCallback(async () => {
    if (!effectiveProjectId || !activeSceneId) return
    setDebateRunning(true)
    setError('')
    setSceneDebateResult(null)
    try {
      const result = await triggerSceneDebate(effectiveProjectId, {
        scene_id: activeSceneId,
      })
      setSceneDebateResult(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Debate failed')
    } finally {
      setDebateRunning(false)
    }
  }, [effectiveProjectId, activeSceneId])

  const handleSimulateCharacter = useCallback(async () => {
    if (!effectiveProjectId || !selectedCharacter || !activeSceneId) return
    setCharacterSimulating(true)
    setError('')
    setCharacterMindResult(null)
    try {
      const result = await simulateCharacterMind(effectiveProjectId, {
        character_name: selectedCharacter,
        scene_id: activeSceneId,
      })
      setCharacterMindResult(result.simulation)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Character simulation failed')
    } finally {
      setCharacterSimulating(false)
    }
  }, [effectiveProjectId, selectedCharacter, activeSceneId])

  const handleSaveMemory = useCallback(async () => {
    if (!effectiveProjectId || !activeSceneId) {
      setError('Select a scene to save to memory')
      return
    }
    setMemorySaving(true)
    setError('')
    try {
      await saveCreativeDecisionMemory(effectiveProjectId, {
        project_id: effectiveProjectId,
        user_note: `Editor snapshot: scene "${activeScene?.scene_name || activeSceneId}"`,
        decision_type: 'creative_note',
        source_context: {
          scene_id: activeSceneId,
          screen_location: 'writers_room_editor',
        },
        inferred_tradeoff: 'not_inferred',
        inferred_tradeoff_explanation: 'Snapshot saved by writer during editing session.',
        editable: true,
        forgettable: true,
      })
      setMemorySavedChip(true)
      setTimeout(() => setMemorySavedChip(false), 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save memory')
    } finally {
      setMemorySaving(false)
    }
  }, [effectiveProjectId, activeSceneId, activeScene])

  // ── Character save handler ────────────────────────────────────────────────
  const handleSaveCharacter = useCallback(
    async (charId: string) => {
      const draft = editDrafts[charId]
      if (!draft || !effectiveProjectId) return
      setCharactersSaving((p) => ({ ...p, [charId]: true }))
      try {
        const result = await updateCharacter(effectiveProjectId, charId, draft)
        if (currentProjectRef.current !== effectiveProjectId) return
        if (result.error) throw new Error(result.error)
        if (result.character) {
          setCharacters((prev) => prev.map((c) => (c.id === charId ? result.character! : c)))
          setEditDrafts((prev) => {
            if (prev[charId] !== draft) return prev
            const next = { ...prev }
            delete next[charId]
            return next
          })
          await refreshCharacterLooks()
        }
      } catch (caught) {
        if (currentProjectRef.current === effectiveProjectId) setError(`Character profile not saved: ${characterLookError(caught)}`)
      } finally {
        setCharactersSaving((p) => ({ ...p, [charId]: false }))
      }
    },
    [editDrafts, effectiveProjectId, refreshCharacterLooks],
  )

  const handleCreateSkeletonCharacters = useCallback(async () => {
    if (!effectiveProjectId || charactersLoading || !charactersLoaded || creatingCharacters) return
    setCharactersLoading(true)
    setCreatingCharacters(true)
    setError('')
    try {
      for (const name of newCharacterNames) {
        const result = await createCharacterSkeleton(effectiveProjectId, name)
        if (result.error) throw new Error(result.error)
      }
      setSuccess('Character profiles created. Add their appearance and voice before storyboarding.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Character profiles could not be created.')
    } finally {
      try {
        await loadCharacters()
        await refreshCharacterLooks()
      } finally {
        setCreatingCharacters(false)
      }
    }
  }, [effectiveProjectId, charactersLoading, charactersLoaded, creatingCharacters, newCharacterNames, loadCharacters, refreshCharacterLooks])

  const handleUploadDescriptor = useCallback(
    async (charId: string) => {
      if (!effectiveProjectId) return
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.txt'
      input.onchange = async (e) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (!file) return
        setCharacterUploading((p) => ({ ...p, [charId]: true }))
        setError('')
        try {
          const result = await uploadCharacterDescriptor(effectiveProjectId, charId, file)
          if (currentProjectRef.current !== effectiveProjectId) return
          if (result && result.character) {
            const char = result.character
            setCharacters((prev) => prev.map((c) => (c.id === charId ? char : c)))
            setEditDrafts((p) => ({
              ...p,
              [charId]: {
                look: char.look || '',
                energy: char.energy || '',
                visual_prompt_summary: char.visual_prompt_summary || '',
                age: char.age || '',
              },
            }))
            setSuccess(`Character "${char.name}" updated from descriptor`)
            await refreshCharacterLooks()
          } else if (result && result.error) {
            setError(result.error)
          }
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Failed to upload descriptor')
        } finally {
          setCharacterUploading((p) => ({ ...p, [charId]: false }))
        }
      }
      input.click()
    },
    [effectiveProjectId, refreshCharacterLooks],
  )

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="relative min-h-screen w-full">
      {/* 3D environment */}
      <div className="pointer-events-none fixed inset-0">
        <PageScene />
      </div>

      {/* UI overlay */}
      <div className="relative z-10">
        <StudioShell title="Writer's Room" subtitle="The Page — Draft and manage your script" beforeNavigate={prepareRoomHandoff} transparent>
          <ProjectGuard>
            <ProjectContextBar roomName="writer's room" compact />

            {/* Status bars */}
            <div className="px-4 pt-2">
              {error && (
                <div className="mb-2 rounded-lg border border-rose-400/40 bg-rose-500/10 px-4 py-2 text-sm text-rose-200">
                  {error}
                </div>
              )}
              {success && (
                <div className="mb-2 rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-200">
                  {success}
                </div>
              )}
              {!backendHealthy && effectiveProjectId && (
                <div className="mb-2 rounded-lg border border-amber-400/40 bg-amber-500/10 px-4 py-2">
                  <div className="flex items-center justify-between">
                    <div className="text-xs text-amber-200">Studio is starting up...</div>
                    <button
                      type="button"
                      onClick={retryHealthCheck}
                      disabled={healthCheckLoading}
                      className="rounded border border-amber-300/50 bg-amber-500/14 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-amber-100"
                    >
                      {healthCheckLoading ? 'Checking...' : 'Retry'}
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div className="mx-auto max-w-[1400px] px-4 pb-10 pt-5 md:px-6">
              <header className="mb-6">
                <p className="text-[11px] uppercase tracking-[0.2em] text-amber-200/80">The Page</p>
                <h1 className="mt-2 text-2xl font-medium tracking-tight text-zinc-100 md:text-3xl">Give the film its voice.</h1>
                <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-400">Shape the script, prepare the profiles, then cast and lock your characters before you storyboard.</p>
              </header>
              <nav aria-label="Writing steps" className="mb-6 grid grid-cols-1 gap-2 border-b border-white/10 pb-4 sm:flex sm:flex-wrap">
                <button type="button" onClick={() => setRightTab('scenes')} aria-current={rightTab === 'scenes' ? 'step' : undefined} className={rightTab === 'scenes' ? 'rounded-md border border-amber-200/40 bg-amber-200/5 px-4 py-3 text-sm text-amber-100' : 'rounded-md border border-white/10 px-4 py-3 text-sm text-zinc-400'}>1. Script</button>
                <button type="button" onClick={() => setRightTab('characters')} aria-current={rightTab === 'characters' ? 'step' : undefined} className={rightTab === 'characters' ? 'rounded-md border border-amber-200/40 bg-amber-200/5 px-4 py-3 text-sm text-amber-100' : 'rounded-md border border-white/10 px-4 py-3 text-sm text-zinc-400'}>2. Character profiles{newCharacterNames.length > 0 && <span className="ml-2 text-xs text-amber-200">· {newCharacterNames.length} to add</span>}</button>
                <button type="button" onClick={() => setRightTab('looks')} aria-current={rightTab === 'looks' ? 'step' : undefined} className={rightTab === 'looks' ? 'rounded-md border border-amber-200/40 bg-amber-200/5 px-4 py-3 text-sm text-amber-100' : 'rounded-md border border-white/10 px-4 py-3 text-sm text-zinc-400'}>3. Lock character looks</button>
              </nav>
              <section aria-label="Script workspace" className={rightTab === 'scenes' ? 'grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]' : 'hidden'}>
                <div className="min-w-0 space-y-3">
                {/* Editor header */}
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 bg-zinc-950/80 px-4 py-3">
                  <div className="text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-primary)' }}>
                    THE PAGE
                  </div>
                  <div className="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-3">
                    {/* Scene selector */}
                    {scenes.length > 0 ? (
                      <select
                        value={activeSceneId || ''}
                        aria-label="Current script scene"
                        onChange={(e) => handleSelectScene(e.target.value)}
                        className="min-w-0 max-w-full rounded-md border border-white/15 bg-zinc-950 px-3 py-2 text-xs outline-none"
                        style={{ color: 'var(--color-on-surface)' }}
                      >
                        {scenes.map((scene) => (
                          <option key={scene.scene_id} value={scene.scene_id} className="bg-zinc-900">
                            {scene.scene_name} {scene.location ? `(${scene.location})` : ''}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                        No scenes loaded
                      </span>
                    )}
                    <button type="button" onClick={() => void saveCurrentScene()} disabled={isSaving || !isDirty} aria-busy={isSaving || undefined} className="inline-flex items-center gap-2 rounded-md border border-amber-200/30 bg-amber-200/5 px-3 py-2 text-xs text-amber-100 disabled:opacity-40"><Save size={13} />{isSaving ? 'Saving…' : 'Save script'}</button>
                    <button type="button" onClick={() => void handleGenerateScene()} disabled={generationLoading || !activeSceneId || !scriptText.trim()} aria-busy={generationLoading || undefined} className="inline-flex items-center gap-2 rounded-md border border-emerald-300/30 bg-emerald-300/10 px-3 py-2 text-xs text-emerald-100 disabled:opacity-40">{generationLoading ? 'Generating…' : 'Generate selected scene'}</button>
                    {/* Autosave indicator */}
                    <span
                      className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.1em]"
                      style={{ color: 'var(--color-outline-variant)' }}
                    >
                      {isSaving ? (
                        <>
                          <span className="relative flex h-2 w-2">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
                          </span>
                          SAVING
                        </>
                      ) : isDirty ? (
                        <span className="text-amber-200">Unsaved changes</span>
                      ) : lastSavedAt ? (
                        <>
                          <span className="h-2 w-2 rounded-full bg-emerald-400" />
                          SAVED {timeAgo(lastSavedAt)}
                        </>
                      ) : (
                        <>
                          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: 'var(--color-outline)' }} />
                          {activeSceneId ? 'Loaded from project' : 'Choose a scene'}
                        </>
                      )}
                    </span>
                  </div>
                </div>

                {/* Toolbar */}
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 bg-zinc-950/80 px-3 py-2">
                  {/* Left group — Fountain format */}
                  <div className="flex items-center gap-1">
                    {FOUNTAIN_PREFIXES.map((item) => (
                      <button
                        key={item.label}
                        type="button"
                        onClick={() => insertFountainPrefix(item.prefix)}
                        title={item.shortcut}
                        className="status-chip rounded border px-2 py-1 text-[11px] font-bold uppercase tracking-[0.12em] transition-all hover:bg-white/10"
                        style={{
                          borderColor: 'rgba(255,255,255,0.1)',
                          color: 'var(--color-on-surface-variant)',
                        }}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>

                  {/* Right group — formatting / actions */}
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => wrapSelection('**', '**')}
                      className="rounded p-1.5 transition-all hover:bg-white/10"
                      title="Bold"
                      style={{ color: 'var(--color-on-surface-variant)' }}
                    >
                      <Bold size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => wrapSelection('*', '*')}
                      className="rounded p-1.5 transition-all hover:bg-white/10"
                      title="Italic"
                      style={{ color: 'var(--color-on-surface-variant)' }}
                    >
                      <Italic size={14} />
                    </button>
                    <span className="mx-1 h-4 w-px opacity-20" style={{ backgroundColor: 'var(--color-on-surface)' }} />
                    <button
                      type="button"
                      onClick={handleUndo}
                      disabled={undoStack.length === 0}
                      className="rounded p-1.5 transition-all hover:bg-white/10 disabled:opacity-30"
                      title="Undo"
                      style={{ color: 'var(--color-on-surface-variant)' }}
                    >
                      <Undo2 size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={handleRedo}
                      disabled={redoStack.length === 0}
                      className="rounded p-1.5 transition-all hover:bg-white/10 disabled:opacity-30"
                      title="Redo"
                      style={{ color: 'var(--color-on-surface-variant)' }}
                    >
                      <Redo2 size={14} />
                    </button>
                    <span className="mx-1 h-4 w-px opacity-20" style={{ backgroundColor: 'var(--color-on-surface)' }} />
                    {/* Export dropdown */}
                    <div className="relative" ref={exportRef}>
                      <button
                        type="button"
                        onClick={() => setShowExportDropdown((p) => !p)}
                        disabled={exporting}
                        aria-busy={exporting || undefined}
                        className="flex items-center gap-1 rounded px-2 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] transition-all hover:bg-white/10 disabled:opacity-50"
                        style={{ color: 'var(--color-on-surface-variant)' }}
                      >
                        Export
                        <ChevronDown size={12} />
                      </button>
                      {showExportDropdown && (
                        <div
                          className="glass-panel absolute right-0 top-full mt-1 w-48 overflow-hidden rounded-xl py-1 shadow-2xl"
                          style={{ zIndex: 50 }}
                        >
                          {([
                            { key: 'txt' as ExportFormat, icon: FileText, label: 'Download TXT' },
                            { key: 'clipboard' as ExportFormat, icon: Copy, label: 'Copy to Clipboard' },
                          ]).map((item) => (
                            <button
                              key={item.key}
                              type="button"
                              onClick={() => void handleExport(item.key)}
                              disabled={exporting}
                              aria-busy={exporting || undefined}
                              className="flex w-full items-center gap-3 px-4 py-2 text-[11px] transition-all hover:bg-white/5 disabled:opacity-50"
                              style={{ color: 'var(--color-on-surface)' }}
                            >
                              <item.icon size={14} className="shrink-0" style={{ color: 'var(--color-on-surface-variant)' }} />
                              {item.label}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Script textarea */}
                <div className="relative min-h-[460px] rounded-lg border border-white/10 bg-zinc-950/85">
                  <textarea
                    ref={editorRef}
                    value={scriptText}
                    onChange={handleTextChange}
                    placeholder={activeScene ? 'Write your script here...' : 'Select or create a scene to start writing...'}
                    aria-label="Scene script" className="min-h-[460px] w-full resize-y bg-transparent p-4 text-sm leading-7 text-zinc-100 outline-none focus-visible:ring-1 focus-visible:ring-amber-200/30 md:p-6"
                    style={{
                      color: 'var(--color-on-surface)',
                      fontFamily: 'var(--font-jetbrains)',
                      lineHeight: '1.8',
                    }}
                    disabled={!activeScene}
                  />

                  {/* Word count */}
                  <div
                    className="absolute bottom-3 right-4 text-xs font-semibold uppercase tracking-[0.1em]"
                    style={{ color: 'var(--color-outline-variant)' }}
                  >
                    {estimateWordCount(scriptText)} words
                  </div>

                  {/* AI suggestion bubble */}
                  {aiSuggestion && !aiSuggestion.accepted && !aiSuggestion.dismissed && (
                    <div className="absolute bottom-12 left-4 right-4 glass-panel rounded-xl border p-4 shadow-2xl" style={{ borderColor: 'rgba(255,209,101,0.3)' }}>
                      <div className="mb-2 flex items-center gap-2">
                        <Brain size={14} style={{ color: 'var(--color-primary)' }} />
                        <span
                          className="text-xs font-bold uppercase tracking-[0.12em]"
                          style={{ color: 'var(--color-primary)' }}
                        >
                          AI Suggestion
                        </span>
                      </div>
                      <p className="mb-3 text-xs leading-relaxed" style={{ color: 'var(--color-on-surface)' }}>
                        {aiSuggestion.text}
                      </p>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={acceptSuggestion}
                          className="rounded-lg px-3 py-1.5 text-xs font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02]"
                          style={{
                            background: 'rgba(255,209,101,0.15)',
                            color: 'var(--color-primary)',
                            border: '1px solid rgba(255,209,101,0.3)',
                          }}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          onClick={dismissSuggestion}
                          className="rounded-lg px-3 py-1.5 text-xs font-bold uppercase tracking-[0.12em] transition-all hover:bg-white/10"
                          style={{ color: 'var(--color-on-surface-variant)' }}
                        >
                          Reject
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Director's Notes — read-only reference from Screening Room */}
                {activeScene?.notes && (
                  <div className="glass-panel rounded-xl p-4">
                    <div
                      className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em]"
                      style={{ color: 'var(--color-primary)' }}
                    >
                      DIRECTOR'S NOTES
                    </div>
                    <div className="border-t pt-2" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                      <p className="text-[12px] leading-relaxed" style={{ color: 'var(--color-on-surface-variant)' }}>
                        {activeScene.notes}
                      </p>
                    </div>
                  </div>
                )}

                {/* Character Mind Simulation */}
                {characterMindResult && (
                  <div className="glass-panel rounded-xl p-4">
                    <div
                      className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em]"
                      style={{ color: 'var(--color-secondary)' }}
                    >
                      CHARACTER MIND — {selectedCharacter}
                    </div>
                    <div className="border-t pt-2" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                      <p className="text-[12px] leading-relaxed italic" style={{ color: 'var(--color-on-surface-variant)' }}>
                        {characterMindResult}
                      </p>
                    </div>
                  </div>
                )}
              </div>
                <aside className="min-w-0 space-y-4">
                  <div className="glass-panel rounded-xl p-4">
                  <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--color-primary)' }}>
                    Import a screenplay
                  </div>

                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".txt,.fountain"
                    onChange={handleFileUpload}
                    className="hidden"
                  />

                  <button
                    type="button"
                    disabled={uploadingScript || !effectiveProjectId}
                    onClick={() => fileInputRef.current?.click()}
                    className="glass-panel flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] transition-all duration-200 hover:scale-[1.02] disabled:opacity-50"
                    style={{ color: 'var(--color-on-surface)' }}
                  >
                    <UploadCloud size={18} />
                    {uploadingScript ? 'Importing...' : 'Import Script'}
                  </button>

                  {/* Recent imports */}
                  {recentImports.length > 0 && (
                    <div className="mt-3 space-y-1">
                      <div
                        className="mb-1 text-xs font-semibold uppercase tracking-[0.12em]"
                        style={{ color: 'var(--color-on-surface-variant)' }}
                      >
                        Recent Imports
                      </div>
                      {recentImports.map((row) => (
                        <div
                          key={row.id}
                          className="flex items-center gap-2 rounded px-2 py-1 text-[11px] transition-colors hover:bg-white/5"
                          style={{ color: 'var(--color-on-surface-variant)' }}
                        >
                          <FileText size={12} className="shrink-0" />
                          <span className="truncate flex-1">{row.name}</span>
                          <span className="shrink-0 opacity-60">{row.sceneCount} scenes</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {recentImports.length === 0 && (
                    <div
                      className="mt-3 text-[11px]"
                      style={{ color: 'var(--color-on-surface-variant)' }}
                    >
                      No imports yet. Upload a .txt or .fountain screenplay.
                    </div>
                  )}
                </div>
                  <details className="rounded-lg border border-white/10 bg-zinc-950/60 p-4" open={scenes.length === 0}><summary className="cursor-pointer text-sm text-zinc-300">Scene outline · {scenes.length} scenes</summary><div className="mt-3 space-y-3">{rightTab === 'scenes' && (
                  <>
                    <div className="glass-panel flex items-center justify-between rounded-xl px-4 py-3">
                      <span className="text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>
                        SCENE LIST
                      </span>
                      <button
                        type="button"
                        onClick={handleAddScene}
                        disabled={loading || !effectiveProjectId}
                        aria-busy={loading || undefined}
                        className="rounded-lg p-1.5 transition-all hover:bg-white/10 disabled:opacity-50"
                        title="Add scene"
                        style={{ color: 'var(--color-primary)' }}
                      >
                        <Plus size={16} />
                      </button>
                    </div>
                    {loading && scenes.length === 0 ? (
                      <div className="flex items-center justify-center py-12">
                        <div className="h-5 w-5 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
                      </div>
                    ) : scenes.length === 0 ? (
                      <div className="glass-panel flex flex-col items-center justify-center rounded-xl px-4 py-12 text-center">
                        <Edit3 size={24} className="mb-3 opacity-30" style={{ color: 'var(--color-on-surface-variant)' }} />
                        <p className="text-xs" style={{ color: 'var(--color-on-surface-variant)' }}>
                          No scenes yet. Import a script or add one manually.
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        {scenes.map((scene, index) => {
                          const isActive = scene.scene_id === activeSceneId
                          const wordCount = estimateWordCount(scene.description || '')
                          return (
                            <button
                              key={scene.scene_id}
                              type="button"
                              onClick={() => void selectSceneFromList(scene.scene_id)}
                              disabled={switchingSceneId !== null}
                              aria-busy={switchingSceneId === scene.scene_id || undefined}
                              className={`flex w-full items-start gap-3 rounded-xl px-4 py-3 text-left transition-all disabled:cursor-progress disabled:opacity-70 ${
                                isActive
                                  ? 'border-l-2 shadow-[inset_0_0_20px_rgba(255,209,101,0.06)]'
                                  : 'hover:bg-white/5'
                              }`}
                              style={{
                                borderLeftColor: isActive ? 'var(--color-primary)' : 'transparent',
                                background: isActive ? 'rgba(255,209,101,0.04)' : 'transparent',
                              }}
                            >
                              <span
                                className="status-chip mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[11px] font-bold"
                                style={{
                                  background: isActive ? 'rgba(255,209,101,0.15)' : 'rgba(255,255,255,0.06)',
                                  color: isActive ? 'var(--color-primary)' : 'var(--color-outline)',
                                }}
                              >
                                {String(index + 1).padStart(2, '0')}
                              </span>
                              <div className="min-w-0 flex-1">
                                <div
                                  className="truncate text-[12px] font-medium leading-tight"
                                  style={{
                                    color: isActive ? 'var(--color-primary)' : 'var(--color-on-surface)',
                                  }}
                                >
                                  {scene.scene_name || `Scene ${index + 1}`}
                                </div>
                                <div
                                  className="mt-0.5 text-xs"
                                  style={{ color: 'var(--color-on-surface-variant)' }}
                                >
                                  {scene.location || 'No location'} · {wordCount} words
                                </div>
                              </div>
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </>
                )}</div></details>
                  <details className="rounded-lg border border-white/10 bg-zinc-950/60 p-4"><summary className="cursor-pointer text-sm text-zinc-300">Creative support</summary><p className="mt-3 text-xs leading-relaxed text-zinc-400">Explore a debate or a character’s motivation when you need another perspective.</p><div className="pt-3"><div className="glass-panel rounded-xl p-4">
                  <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--color-secondary)' }}>
                    INTELLIGENCE
                  </div>

                  <div className="space-y-2">
                    {/* Debate Mode */}
                    <div>
                      <button
                        type="button"
                        onClick={() => setDebateMode((p) => !p)}
                        className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] transition-all ${
                          debateMode
                            ? 'bg-secondary-container/20 shadow-[0_0_12px_rgba(76,215,246,0.3)]'
                            : 'hover:bg-white/5'
                        }`}
                        style={{
                          color: debateMode ? 'var(--color-secondary)' : 'var(--color-on-surface)',
                        }}
                      >
                        <Brain size={16} />
                        Debate Mode
                        {debateMode && <span className="ml-auto h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_6px_rgba(76,215,246,0.6)]" />}
                      </button>

                      {debateMode && (
                        <div className="mt-2 space-y-2 rounded-lg border p-3" style={{ borderColor: 'rgba(76,215,246,0.2)' }}>
                          <p className="text-xs text-zinc-500 leading-relaxed">
                            Debates two opposing directorial perspectives — Restraint vs Urgency — on the current scene.
                          </p>
                          <button
                            type="button"
                            onClick={handleStartDebate}
                            disabled={debateRunning || !activeSceneId}
                            aria-busy={debateRunning || undefined}
                            className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.02] disabled:opacity-50"
                            style={{
                              background: 'rgba(76,215,246,0.15)',
                              color: 'var(--color-secondary)',
                              border: '1px solid rgba(76,215,246,0.3)',
                            }}
                          >
                            {debateRunning ? (
                              <>
                                <div className="h-3 w-3 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
                                Debating...
                              </>
                            ) : (
                              'START DEBATE'
                            )}
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Character Mind */}
                    <div>
                      <button
                        type="button"
                        onClick={() => setCharacterMindMode((p) => !p)}
                        className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] transition-all ${
                          characterMindMode
                            ? 'bg-secondary-container/20 shadow-[0_0_12px_rgba(76,215,246,0.3)]'
                            : 'hover:bg-white/5'
                        }`}
                        style={{
                          color: characterMindMode ? 'var(--color-secondary)' : 'var(--color-on-surface)',
                        }}
                      >
                        <UserCheck size={16} />
                        Character Mind
                        {characterMindMode && <span className="ml-auto h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_6px_rgba(76,215,246,0.6)]" />}
                      </button>

                      {characterMindMode && (
                        <div className="mt-2 space-y-2 rounded-lg border p-3" style={{ borderColor: 'rgba(76,215,246,0.2)' }}>
                          <select
                            value={selectedCharacter}
                            onChange={(e) => setSelectedCharacter(e.target.value)}
                            className="w-full rounded border bg-transparent p-2 text-xs outline-none"
                            style={{ borderColor: 'rgba(76,215,246,0.2)', color: 'var(--color-on-surface)' }}
                          >
                            <option value="" disabled>
                              Select character...
                            </option>
                            {allCharacters.map((char) => (
                              <option key={char} value={char} className="bg-zinc-900">
                                {char}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            onClick={handleSimulateCharacter}
                            disabled={characterSimulating || !selectedCharacter}
                            aria-busy={characterSimulating || undefined}
                            className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.02] disabled:opacity-50"
                            style={{
                              background: 'rgba(76,215,246,0.15)',
                              color: 'var(--color-secondary)',
                              border: '1px solid rgba(76,215,246,0.3)',
                            }}
                          >
                            {characterSimulating ? (
                              <>
                                <div className="h-3 w-3 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
                                Simulating...
                              </>
                            ) : (
                              'SIMULATE'
                            )}
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Director's Memory */}
                    <div>
                      <button
                        type="button"
                        onClick={handleSaveMemory}
                        disabled={memorySaving || !effectiveProjectId}
                        aria-busy={memorySaving || undefined}
                        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] transition-all hover:bg-white/5 disabled:opacity-50"
                        style={{ color: 'var(--color-on-surface)' }}
                      >
                        {memorySaving ? <Loader2 size={16} className="animate-spin" /> : <MemoryStick size={16} />}
                        {memorySaving ? 'Saving decision…' : 'Save this decision to project memory'}
                        {memorySavedChip && (
                          <span className="ml-auto flex items-center gap-1 rounded bg-emerald-500/20 px-2 py-0.5 text-[11px] font-bold uppercase tracking-[0.12em] text-emerald-400">
                            <CheckCircle2 size={10} />
                            SAVED
                          </span>
                        )}
                        {memorySaving && (
                          <div className="ml-auto h-3 w-3 animate-spin rounded-full border-2 border-emerald-400 border-t-transparent" />
                        )}
                      </button>
                    </div>
                  </div>
                </div></div></details>
                </aside>
              </section>
              <section aria-label="Production character profiles" className={rightTab === 'characters' ? 'space-y-5' : 'hidden'}>
                <div><h2 className="text-lg font-medium text-zinc-100">Make your characters recognizable.</h2><p className="mt-1 max-w-2xl text-sm leading-relaxed text-zinc-400">Save appearance, energy, render description, and voice here. In the next step, generate casting options or upload portraits, then approve each physical look.</p></div>
                {rightTab === 'characters' && (
                  <div className="flex flex-col gap-3">
                    {/* New characters banner */}
                    {newCharacterNames.length > 0 && (
                      <div className="glass-panel rounded-xl border px-4 py-3" style={{ borderColor: 'rgba(251,191,36,0.3)' }}>
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="text-xs font-bold uppercase tracking-[0.12em] text-amber-400">
                              New characters detected
                            </div>
                            <div className="mt-1 text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                              {newCharacterNames.join(', ')}
                            </div>
                            <div className="mt-1 text-xs" style={{ color: 'var(--color-on-surface-variant)' }}>
                              Add descriptions to improve render quality.
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={handleCreateSkeletonCharacters}
                            disabled={creatingCharacters || charactersLoading || !charactersLoaded || !effectiveProjectId}
                            aria-busy={creatingCharacters || undefined}
                            className="shrink-0 rounded-lg px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02] disabled:opacity-50"
                            style={{
                              background: 'rgba(251,191,36,0.15)',
                              color: '#fbbf24',
                              border: '1px solid rgba(251,191,36,0.3)',
                            }}
                          >
                            {creatingCharacters ? 'Adding…' : 'Add'}
                          </button>
                        </div>
                      </div>
                    )}

                    {charactersLoading ? (
                      <div className="flex items-center justify-center py-12">
                        <div className="h-5 w-5 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
                      </div>
                    ) : characters.length === 0 ? (
                      <div className="glass-panel flex flex-col items-center justify-center rounded-xl px-4 py-12 text-center">
                        <Users size={24} className="mb-3 opacity-30" style={{ color: 'var(--color-on-surface-variant)' }} />
                        <p className="text-xs" style={{ color: 'var(--color-on-surface-variant)' }}>
                          No character descriptions yet.
                        </p>
                      </div>
                    ) : (
                      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
                        {characters.map((char) => {
                          const draft = editDrafts[char.id] || {}
                          const savedLook = characterLooks.looks.find((item) => item.character_id === char.id)
                          const appearanceLocked = savedLook?.status === 'locked'
                          const appearanceUnavailable = !savedLook || characterLooks.loading || Boolean(characterLooks.error)
                          const isSaving = charactersSaving[char.id] || false
                          const look = draft.look ?? char.look ?? ''
                          const energy = draft.energy ?? char.energy ?? ''
                          const vps = draft.visual_prompt_summary ?? char.visual_prompt_summary ?? ''
                          const age = draft.age ?? char.age ?? ''

                          const hasChanges =
                            editDrafts[char.id] !== undefined &&
                            Object.keys(editDrafts[char.id] || {}).length > 0

                          return (
                            <div
                              key={char.id}
                              className="glass-panel rounded-xl p-4"
                            >
                              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                                <div className="flex items-center gap-2">
                                  <span className="text-[12px] font-bold" style={{ color: 'var(--color-on-surface)' }}>
                                    {char.name}
                                  </span>
                                  {age && (
                                    <span className="text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                                      ({age})
                                    </span>
                                  )}
                                </div>
                                <div className="flex items-center gap-2">
                                  <button
                                    type="button"
                                    onClick={() => void handleUploadDescriptor(char.id)}
                                    disabled={characterUploading[char.id] || appearanceLocked || appearanceUnavailable}
                                    aria-busy={characterUploading[char.id] || undefined}
                                    className="flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02] disabled:opacity-50"
                                    style={{
                                      background: 'rgba(76,175,80,0.15)',
                                      color: '#4caf50',
                                      border: '1px solid rgba(76,175,80,0.3)',
                                    }}
                                    title="Upload .txt descriptor"
                                  >
                                    {characterUploading[char.id] ? (
                                      <div className="h-3 w-3 animate-spin rounded-full border-2 border-green-400 border-t-transparent" />
                                    ) : (
                                      <UploadCloud size={10} />
                                    )}
                                    Upload
                                  </button>
                                  {hasChanges && (
                                    <button
                                      type="button"
                                      onClick={() => void handleSaveCharacter(char.id)}
                                      disabled={isSaving}
                                      aria-busy={isSaving || undefined}
                                      className="flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02] disabled:opacity-50"
                                      style={{
                                        background: 'rgba(255,209,101,0.15)',
                                        color: 'var(--color-primary)',
                                        border: '1px solid rgba(255,209,101,0.3)',
                                      }}
                                    >
                                      {isSaving ? (
                                        <div className="h-3 w-3 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
                                      ) : (
                                        <Save size={10} />
                                      )}
                                      Save
                                    </button>
                                  )}
                                </div>
                              </div>

                              {appearanceLocked && <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded border border-amber-200/20 bg-amber-200/5 px-3 py-2"><span className="text-xs text-amber-100">Physical look locked · version {savedLook.version}</span><button type="button" onClick={() => { setSearchParams((previous) => { const next = new URLSearchParams(previous); next.set('step', 'looks'); next.set('character', char.id); return next }, { replace: true }); void refreshCharacterLooks() }} disabled={characterLooks.busy} aria-busy={characterLooks.busy || undefined} className="py-1 text-xs text-zinc-200 underline underline-offset-4 disabled:opacity-50">Review or revise look</button></div>}
                              {appearanceUnavailable && <p className="mb-3 text-xs text-zinc-400">{characterLooks.error ? 'Appearance approval could not be checked. Reload saved looks in step 3.' : 'Checking appearance approval…'}</p>}
                              {/* Voice assignment */}
                              <div className="mb-2 flex items-center justify-between rounded-lg border border-zinc-800/80 bg-zinc-900/30 px-3 py-2">
                                <div className="flex items-center gap-2">
                                  <Mic size={12} style={{ color: 'var(--color-on-surface-variant)' }} />
                                  <span className="text-xs font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-outline-variant)' }}>
                                    Voice
                                  </span>
                                  <span className="text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                                    {voiceUpdates[char.id]?.voiceName
                                      || char.voice_name
                                      || char.elevenlabs_voice_name
                                      || 'Not cast'}
                                    {(voiceUpdates[char.id]?.provider || char.voice_provider) && (
                                      <span className="ml-1 opacity-70">
                                        ({voiceUpdates[char.id]?.provider || char.voice_provider})
                                      </span>
                                    )}
                                  </span>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => setVoicePickerChar(char)}
                                  className="flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02]"
                                  style={{
                                    background: 'rgba(6,182,212,0.12)',
                                    color: '#22d3ee',
                                    border: '1px solid rgba(6,182,212,0.25)',
                                  }}
                                >
                                  <Mic size={10} />
                                  Cast
                                </button>
                              </div>

                              <div className="space-y-2">
                                <label className="block text-xs text-zinc-400">Age<input aria-label={`${char.name} age`} value={age} disabled={appearanceLocked || appearanceUnavailable} onChange={(event) => setEditDrafts((previous) => ({ ...previous, [char.id]: { ...(previous[char.id] || {}), age: event.target.value } }))} className="mt-1 block w-full rounded border border-white/10 bg-transparent p-2 text-xs text-zinc-200 outline-none focus:border-amber-400/60 disabled:opacity-60" /></label>
                                <div>
                                  <div className="mb-0.5 text-[11px] font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-outline-variant)' }}>
                                    Look
                                  </div>
                                  <textarea
                                    value={look}
                                    disabled={appearanceLocked || appearanceUnavailable}
                                  aria-label={`${char.name} appearance`}
                                    onChange={(e) =>
                                      setEditDrafts((p) => ({
                                        ...p,
                                        [char.id]: { ...(p[char.id] || {}), look: e.target.value },
                                      }))
                                    }
                                    rows={2}
                                    className="w-full resize-none rounded border bg-transparent p-2 text-[11px] outline-none transition focus:border-amber-400/60"
                                    style={{ borderColor: 'rgba(255,255,255,0.1)', color: 'var(--color-on-surface)' }}
                                  />
                                </div>
                                <div>
                                  <div className="mb-0.5 text-[11px] font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-outline-variant)' }}>
                                    Energy
                                  </div>
                                  <textarea
                                    value={energy}
                                  aria-label={`${char.name} energy`}
                                    onChange={(e) =>
                                      setEditDrafts((p) => ({
                                        ...p,
                                        [char.id]: { ...(p[char.id] || {}), energy: e.target.value },
                                      }))
                                    }
                                    rows={2}
                                    className="w-full resize-none rounded border bg-transparent p-2 text-[11px] outline-none transition focus:border-amber-400/60"
                                    style={{ borderColor: 'rgba(255,255,255,0.1)', color: 'var(--color-on-surface)' }}
                                  />
                                </div>
                                <div>
                                  <div className="mb-0.5 text-[11px] font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-outline-variant)' }}>
                                    Visual Prompt Summary
                                  </div>
                                  <textarea
                                    value={vps}
                                    disabled={appearanceLocked || appearanceUnavailable}
                                  aria-label={`${char.name} render description`}
                                    onChange={(e) =>
                                      setEditDrafts((p) => ({
                                        ...p,
                                        [char.id]: { ...(p[char.id] || {}), visual_prompt_summary: e.target.value },
                                      }))
                                    }
                                    rows={2}
                                    className="w-full resize-none rounded border bg-transparent p-2 text-[11px] outline-none transition focus:border-amber-400/60"
                                    style={{ borderColor: 'rgba(255,255,255,0.1)', color: 'var(--color-on-surface)' }}
                                  />
                                </div>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )}
              </section>
              {rightTab === 'looks' && <CharacterLookApproval controller={characterLooks} selectedId={selectedLookCharacter} onSelect={(id) => setSearchParams((previous) => { const next = new URLSearchParams(previous); next.set('character', id); return next }, { replace: true })} onProfiles={() => setRightTab('characters')} hasProfileDrafts={Object.keys(editDrafts).length > 0} />}
              <div className="mt-7 flex flex-wrap items-center justify-between gap-4 border-t border-white/10 pt-5">
                <p className="max-w-xl text-xs leading-relaxed text-zinc-400">{rightTab === 'scenes' ? 'Edits save while you work. Review character profiles before planning your shots.' : Object.keys(editDrafts).length ? 'Save the changed character profiles before continuing.' : rightTab === 'characters' ? 'Next, cast each character with generated options or your own portraits, then lock the look.' : 'Your saved script, profiles, and approved looks stay with this film in Previs.'}</p>
                {rightTab === 'scenes' ? <button type="button" onClick={() => setRightTab('characters')} className="rounded-md bg-amber-200 px-4 py-3 text-sm font-medium text-zinc-950 hover:bg-amber-100">Review character profiles →</button> : rightTab === 'characters' ? <button type="button" disabled={Object.keys(editDrafts).length > 0 || Object.values(charactersSaving).some(Boolean)} onClick={() => setRightTab('looks')} className="rounded-md bg-amber-200 px-4 py-3 text-sm font-medium text-zinc-950 hover:bg-amber-100 disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-zinc-500">Review and lock character looks →</button> : <button type="button" disabled={isSaving || !activeSceneId || Object.keys(editDrafts).length > 0 || characterLooks.busy} onClick={async () => { if (await saveCurrentScene()) navigate(withProductionContext('/studio/previs', { projectId: effectiveProjectId, sceneId: activeSceneId, shotNumber: Number(searchParams.get('shot')) || null })) }} aria-busy={isSaving || characterLooks.busy || undefined} className="rounded-md bg-amber-200 px-4 py-3 text-sm font-medium text-zinc-950 hover:bg-amber-100 disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-zinc-500">Continue to storyboard →</button>}
              </div>
            </div>

            {/* Debate Modal (existing 5-agent) */}
            {activeDebate && (
              <DirectorDebatePanel
                projectId={effectiveProjectId || ''}
                debate={activeDebate}
                onDismiss={() => setActiveDebate(null)}
              />
            )}

            {/* Scene Debate Modal (Restraint vs Urgency) */}
            {sceneDebateResult && (
              <WritersDebateModal
                projectId={effectiveProjectId || ''}
                restraint={sceneDebateResult.restraint}
                urgency={sceneDebateResult.urgency}
                sceneId={sceneDebateResult.scene_id}
                onDismiss={() => setSceneDebateResult(null)}
              />
            )}

            {/* Voice Picker Modal */}
            {voicePickerChar && (
              <VoicePicker
                isOpen={!!voicePickerChar}
                onClose={() => setVoicePickerChar(null)}
                projectId={effectiveProjectId || ''}
                characterId={voicePickerChar.id}
                characterName={voicePickerChar.name}
                currentVoiceId={voiceUpdates[voicePickerChar.id]?.voiceId || voicePickerChar.voice_id || voicePickerChar.elevenlabs_voice_id || null}
                currentVoiceName={voiceUpdates[voicePickerChar.id]?.voiceName || voicePickerChar.voice_name || voicePickerChar.elevenlabs_voice_name || null}
                currentProvider={voiceUpdates[voicePickerChar.id]?.provider || voicePickerChar.voice_provider || null}
                currentSourceType={voiceUpdates[voicePickerChar.id]?.sourceType || voicePickerChar.voice_source_type || null}
                currentStylePrompt={voiceUpdates[voicePickerChar.id]?.stylePrompt || voicePickerChar.voice_style_prompt || null}
                onAssigned={(voiceId, voiceName, provider, sourceType, stylePrompt) => {
                  setVoiceUpdates((p) => ({
                    ...p,
                    [voicePickerChar.id]: { voiceId, voiceName, provider, sourceType, stylePrompt },
                  }))
                  setCharacters((prev) =>
                    prev.map((c) =>
                      c.id === voicePickerChar.id
                        ? {
                          ...c,
                          voice_provider: voiceId ? provider : null,
                          voice_id: voiceId || null,
                          voice_name: voiceName || null,
                          voice_source_type: voiceId ? sourceType || null : null,
                          voice_style_prompt: voiceId ? stylePrompt || null : null,
                          elevenlabs_voice_id: provider === 'elevenlabs' ? voiceId || null : c.elevenlabs_voice_id,
                          elevenlabs_voice_name: provider === 'elevenlabs' ? voiceName || null : c.elevenlabs_voice_name,
                        }
                        : c,
                    ),
                  )
                }}
              />
            )}
          </ProjectGuard>
        </StudioShell>
      </div>
    </div>
  )
}
