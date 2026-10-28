import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Brain,
  Check,
  FileText,
  Film,
  Loader2,
  MessageSquare,
  Plus,
  Send,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import StudioShell from '../components/StudioShell'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import KnowledgeLibraryPanel from '../components/KnowledgeLibraryPanel'
import { useProjectRouteContext } from '../hooks/useProjectRouteContext'
import {
  STUDIO_API_BASE,
  attachStudioBrainLibraryFiles,
  deleteDirectorMemoryEntry,
  getDirectorMemory,
  getStudioProject,
  listStudioBrainLibrary,
  reorganizeReferenceLibrary,
  saveCreativeDecisionMemory,
  saveDirectorMemoryEntry,
  studyReferencePrompt,
} from '../lib/studioApi'
import type { StudioBrainLibraryFile } from '../lib/studioApi'
import { persistActiveProjectId } from '../lib/projectContext'
import type {
  DirectorMemoryBundle,
  DirectorMemoryEntry,
  DirectorMemoryKind,
} from '../types/directorMemory'

/* ── Types ─────────────────────────────────────────────────────────────────── */

type CategoryFilter = 'all' | 'cinematography' | 'editing' | 'sound' | 'narrative' | 'visual' | 'character' | 'world'
type IntelligenceBatch = 'emotional' | 'historical' | 'industry' | 'judgment'

interface ReferenceCard {
  id: string
  title: string
  category: string
  summary: string
  source?: string
  filename?: string
  study_focus?: string
}

interface ActiveMemoryItem {
  entry_id: string
  kind: DirectorMemoryKind
  text: string
}

interface UploadProgressItem {
  filename: string
  progress: number
  status: 'uploading' | 'complete' | 'error'
  error?: string
}

/* ── Constants ─────────────────────────────────────────────────────────────── */

const CATEGORY_LABELS: Record<CategoryFilter, string> = {
  all: 'ALL',
  cinematography: 'Cinematography',
  editing: 'Editing',
  sound: 'Sound',
  narrative: 'Narrative',
  visual: 'Visual',
  character: 'Character',
  world: 'World',
}

const BATCH_LABELS: Record<IntelligenceBatch, string> = {
  emotional: 'EMOTIONAL',
  historical: 'HISTORICAL',
  industry: 'INDUSTRY',
  judgment: 'JUDGMENT',
}

const ACCEPTED_EXTENSIONS = '.pdf,.txt,.fdx,.md,.markdown,.mp4,.mov,.mp3,.wav'

const MIME_TYPE_MAP: Record<string, string> = {
  'application/pdf': 'document',
  'text/plain': 'document',
  'text/markdown': 'document',
  'text/x-markdown': 'document',
  'text/fdx': 'document',
  'video/mp4': 'film',
  'video/quicktime': 'film',
  'audio/mpeg': 'audio',
  'audio/wav': 'audio',
}

const EMPTY_BUNDLE: DirectorMemoryBundle = {
  symbols: [],
  motifs: [],
  characters: [],
  themes: [],
  notes: [],
  debates: [],
}

/* ── CSS-in-JS helpers ─────────────────────────────────────────────────────── */

/* ── Helpers ──────────────────────────────────────────────────────────────── */

function entryDisplayText(entry: DirectorMemoryEntry): string {
  switch (entry.kind) {
    case 'symbols':
      return `${entry.symbol}: ${entry.meaning}`
    case 'motifs':
      return `${entry.motif} — ${entry.keyword}`
    case 'themes':
      return entry.theme
    case 'notes':
      return entry.note || entry.headline
    case 'characters':
      return `${entry.character}: ${entry.motivations}`
    case 'debates':
      return entry.synthesis?.slice(0, 140) || entry.query
    default:
      return ''
  }
}

function categorizeDirectorMemory(bundle: DirectorMemoryBundle): {
  styleMemories: ActiveMemoryItem[]
  toneMemories: ActiveMemoryItem[]
  pacingMemories: ActiveMemoryItem[]
  allMemories: ActiveMemoryItem[]
} {
  const style: ActiveMemoryItem[] = []
  const tone: ActiveMemoryItem[] = []
  const pacing: ActiveMemoryItem[] = []
  const all: ActiveMemoryItem[] = []

  const push = (entry: DirectorMemoryEntry, bucket: ActiveMemoryItem[]) => {
    const text = entryDisplayText(entry).trim()
    if (!text) return
    const item = { entry_id: entry.entry_id, kind: entry.kind, text }
    bucket.push(item)
    all.push(item)
  }

  for (const entry of bundle.motifs) push(entry, style)
  for (const entry of bundle.symbols) push(entry, style)

  for (const entry of bundle.themes) push(entry, tone)

  for (const entry of bundle.notes) {
    const hay = `${entry.headline} ${entry.note} ${entry.keyword}`.toLowerCase()
    if (/pace|rhythm|tempo|cut timing|editing speed/.test(hay)) push(entry, pacing)
    else if (/tone|mood|emotion|feel|tension|atmosphere/.test(hay)) push(entry, tone)
    else if (/style|visual|composition|light|color|frame|camera/.test(hay)) push(entry, style)
    else push(entry, style)
  }

  for (const entry of bundle.debates) {
    const hay = `${entry.query} ${entry.synthesis}`.toLowerCase()
    if (/pace|rhythm|tempo|cut|timing/.test(hay)) push(entry, pacing)
    else if (/tone|mood|emotion|tension/.test(hay)) push(entry, tone)
    else if (/style|visual|composition|look|aesthetic/.test(hay)) push(entry, style)
  }

  return {
    styleMemories: style,
    toneMemories: tone,
    pacingMemories: pacing,
    allMemories: all,
  }
}

