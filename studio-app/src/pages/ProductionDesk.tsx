import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  Camera,
  CheckCircle2,
  CircleHelp,
  Clock3,
  Film,
  Layers,
  Loader2,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react'
import type { ReactNode } from 'react'
import StudioShell from '../components/StudioShell'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import { RoomBackdrop } from '../components/RoomCinematicChrome'
import { getProceduralRoomStyle } from '../lib/proceduralBackdrops'
import RenderSparkline from '../components/RenderSparkline'
import CreditRadialGauge from '../components/CreditRadialGauge'
import LatencyVectorSparkline from '../components/LatencyVectorSparkline'
import ProductionSoundstageOverlay from '../components/ProductionSoundstageOverlay'
import RouterNormalizationBadge from '../components/RouterNormalizationBadge'
import { JobInspectorDrawer } from '../components/ProductionExecutionBay'
import { getRouterNormalizationWarnings, isRouterPayloadNormalized } from '../lib/routerNormalization'
import {
  EXECUTION_LOG_FILTERS,
  EXECUTION_LOG_FILTER_LABEL,
  creditTelemetry,
  durationTelemetry,
  executionFilterCounts,
  executionLogRows,
  filterExecutionLog,
  queueCounts,
  type ExecutionLogFilter,
} from '../lib/renderTelemetry'
import { useProjectRouteContext } from '../hooks/useProjectRouteContext'
import { useStudio } from '../context/StudioContext'
import { getTakeChoices, type SceneTakeChoices } from '../lib/takeSelectionApi'
import { getShotReferenceConfirmation, listReferenceAssets, recordShotReferenceConfirmation, resolveShotReferenceBinding, type ReferenceAsset, type ShotReferenceBinding, type ShotReferenceConfirmation } from '../lib/visualTrainingApi'
import { friendlyRefusalError } from '../lib/sceneMintRefusals'
import { buildDeskConfirmedBindingState } from '../lib/confirmedBindingHandoff'
import {
  getAssemblyStatus,
  getCurrentFilmCut,
  getLatestProductionAcceptanceSummary,
  getProductionQueueSummary,
  getScreeningManifest,
  listFinalShortFilmPackagesForProject,
  listRenderJobs,
  listScenes,
  listStoryboardBlueprints,
  type AssemblyStatusResponse,
  type FilmCutVersion,
  type FinalShortFilmPackage,
  type ProductionAcceptanceSummary,
  type ProductionQueueSummary,
  type RenderJob,
  type Scene,
  type ScreeningManifest,
  type StoryboardBlueprintSummary,
} from '../lib/studioApi'
import { normalizeJobStatus } from '../lib/jobStatus'

type LoadState<T> = { status: 'loading' } | { status: 'unavailable'; message: string } | { status: 'loaded'; value: T }

function empty<T>(): LoadState<T> { return { status: 'loading' } }

function StateLine({ label, state }: { label: string; state: 'verified' | 'blocked' | 'stale' | 'unavailable' | 'unverified'; }) {
  const style = state === 'verified' ? 'text-emerald-200' : state === 'blocked' || state === 'stale' ? 'text-amber-200' : 'text-zinc-400'
  return <span className={`inline-flex items-center gap-1.5 text-xs ${style}`}><span aria-hidden="true">{state === 'verified' ? '●' : state === 'blocked' || state === 'stale' ? '▲' : '○'}</span>{label}</span>
}

/** Take choices are one request per scene; cap the burst and say so when capped. */
const TAKE_LOOKUP_LIMIT = 24

type SceneRowState = 'draft' | 'rendering' | 'needs_review' | 'blocked' | 'ready' | 'composed'

const SCENE_STATE_LABEL: Record<SceneRowState, string> = {
  draft: 'Draft',
  rendering: 'Rendering',
  needs_review: 'Needs review',
  blocked: 'Blocked',
  ready: 'Ready',
  composed: 'Composed',
}

type AssemblyCellState = 'unavailable' | 'unknown' | 'outside_cut' | 'needs_assembly' | 'current'

const ASSEMBLY_LABEL: Record<AssemblyCellState, string> = {
  unavailable: 'Unavailable',
  unknown: 'Not evaluated',
  outside_cut: 'Not in cut',
  needs_assembly: 'Assembly needed',
  current: 'Current composition',
}

type SceneRow = {
  scene: Scene
  shotsTotal: number
  shotsComplete: number
  shotsFailed: number
  shotsActive: number
  shotsNeedingReview: number
  mediaReady: number
  storyboard: StoryboardBlueprintSummary | null
  takesSelected: number | null
  takesTotal: number | null
  assembly: AssemblyCellState
  state: SceneRowState
  blockers: string[]
}

function deriveSceneRow(input: {
  scene: Scene
  jobs: RenderJob[]
  blueprint?: StoryboardBlueprintSummary | null
  cut?: FilmCutVersion | null
  delivery?: AssemblyStatusResponse | null
  takeChoices?: SceneTakeChoices | null
  takesAvailable: boolean
}): SceneRow {
  const { scene, jobs, blueprint, cut, delivery, takeChoices, takesAvailable } = input
  const sceneJobs = jobs.filter((job) => (job.shot_id || '').split('_shot_')[0] === scene.scene_id)
  const shotIds = new Set(sceneJobs.map((job) => job.shot_id))
  const isComplete = (job: RenderJob) =>
    normalizeJobStatus(job.status) === 'complete' && Boolean(job.output_payload?.asset_url || job.output_url)
  const shotsComplete = new Set(sceneJobs.filter(isComplete).map((job) => job.shot_id)).size
  const shotsFailed = new Set(sceneJobs.filter((job) => normalizeJobStatus(job.status) === 'failed').map((job) => job.shot_id)).size
  const shotsActive = new Set(sceneJobs.filter((job) => ['pending', 'queued', 'rendering'].includes(normalizeJobStatus(job.status))).map((job) => job.shot_id)).size
  const shotsNeedingReview = new Set(sceneJobs.filter((job) => normalizeJobStatus(job.status) === 'needs_review').map((job) => job.shot_id)).size
  const mediaReady = sceneJobs.filter(isComplete).length
  const shotsTotal = shotIds.size

  let assembly: AssemblyCellState = 'unknown'
  if (!delivery) {
    assembly = 'unavailable'
  } else if (cut && !(cut.scene_order || []).includes(scene.scene_id)) {
    assembly = 'outside_cut'
  } else if (cut && cut.status === 'approved') {
    assembly = (delivery.scenes_needing_assembly || []).includes(scene.scene_id) ? 'needs_assembly' : 'current'
  }

  const choices = takeChoices?.choices || []
  const takesSelected = takesAvailable && takeChoices ? choices.filter((choice) => Boolean(choice.job_id)).length : null
  const takesTotal = takesAvailable && takeChoices ? choices.length : null

  const blockers: string[] = []
  if (shotsFailed > 0) blockers.push(`${shotsFailed} shot${shotsFailed === 1 ? '' : 's'} failed`)
  if (shotsNeedingReview > 0) blockers.push(`${shotsNeedingReview} shot${shotsNeedingReview === 1 ? '' : 's'} waiting on review`)
  if (shotsActive > 0) blockers.push(`${shotsActive} shot${shotsActive === 1 ? '' : 's'} still rendering`)
  if (shotsTotal > 0 && shotsComplete < shotsTotal) blockers.push(`${shotsTotal - shotsComplete} shot${shotsTotal - shotsComplete === 1 ? '' : 's'} without a saved media URL`)
  if (assembly === 'needs_assembly') blockers.push('Scene composition is missing or out of date')

  let state: SceneRowState = 'ready'
  if (shotsTotal === 0) state = 'draft'
  else if (shotsFailed > 0 || (shotsTotal > 0 && shotsComplete < shotsTotal)) state = 'blocked'
  else if (shotsNeedingReview > 0) state = 'needs_review'
  else if (shotsActive > 0) state = 'rendering'
  else if (assembly === 'current') state = 'composed'

  return {
    scene,
    shotsTotal,
    shotsComplete,
    shotsFailed,
    shotsActive,
    shotsNeedingReview,
    mediaReady,
    storyboard: blueprint || null,
    takesSelected,
    takesTotal,
    assembly,
    state,
    blockers,
  }
}

type NextAction = {
  id: string
  severity: 'blocker' | 'next' | 'info'
  label: string
  detail: string
  to?: string
  toLabel?: string
}

