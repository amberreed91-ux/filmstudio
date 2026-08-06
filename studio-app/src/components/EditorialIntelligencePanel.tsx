import { useEffect, useMemo, useState } from 'react'
import { Brain, CheckCircle2, Loader2, Scissors } from 'lucide-react'
import {
  analyzeEditorialIntelligence,
  approveFilmCut,
  applyEditorialDecisions,
  getCurrentFilmCut,
  getLatestEditorialIntelligence,
  type EditorialAnalysisRecord,
  type EditorialApplyResult,
  type FilmCutVersion,
} from '../lib/studioApi'
import { isStitchableEditorialDecision } from '../lib/editorialDecision'

type EditorialIntelligencePanelProps = {
  projectId: string
  sourcePackageId?: string
  onApplied?: (result: EditorialApplyResult) => void
}

export default function EditorialIntelligencePanel({
  projectId,
  sourcePackageId = '',
  onApplied,
}: EditorialIntelligencePanelProps) {
  const [analysis, setAnalysis] = useState<EditorialAnalysisRecord | null>(null)
  const [filmCut, setFilmCut] = useState<FilmCutVersion | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [approvingCut, setApprovingCut] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    setError('')
    void getLatestEditorialIntelligence(projectId)
      .then((payload) => {
        if (!cancelled) setAnalysis(payload.analysis)
      })
    void getCurrentFilmCut(projectId)
      .then((payload) => {
        if (!cancelled) setFilmCut(payload.film_cut)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Film Cut unavailable')
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Editorial intelligence unavailable')
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  useEffect(() => {
    setSelected([])
  }, [analysis?.analysis_id])

  const stitchableDecisionIds = useMemo(
    () => analysis?.edit_decisions.filter((row) => isStitchableEditorialDecision(row.decision_type)).map((row) => row.decision_id) ?? [],
    [analysis],
  )

  async function onReadCut() {
    if (!projectId) return
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const payload = await analyzeEditorialIntelligence(projectId, {
        source_package_id: sourcePackageId,
        analysis_depth: 'standard',
        revision_emphasis: 'balanced',
      })
      setAnalysis(payload.analysis)
      setMessage('Editorial read updated.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Editorial analysis failed')
    } finally {
      setLoading(false)
    }
  }

  async function onApplyToNextStitch() {
    if (!projectId || !analysis || selected.length === 0) return
    const decisionIds = selected.filter((decisionId) => stitchableDecisionIds.includes(decisionId))
    if (decisionIds.length === 0) return
    setApplying(true)
    setError('')
    setMessage('')
    try {
      const payload = await applyEditorialDecisions(projectId, analysis.analysis_id, {
        decision_ids: decisionIds,
        apply_mode: 'next_stitch',
        expected_context_hash: analysis.context_hash,
        creator_confirmation: true,
      })
      setMessage(payload.result.applied_effects[0] || 'Editorial decisions prepared for the next stitch.')
      onApplied?.(payload.result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not apply editorial decisions')
    } finally {
      setApplying(false)
    }
  }

  async function onApplyCutRevision() {
    if (!projectId || !analysis) return
    const decisionIds = analysis.edit_decisions
      .filter((decision) => decision.decision_type === 'reorder_scene' && selected.includes(decision.decision_id))
      .map((decision) => decision.decision_id)
    if (decisionIds.length === 0) return
    if (!window.confirm('Create a new Film Cut version from the selected editorial decision? The current version will remain in history.')) return
    setApplying(true)
    setError('')
    setMessage('')
    try {
      const payload = await applyEditorialDecisions(projectId, analysis.analysis_id, {
        decision_ids: decisionIds,
        apply_mode: 'update_cut',
        expected_context_hash: analysis.context_hash,
        creator_confirmation: true,
      })
      const current = await getCurrentFilmCut(projectId)
      setFilmCut(current.film_cut)
      setSelected([])
      setMessage(`Film Cut v${current.film_cut.version_number} created from this analysis.`)
      onApplied?.(payload.result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create Film Cut revision')
    } finally {
      setApplying(false)
    }
  }

  async function onApproveCut() {
    if (!projectId || !filmCut || filmCut.status === 'approved') return
    if (!window.confirm(`Approve Film Cut v${filmCut.version_number} as the current cut?`)) return
    setApprovingCut(true)
    setError('')
    try {
      const payload = await approveFilmCut(projectId, filmCut.cut_id)
      setFilmCut(payload.film_cut)
      setMessage(`Film Cut v${payload.film_cut.version_number} approved.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Film Cut approval failed')
    } finally {
      setApprovingCut(false)
    }
  }

  function toggleDecision(decisionId: string) {
    setSelected((current) => (
      current.includes(decisionId)
        ? current.filter((row) => row !== decisionId)
        : [...current, decisionId]
    ))
  }

  const canApplyToStitch = selected.some((decisionId) => stitchableDecisionIds.includes(decisionId)) && Boolean(analysis)
  const canApplyCutRevision = Boolean(analysis?.edit_decisions.some(
    (decision) => decision.decision_type === 'reorder_scene' && selected.includes(decision.decision_id),
  ))

  return (
    <section className="glass-panel rounded-xl p-4" data-testid="editorial-intelligence-panel">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Brain size={15} style={{ color: 'var(--color-primary)' }} />
          <h3 className="text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: 'var(--color-on-surface-variant)' }}>
            Editorial Intelligence
          </h3>
        </div>
        <button
          type="button"
          onClick={onReadCut}
          disabled={loading || !projectId}
          className="flex shrink-0 items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-[0.1em] transition-all hover:bg-white/10 disabled:opacity-50"
          style={{ color: 'var(--color-on-surface-variant)' }}
        >
          {loading ? <Loader2 size={12} className="animate-spin" /> : <Scissors size={12} />}
          Read Cut
        </button>
      </div>

      {filmCut ? (
        <div className="mt-3 flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-[10px] uppercase tracking-[0.1em] text-zinc-300">
          <span>Film Cut v{filmCut.version_number} · {filmCut.status.replace(/_/g, ' ')}</span>
          <button
            type="button"
            onClick={() => void onApproveCut()}
            disabled={approvingCut || filmCut.status === 'approved'}
            className="rounded border border-amber-400/40 px-2 py-1 font-bold text-amber-200 disabled:opacity-50"
          >
            {approvingCut ? 'Approving…' : filmCut.status === 'approved' ? 'Approved' : 'Approve Cut'}
          </button>
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 rounded-lg border border-rose-400/30 bg-rose-500/10 p-2 text-xs text-rose-100">
          {error}
        </div>
      ) : null}
      {message ? (
        <div className="mt-3 rounded-lg border border-emerald-400/30 bg-emerald-500/10 p-2 text-xs text-emerald-100">
          {message}
        </div>
      ) : null}

      {!analysis ? (
        <p className="mt-3 text-xs leading-relaxed" style={{ color: 'var(--color-on-surface-variant)' }}>
          Ask the Studio to read pacing, rhythm, transitions, and emotional flow from the current cut.
        </p>
      ) : (
        <div className="mt-3 space-y-3">
          <div className="rounded-lg border border-white/10 bg-white/5 p-3">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-cyan-200">Read</div>
            <p className="mt-1 text-sm leading-relaxed text-zinc-100">{analysis.overall_read}</p>
            {analysis.low_data_reasons.length > 0 ? (
              <ul className="mt-2 space-y-1 text-[11px] text-zinc-400">
                {analysis.low_data_reasons.map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
            ) : null}
          </div>

          <div className="grid gap-2">
            {analysis.pacing_diagnostics.slice(0, 1).map((diagnostic) => (
              <div key={diagnostic.diagnostic_id} className="rounded-lg border border-white/10 bg-black/20 p-2">
                <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-amber-200">Pacing</div>
                <p className="mt-1 text-xs text-zinc-200">{diagnostic.read}</p>
                {diagnostic.recommendation ? <p className="mt-1 text-[11px] text-zinc-400">{diagnostic.recommendation}</p> : null}
              </div>
            ))}
            <div className="rounded-lg border border-white/10 bg-black/20 p-2">
              <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-fuchsia-200">Emotional Flow</div>
              <p className="mt-1 text-xs text-zinc-200">{analysis.emotional_flow.read}</p>
              <p className="mt-1 text-[11px] text-zinc-400">{analysis.emotional_flow.emotional_residue}</p>
            </div>
          </div>

          {analysis.transition_advisories.length > 0 ? (
            <div className="rounded-lg border border-white/10 bg-black/20 p-2">
              <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-emerald-200">Transitions</div>
              <div className="mt-2 space-y-2">
                {analysis.transition_advisories.slice(0, 3).map((advisory) => (
                  <div key={advisory.transition_id} className="rounded border border-white/10 bg-white/5 p-2 text-[11px] text-zinc-300">
                    <div className="font-semibold text-zinc-100">
                      {advisory.from_scene_id || 'scene'} to {advisory.to_scene_id || 'scene'}: {advisory.recommended_transition_type.replace(/_/g, ' ')}
                    </div>
                    <div className="mt-1">{advisory.rationale}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {analysis.reasoning_trace.length > 0 ? (
            <div className="rounded-lg border border-white/10 bg-black/20 p-2">
              <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-sky-200">Reasoning Trace</div>
              <ul className="mt-2 space-y-1 text-[11px] text-zinc-400">
                {analysis.reasoning_trace.slice(0, 4).map((trace) => <li key={trace}>{trace}</li>)}
              </ul>
            </div>
          ) : null}

          <div className="rounded-lg border border-white/10 bg-black/20 p-2">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-violet-200">Decisions</div>
            <div className="mt-2 space-y-2">
              {analysis.edit_decisions.slice(0, 4).map((decision) => {
                const selectable = stitchableDecisionIds.includes(decision.decision_id) || decision.decision_type === 'reorder_scene'
                return (
                  <label key={decision.decision_id} className="flex gap-2 rounded border border-white/10 bg-white/5 p-2 text-[11px] text-zinc-300">
                    <input
                      type="checkbox"
                      checked={selected.includes(decision.decision_id)}
                      onChange={() => toggleDecision(decision.decision_id)}
                      disabled={!selectable}
                      className="mt-0.5"
                    />
                      <span>
                        <span className="block font-semibold text-zinc-100">{decision.recommendation}</span>
                        <span className="mt-1 block">{decision.rationale}</span>
                      {decision.evidence_refs.length > 0 ? (
                        <span className="mt-1 block text-zinc-500">
                          Evidence: {decision.evidence_refs.slice(0, 2).map((ref) => ref.description || `${ref.source_type}:${ref.source_id}`).join(' · ')}
                        </span>
                      ) : (
                        <span className="mt-1 block text-zinc-500">Evidence is still forming for this note.</span>
                      )}
                      </span>
                  </label>
                )
              })}
            </div>
            <button
              type="button"
              onClick={onApplyToNextStitch}
              disabled={!canApplyToStitch || applying}
              className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-emerald-100 transition-all hover:bg-emerald-500/20 disabled:opacity-50"
            >
              {applying ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
              Apply To Next Stitch
            </button>
            <button
              type="button"
              onClick={() => void onApplyCutRevision()}
              disabled={!canApplyCutRevision || applying}
              className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-amber-100 transition-all hover:bg-amber-500/20 disabled:opacity-50"
            >
              {applying ? <Loader2 size={12} className="animate-spin" /> : <Scissors size={12} />}
              Create Film Cut Revision
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
