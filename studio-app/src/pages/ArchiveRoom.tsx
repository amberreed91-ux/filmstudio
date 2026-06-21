import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom'
import { Archive } from 'lucide-react'
import StudioShell, { TabGroup } from '../components/StudioShell'
import { useStudio } from '../context/StudioContext'
import { buildLocalFallbackExport, downloadJson, fetchExportPackage, getProject, type ExportPackageType } from '../lib/studioApi'
import { persistActiveProjectId, readPersistedActiveProjectId, resolveActiveProjectId, withProjectQuery } from '../lib/projectContext'

type AnyRecord = Record<string, unknown>

type ArchiveSnapshot = {
  snapshot_id: string
  timestamp: string
  scene_count: number
  completion_percent: number
  dominant_tone: string
  best_cut: 'original' | 'iteration'
  notes: string
}

function asRecord(value: unknown): AnyRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as AnyRecord
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function getExecutionSummary(state: unknown, projectSummary: unknown): AnyRecord {
  let localBundle: AnyRecord | null = null
  try {
    const raw = localStorage.getItem('studio:lastBundle')
    if (raw) localBundle = asRecord(JSON.parse(raw))
  } catch {
    localBundle = null
  }
  const locationState = asRecord(state)
  const candidates: unknown[] = [
    asRecord(locationState?.execution_summary),
    asRecord(locationState?.executionSummary),
    asRecord(locationState?.bundle),
    asRecord(asRecord(locationState?.project)?.execution_summary),
    asRecord(projectSummary),
    localBundle,
  ]
  for (const candidate of candidates) {
    const record = asRecord(candidate)
    if (record && Object.keys(record).length > 0) return record
  }
  return {}
}

