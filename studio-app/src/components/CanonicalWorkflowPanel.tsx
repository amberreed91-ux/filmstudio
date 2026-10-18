import { useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, RefreshCcw, Workflow } from 'lucide-react'
import {
  analyzeCanonicalEditorial,
  applyCanonicalEditorialDecision,
  approveCanonicalFilmCut,
  approveCanonicalPrevis,
  approveCanonicalScreening,
  beginCanonicalWorkflow,
  createCanonicalProductionPackage,
  createCanonicalRevision,
  estimateCanonicalRenders,
  generateCanonicalPrevis,
  renderCanonicalProductionPackage,
  renderCanonicalRevision,
  renderCanonicalShots,
  saveCanonicalMemory,
  syncCanonicalScreening,
  updateCanonicalFilmCut,
  type CanonicalWorkflowResponse,
  type CanonicalWorkflowRun,
  type RenderEstimateResponse,
} from '../lib/canonicalWorkflowApi'
import {
  isRevisionSubmitted,
  nextCanonicalWorkflowAction,
  workflowArtifactIds,
  workflowIdentifierList,
  type CanonicalSceneContext,
} from '../lib/canonicalWorkflowContext'
import { withProductionContext } from '../lib/projectContext'
import { useCanonicalWorkflow } from '../hooks/useCanonicalWorkflow'

type AnyRecord = Record<string, unknown>

type CanonicalWorkflowPanelProps = {
  projectId: string
  sceneId: string
  sceneContext: CanonicalSceneContext
  surface: 'previs' | 'screening'
  renderProvider?: string
  renderProviderLabel?: string
}

function record(value: unknown): AnyRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as AnyRecord
    : null
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function decisionRows(run: CanonicalWorkflowRun | null): AnyRecord[] {
  const analysis = record(run?.data.artifacts.editorial_analysis)
  return Array.isArray(analysis?.edit_decisions)
    ? analysis.edit_decisions.map(record).filter((row): row is AnyRecord => Boolean(row))
    : []
}

function statusLabel(status: string): string {
  return status.replace(/_/g, ' ')
}

// D5 guarded single-shot render: dialog state only. Nothing here contacts a
// provider on render or on dialog open — Check cost is the sole network call
// and it fires only from its own click (dryRun:true, no task, no billing per
// provider code comments; billing on this account is unverified).
type PackageShot = {
  storyboard_shot_id: string
  shot_id: string
  prompt: string
  parameters: Record<string, unknown>
  previs_image_id: string
}

function packageShots(run: CanonicalWorkflowRun | null): PackageShot[] {
  const artifacts = record(run?.data.artifacts)
  const payload = record(record(artifacts?.production_package)?.payload)
  const shots = payload?.shots
  if (!Array.isArray(shots)) return []
  const rows: PackageShot[] = []
  for (const entry of shots) {
    const shot = record(entry)
    const storyboardShotId = text(shot?.storyboard_shot_id)
    if (!storyboardShotId) continue
    rows.push({
      storyboard_shot_id: storyboardShotId,
      shot_id: text(shot?.shot_id),
      prompt: typeof shot?.prompt === 'string' ? shot.prompt : '',
      parameters: record(shot?.parameters) ?? {},
      previs_image_id: text(shot?.previs_image_id),
    })
  }
  return rows
}

function plannedDurationOf(shot: PackageShot): number | null {
  for (const key of ['duration_seconds', 'duration']) {
    const value = shot.parameters[key]
    if (typeof value === 'number' && Number.isInteger(value)) return value
  }
  return null
}

