import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  AlertCircle,
  Bold,
  Brain,
  CheckCircle2,
  ChevronDown,
  Copy,
  Download,
  Edit3,
  FileText,
  Italic,
  MemoryStick,
  MessageSquare,
  Plus,
  UserCheck,
  Redo2,
  Save,
  Undo2,
  Upload,
  UploadCloud,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react'
import StudioShell from '../components/StudioShell'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import { useStudio } from '../context/StudioContext'
import DirectorDebatePanel from '../components/DirectorDebatePanel'
import WritersDebateModal from '../components/WritersDebateModal'
import { PageScene } from '../rooms/ThePage'
import {
  checkBackendHealth,
  createScene,
  createCharacterSkeleton,
  deleteScene,
  generateScenes,
  listCharacters,
  listScenes,
  saveCreativeDecisionMemory,
  saveDirectorMemoryEntry,
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

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

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

// ── Component ──────────────────────────────────────────────────────────────

export default function WritersRoom() {
  const { projectId } = useParams()
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const navigate = useNavigate()
  const { activeProject, activeProjectId } = useStudio()

  const effectiveProjectId = activeProjectId || projectId || queryProjectId

  // ── Core state ────────────────────────────────────────────────────────────
  const [scenes, setScenes] = useState<Scene[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [backendHealthy, setBackendHealthy] = useState(true)
  const [healthCheckLoading, setHealthCheckLoading] = useState(false)

  // ── Editor state ──────────────────────────────────────────────────────────
  const [activeSceneId, setActiveSceneId] = useState<string | null>(null)
  const [scriptText, setScriptText] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null)
  const [isDirty, setIsDirty] = useState(false)
  const [showExportDropdown, setShowExportDropdown] = useState(false)
  const [aiSuggestion, setAiSuggestion] = useState<AiSuggestion | null>(null)

  // Undo/redo stack
  const [undoStack, setUndoStack] = useState<string[]>([])
  const [redoStack, setRedoStack] = useState<string[]>([])

  const fileInputRef = useRef<HTMLInputElement>(null)
  const exportRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<HTMLTextAreaElement>(null)

  // ── Intelligence state ────────────────────────────────────────────────────
  const [debateMode, setDebateMode] = useState(false)
  const [debateTopic, setDebateTopic] = useState('')
  const [debateRunning, setDebateRunning] = useState(false)
  const [activeDebate, setActiveDebate] = useState<CoDirectorDebateEntry | null>(null)

  const [characterMindMode, setCharacterMindMode] = useState(false)
  const [selectedCharacter, setSelectedCharacter] = useState('')
  const [characterSimulating, setCharacterSimulating] = useState(false)
  const [characterMindResult, setCharacterMindResult] = useState<string | null>(null)

  const [sceneDebateResult, setSceneDebateResult] = useState<{ restraint: string; urgency: string; scene_id: string } | null>(null)
  const [sceneDebateAgreed, setSceneDebateAgreed] = useState<'restraint' | 'urgency' | null>(null)

  const [memorySaving, setMemorySaving] = useState(false)
  const [memorySavedChip, setMemorySavedChip] = useState(false)

  // ── Character descriptions state ──────────────────────────────────────────
  const [rightTab, setRightTab] = useState<'scenes' | 'characters'>('scenes')
  const [characters, setCharacters] = useState<CharacterRecord[]>([])
  const [charactersLoading, setCharactersLoading] = useState(false)
  const [charactersSaving, setCharactersSaving] = useState<Record<string, boolean>>({})
  const [characterUploading, setCharacterUploading] = useState<Record<string, boolean>>({})
  const [newCharacterNames, setNewCharacterNames] = useState<string[]>([])
  const [editDrafts, setEditDrafts] = useState<Record<string, Partial<CharacterRecord>>>({})

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

  const loadScenes = async () => {
    if (!effectiveProjectId) return
    setLoading(true)
    setError('')
    try {
      const result = await listScenes(effectiveProjectId)
      if (result.error) {
        setError(result.error)
      } else {
        setScenes(result.scenes)
        // If no active scene set, default to first
        if (!activeSceneId && result.scenes.length > 0) {
          setActiveSceneId(result.scenes[0].scene_id)
          setScriptText(result.scenes[0].text || result.scenes[0].description || '')
          setIsDirty(false)
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scenes')
    } finally {
      setLoading(false)
    }
  }

  const loadCharacters = useCallback(async () => {
    if (!effectiveProjectId) return
    setCharactersLoading(true)
    try {
      const result = await listCharacters(effectiveProjectId)
      if (!result.error) {
        setCharacters(result.characters)
      }
    } catch {
      // silent
    } finally {
      setCharactersLoading(false)
    }
  }, [effectiveProjectId])

  // Detect new characters from scenes vs DB
  useEffect(() => {
    if (characters.length > 0 && scenes.length > 0) {
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
    }
  }, [characters, scenes])

  // Load characters when scenes load
  useEffect(() => {
    if (effectiveProjectId && scenes.length > 0) {
      void loadCharacters()
    }
  }, [effectiveProjectId, scenes.length]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Scene selection ──────────────────────────────────────────────────────
  const handleSelectScene = useCallback(
    (sceneId: string) => {
      // Save current scene text before switching
      if (activeScene && isDirty) {
        void saveCurrentScene()
      }
      const scene = scenes.find((s) => s.scene_id === sceneId)
      if (scene) {
        setActiveSceneId(sceneId)
        setScriptText(scene.text || scene.description || '')
        setIsDirty(false)
        setUndoStack([])
        setRedoStack([])
      }
    },
    [activeScene, isDirty, scenes], // eslint-disable-line react-hooks/exhaustive-deps
  )

  // ── Auto-save ─────────────────────────────────────────────────────────────
  const saveCurrentScene = useCallback(async () => {
    if (!effectiveProjectId || !activeSceneId) return
    setIsSaving(true)
    try {
      await updateScene(effectiveProjectId, activeSceneId, { text: scriptText, description: scriptText })
      setLastSavedAt(new Date())
      setIsDirty(false)
    } catch (err) {
      console.error('Autosave failed:', err)
    } finally {
      setIsSaving(false)
    }
  }, [effectiveProjectId, activeSceneId, scriptText])

  // Debounced auto-save
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!isDirty) return
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      void saveCurrentScene()
    }, 3000)
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    }
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

  // ── Export handlers (stubs — 501) ────────────────────────────────────────
  const handleExport = useCallback(
    (format: ExportFormat) => {
      setShowExportDropdown(false)
      if (format === 'clipboard') {
        navigator.clipboard.writeText(scriptText).catch(() => {})
        setSuccess('Copied to clipboard')
        return
      }
      setError(`Export to ${format.toUpperCase()} — endpoint returning 501 (not implemented yet)`)
    },
    [scriptText, setSuccess, setError],
  )

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
      reader.readAsText(file)
      // Reset file input so same file can be re-uploaded
      event.target.value = ''
    },
    [effectiveProjectId, loadScenes],
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
  }, [effectiveProjectId, activeSceneId, activeScene, scriptText])

  // ── Character save handler ────────────────────────────────────────────────
  const handleSaveCharacter = useCallback(
    async (charId: string) => {
      const draft = editDrafts[charId]
      if (!draft || !effectiveProjectId) return
      setCharactersSaving((p) => ({ ...p, [charId]: true }))
      try {
        const result = await updateCharacter(effectiveProjectId, charId, draft)
        if (result.character) {
          setCharacters((prev) => prev.map((c) => (c.id === charId ? result.character! : c)))
          setEditDrafts((prev) => {
            const next = { ...prev }
            delete next[charId]
            return next
          })
        }
      } catch {
        // silent
      } finally {
        setCharactersSaving((p) => ({ ...p, [charId]: false }))
      }
    },
    [editDrafts, effectiveProjectId],
  )

  const handleCreateSkeletonCharacters = useCallback(async () => {
    if (!effectiveProjectId) return
    for (const name of newCharacterNames) {
      await createCharacterSkeleton(effectiveProjectId, name)
    }
    setNewCharacterNames([])
    void loadCharacters()
  }, [effectiveProjectId, newCharacterNames, loadCharacters])

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
    [effectiveProjectId],
  )

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ position: 'relative', width: '100vw', height: '100vh' }}>
      {/* 3D environment */}
      <div style={{ position: 'absolute', inset: 0 }}>
        <PageScene />
      </div>

      {/* UI overlay */}
      <div style={{ position: 'absolute', inset: 0, zIndex: 10, pointerEvents: 'auto' }}>
        <StudioShell title="Writer's Room" subtitle="The Page — Draft and manage your script" transparent>
          <ProjectGuard>
            <ProjectContextBar roomName="writer's room" />

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
                      className="rounded border border-amber-300/50 bg-amber-500/14 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-100"
                    >
                      {healthCheckLoading ? 'Checking...' : 'Retry'}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* ── THREE-PANEL LAYOUT ────────────────────────────────────────── */}
            <div className="flex h-[calc(100vh-100px)] w-full px-4 pb-4 gap-4">
              {/* ── LEFT: INGEST PANEL (25%) ─────────────────────────────── */}
              <div className="flex w-1/4 flex-col gap-4 overflow-y-auto">
                {/* Ingest Section */}
                <div className="glass-panel rounded-xl p-4">
                  <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--color-primary)' }}>
                    INGEST
                  </div>

                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.fdx,.txt,.fountain"
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
                        className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em]"
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
                      No imports yet. Upload a .pdf, .fdx, or .txt script.
                    </div>
                  )}
                </div>

                {/* Intelligence Section */}
                <div className="glass-panel rounded-xl p-4">
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
                          <p className="text-[10px] text-zinc-500 leading-relaxed">
                            Debates two opposing directorial perspectives — Restraint vs Urgency — on the current scene.
                          </p>
                          <button
                            type="button"
                            onClick={handleStartDebate}
                            disabled={debateRunning || !activeSceneId}
                            className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.02] disabled:opacity-50"
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
                            className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.02] disabled:opacity-50"
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
                        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] transition-all hover:bg-white/5 disabled:opacity-50"
                        style={{ color: 'var(--color-on-surface)' }}
                      >
                        <MemoryStick size={16} />
                        Director's Memory
                        {memorySavedChip && (
                          <span className="ml-auto flex items-center gap-1 rounded bg-emerald-500/20 px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.12em] text-emerald-400">
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
                </div>
              </div>

              {/* ── CENTER: EDITOR (50%) ──────────────────────────────────── */}
              <div className="flex w-1/2 flex-col gap-3 z-20">
                {/* Editor header */}
                <div className="glass-panel flex items-center justify-between rounded-xl px-4 py-3">
                  <div className="text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-primary)' }}>
                    THE PAGE
                  </div>
                  <div className="flex items-center gap-3">
                    {/* Scene selector */}
                    {scenes.length > 0 ? (
                      <select
                        value={activeSceneId || ''}
                        onChange={(e) => handleSelectScene(e.target.value)}
                        className="glass-panel rounded-lg px-3 py-1.5 text-xs outline-none"
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
                    {/* Autosave indicator */}
                    <span
                      className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.1em]"
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
                      ) : lastSavedAt ? (
                        <>
                          <span className="h-2 w-2 rounded-full bg-emerald-400" />
                          SAVED {timeAgo(lastSavedAt)}
                        </>
                      ) : (
                        <>
                          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: 'var(--color-outline)' }} />
                          UNSAVED
                        </>
                      )}
                    </span>
                  </div>
                </div>

                {/* Toolbar */}
                <div className="glass-panel flex items-center justify-between rounded-xl px-3 py-2">
                  {/* Left group — Fountain format */}
                  <div className="flex items-center gap-1">
                    {FOUNTAIN_PREFIXES.map((item) => (
                      <button
                        key={item.label}
                        type="button"
                        onClick={() => insertFountainPrefix(item.prefix)}
                        title={item.shortcut}
                        className="status-chip rounded border px-2 py-1 text-[9px] font-bold uppercase tracking-[0.12em] transition-all hover:bg-white/10"
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
                        className="flex items-center gap-1 rounded px-2 py-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] transition-all hover:bg-white/10"
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
                            { key: 'pdf' as ExportFormat, icon: FileText, label: 'Download PDF' },
                            { key: 'fdx' as ExportFormat, icon: FileText, label: 'Download FDX' },
                            { key: 'txt' as ExportFormat, icon: FileText, label: 'Download TXT' },
                            { key: 'clipboard' as ExportFormat, icon: Copy, label: 'Copy to Clipboard' },
                          ]).map((item) => (
                            <button
                              key={item.key}
                              type="button"
                              onClick={() => handleExport(item.key)}
                              className="flex w-full items-center gap-3 px-4 py-2 text-[11px] transition-all hover:bg-white/5"
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
                <div className="glass-panel relative flex-1 overflow-hidden rounded-xl">
                  <textarea
                    ref={editorRef}
                    value={scriptText}
                    onChange={handleTextChange}
                    placeholder={activeScene ? 'Write your script here...' : 'Select or create a scene to start writing...'}
                    className="h-full w-full resize-none bg-transparent p-6 text-sm leading-relaxed outline-none"
                    style={{
                      color: 'var(--color-on-surface)',
                      fontFamily: 'var(--font-jetbrains)',
                      lineHeight: '1.8',
                    }}
                    disabled={!activeScene}
                  />

                  {/* Word count */}
                  <div
                    className="absolute bottom-3 right-4 text-[10px] font-semibold uppercase tracking-[0.1em]"
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
                          className="text-[10px] font-bold uppercase tracking-[0.12em]"
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
                          className="rounded-lg px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02]"
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
                          className="rounded-lg px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] transition-all hover:bg-white/10"
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
                      className="mb-2 text-[9px] font-semibold uppercase tracking-[0.14em]"
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
                      className="mb-2 text-[9px] font-semibold uppercase tracking-[0.14em]"
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

              {/* ── RIGHT: TABBED PANEL (25%) ────────────────────────────── */}
              <div className="flex w-1/4 flex-col gap-3 overflow-y-auto">
                {/* Tab bar */}
                <div className="glass-panel flex items-center rounded-xl px-1 py-1">
                  <button
                    type="button"
                    onClick={() => setRightTab('scenes')}
                    className={`flex-1 rounded-lg px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] transition-all ${
                      rightTab === 'scenes' ? 'bg-white/10 shadow-sm' : 'hover:bg-white/5'
                    }`}
                    style={{
                      color: rightTab === 'scenes' ? 'var(--color-primary)' : 'var(--color-on-surface-variant)',
                    }}
                  >
                    Scene List
                  </button>
                  <button
                    type="button"
                    onClick={() => setRightTab('characters')}
                    className={`flex items-center justify-center gap-1.5 flex-1 rounded-lg px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] transition-all ${
                      rightTab === 'characters' ? 'bg-white/10 shadow-sm' : 'hover:bg-white/5'
                    }`}
                    style={{
                      color: rightTab === 'characters' ? 'var(--color-primary)' : 'var(--color-on-surface-variant)',
                    }}
                  >
                    <Users size={12} />
                    Characters
                    {newCharacterNames.length > 0 && (
                      <span className="flex h-4 w-4 items-center justify-center rounded-full bg-amber-500 text-[8px] font-bold text-black">
                        {newCharacterNames.length}
                      </span>
                    )}
                  </button>
                </div>

                {/* Scene List Tab */}
                {rightTab === 'scenes' && (
                  <>
                    <div className="glass-panel flex items-center justify-between rounded-xl px-4 py-3">
                      <span className="text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>
                        SCENE LIST
                      </span>
                      <button
                        type="button"
                        onClick={handleAddScene}
                        disabled={loading || !effectiveProjectId}
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
                              onClick={() => handleSelectScene(scene.scene_id)}
                              className={`flex w-full items-start gap-3 rounded-xl px-4 py-3 text-left transition-all ${
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
                                className="status-chip mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold"
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
                                  className="mt-0.5 text-[10px]"
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
                )}

                {/* Character Descriptions Tab */}
                {rightTab === 'characters' && (
                  <div className="flex flex-col gap-3">
                    {/* New characters banner */}
                    {newCharacterNames.length > 0 && (
                      <div className="glass-panel rounded-xl border px-4 py-3" style={{ borderColor: 'rgba(251,191,36,0.3)' }}>
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-amber-400">
                              New characters detected
                            </div>
                            <div className="mt-1 text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                              {newCharacterNames.join(', ')}
                            </div>
                            <div className="mt-1 text-[10px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                              Add descriptions to improve render quality.
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={handleCreateSkeletonCharacters}
                            className="shrink-0 rounded-lg px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02]"
                            style={{
                              background: 'rgba(251,191,36,0.15)',
                              color: '#fbbf24',
                              border: '1px solid rgba(251,191,36,0.3)',
                            }}
                          >
                            Add
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
                      <div className="space-y-3">
                        {characters.map((char) => {
                          const draft = editDrafts[char.id] || {}
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
                              <div className="mb-2 flex items-center justify-between">
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
                                    onClick={() => handleUploadDescriptor(char.id)}
                                    disabled={characterUploading[char.id]}
                                    className="flex items-center gap-1 rounded-lg px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02] disabled:opacity-50"
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
                                      onClick={() => handleSaveCharacter(char.id)}
                                      disabled={isSaving}
                                      className="flex items-center gap-1 rounded-lg px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02] disabled:opacity-50"
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

                              <div className="space-y-2">
                                <div>
                                  <div className="mb-0.5 text-[9px] font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-outline-variant)' }}>
                                    Look
                                  </div>
                                  <textarea
                                    value={look}
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
                                  <div className="mb-0.5 text-[9px] font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-outline-variant)' }}>
                                    Energy
                                  </div>
                                  <textarea
                                    value={energy}
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
                                  <div className="mb-0.5 text-[9px] font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-outline-variant)' }}>
                                    Visual Prompt Summary
                                  </div>
                                  <textarea
                                    value={vps}
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
          </ProjectGuard>
        </StudioShell>
      </div>
    </div>
  )
}