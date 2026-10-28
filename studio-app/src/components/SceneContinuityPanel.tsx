import { useEffect, useMemo, useState } from 'react'

type ScenePair = [string, string]

type Scene = {
  scene_id: string
  [key: string]: unknown
}

type CausalImpossibility = {
  description: string
  conflicting_event: string
  established_at: string
  severity: 'low' | 'medium' | 'high'
}

type CausalCheck = {
  impossibilities: CausalImpossibility[]
  advisory: string
  uncertainty_notes: string[]
}

type TransitionRead = {
  from_scene_id: string
  to_scene_id: string
  entering_emotion: string
  exiting_emotion: string
  unresolved_tension: string
  continuity_warnings: string[]
  advisory_note: string
  causal_check?: CausalCheck | null
}

type MotifThread = {
  motif: string
  introduced_at: string
  reinforced_at: string[]
  last_seen_at: string
  status: 'active' | 'resolved' | 'abandoned'
  thread_read: string
  uncertainty_note: string | null
  scene_appearances: string[]
}

type MotifAnalysis = {
  motifs: MotifThread[]
  unresolved_motifs: string[]
  dominant_motif: string | null
  advisory: string
  echoes_edges: Array<{ from_scene_id: string; to_scene_id: string; motif: string; edge_type: string }>
}

type SceneContinuityResponse = {
  project_id: string
  mode: string
  strictness: string
  transition_reads: TransitionRead[]
  overall_status: string
  advisory_notes: string[]
  advisory_only: boolean
  auto_regeneration_triggered: boolean
}

type RevisionProposal = {
  from_scene_id: string
  to_scene_id: string
  advisory_note: string
  continuity_warnings: string[]
}

type SceneContinuityPanelProps = {
  filmId: string
  scenes: Scene[]
  scenePairs: ScenePair[]
  onRevisionProposalAccepted: (proposal: RevisionProposal) => void
}

function statusTone(status: string): string {
  if (status === 'clean') return 'text-emerald-300'
  if (status === 'minor_concerns') return 'text-amber-300'
  if (status === 'review_recommended') return 'text-rose-300'
  return 'text-zinc-400'
}

function warningTone(count: number): string {
  if (count === 0) return 'border-emerald-400/30 bg-emerald-500/8'
  if (count <= 2) return 'border-amber-400/30 bg-amber-500/8'
  return 'border-rose-400/30 bg-rose-500/8'
}

function causalSeverityStyle(severity: CausalImpossibility['severity']): string {
  if (severity === 'high') return 'text-rose-200 border-rose-400/40 bg-rose-500/10'
  if (severity === 'medium') return 'text-amber-200 border-amber-400/40 bg-amber-500/10'
  return 'text-zinc-300 border-zinc-600/40 bg-zinc-700/20'
}

function causalSeverityLabel(severity: CausalImpossibility['severity']): string {
  if (severity === 'high') return 'potential conflict'
  if (severity === 'medium') return 'worth reviewing'
  return 'weak signal'
}