function deriveNextActions(input: {
  projectId: string
  scenes: LoadState<Scene[]>
  jobs: LoadState<RenderJob[]>
  cut: LoadState<FilmCutVersion>
  delivery: LoadState<AssemblyStatusResponse>
  acceptance: LoadState<ProductionAcceptanceSummary>
  screening: LoadState<ScreeningManifest>
  queue: LoadState<ProductionQueueSummary>
}): NextAction[] {
  const { projectId, scenes, jobs, cut, delivery, acceptance, screening, queue } = input
  const q = encodeURIComponent(projectId || '')
  const board = `/studio/production-board?project_id=${q}`
  const theater = `/studio/screening-room?project_id=${q}`
  const page = `/studio/writers-room?project_id=${q}`
  const actions: NextAction[] = []

  if (scenes.status === 'unavailable') {
    actions.push({ id: 'scenes-unavailable', severity: 'blocker', label: 'Scene list unavailable', detail: scenes.message })
  } else if (scenes.status === 'loaded' && scenes.value.length === 0) {
    actions.push({ id: 'no-scenes', severity: 'blocker', label: 'No scenes are saved for this project', detail: 'Nothing can render, assemble, or deliver until scenes exist.', to: page, toLabel: 'Open The Page' })
  }

  if (jobs.status === 'unavailable') {
    actions.push({ id: 'jobs-unavailable', severity: 'blocker', label: 'Render queue unavailable', detail: jobs.message })
  } else if (jobs.status === 'loaded' && scenes.status === 'loaded') {
    const sceneIds = new Set(scenes.value.map((scene) => scene.scene_id))
    const usable = (job: RenderJob) => Boolean(job.output_payload?.asset_url || job.output_url)
    const failed = jobs.value.filter((job) => normalizeJobStatus(job.status) === 'failed').length
    const active = jobs.value.filter((job) => ['pending', 'queued', 'rendering'].includes(normalizeJobStatus(job.status))).length
    const covered = new Set(
      jobs.value
        .filter((job) => normalizeJobStatus(job.status) === 'complete' && usable(job))
        .map((job) => (job.shot_id || '').split('_shot_')[0]),
    )
    const uncovered = scenes.value.filter((scene) => !covered.has(scene.scene_id)).length
    if (failed > 0) actions.push({ id: 'failed-jobs', severity: 'blocker', label: `${failed} render job${failed === 1 ? '' : 's'} failed`, detail: 'Failed jobs hold their scenes out of review until they are retried.', to: board, toLabel: 'Inspect the queue' })
    if (scenes.value.length > 0 && uncovered > 0) actions.push({ id: 'uncovered-scenes', severity: 'next', label: `${uncovered} of ${scenes.value.length} scene${scenes.value.length === 1 ? '' : 's'} still waiting for a completed shot output`, detail: 'Every scene needs complete, project-owned media before delivery.', to: board, toLabel: 'Open scene board' })
    if (failed === 0 && active > 0 && sceneIds.size > 0) actions.push({ id: 'active-jobs', severity: 'info', label: `${active} render job${active === 1 ? '' : 's'} in progress`, detail: 'Scene coverage can change when they finish.', to: board, toLabel: 'Inspect the queue' })
  }

  if (cut.status === 'unavailable') {
    actions.push({ id: 'cut-unavailable', severity: 'info', label: 'Film Cut status unavailable', detail: cut.message })
  } else if (cut.status === 'loaded' && cut.value.status !== 'approved') {
    actions.push({ id: 'cut-not-approved', severity: 'next', label: 'Approve the current Film Cut', detail: 'Full-film delivery refuses to assemble an unapproved cut.', to: theater, toLabel: 'Open The Theater' })
  }

  if (delivery.status === 'loaded' && delivery.value.film_outdated) {
    actions.push({ id: 'delivery-stale', severity: 'blocker', label: 'Saved delivery is stale against the current cut', detail: 'The stored film no longer matches scene media or the approved cut order.', to: theater, toLabel: 'Rebuild delivery' })
  } else if (delivery.status === 'loaded' && !delivery.value.film_assembled && cut.status === 'loaded' && cut.value.status === 'approved') {
    actions.push({ id: 'assemble', severity: 'next', label: 'Assemble the full film', detail: 'The cut is approved and scene compositions are the remaining input.', to: theater, toLabel: 'Open The Theater' })
  }

  if (acceptance.status === 'unavailable') {
    actions.push({ id: 'acceptance-unavailable', severity: 'info', label: 'Acceptance record unavailable', detail: acceptance.message })
  } else if (acceptance.status === 'loaded') {
    const summary = acceptance.value
    if (summary.stale) {
      actions.push({ id: 'acceptance-stale', severity: 'blocker', label: 'Acceptance evidence is stale', detail: summary.recommended_action || 'The accepted output changed after acceptance ran. Run acceptance again.' })
    } else if (summary.disposition === 'blocked') {
      actions.push({ id: 'acceptance-blocked', severity: 'blocker', label: 'Production Integrity reports a blocked package', detail: summary.recommended_action || 'Resolve the reported checks before creator approval.' })
    } else if (summary.disposition === 'ready_for_creator_approval') {
      actions.push({ id: 'creator-approval', severity: 'next', label: 'Creator approval is required for this package', detail: summary.recommended_action || 'Acceptance passed package checks and is waiting on your decision.', to: theater, toLabel: 'Review in Screening' })
    } else if (delivery.status === 'loaded' && delivery.value.film_assembled) {
      actions.push({ id: 'run-acceptance', severity: 'next', label: 'Run Production Integrity acceptance for the assembled film', detail: summary.recommended_action || 'Screening cannot select a final without package-scoped acceptance.' })
    }
  }

  if (screening.status === 'loaded' && !screening.value.current_final_output) {
    actions.push({ id: 'no-current-final', severity: 'info', label: 'Screening has no selected current final', detail: 'A manifest entry alone does not prove creator acceptance.', to: theater, toLabel: 'Open Screening Room' })
  } else if (screening.status === 'loaded' && screening.value.current_final_output) {
    actions.push({ id: 'current-final', severity: 'info', label: 'Screening is pointing at an accepted current final', detail: 'Playback and approval stay scoped to that exact output.' })
  }

  if (queue.status === 'loaded' && queue.value.blocked_reasons.length > 0) {
    const reasons = queue.value.blocked_reasons
    actions.push({ id: 'queue-blocked', severity: 'blocker', label: `Production queue reports ${reasons.length} blockage${reasons.length === 1 ? '' : 's'}`, detail: reasons.slice(0, 2).join(' · '), to: board, toLabel: 'Open queue detail' })
  }

  const rank = { blocker: 0, next: 1, info: 2 }
  const ordered = [...actions].sort((a, b) => rank[a.severity] - rank[b.severity])
  const visible = ordered.slice(0, 6)
  if (visible.length === 0) {
    visible.push({ id: 'clear', severity: 'info', label: 'Nothing is waiting on a decision from the saved evidence', detail: 'Refresh evidence after the next render, delivery, or acceptance run.' })
  }
  return visible
}

