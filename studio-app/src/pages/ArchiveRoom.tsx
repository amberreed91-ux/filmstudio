import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  Archive,
  CheckCircle2,
  Download,
  Edit3,
  Filter,
  Loader2,
  Play,
  Plus,
  Search,
  Trash2,
  X,
  ImageIcon,
  FileVideo,
  Music,
  FileType2,
  Upload,
} from 'lucide-react'
import StudioShell from '../components/StudioShell'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import {
  deleteProject,
  fetchExportPackage,
  getProjectDecisionGate,
  listProjects,
  listScenes,
  listVideoAssetsForProject,
  type PersistedProjectState,
  type Scene,
} from '../lib/studioApi'

// ── Types ──────────────────────────────────────────────────────────────────

type SortMode = 'recent' | 'az' | 'status'
type FilterMode = 'all' | 'in_progress' | 'complete'
type FilmStatus = 'complete' | 'in_progress' | 'draft'

interface FilmEntry {
  project: PersistedProjectState
  status: FilmStatus
  sceneCount: number
  genre: string
  logline: string
  thumbnailUrl?: string
}

interface AssetEntry {
  asset_id: string
  source_type: string
  source_url?: string
  status: string
  filename?: string
  content_type?: string
  title?: string
}

interface ReadinessIssue {
  id: string
  severity: 'error' | 'warning' | 'info'
  message: string
}

// ── Helpers ────────────────────────────────────────────────────────────────

const SORT_LABELS: Record<SortMode, string> = {
  recent: 'Most Recent',
  az: 'A-Z',
  status: 'Status',
}

const FILTER_LABELS: Record<FilterMode, string> = {
  all: 'ALL',
  in_progress: 'IN PROGRESS',
  complete: 'SCENES APPROVED',
}

function statusBadgeClass(status: FilmStatus): string {
  switch (status) {
    case 'complete':
      return 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10'
    case 'in_progress':
      return 'text-amber-400 border-amber-400/30 bg-amber-400/10 animate-pulse'
    case 'draft':
      return 'text-zinc-400 border-zinc-400/30 bg-zinc-400/5'
  }
}

function deriveStatus(project: PersistedProjectState, scenes: Scene[]): FilmStatus {
  const approvedCount = project.approved_scenes?.length || 0
  const reviewedCount = project.reviewed_scenes?.length || 0
  if (approvedCount > 0 && approvedCount >= scenes.length && scenes.length > 0) return 'complete'
  if (reviewedCount > 0 || approvedCount > 0) return 'in_progress'
  return 'draft'
}

function deriveGenre(project: PersistedProjectState): string {
  const exec = project.execution_summary as Record<string, unknown>
  const genre = exec?.genre
  if (typeof genre === 'string' && genre.trim()) return genre
  return 'Drama'
}

function filmCompletedDate(film: FilmEntry): string {
  const dateSource = film.status === 'complete' ? film.project.updated_at : film.project.created_at
  return new Date(dateSource).toLocaleDateString()
}

function deriveLogline(project: PersistedProjectState): string {
  const exec = project.execution_summary as Record<string, unknown>
  const logline = exec?.logline
  if (typeof logline === 'string' && logline.trim()) return logline
  return 'No logline set. Click to edit.'
}

function assetTypeBadge(sourceType: string, contentType?: string): { label: string; className: string } {
  const st = sourceType.toLowerCase()
  if (st.includes('audio') || contentType?.startsWith('audio')) return { label: 'AUDIO', className: 'bg-cyan-500/15 text-cyan-300 border-cyan-400/20' }
  if (st.includes('exr') || st.includes('image') || contentType?.startsWith('image')) return { label: 'EXR', className: 'bg-violet-500/15 text-violet-300 border-violet-400/20' }
  const ct = contentType?.toLowerCase() || ''
  if (ct.includes('raw') || st.includes('raw')) return { label: 'RAW', className: 'bg-amber-500/15 text-amber-300 border-amber-400/20' }
  return { label: 'FILE', className: 'bg-zinc-500/15 text-zinc-300 border-zinc-400/20' }
}