function CausalFlagsSection({ causalCheck }: { causalCheck: CausalCheck }) {
  const [open, setOpen] = useState(false)
  const { impossibilities, uncertainty_notes } = causalCheck

  if (impossibilities.length === 0) return null

  const highCount = impossibilities.filter((i) => i.severity === 'high').length

  const badgeStyle = highCount > 0
    ? 'border-rose-400/50 bg-rose-500/12 text-rose-200'
    : 'border-amber-400/50 bg-amber-500/12 text-amber-200'

  return (
    <div
      className="mt-2 rounded border border-zinc-700/60 bg-zinc-900/40"
      data-testid="causal-flags-section"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-300">
            Causal Flags
          </span>
          <span className={`rounded-full border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] ${badgeStyle}`}>
            {impossibilities.length} flag{impossibilities.length !== 1 ? 's' : ''}
          </span>
        </div>
        <span className="text-[10px] text-zinc-500">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="space-y-2 px-2.5 pb-2.5">
          {impossibilities.map((imp, i) => (
            <div
              key={i}
              className={`rounded border px-2 py-1.5 text-[10px] ${causalSeverityStyle(imp.severity)}`}
              data-testid={`causal-flag-${imp.severity}`}
            >
              <div className="flex items-center gap-1.5">
                <span className="rounded border border-current/30 px-1 py-0.5 text-[10px] uppercase tracking-[0.1em] opacity-70">
                  {causalSeverityLabel(imp.severity)}
                </span>
                <span className="text-zinc-400 text-[10px]">
                  established at {imp.established_at || '—'}
                </span>
              </div>
              <div className="mt-1">{imp.description}</div>
              <div className="mt-0.5 text-[10px] opacity-60">
                Causal event: {imp.conflicting_event}
              </div>
            </div>
          ))}

          {uncertainty_notes.length > 0 && (
            <div className="space-y-0.5 pt-1">
              {uncertainty_notes.map((note, i) => (
                <div key={i} className="text-xs text-zinc-500">· {note}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function motifStatusStyle(status: MotifThread['status']): string {
  if (status === 'active') return 'border-emerald-400/50 bg-emerald-500/12 text-emerald-200'
  if (status === 'resolved') return 'border-cyan-400/50 bg-cyan-500/12 text-cyan-200'
  return 'border-amber-400/50 bg-amber-500/12 text-amber-200'
}

function motifDotStyle(status: MotifThread['status']): string {
  if (status === 'active') return 'bg-emerald-400'
  if (status === 'resolved') return 'bg-cyan-400'
  return 'bg-amber-400'
}

function MotifRow({ motif, allSceneIds }: { motif: MotifThread; allSceneIds: string[] }) {
  const [open, setOpen] = useState(false)
  const appearances = new Set(motif.scene_appearances)

  return (
    <div
      className="rounded border border-zinc-700/50 bg-zinc-900/30 px-2.5 py-2"
      data-testid="motif-row"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 text-left"
        aria-expanded={open}
      >
        {/* Motif name */}
        <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-zinc-200">
          {motif.motif}
        </span>

        {/* Timeline dots */}
        <div className="flex items-center gap-0.5" aria-label={`${motif.motif} appearances`}>
          {allSceneIds.map((sid) => (
            <span
              key={sid}
              className={`h-2 w-2 rounded-full transition-opacity ${
                appearances.has(sid)
                  ? motifDotStyle(motif.status)
                  : 'bg-zinc-700'
              }`}
              title={sid}
            />
          ))}
        </div>

        {/* Status badge */}
        <span
          className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] ${motifStatusStyle(motif.status)}`}
          data-testid={`motif-status-${motif.status}`}
        >
          {motif.status}
        </span>

        <span className="text-[10px] text-zinc-500">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="mt-2 space-y-1.5 pl-0.5">
          <div className="text-xs text-zinc-300">{motif.thread_read}</div>
          {motif.uncertainty_note && (
            <div className="text-xs text-zinc-500">· {motif.uncertainty_note}</div>
          )}
        </div>
      )}
    </div>
  )
}

function MotifsSection({ filmId }: { filmId: string }) {
  const [analysis, setAnalysis] = useState<MotifAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [fetchError, setFetchError] = useState('')

  useEffect(() => {
    if (!filmId) return
    let cancelled = false
    const controller = new AbortController()

    async function load() {
      setLoading(true)
      setFetchError('')
      try {
        const base = (
          import.meta.env.VITE_API_BASE_URL ||
          import.meta.env.VITE_STUDIO_API_BASE ||
          'http://127.0.0.1:8010'
        ).replace(/\/+$/, '').replace(/^(https?:\/\/(localhost|127\.0\.0\.1)):8012$/, 'http://127.0.0.1:8010')

        const res = await fetch(
          `${base}/api/f51/studio/projects/${encodeURIComponent(filmId)}/motif-threads`,
          { headers: { Accept: 'application/json' }, signal: controller.signal },
        )
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = (await res.json()) as MotifAnalysis
        if (!cancelled) setAnalysis(data)
      } catch (err) {
        if (!cancelled) {
          if (err instanceof Error && err.name === 'AbortError') return
          setFetchError('Motif analysis unavailable.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => { cancelled = true; controller.abort() }
  }, [filmId])

  // Collect all scene IDs in order from motif appearances for the timeline.
  const allSceneIds = useMemo(() => {
    if (!analysis) return []
    const seen = new Set<string>()
    const ids: string[] = []
    for (const m of analysis.motifs) {
      for (const sid of m.scene_appearances) {
        if (!seen.has(sid)) { seen.add(sid); ids.push(sid) }
      }
    }
    return ids
  }, [analysis])

  return (
    <div className="space-y-2" data-testid="motifs-section">
      <div className="flex items-center gap-2">
        <span className="text-[11px] uppercase tracking-[0.14em] text-zinc-300">Motifs</span>
        {analysis?.dominant_motif && (
          <span className="text-[10px] text-zinc-500">
            · dominant: <span className="text-zinc-300">{analysis.dominant_motif}</span>
          </span>
        )}
      </div>

      {loading ? (
        <div className="text-xs text-zinc-500">Analysing motifs…</div>
      ) : fetchError ? (
        <div className="text-xs text-zinc-500">{fetchError}</div>
      ) : !analysis || analysis.motifs.length === 0 ? (
        <div
          className="text-[11px] text-zinc-500"
          data-testid="motifs-empty-state"
        >
          Add visual tags to scenes to begin motif tracking.
        </div>
      ) : (
        <>
          {/* Advisory */}
          <div className="text-xs text-zinc-400">{analysis.advisory}</div>

          {/* Unresolved motifs highlight */}
          {analysis.unresolved_motifs.length > 0 && (
            <div
              className="rounded border border-amber-400/30 bg-amber-500/8 px-2.5 py-1.5 text-[10px] text-amber-200"
              data-testid="unresolved-motifs"
            >
              Potentially unresolved: {analysis.unresolved_motifs.join(', ')}
            </div>
          )}

          {/* Motif rows */}
          <div className="space-y-1.5">
            {analysis.motifs.map((m) => (
              <MotifRow key={m.motif} motif={m} allSceneIds={allSceneIds} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default function SceneContinuityPanel({
  filmId,
  scenes,
  scenePairs,
  onRevisionProposalAccepted,
}: SceneContinuityPanelProps) {
  const [result, setResult] = useState<SceneContinuityResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [strictness, setStrictness] = useState<'low' | 'medium' | 'high'>('medium')
  const [mode, setMode] = useState<'passive' | 'active'>('passive')

  // Derive scene dicts keyed by id for the request body
  const scenePayload = useMemo(
    () => scenes.map((s) => ({ ...s })),
    [scenes],
  )

  const pairsPayload = useMemo(
    () => scenePairs.map(([from, to]) => ({ from_scene_id: from, to_scene_id: to })),
    [scenePairs],
  )

  useEffect(() => {
    if (!filmId || scenePairs.length === 0) return
    let cancelled = false
    const controller = new AbortController()

    async function load() {
      setLoading(true)
      setError('')
      try {
        const base =
          (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_STUDIO_API_BASE || 'http://127.0.0.1:8010')
            .replace(/\/+$/, '')
            .replace(/^(https?:\/\/(localhost|127\.0\.0\.1)):8012$/, 'http://127.0.0.1:8010')

        const res = await fetch(
          `${base}/api/f51/studio/projects/${encodeURIComponent(filmId)}/scene-continuity-intelligence`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            body: JSON.stringify({
              scene_pairs: pairsPayload,
              scenes: scenePayload,
              mode,
              strictness,
            }),
            signal: controller.signal,
          },
        )
        if (!res.ok) {
          const text = await res.text()
          throw new Error(text || `HTTP ${res.status}`)
        }
        const data = (await res.json()) as SceneContinuityResponse
        if (!cancelled) setResult(data)
      } catch (err) {
        if (!cancelled) {
          if (err instanceof Error && err.name === 'AbortError') return
          setError(err instanceof Error ? err.message : 'Scene continuity read unavailable.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [filmId, pairsPayload, scenePayload, mode, strictness, scenePairs.length])

  if (!filmId) {
    return (
      <section className="cinematic-panel p-4">
        <div className="text-xs text-zinc-500">No active project — scene continuity reads unavailable.</div>
      </section>
    )
  }

  if (scenePairs.length === 0) {
    return (
      <section className="cinematic-panel p-4">
        <div className="text-[11px] uppercase tracking-[0.14em] text-zinc-400">Scene Continuity</div>
        <div className="mt-2 text-xs text-zinc-500">
          No scene pairs available yet. Generate scenes first to see continuity reads.
        </div>
      </section>
    )
  }

  return (
    <section className="cinematic-panel p-4 space-y-4" data-testid="scene-continuity-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.14em] text-zinc-300">Scene Continuity</div>
          <div className="mt-0.5 text-xs text-zinc-500">Advisory only · no auto-regeneration</div>
        </div>

        {/* Controls */}
        <div className="flex flex-wrap items-center gap-2 text-[10px]">
          {/* Mode toggle */}
          <div className="inline-flex rounded border border-zinc-700 bg-zinc-900/70">
            {(['passive', 'active'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`px-2.5 py-1 rounded capitalize ${
                  mode === m
                    ? 'bg-zinc-700 text-zinc-100'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {m}
              </button>
            ))}
          </div>

          {/* Strictness toggle */}
          <div className="inline-flex rounded border border-zinc-700 bg-zinc-900/70">
            {(['low', 'medium', 'high'] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setStrictness(s)}
                className={`px-2.5 py-1 rounded capitalize ${
                  strictness === s
                    ? 'bg-zinc-700 text-zinc-100'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="text-xs text-zinc-400">Reading scene continuity…</div>
      ) : error ? (
        <div className="rounded border border-rose-400/30 bg-rose-500/8 px-3 py-2 text-[11px] text-rose-200">
          {error}
        </div>
      ) : result ? (
        <>
          {/* Overall status */}
          <div className="flex flex-wrap items-center gap-3 text-[11px]">
            <span className="uppercase tracking-[0.12em] text-zinc-400">Overall:</span>
            <span className={`font-semibold uppercase tracking-[0.1em] ${statusTone(result.overall_status)}`}>
              {result.overall_status.replace(/_/g, ' ')}
            </span>
            <span className="text-zinc-500">·</span>
            <span className="text-zinc-400">{result.transition_reads.length} transition(s)</span>
          </div>

          {/* Advisory notes */}
          {result.advisory_notes.length > 0 && (
            <div className="space-y-1">
              {result.advisory_notes.map((note, i) => (
                <div key={i} className="text-xs text-zinc-400">{note}</div>
              ))}
            </div>
          )}

          {/* Transition reads */}
          <div className="space-y-3">
            {result.transition_reads.map((tr, i) => (
              <div
                key={`${tr.from_scene_id}-${tr.to_scene_id}-${i}`}
                className={`rounded-lg border px-3 py-3 ${warningTone(tr.continuity_warnings.length)}`}
              >
                {/* Header */}
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-[11px] font-semibold text-zinc-100">
                    {tr.from_scene_id || '—'}
                    <span className="mx-1.5 text-zinc-500">→</span>
                    {tr.to_scene_id || '—'}
                  </div>
                  {tr.continuity_warnings.length > 0 && (
                    <span className="rounded-full border border-amber-400/50 bg-amber-500/12 px-2 py-0.5 text-[10px] uppercase tracking-[0.1em] text-amber-200">
                      {tr.continuity_warnings.length} concern{tr.continuity_warnings.length !== 1 ? 's' : ''}
                    </span>
                  )}
                </div>

                {/* Emotion fields */}
                <div className="mt-2 grid grid-cols-2 gap-2 text-[10px]">
                  {tr.exiting_emotion && (
                    <div>
                      <span className="text-zinc-500">Exiting: </span>
                      <span className="text-zinc-200">{tr.exiting_emotion}</span>
                    </div>
                  )}
                  {tr.entering_emotion && (
                    <div>
                      <span className="text-zinc-500">Entering: </span>
                      <span className="text-zinc-200">{tr.entering_emotion}</span>
                    </div>
                  )}
                  {tr.unresolved_tension && (
                    <div className="col-span-2">
                      <span className="text-zinc-500">Unresolved: </span>
                      <span className="text-amber-200">{tr.unresolved_tension}</span>
                    </div>
                  )}
                </div>

                {/* Advisory note */}
                {tr.advisory_note && (
                  <div className="mt-2 text-xs text-zinc-300">{tr.advisory_note}</div>
                )}

                {/* Warnings list */}
                {tr.continuity_warnings.length > 0 && (
                  <ul className="mt-2 space-y-0.5">
                    {tr.continuity_warnings.map((w, wi) => (
                      <li key={wi} className="text-xs text-amber-300">· {w}</li>
                    ))}
                  </ul>
                )}

                {/* Causal flags */}
                {tr.causal_check && tr.causal_check.impossibilities.length > 0 && (
                  <CausalFlagsSection causalCheck={tr.causal_check} />
                )}

                {/* Accept for revision */}
                {mode === 'active' && (
                  <button
                    type="button"
                    onClick={() =>
                      onRevisionProposalAccepted({
                        from_scene_id: tr.from_scene_id,
                        to_scene_id: tr.to_scene_id,
                        advisory_note: tr.advisory_note,
                        continuity_warnings: tr.continuity_warnings,
                      })
                    }
                    className="mt-2 rounded border border-cyan-400/40 bg-cyan-500/10 px-2.5 py-1 text-[10px] uppercase tracking-[0.1em] text-cyan-100"
                  >
                    Accept for revision pass
                  </button>
                )}
              </div>
            ))}
          </div>

          {/* Motifs */}
          <MotifsSection filmId={filmId} />
        </>
      ) : null}
    </section>
  )
}