function capsNames(prompt: string): string[] {
  const hits = prompt.match(/\b[A-Z][A-Z'\u2019-]{2,}\b/g) || []
  return [...new Set(hits)].slice(0, 12)
}

export default function CanonicalWorkflowPanel({
  projectId,
  sceneId,
  sceneContext,
  surface,
  renderProvider,
  renderProviderLabel,
}: CanonicalWorkflowPanelProps) {
  const controller = useCanonicalWorkflow(projectId, sceneId)
  const resolvedSceneContext = controller.sceneContext ?? sceneContext
  const [revisionPrompt, setRevisionPrompt] = useState('')
  const [revisionReason, setRevisionReason] = useState('')
  const [changedFields, setChangedFields] = useState('timing, performance_guidance')
  const [memorySummary, setMemorySummary] = useState('')
  const [singleShotOpen, setSingleShotOpen] = useState(false)
  const [wholePackageOpen, setWholePackageOpen] = useState(false)
  const [selectedShotId, setSelectedShotId] = useState('')
  const [durationInput, setDurationInput] = useState('')
  const [spendConfirmed, setSpendConfirmed] = useState(false)
  const [unknownCostConfirmed, setUnknownCostConfirmed] = useState(false)
  const [wholeSpendConfirmed, setWholeSpendConfirmed] = useState(false)
  const [wholeUnknownCostConfirmed, setWholeUnknownCostConfirmed] = useState(false)
  const [estimate, setEstimate] = useState<RenderEstimateResponse | null>(null)
  const [estimateLoading, setEstimateLoading] = useState(false)
  const [estimateError, setEstimateError] = useState('')
  const run = controller.run
  const stale = Boolean(
    run
    && controller.currentBlueprintVersionId
    && run.blueprint_version_id !== controller.currentBlueprintVersionId,
  )
  const nextAction = nextCanonicalWorkflowAction(
    run?.status || null,
    surface,
    run ? isRevisionSubmitted(run) : false,
  )
  const decisions = useMemo(() => decisionRows(run), [run])
  const shots = useMemo(() => packageShots(run), [run])
  const busy = Boolean(controller.action) || controller.polling
  const selectedShot = shots.find((shot) => shot.storyboard_shot_id === selectedShotId) ?? null
  const plannedDuration = selectedShot ? plannedDurationOf(selectedShot) : null
  const parsedDuration = durationInput.trim() ? Number(durationInput) : null
  const effectiveDuration = parsedDuration ?? plannedDuration
  const durationValid = effectiveDuration !== null
    && Number.isInteger(effectiveDuration)
    && effectiveDuration >= 2
    && effectiveDuration <= 30
  const estimateRow = estimate?.estimates.find((row) => row.storyboard_shot_id === selectedShotId) ?? null
  const estimateAvailable = Boolean(estimateRow?.estimate_available)
  const overCeiling = Boolean(
    estimate
    && estimateRow?.estimated_credits != null
    && estimateRow.estimated_credits > estimate.ceiling_credits,
  )
  const needsUnknownAck = !estimateAvailable
  const canConfirmSingle = Boolean(
    run
    && selectedShot
    && durationValid
    && spendConfirmed
    && (!needsUnknownAck || unknownCostConfirmed)
    && !overCeiling
    && !busy,
  )
  const memorySaved = Boolean(text(run?.data.identifiers.memory_record_id))
  const failure = run?.data.failures?.[run.data.failures.length - 1]
  const providerLabel = renderProvider ? (renderProviderLabel || renderProvider) : 'Approved Previs provider'

  const apply = (
    label: string,
    operation: () => Promise<CanonicalWorkflowResponse>,
  ) => void controller.perform(label, operation)

  const confirmAction = (
    prompt: string,
    label: string,
    operation: () => Promise<CanonicalWorkflowResponse>,
  ) => {
    if (window.confirm(prompt)) apply(label, operation)
  }

  const selectShot = (id: string) => {
    setSelectedShotId(id)
    setEstimate(null)
    setEstimateError('')
    setSpendConfirmed(false)
    setUnknownCostConfirmed(false)
  }

  const checkCost = () => {
    if (!run || !selectedShot) return
    setEstimateLoading(true)
    setEstimateError('')
    estimateCanonicalRenders(run.run_id, {
      storyboardShotIds: [selectedShot.storyboard_shot_id],
      durationSeconds: parsedDuration ?? undefined,
    })
      .then((res) => setEstimate(res))
      .catch((err: unknown) => setEstimateError(err instanceof Error ? err.message : 'Cost check failed'))
      .finally(() => setEstimateLoading(false))
  }

  const screeningUrl = withProductionContext('/studio/screening-room', {
    projectId,
    sceneId,
  })
  const previsUrl = withProductionContext('/studio/previs', {
    projectId,
    sceneId,
  })

  return (
    <section
      className="mx-4 mt-2 rounded-xl border border-white/10 bg-black/45 px-4 py-3 backdrop-blur"
      data-testid="canonical-workflow-panel"
      data-project-id={projectId}
      data-scene-id={sceneId}
      data-workflow-status={run?.status || 'not_started'}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Workflow size={15} className="shrink-0 text-amber-300" />
          <div className="min-w-0">
            <div className="text-[10px] font-bold uppercase tracking-[0.16em] text-zinc-200">
              Canonical Production Thread
            </div>
            <div className="truncate text-[10px] text-zinc-500">
              {sceneId || 'Select a scene'}
              {run ? ` · Blueprint ${run.blueprint_version_id}` : ''}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {run ? (
            <span className={`rounded-full border px-2 py-1 text-[9px] font-bold uppercase tracking-[0.1em] ${
              stale
                ? 'border-rose-400/40 bg-rose-500/10 text-rose-200'
                : run.status.includes('failed')
                  ? 'border-rose-400/40 bg-rose-500/10 text-rose-200'
                  : 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200'
            }`}>
              {stale ? 'Superseded source' : statusLabel(run.status)}
            </span>
          ) : null}
          <button
            type="button"
            onClick={() => void controller.refresh()}
            disabled={!run || busy}
            aria-label="Refresh production thread"
            className="rounded border border-white/10 p-1.5 text-zinc-400 hover:text-zinc-100 disabled:opacity-30"
          >
            <RefreshCcw size={13} className={controller.loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <p className="mt-2 text-[10px] text-zinc-400" data-testid="canonical-render-provider">
        New renders: {providerLabel}.
        Retries and revisions retain their original render provider.
      </p>

      <p className="mt-1 text-[10px] text-zinc-400" data-testid="canonical-previs-provider">
        Simulated previs: instant, no cost.
      </p>

      {controller.loading ? (
        <div className="mt-3 flex items-center gap-2 text-xs text-zinc-400">
          <Loader2 size={13} className="animate-spin" /> Loading durable production state…
        </div>
      ) : null}

      {controller.error ? (
        <div role="alert" className="mt-3 flex items-start gap-2 rounded-lg border border-rose-400/30 bg-rose-500/10 p-2 text-xs text-rose-100">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>{controller.error}</span>
        </div>
      ) : null}

      {stale ? (
        <div role="status" className="mt-3 rounded-lg border border-amber-400/30 bg-amber-500/10 p-2 text-xs text-amber-100">
          This thread belongs to an older approved Blueprint. It is read-only; start the current approved version before generating again.
        </div>
      ) : null}

      {!run && !controller.loading && controller.currentBlueprintVersionId && controller.availableRuns.length > 0 ? (
        <div role="status" className="mt-3 rounded-lg border border-amber-400/30 bg-amber-500/10 p-2 text-xs text-amber-100">
          {controller.availableRuns.length} prior production thread(s) remain retained for audit. None belongs to the current approved Blueprint {controller.currentBlueprintVersionId}; start a new thread to continue.
        </div>
      ) : null}

      {failure ? (
        <div className="mt-2 text-[10px] text-rose-200">
          Last failure: {text(failure.message) || text(failure.error_type) || 'Downstream work failed and remains recoverable.'}
        </div>
      ) : null}

      {!controller.loading && !stale ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {!run ? (
            <button
              type="button"
              onClick={() => apply('Starting thread', () => beginCanonicalWorkflow({
                projectId,
                sceneId,
                scriptId: resolvedSceneContext.scriptId,
                sequenceId: resolvedSceneContext.sequenceId,
                beatIds: resolvedSceneContext.beatIds,
              }))}
              disabled={busy || !projectId || !sceneId || !resolvedSceneContext.scriptId}
              className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-amber-100 disabled:opacity-40"
            >
              Start approved production thread
            </button>
          ) : null}

          {nextAction === 'generate_previs' ? (
            <button type="button" disabled={busy} onClick={() => apply('Generating Previs', () => generateCanonicalPrevis(run!.run_id))} className="btn-ghost px-3 py-2 text-[10px]">
              Generate approved Previs
            </button>
          ) : null}

          {nextAction === 'approve_previs' ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => confirmAction(
                'Approve every generated Previs artifact for this exact Blueprint version?',
                'Approving Previs',
                () => approveCanonicalPrevis(run!.run_id, workflowArtifactIds(run!, 'previs', 'previs_image_id')),
              )}
              className="btn-ghost px-3 py-2 text-[10px]"
            >
              Approve exact Previs set
            </button>
          ) : null}

          {nextAction === 'create_package' ? (
            <button type="button" disabled={busy} onClick={() => apply('Building package', () => createCanonicalProductionPackage(run!.run_id))} className="btn-ghost px-3 py-2 text-[10px]">
              Build production package
            </button>
          ) : null}

          {nextAction === 'render' ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => { setSingleShotOpen((open) => !open); setWholePackageOpen(false) }}
              className="btn-ghost px-3 py-2 text-[10px]"
              data-testid="single-shot-render-toggle"
            >
              Render one shot…
            </button>
          ) : null}

          {nextAction === 'render' ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => { setWholePackageOpen((open) => !open); setSingleShotOpen(false) }}
              className="rounded-lg border border-rose-400/40 px-3 py-2 text-[10px] font-bold uppercase text-rose-100"
              data-testid="whole-package-render-toggle"
            >
              Queue whole package…
            </button>
          ) : null}

          {nextAction === 'polling' || nextAction === 'revision_polling' ? (
            <span role="status" className="flex items-center gap-2 text-xs text-amber-200">
              <Loader2 size={13} className="animate-spin" /> Waiting on canonical render state…
            </span>
          ) : null}

          {nextAction === 'retry_render' ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => confirmAction(
                'Retry the existing paid render jobs without creating duplicates?',
                'Retrying render',
                () => renderCanonicalProductionPackage(run!.run_id, true),
              )}
              className="rounded-lg border border-rose-400/40 px-3 py-2 text-[10px] font-bold uppercase text-rose-100"
            >
              Retry existing render jobs
            </button>
          ) : null}

          {nextAction === 'sync_screening' ? (
            <button type="button" disabled={busy} onClick={() => apply('Registering Screening output', () => syncCanonicalScreening(run!.run_id))} className="btn-ghost px-3 py-2 text-[10px]">
              Register completed clips in Screening
            </button>
          ) : null}

          {surface === 'previs' && run && ['screening_ready', 'screening_approved', 'editorial_analyzed', 'editorial_decided', 'cut_updated', 'cut_approved', 'revision_pending', 'revision_completed', 'revision_failed'].includes(run.status) ? (
            <a href={screeningUrl} className="rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-emerald-100">
              Continue in Screening
            </a>
          ) : null}

          {nextAction === 'approve_screening' ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => confirmAction(
                'Approve every Screening output registered to this production thread?',
                'Approving Screening output',
                () => approveCanonicalScreening(run!.run_id, workflowIdentifierList(run!, 'screening_output_ids')),
              )}
              className="btn-ghost px-3 py-2 text-[10px]"
            >
              Approve exact Screening set
            </button>
          ) : null}

          {nextAction === 'analyze_editorial' ? (
            <button type="button" disabled={busy} onClick={() => apply('Reading cut', () => analyzeCanonicalEditorial(run!.run_id))} className="btn-ghost px-3 py-2 text-[10px]">
              Read approved cut
            </button>
          ) : null}

          {nextAction === 'update_cut' ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => confirmAction('Create a new Film Cut version from the confirmed decision?', 'Creating Film Cut', () => updateCanonicalFilmCut(run!.run_id))}
              className="btn-ghost px-3 py-2 text-[10px]"
            >
              Create new Film Cut version
            </button>
          ) : null}

          {nextAction === 'approve_cut' ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => confirmAction('Approve this exact Film Cut version?', 'Approving Film Cut', () => approveCanonicalFilmCut(run!.run_id))}
              className="btn-ghost px-3 py-2 text-[10px]"
            >
              Approve current Film Cut
            </button>
          ) : null}

          {nextAction === 'render_revision' || nextAction === 'retry_revision' ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => confirmAction(
                nextAction === 'retry_revision' ? 'Retry this existing Revision render?' : 'Render the confirmed Revision?',
                nextAction === 'retry_revision' ? 'Retrying Revision' : 'Rendering Revision',
                () => renderCanonicalRevision(run!.run_id),
              )}
              className="btn-ghost px-3 py-2 text-[10px]"
            >
              {nextAction === 'retry_revision' ? 'Retry Revision render' : 'Render confirmed Revision'}
            </button>
          ) : null}

          {surface === 'screening' && run ? (
            <a href={previsUrl} className="px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-zinc-400 underline-offset-2 hover:text-zinc-100 hover:underline">
              Return to Previs context
            </a>
          ) : null}
        </div>
      ) : null}

      {nextAction === 'render' && singleShotOpen && !stale ? (
        <div className="mt-3 rounded-lg border border-white/10 bg-white/5 p-3" data-testid="single-shot-render-dialog">
          <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-zinc-200">
            Render one shot with {providerLabel}
          </div>
          <p className="mt-1 text-[10px] text-zinc-500">
            Nothing is preselected. Pick exactly one shot; confirming spends Runway credits for 1 submission.
          </p>
          <div className="mt-2 space-y-1" role="radiogroup" aria-label="Package shots">
            {shots.map((shot) => (
              <label key={shot.storyboard_shot_id} className="flex items-center gap-2 text-xs text-zinc-200">
                <input
                  type="radio"
                  name="single-shot-choice"
                  value={shot.storyboard_shot_id}
                  checked={selectedShotId === shot.storyboard_shot_id}
                  onChange={() => selectShot(shot.storyboard_shot_id)}
                />
                <span>{shot.shot_id || shot.storyboard_shot_id}</span>
                <span className="text-[10px] text-zinc-500">{shot.storyboard_shot_id}</span>
              </label>
            ))}
            {shots.length === 0 ? (
              <p className="text-[10px] text-amber-200">No package shots are available yet — build the production package first.</p>
            ) : null}
          </div>

          {selectedShot ? (
            <div className="mt-3 space-y-2 border-t border-white/10 pt-3" data-testid="single-shot-confirm">
              <div className="text-xs text-zinc-200">
                Shot {selectedShot.shot_id || selectedShot.storyboard_shot_id} · 1 Runway submission
              </div>
              <label className="block text-[10px] text-zinc-400">
                Duration in seconds (planned: {plannedDuration ?? 'unknown'}; Router accepts 2–30)
                <input
                  value={durationInput}
                  onChange={(event) => { setDurationInput(event.target.value); setEstimate(null) }}
                  placeholder={plannedDuration !== null ? String(plannedDuration) : 'e.g. 5'}
                  inputMode="numeric"
                  aria-label="Render duration in seconds"
                  className="cyber-input mt-1 w-24 rounded p-1.5 text-xs"
                />
              </label>
              {!durationValid ? (
                <p className="text-[10px] text-rose-200">Duration must be a whole number of seconds between 2 and 30.</p>
              ) : null}
              <div>
                <div className="text-[10px] font-bold uppercase tracking-[0.1em] text-zinc-500">
                  Exact prompt text that will be sent (first 600 characters)
                </div>
                <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-black/40 p-2 text-[10px] leading-relaxed text-zinc-300">
                  {selectedShot.prompt.slice(0, 600) || '(empty prompt — submission will fail closed)'}
                </pre>
                <div className="mt-1 text-[10px] text-zinc-500">
                  ALL-CAPS names in prompt: {capsNames(selectedShot.prompt).join(', ') || 'none'}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={busy || estimateLoading || !durationValid}
                  onClick={checkCost}
                  className="btn-ghost px-3 py-2 text-[10px]"
                  data-testid="single-shot-check-cost"
                  title="Calls Runway with dryRun:true for this shot only. Creates no task; prior reports observed no billing change, unverified on this account."
                >
                  {estimateLoading ? 'Checking cost…' : 'Check cost (may contact Runway)'}
                </button>
                {estimateRow ? (
                  <span className="text-[10px] text-zinc-300" data-testid="single-shot-estimate">
                    {estimateAvailable
                      ? `Estimate: ${estimateRow.estimated_credits} credits${estimateRow.resolved_model ? ` · ${estimateRow.resolved_model}` : ''} · ceiling ${estimate?.ceiling_credits} (${estimate?.ceiling_env_var})`
                      : `Estimate unavailable · ceiling ${estimate?.ceiling_credits} (${estimate?.ceiling_env_var})`}
                  </span>
                ) : (
                  <span className="text-[10px] text-zinc-500">
                    Ceiling 300 credits (RUNWAY_RENDER_MAX_CREDITS) until checked.
                  </span>
                )}
              </div>
              {estimateError ? <p className="text-[10px] text-rose-200">{estimateError}</p> : null}
              {overCeiling ? (
                <p className="text-[10px] text-rose-200">
                  The estimate exceeds the ceiling — this shot cannot be submitted at the current ceiling.
                </p>
              ) : null}
              <label className="flex items-start gap-2 text-xs text-zinc-200">
                <input
                  type="checkbox"
                  checked={spendConfirmed}
                  onChange={(event) => setSpendConfirmed(event.target.checked)}
                  className="mt-0.5"
                />
                I understand this spends Runway credits
              </label>
              {needsUnknownAck ? (
                <label className="flex items-start gap-2 text-xs text-zinc-200">
                  <input
                    type="checkbox"
                    checked={unknownCostConfirmed}
                    onChange={(event) => setUnknownCostConfirmed(event.target.checked)}
                    className="mt-0.5"
                  />
                  No cost estimate is available — proceed anyway and accept the unknown cost
                </label>
              ) : null}
              <button
                type="button"
                disabled={!canConfirmSingle}
                onClick={() => run && selectedShot && effectiveDuration !== null && apply(
                  'Queuing single-shot render',
                  () => renderCanonicalShots(run.run_id, {
                    provider: renderProvider,
                    storyboardShotIds: [selectedShot.storyboard_shot_id],
                    durationSeconds: effectiveDuration,
                    acknowledgeUnknownCost: unknownCostConfirmed,
                  }),
                )}
                className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-amber-100 disabled:opacity-40"
                data-testid="single-shot-confirm-button"
              >
                Confirm: render this one shot
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {nextAction === 'render' && wholePackageOpen && !stale ? (
        <div className="mt-3 rounded-lg border border-rose-400/30 bg-rose-500/5 p-3" data-testid="whole-package-render-dialog">
          <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-rose-100">
            Queue the whole package ({shots.length} shots, {shots.length} Runway submissions)
          </div>
          <p className="mt-1 text-[10px] text-zinc-400">
            This submits every package shot and needs a separate owner decision. No per-shot estimate is shown here.
          </p>
          <label className="mt-2 flex items-start gap-2 text-xs text-zinc-200">
            <input
              type="checkbox"
              checked={wholeSpendConfirmed}
              onChange={(event) => setWholeSpendConfirmed(event.target.checked)}
              className="mt-0.5"
            />
            I understand this spends Runway credits for all {shots.length} shots
          </label>
          <label className="mt-1 flex items-start gap-2 text-xs text-zinc-200">
            <input
              type="checkbox"
              checked={wholeUnknownCostConfirmed}
              onChange={(event) => setWholeUnknownCostConfirmed(event.target.checked)}
              className="mt-0.5"
            />
            No cost estimate is shown — proceed anyway and accept the unknown cost
          </label>
          <button
            type="button"
            disabled={!run || busy || !wholeSpendConfirmed || !wholeUnknownCostConfirmed}
            onClick={() => run && apply(
              'Queuing whole package',
              () => renderCanonicalShots(run.run_id, {
                provider: renderProvider,
                allowFullPackage: true,
                acknowledgeUnknownCost: wholeUnknownCostConfirmed,
              }),
            )}
            className="mt-2 rounded-lg border border-rose-400/40 px-3 py-2 text-[10px] font-bold uppercase text-rose-100 disabled:opacity-40"
            data-testid="whole-package-confirm"
          >
            Confirm: queue all {shots.length} shots
          </button>
        </div>
      ) : null}

      {nextAction === 'choose_editorial_decision' && decisions.length > 0 ? (
        <div className="mt-3 space-y-2" data-testid="canonical-editorial-decisions">
          <div className="text-[9px] font-bold uppercase tracking-[0.12em] text-zinc-500">Proposed Editorial changes</div>
          {decisions.map((decision) => (
            <button
              key={text(decision.decision_id)}
              type="button"
              disabled={busy}
              onClick={() => confirmAction(
                `Apply this proposed Editorial change: ${text(decision.recommendation) || 'selected change'}?`,
                'Applying Editorial decision',
                () => applyCanonicalEditorialDecision(
                  run!.run_id,
                  text(run!.data.identifiers.editorial_analysis_id),
                  text(decision.decision_id),
                ),
              )}
              className="block w-full rounded-lg border border-white/10 bg-white/5 p-2 text-left hover:bg-white/10 disabled:opacity-40"
            >
              <span className="block text-xs text-zinc-200">{text(decision.recommendation) || 'Editorial change'}</span>
              <span className="mt-1 block text-[10px] leading-relaxed text-zinc-500">{text(decision.rationale)}</span>
            </button>
          ))}
        </div>
      ) : null}

      {nextAction === 'create_revision' ? (
        <div className="mt-3 grid gap-2 md:grid-cols-3" data-testid="canonical-revision-form">
          <textarea value={revisionPrompt} onChange={(event) => setRevisionPrompt(event.target.value)} placeholder="Describe the exact visual or timing change" className="cyber-input rounded p-2 text-xs" />
          <textarea value={revisionReason} onChange={(event) => setRevisionReason(event.target.value)} placeholder="Why this change protects the cut" className="cyber-input rounded p-2 text-xs" />
          <div className="space-y-2">
            <input value={changedFields} onChange={(event) => setChangedFields(event.target.value)} aria-label="Changed fields" className="cyber-input w-full rounded p-2 text-xs" />
            <button
              type="button"
              disabled={busy || !revisionPrompt.trim() || !revisionReason.trim()}
              onClick={() => confirmAction(
                'Create a Revision from the approved cut and preserve all unchanged continuity?',
                'Creating Revision',
                () => createCanonicalRevision(run!.run_id, {
                  originalJobId: workflowIdentifierList(run!, 'render_job_ids')[0] || '',
                  revisionPrompt,
                  revisionReason,
                  changedFields: changedFields.split(',').map((value) => value.trim()).filter(Boolean),
                }),
              )}
              className="w-full rounded border border-amber-400/40 px-3 py-2 text-[10px] font-bold uppercase text-amber-100 disabled:opacity-40"
            >
              Create confirmed Revision
            </button>
          </div>
        </div>
      ) : null}

      {run?.status === 'revision_completed' ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-emerald-400/25 bg-emerald-500/10 p-2 text-xs text-emerald-100">
          <CheckCircle2 size={14} /> Revision complete and returned to Screening review.
          {!memorySaved ? (
            <>
              <input value={memorySummary} onChange={(event) => setMemorySummary(event.target.value)} placeholder="Optional approved memory note" className="cyber-input min-w-[220px] flex-1 rounded p-1.5 text-xs" />
              <button
                type="button"
                disabled={busy}
                onClick={() => confirmAction('Save this approved output to editable project memory?', 'Saving approved memory', () => saveCanonicalMemory(run.run_id, memorySummary))}
                className="rounded border border-emerald-400/40 px-2 py-1 text-[10px] font-bold uppercase"
              >
                Save approved memory
              </button>
            </>
          ) : (
            <span className="font-semibold">Approved memory saved explicitly.</span>
          )}
        </div>
      ) : null}

      {!run && !controller.loading && !resolvedSceneContext.scriptId ? (
        <p className="mt-2 text-[10px] text-amber-200">Save this film’s script in Write before starting a production thread.</p>
      ) : null}
      {!run && !controller.loading && resolvedSceneContext.scriptId && !controller.currentBlueprintVersionId ? (
        <p className="mt-2 text-[10px] text-amber-200">Build and approve this scene’s Storyboard Blueprint, then start its production thread.</p>
      ) : null}

      {run ? (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[9px] uppercase tracking-[0.08em] text-zinc-600">
          <span>Run {run.run_id}</span>
          <span>Approved source</span>
          <span>{controller.transitions.length} persisted transitions</span>
          {controller.availableRuns.length > 1 ? <span>{controller.availableRuns.length - 1} prior version(s) retained</span> : null}
          {controller.action ? <span>{controller.action}…</span> : null}
        </div>
      ) : null}
    </section>
  )
}