export default function ProductionDesk() {
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const { activeProject } = useStudio()
  const { projectId, projectError } = useProjectRouteContext(queryProjectId)
  const scope = useRef(projectId)
  const [scenes, setScenes] = useState<LoadState<Scene[]>>(empty())
  const [jobs, setJobs] = useState<LoadState<RenderJob[]>>(empty())
  const [cut, setCut] = useState<LoadState<FilmCutVersion>>(empty())
  const [packages, setPackages] = useState<LoadState<FinalShortFilmPackage[]>>(empty())
  const [delivery, setDelivery] = useState<LoadState<AssemblyStatusResponse>>(empty())
  const [screening, setScreening] = useState<LoadState<ScreeningManifest>>(empty())
  const [acceptance, setAcceptance] = useState<LoadState<ProductionAcceptanceSummary>>(empty())
  const [queue, setQueue] = useState<LoadState<ProductionQueueSummary>>(empty())
  const [blueprints, setBlueprints] = useState<LoadState<StoryboardBlueprintSummary[]>>(empty())
  const [references, setReferences] = useState<LoadState<ReferenceAsset[]>>(empty())
  const [takes, setTakes] = useState<LoadState<{ byScene: Record<string, SceneTakeChoices>; partial: boolean }>>(empty())
  const [refreshing, setRefreshing] = useState(false)
  const [logFilter, setLogFilter] = useState<ExecutionLogFilter>('all')
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)

  const loadTakes = useCallback(async (project: string, sceneIds: string[]) => {
    if (sceneIds.length === 0) return { byScene: {} as Record<string, SceneTakeChoices>, partial: false }
    const slice = sceneIds.slice(0, TAKE_LOOKUP_LIMIT)
    const rows = await Promise.all(slice.map(async (sceneId) => {
      try {
        return { sceneId, choices: await getTakeChoices(project, sceneId) }
      } catch {
        return { sceneId, choices: null }
      }
    }))
    const failures = rows.filter((row) => row.choices === null)
    if (failures.length > 0) {
      throw new Error(`Take choices unavailable for ${failures.length} scene${failures.length === 1 ? '' : 's'}.`)
    }
    const byScene: Record<string, SceneTakeChoices> = {}
    for (const row of rows) {
      if (row.choices) byScene[row.sceneId] = row.choices
    }
    return { byScene, partial: sceneIds.length > slice.length }
  }, [])

  const load = useCallback(async (showSpinner = false) => {
    if (!projectId) return
    const requestedProjectId = projectId
    scope.current = projectId
    if (showSpinner) setRefreshing(true)
    const guarded = <T,>(promise: Promise<T>, set: (state: LoadState<T>) => void, message: string): Promise<T | null> =>
      promise.then((value) => { if (scope.current === requestedProjectId) set({ status: 'loaded', value }); return value })
        .catch((error: unknown) => {
          if (scope.current === requestedProjectId) set({ status: 'unavailable', message: error instanceof Error ? error.message : message })
          return null
        })

    const sceneList = await guarded(
      listScenes(projectId).then((result) => {
        if (result.error) throw new Error(result.error)
        return result.scenes
      }),
      setScenes,
      'Scene list unavailable',
    )
    const sceneIds = (sceneList || []).map((scene) => scene.scene_id)

    await Promise.all([
      guarded(listRenderJobs(projectId), setJobs, 'Render queue unavailable'),
      guarded(getCurrentFilmCut(projectId).then((result) => result.film_cut), setCut, 'Film Cut unavailable'),
      guarded(listFinalShortFilmPackagesForProject(projectId).then((result) => result.packages), setPackages, 'Delivery records unavailable'),
      guarded(getAssemblyStatus(projectId), setDelivery, 'Delivery status unavailable'),
      guarded(getScreeningManifest(projectId, false), setScreening, 'Screening registration unavailable'),
      guarded(getLatestProductionAcceptanceSummary(projectId).then((result) => result.summary), setAcceptance, 'Acceptance status unavailable'),
      guarded(getProductionQueueSummary(projectId), setQueue, 'Production queue unavailable'),
      guarded(listStoryboardBlueprints(projectId), setBlueprints, 'Shot list unavailable'),
      guarded(listReferenceAssets(projectId).then((result) => result.reference_assets || []), setReferences, 'Reference assets unavailable'),
      guarded(loadTakes(projectId, sceneIds), setTakes, 'Take choices unavailable'),
    ])
    if (scope.current === requestedProjectId && showSpinner) setRefreshing(false)
  }, [projectId, loadTakes])

  useEffect(() => {
    setScenes(empty()); setJobs(empty()); setCut(empty()); setPackages(empty())
    setDelivery(empty()); setScreening(empty()); setAcceptance(empty())
    setQueue(empty()); setBlueprints(empty()); setReferences(empty()); setTakes(empty())
    setLogFilter('all')
    setSelectedJobId(null)
    void load()
  }, [load])

  const loadedScenes = useMemo(() => scenes.status === 'loaded' ? scenes.value : [], [scenes])
  const loadedJobs = useMemo(() => jobs.status === 'loaded' ? jobs.value : [], [jobs])
  const completeSceneIds = useMemo(() => new Set(loadedJobs.filter((job) => normalizeJobStatus(job.status) === 'complete' && Boolean(job.output_payload?.asset_url || job.output_url)).map((job) => job.shot_id?.split('_shot_')[0] || job.shot_id)), [loadedJobs])
  const failedCount = loadedJobs.filter((job) => normalizeJobStatus(job.status) === 'failed').length
  const activeCount = loadedJobs.filter((job) => ['pending', 'queued', 'rendering'].includes(normalizeJobStatus(job.status))).length
  const packageRows = packages.status === 'loaded' ? packages.value : []
  const latestPackage = packageRows[0]
  const accepted = acceptance.status === 'loaded' && acceptance.value.disposition === 'ready_for_creator_approval' && !acceptance.value.stale
  const hasVerifiedFinal = screening.status === 'loaded' && screening.value.current_final_output?.approved === true && acceptance.status === 'loaded' && acceptance.value.package_id === screening.value.current_final_output?.source_id && accepted
  const cutStatus = cut.status === 'loaded' ? cut.value.status : 'unavailable'
  const sceneBlockers = loadedScenes.filter((scene) => !completeSceneIds.has(scene.scene_id))

  const sceneRows = useMemo(() => {
    if (scenes.status !== 'loaded') return []
    const deliveryValue = delivery.status === 'loaded' ? delivery.value : null
    const cutValue = cut.status === 'loaded' ? cut.value : null
    const blueprintRows = blueprints.status === 'loaded' ? blueprints.value : []
    const takesAvailable = takes.status === 'loaded'
    return loadedScenes.map((scene) => deriveSceneRow({
      scene,
      jobs: loadedJobs,
      blueprint: blueprintRows.find((row) => row.scene_id === scene.scene_id) || null,
      cut: cutValue,
      delivery: deliveryValue,
      takeChoices: takesAvailable ? takes.value.byScene[scene.scene_id] || null : null,
      takesAvailable,
    }))
  }, [scenes, loadedScenes, loadedJobs, delivery, cut, blueprints, takes])

  const nextActions = useMemo(() => deriveNextActions({
    projectId,
    scenes,
    jobs,
    cut,
    delivery,
    acceptance,
    screening,
    queue,
  }), [projectId, scenes, jobs, cut, delivery, acceptance, screening, queue])

  const [shotInput, setShotInput] = useState('')
  const [binding, setBinding] = useState<ShotReferenceBinding | null>(null)
  const [bindingError, setBindingError] = useState('')
  const [resolving, setResolving] = useState(false)
  const [confirmed, setConfirmed] = useState<{ shot_id: string; digest: string } | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [confirmError, setConfirmError] = useState('')
  // Durable server-side confirmation record (R4.2). Recovered read-only on
  // every resolution so a confirmation survives reloads and navigation;
  // written only by the explicit Confirm action below. Null means no record
  // was recovered — never a confirmation.
  const [serverConfirmation, setServerConfirmation] = useState<ShotReferenceConfirmation | null>(null)

  useEffect(() => {
    setShotInput('')
    setBinding(null)
    setBindingError('')
    setConfirmed(null)
    setConfirmError('')
    setServerConfirmation(null)
  }, [projectId])

  async function resolveBinding() {
    const shotId = shotInput.trim()
    if (!projectId || !shotId || resolving) return
    setResolving(true)
    setBindingError('')
    setBinding(null)
    setServerConfirmation(null)
    try {
      setBinding(await resolveShotReferenceBinding(projectId, shotId))
    } catch (error: unknown) {
      setBindingError(friendlyRefusalError(error, 'Reference resolution failed.'))
    } finally {
      setResolving(false)
    }
    // Read-only recovery of the durable record for this exact project and
    // shot. A lookup failure leaves no recovered state — never a
    // confirmation — and never disturbs the fresh resolution above.
    try {
      setServerConfirmation(await getShotReferenceConfirmation(projectId, shotId))
    } catch {
      setServerConfirmation(null)
    }
  }

  async function confirmBinding() {
    if (!binding || resolving || confirming) return
    setConfirming(true)
    setConfirmError('')
    try {
      // The backend re-verifies the digest against the freshly resolved
      // binding and persists the server-resolved record only on a match.
      const recorded = await recordShotReferenceConfirmation(projectId || '', binding.shot_id, binding.binding_digest)
      setConfirmed({ shot_id: binding.shot_id, digest: binding.binding_digest })
      setServerConfirmation(recorded)
    } catch (error: unknown) {
      // Fail-closed display: a confirmation that could not be saved durably
      // is not shown as confirmed anywhere.
      setConfirmError(friendlyRefusalError(error, 'Confirmation could not be saved.'))
    } finally {
      setConfirming(false)
    }
  }

  const confirmedStale = confirmed !== null && binding !== null
    && (confirmed.shot_id !== binding.shot_id || confirmed.digest !== binding.binding_digest)
  const confirmedCurrent = confirmed !== null && binding !== null && !confirmedStale
  // Server-recovered confirmation: the durable record matches this fresh
  // resolution, so the confirmation survived a reload or navigation. Shown
  // only when the backend itself reports it — never from local memory.
  const serverConfirmedCurrent = serverConfirmation !== null && binding !== null
    && serverConfirmation.status === 'confirmed'
    && serverConfirmation.shot_id === binding.shot_id
    && (serverConfirmation.confirmed_digest || '') === binding.binding_digest
  const serverConfirmationStale = serverConfirmation !== null && binding !== null
    && serverConfirmation.shot_id === binding.shot_id
    && (serverConfirmation.status === 'stale' || serverConfirmation.status === 'unverifiable')

  // Route-state handoff into the generation room: only a confirmation that
  // matches the fresh server resolution travels. A stale or absent
  // confirmation carries nothing, so generation can never mistake it for
  // an explicit confirmation. Previs adopts this once per navigation and
  // attaches it to the real generation request; the server re-verifies.
  const previsHandoffState =
    confirmedCurrent && projectId && confirmed && binding
      ? buildDeskConfirmedBindingState({
        projectId,
        sceneId: binding.scene_id,
        shotId: confirmed.shot_id,
        digest: confirmed.digest,
      })
      : undefined

  const referenceRows = references.status === 'loaded' ? references.value : []
  const approvedReferences = referenceRows.filter((asset) => asset.approval_state === 'approved').length
  const canonicalReferences = referenceRows.filter((asset) => asset.canonical === true).length
  const storyboardCovered = sceneRows.filter((row) => Boolean(row.storyboard?.shot_count)).length
  const plannedShots = blueprints.status === 'loaded' ? blueprints.value.reduce((total, row) => total + (row.shot_count || 0), 0) : 0
  const readyShots = blueprints.status === 'loaded' ? blueprints.value.reduce((total, row) => total + (row.ready_shot_count || 0), 0) : 0

  const stages = useMemo(() => {
    const sceneState: 'verified' | 'blocked' | 'unavailable' | 'unverified' =
      scenes.status === 'unavailable' ? 'unavailable'
        : scenes.status === 'loaded' && loadedScenes.length === 0 ? 'blocked'
          : sceneBlockers.length === 0 && scenes.status === 'loaded' ? 'verified' : 'unverified'
    const editorialState: 'verified' | 'blocked' | 'unavailable' | 'unverified' =
      cut.status === 'unavailable' ? 'unavailable' : cutStatus === 'approved' ? 'verified' : 'blocked'
    const deliveryState: 'verified' | 'blocked' | 'stale' | 'unavailable' | 'unverified' =
      delivery.status !== 'loaded' ? 'unavailable'
        : delivery.value.film_outdated ? 'stale'
          : delivery.value.film_assembled ? 'verified' : 'blocked'
    const screeningState: 'verified' | 'blocked' | 'unavailable' | 'unverified' =
      screening.status === 'unavailable' ? 'unavailable'
        : hasVerifiedFinal ? 'verified'
          : acceptance.status === 'loaded' && acceptance.value.stale ? 'blocked' : 'unverified'
    const stageDetail = (state: LoadState<unknown>, loaded: string) =>
      state.status === 'loaded' ? loaded : state.status === 'loading' ? 'Loading…' : 'Unavailable'
    return [
      { key: 'scenes', label: 'Scenes', state: sceneState, detail: stageDetail(scenes, `${completeSceneIds.size}/${loadedScenes.length} covered`), note: 'Saved scenes with completed shot outputs' },
      { key: 'editorial', label: 'Editorial', state: editorialState, detail: stageDetail(cut, cut.status === 'loaded' ? `Cut v${cut.value.version_number} · ${cut.value.status}` : ''), note: 'Approved Film Cut governs delivery order' },
      { key: 'delivery', label: 'Delivery', state: deliveryState, detail: stageDetail(delivery, delivery.status === 'loaded' ? `${delivery.value.scenes_with_compositions}/${delivery.value.scenes_total} composed` : ''), note: 'Scene compositions and full-film assembly' },
      { key: 'screening', label: 'Screening', state: screeningState, detail: stageDetail(screening, hasVerifiedFinal ? 'Accepted final' : 'No accepted final'), note: 'Selection requires package-scoped acceptance' },
    ]
  }, [scenes, cut, delivery, screening, acceptance, loadedScenes, completeSceneIds, sceneBlockers, cutStatus, hasVerifiedFinal])

  const jobQueue = useMemo(() => queueCounts(loadedJobs), [loadedJobs])
  const credits = useMemo(() => creditTelemetry(loadedJobs), [loadedJobs])
  const durations = useMemo(() => durationTelemetry(loadedJobs), [loadedJobs])
  const logRows = useMemo(() => executionLogRows(loadedJobs), [loadedJobs])
  const logCounts = useMemo(() => executionFilterCounts(logRows), [logRows])
  const visibleLogRows = useMemo(() => filterExecutionLog(logRows, logFilter).slice(0, 24), [logRows, logFilter])
  const filteredLogTotal = logCounts[logFilter] || 0
  const autoOptimizedCount = useMemo(() => loadedJobs.filter((job) => isRouterPayloadNormalized(job)).length, [loadedJobs])
  const selectedJob = useMemo(() => loadedJobs.find((job) => job.id === selectedJobId) || null, [loadedJobs, selectedJobId])
  const queueChips: { key: string; label: string; tone: string; count: number }[] = [
    { key: 'pending', label: 'Queued', tone: 'border-amber-400/40 text-amber-200', count: jobQueue.pending },
    { key: 'rendering', label: 'Rendering', tone: 'border-cyan-400/40 text-cyan-200', count: jobQueue.rendering },
    { key: 'auto_optimized', label: 'Auto-Optimized', tone: 'border-amber-300/45 text-amber-100', count: autoOptimizedCount },
    { key: 'complete', label: 'Done', tone: 'border-emerald-400/40 text-emerald-200', count: jobQueue.complete },
    { key: 'failed', label: 'Fail', tone: 'border-rose-400/40 text-rose-200', count: jobQueue.failed },
  ]

  const loading = [scenes, jobs, cut, packages, delivery, screening, acceptance, queue, blueprints, references, takes].some((state) => state.status === 'loading')

  const section = (title: string, children: ReactNode, aside?: ReactNode) => (
    <section className="border-t border-white/10 pt-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-200/80">{title}</h2>
        {aside}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )
  const failureText = (state: LoadState<unknown>) => state.status === 'unavailable' ? state.message : ''
  const severityStyle: Record<NextAction['severity'], string> = {
    blocker: 'text-amber-200',
    next: 'text-violet-200',
    info: 'text-zinc-300',
  }
  const stateChipStyle: Record<SceneRowState, string> = {
    draft: 'border-white/15 text-zinc-400',
    rendering: 'border-sky-400/30 text-sky-200',
    needs_review: 'border-violet-400/40 text-violet-200',
    blocked: 'border-amber-400/40 text-amber-200',
    ready: 'border-emerald-400/30 text-emerald-200',
    composed: 'border-emerald-400/50 text-emerald-100 bg-emerald-400/10',
  }

  const deskAccent = getProceduralRoomStyle('desk').tokens.accent
  return <StudioShell title="Production Desk" subtitle="What the production has, what it owes, and what is waiting on you.">
    <ProjectGuard>
      <RoomBackdrop roomKey="desk" testid="desk-room">
      <main className="mx-auto max-w-6xl space-y-5 px-4 pb-12 pt-4 sm:px-6">
        <header className="border-b border-white/15 pb-5" style={{ borderColor: `${deskAccent}33` }}>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-violet-300/80">Production control</p>
              <p className="mt-2 text-xs uppercase tracking-[0.15em] text-amber-200/80">{activeProject?.title || projectId || 'No project selected'}</p>
              <h1 className="mt-1 text-3xl font-medium text-zinc-100">Production Desk</h1>
              <p className="mt-2 max-w-2xl text-sm text-zinc-400">Project-scoped status from saved scenes, render jobs, take choices, editorial versions, delivery manifests, and acceptance reports. This desk reports evidence; it does not approve or change production state.</p>
            </div>
            <button type="button" onClick={() => void load(true)} disabled={!projectId || refreshing} className="inline-flex min-h-11 items-center gap-2 rounded-md border border-white/15 px-4 text-sm font-medium text-zinc-200 transition-colors hover:border-white/30 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40">{refreshing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}Refresh evidence</button>
          </div>
          <div className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {stages.map((stage) => <div key={stage.key} className="border-l-2 border-white/15 pl-4" aria-label={`${stage.label} stage`}>
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">{stage.label}</p>
              <p className={`mt-1.5 text-lg ${stage.state === 'verified' ? 'text-emerald-200' : stage.state === 'blocked' || stage.state === 'stale' ? 'text-amber-200' : stage.state === 'unavailable' ? 'text-zinc-500' : 'text-zinc-200'}`}>{stage.detail}</p>
              <p className="mt-1 text-xs leading-relaxed text-zinc-500">{stage.note}</p>
            </div>)}
          </div>
        </header>

        {projectError && <p role="alert" className="rounded-lg border border-amber-300/20 bg-amber-300/5 p-4 text-sm text-amber-100">{projectError}</p>}
        {!projectId && !projectError && <p role="status" className="rounded-lg border border-white/10 p-4 text-sm text-zinc-400">Choose a project to inspect its production state.</p>}
        {loading && <p role="status" className="flex items-center gap-2 text-sm text-zinc-400"><Loader2 size={16} className="animate-spin" />Reading persisted production state…</p>}

        {section('Next on this production', nextActions.length === 0
          ? <p className="text-sm text-zinc-400">Evidence is still loading.</p>
          : <ol className="space-y-3">
            {nextActions.map((action) => <li key={action.id} className="flex flex-wrap items-start justify-between gap-3 border-b border-white/10 pb-3 last:border-0 last:pb-0">
              <div className="min-w-0">
                <p className={`flex items-start gap-2 text-sm ${severityStyle[action.severity]}`}>
                  {action.severity === 'blocker' ? <AlertTriangle size={15} className="mt-0.5 shrink-0" /> : action.severity === 'next' ? <ArrowRight size={15} className="mt-0.5 shrink-0" /> : <CircleHelp size={15} className="mt-0.5 shrink-0" />}
                  {action.label}
                </p>
                <p className="mt-1 pl-6 text-xs leading-relaxed text-zinc-500">{action.detail}</p>
              </div>
              {action.to && <Link className="inline-flex min-h-10 shrink-0 items-center gap-1.5 text-sm text-cyan-200" to={action.to}>{action.toLabel}<ArrowRight size={14} /></Link>}
            </li>)}
          </ol>)}

        {section('Scene production', <>
          {scenes.status === 'unavailable' && <p role="status" className="mb-3 text-sm text-amber-100">Scene data unavailable: {scenes.message}</p>}
          <div className="flex flex-wrap gap-4">
            <StateLine label={scenes.status === 'loaded' ? `${scenes.value.length} saved scene${scenes.value.length === 1 ? '' : 's'}` : 'Scene state unavailable'} state={scenes.status === 'loaded' ? (scenes.value.length ? 'verified' : 'blocked') : 'unavailable'} />
            <StateLine label={jobs.status === 'loaded' ? `${completeSceneIds.size}/${loadedScenes.length} scenes with completed shot outputs` : 'Output coverage unavailable'} state={jobs.status === 'loaded' ? (sceneBlockers.length ? 'blocked' : loadedScenes.length ? 'verified' : 'unverified') : 'unavailable'} />
          </div>
          {scenes.status === 'loaded' && scenes.value.length === 0 && <p className="mt-3 text-sm text-zinc-400">No saved scenes yet. Start in The Page, then return here for coverage.</p>}
          {sceneBlockers.length > 0 && <ul className="mt-3 space-y-2 text-sm text-amber-100">{sceneBlockers.slice(0, 8).map((scene) => <li key={scene.scene_id} className="flex gap-2"><AlertTriangle size={15} className="mt-0.5 shrink-0" />{scene.scene_name || scene.scene_id}: no completed shot output with a saved media URL.</li>)}</ul>}

          {sceneRows.length > 0 && <div className="mt-4 overflow-x-auto rounded-md border border-white/10">
            <table className="w-full min-w-[760px] border-collapse text-left">
              <caption className="sr-only">Per-scene production state derived from saved render jobs, take choices, storyboard plans, and scene compositions.</caption>
              <thead>
                <tr className="border-b border-white/15 bg-white/5 text-[10px] uppercase tracking-[0.16em] text-zinc-400">
                  <th scope="col" className="px-3 py-2 font-medium">Scene</th>
                  <th scope="col" className="px-3 py-2 font-medium">Shot list</th>
                  <th scope="col" className="px-3 py-2 font-medium">Renders</th>
                  <th scope="col" className="px-3 py-2 font-medium">Takes</th>
                  <th scope="col" className="px-3 py-2 font-medium">Delivery</th>
                  <th scope="col" className="px-3 py-2 font-medium">State</th>
                </tr>
              </thead>
              <tbody>
                {sceneRows.map((row) => <tr key={row.scene.scene_id} className="border-t border-white/10 align-top">
                  <th scope="row" className="px-3 py-3 text-left font-normal">
                    <p className="text-sm text-zinc-100">{row.scene.scene_name || row.scene.scene_id}</p>
                    <p className="mt-0.5 font-mono text-[11px] text-zinc-500">{row.scene.scene_id}{row.scene.approval ? ` · approval ${row.scene.approval.status}` : ''}</p>
                  </th>
                  <td className="px-3 py-3 text-xs text-zinc-300">
                    {blueprints.status === 'unavailable' ? <span className="text-zinc-500">Unavailable</span>
                      : row.storyboard ? <>{row.storyboard.ready_shot_count}/{row.storyboard.shot_count} shots ready<p className="mt-0.5 text-[11px] uppercase tracking-[0.1em] text-zinc-500">{row.storyboard.status}{row.storyboard.locked ? ' · locked' : ''}</p></>
                        : <span className="text-zinc-500">No storyboard plan</span>}
                  </td>
                  <td className="px-3 py-3 text-xs text-zinc-300">
                    <span className="tabular-nums">{row.shotsComplete}/{row.shotsTotal} complete</span>
                    <span className="mt-0.5 flex flex-wrap gap-2 text-[11px]">
                      {row.shotsFailed > 0 && <span className="text-rose-200">{row.shotsFailed} failed shot{row.shotsFailed === 1 ? '' : 's'}</span>}
                      {row.shotsActive > 0 && <span className="text-sky-200">{row.shotsActive} active shot{row.shotsActive === 1 ? '' : 's'}</span>}
                      {row.shotsNeedingReview > 0 && <span className="text-violet-200">{row.shotsNeedingReview} shot{row.shotsNeedingReview === 1 ? '' : 's'} to review</span>}
                      {row.mediaReady > 0 && <span className="text-zinc-500">{row.mediaReady} with media</span>}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-xs text-zinc-300">
                    {takes.status === 'unavailable' ? <span className="text-zinc-500">Unavailable</span>
                      : row.takesTotal === null ? <span className="text-zinc-500">Not evaluated</span>
                        : row.takesTotal === 0 ? <span className="text-zinc-500">No shot slots yet</span>
                          : <span className="tabular-nums">{row.takesSelected}/{row.takesTotal} selected</span>}
                  </td>
                  <td className="px-3 py-3 text-xs text-zinc-300">
                    {ASSEMBLY_LABEL[row.assembly]}
                    {delivery.status === 'unavailable' && <p className="mt-0.5 text-[11px] text-amber-200/80">Delivery status unavailable</p>}
                  </td>
                  <td className="px-3 py-3">
                    <span className={`inline-flex items-center rounded border px-2 py-1 text-[11px] uppercase tracking-[0.1em] ${stateChipStyle[row.state]}`} title={row.blockers.join('; ') || SCENE_STATE_LABEL[row.state]}>
                      {SCENE_STATE_LABEL[row.state]}
                    </span>
                    {row.blockers.length > 0 && <p className="mt-1 max-w-[16rem] text-[11px] leading-snug text-zinc-500">{row.blockers[0]}</p>}
                  </td>
                </tr>)}
              </tbody>
            </table>
          </div>}
          {takes.status === 'unavailable' && <p role="status" className="mt-3 text-xs text-amber-200/90">Take choices unavailable: {takes.message}</p>}
          {takes.status === 'loaded' && takes.value.partial && <p className="mt-3 text-xs text-zinc-500">Take choices were read for the first {TAKE_LOOKUP_LIMIT} scenes; open the scene board for the rest.</p>}
          {takes.status === 'loaded' && !takes.value.partial && loadedScenes.length > 0 && <p className="mt-3 text-xs text-zinc-500">Take choices read for {loadedScenes.length} scene{loadedScenes.length === 1 ? '' : 's'}.</p>}
          <div className="mt-4 flex flex-wrap gap-3">
            <Link className="inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200" to={`/studio/production-board?project_id=${encodeURIComponent(projectId || '')}`}>Open scene board <ArrowRight size={14} /></Link>
            <Link className="inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200" to={`/studio/writers-room?project_id=${encodeURIComponent(projectId || '')}`}>Open The Page <ArrowRight size={14} /></Link>
          </div>
        </>)}

        {section('Render queue & pipeline', <>
          {jobs.status === 'loaded'
            ? <div className="flex flex-wrap gap-4">
              <StateLine label={`${activeCount} active`} state={activeCount ? 'unverified' : 'verified'} />
              <StateLine label={`${failedCount} failed`} state={failedCount ? 'blocked' : 'verified'} />
              <StateLine label={`${loadedJobs.filter((job) => normalizeJobStatus(job.status) === 'complete').length} complete jobs`} state="verified" />
            </div>
            : <p className="text-sm text-zinc-400">{failureText(jobs) || 'Render queue is loading.'}</p>}
          {jobs.status === 'loaded' && activeCount > 0 && <p className="mt-3 flex items-center gap-2 text-sm text-zinc-300"><Clock3 size={15} />Jobs are still active; scene coverage may change when they finish.</p>}
          {failedCount > 0 && <p className="mt-2 text-sm text-amber-100">Failed jobs remain visible in the queue; inspect their scene and failure detail in Previs.</p>}

          <div className="mt-4 border-t border-white/10 pt-4">
            {queue.status === 'unavailable' && <p role="status" className="text-sm text-amber-100">Production queue unavailable: {queue.message}</p>}
            {queue.status === 'loaded' && <>
              <div className="flex flex-wrap gap-2">
                {Object.entries(queue.value.counts_by_status).length === 0 && <span className="text-sm text-zinc-400">No queue items are recorded for this project.</span>}
                {Object.entries(queue.value.counts_by_status).map(([status, count]) => <span key={status} className="rounded border border-white/15 px-2 py-1 text-xs text-zinc-300"><span className="tabular-nums text-zinc-100">{count}</span> {status}</span>)}
                {queue.value.stale_leases > 0 && <span className="rounded border border-amber-400/40 px-2 py-1 text-xs text-amber-200">{queue.value.stale_leases} stale lease{queue.value.stale_leases === 1 ? '' : 's'}</span>}
              </div>
              {queue.value.blocked_reasons.length > 0 && <ul className="mt-3 space-y-1.5 text-sm text-amber-100">{queue.value.blocked_reasons.map((reason) => <li key={reason} className="flex gap-2"><ShieldAlert size={15} className="mt-0.5 shrink-0" />{reason}</li>)}</ul>}
              {queue.value.oldest_waiting_item && <p className="mt-3 text-xs text-zinc-500">Oldest waiting item: {queue.value.oldest_waiting_item.work_type || 'work'} · queued {String(queue.value.oldest_waiting_item.created_at || '').replace('T', ' ').replace('Z', '')} UTC</p>}
              {queue.value.recent_failures.length > 0 && <p className="mt-2 text-xs text-rose-200">{queue.value.recent_failures.length} recent queue failure{queue.value.recent_failures.length === 1 ? '' : 's'} recorded.</p>}
            </>}
          </div>
          <Link className="mt-4 inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200" to={`/studio/production-board?project_id=${encodeURIComponent(projectId || '')}`}>Inspect renders and queue <ArrowRight size={14} /></Link>
        </>, <span className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">Backend queue, read only</span>)}

        {section('Tier 01 · Telemetry & credit band', <>
          {jobs.status === 'unavailable' && <p role="status" className="text-sm text-amber-100">Render telemetry unavailable: {jobs.message}</p>}
          {jobs.status === 'loading' && <p role="status" className="flex items-center gap-2 text-sm text-zinc-400"><Loader2 size={15} className="animate-spin" />Reading render telemetry…</p>}
          {jobs.status === 'loaded' && <>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-md border border-white/10 bg-white/[0.02] p-3" aria-label="Active job queues">
                <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Job queues</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {queueChips.map((chip) => (
                    <span key={chip.key} data-testid={`queue-chip-${chip.key}`} className={`rounded border px-2 py-1 text-[11px] ${chip.tone}`}>
                      <span className="tabular-nums">{chip.count}</span> {chip.label}
                    </span>
                  ))}
                </div>
                <p className="mt-2 text-[11px] leading-snug text-zinc-500">{jobQueue.rendering + jobQueue.pending} active of {jobQueue.total} recorded job{jobQueue.total === 1 ? '' : 's'}.</p>
                {jobQueue.unknown > 0 && <p className="mt-1 text-[11px] text-amber-200/90">{jobQueue.unknown} job{jobQueue.unknown === 1 ? '' : 's'} carry a status this desk does not recognise.</p>}
              </div>

              <div className="rounded-md border border-white/10 bg-white/[0.02] p-3" aria-label="Runway credit tracker">
                <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Runway credits</p>
                <p className="mt-1.5 text-lg text-zinc-100 tabular-nums" data-testid="credit-realized">
                  {credits.realizedJobs > 0 ? credits.realized.toLocaleString() : '—'}
                  <span className="ml-1 text-[11px] font-normal text-zinc-500">realized</span>
                </p>
                <p className="mt-1 text-[11px] leading-snug text-zinc-500">
                  {credits.realizedJobs} job{credits.realizedJobs === 1 ? '' : 's'} reported cost · {credits.estimatedOnlyJobs} still estimated{credits.estimatedOnlyJobs === 1 ? '' : 'd'} at {credits.estimated.toLocaleString()} credit{credits.estimated === 1 ? '' : 's'}.
                </p>
                <div className="mt-3 border-t border-white/10 pt-3">
                  <CreditRadialGauge realized={credits.realized} estimated={credits.estimated} realizedJobs={credits.realizedJobs} estimatedOnlyJobs={credits.estimatedOnlyJobs} />
                </div>
                {credits.unpricedJobs > 0 && <p className="mt-1 text-[11px] text-zinc-500">{credits.unpricedJobs} job{credits.unpricedJobs === 1 ? '' : 's'} recorded no cost. This is spend on record, not an account balance.</p>}
                {credits.unpricedJobs === 0 && <p className="mt-1 text-[11px] text-zinc-600">Spend on record, not an account balance.</p>}
              </div>

              <div className="rounded-md border border-white/10 bg-white/[0.02] p-3" aria-label="Render duration trend">
                <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Render duration</p>
                <div className="mt-2 text-amber-200/80">
                  <RenderSparkline samples={durations.samples} label={`Render duration trend across ${durations.samples.length} completed job${durations.samples.length === 1 ? '' : 's'}`} />
                </div>
                <p className="mt-1.5 text-[11px] leading-snug text-zinc-500">
                  {durations.medianSeconds === null
                    ? 'No completed duration is recorded.'
                    : `Median ${Math.round(durations.medianSeconds)}s · slowest ${Math.round(durations.slowestSeconds || 0)}s across ${durations.samples.length} job${durations.samples.length === 1 ? '' : 's'}.`}
                </p>
                <div className="mt-3 border-t border-white/10 pt-3">
                  <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Latency vector · 60-min cadence</p>
                  <div className="mt-2 text-violet-300/90">
                    <LatencyVectorSparkline samples={durations.samples} label={`Render latency vector across ${durations.samples.length} completed job${durations.samples.length === 1 ? '' : 's'}`} />
                  </div>
                </div>
                {durations.undatedCompleted > 0 && <p className="mt-1 text-[11px] text-zinc-600">{durations.undatedCompleted} completed job{durations.undatedCompleted === 1 ? '' : 's'} carry no usable timestamps and are excluded.</p>}
              </div>
            </div>

          </>}
        </>, <span className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">Derived from saved job records</span>)}

        {section('Tier 02 · Production soundstage', jobs.status === 'loaded'
          ? <ProductionSoundstageOverlay rigs={loadedJobs.map((job) => ({ id: job.id, shotId: job.shot_id || job.id, status: job.status }))} selectedJobId={selectedJobId} onSelect={setSelectedJobId} />
          : <p className="text-sm text-zinc-400">{jobs.status === 'unavailable' ? `Stage plot unavailable: ${failureText(jobs)}` : 'Reading stage plot…'}</p>)}

        {section('Tier 03 · High-density execution queue', <>
          {jobs.status === 'unavailable' && <p role="status" className="text-sm text-amber-100">Execution queue unavailable: {jobs.message}</p>}
          {jobs.status === 'loading' && <p role="status" className="flex items-center gap-2 text-sm text-zinc-400"><Loader2 size={15} className="animate-spin" />Reading execution queue…</p>}
          {jobs.status === 'loaded' && <>
            <div>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-xs font-semibold text-zinc-200">Execution log</p>
                <span className="text-[11px] text-zinc-500">{logRows.length} job record{logRows.length === 1 ? '' : 's'}</span>
              </div>
              <div role="group" aria-label="Execution log filters" className="mt-2 flex flex-wrap gap-1.5">
                {EXECUTION_LOG_FILTERS.map((filter) => {
                  const active = logFilter === filter
                  return (
                    <button
                      key={filter}
                      type="button"
                      aria-pressed={active}
                      data-testid={`execution-filter-${filter}`}
                      onClick={() => setLogFilter(filter)}
                      className={`min-h-8 rounded border px-2.5 text-[11px] transition-colors ${active ? 'border-amber-200/50 bg-amber-200/10 text-amber-100' : 'border-white/15 text-zinc-300 hover:border-white/30'}`}
                    >
                      {EXECUTION_LOG_FILTER_LABEL[filter]} <span className="tabular-nums text-zinc-500">{logCounts[filter]}</span>
                    </button>
                  )
                })}
              </div>

              {logRows.length === 0 ? (
                <p className="mt-3 text-sm text-zinc-400">No render jobs are recorded for this project, so there is nothing to log.</p>
              ) : visibleLogRows.length === 0 ? (
                <p className="mt-3 text-sm text-zinc-400">No job matches the {EXECUTION_LOG_FILTER_LABEL[logFilter]} filter.</p>
              ) : (<>
                <div aria-hidden="true" className="mt-3 hidden grid-cols-[6rem_11rem_8rem_minmax(0,1fr)_auto] gap-x-3 px-1 text-[10px] uppercase tracking-[0.14em] text-zinc-600 md:grid">
                  <span>Status</span><span>Shot</span><span>Provider</span><span>Detail</span><span className="text-right">Logged</span>
                </div>
                <ul className="mt-1 space-y-1" aria-label="Execution log rows">
                  {visibleLogRows.map((row) => {
                    const rowJob = loadedJobs.find((job) => job.id === row.id)
                    const rowWarnings = rowJob ? getRouterNormalizationWarnings(rowJob) : []
                    return (
                    <li key={row.id} className="border-b border-white/5 pb-1 last:border-0">
                      <button
                        type="button"
                        data-testid={`execution-row-${row.id}`}
                        onClick={() => setSelectedJobId(row.id)}
                        aria-label={`Inspect job ${row.shotId} with status ${row.statusLabel}`}
                        className="grid w-full grid-cols-[5.5rem_minmax(0,1fr)] items-baseline gap-x-3 gap-y-0.5 rounded px-1 py-1 text-left text-xs hover:bg-white/[0.03] focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-200/60 md:grid-cols-[6rem_11rem_8rem_minmax(0,1fr)_auto]"
                      >
                        <span className={`w-fit rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] ${row.status === 'complete' ? 'border-emerald-400/40 text-emerald-200' : row.status === 'failed' ? 'border-rose-400/40 text-rose-200' : row.status === 'rendering' ? 'border-cyan-400/40 text-cyan-200' : 'border-amber-400/40 text-amber-200'}`}>{row.statusLabel}</span>
                        <span className="truncate font-mono text-[11px] text-zinc-300">{row.shotId}</span>
                        <span className="truncate text-[11px] text-zinc-500">{row.provider}</span>
                        <span className="min-w-0 text-[11px] text-zinc-400">{row.detail} {row.autoOptimized ? <RouterNormalizationBadge detail={rowWarnings.length > 0 ? `· ${rowWarnings.length} adjustment${rowWarnings.length === 1 ? '' : 's'}` : undefined} /> : null}</span>
                        <span className="text-right text-[11px] tabular-nums text-zinc-500">{row.durationSeconds !== null ? `${Math.round(row.durationSeconds)}s` : ''}{row.at ? <span className="ml-2 text-[10px] text-zinc-600">{row.at.replace('T', ' ').replace('Z', ' UTC')}</span> : null}</span>
                      </button>
                    </li>
                    )
                  })}
                </ul>
              </>)}
              {filteredLogTotal > visibleLogRows.length && <p className="mt-2 text-[11px] text-zinc-500">Showing {visibleLogRows.length} of {filteredLogTotal} matching records.</p>}
            </div>
          </>}
        </>, <span className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">Execution queue · derived from saved job records</span>)}

        {section('Reference & media coverage', <>
          {references.status === 'unavailable' && <p role="status" className="text-sm text-amber-100">Reference assets unavailable: {references.message}</p>}
          {blueprints.status === 'unavailable' && <p role="status" className="text-sm text-amber-100">Shot list unavailable: {blueprints.message}</p>}
          <div className="flex flex-wrap gap-4">
            <StateLine label={references.status === 'loaded' ? `${referenceRows.length} reference asset${referenceRows.length === 1 ? '' : 's'}${approvedReferences ? ` · ${approvedReferences} approved` : ''}${canonicalReferences ? ` · ${canonicalReferences} canonical` : ''}` : 'Reference assets unavailable'} state={references.status === 'loaded' ? (referenceRows.length ? 'verified' : 'blocked') : 'unavailable'} />
            <StateLine label={blueprints.status === 'loaded' ? `${storyboardCovered}/${loadedScenes.length} scenes with a storyboard plan` : 'Shot list unavailable'} state={blueprints.status === 'loaded' ? (loadedScenes.length && storyboardCovered === loadedScenes.length ? 'verified' : storyboardCovered ? 'unverified' : 'blocked') : 'unavailable'} />
            <StateLine label={blueprints.status === 'loaded' ? `${readyShots}/${plannedShots} planned shots ready` : 'Planned shot state unavailable'} state={blueprints.status === 'loaded' ? (plannedShots === 0 ? 'blocked' : readyShots === plannedShots ? 'verified' : 'unverified') : 'unavailable'} />
            <StateLine label={jobs.status === 'loaded' ? `${loadedJobs.filter((job) => job.output_payload?.asset_url || job.output_url).length} saved media files` : 'Media inventory unavailable'} state={jobs.status === 'loaded' ? (loadedJobs.some((job) => job.output_payload?.asset_url || job.output_url) ? 'verified' : 'blocked') : 'unavailable'} />
          </div>
          {references.status === 'loaded' && referenceRows.length === 0 && <p className="mt-3 text-sm text-zinc-400">No reference assets are registered for this project yet. Reference Space holds canonical faces, wardrobe, and environment boards.</p>}
          {blueprints.status === 'loaded' && plannedShots === 0 && loadedScenes.length > 0 && <p className="mt-3 text-sm text-zinc-400">No shot list is planned yet. Storyboard plans in Previs give this desk real shot counts.</p>}
          <div className="mt-4 flex flex-wrap gap-3">
            <Link className="inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200" to={`/studio/vault?project_id=${encodeURIComponent(projectId || '')}`}>Inspect the Vault <Layers size={14} /></Link>
            <Link className="inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200" to={`/studio/previs?project_id=${encodeURIComponent(projectId || '')}`} state={previsHandoffState}>Open Previs Bay <Camera size={14} /></Link>
          </div>
        </>)}

        {section('Shot reference binding', <>
          <p className="max-w-2xl text-xs leading-relaxed text-zinc-500">Review the server-resolved authorized references for one shot, in the server&apos;s canonical order, then explicitly confirm them. Resolving and confirming create no render jobs, approve nothing, and invoke no provider. Confirming saves a durable project-scoped record that survives reloads; if references change before submission, the Production Integrity Gate rejects the stale binding.</p>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="min-w-0 flex-1 basis-64 text-xs text-zinc-400">Shot ID
              <input
                type="text"
                value={shotInput}
                onChange={(event) => setShotInput(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') void resolveBinding() }}
                placeholder="scene_002_shot_001"
                aria-label="Shot ID"
                className="mt-1 block w-full min-h-10 rounded-md border border-white/15 bg-black/30 px-3 font-mono text-sm text-zinc-100 placeholder:text-zinc-600"
              />
            </label>
            <button
              type="button"
              onClick={() => void resolveBinding()}
              disabled={!projectId || !shotInput.trim() || resolving}
              className="inline-flex min-h-10 items-center gap-2 rounded-md border border-white/15 px-4 text-sm font-medium text-zinc-200 transition-colors hover:border-white/30 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
            >{resolving ? <Loader2 size={15} className="animate-spin" /> : null}Resolve binding</button>
          </div>
          {bindingError && <p role="alert" className="mt-3 rounded-md border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-200">{bindingError}</p>}
          {binding && <div className="mt-4 rounded-md border border-white/10 bg-white/[0.02] p-3">
            <p className="text-sm text-zinc-100">Authorized binding for <span className="font-mono">{binding.shot_id}</span></p>
            <p className="mt-1 font-mono text-[11px] text-zinc-500">project {binding.project_id} · scene {binding.scene_id} · {binding.binding.length} reference{binding.binding.length === 1 ? '' : 's'}</p>
            <p className="mt-1 break-all font-mono text-[11px] text-zinc-500">digest {binding.binding_digest}</p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[560px] border-collapse text-left">
                <caption className="sr-only">Server-resolved authorized references in canonical order.</caption>
                <thead>
                  <tr className="border-b border-white/15 text-[10px] uppercase tracking-[0.16em] text-zinc-500">
                    <th scope="col" className="py-1 pr-3 font-medium">Reference</th>
                    <th scope="col" className="py-1 pr-3 font-medium">Target</th>
                    <th scope="col" className="py-1 pr-3 font-medium">Role</th>
                    <th scope="col" className="py-1 font-medium">Authorization</th>
                  </tr>
                </thead>
                <tbody>
                  {binding.binding.map((row) => <tr key={row.ref_id} className="border-t border-white/10 align-top text-xs">
                    <td className="py-2 pr-3 font-mono text-[11px] text-zinc-200">{row.ref_id}</td>
                    <td className="py-2 pr-3 font-mono text-[11px] text-zinc-400">{row.target_type}/{row.target_id}</td>
                    <td className="py-2 pr-3 text-zinc-300">{row.role}{row.category && row.category !== row.role ? ` · ${row.category}` : ''}</td>
                    <td className="py-2 text-zinc-300">{row.canonical && row.approval_state === 'approved' ? 'Approved canonical' : `${row.approval_state}${row.canonical ? ' · canonical' : ''}`}</td>
                  </tr>)}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => void confirmBinding()}
                disabled={resolving || confirming}
                className="inline-flex min-h-10 items-center gap-2 rounded-md border border-emerald-300/30 bg-emerald-500/10 px-4 text-sm font-semibold text-emerald-200 disabled:opacity-50"
              >{confirming ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}Confirm this binding</button>
              {confirmedCurrent && <p role="status" className="text-xs text-emerald-200">Confirmed for {confirmed?.shot_id} · digest {confirmed?.digest.slice(0, 12)}… — saved durably for this project and shot. Open Previs Bay to carry it to generation.</p>}
              {!confirmedCurrent && serverConfirmedCurrent && <p role="status" className="text-xs text-emerald-200">Confirmed for {binding.shot_id} · digest {(serverConfirmation?.confirmed_digest || '').slice(0, 12)}… — recovered from the durable record after reload. Open Previs Bay to carry it to generation.</p>}
              {confirmedStale && <p role="alert" className="text-xs text-amber-200">The confirmed binding differs from this fresh resolution. Review and confirm again before submitting.</p>}
              {!confirmedStale && serverConfirmationStale && <p role="alert" className="text-xs text-amber-200">The durable confirmation no longer matches this fresh resolution. Review and confirm again before submitting.</p>}
              {confirmError && <p role="alert" className="text-xs text-rose-200">Confirmation was not saved: {confirmError}</p>}
            </div>
          </div>}
        </>)}

        {section('Editorial readiness', <>
          {cut.status === 'loaded' ? <div className="space-y-2"><div className="flex flex-wrap gap-4"><StateLine label={`Film Cut v${cut.value.version_number} · ${cut.value.status}`} state={cut.value.status === 'approved' ? 'verified' : 'blocked'} /><span className="text-xs text-zinc-400">{cut.value.scene_order.length} scene slots in saved order</span></div>{cut.value.status !== 'approved' && <p className="text-sm text-amber-100">This Film Cut is not approved. Full-film assembly must wait for a current approved cut.</p>}{cut.value.status === 'approved' && loadedScenes.length && cut.value.scene_order.some((id) => !loadedScenes.some((scene) => scene.scene_id === id)) && <p className="text-sm text-rose-200">Cut contains scene IDs that are absent from the current project scene list; delivery is blocked.</p>}</div> : <p className="text-sm text-zinc-400">{failureText(cut) || 'Film Cut status is loading.'}</p>}
          <Link className="mt-3 inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200" to={`/studio/screening-room?project_id=${encodeURIComponent(projectId || '')}`}>Review editorial context in The Theater <ArrowRight size={14} /></Link>
        </>)}

        {section('Delivery & acceptance', <>
          {delivery.status === 'unavailable' && <p role="status" className="mb-3 text-sm text-amber-100">Delivery status unavailable: {delivery.message}</p>}
          <div className="flex flex-wrap gap-4">
            <StateLine label={delivery.status === 'loaded' ? `${delivery.value.scenes_with_compositions}/${delivery.value.scenes_total} scenes assembled` : 'Delivery status unavailable'} state={delivery.status === 'loaded' ? (delivery.value.film_outdated ? 'stale' : delivery.value.film_assembled ? 'verified' : 'blocked') : 'unavailable'} />
            <StateLine label={cutStatus === 'approved' ? 'Approved Film Cut' : cutStatus === 'unavailable' ? 'Film Cut unverified' : 'Film Cut not approved'} state={cutStatus === 'approved' ? 'verified' : cutStatus === 'unavailable' ? 'unavailable' : 'blocked'} />
            <StateLine label={acceptance.status === 'loaded' ? `Acceptance · ${acceptance.value.disposition}${acceptance.value.stale ? ' · stale' : ''}` : 'Acceptance unavailable'} state={acceptance.status === 'loaded' ? (acceptance.value.stale ? 'stale' : accepted ? 'verified' : acceptance.value.disposition === 'blocked' ? 'blocked' : 'unverified') : 'unavailable'} />
            <StateLine label={hasVerifiedFinal ? 'Accepted current final registered' : 'No verified current accepted final'} state={hasVerifiedFinal ? 'verified' : 'unverified'} />
          </div>
          {delivery.status === 'loaded' && !delivery.value.film_assembled && <p className="mt-3 text-sm text-amber-100">{delivery.value.film_outdated ? 'Saved delivery is stale against current scene media or Film Cut.' : 'No current full-film assembly is recorded.'} Assembly requires every included scene output and an approved Film Cut.</p>}
          {acceptance.status === 'loaded' && !accepted && <p className="mt-2 text-sm text-amber-100">{acceptance.value.recommended_action || 'Acceptance has not established a current approvable output.'}</p>}
          {packages.status === 'loaded' && packageRows.length === 0 && <p className="mt-2 text-sm text-zinc-400">No final package is recorded yet.</p>}
          {latestPackage && <p className="mt-2 text-xs text-zinc-400">Latest package: {latestPackage.film_title} · {latestPackage.package_status} · {latestPackage.scene_count} scenes</p>}
          {screening.status === 'loaded' && !screening.value.current_final_output && <p className="mt-2 text-sm text-zinc-400">Screening has no selected current final. A manifest entry alone does not prove creator acceptance.</p>}
          {screening.status === 'loaded' && screening.value.current_final_output && <p className="mt-2 flex items-start gap-2 text-sm text-emerald-200"><CheckCircle2 size={15} className="mt-0.5 shrink-0" />Screening has a selected current final{hasVerifiedFinal ? ' that matches the accepted package.' : ' whose acceptance this desk could not confirm.'}</p>}
          <div className="mt-4 flex flex-wrap gap-3"><Link className="inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200" to={`/studio/screening-room?project_id=${encodeURIComponent(projectId || '')}`}>Open Screening Room <Film size={14} /></Link><Link className="inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200" to={`/studio/archive?project_id=${encodeURIComponent(projectId || '')}`}>Inspect project archive <ArrowRight size={14} /></Link></div>
        </>)}

        {packages.status === 'unavailable' && <p role="status" className="flex items-center gap-2 text-sm text-amber-100"><ShieldAlert size={15} />Package records unavailable: {packages.message}</p>}
        {screening.status === 'unavailable' && <p role="status" className="flex items-center gap-2 text-sm text-amber-100"><ShieldAlert size={15} />Screening registration unavailable: {screening.message}</p>}
        {acceptance.status === 'unavailable' && <p role="status" className="flex items-center gap-2 text-sm text-amber-100"><ShieldAlert size={15} />Acceptance record unavailable: {acceptance.message}</p>}
        <p className="flex items-start gap-2 border-t border-white/10 pt-4 text-xs leading-relaxed text-zinc-500"><CircleHelp size={14} className="mt-0.5 shrink-0" />All readiness here is informational. Approval, ownership, current-output selection, and playback are enforced by their project-scoped backend workflows.</p>
        <details className="text-xs text-zinc-500"><summary className="cursor-pointer">Project context</summary><ProjectContextBar roomName="production desk" /></details>
      </main>
      {selectedJob ? <JobInspectorDrawer job={selectedJob} projectId={projectId || ''} onClose={() => setSelectedJobId(null)} /> : null}
      </RoomBackdrop>
    </ProjectGuard>
  </StudioShell>
}
