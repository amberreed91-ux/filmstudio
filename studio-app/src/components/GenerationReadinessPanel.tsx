import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Loader2,
  Play,
  RefreshCw,
  ShieldAlert,
  XCircle,
} from 'lucide-react'
import {
  getGenerationPreflight,
  type BatchAuthorizationShotResult,
  type GenerationPreflight,
  type GenerationPreflightCameraInstruction,
  type GenerationPreflightEntry,
  type GenerationPreflightManifestShot,
} from '../lib/studioApi'
import { friendlyRefusalError } from '../lib/sceneMintRefusals'

/** Single-take submit selection: one frozen storyboard shot via the scene-pipeline filter. */
export type SingleTakeSelection = {
  storyboardShotIds: string[]
  allowFullPackage: boolean
  acknowledgeUnknownCost: boolean
}

type Props = {
  projectId: string
  sceneId: string
  provider?: string
  renderProviderLabel?: string
  /** Multi-shot path: the panel itself triggers the scene pipeline Generate. */
  onGenerate?: () => void
  generateBusy?: boolean
  /** Single-take path: the parent submits the selected shot through the pipeline filter. */
  onGenerateSingleShot?: (selection: SingleTakeSelection) => void
  singleShotBusy?: boolean
  generateLabel?: string
  /** 'pipeline' gates the whole-scene button; 'single-shot' only blocks via guard. */
  mode?: 'pipeline' | 'single-shot'
  /** Callback when a reference action (e.g. Review References) is requested. */
  onReferenceAction?: () => void
  /** Extra frontend gate ANDed with backend readiness (e.g. audio-mode validation). */
  extraGenerateGate?: boolean
  /** Bump to force a fresh preflight (parent knows canonical state changed). */
  revision?: number
}

const NO_CREDITS_WHILE_BLOCKED =
  'No provider credits can be spent while generation is blocked.'

function blockerCategory(raw: string): string {
  const text = String(raw || '')
  if (/reference gate|environment reference|setting reference|canonical.*reference|locked reference/i.test(text)) {
    return 'References'
  }
  if (/unapproved AI suggestion|camera/i.test(text)) {
    return 'Camera'
  }
  if (/prompt|truncat|severed|ellipsis/i.test(text)) {
    return 'Prompt integrity'
  }
  if (/cost|budget|limit/i.test(text)) {
    return 'Cost'
  }
  if (/stale|mismatch|version/i.test(text)) {
    return 'State currency'
  }
  return 'Generation readiness'
}

function CameraProvenanceLine({ instruction }: { instruction: GenerationPreflightCameraInstruction }) {
  const dimension = String(instruction.dimension || '').replace(/_/g, ' ')
  const value = String(instruction.value || '').trim()
  const source = String(instruction.instruction_source || instruction.source || '')
  const unspecified = /unspecified/i.test(source)
  const aiSuggested = /AI_SUGGESTED/i.test(source)
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      {dimension && <span className="text-[10px] uppercase tracking-wide text-zinc-500">{dimension}</span>}
      <span className="text-[11px] text-zinc-200">{value || 'Unspecified'}</span>
      {aiSuggested ? (
        <span
          data-testid="camera-ai-suggested"
          className="rounded border border-amber-300/40 bg-amber-300/10 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-amber-200"
        >
          AI suggestion awaiting approval — not renderable
        </span>
      ) : unspecified ? (
        <span className="text-[9px] uppercase tracking-wide text-zinc-500">No decision recorded</span>
      ) : source ? (
        <span className="rounded border border-white/15 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-zinc-400">
          {source.replace(/_/g, ' ')}
        </span>
      ) : null}
    </div>
  )
}

