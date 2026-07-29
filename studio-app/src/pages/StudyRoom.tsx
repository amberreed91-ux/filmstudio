import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Brain,
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
import { useStudio } from '../context/StudioContext'
import {
  STUDIO_API_BASE,
  deleteDirectorMemoryEntry,
  getDirectorMemory,
  getStudioProject,
  listProjects,
  reorganizeReferenceLibrary,
  saveCreativeDecisionMemory,
  saveDirectorMemoryEntry,
  studyReferencePrompt,
} from '../lib/studioApi'
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
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-on-surface)' }}>
        {title}
      </div>
      {items.length === 0 ? (
        <div>
          <p className="text-on-surface-variant body-md text-[11px]">{emptyLabel}</p>
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
  const { activeProjectId } = useStudio()

  // useMemo (derived values, no side effects)
  const queryProjectId = useMemo(() => searchParams.get('project_id') || '', [searchParams])
  const effectiveProjectId = useMemo(() => activeProjectId || queryProjectId || null, [activeProjectId, queryProjectId])
  const [resolvedProjectId, setResolvedProjectId] = useState<string | null>(null)

  useEffect(() => {
    if (effectiveProjectId) {
      setResolvedProjectId(effectiveProjectId)
      return
    }
    const timeout = setTimeout(async () => {
      try {
        const result = await listProjects()
        if (result.projects?.length > 0) {
          setResolvedProjectId(result.projects[0].project_id)
        }
      } catch (e) {
        console.error('Could not resolve project:', e)
      }
    }, 3000)
    return () => clearTimeout(timeout)
  }, [effectiveProjectId])

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

  // useRef — ALL of them
  const fileInputRef = useRef<HTMLInputElement>(null)

  // useMemo — derived computations (no side effects)
  const { styleMemories, toneMemories, pacingMemories, allMemories } = useMemo(
    () => categorizeDirectorMemory(memoryBundle),
    [memoryBundle],
  )
  const memoryCount = allMemories.length

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
      // First re-categorize all existing references using content-based category detection
      try {
        await reorganizeReferenceLibrary(resolvedProjectId)
      } catch {
        // Non-critical — continue even if reorg fails
      }
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

  const loadMemories = useCallback(async () => {
    if (!resolvedProjectId) return
    setLoadingMemories(true)
    try {
      const response = await getDirectorMemory(resolvedProjectId)
      const bundle = response.memory ?? EMPTY_BUNDLE
      console.log('Memory count set to:', Object.values(bundle).flat().length, 'source: API response', 'project_id:', resolvedProjectId)
      setMemoryBundle(bundle)
    } catch (err) {
      // Suppress 404 errors for non-critical endpoints
      const is404 = err instanceof Error && err.message.includes('404')
      if (!is404) {
        console.error('loadMemories failed:', err)
      }
      console.log('Memory count set to: 0', 'source: error fallback')
      setMemoryBundle(EMPTY_BUNDLE)
    } finally {
      setLoadingMemories(false)
    }
  }, [resolvedProjectId])

  const handleSaveReference = useCallback(async (ref: ReferenceCard) => {
    if (!resolvedProjectId) return
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
    }
  }, [resolvedProjectId, loadMemories])

  const handleReferenceCardClick = useCallback((ref: ReferenceCard) => {
    setIngestText(`From reference "${ref.title}": ${ref.summary}`)
    document.getElementById('teach-studio-bar')?.scrollIntoView({ behavior: 'smooth' })
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
    try {
      await deleteDirectorMemoryEntry(resolvedProjectId, kind, entryId)
      void loadMemories()
    } catch {
      setError('Failed to delete memory')
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
  }, [filmTitle, filmDimensions, resolvedProjectId, loadReferences])

  const getFileCategory = (file: File): string => {
    const ext = file.name.toLowerCase().split('.').pop() || ''
    const mime = file.type
    if (MIME_TYPE_MAP[mime]) return MIME_TYPE_MAP[mime]
    if (['mp4', 'mov'].includes(ext)) return 'film'
    if (['mp3', 'wav'].includes(ext)) return 'audio'
    if (['pdf', 'txt', 'fdx', 'md'].includes(ext)) return 'document'
    return 'document'
  }

  const handleFileIngest = useCallback(async (files: File[]) => {
    console.log('handleFileIngest called:', {
      files: files.map(f => f.name),
      resolvedProjectId,
    })
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
        console.log('About to call API with:', { projectId: resolvedProjectId, fileName: file.name })
        uploadFileWithProgress(resolvedProjectId, file)
      }
    } catch (err) {
      console.error('handleFileIngest failed:', err)
    }
  }, [resolvedProjectId, filmDimensions])

  const uploadFileWithProgress = (projectId: string, file: File) => {
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
  }

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
          <ProjectContextBar roomName="study" />

          {/* Status messages */}
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
          </div>

          {/* TWO-PANEL LAYOUT */}
          <div className="flex h-[calc(100vh-160px)] w-full gap-4 px-4 pb-4">
            {/* LEFT: ACTIVE MEMORY PANEL (33%) */}
            <div className="flex w-[33%] flex-col gap-4 overflow-y-auto">
              <div className="glass-panel rounded-xl p-4 space-y-4">
                {/* Header */}
                <div className="flex items-center gap-2">
                  <span className="status-chip rounded border px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-[0.12em]" style={{ borderColor: 'rgba(255,255,255,0.1)', color: 'var(--color-on-surface-variant)' }}>memory</span>
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
                <div className="glass-panel rounded-lg p-3 space-y-3">
                   <div className="flex items-center gap-2">
                     <Film size={14} style={{ color: 'var(--color-secondary)' }} />
                     <span className="font-metadata-sm text-[10px] font-bold uppercase tracking-[0.15em]" style={{ color: 'var(--color-secondary)' }}>FILM REFERENCES</span>
                     {!resolvedProjectId && <span className="ml-1.5 h-2 w-2 rounded-full bg-amber-400 animate-pulse" />}
                   </div>

                  {/* Segmented Control */}
                  <div className="flex rounded-lg border p-0.5" style={{ borderColor: 'rgba(255,255,255,0.1)' }}>
                    <button type="button" onClick={() => setFilmIngestMode('title')} className={`flex-1 rounded px-2 py-1.5 text-[9px] font-bold uppercase tracking-[0.08em] transition-all ${filmIngestMode === 'title' ? 'bg-white/10 text-on-surface' : 'text-on-surface-variant hover:bg-white/5'}`}>FILM TITLE</button>
                    <button type="button" onClick={() => setFilmIngestMode('upload')} className={`flex-1 rounded px-2 py-1.5 text-[9px] font-bold uppercase tracking-[0.08em] transition-all ${filmIngestMode === 'upload' ? 'bg-white/10 text-on-surface' : 'text-on-surface-variant hover:bg-white/5'}`}>UPLOAD FILE</button>
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
                      <input type="text" value={filmTitle} onChange={(e) => { setFilmTitle(e.target.value); if (filmTitleInvalid) setFilmTitleInvalid(false) }} onKeyDown={(e) => { if (e.key === 'Enter') void handleFilmTitleIngest() }} placeholder="Film title, director, year..." className={`cyber-input w-full rounded px-2 py-1.5 text-xs outline-none ${filmTitleInvalid ? 'animate-shake border-rose-400' : ''}`} style={{ color: 'var(--color-on-surface)' }} />
                      <div className="flex items-center gap-2">
                        <span className="text-[9px] font-semibold uppercase tracking-[0.08em]" style={{ color: 'var(--color-on-surface-variant)' }}>ANALYZE FOR →</span>
                        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                        <select value={filmDimensions} onChange={(e) => setFilmDimensions(e.target.value as any)} className="cyber-input rounded px-2 py-1 text-[10px] font-bold uppercase tracking-[0.08em] outline-none" style={{ color: 'var(--color-on-surface)' }}>
                          <option value="all">All Dimensions</option>
                          <option value="cinematography">Cinematography</option>
                          <option value="editing">Editing</option>
                          <option value="sound">Sound</option>
                          <option value="narrative">Narrative</option>
                        </select>
                      </div>
                       <button type="button" onClick={handleFilmTitleIngest} disabled={filmProcessing || !resolvedProjectId} title={!resolvedProjectId ? 'Loading project...' : undefined} className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01] disabled:opacity-50" style={{ background: 'rgba(255,209,101,0.15)', color: 'var(--color-primary)', border: '1px solid rgba(255,209,101,0.3)' }}>
                        {filmProcessing ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                        {filmProcessing ? 'ANALYZING...' : '+ INGEST FILM'}
                      </button>
                    </div>
                  )}

                  {/* UPLOAD FILE Mode */}
                  {filmIngestMode === 'upload' && (
                    <div className="space-y-2">
                       <div role="button" tabIndex={0} onClick={() => fileInputRef.current?.click()} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click() }} title={!resolvedProjectId ? 'Loading project...' : undefined} className={`rounded-lg border-2 border-dashed p-4 text-center transition-all cursor-pointer ${isDragging ? 'border-secondary shadow-[0_0_20px_rgba(76,215,246,0.3)]' : 'border-outline-variant'} ${!resolvedProjectId ? 'opacity-50 pointer-events-none' : ''}`} style={isDragging ? undefined : { borderColor: 'rgba(255,255,255,0.2)' }} onDragEnter={handleDragEnter} onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}>
                        <Upload size={20} className="mx-auto mb-2" style={{ color: 'var(--color-on-surface-variant)' }} />
                        <p className="text-[10px]" style={{ color: 'var(--color-on-surface-variant)' }}>{filmFile ? filmFile.name : 'Drop a file here or click to browse'}</p>
                        <p className="text-[8px] mt-1" style={{ color: 'var(--color-on-surface-variant)' }}>PDF, FDX, TXT, MD, MP4, MOV, MP3, WAV supported</p>
                      </div>

                      {Object.values(uploadProgress).map((item) => (
                        <div key={item.filename} className={`glass-panel rounded-lg p-2.5 ${item.status === 'error' ? '!border-rose-400/40' : ''}`}>
                          <div className="flex items-center gap-2 mb-1">
                            <Upload size={12} style={{ color: 'var(--color-on-surface-variant)' }} />
                            <span className="flex-1 truncate text-[10px] font-medium" style={{ color: 'var(--color-on-surface)' }}>{item.filename}</span>
                            {item.status === 'complete' && <span className="text-[9px] font-bold uppercase tracking-wider" style={{ color: 'var(--color-secondary)' }}>● INGESTED</span>}
                            {item.status === 'error' && <span className="text-[9px] font-bold uppercase tracking-wider text-rose-300">⚠ ERROR</span>}
                          </div>
                          <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
                            <div className={`h-full rounded-full transition-all duration-300 ${item.status === 'error' ? 'bg-rose-400' : 'bg-[var(--color-primary)]'}`} style={{ width: `${item.progress}%` }} />
                          </div>
                          <div className="mt-1 flex justify-between">
                            <span className="text-[8px]" style={{ color: 'var(--color-on-surface-variant)' }}>{item.status === 'uploading' ? `${item.progress}%` : item.status === 'complete' ? 'Complete' : item.error || 'Failed'}</span>
                            {item.status === 'complete' && <span className="text-[8px] text-emerald-300">✓</span>}
                          </div>
                        </div>
                      ))}

                      <div className="flex items-center gap-2">
                        <span className="text-[9px] font-semibold uppercase tracking-[0.08em]" style={{ color: 'var(--color-on-surface-variant)' }}>ANALYZE FOR →</span>
                        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                        <select value={filmDimensions} onChange={(e) => setFilmDimensions(e.target.value as any)} className="cyber-input rounded px-2 py-1 text-[10px] font-bold uppercase tracking-[0.08em] outline-none" style={{ color: 'var(--color-on-surface)' }}>
                          <option value="all">All Dimensions</option>
                          <option value="cinematography">Cinematography</option>
                          <option value="editing">Editing</option>
                          <option value="sound">Sound</option>
                          <option value="narrative">Narrative</option>
                        </select>
                      </div>
                      <button type="button" onClick={() => { if (!resolvedProjectId) return; if (filmFile) { uploadFileWithProgress(resolvedProjectId, filmFile) } else if (Object.keys(uploadProgress).length === 0) { setError('Select files by clicking the drop zone or dragging files in') } }} disabled={filmProcessing || !resolvedProjectId} title={!resolvedProjectId ? 'Loading project...' : undefined} className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01] disabled:opacity-50" style={{ background: 'rgba(255,209,101,0.15)', color: 'var(--color-primary)', border: '1px Solid rgba(255,209,101,0.3)' }}>
                        {filmProcessing ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                        {filmProcessing ? 'PROCESSING...' : '+ INGEST FILE'}
                      </button>
                    </div>
                  )}

                  {filmProcessing && (
                    <div className="glass-panel rounded-lg p-3">
                      <p className="font-bold text-xs" style={{ color: 'var(--color-on-surface)' }}>{filmTitle || filmFile?.name || 'Film Reference'}</p>
                      <p className="mt-1 text-[9px] font-bold uppercase tracking-[0.1em] animate-pulse" style={{ color: 'var(--color-secondary)' }}>ANALYZING...</p>
                    </div>
                  )}

                  {filmLearned && !filmProcessing && (
                    <div className="glass-panel rounded-lg p-3">
                      <p className="font-bold text-xs" style={{ color: 'var(--color-on-surface)' }}>{filmTitle || filmFile?.name || 'Film Reference'}</p>
                      <ul className="mt-2 space-y-1">
                        {filmLearned.slice(0, 4).map((insight, idx) => (
                          <li key={idx} className="font-metadata-sm text-[10px]" style={{ color: 'var(--color-on-surface-variant)' }}>● Learned: {insight}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {filmIngestConfirmed && (
                    <div className="text-[10px] font-semibold transition-opacity duration-300" style={{ color: 'var(--color-secondary)' }}>● INGESTED — added to Reference Library</div>
                  )}
                </div>

                <button type="button" onClick={() => setShowMemoryDrawer(true)} className="glass-panel w-full rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01]" style={{ color: 'var(--color-on-surface-variant)' }}>OPEN FULL MEMORY BANK</button>
              </div>
            </div>

            {/* RIGHT: RESEARCH PANEL (67%) */}
            <div className="flex flex-[2] flex-col gap-4 overflow-y-auto">
              {resolvedProjectId && <KnowledgeLibraryPanel projectId={resolvedProjectId} />}

              <div className="glass-panel rounded-xl p-3">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex flex-wrap gap-1">
                    {(Object.entries(CATEGORY_LABELS) as [CategoryFilter, string][]).map(([key, label]) => (
                      <button key={key} type="button" onClick={() => setCategory(key)} className={`status-chip rounded border px-2 py-1 text-[8px] font-bold uppercase tracking-[0.08em] transition-all ${category === key ? 'border-primary/50 bg-primary/15 text-primary' : 'hover:bg-white/8'}`} style={{ borderColor: category === key ? undefined : 'rgba(255,255,255,0.08)', color: category === key ? undefined : 'var(--color-on-surface-variant)' }}>{label}</button>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {(Object.entries(BATCH_LABELS) as [IntelligenceBatch, string][]).map(([key, label]) => {
                      const isActive = activeBatches.has(key)
                      return (
                        <button key={key} type="button" onClick={() => toggleBatch(key)} className={`status-chip rounded border px-2 py-1 text-[8px] font-bold uppercase tracking-[0.08em] transition-all ${isActive ? 'border-secondary/50 bg-secondary/15 text-secondary' : 'hover:bg-white/8'}`} style={{ borderColor: isActive ? undefined : 'rgba(255,255,255,0.08)', color: isActive ? undefined : 'var(--color-on-surface-variant)' }}>[{key[0].toUpperCase()}] {label}</button>
                      )
                    })}
                  </div>
                </div>
              </div>

                <div className="glass-panel rounded-xl p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>REFERENCE LIBRARY</span>
                    <div className="flex items-center gap-3">
                      <span className="text-[9px]" style={{ color: 'var(--color-on-surface-variant)' }}>{filteredReferences.length} items</span>
                      <button type="button" onClick={() => setFilmIngestMode('upload')} className="flex items-center gap-1 rounded border border-white/10 px-2 py-1 text-[9px] font-bold uppercase tracking-wider transition-all hover:bg-white/10" style={{ color: 'var(--color-secondary)' }} title="Add a new reference"><Plus size={10} />ADD REFERENCE</button>
                    </div>
                  </div>

                  <div className="overflow-y-auto max-h-[600px]">
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                      {filteredReferences.map((ref) => (
                        <div key={ref.id} className="glass-panel rounded-lg p-3 transition-all hover:scale-[1.01] cursor-pointer group relative" onClick={() => handleReferenceCardClick(ref)} title="Click to use this reference in Teach Studio">
                          <div className="mb-1 text-[9px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-secondary)' }}>{ref.category}</div>
                          <h3 className="mb-1 text-[13px] font-bold pr-6" style={{ color: 'var(--color-on-surface)' }}>{ref.title}</h3>
                          <p className="line-clamp-2 text-[10px] leading-relaxed" style={{ color: 'var(--color-on-surface-variant)' }}>{ref.summary}</p>
                          {ref.source && <p className="mt-1.5 text-[8px]" style={{ color: 'var(--color-on-surface-variant)' }}>Source: {ref.source}</p>}
                          <button type="button" onClick={(e) => { e.stopPropagation(); void handleSaveReference(ref) }} className="absolute top-2.5 right-2 rounded p-1 transition-all hover:bg-white/10 opacity-0 group-hover:opacity-100" style={{ color: 'var(--color-secondary)' }} title="Save to Director's Memory">
                            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z" /></svg>
                          </button>
                        </div>
                      ))}
                      {filteredReferences.length === 0 && !loadingRefs && (
                        <p className="col-span-full text-center text-[11px] py-4" style={{ color: 'var(--color-on-surface-variant)' }}>No references match the current filters. Click + ADD REFERENCE to add one.</p>
                      )}
                    </div>
                  </div>
                </div>

              <div className="glass-panel rounded-xl border-l-2 p-4" id="ask-studio-brain" style={{ borderLeftColor: 'var(--color-secondary)' }}>
                <div className="mb-3 flex items-center gap-1.5">
                  <Brain size={16} style={{ color: 'var(--color-secondary)' }} />
                  <span className="text-[11px] font-semibold uppercase tracking-[0.14em]" style={{ color: 'var(--color-secondary)' }}>ASK STUDIO BRAIN</span>
                </div>

                <textarea value={queryText} onChange={(e) => setQueryText(e.target.value)} placeholder="Enter a research question, topic, or area you'd like Studio Brain to analyze..." rows={3} className="cyber-input mb-3 w-full rounded px-3 py-2 text-sm outline-none" style={{ color: 'var(--color-on-surface)' }} />

                <button type="button" onClick={handleAnalyze} disabled={analyzing || !queryText.trim()} className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[11px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.01] disabled:opacity-50" style={{ background: 'rgba(255,209,101,0.15)', color: 'var(--color-primary)', border: '1px solid rgba(255,209,101,0.3)' }}>
                  {analyzing ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                  {analyzing ? 'ANALYZING...' : 'ANALYZE'}
                </button>

                {analysisResult && (
                  <div className="glass-panel mt-3 rounded-lg border-l-2 p-4" style={{ borderLeftColor: 'var(--color-secondary)' }}>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="status-chip bg-secondary/20 text-secondary text-[9px] font-bold uppercase tracking-[0.1em] px-2 py-1 rounded">ANALYSIS COMPLETE</span>
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
                                  <span className="status-chip rounded border px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-[0.1em]" style={{ borderColor: 'rgba(255,255,255,0.15)', color: 'var(--color-on-surface-variant)' }}>
                                    {String(card.agent || '')} — {String(card.department || '')}
                                  </span>
                                </div>
                                <div className="text-[11px] font-bold" style={{ color: 'var(--color-on-surface)' }}>
                                  {String(card.study_focus || '')}
                                </div>
                                {Array.isArray(card.reusable_principles) && card.reusable_principles.length > 0 && (
                                  <div>
                                    <div className="text-[9px] font-semibold uppercase tracking-[0.1em] mb-0.5" style={{ color: 'var(--color-on-surface-variant)' }}>Key Principles</div>
                                    <ul className="space-y-0.5">
                                      {card.reusable_principles.map((principle: unknown, pi: number) => (
                                        <li key={pi} className="flex items-start gap-1.5 text-[10px]" style={{ color: 'var(--color-on-surface)' }}>
                                          <span className="mt-0.5 h-1 w-1 shrink-0 rounded-full bg-amber-400" />
                                          {String(principle)}
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                                {Array.isArray(card.observations_to_make) && card.observations_to_make.length > 0 && (
                                  <div>
                                    <div className="text-[9px] font-semibold uppercase tracking-[0.1em] mb-0.5" style={{ color: 'var(--color-on-surface-variant)' }}>Observations</div>
                                    <ul className="space-y-0.5">
                                      {card.observations_to_make.map((obs: unknown, oi: number) => (
                                        <li key={oi} className="flex items-start gap-1.5 text-[10px]" style={{ color: 'var(--color-on-surface)' }}>
                                          <span className="mt-0.5 h-1 w-1 shrink-0 rounded-full bg-amber-400" />
                                          {String(obs)}
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                                {Array.isArray(card.next_actions) && card.next_actions.length > 0 && (
                                  <div>
                                    <div className="text-[9px] font-semibold uppercase tracking-[0.1em] mb-0.5" style={{ color: 'var(--color-on-surface-variant)' }}>Next Actions</div>
                                    <ul className="space-y-0.5">
                                      {card.next_actions.map((action: unknown, ai: number) => (
                                        <li key={ai} className="flex items-start gap-1.5 text-[10px]" style={{ color: 'var(--color-on-surface)' }}>
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
              </div>

              <div className="glass-panel rounded-xl p-4" id="teach-studio-bar">
                <div className="flex items-center gap-2">
                  <MessageSquare size={14} style={{ color: 'var(--color-on-surface-variant)' }} />
                  <input type="text" value={ingestText} onChange={(e) => setIngestText(e.target.value)} placeholder="Teach Studio a new pattern..." className="cyber-input flex-1 rounded px-3 py-1.5 text-xs outline-none" style={{ color: 'var(--color-on-surface)' }} onKeyDown={(e) => { if (e.key === 'Enter') void handleIngest() }} />
                  <button type="button" onClick={handleIngest} disabled={ingesting || !ingestText.trim()} className="flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-[10px] font-bold uppercase tracking-[0.1em] transition-all hover:scale-[1.02] disabled:opacity-50" style={{ background: 'rgba(255,209,101,0.15)', color: 'var(--color-primary)', border: '1px solid rgba(255,209,101,0.3)' }}>
                    {ingesting ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                    INGEST
                  </button>
                </div>
                {ingestConfirmed && <div className="mt-2 text-[10px] font-semibold transition-opacity duration-300" style={{ color: 'var(--color-secondary)' }}>● LEARNED — added to Director's Memory</div>}
              </div>
            </div>
          </div>

          <button type="button" onClick={() => setShowMemoryDrawer(true)} className="glass-panel fixed right-4 top-4 z-30 flex items-center gap-2 rounded-lg px-3 py-1.5 transition-all hover:scale-[1.05]" style={{ color: 'var(--color-on-surface-variant)' }}>
            <Brain size={14} />
            <span className="text-[10px] font-bold uppercase tracking-[0.1em]">{memoryCount} MEMOR{memoryCount === 1 ? 'Y' : 'IES'}</span>
          </button>

          {showMemoryDrawer && (
            <div className="glass-panel fixed right-4 top-14 z-40 w-[320px] rounded-xl p-4 shadow-2xl" style={{ maxHeight: 'calc(100vh - 100px)', overflowY: 'auto' }}>
              <div className="mb-3 flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>DIRECTOR'S MEMORY</span>
                <button type="button" onClick={() => setShowMemoryDrawer(false)} className="rounded p-1 transition-all hover:bg-white/10" style={{ color: 'var(--color-on-surface-variant)' }}><X size={14} /></button>
              </div>

              {loadingMemories ? (
                <div className="flex items-center justify-center py-6"><Loader2 size={20} className="animate-spin" style={{ color: 'var(--color-primary)' }} /></div>
              ) : allMemories.length === 0 ? (
                <div className="text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>No memories saved yet. Save references to build your memory bank.</div>
              ) : (
                <div className="space-y-2">
                  {allMemories.map((mem) => (
                    <div key={mem.entry_id} className="rounded-lg border p-2.5" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                      <div className="mb-1 flex items-center justify-between">
                        <span className="truncate text-[11px] font-semibold" style={{ color: 'var(--color-on-surface)' }}>{mem.text}</span>
                        <button type="button" onClick={() => void handleDeleteMemory(mem.entry_id, mem.kind)} className="ml-1 rounded p-0.5 transition-all hover:bg-white/10" style={{ color: 'var(--color-error)' }}><Trash2 size={10} /></button>
                      </div>
                      <p className="text-[8px] uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>{mem.kind}</p>
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