export default function ArchiveRoom() {
  const { projectId } = useParams()
  const [searchParams] = useSearchParams()
  const sessionId = searchParams.get('session_id')
  const queryProjectId = searchParams.get('project_id') || ''
  const location = useLocation()
  const { project, loadProject } = useStudio()
  const loadRequestKeyRef = useRef<string | null>(null)
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>('')
  const [archiveTab, setArchiveTab] = useState<'snapshots' | 'versions' | 'best_cuts' | 'memory'>('snapshots')
  const [exportMessage, setExportMessage] = useState('')
  const [persistedSummary, setPersistedSummary] = useState<AnyRecord | null>(null)
  const activeProjectId = resolveActiveProjectId({
    queryProjectId,
    routeProjectId: projectId || '',
    locationState: location.state,
    persistedProjectId: readPersistedActiveProjectId(),
    contextProjectId: project?.project_id || '',
  })
  useEffect(() => {
    if (activeProjectId) persistActiveProjectId(activeProjectId)
  }, [activeProjectId])
  const exportCards: Array<{ type: ExportPackageType; title: string; description: string }> = [
    { type: 'pitch-pack', title: 'Pitch Pack', description: 'Story, structure, direction, and ending payload.' },
    { type: 'shot-list', title: 'Shot List', description: 'Scene/shot intent with render references.' },
    { type: 'prompt-pack', title: 'Prompt Pack', description: 'Visual briefs, prompt packs, and memory influence.' },
    { type: 'cut-manifest', title: 'Cut Manifest', description: 'Cut order, inclusion list, runtime and transitions.' },
    { type: 'festival-export', title: 'Festival Export', description: 'Submission-ready package with delivery metadata and presets.' },
    { type: 'youtube-export', title: 'YouTube Export', description: 'Channel-ready delivery with runtime, poster, and subtitle metadata.' },
    { type: 'trailer-export', title: 'Trailer Export', description: '90-second promotional export preset with source-cut references.' },
    { type: 'teaser-export', title: 'Teaser Export', description: '30-second teaser preset for social promotion workflows.' },
    { type: 'subtitle-packages', title: 'Subtitle Packages', description: 'SRT/VTT subtitle bundle for distribution channels.' },
    { type: 'archive-snapshot', title: 'Archive Snapshot', description: 'Snapshots, versions, best cut, production summary.' },
  ]

  async function handleExportPackage(type: ExportPackageType) {
    const safeProjectId = activeProjectId || 'local_project'
    try {
      const payload = await fetchExportPackage(safeProjectId, type)
      downloadJson(`${safeProjectId}-${type}.json`, payload)
      setExportMessage('Export created')
    } catch {
      const fallback = buildLocalFallbackExport(type)
      downloadJson(`${safeProjectId}-${type}-fallback.json`, fallback)
      setExportMessage('Export created (local fallback)')
    }
  }

  useEffect(() => {
    if (!projectId) return
    const loadRequestKey = `${projectId}:${sessionId ?? ''}`
    if (loadRequestKeyRef.current === loadRequestKey) return
    loadRequestKeyRef.current = loadRequestKey
    void loadProject(projectId, { sessionId })
  }, [loadProject, projectId, sessionId])

  useEffect(() => {
    if (!activeProjectId || projectId) return
    void (async () => {
      const response = await getProject(activeProjectId)
      const summary = asRecord(response.project?.execution_summary)
      if (summary) setPersistedSummary(summary)
    })()
  }, [activeProjectId, projectId])

  const executionSummary = useMemo(
    () => getExecutionSummary(location.state, project?.execution_summary || persistedSummary),
    [location.state, project?.execution_summary, persistedSummary],
  )

  const archiveSnapshots = useMemo<ArchiveSnapshot[]>(() => {
    const raw = asArray(executionSummary.archive_snapshots)
    const parsed = raw.map((entry, index) => {
      const item = asRecord(entry) || {}
      const bestCut: ArchiveSnapshot['best_cut'] =
        asString(item.best_cut).trim().toLowerCase() === 'iteration' ? 'iteration' : 'original'
      return {
        snapshot_id: asString(item.snapshot_id).trim() || `snap_${String(index + 1).padStart(3, '0')}`,
        timestamp: asString(item.timestamp).trim() || `2026-01-0${index + 1}T00:00:00Z`,
        scene_count: asNumber(item.scene_count) ?? 0,
        completion_percent: asNumber(item.completion_percent) ?? 0,
        dominant_tone: asString(item.dominant_tone).trim() || 'none',
        best_cut: bestCut,
        notes: asString(item.notes).trim() || 'No notes',
      }
    })
    if (parsed.length > 0) return parsed
    return [
      {
        snapshot_id: 'snap_001',
        timestamp: '2026-01-01T00:00:00Z',
        scene_count: 0,
        completion_percent: 0,
        dominant_tone: 'none',
        best_cut: 'original',
        notes: 'No archive snapshots available yet.',
      },
    ]
  }, [executionSummary.archive_snapshots])
  const hasRealArchiveSnapshots = asArray(executionSummary.archive_snapshots).length > 0

  useEffect(() => {
    if (!selectedSnapshotId && archiveSnapshots.length > 0) {
      setSelectedSnapshotId(archiveSnapshots[archiveSnapshots.length - 1].snapshot_id)
    }
  }, [archiveSnapshots, selectedSnapshotId])

  const selectedSnapshot = useMemo(
    () => archiveSnapshots.find((snap) => snap.snapshot_id === selectedSnapshotId) || archiveSnapshots[0],
    [archiveSnapshots, selectedSnapshotId],
  )

  const sceneVersions = useMemo(() => {
    const scenes = asArray(executionSummary.scenes)
    return scenes
      .map((scene) => {
        const row = asRecord(scene) || {}
        return {
          scene_id: asString(row.scene_id).trim() || 'scene_unknown',
          versions: asArray(row.scene_versions)
            .map((version, index) => {
              const item = asRecord(version) || {}
              return {
                version_id: asString(item.version_id).trim() || `version_${index + 1}`,
                type: asString(item.type).trim() || 'original',
                timestamp: asString(item.timestamp).trim() || '',
                quality_score: asNumber(item.quality_score) ?? 0,
              }
            })
            .filter((version) => Boolean(version.version_id)),
        }
      })
      .filter((scene) => scene.versions.length > 0)
  }, [executionSummary.scenes])

  const archiveSummary = useMemo(() => {
    const summary = asRecord(executionSummary.archive_summary) || {}
    return {
      total_snapshots: asNumber(summary.total_snapshots) ?? archiveSnapshots.length,
      latest_completion: asNumber(summary.latest_completion) ?? selectedSnapshot?.completion_percent ?? 0,
      best_quality_scene: asString(summary.best_quality_scene).trim() || 'none',
    }
  }, [executionSummary.archive_summary, archiveSnapshots.length, selectedSnapshot])

  const bestCutSummary = useMemo(() => {
    const summary = asRecord(executionSummary.best_cut_summary) || {}
    return {
      selected_cut: asString(summary.selected_cut).trim() || 'original',
      reason: asString(summary.reason).trim() || 'No reason available',
      confidence: asNumber(summary.confidence) ?? 0,
    }
  }, [executionSummary.best_cut_summary])

  return (
    <StudioShell title="Archive Room" subtitle="Memory vault for film snapshots, scene versions, and best-cut lineage.">
      <div className="w-full overflow-visible" style={{ background: 'var(--color-surface-0)' }}>
        <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-8 space-y-8">
          {/* Room Hero - "The Vault" */}
          <section className="rounded-2xl border p-8" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border)' }}>
            <div className="text-[11px] uppercase tracking-[0.2em]" style={{ color: 'var(--color-accent)' }}>Archive Room</div>
            <h1 className="mt-3 text-4xl font-light tracking-tight" style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}>
              The Vault
            </h1>
            <p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              Every version, every snapshot, every decision preserved.
            </p>
          </section>

          <section className="rounded-2xl border p-5" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="flex items-center gap-2 text-xl font-semibold tracking-wide" style={{ color: 'var(--color-text-primary)' }}><Archive size={18} />Archive Snapshots</h2>
              <button
                type="button"
                onClick={() => { void handleExportPackage('archive-snapshot') }}
                className="rounded-lg border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] transition hover:border-[#00d4aa]"
                style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border)', color: 'var(--color-accent)' }}
              >
                Export Snapshot
              </button>
            </div>
            {!hasRealArchiveSnapshots ? (
              <div className="mt-3 rounded-lg border border-dashed px-3 py-3 text-xs" style={{ borderColor: 'var(--color-border-subtle)', color: 'var(--color-text-secondary)' }}>
                <div>No saved versions yet.</div>
                <Link
                  to={withProjectQuery('/studio/writers-room', activeProjectId)}
                  className="mt-2 inline-flex rounded-lg border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] no-underline transition hover:border-[#00d4aa]"
                  style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border)', color: 'var(--color-accent)' }}
                >
                  Generate a film
                </Link>
              </div>
            ) : null}
            {exportMessage ? <div className="mt-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{exportMessage}</div> : null}
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-6 xl:grid-cols-12">
              {archiveSnapshots.map((snapshot) => {
                const isActive = snapshot.snapshot_id === selectedSnapshot?.snapshot_id
                const statusLabel = snapshot.completion_percent >= 100 ? 'Complete' : 'In Progress'
                return (
                  <button
                    key={snapshot.snapshot_id}
                    type="button"
                    onClick={() => setSelectedSnapshotId(snapshot.snapshot_id)}
                    className={`min-w-0 break-words rounded-xl border p-3 text-left transition-all md:col-span-2 xl:col-span-4 ${
                      isActive
                        ? 'border-cyan-300/60 bg-cyan-500/15 shadow-[0_0_24px_rgba(34,211,238,0.25)]'
                        : 'border-zinc-700/70 bg-zinc-900/60 hover:border-zinc-500/80'
                    }`}
                  >
                    <div className="text-xs uppercase tracking-[0.14em] text-zinc-300">{snapshot.snapshot_id}</div>
                    <div className="mt-1 text-xs text-zinc-400">{snapshot.timestamp}</div>
                    <div className="mt-1 text-xs text-zinc-200">Status: {statusLabel}</div>
                    {snapshot.dominant_tone && snapshot.dominant_tone !== 'none' && (
                      <div className="mt-1 text-xs text-zinc-200">Tone: {snapshot.dominant_tone}</div>
                    )}
                    <div className="mt-1 text-xs text-zinc-200">Best Cut: {snapshot.best_cut}</div>
                  </button>
                )
              })}
            </div>
          </section>

          <section className="rounded-2xl border border-zinc-800/70 bg-zinc-900/45 p-5 shadow-2xl backdrop-blur-md">
            <TabGroup
              className="mb-3"
              value={archiveTab}
              onChange={(next) => setArchiveTab(next)}
              options={[
                { id: 'snapshots', label: 'Snapshots' },
                { id: 'versions', label: 'Scene Versions' },
                { id: 'best_cuts', label: 'Best Cuts' },
                { id: 'memory', label: 'Memory' },
              ]}
            />
            <h3 className="text-sm uppercase tracking-[0.14em] text-zinc-300">Export Center</h3>
            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {exportCards.map((card) => (
                <article key={card.type} className="rounded-xl border border-zinc-700/70 bg-zinc-900/60 p-3">
                  <div className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-100">{card.title}</div>
                  <div className="mt-1 text-[11px] text-zinc-400">{card.description}</div>
                  <div className="mt-2 text-[10px] uppercase tracking-[0.12em] text-emerald-300">status: ready</div>
                  <button
                    type="button"
                    onClick={() => { void handleExportPackage(card.type) }}
                    className="mt-2 rounded-md border border-cyan-300/40 bg-cyan-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-cyan-100"
                  >
                    Export JSON
                  </button>
                </article>
              ))}
            </div>
          </section>

          <section className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            <article className="lg:col-span-8 rounded-2xl border border-zinc-800/70 bg-zinc-900/40 p-5 shadow-xl backdrop-blur-md">
              {archiveTab === 'versions' ? (
                <>
                  <h3 className="text-sm uppercase tracking-[0.14em] text-zinc-300">Scene Version Panel</h3>
                  <div className="mt-3 space-y-3 max-h-[calc(100vh-220px)] overflow-y-auto pr-1">
                    {sceneVersions.length > 0 ? sceneVersions.map((scene) => (
                      <div key={scene.scene_id} className="rounded-xl border border-zinc-700/70 bg-zinc-900/60 p-3">
                        <div className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-200">{scene.scene_id}</div>
                        <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                          {scene.versions.map((version) => (
                            <div key={version.version_id} className="rounded-lg border border-zinc-700/60 bg-zinc-950/50 p-2">
                              <div className="text-[11px] text-zinc-300">{version.version_id}</div>
                              <div className="text-[11px] text-zinc-400">Type: {version.type}</div>
                              <div className="text-[11px] text-zinc-400">{version.timestamp}</div>
                              <div className="text-[11px] text-cyan-200">Quality: {version.quality_score.toFixed(3)}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )) : (
                      <div className="rounded-xl border border-dashed border-zinc-700 p-4 text-xs text-zinc-400">No scene version history found.</div>
                    )}
                  </div>
                </>
              ) : archiveTab === 'best_cuts' ? (
                <div className="rounded-xl border border-zinc-700/70 bg-zinc-900/60 p-4 text-xs text-zinc-200">
                  Best cut summary is shown in the right panel. Use snapshot cards to compare iterations.
                </div>
              ) : archiveTab === 'memory' ? (
                <div className="rounded-xl border border-zinc-700/70 bg-zinc-900/60 p-4 text-xs text-zinc-200">
                  Archive memory links snapshots, scene versions, and best-cut decisions for reuse.
                </div>
              ) : (
                <div className="rounded-xl border border-zinc-700/70 bg-zinc-900/60 p-4 text-xs text-zinc-200">
                  Select a snapshot above to inspect the active archive state.
                </div>
              )}
            </article>

            <aside className="lg:col-span-4 space-y-4">
              <section className="rounded-2xl border border-zinc-800/70 bg-zinc-900/40 p-4 shadow-xl backdrop-blur-md">
                <h3 className="text-sm uppercase tracking-[0.14em] text-zinc-300">Archive Summary</h3>
                <div className="mt-2 space-y-1 text-xs text-zinc-200">
                  <div>Total Snapshots: <span className="text-zinc-100">{archiveSummary.total_snapshots}</span></div>
                  <div>Latest Completion: <span className="text-zinc-100">{archiveSummary.latest_completion.toFixed(2)}%</span></div>
                  <div>Best Quality Scene: <span className="text-zinc-100">{archiveSummary.best_quality_scene}</span></div>
                </div>
              </section>

              <section className="rounded-2xl border border-zinc-800/70 bg-zinc-900/40 p-4 shadow-xl backdrop-blur-md">
                <h3 className="text-sm uppercase tracking-[0.14em] text-zinc-300">Best Cut</h3>
                <div className="mt-2 space-y-1 text-xs text-zinc-200">
                  <div>Selected: <span className="text-zinc-100">{bestCutSummary.selected_cut}</span></div>
                  <div>Reason: <span className="text-zinc-100">{bestCutSummary.reason}</span></div>
                  <div>Confidence: <span className="text-cyan-200">{bestCutSummary.confidence.toFixed(3)}</span></div>
                </div>
              </section>

              <section className="rounded-2xl border border-zinc-800/70 bg-zinc-900/40 p-4 shadow-xl backdrop-blur-md">
                <h3 className="text-sm uppercase tracking-[0.14em] text-zinc-300">Selected Snapshot Notes</h3>
                <div className="mt-2 text-xs text-zinc-200">{selectedSnapshot?.notes || 'No notes'}</div>
              </section>
            </aside>
          </section>
        </div>
      </div>
    </StudioShell>
  )
}