function MemorySection({
  title,
  items,
  emptyLabel,
  teachPlaceholder,
  onTeach,
}: {
  title: string
  items: ActiveMemoryItem[]
  emptyLabel: string
  teachPlaceholder?: string
  onTeach?: (placeholder: string) => void
}) {
  return (
    <div>
      <div className="mb-1.5 text-xs font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-on-surface)' }}>
        {title}
      </div>
      {items.length === 0 ? (
        <div>
          <p className="text-on-surface-variant body-md text-xs">{emptyLabel}</p>
          {teachPlaceholder && onTeach && (
            <button
              type="button"
              onClick={() => onTeach(teachPlaceholder)}
              className="text-xs text-secondary underline mt-1"
            >
              + Teach Studio your {title.toLowerCase().replace(/learned |rules|pacing/, '').trim()} preferences
            </button>
          )}
        </div>
      ) : (
        <ul className="space-y-1.5">
          {items.map((m) => (
            <li key={m.entry_id} className="flex items-start gap-2 body-md text-on-surface">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
              <span className="line-clamp-3">{m.text}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/* ── Inject shake keyframes once ───────────────────────────────────────────── */

const STYLE_ID = 'studyroom-shake-keyframes'
if (typeof document !== 'undefined' && !document.getElementById(STYLE_ID)) {
  const el = document.createElement('style')
  el.id = STYLE_ID
  el.textContent = `
    @keyframes shake {
      0%, 100% { transform: translateX(0); }
      20% { transform: translateX(-4px); }
      40% { transform: translateX(4px); }
      60% { transform: translateX(-4px); }
      80% { transform: translateX(4px); }
    }
    @keyframes fadeOut {
      from { opacity: 1; }
      to   { opacity: 0; }
    }
  `
  document.head.appendChild(el)
}

/* ═══════════════════════════════════════════════════════════════════════════════
   AUDIT PREAMBLE — findings inline as comments before the main component
   ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Component ────────────────────────────────────────────────────────────── */

export default function StudyRoom() {
  // ============ ALL HOOKS — NO EXCEPTIONS ============
  // Custom hooks first
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const { projectId: resolvedProjectId, projectError } = useProjectRouteContext(queryProjectId)
  const [studyStep, setStudyStep] = useState<'bibles' | 'references' | 'guidance'>('bibles')
  const [reorganizing, setReorganizing] = useState(false)

  // useState — ALL of them, unconditionally
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [activeBatches, setActiveBatches] = useState<Set<IntelligenceBatch>>(new Set())
  const [references, setReferences] = useState<ReferenceCard[]>([])
  const [loadingRefs, setLoadingRefs] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [queryText, setQueryText] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState<string | null>(null)
  const [ingestText, setIngestText] = useState('')
  const [ingesting, setIngesting] = useState(false)
  const [ingestConfirmed, setIngestConfirmed] = useState(false)
  const [filmIngestMode, setFilmIngestMode] = useState<'title' | 'upload'>('title')
  const [filmTitle, setFilmTitle] = useState('')
  const [filmDimensions, setFilmDimensions] = useState<'cinematography' | 'editing' | 'sound' | 'narrative' | 'all'>('all')
  const [filmFile] = useState<File | null>(null)
  const [filmProcessing, setFilmProcessing] = useState(false)
  const [filmLearned, setFilmLearned] = useState<string[] | null>(null)
  const [filmIngestConfirmed, setFilmIngestConfirmed] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<Record<string, UploadProgressItem>>({})
  const [filmTitleInvalid, setFilmTitleInvalid] = useState(false)
  const [showMemoryDrawer, setShowMemoryDrawer] = useState(false)
  const [memoryBundle, setMemoryBundle] = useState<DirectorMemoryBundle>(EMPTY_BUNDLE)
  const [loadingMemories, setLoadingMemories] = useState(false)
  const [studioBrainFiles, setStudioBrainFiles] = useState<StudioBrainLibraryFile[]>([])
  const [selectedStudioBrainFiles, setSelectedStudioBrainFiles] = useState<Set<string>>(new Set())
  const [loadingStudioBrainFiles, setLoadingStudioBrainFiles] = useState(false)
  const [attachingStudioBrainFiles, setAttachingStudioBrainFiles] = useState(false)
  const [savingReferenceId, setSavingReferenceId] = useState('')
  const [deletingMemoryId, setDeletingMemoryId] = useState('')

  // useRef — ALL of them
  const fileInputRef = useRef<HTMLInputElement>(null)

  // useMemo — derived computations (no side effects)
  const { styleMemories, toneMemories, pacingMemories, allMemories } = useMemo(
    () => categorizeDirectorMemory(memoryBundle),
    [memoryBundle],
  )

  const filteredReferences = useMemo(() => {
    let result = references
    if (category !== 'all') {
      result = result.filter((r) => r.category.toLowerCase() === category.toLowerCase())
    }
    if (activeBatches.size > 0) {
      result = result.filter((r) => {
        const text = `${r.title} ${r.summary} ${r.category}`.toLowerCase()
        for (const batch of activeBatches) {
          if (batch === 'emotional' && (text.includes('emotion') || text.includes('feeling') || text.includes('tension'))) return true
          if (batch === 'historical' && (text.includes('history') || text.includes('classic') || text.includes('tradition'))) return true
          if (batch === 'industry' && (text.includes('industry') || text.includes('market') || text.includes('commercial'))) return true
          if (batch === 'judgment' && (text.includes('quality') || text.includes('craft') || text.includes('standard'))) return true
        }
        return false
      })
    }
    return result
  }, [references, category, activeBatches])

  const selectedStudioBrainCount = selectedStudioBrainFiles.size

  // useCallback — ALL of them
  const toggleBatch = useCallback((batch: IntelligenceBatch) => {
    setActiveBatches((prev) => {
      const next = new Set(prev)
      if (next.has(batch)) next.delete(batch)
      else next.add(batch)
      return next
    })
  }, [])

  const loadReferences = useCallback(async () => {
    if (!resolvedProjectId) return
    setLoadingRefs(true)
    try {
      const project = await getStudioProject(resolvedProjectId)
      if (project?.reference_study_library?.studies) {
        const refs: ReferenceCard[] = (project.reference_study_library.studies as Array<Record<string, unknown>>).map((study: Record<string, unknown>) => ({
          id: (study.reference_id as string) || '',
          title: (study.filename as string) || 'Untitled Reference',
          category: (study.study_focus as string) || 'General',
          summary: (study.notes as string) || (study.study_focus as string) || '',
          source: study.content_type as string,
          filename: study.filename as string,
          study_focus: study.study_focus as string,
        }))
        setReferences(refs)
      } else {
        setReferences([])
      }
    } catch (err) {
      // Suppress 404 errors for non-critical endpoints
      const is404 = err instanceof Error && err.message.includes('404')
      if (!is404) {
        console.error('loadReferences failed:', err)
      }
      setReferences([])
    } finally {
      setLoadingRefs(false)
    }
  }, [resolvedProjectId])

  async function handleReorganizeReferences() {
    if (!resolvedProjectId || reorganizing) return
    setReorganizing(true)
    setError('')
    try {
      await reorganizeReferenceLibrary(resolvedProjectId)
      await loadReferences()
      setSuccess('Reference categories refreshed.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not reorganize references.')
    } finally { setReorganizing(false) }
  }

  const loadMemories = useCallback(async () => {
    if (!resolvedProjectId) return
    setLoadingMemories(true)
    try {
      const response = await getDirectorMemory(resolvedProjectId)
      const bundle = response.memory ?? EMPTY_BUNDLE
      setMemoryBundle(bundle)
    } catch (err) {
      // Suppress 404 errors for non-critical endpoints
      const is404 = err instanceof Error && err.message.includes('404')
      if (!is404) {
        console.error('loadMemories failed:', err)
      }
      setMemoryBundle(EMPTY_BUNDLE)
    } finally {
      setLoadingMemories(false)
    }
  }, [resolvedProjectId])

  const loadStudioBrainFiles = useCallback(async () => {
    setLoadingStudioBrainFiles(true)
    try {
      const result = await listStudioBrainLibrary()
      setStudioBrainFiles(result.files || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load Studio Brain library')
      setStudioBrainFiles([])
    } finally {
      setLoadingStudioBrainFiles(false)
    }
  }, [])

  const toggleStudioBrainFile = useCallback((filename: string) => {
    setSelectedStudioBrainFiles((prev) => {
      const next = new Set(prev)
      if (next.has(filename)) next.delete(filename)
      else next.add(filename)
      return next
    })
  }, [])

  const handleAttachStudioBrainFiles = useCallback(async () => {
    if (!resolvedProjectId || selectedStudioBrainFiles.size === 0) return
    setAttachingStudioBrainFiles(true)
    setError('')
    setSuccess('')
    try {
      const result = await attachStudioBrainLibraryFiles(resolvedProjectId, Array.from(selectedStudioBrainFiles))
      setSelectedStudioBrainFiles(new Set())
      const skipped = result.skipped?.length || 0
      const attached = result.total_attached || 0
      setSuccess(
        skipped > 0
          ? `${attached} Studio Brain files added; ${skipped} already existed or could not be added.`
          : `${attached} Studio Brain files added to this project.`,
      )
      void loadReferences()
      void loadMemories()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add Studio Brain files')
    } finally {
      setAttachingStudioBrainFiles(false)
    }
  }, [resolvedProjectId, selectedStudioBrainFiles, loadReferences, loadMemories])

  const handleSaveReference = useCallback(async (ref: ReferenceCard) => {
    if (!resolvedProjectId) return
    setSavingReferenceId(ref.id)
    try {
      await saveDirectorMemoryEntry(resolvedProjectId, 'notes', {
        headline: ref.title,
        note: ref.summary,
        keyword: ref.source || ref.category,
      })
      setSuccess(`"${ref.title}" saved to Director's Memory`)
      void loadMemories()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save reference')
    } finally {
      setSavingReferenceId('')
    }
  }, [resolvedProjectId, loadMemories])

  const handleReferenceCardClick = useCallback((ref: ReferenceCard) => {
    setIngestText(`From reference "${ref.title}": ${ref.summary}`)
    setStudyStep('guidance')
    requestAnimationFrame(() => document.getElementById('teach-studio-bar')?.scrollIntoView({ behavior: 'smooth' }))
  }, [])

  const handleAnalyze = useCallback(async () => {
    if (!queryText.trim() || !resolvedProjectId) return
    setAnalyzing(true)
    setAnalysisResult(null)

    try {
      const result = await studyReferencePrompt(queryText.trim(), resolvedProjectId, category === 'all' ? undefined : category)
      const raw = result as Record<string, unknown>
      // Try to pretty-print study_cards if present
      const cards = raw.study_cards as Array<Record<string, unknown>> | undefined
      if (Array.isArray(cards) && cards.length > 0) {
        setAnalysisResult(raw as unknown as string)
      } else {
        setAnalysisResult(
          String(raw?.response || raw?.analysis || raw?.content || JSON.stringify(result))
        )
      }
    } catch (err) {
      console.error('Analysis failed:', err)
      setAnalysisResult('Analysis failed. Please try again.')
    } finally {
      setAnalyzing(false)
    }
  }, [queryText, resolvedProjectId, category])

  const handleIngest = useCallback(async () => {
    if (!ingestText.trim() || !resolvedProjectId) return
    setIngesting(true)
    setError('')
    try {
      await saveCreativeDecisionMemory(resolvedProjectId, {
        project_id: resolvedProjectId,
        decision_type: 'creative_note',
        user_note: ingestText.trim(),
        inferred_tradeoff: 'not_inferred',
        inferred_tradeoff_explanation: '',
        source_context: {
          screen_location: 'study_room_ingest',
        },
        editable: true,
        forgettable: true,
      })
      await saveDirectorMemoryEntry(resolvedProjectId, 'notes', {
        headline: 'Studio pattern',
        note: ingestText.trim(),
        keyword: 'study_ingest',
      })
      setIngestText('')
      setIngestConfirmed(true)
      setTimeout(() => setIngestConfirmed(false), 3000)
      void loadMemories()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ingest failed')
    } finally {
      setIngesting(false)
    }
  }, [ingestText, resolvedProjectId, loadMemories])

  const handleDeleteMemory = useCallback(async (entryId: string, kind: DirectorMemoryKind) => {
    if (!resolvedProjectId) return
    setDeletingMemoryId(entryId)
    try {
      await deleteDirectorMemoryEntry(resolvedProjectId, kind, entryId)
      void loadMemories()
    } catch {
      setError('Failed to delete memory')
    } finally {
      setDeletingMemoryId('')
    }
  }, [resolvedProjectId, loadMemories])

  const handleFilmTitleIngest = useCallback(async () => {
    if (!resolvedProjectId) {
      setError('No active project. Select a project first.')
      return
    }
    if (!filmTitle.trim()) {
      setFilmTitleInvalid(true)
      setTimeout(() => setFilmTitleInvalid(false), 600)
      return
    }
    setFilmProcessing(true)
    setFilmLearned(null)
    setError('')
    try {
      const result = await studyReferencePrompt(filmTitle.trim(), resolvedProjectId, filmDimensions)
      setFilmLearned([
        `Analyzed: ${result.filename}`,
        `Focus: ${result.study_focus}`,
        `Status: ${result.extraction_status}`,
        `Rights: ${result.rights_status}`,
      ])
      setFilmTitle('')
      setFilmIngestConfirmed(true)
      setFilmTitleInvalid(false)
      setTimeout(() => setFilmIngestConfirmed(false), 3000)
      void loadReferences()
      void loadMemories()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Film analysis failed')
    } finally {
      setFilmProcessing(false)
    }
  }, [filmTitle, filmDimensions, resolvedProjectId, loadReferences, loadMemories])

  const getFileCategory = useCallback((file: File): string => {
    const ext = file.name.toLowerCase().split('.').pop() || ''
    const mime = file.type
    if (MIME_TYPE_MAP[mime]) return MIME_TYPE_MAP[mime]
    if (['mp4', 'mov'].includes(ext)) return 'film'
    if (['mp3', 'wav'].includes(ext)) return 'audio'
    if (['pdf', 'txt', 'fdx', 'md'].includes(ext)) return 'document'
    return 'document'
  }, [])

  const uploadFileWithProgress = useCallback((projectId: string, file: File) => {
    const filename = file.name
    const fileType = getFileCategory(file)
    setUploadProgress((prev) => ({
      ...prev,
      [filename]: { filename, progress: 0, status: 'uploading' },
    }))
    const formData = new FormData()
    formData.append('file', file)
    formData.append('type', fileType)
    formData.append('project_id', projectId)
    formData.append('title', filename)
    const isMarkdown = file.name.toLowerCase().endsWith('.md') || file.name.toLowerCase().endsWith('.markdown') || file.type === 'text/markdown'
    if (isMarkdown) {
      file.text().then((text: string) => {
        const h1Match = text.match(/^#\s+(.+)$/m)
        const h1 = h1Match ? h1Match[1].trim() : ''
        const lines = text.split('\n')
        const firstPara = lines.filter((l: string) => l.trim() && !l.trim().startsWith('#')).shift()?.trim() || ''
        formData.append('derived_title', h1)
        formData.append('derived_summary', firstPara.slice(0, 500))
      }).catch(() => {})
    }
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${STUDIO_API_BASE}/api/f51/studio/study-reference`)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        setUploadProgress((prev) => ({
          ...prev,
          [filename]: { ...prev[filename], progress: Math.round((e.loaded / e.total) * 100) },
        }))
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        setUploadProgress((prev) => ({ ...prev, [filename]: { filename, progress: 100, status: 'complete' } }))
        void loadReferences()
        void loadMemories()
        setTimeout(() => {
          setUploadProgress((prev) => { const next = { ...prev }; delete next[filename]; return next })
        }, 3000)
      } else {
        let msg = `Upload failed (${xhr.status})`
        try {
          const body = JSON.parse(xhr.responseText)
          msg = body.detail || body.message || msg
        } catch { msg = xhr.responseText || msg }
        setUploadProgress((prev) => ({ ...prev, [filename]: { filename, progress: 0, status: 'error', error: msg } }))
      }
    }
    xhr.onerror = () => {
      setUploadProgress((prev) => ({ ...prev, [filename]: { filename, progress: 0, status: 'error', error: 'Network error' } }))
    }
    xhr.send(formData)
  }, [getFileCategory, loadReferences, loadMemories])

  const handleFileIngest = useCallback(async (files: File[]) => {
    try {
      if (!resolvedProjectId) {
        setError('No active project. Select a project first.')
        return
      }
      const validFiles: File[] = []
      for (const file of files) {
        const ext = '.' + file.name.toLowerCase().split('.').pop()
        if (ACCEPTED_EXTENSIONS.includes(ext) || MIME_TYPE_MAP[file.type]) {
          validFiles.push(file)
        } else {
          setError(`Unsupported file type: ${ext}. Accepted: ${ACCEPTED_EXTENSIONS}`)
        }
      }
      if (validFiles.length === 0) return
      for (const file of validFiles) {
        uploadFileWithProgress(resolvedProjectId, file)
      }
    } catch (err) {
      console.error('handleFileIngest failed:', err)
    }
  }, [resolvedProjectId, uploadFileWithProgress])

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) handleFileIngest(files)
  }, [handleFileIngest])

  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : []
    if (files.length > 0) handleFileIngest(files)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [handleFileIngest])

  // useEffect — ALL of them
  useEffect(() => {
    if (resolvedProjectId) persistActiveProjectId(resolvedProjectId)
  }, [resolvedProjectId])

  useEffect(() => { void loadReferences() }, [loadReferences])

  useEffect(() => { void loadMemories() }, [loadMemories])

  useEffect(() => { void loadStudioBrainFiles() }, [loadStudioBrainFiles])

  // ============ RENDER ============
  return (
    <>
      <style>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          20% { transform: translateX(-4px); }
          40% { transform: translateX(4px); }
          60% { transform: translateX(-4px); }
          80% { transform: translateX(4px); }
        }
        .animate-shake { animation: shake 0.6s ease-in-out; }
        @keyframes fadeOut {
          from { opacity: 1; }
          to   { opacity: 0; }
        }
        .animate-fade-out { animation: fadeOut 1s ease-out forwards; }
      `}</style>
      <StudioShell title="Study" subtitle="The Study — AI Research Room">
        <ProjectGuard>
          <ProjectContextBar roomName="study" compact />

          {/* Status messages */}
          <div className="px-4 pt-2">
            {(error || projectError) && (
              <div className="mb-2 rounded-lg border border-rose-400/40 bg-rose-500/10 px-4 py-2 text-sm text-rose-200">
                {error || projectError}
              </div>
            )}
            {success && (
              <div className="mb-2 rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-200">
                {success}
              </div>
            )}
          </div>

          <div className="mx-auto max-w-[1320px] px-4 pb-10 pt-5 md:px-6">
            <header className="mb-6">
              <p className="text-[11px] uppercase tracking-[0.2em] text-amber-200/80">The Study</p>
              <h1 className="mt-2 text-2xl font-medium tracking-tight text-zinc-100 md:text-3xl">Define the world before the first frame.</h1>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-400">Keep your film’s rules, creative references, and saved direction in one place. Begin with what you already have.</p>
            </header>
            <nav aria-label="Study steps" className="mb-6 grid grid-cols-3 gap-2 border-b border-white/10 pb-4">
              {([{ id: 'bibles', title: 'Bibles' }, { id: 'references', title: 'References' }, { id: 'guidance', title: 'Saved guidance' }] as const).map((step, index) => <button key={step.id} type="button" onClick={() => setStudyStep(step.id)} aria-current={studyStep === step.id ? 'step' : undefined} className={studyStep === step.id ? 'rounded-md border border-amber-200/40 bg-amber-200/5 px-3 py-3 text-left text-xs text-amber-100' : 'rounded-md border border-white/10 px-3 py-3 text-left text-xs text-zinc-400 hover:text-zinc-200'}><span className="mb-1 block text-xs opacity-60">0{index + 1}</span><span className="font-medium">{step.title}</span></button>)}
            </nav>
            <section aria-label="Project Bibles" className={studyStep === 'bibles' ? 'space-y-5' : 'hidden'}>
              <div><h2 className="text-lg font-medium text-zinc-100">The rules of your film</h2><p className="mt-1 max-w-2xl text-sm leading-relaxed text-zinc-400">Add your story, visual, or character Bible here. These are project rules; reference films and research belong in the next step.</p></div>
              {resolvedProjectId && <KnowledgeLibraryPanel key={resolvedProjectId} projectId={resolvedProjectId} />}
              <button type="button" onClick={() => setStudyStep('references')} className="rounded-md bg-amber-200 px-4 py-3 text-sm font-medium text-zinc-950 hover:bg-amber-100">Continue to references →</button>
            </section>
            <section aria-label="Creative references" className={studyStep === 'references' ? 'space-y-5' : 'hidden'}>
              <div><h2 className="text-lg font-medium text-zinc-100">Show the studio what you mean</h2><p className="mt-1 max-w-2xl text-sm leading-relaxed text-zinc-400">Upload a reference or study a film title for lighting, rhythm, sound, or story. Choose a focus for title studies. Uploaded files are organized automatically.</p></div>
              <div className="grid min-w-0 items-start gap-5 lg:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.4fr)]">
                <div id="study-reference-upload" className="min-w-0 rounded-lg border border-white/10 bg-zinc-950/60 p-5 space-y-4">
                   <div className="flex items-center gap-2">
                     <Film size={14} style={{ color: 'var(--color-secondary)' }} />
                     <span className="font-metadata-sm text-xs font-bold uppercase tracking-[0.15em]" style={{ color: 'var(--color-secondary)' }}>FILM REFERENCES</span>
                     {!resolvedProjectId && <span className="ml-1.5 h-2 w-2 rounded-full bg-amber-400 animate-pulse" />}
                   </div>

                  {/* Segmented Control */}
                  <div className="flex rounded-lg border p-0.5" style={{ borderColor: 'rgba(255,255,255,0.1)' }}>
                    <button type="button" onClick={() => setFilmIngestMode('title')} className={`flex-1 rounded px-2 py-1.5 text-[11px] font-bold uppercase tracking-[0.08em] transition-all ${filmIngestMode === 'title' ? 'bg-white/10 text-on-surface' : 'text-on-surface-variant hover:bg-white/5'}`}>FILM TITLE</button>
                    <button type="button" onClick={() => { setFilmIngestMode('upload'); document.getElementById('study-reference-upload')?.scrollIntoView({ behavior: 'smooth' }) }} className={`flex-1 rounded px-2 py-1.5 text-[11px] font-bold uppercase tracking-[0.08em] transition-all ${filmIngestMode === 'upload' ? 'bg-white/10 text-on-surface' : 'text-on-surface-variant hover:bg-white/5'}`}>UPLOAD FILE</button>
                  </div>

                  {/* Hidden file input — always mounted regardless of tab */}
                  <input
                    ref={fileInputRef}
                    type="file"
                    className="hidden"
                    multiple
                    accept={ACCEPTED_EXTENSIONS}
                    onChange={handleFileInputChange}
                  />

                  {/* FILM TITLE Mode */}
                  {filmIngestMode === 'title' && (
                    <div className="space-y-2">
                      <input type="text" aria-label="Film reference title" value={filmTitle} onChange={(e) => { setFilmTitle(e.target.value); if (filmTitleInvalid) setFilmTitleInvalid(false) }} onKeyDown={(e) => { if (e.key === 'Enter') void handleFilmTitleIngest() }} placeholder="Film title, director, year..." className={`cyber-input w-full rounded px-2 py-1.5 text-xs outline-none ${filmTitleInvalid ? 'animate-shake border-rose-400' : ''}`} style={{ color: 'var(--color-on-surface)' }} />
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-semibold uppercase tracking-[0.08em]" style={{ color: 'var(--color-on-surface-variant)' }}>ANALYZE FOR →</span>
                        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                        <select aria-label="Film title study focus" value={filmDimensions} onChange={(e) => setFilmDimensions(e.target.value as any)} className="cyber-input rounded px-2 py-1 text-xs font-bold uppercase tracking-[0.08em] outline-none" style={{ color: 'var(--color-on-surface)' }}>
                          <option value="all">All Dimensions</option>
                          <option value="cinematography">Cinematography</option>
                          <option value="editing">Editing</option>
                          <option value="sound">Sound</option>
                          <option value="narrative">Narrative</option>
                        </select>
                      </div>
                       <button type="button" onClick={handleFilmTitleIngest} disabled={filmProcessing || !resolvedProjectId} aria-busy={filmProcessing} title={!resolvedProjectId ? 'Loading project...' : undefined} className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01] disabled:opacity-50" style={{ background: 'rgba(255,209,101,0.15)', color: 'var(--color-primary)', border: '1px solid rgba(255,209,101,0.3)' }}>
                        {filmProcessing ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                        {filmProcessing ? 'ANALYZING...' : 'Study this reference'}
                      </button>
                    </div>
                  )}

                  {/* UPLOAD FILE Mode */}
                  {filmIngestMode === 'upload' && (
                    <div className="space-y-2">
                      <p className="text-xs leading-relaxed text-zinc-400">Uploaded references are categorized automatically from their filename and content.</p>
                       <div role="button" tabIndex={0} onClick={() => fileInputRef.current?.click()} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInputRef.current?.click() } }} title={!resolvedProjectId ? 'Loading project...' : undefined} className={`rounded-lg border-2 border-dashed p-4 text-center transition-all cursor-pointer ${isDragging ? 'border-secondary shadow-[0_0_20px_rgba(76,215,246,0.3)]' : 'border-outline-variant'} ${!resolvedProjectId ? 'opacity-50 pointer-events-none' : ''}`} style={isDragging ? undefined : { borderColor: 'rgba(255,255,255,0.2)' }} onDragEnter={handleDragEnter} onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}>
                        <Upload size={20} className="mx-auto mb-2" style={{ color: 'var(--color-on-surface-variant)' }} />
                        <p className="text-xs" style={{ color: 'var(--color-on-surface-variant)' }}>{filmFile ? filmFile.name : 'Drop a file here or click to browse'}</p>
                        <p className="text-[11px] mt-1" style={{ color: 'var(--color-on-surface-variant)' }}>PDF, FDX, TXT, MD, MP4, MOV, MP3, WAV supported</p>
                      </div>

                      {Object.values(uploadProgress).map((item) => (
                        <div key={item.filename} className={`glass-panel rounded-lg p-2.5 ${item.status === 'error' ? '!border-rose-400/40' : ''}`}>
                          <div className="flex items-center gap-2 mb-1">
                            <Upload size={12} style={{ color: 'var(--color-on-surface-variant)' }} />
                            <span className="flex-1 truncate text-xs font-medium" style={{ color: 'var(--color-on-surface)' }}>{item.filename}</span>
                            {item.status === 'complete' && <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--color-secondary)' }}>● INGESTED</span>}
                            {item.status === 'error' && <span className="text-[11px] font-bold uppercase tracking-wider text-rose-300">⚠ ERROR</span>}
                          </div>
                          <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
                            <div className={`h-full rounded-full transition-all duration-300 ${item.status === 'error' ? 'bg-rose-400' : 'bg-[var(--color-primary)]'}`} style={{ width: `${item.progress}%` }} />
                          </div>
                          <div className="mt-1 flex justify-between">
                            <span className="text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>{item.status === 'uploading' ? `${item.progress}%` : item.status === 'complete' ? 'Complete' : item.error || 'Failed'}</span>
                            {item.status === 'complete' && <span className="text-[11px] text-emerald-300">✓</span>}
                          </div>
                        </div>
                      ))}


                      <p className="text-xs leading-relaxed text-zinc-400">Selecting or dropping files starts the upload. Review them in the reference library when it finishes.</p>
                    </div>
                  )}

                  {filmProcessing && (
                    <div className="glass-panel rounded-lg p-3">
                      <p className="font-bold text-xs" style={{ color: 'var(--color-on-surface)' }}>{filmTitle || filmFile?.name || 'Film Reference'}</p>
                      <p className="mt-1 text-[11px] font-bold uppercase tracking-[0.1em] animate-pulse" style={{ color: 'var(--color-secondary)' }}>ANALYZING...</p>
                    </div>
                  )}

                  {filmLearned && !filmProcessing && (
                    <div className="glass-panel rounded-lg p-3">
                      <p className="font-bold text-xs" style={{ color: 'var(--color-on-surface)' }}>{filmTitle || filmFile?.name || 'Film Reference'}</p>
                      <ul className="mt-2 space-y-1">
                        {filmLearned.slice(0, 4).map((insight, idx) => (
                          <li key={idx} className="font-metadata-sm text-xs" style={{ color: 'var(--color-on-surface-variant)' }}>● Learned: {insight}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {filmIngestConfirmed && (
                    <div className="text-xs font-semibold transition-opacity duration-300" style={{ color: 'var(--color-secondary)' }}>● INGESTED — added to Reference Library</div>
                  )}
                </div>
                <div className="min-w-0 space-y-4"><details className="rounded-md border border-white/10 p-3"><summary className="cursor-pointer text-xs text-zinc-300">Filter references</summary><div className="pt-3"><div className="glass-panel rounded-xl p-3">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex flex-wrap gap-1">
                    {(Object.entries(CATEGORY_LABELS) as [CategoryFilter, string][]).map(([key, label]) => (
                      <button key={key} type="button" onClick={() => setCategory(key)} className={`status-chip rounded border px-2 py-1 text-[11px] font-bold uppercase tracking-[0.08em] transition-all ${category === key ? 'border-primary/50 bg-primary/15 text-primary' : 'hover:bg-white/8'}`} style={{ borderColor: category === key ? undefined : 'rgba(255,255,255,0.08)', color: category === key ? undefined : 'var(--color-on-surface-variant)' }}>{label}</button>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {(Object.entries(BATCH_LABELS) as [IntelligenceBatch, string][]).map(([key, label]) => {
                      const isActive = activeBatches.has(key)
                      return (
                        <button key={key} type="button" onClick={() => toggleBatch(key)} className={`status-chip rounded border px-2 py-1 text-[11px] font-bold uppercase tracking-[0.08em] transition-all ${isActive ? 'border-secondary/50 bg-secondary/15 text-secondary' : 'hover:bg-white/8'}`} style={{ borderColor: isActive ? undefined : 'rgba(255,255,255,0.08)', color: isActive ? undefined : 'var(--color-on-surface-variant)' }}>[{key[0].toUpperCase()}] {label}</button>
                      )
                    })}
                  </div>
                </div>
              </div></div></details><div className="glass-panel rounded-xl p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>REFERENCE LIBRARY</span>
                    <div className="flex items-center gap-3">
                      <span className="text-xs" style={{ color: 'var(--color-on-surface-variant)' }}>{filteredReferences.length} items</span>
                      <button type="button" onClick={() => setFilmIngestMode('upload')} className="flex items-center gap-1 rounded border border-white/10 px-2 py-1 text-[11px] font-bold uppercase tracking-wider transition-all hover:bg-white/10" style={{ color: 'var(--color-secondary)' }} title="Add a new reference"><Plus size={10} />ADD REFERENCE</button>
                    </div>
                  </div>

                  <div className="overflow-y-auto ">
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                      {filteredReferences.map((ref) => (
                        <div key={ref.id} className="glass-panel rounded-lg p-3 transition-all hover:scale-[1.01] cursor-pointer group relative" onClick={() => handleReferenceCardClick(ref)} title="Click to use this reference in Teach Studio">
                          <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-secondary)' }}>{ref.category}</div>
                          <h3 className="mb-1 text-[13px] font-bold pr-6" style={{ color: 'var(--color-on-surface)' }}>{ref.title}</h3>
                          <p className="line-clamp-2 text-xs leading-relaxed" style={{ color: 'var(--color-on-surface-variant)' }}>{ref.summary}</p>
                          {ref.source && <p className="mt-1.5 text-xs" style={{ color: 'var(--color-on-surface-variant)' }}>Source: {ref.source}</p>}
                          <button type="button" onClick={(e) => { e.stopPropagation(); void handleSaveReference(ref) }} disabled={savingReferenceId === ref.id} aria-busy={savingReferenceId === ref.id} className="absolute top-2.5 right-2 rounded p-1 transition-all hover:bg-white/10 opacity-70 group-hover:opacity-100 focus-visible:opacity-100 disabled:opacity-40" style={{ color: 'var(--color-secondary)' }} title="Save to Director's Memory">
                            {savingReferenceId === ref.id
                              ? <Loader2 size={12} className="animate-spin" />
                              : <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z" /></svg>}
                          </button>
                        </div>
                      ))}
                      {filteredReferences.length === 0 && !loadingRefs && (
                        <p className="col-span-full text-center text-xs py-4" style={{ color: 'var(--color-on-surface-variant)' }}>No references match the current filters. Click + ADD REFERENCE to add one.</p>
                      )}
                    </div>
                  </div>
                </div></div>
              </div>
              <details className="rounded-lg border border-white/10 p-4"><summary className="cursor-pointer text-sm text-zinc-300">Study a question with Studio Brain</summary><div className="pt-4"><div className="glass-panel rounded-xl border-l-2 p-4" id="ask-studio-brain" style={{ borderLeftColor: 'var(--color-secondary)' }}>
                <div className="mb-3 flex items-center gap-1.5">
                  <Brain size={16} style={{ color: 'var(--color-secondary)' }} />
                  <span className="text-[11px] font-semibold uppercase tracking-[0.14em]" style={{ color: 'var(--color-secondary)' }}>ASK STUDIO BRAIN</span>
                </div>

                <textarea aria-label="Research question" value={queryText} onChange={(e) => setQueryText(e.target.value)} placeholder="Enter a research question, topic, or area you'd like Studio Brain to analyze..." rows={3} className="cyber-input mb-3 w-full rounded px-3 py-2 text-sm outline-none" style={{ color: 'var(--color-on-surface)' }} />

                <button type="button" onClick={handleAnalyze} disabled={analyzing || !queryText.trim()} aria-busy={analyzing} className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[11px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.01] disabled:opacity-50" style={{ background: 'rgba(255,209,101,0.15)', color: 'var(--color-primary)', border: '1px solid rgba(255,209,101,0.3)' }}>
                  {analyzing ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                  {analyzing ? 'ANALYZING...' : 'ANALYZE'}
                </button>

                {analysisResult && (
                  <div className="glass-panel mt-3 rounded-lg border-l-2 p-4" style={{ borderLeftColor: 'var(--color-secondary)' }}>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="status-chip bg-secondary/20 text-secondary text-[11px] font-bold uppercase tracking-[0.1em] px-2 py-1 rounded">ANALYSIS COMPLETE</span>
                    </div>
                    {(() => {
                      let resultObj: Record<string, unknown> | null = null
                      try {
                        resultObj = typeof analysisResult === 'string' ? JSON.parse(analysisResult) : analysisResult
                      } catch {
                        resultObj = null
                      }
                      const cards = resultObj?.study_cards as Array<Record<string, unknown>> | undefined
                      if (Array.isArray(cards) && cards.length > 0) {
                        return (
                          <div className="space-y-3">
                            {cards.map((card, ci) => (
                              <div key={ci} className="rounded-lg border p-3 space-y-2" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="status-chip rounded border px-1.5 py-0.5 text-[11px] font-bold uppercase tracking-[0.1em]" style={{ borderColor: 'rgba(255,255,255,0.15)', color: 'var(--color-on-surface-variant)' }}>
                                    {String(card.agent || '')} — {String(card.department || '')}
                                  </span>
                                </div>
                                <div className="text-[11px] font-bold" style={{ color: 'var(--color-on-surface)' }}>
                                  {String(card.study_focus || '')}
                                </div>
                                {Array.isArray(card.reusable_principles) && card.reusable_principles.length > 0 && (
                                  <div>
                                    <div className="text-[11px] font-semibold uppercase tracking-[0.1em] mb-0.5" style={{ color: 'var(--color-on-surface-variant)' }}>Key Principles</div>
                                    <ul className="space-y-0.5">
                                      {card.reusable_principles.map((principle: unknown, pi: number) => (
                                        <li key={pi} className="flex items-start gap-1.5 text-xs" style={{ color: 'var(--color-on-surface)' }}>
                                          <span className="mt-0.5 h-1 w-1 shrink-0 rounded-full bg-amber-400" />
                                          {String(principle)}
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                                {Array.isArray(card.observations_to_make) && card.observations_to_make.length > 0 && (
                                  <div>
                                    <div className="text-[11px] font-semibold uppercase tracking-[0.1em] mb-0.5" style={{ color: 'var(--color-on-surface-variant)' }}>Observations</div>
                                    <ul className="space-y-0.5">
                                      {card.observations_to_make.map((obs: unknown, oi: number) => (
                                        <li key={oi} className="flex items-start gap-1.5 text-xs" style={{ color: 'var(--color-on-surface)' }}>
                                          <span className="mt-0.5 h-1 w-1 shrink-0 rounded-full bg-amber-400" />
                                          {String(obs)}
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                                {Array.isArray(card.next_actions) && card.next_actions.length > 0 && (
                                  <div>
                                    <div className="text-[11px] font-semibold uppercase tracking-[0.1em] mb-0.5" style={{ color: 'var(--color-on-surface-variant)' }}>Next Actions</div>
                                    <ul className="space-y-0.5">
                                      {card.next_actions.map((action: unknown, ai: number) => (
                                        <li key={ai} className="flex items-start gap-1.5 text-xs" style={{ color: 'var(--color-on-surface)' }}>
                                          <span className="mt-0.5 h-1 w-1 shrink-0 rounded-full bg-amber-400" />
                                          {String(action)}
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )
                      }
                      return (
                        <p className="text-on-surface text-sm leading-relaxed font-body whitespace-pre-wrap" style={{ color: 'var(--color-on-surface)' }}>
                          {typeof analysisResult === 'string' ? analysisResult : JSON.stringify(analysisResult, null, 2)}
                        </p>
                      )
                    })()}
                  </div>
                )}
              </div></div></details>
              <details className="rounded-lg border border-white/10 p-4"><summary className="cursor-pointer text-sm text-zinc-300">Add from the Studio Brain library</summary><div className="pt-4"><div className="glass-panel rounded-xl p-4">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <FileText size={15} style={{ color: 'var(--color-secondary)' }} />
                    <span className="text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>PERMANENT STUDIO BRAIN</span>
                  </div>
                  <button
                    type="button"
                    onClick={handleAttachStudioBrainFiles}
                    disabled={!resolvedProjectId || selectedStudioBrainCount === 0 || attachingStudioBrainFiles}
                    aria-busy={attachingStudioBrainFiles}
                    className="flex items-center gap-1 rounded border border-white/10 px-2 py-1 text-[11px] font-bold uppercase tracking-wider transition-all hover:bg-white/10 disabled:opacity-50"
                    style={{ color: 'var(--color-secondary)' }}
                    title="Add selected Studio Brain files to this project"
                  >
                    {attachingStudioBrainFiles ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} />}
                    ADD SELECTED {selectedStudioBrainCount > 0 ? `(${selectedStudioBrainCount})` : ''}
                  </button>
                </div>

                {loadingStudioBrainFiles ? (
                  <div className="flex items-center justify-center py-6">
                    <Loader2 size={18} className="animate-spin" style={{ color: 'var(--color-primary)' }} />
                  </div>
                ) : (
                  <div className="max-h-[260px] overflow-y-auto pr-1">
                    <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                      {studioBrainFiles.map((file) => {
                        const selected = selectedStudioBrainFiles.has(file.filename)
                        return (
                          <label
                            key={file.filename}
                            className={`flex cursor-pointer items-start gap-2 rounded-lg border p-2.5 transition-all ${selected ? 'bg-secondary/10' : 'hover:bg-white/5'}`}
                            style={{ borderColor: selected ? 'rgba(76,215,246,0.45)' : 'rgba(255,255,255,0.08)' }}
                          >
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={() => toggleStudioBrainFile(file.filename)}
                              className="mt-0.5 h-4 w-4 shrink-0"
                            />
                            <span className="min-w-0">
                              <span className="block truncate text-[12px] font-bold" style={{ color: 'var(--color-on-surface)' }}>{file.title}</span>
                              <span className="mt-0.5 block text-[11px] font-semibold uppercase tracking-[0.08em]" style={{ color: 'var(--color-secondary)' }}>{file.study_focus}</span>
                              {file.summary && <span className="mt-1 line-clamp-2 block text-xs leading-relaxed" style={{ color: 'var(--color-on-surface-variant)' }}>{file.summary}</span>}
                            </span>
                          </label>
                        )
                      })}
                      {studioBrainFiles.length === 0 && (
                        <p className="col-span-full text-center text-xs py-4" style={{ color: 'var(--color-on-surface-variant)' }}>No permanent Studio Brain Markdown files found.</p>
                      )}
                    </div>
                  </div>
                )}
              </div></div></details>
              <details className="rounded-lg border border-white/10 p-4"><summary className="cursor-pointer text-xs text-zinc-400">Library maintenance</summary><p className="mt-3 text-xs leading-relaxed text-zinc-400">Reorganize existing references when you want their categories refreshed.</p><button type="button" disabled={reorganizing || !resolvedProjectId} aria-busy={reorganizing} onClick={() => void handleReorganizeReferences()} className="mt-3 rounded border border-white/15 px-3 py-2 text-xs text-zinc-200 disabled:opacity-40">{reorganizing ? 'Reorganizing…' : 'Reorganize references'}</button></details>
              <button type="button" onClick={() => setStudyStep('guidance')} className="rounded-md bg-amber-200 px-4 py-3 text-sm font-medium text-zinc-950 hover:bg-amber-100">Review saved guidance →</button>
            </section>
            <section aria-label="Saved creative guidance" className={studyStep === 'guidance' ? 'space-y-5' : 'hidden'}>
              <div><h2 className="text-lg font-medium text-zinc-100">Keep the direction you believe in</h2><p className="mt-1 max-w-2xl text-sm leading-relaxed text-zinc-400">Save a creative decision when it belongs to this film. Uploading a reference is separate from saving your own direction.</p></div>
              <div className="glass-panel rounded-xl p-4" id="teach-studio-bar">
                <div className="flex flex-wrap items-center gap-3">
                  <MessageSquare size={14} style={{ color: 'var(--color-on-surface-variant)' }} />
                  <input type="text" aria-label="Creative decision to remember" value={ingestText} onChange={(e) => setIngestText(e.target.value)} placeholder="The direction I want to remember for this film…" className="cyber-input min-w-0 basis-[220px] flex-1 rounded px-3 py-2 text-sm outline-none" style={{ color: 'var(--color-on-surface)' }} onKeyDown={(e) => { if (e.key === 'Enter') void handleIngest() }} />
                  <button type="button" onClick={handleIngest} disabled={ingesting || !ingestText.trim()} aria-busy={ingesting} className="flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-xs font-bold uppercase tracking-[0.1em] transition-all hover:scale-[1.02] disabled:opacity-50" style={{ background: 'rgba(255,209,101,0.15)', color: 'var(--color-primary)', border: '1px solid rgba(255,209,101,0.3)' }}>
                    {ingesting ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                    Save this decision
                  </button>
                </div>
                {ingestConfirmed && <div className="mt-2 text-xs font-semibold transition-opacity duration-300" style={{ color: 'var(--color-secondary)' }}>● LEARNED — added to Director's Memory</div>}
              </div>
              <div className="glass-panel rounded-xl p-4 space-y-4">
                {/* Header */}
                <div className="flex items-center gap-2">
                  <span className="status-chip rounded border px-1.5 py-0.5 text-[11px] font-bold uppercase tracking-[0.12em]" style={{ borderColor: 'rgba(255,255,255,0.1)', color: 'var(--color-on-surface-variant)' }}>memory</span>
                  <span className="font-metadata-sm text-[11px] font-bold uppercase tracking-[0.15em]" style={{ color: 'var(--color-secondary)' }}>ACTIVE MEMORY</span>
                </div>

                {loadingMemories ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 size={20} className="animate-spin" style={{ color: 'var(--color-primary)' }} />
                  </div>
                ) : (
                  <>
                    <MemorySection
                      title="LEARNED STYLE"
                      items={styleMemories}
                      emptyLabel="No style memories yet"
                      teachPlaceholder="My visual style is..."
                      onTeach={(placeholder) => {
                        setIngestText(placeholder)
                        document.getElementById('teach-studio-bar')?.scrollIntoView({ behavior: 'smooth' })
                      }}
                    />
                    <MemorySection
                      title="TONE RULES"
                      items={toneMemories}
                      emptyLabel="No tone memories yet"
                      teachPlaceholder="The emotional tone I want is..."
                      onTeach={(placeholder) => {
                        setIngestText(placeholder)
                        document.getElementById('teach-studio-bar')?.scrollIntoView({ behavior: 'smooth' })
                      }}
                    />
                    <MemorySection
                      title="PACING"
                      items={pacingMemories}
                      emptyLabel="No pacing memories yet"
                      teachPlaceholder="My pacing approach is..."
                      onTeach={(placeholder) => {
                        setIngestText(placeholder)
                        document.getElementById('teach-studio-bar')?.scrollIntoView({ behavior: 'smooth' })
                      }}
                    />
                  </>
                )}

                {/* Film Reference Ingest Section */}


                <button type="button" onClick={() => setShowMemoryDrawer(true)} className="glass-panel w-full rounded-lg px-3 py-2 text-xs font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01]" style={{ color: 'var(--color-on-surface-variant)' }}>OPEN FULL MEMORY BANK</button>
              </div>
            </section>
          </div>

          {showMemoryDrawer && (
            <div className="mx-auto mb-8 max-w-[1288px] rounded-lg border border-white/15 bg-zinc-950 p-5">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>DIRECTOR'S MEMORY</span>
                <button type="button" onClick={() => setShowMemoryDrawer(false)} aria-label="Close saved memories" className="rounded p-1 transition-all hover:bg-white/10" style={{ color: 'var(--color-on-surface-variant)' }}><X size={14} /></button>
              </div>

              {loadingMemories ? (
                <div className="flex items-center justify-center py-6"><Loader2 size={20} className="animate-spin" style={{ color: 'var(--color-primary)' }} /></div>
              ) : allMemories.length === 0 ? (
                <div className="text-xs" style={{ color: 'var(--color-on-surface-variant)' }}>No memories saved yet. Save references to build your memory bank.</div>
              ) : (
                <div className="space-y-2">
                  {allMemories.map((mem) => (
                    <div key={mem.entry_id} className="rounded-lg border p-2.5" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                      <div className="mb-1 flex items-center justify-between">
                        <span className="truncate text-[11px] font-semibold" style={{ color: 'var(--color-on-surface)' }}>{mem.text}</span>
                        <button type="button" onClick={() => void handleDeleteMemory(mem.entry_id, mem.kind)} disabled={deletingMemoryId === mem.entry_id} aria-busy={deletingMemoryId === mem.entry_id} aria-label={`Forget saved memory: ${mem.text}`} className="ml-1 rounded p-2 transition-all hover:bg-white/10 disabled:opacity-40" style={{ color: 'var(--color-error)' }}>{deletingMemoryId === mem.entry_id ? <Loader2 size={10} className="animate-spin" /> : <Trash2 size={10} />}</button>
                      </div>
                      <p className="text-[11px] uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>{mem.kind}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </ProjectGuard>
      </StudioShell>
    </>
  )
}