function ShotPlanSection({
  shot,
  expanded,
  onToggle,
}: {
  shot: GenerationPreflightManifestShot
  expanded: boolean
  onToggle: () => void
}) {
  const order = shot.shot_order ?? ''
  const duration = shot.shot_duration_seconds
  const prompt = String(shot.shot_prompt || '').trim()
  const references = shot.references || []
  const cameras = shot.camera_instructions || []
  return (
    <div data-testid={`manifest-shot-${order}`} className="rounded border border-white/10 bg-black/20">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
      >
        <span className="flex items-center gap-2 text-xs font-medium text-zinc-200">
          {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          Shot {order}
          <span className="font-normal text-zinc-500">
            {duration ? `· ${duration}s` : ''}
            {shot.shot_version && shot.shot_version !== 'absent' ? ` · shot v ${shot.shot_version}` : ''}
          </span>
        </span>
        <span className="text-[10px] text-zinc-500">{expanded ? 'Hide details' : 'Review details'}</span>
      </button>
      {expanded && (
        <div className="space-y-2 border-t border-white/10 px-3 py-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">Prompt (sent verbatim)</p>
            {prompt ? (
              <p data-testid={`shot-prompt-${order}`} className="whitespace-pre-wrap break-words text-[11px] leading-relaxed text-zinc-300">
                {prompt}
              </p>
            ) : (
              <p data-testid={`shot-prompt-${order}`} className="text-[11px] text-zinc-400">Prompt unavailable</p>
            )}
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">Camera · provenance</p>
            {cameras.length > 0 ? (
              <div className="space-y-1">
                {cameras.map((instruction, idx) => (
                  <CameraProvenanceLine key={`${instruction.dimension}-${idx}`} instruction={instruction} />
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-zinc-400">Camera: Unspecified</p>
            )}
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">References</p>
            {references.length > 0 ? (
              <ul className="space-y-0.5">
                {references.map((url) => (
                  <li key={url} className="break-all text-[11px] text-zinc-300">
                    {url.startsWith('data:') ? '(inline image reference)' : url}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[11px] text-zinc-400">No references attached to this shot</p>
            )}
            <p className="text-[10px] text-zinc-500">Reference version: {shot.reference_version || 'none'}</p>
          </div>
          <p className="text-[10px] text-zinc-500">
            {shot.storyboard_shot_id ? `Storyboard shot: ${shot.storyboard_shot_id} · ` : ''}
            Shot version: {shot.shot_version || 'absent'}
          </p>
        </div>
      )}
    </div>
  )
}

/**
 * Single-take picker + spend dialog. Submits through the scene-pipeline
 * shot filter (one frozen storyboard shot, whole-scene gates still apply).
 * Nothing is preselected; confirming spends for exactly 1 submission.
 */
function SingleTakeDialog({
  entries,
  manifestShots,
  ceilingCredits,
  ceilingEnvVar,
  providerLabel,
  busy,
  boardId,
  onPick,
  spendConfirmed,
  onSpendConfirm,
  onCheckCost,
  checkingCost,
  onConfirm,
}: {
  entries: GenerationPreflightEntry[]
  manifestShots: GenerationPreflightManifestShot[]
  ceilingCredits: number
  ceilingEnvVar: string
  providerLabel?: string
  busy: boolean
  boardId: string
  onPick: (boardId: string) => void
  spendConfirmed: boolean
  onSpendConfirm: (confirmed: boolean) => void
  onCheckCost: () => void
  checkingCost: boolean
  onConfirm: (boardId: string) => void
}) {
  const selectable = entries.filter((entry) => (entry.blockers || []).length === 0 && entry.storyboard_shot_id)
  const selected = entries.find((entry) => entry.storyboard_shot_id === boardId) ?? null
  const manifestRow = manifestShots.find((shot) => shot.storyboard_shot_id === boardId) ?? null
  const exactPrompt = String(selected?.prompt || manifestRow?.shot_prompt || '').trim()
  const characters = (selected?.character_focus || []).filter(Boolean)
  const estimate = selected?.cost_estimate ?? null
  const estimateKnown = Boolean(estimate?.estimated) && estimate?.estimated_credits != null
  const priorSubmissions = selected?.prior_render_submissions ?? 0
  return (
    <div className="mt-2" data-testid="single-take-dialog">
      <p className="text-[10px] text-zinc-500">
        Nothing is preselected. Pick exactly one shot{providerLabel ? ` with ${providerLabel}` : ''}; confirming spends Runway credits for 1 submission.
      </p>
      <div className="mt-2 space-y-1" role="radiogroup" aria-label="Scene shots">
        {selectable.map((entry) => (
          <label key={entry.storyboard_shot_id} className="flex items-center gap-2 text-xs text-zinc-200">
            <input
              type="radio"
              name="single-take-choice"
              value={entry.storyboard_shot_id}
              checked={boardId === entry.storyboard_shot_id}
              onChange={() => onPick(String(entry.storyboard_shot_id))}
            />
            <span>Shot {entry.shot_order ?? entry.shot_id}</span>
            <span className="text-[10px] text-zinc-500">
              {entry.duration_seconds ? `· ${entry.duration_seconds}s` : ''}
              {' '}· {(entry.prior_render_submissions ?? 0) === 0 ? 'no prior Runway submissions' : `${entry.prior_render_submissions} prior Runway submission${entry.prior_render_submissions === 1 ? '' : 's'}`}
            </span>
          </label>
        ))}
        {selectable.length === 0 ? (
          <p className="text-[10px] text-amber-200">No ready shots are available — resolve the blockers above first.</p>
        ) : null}
      </div>
      {selected && (
        <div className="mt-3 space-y-2 border-t border-white/10 pt-3" data-testid="single-take-confirm">
          <div className="text-xs text-zinc-200">
            Shot {selected.shot_order ?? selected.shot_id} · 1 Runway submission
            {' '}· {priorSubmissions === 0 ? 'no prior Runway submissions' : `${priorSubmissions} prior Runway submission${priorSubmissions === 1 ? '' : 's'}`}
          </div>
          <div className="text-[11px] text-zinc-300">
            Characters: {characters.length > 0 ? characters.join(', ') : 'none named'}
            {selected.duration_seconds ? ` · Duration: ${selected.duration_seconds}s` : ''}
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.1em] text-zinc-500">
              Exact prompt text that will be sent (first 600 characters)
            </div>
            <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-black/40 p-2 text-[10px] leading-relaxed text-zinc-300">
              {exactPrompt.slice(0, 600) || '(empty prompt — submission will fail closed)'}
            </pre>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={busy || checkingCost}
              onClick={onCheckCost}
              className="btn-ghost px-3 py-2 text-[10px]"
              data-testid="single-take-check-cost"
              title="Re-runs the read-only generation preflight for this scene. Creates no job and spends nothing."
            >
              {checkingCost ? 'Checking cost…' : 'Check cost (estimate)'}
            </button>
            <span className="text-[10px] text-zinc-300" data-testid="single-take-estimate">
              {estimateKnown
                ? `Runway cost estimate (advisory — submit path may differ, not a quote): ${estimate?.estimated_credits} credits · ceiling ${ceilingCredits} (${ceilingEnvVar})`
                : `Runway cost estimate unavailable (submit path may differ) · ceiling ${ceilingCredits} (${ceilingEnvVar})`}
            </span>
          </div>
          <label className="flex items-start gap-2 text-xs text-zinc-200">
            <input
              type="checkbox"
              checked={spendConfirmed}
              onChange={(event) => onSpendConfirm(event.target.checked)}
              className="mt-0.5"
            />
            I understand this spends Runway credits for 1 submission{estimateKnown ? '' : ' and accept the unknown cost'}
          </label>
          <button
            type="button"
            disabled={!spendConfirmed || busy}
            onClick={() => onConfirm(String(selected.storyboard_shot_id))}
            className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-amber-100 disabled:opacity-40"
            data-testid="single-take-confirm-button"
          >
            Confirm: render this one take
          </button>
        </div>
      )}
    </div>
  )
}

/**
 * Generation Readiness — an inspection and safety surface over the backend's
 * own preflight (SceneProductionPipelineService.prepare_scene_batch).
 *
 * This component contains NO readiness logic of its own: it displays the
 * backend's verdict, blockers, cost estimate, and deterministic shot manifest
 * exactly as returned, and disables Generate while the backend reports the
 * scene blocked or its state has changed since the last preflight.
 */
export default function GenerationReadinessPanel({
  projectId,
  sceneId,
  provider,
  renderProviderLabel,
  onGenerate,
  generateBusy,
  onGenerateSingleShot,
  singleShotBusy,
  generateLabel = 'Generate new scene footage',
  mode = 'pipeline',
  onReferenceAction,
  extraGenerateGate = true,
  revision = 0,
}: Props) {
  const [preflight, setPreflight] = useState<GenerationPreflight | null>(null)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState('')
  const [stale, setStale] = useState(false)
  const [expandedShots, setExpandedShots] = useState<Set<number>>(new Set())
  // Single-take dialog state only. Nothing here submits — confirming calls
  // the parent's pipeline-filter submit; Check cost only re-runs the
  // read-only preflight.
  const [takeOpen, setTakeOpen] = useState(false)
  const [takeShotBoardId, setTakeShotBoardId] = useState('')
  const [takeSpendConfirmed, setTakeSpendConfirmed] = useState(false)
  const checkedKeyRef = useRef('')

  const canCheck = Boolean(projectId && sceneId)

  const check = useCallback(async () => {
    if (!canCheck) return
    checkedKeyRef.current = `${projectId}::${sceneId}::${provider || ''}`
    setChecking(true)
    setError('')
    try {
      const result = await getGenerationPreflight(projectId, sceneId, provider || undefined)
      setPreflight(result)
      setStale(false)
    } catch (err) {
      setPreflight(null)
      setError(err instanceof Error ? err.message : 'Generation preflight is unavailable')
    } finally {
      setChecking(false)
    }
  }, [projectId, sceneId, provider, canCheck])

  // First mount: run the preflight. Afterwards, any change of scene,
  // project, or provider invalidates the displayed result and REQUIRES an
  // explicit new preflight — an old verdict never authorizes new state.
  useEffect(() => {
    const key = `${projectId}::${sceneId}::${provider || ''}`
    if (checkedKeyRef.current === '') {
      void check()
      return
    }
    if (checkedKeyRef.current !== key) {
      setStale(true)
    }
  }, [projectId, sceneId, provider, check])

  // External revision bumps (storyboard/scene mutations) invalidate the
  // displayed verdict and immediately re-run the read-only preflight.
  const revisionRef = useRef(revision)
  useEffect(() => {
    if (revisionRef.current === revision) return
    revisionRef.current = revision
    if (canCheck) {
      setStale(true)
      void check()
    }
  }, [revision, check, canCheck])

  // Batch authorization (R4.1A): the backend's all-or-nothing verdict over
  // every shot. Absent on older backends — treated as satisfied so the
  // existing readiness verdict keeps working unmodified.
  const authorization = preflight?.authorization ?? null
  const authorizationReady = !authorization || authorization.ready === true
  const authorizationFailedShots: BatchAuthorizationShotResult[] = (authorization?.shots || []).filter(
    (shot) => !shot.ok,
  )
  // A batch the backend refused to authorize must never appear ready for
  // generation, even when the readiness gates themselves passed.
  const batchBlocked = !preflight?.ready || !authorizationReady

  const generateAllowed =
    preflight !== null && preflight.ready === true && authorizationReady && !stale && !checking && !error && extraGenerateGate

  const manifestShots = preflight?.manifest?.shots || []
  const entries = preflight?.entries || []
  const shotsReady = entries.filter((entry) => (entry.blockers || []).length === 0).length
  const shotsBlocked = entries.length - shotsReady
  const batch = preflight?.manifest?.batch
  const cost = preflight?.cost_estimate

  const aggregateBlockers = useMemo(() => {
    if (!preflight) return [] as string[]
    return preflight.blockers || []
  }, [preflight])

  const toggleShot = (order: number) => {
    setExpandedShots((prev) => {
      const next = new Set(prev)
      if (next.has(order)) next.delete(order)
      else next.add(order)
      return next
    })
  }

  /**
   * Generate: runs a FRESH backend preflight first and only forwards to
   * ``onGenerate`` from that fresh verdict. If the scene changed between the
   * displayed check and this click, the fresh check is authoritative — the
   * displayed blockers refresh and nothing is generated.
   */
  const handleGenerateClick = useCallback(async () => {
    if (!canCheck || generateBusy) return
    try {
      const fresh = await getGenerationPreflight(projectId, sceneId, provider || undefined)
      setPreflight(fresh)
      setStale(false)
      if (!fresh.ready || fresh.authorization?.ready === false) return
      onGenerate?.()
    } catch (err) {
      setPreflight(null)
      setError(err instanceof Error ? err.message : 'Generation preflight is unavailable')
    }
  }, [canCheck, generateBusy, projectId, sceneId, provider, onGenerate])

  if (!canCheck) return null

  return (
    <section data-testid="generation-readiness" className="rounded-lg border border-white/10 bg-black/15 p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-zinc-100">Generation Readiness</h3>
        <button
          type="button"
          data-testid="preflight-recheck"
          onClick={() => void check()}
          disabled={checking}
          className="inline-flex items-center gap-1 rounded border border-white/15 px-2 py-1 text-[10px] text-zinc-300 disabled:opacity-50"
        >
          {checking ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          Re-check
        </button>
      </div>

      {checking && (
        <p data-testid="preflight-checking" role="status" className="mt-2 flex items-center gap-2 text-xs text-zinc-400">
          <Loader2 size={13} className="animate-spin" />
          Checking generation readiness...
        </p>
      )}

      {!checking && error && (
        <div data-testid="preflight-error" role="alert" className="mt-3 rounded border border-rose-400/30 bg-rose-500/5 p-3">
          <p className="flex items-center gap-2 text-xs font-medium text-rose-200">
            <AlertTriangle size={13} /> Generation preflight is unavailable
          </p>
          <p className="mt-1 break-words text-[11px] text-rose-200/80">{error}</p>
          <p className="mt-1 text-[11px] text-zinc-400">
            The backend could not be reached, so generation stays disabled. Nothing has been spent.
          </p>
        </div>
      )}

      {!checking && !error && stale && (
        <div data-testid="preflight-stale" role="alert" className="mt-3 rounded border border-amber-300/30 bg-amber-300/5 p-3">
          <p className="flex items-center gap-2 text-xs font-medium text-amber-200">
            <ShieldAlert size={13} /> This readiness result is stale
          </p>
          <p className="mt-1 text-[11px] text-amber-200/80">
            The scene, storyboard, or provider selection changed after this preflight. Re-check before generating.
          </p>
          <button
            type="button"
            data-testid="preflight-recheck-stale"
            onClick={() => void check()}
            className="mt-2 inline-flex items-center gap-1 rounded border border-amber-300/40 px-2 py-1 text-[11px] text-amber-100"
          >
            <RefreshCw size={11} /> Re-run preflight
          </button>
        </div>
      )}

      {!checking && !error && !stale && preflight && (
        <>
          <div
            data-testid={`preflight-status-${batchBlocked ? 'blocked' : 'ready'}`}
            role="status"
            className={`mt-3 rounded border p-3 ${
              batchBlocked
                ? 'border-rose-400/30 bg-rose-500/5'
                : 'border-emerald-300/30 bg-emerald-300/5'
            }`}
          >
            <p className={`flex items-center gap-2 text-xs font-semibold uppercase tracking-wide ${batchBlocked ? 'text-rose-200' : 'text-emerald-200'}`}>
              {batchBlocked ? <XCircle size={14} /> : <CheckCircle2 size={14} />}
              {batchBlocked ? 'BLOCKED' : 'READY'}
            </p>

            {!batchBlocked ? (
              <div data-testid="preflight-plan" className="mt-2 space-y-1 text-[11px] text-zinc-300">
                <p className="text-xs font-medium text-emerald-100">Ready to Generate</p>
                {renderProviderLabel && (
                  <p data-testid="preflight-provider">
                    Execution provider: <span className="text-zinc-100">{renderProviderLabel}</span>
                  </p>
                )}
                <p data-testid="preflight-shot-count">
                  Shots: {batch?.shot_count ?? preflight.shot_count}
                </p>
                {batch?.total_duration_seconds != null && (
                  <p data-testid="preflight-total-duration">
                    Total generated footage: {batch.total_duration_seconds}s
                  </p>
                )}
                {cost?.estimated && cost.estimated_total_credits != null && (
                  <p data-testid="preflight-estimated-cost">
                    Estimated cost: {cost.estimated_total_credits} credits
                  </p>
                )}
                <p data-testid="preflight-mode">Generation mode: Studio Multi Shot</p>
                <p className="text-zinc-400">
                  Provider execution: {batch?.shot_count ?? preflight.shot_count} individual shot generations · Assembly: Studio local scene assembly
                </p>
              </div>
            ) : (
              <div data-testid="preflight-blockers" className="mt-2 space-y-2">
                {aggregateBlockers.length === 0 ? (
                  <p className="text-[11px] text-rose-200/80">Generation is blocked by the backend preflight.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {aggregateBlockers.map((raw, idx) => (
                      <li key={`${idx}-${raw.slice(0, 24)}`} className="rounded border border-rose-400/20 bg-black/20 p-2">
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-rose-200/80">
                          {blockerCategory(raw)}
                        </p>
                        <p className="mt-0.5 break-words text-[11px] leading-relaxed text-zinc-200">{friendlyRefusalError(raw, raw)}</p>
                      </li>
                    ))}
                  </ul>
                )}
                {authorizationFailedShots.length > 0 && (
                  <div data-testid="preflight-authorization-failures" className="space-y-1.5">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-rose-200/80">
                      Batch authorization — no jobs were created
                    </p>
                    <ul className="space-y-1.5">
                      {authorizationFailedShots.map((shot) => (
                        <li
                          key={shot.shot_id || shot.failure_code || 'unknown'}
                          data-testid={`preflight-auth-shot-${shot.shot_id}`}
                          className="rounded border border-rose-400/20 bg-black/20 p-2"
                        >
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-rose-200/80">
                            {shot.shot_id || 'Unidentified shot'}
                          </p>
                          <p className="mt-0.5 break-words text-[11px] leading-relaxed text-zinc-200">
                            {friendlyRefusalError(shot.message, 'This shot failed batch authorization.')}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {onReferenceAction && aggregateBlockers.some((raw) => blockerCategory(raw) === 'References') && (
                  <button
                    type="button"
                    data-testid="preflight-review-references"
                    onClick={onReferenceAction}
                    className="rounded border border-white/20 px-2 py-1 text-[11px] text-zinc-200"
                  >
                    Review References
                  </button>
                )}
                <p data-testid="preflight-no-credits" className="text-[11px] font-medium text-amber-200">
                  {NO_CREDITS_WHILE_BLOCKED}
                </p>
              </div>
            )}
          </div>

          {entries.length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-medium text-zinc-200">Shot Readiness</p>
              {entries.length > 1 && (
                <p data-testid="preflight-multishot-summary" className="mt-0.5 text-[11px] text-zinc-400">
                  {entries.length} shots · {shotsReady} ready · {shotsBlocked} blocked
                  {!preflight.ready && shotsBlocked > 0 && ' — the scene cannot render until all required shots pass preflight'}
                </p>
              )}
              <ul className="mt-1 space-y-1">
                {entries.map((entry: GenerationPreflightEntry) => {
                  const shotBlockers = entry.blockers || []
                  const order = entry.shot_order ?? entry.shot_id
                  return (
                    <li
                      key={entry.shot_id}
                      data-testid={`preflight-shot-${order}`}
                      className={`rounded border px-2 py-1.5 ${
                        shotBlockers.length === 0
                          ? 'border-emerald-300/20 bg-emerald-300/5'
                          : 'border-rose-400/25 bg-rose-500/5'
                      }`}
                    >
                      <p className={`flex items-center gap-1.5 text-[11px] font-medium ${shotBlockers.length === 0 ? 'text-emerald-200' : 'text-rose-200'}`}>
                        {shotBlockers.length === 0 ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
                        Shot {order} {shotBlockers.length === 0 ? '· Ready' : '· Blocked'}
                      </p>
                      {shotBlockers.length > 0 && (
                        <ul className="mt-0.5 space-y-0.5">
                          {shotBlockers.map((raw, idx) => (
                            <li key={`${idx}-${raw.slice(0, 24)}`} className="break-words text-[11px] leading-relaxed text-zinc-300">
                              {friendlyRefusalError(raw, raw)}
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          {manifestShots.length > 0 && (
            <details data-testid="preflight-manifest" className="mt-3 rounded-lg border border-white/10 p-3">
              <summary className="cursor-pointer text-xs font-medium text-zinc-300">Review Generation Plan</summary>
              <p className="mt-2 text-[11px] text-zinc-500">
                Exactly what Studio will send to the provider, shot by shot, from the backend&apos;s deterministic manifest
                {preflight.manifest?.manifest_fingerprint ? ` (fingerprint ${preflight.manifest.manifest_fingerprint})` : ''}.
              </p>
              <div className="mt-2 space-y-2">
                {manifestShots.map((shot) => (
                  <ShotPlanSection
                    key={shot.shot_id}
                    shot={shot}
                    expanded={expandedShots.has(shot.shot_order ?? 0)}
                    onToggle={() => toggleShot(shot.shot_order ?? 0)}
                  />
                ))}
              </div>
            </details>
          )}
        </>
      )}

      {mode === 'pipeline' && onGenerateSingleShot && !batchBlocked && !stale && !checking && !error && preflight && (
        <div className="mt-3 rounded-lg border border-white/10 bg-black/20 p-3" data-testid="single-take-section">
          <button
            type="button"
            data-testid="single-take-toggle"
            onClick={() => { setTakeOpen((open) => !open); setTakeShotBoardId(''); setTakeSpendConfirmed(false) }}
            className="flex w-full items-center justify-between gap-2 text-left"
            aria-expanded={takeOpen}
          >
            <span className="text-xs font-medium text-zinc-200">Render a single take…</span>
            <span className="text-[10px] text-zinc-500">{takeOpen ? 'Hide' : 'Pick one frozen shot'}</span>
          </button>
          {takeOpen && (
            <SingleTakeDialog
              entries={entries}
              manifestShots={manifestShots}
              ceilingCredits={preflight.credit_ceiling_credits ?? 300}
              ceilingEnvVar={preflight.credit_ceiling_env_var || 'RUNWAY_RENDER_MAX_CREDITS'}
              providerLabel={renderProviderLabel}
              busy={Boolean(singleShotBusy)}
              boardId={takeShotBoardId}
              onPick={(id) => { setTakeShotBoardId(id); setTakeSpendConfirmed(false) }}
              spendConfirmed={takeSpendConfirmed}
              onSpendConfirm={setTakeSpendConfirmed}
              onCheckCost={() => void check()}
              checkingCost={checking}
              onConfirm={(boardId) => onGenerateSingleShot({
                storyboardShotIds: [boardId],
                allowFullPackage: false,
                acknowledgeUnknownCost: takeSpendConfirmed,
              })}
            />
          )}
        </div>
      )}
      {mode === 'pipeline' && onGenerate && (
        <button
          type="button"
          data-testid="preflight-generate"
          onClick={() => void handleGenerateClick()}
          disabled={!generateAllowed || Boolean(generateBusy)}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border px-3 py-2 text-[10px] font-bold uppercase tracking-[0.1em] transition-all disabled:cursor-not-allowed disabled:opacity-50"
          style={{
            borderColor: 'rgba(34,211,238,0.35)',
            color: 'var(--color-primary)',
            background: 'rgba(34,211,238,0.08)',
          }}
        >
          {generateBusy ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
          {generateBusy ? 'Generating' : generateLabel}
        </button>
      )}
      {mode === 'pipeline' && !generateAllowed && !checking && (
        <p className="mt-1 text-[10px] leading-relaxed text-zinc-500">
          Generation is disabled until the backend preflight reports this scene ready.
        </p>
      )}
    </section>
  )
}