function assetTypeIcon(sourceType: string) {
  const st = sourceType.toLowerCase()
  if (st.includes('audio') || st.includes('music') || st.includes('sound')) return <Music size={18} />
  if (st.includes('exr') || st.includes('image') || st.includes('png') || st.includes('jpg')) return <FileType2 size={18} />
  return <FileVideo size={18} />
}

// ── Component ──────────────────────────────────────────────────────────────

export default function ArchiveRoom() {
  const navigate = useNavigate()

  // ── Core state ────────────────────────────────────────────────────────────
  const [films, setFilms] = useState<FilmEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // ── Filter/sort/search ────────────────────────────────────────────────────
  const [sortMode, setSortMode] = useState<SortMode>('recent')
  const [filterMode, setFilterMode] = useState<FilterMode>('all')
  const [searchQuery, setSearchQuery] = useState('')

  // ── Selected film ─────────────────────────────────────────────────────────
  const [selectedFilm, setSelectedFilm] = useState<FilmEntry | null>(null)
  // ── Actions ───────────────────────────────────────────────────────────────
  const [archiving, setArchiving] = useState<string | null>(null)
  const [exporting, setExporting] = useState<string | null>(null)
  const [showArchiveConfirm, setShowArchiveConfirm] = useState<FilmEntry | null>(null)
  const [scanning, setScanning] = useState(false)
  const [readinessIssues, setReadinessIssues] = useState<ReadinessIssue[]>([])
  const [publishing, setPublishing] = useState(false)

  // ── Asset Bin ─────────────────────────────────────────────────────────────
  const [assets, setAssets] = useState<AssetEntry[]>([])
  const [loadingAssets, setLoadingAssets] = useState(false)
  const [assetFilter, setAssetFilter] = useState<string>('all')
  const [showImportModal, setShowImportModal] = useState(false)

  // ── Load films ────────────────────────────────────────────────────────────
  const loadFilms = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { projects, error: listError } = await listProjects()
      if (listError) {
        setError(listError)
        setFilms([])
        return
      }

      // Load scenes for each project to derive status/runtime
      const filmEntries: FilmEntry[] = []
      for (const project of projects) {
        try {
          const { scenes } = await listScenes(project.project_id)
          filmEntries.push({
            project,
            status: deriveStatus(project, scenes),
            sceneCount: scenes.length,
            genre: deriveGenre(project),
            logline: deriveLogline(project),
          })
        } catch {
          filmEntries.push({
            project,
            status: 'draft',
            sceneCount: 0,
            genre: deriveGenre(project),
            logline: deriveLogline(project),
          })
        }
      }
      setFilms(filmEntries)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load films')
    } finally {
      setLoading(false)
    }
  }, [])

  // ── Load assets for selected film ─────────────────────────────────────────
  const loadAssets = useCallback(async () => {
    if (!selectedFilm) return
    setLoadingAssets(true)
    try {
      const { assets: loadedAssets } = await listVideoAssetsForProject(selectedFilm.project.project_id)
      const normalized = (Array.isArray(loadedAssets) ? loadedAssets : []).map((asset) => ({
        asset_id: asset.asset_id,
        source_type: asset.source_type,
        source_url: asset.source_url,
        status: asset.status,
        filename: asset.title,
        title: asset.title,
        content_type: typeof asset.metadata?.content_type === 'string' ? asset.metadata.content_type : undefined,
      }))
      setAssets(normalized)
    } catch {
      setAssets([])
    } finally {
      setLoadingAssets(false)
    }
  }, [selectedFilm])

  useEffect(() => {
    void loadFilms()
  }, [loadFilms])

  useEffect(() => {
    void loadAssets()
  }, [loadAssets])

  // ── Filtered + sorted films ───────────────────────────────────────────────
  const displayedFilms = useMemo(() => {
    let result = films

    // Filter
    if (filterMode !== 'all') {
      result = result.filter((f) => f.status === filterMode)
    }

    // Search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      result = result.filter(
        (f) =>
          f.project.title.toLowerCase().includes(q) ||
          f.genre.toLowerCase().includes(q) ||
          f.logline.toLowerCase().includes(q),
      )
    }

    // Sort
    const sorted = [...result]
    switch (sortMode) {
      case 'recent':
        sorted.sort((a, b) => new Date(b.project.updated_at).getTime() - new Date(a.project.updated_at).getTime())
        break
      case 'az':
        sorted.sort((a, b) => a.project.title.localeCompare(b.project.title))
        break
      case 'status': {
        const order: Record<FilmStatus, number> = { complete: 0, in_progress: 1, draft: 2 }
        sorted.sort((a, b) => order[a.status] - order[b.status])
        break
      }
    }

    return sorted
  }, [films, filterMode, searchQuery, sortMode])

  // ── Filtered assets ───────────────────────────────────────────────────────
  const filteredAssets = useMemo(() => {
    if (assetFilter === 'all') return assets
    return assets.filter((a) => a.content_type?.startsWith(assetFilter) || a.source_type === assetFilter)
  }, [assets, assetFilter])

  // ── Handlers ──────────────────────────────────────────────────────────────
  const handleScreen = useCallback(
    (film: FilmEntry) => {
      navigate(`/studio/screening-room?project_id=${film.project.project_id}`)
    },
    [navigate],
  )

  const handleExport = useCallback(async (film: FilmEntry) => {
    setExporting(film.project.project_id)
    setError('')
    try {
      const result = await fetchExportPackage(film.project.project_id, 'festival-export')
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${film.project.title}-export.json`
      a.click()
      URL.revokeObjectURL(url)
      setSuccess(`Downloaded export details (JSON) for "${film.project.title}"`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExporting(null)
    }
  }, [])

  const handleArchive = useCallback(async (film: FilmEntry) => {
    setArchiving(film.project.project_id)
    setError('')
    try {
      const { error: delError } = await deleteProject(film.project.project_id)
      if (delError) {
        setError(delError)
      } else {
        setSuccess(`"${film.project.title}" deleted`)
        setFilms((prev) => prev.filter((f) => f.project.project_id !== film.project.project_id))
        if (selectedFilm?.project.project_id === film.project.project_id) {
          setSelectedFilm(null)
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setArchiving(null)
      setShowArchiveConfirm(null)
    }
  }, [selectedFilm])

  const handleReadinessScan = useCallback(async () => {
    if (!selectedFilm) return
    setScanning(true)
    setReadinessIssues([])
    setError('')
    try {
      await getProjectDecisionGate(selectedFilm.project.project_id)
      const issues: ReadinessIssue[] = []

      if (selectedFilm.sceneCount === 0) {
        issues.push({ id: 'no-scenes', severity: 'error', message: 'No scenes in project' })
      }
      if (selectedFilm.project.approved_scenes.length === 0) {
        issues.push({ id: 'no-approvals', severity: 'warning', message: 'No scenes approved yet' })
      }
      if (selectedFilm.project.reviewed_scenes.length < selectedFilm.sceneCount) {
        issues.push({
          id: 'unreviewed',
          severity: 'info',
          message: `${selectedFilm.sceneCount - selectedFilm.project.reviewed_scenes.length} scenes not yet reviewed`,
        })
      }
      if (!selectedFilm.project.film_cut || Object.keys(selectedFilm.project.film_cut).length === 0) {
        issues.push({ id: 'no-cut', severity: 'warning', message: 'No final film cut assembled' })
      }

      setReadinessIssues(issues)
      if (issues.length === 0) {
        setSuccess('No issues found in these project checks. Review and approve the final output in Theatre.')
      } else {
        const errors = issues.filter((i) => i.severity === 'error').length
        const warnings = issues.filter((i) => i.severity === 'warning').length
        setSuccess(`Scan complete: ${errors} error${errors !== 1 ? 's' : ''}, ${warnings} warning${warnings !== 1 ? 's' : ''}`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scan failed')
    } finally {
      setScanning(false)
    }
  }, [selectedFilm])

  const handlePublish = useCallback(async () => {
    if (!selectedFilm) return
    setPublishing(true)
    setError('')
    try {
      await fetchExportPackage(selectedFilm.project.project_id, 'festival-export')
      setSuccess(`Export details are ready for "${selectedFilm.project.title}". Use Export JSON to download them.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not prepare export details')
    } finally {
      setPublishing(false)
    }
  }, [selectedFilm])

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <>
      <StudioShell title="Archive" subtitle="The Vault — Film Archive">
      <ProjectGuard>
        <ProjectContextBar roomName="archive" />

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

        {/* ── HEADER ROW ────────────────────────────────────────────────── */}
        <div className="px-4 pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h1
              className="text-2xl font-bold uppercase tracking-[0.2em] amber-glow"
              style={{ color: 'var(--color-primary)' }}
            >
              THE VAULT
            </h1>
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              {/* Sort dropdown */}
              <select
                value={sortMode}
                onChange={(e) => setSortMode(e.target.value as SortMode)}
                className="glass-panel rounded-lg px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] outline-none"
                style={{ color: 'var(--color-on-surface)' }}
              >
                {(Object.keys(SORT_LABELS) as SortMode[]).map((mode) => (
                  <option key={mode} value={mode} className="bg-zinc-900">
                    {SORT_LABELS[mode]}
                  </option>
                ))}
              </select>

              {/* Search */}
              <div className="flex items-center gap-1.5">
                <Search size={14} style={{ color: 'var(--color-on-surface-variant)' }} />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search films..."
                  className="cyber-input w-[160px] rounded px-3 py-1.5 text-xs outline-none"
                  style={{ color: 'var(--color-on-surface)' }}
                />
              </div>
            </div>
          </div>

          {/* Filter chips */}
          <div className="mt-3 flex gap-1.5">
            {(Object.keys(FILTER_LABELS) as FilterMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setFilterMode(mode)}
                className={`status-chip rounded border px-3 py-1 text-[10px] font-bold uppercase tracking-[0.1em] transition-all ${
                  filterMode === mode
                    ? 'border-primary/50 bg-primary/15 text-primary'
                    : 'hover:bg-white/8'
                }`}
                style={{
                  borderColor: filterMode === mode ? undefined : 'rgba(255,255,255,0.08)',
                  color: filterMode === mode ? undefined : 'var(--color-on-surface-variant)',
                }}
              >
                {FILTER_LABELS[mode]}
              </button>
            ))}
          </div>
        </div>

        {/* ── TWO-PANEL LAYOUT ──────────────────────────────────────────── */}
        <div className="flex w-full flex-col gap-4 px-4 pb-8 xl:flex-row">
          {/* ── LEFT: FILM LIST (horizontal rows) ──────────────────────── */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 size={32} className="animate-spin" style={{ color: 'var(--color-primary)' }} />
              </div>
            ) : displayedFilms.length === 0 ? (
              <div className="glass-panel flex flex-col items-center justify-center rounded-xl py-20 text-center">
                <Archive size={32} className="mb-3 opacity-30" style={{ color: 'var(--color-on-surface-variant)' }} />
                <p className="text-sm" style={{ color: 'var(--color-on-surface-variant)' }}>
                  {searchQuery || filterMode !== 'all'
                    ? 'No films match your filters.'
                    : 'The vault is empty. Create a project to get started.'}
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {displayedFilms.map((film) => (
                  <div
                    key={film.project.project_id}
                    className={`glass-panel group flex items-center gap-4 overflow-hidden rounded-xl px-4 py-3 transition-all duration-200 hover:scale-[1.005] ${
                      selectedFilm?.project.project_id === film.project.project_id ? 'ring-1 ring-amber-400/40' : ''
                    }`}
                    onClick={() => setSelectedFilm(film)}
                  >
                    {/* Thumbnail 180x100 */}
                    <div
                      className="glass-panel relative shrink-0 overflow-hidden rounded-lg"
                      style={{ width: 180, height: 100 }}
                    >
                      {film.thumbnailUrl ? (
                        <img
                          src={film.thumbnailUrl}
                          alt=""
                          className="h-full w-full object-cover"
                          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center">
                          <ImageIcon size={28} className="opacity-20" style={{ color: 'var(--color-on-surface-variant)' }} />
                        </div>
                      )}
                      <span
                        className={`status-chip absolute right-2 top-2 z-10 rounded border px-1.5 py-0.5 text-[8px] font-bold ${statusBadgeClass(film.status)}`}
                      >
                        {film.status === 'complete' ? 'Scenes approved' : film.status.replace('_', ' ').toUpperCase()}
                      </span>
                    </div>

                    {/* Right detail area */}
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <h3 className="headline-lg truncate text-on-surface">
                          {film.project.title}
                        </h3>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); handleScreen(film) }}
                            className="glass-panel flex items-center gap-1 rounded px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-[0.08em] transition-all hover:scale-[1.02]"
                            style={{ color: 'var(--color-primary)' }}
                          >
                            <Play size={12} />
                            SCREEN
                          </button>
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); void handleExport(film) }}
                            disabled={exporting === film.project.project_id}
                            className="glass-panel flex items-center gap-1 rounded px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-[0.08em] transition-all hover:scale-[1.02] disabled:opacity-50"
                            style={{ color: 'var(--color-on-surface-variant)' }}
                          >
                            {exporting === film.project.project_id ? (
                              <Loader2 size={12} className="animate-spin" />
                            ) : (
                              <Download size={12} />
                            )}
                            EXPORT JSON
                          </button>
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); setSelectedFilm(film) }}
                            className="glass-panel flex items-center gap-1 rounded px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-[0.08em] transition-all hover:scale-[1.02]"
                            style={{ color: 'var(--color-on-surface-variant)' }}
                          >
                            <Edit3 size={12} />
                            DETAILS
                          </button>
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); setShowArchiveConfirm(film) }}
                            disabled={archiving === film.project.project_id}
                            className="flex items-center gap-1 rounded px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-[0.08em] transition-all hover:scale-[1.02] disabled:opacity-50"
                            style={{ background: 'rgba(244,63,94,0.1)', color: 'var(--color-error)' }}
                          >
                            {archiving === film.project.project_id ? (
                              <Loader2 size={12} className="animate-spin" />
                            ) : (
                              <Trash2 size={12} />
                            )}
                            DELETE
                          </button>
                        </div>
                      </div>
                      {/* Metadata row */}
                      <div className="mt-1.5 flex flex-wrap items-center gap-3 font-metadata-sm" style={{ color: 'var(--color-on-surface-variant)' }}>
                        <span>{filmCompletedDate(film)}</span>
                        <span className="opacity-30">|</span>
                        <span>{film.sceneCount} SCENES</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── RIGHT: ASSET BIN PANEL (380px) ────────────────────────── */}
          <div className="flex min-w-0 w-full flex-col gap-3 xl:w-[360px] xl:shrink-0">
            {selectedFilm ? (
              <div className="glass-panel rounded-xl p-4 space-y-3">
                {/* Header */}
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span className="font-metadata-sm text-[11px] font-bold uppercase tracking-[0.15em]" style={{ color: 'var(--color-primary)' }}>
                      ASSET BIN
                    </span>
                    <button
                      type="button"
                      onClick={() => setAssetFilter(assetFilter === 'all' ? 'video' : 'all')}
                      className="rounded p-0.5 transition-all hover:bg-white/10"
                      aria-label="Filter assets"
                    >
                      <Filter size={12} style={{ color: 'var(--color-on-surface-variant)' }} />
                    </button>
                  </div>
                </div>

                {/* Asset filter chips */}
                <div className="flex gap-1.5">
                  {['all', 'video', 'image', 'audio'].map((filter) => (
                    <button
                      key={filter}
                      type="button"
                      onClick={() => setAssetFilter(filter)}
                      className={`status-chip rounded border px-2 py-1 text-[8px] font-bold uppercase tracking-[0.08em] transition-all ${
                        assetFilter === filter ? 'border-primary/40 bg-primary/10 text-primary' : ''
                      }`}
                      style={{
                        borderColor: assetFilter === filter ? undefined : 'rgba(255,255,255,0.06)',
                        color: assetFilter === filter ? undefined : 'var(--color-on-surface-variant)',
                      }}
                    >
                      {filter.toUpperCase()}
                    </button>
                  ))}
                </div>

                {/* Asset grid 2-col */}
                {loadingAssets ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 size={20} className="animate-spin" style={{ color: 'var(--color-primary)' }} />
                  </div>
                ) : filteredAssets.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <ImageIcon size={24} className="mb-2 opacity-20" style={{ color: 'var(--color-on-surface-variant)' }} />
                    <p className="text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                      No assets imported yet.
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    {filteredAssets.map((asset) => {
                      const badge = assetTypeBadge(asset.source_type, asset.content_type)
                      const thumbSrc = asset.source_url || ''
                      return (
                        <div
                          key={asset.asset_id}
                          className="glass-panel flex flex-col items-center rounded-lg p-2 transition-all hover:scale-[1.02]"
                          style={{ background: 'rgba(14,14,14,0.5)' }}
                        >
                          {/* Preview area */}
                          <div
                            className="flex h-[80px] w-full items-center justify-center rounded-md"
                            style={{ background: 'var(--color-surface-container-lowest)' }}
                          >
                            {thumbSrc ? (
                              <img
                                src={thumbSrc}
                                alt=""
                                className="h-full w-full rounded-md object-cover opacity-70"
                                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                              />
                            ) : (
                              <span style={{ color: 'var(--color-on-surface-variant)', opacity: 0.3 }}>
                                {assetTypeIcon(asset.source_type)}
                              </span>
                            )}
                          </div>
                          {/* Filename */}
                          <p
                            className="mt-1.5 w-full truncate text-[9px] font-mono"
                            style={{ color: 'var(--color-on-surface)' }}
                          >
                            {asset.filename || asset.title || asset.asset_id}
                          </p>
                          {/* Badge */}
                          <span
                            className={`status-chip mt-0.5 rounded px-1.5 py-0.5 text-[7px] font-bold ${badge.className}`}
                          >
                            {badge.label}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* Bottom import button */}
                <button
                  type="button"
                  onClick={() => setShowImportModal(true)}
                  className="glass-panel flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01]"
                  style={{ color: 'var(--color-on-surface-variant)', background: 'rgba(20,20,20,0.5)' }}
                >
                  <Plus size={12} />
                  IMPORT ASSET
                </button>

                {/* Readiness scan + Publish actions */}
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void handleReadinessScan()}
                    disabled={scanning}
                    className="glass-panel flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01] disabled:opacity-50"
                    style={{ color: 'var(--color-primary)' }}
                  >
                    {scanning ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
                    SCAN
                  </button>
                  <button
                    type="button"
                    onClick={() => void handlePublish()}
                    disabled={publishing}
                    className="glass-panel flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01] disabled:opacity-50"
                    style={{ color: 'var(--color-on-surface-variant)' }}
                  >
                    {publishing ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
                    PREPARE EXPORT DETAILS
                  </button>
                </div>

                {/* Readiness issues */}
                {readinessIssues.length > 0 && (
                  <div className="space-y-1">
                    {readinessIssues.map((issue) => (
                      <div
                        key={issue.id}
                        className={`rounded px-2 py-1 text-[10px] ${
                          issue.severity === 'error'
                            ? 'bg-rose-500/10 text-rose-300'
                            : issue.severity === 'warning'
                              ? 'bg-amber-500/10 text-amber-300'
                              : 'bg-sky-500/10 text-sky-300'
                        }`}
                      >
                        {issue.message}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="glass-panel flex flex-col items-center justify-center rounded-xl py-16 text-center">
                <Archive size={28} className="mb-3 opacity-20" style={{ color: 'var(--color-on-surface-variant)' }} />
                <p className="text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  Select a film to view its asset bin.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* ── ARCHIVE CONFIRM MODAL ────────────────────────────────────── */}
        {showArchiveConfirm && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
            onClick={() => setShowArchiveConfirm(null)}
          >
            <div className="glass-panel w-[360px] max-w-[calc(100vw-32px)] rounded-xl p-6" onClick={(e) => e.stopPropagation()}>
              <div className="mb-2 flex items-center gap-2">
                <AlertCircle size={20} style={{ color: 'var(--color-error)' }} />
                <h3 className="text-lg font-bold" style={{ color: 'var(--color-on-surface)' }}>
                  Delete film
                </h3>
              </div>
              <p className="mb-4 text-sm" style={{ color: 'var(--color-on-surface-variant)' }}>
                Delete "{showArchiveConfirm.project.title}" permanently? This deletes the project rather than moving it into an archive. This cannot be undone.
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setShowArchiveConfirm(null)}
                  className="glass-panel flex-1 rounded-lg px-4 py-2 text-[11px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01]"
                  style={{ color: 'var(--color-on-surface-variant)' }}
                >
                  CANCEL
                </button>
                <button
                  type="button"
                  onClick={() => void handleArchive(showArchiveConfirm)}
                  disabled={archiving === showArchiveConfirm.project.project_id}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-lg px-4 py-2 text-[11px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01] disabled:opacity-50"
                  style={{
                    background: 'rgba(244,63,94,0.15)',
                    color: 'var(--color-error)',
                    border: '1px solid rgba(244,63,94,0.3)',
                  }}
                >
                  {archiving === showArchiveConfirm.project.project_id ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Trash2 size={14} />
                  )}
                  DELETE FILM
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── IMPORT ASSET MODAL (stub) ─────────────────────────────────── */}
        {showImportModal && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
            onClick={() => setShowImportModal(false)}
          >
            <div className="glass-panel w-[380px] rounded-xl p-6" onClick={(e) => e.stopPropagation()}>
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-bold uppercase tracking-[0.12em]" style={{ color: 'var(--color-on-surface)' }}>
                  IMPORT ASSET
                </h3>
                <button
                  type="button"
                  onClick={() => setShowImportModal(false)}
                  className="rounded p-1 transition-all hover:bg-white/10"
                  style={{ color: 'var(--color-on-surface-variant)' }}
                >
                  <X size={14} />
                </button>
              </div>
              <p className="text-[11px] leading-relaxed" style={{ color: 'var(--color-on-surface-variant)' }}>
                Asset import uses the existing <code className="font-mono text-[10px] text-cyan-300">uploadVideoAsset</code> flow in other rooms. This panel is ready for wire-up.
              </p>
              <div className="mt-4 flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowImportModal(false)}
                  className="glass-panel flex-1 rounded-lg px-4 py-2 text-[11px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01]"
                  style={{ color: 'var(--color-on-surface-variant)' }}
                >
                  CLOSE
                </button>
              </div>
            </div>
          </div>
        )}
      </ProjectGuard>
    </StudioShell>
    </>
  )
}
