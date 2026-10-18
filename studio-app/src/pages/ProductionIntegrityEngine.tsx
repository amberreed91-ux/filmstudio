import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Clock3,
  Link2,
  Loader2,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'
import type { ReactNode } from 'react'
import StudioShell from '../components/StudioShell'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import { RoomBackdrop } from '../components/RoomCinematicChrome'
import { getProceduralRoomStyle } from '../lib/proceduralBackdrops'
import PipelineGateFlow from '../components/PipelineGateFlow'
import { buildPipelineGateFlow } from '../lib/pipelineGateFlow'
import { useProjectRouteContext } from '../hooks/useProjectRouteContext'
import { useStudio } from '../context/StudioContext'
import { normalizeJobStatus } from '../lib/jobStatus'
import {
  getAssemblyStatus,
  getCurrentFilmCut,
  getLatestProductionAcceptanceSummary,
  getPackageAcceptanceGuard,
  getProjectDecisionGate,
  getScreeningManifest,
  listFinalShortFilmPackagesForProject,
  listProductionAcceptanceReports,
  listRenderJobs,
  listScenes,
  type AssemblyStatusResponse,
  type FilmCutVersion,
  type FinalShortFilmPackage,
  type PackageApprovalGuardResult,
  type ProductionAcceptanceCheckResult,
  type ProductionAcceptanceReport,
  type ProductionAcceptanceSummary,
  type RenderJob,
  type Scene,
  type ScreeningManifest,
  type StudioDecisionGate,
} from '../lib/studioApi'

type LoadState<T> = { status: 'loading' } | { status: 'unavailable'; message: string } | { status: 'loaded'; value: T }

function empty<T>(): LoadState<T> { return { status: 'loading' } }

/**
 * Evidence states used across the console. Every state maps to a record the
 * backend returned (or to an explicit absence). Nothing here is computed as a
 * verdict the backend has not established.
 */
type EvidenceState =
  | 'satisfied'
  | 'partial'
  | 'missing'
  | 'stale'
  | 'blocked'
  | 'unavailable'
  | 'not_established'

const STATE_LABEL: Record<EvidenceState, string> = {
  satisfied: 'Satisfied',
  partial: 'Partial',
  missing: 'Missing',
  stale: 'Stale',
  blocked: 'Blocked',
  unavailable: 'Unavailable',
  not_established: 'Not established',
}

const STATE_TONE: Record<EvidenceState, string> = {
  satisfied: 'border-emerald-400/40 bg-emerald-400/5 text-emerald-200',
  partial: 'border-sky-400/40 bg-sky-400/5 text-sky-200',
  missing: 'border-amber-400/40 bg-amber-400/5 text-amber-200',
  stale: 'border-amber-400/40 bg-amber-400/5 text-amber-200',
  blocked: 'border-rose-400/40 bg-rose-400/5 text-rose-200',
  unavailable: 'border-white/15 text-zinc-400',
  not_established: 'border-white/15 text-zinc-400',
}

const SEVERITY_TONE: Record<string, string> = {
  blocker: 'border-rose-400/40 bg-rose-400/5 text-rose-200',
  warning: 'border-amber-400/40 bg-amber-400/5 text-amber-200',
  pass: 'border-emerald-400/40 bg-emerald-400/5 text-emerald-200',
  not_applicable: 'border-white/15 text-zinc-400',
}

const SEVERITY_ORDER: ProductionAcceptanceCheckResult['severity'][] = ['blocker', 'warning', 'pass', 'not_applicable']

type DependencyRow = {
  id: string
  name: string
  state: EvidenceState
  detail: string
  evidenceSource: string
  dependsOn: string
  waitingOn?: string
  action?: { label: string; to: string }
}

type BlockerItem = {
  id: string
  origin: 'decision-gate' | 'acceptance' | 'dependency'
  title: string
  evidence: string
  missing: string
  remediation: string[]
  waitingOn?: string
  action?: { label: string; to: string }
}

function formatObserved(value: unknown): string {
  if (value === null || value === undefined) return ''
  let text: string
  if (typeof value === 'string') text = value
  else {
    try {
      text = JSON.stringify(value)
    } catch {
      text = String(value)
    }
  }
  return text.length > 120 ? `${text.slice(0, 117)}…` : text
}

/**
 * Conservative navigation hint for advisory gate blockers (plain strings with no
 * remediation field). The link is navigation only — it never asserts that the
 * destination resolves the blocker.
 */
function routeForAdvisoryBlocker(text: string, projectId: string): { label: string; to: string } {
  const query = `?project_id=${encodeURIComponent(projectId || '')}`
  const normalized = text.toLowerCase()
  if (normalized.includes('render') || normalized.includes('clip')) {
    return { label: 'Inspect renders', to: `/studio/production-board${query}` }
  }
  if (normalized.includes('review') || normalized.includes('revision') || normalized.includes('screening')) {
    return { label: 'Open review workflow', to: `/studio/screening-room${query}` }
  }
  return { label: 'Open Production Desk', to: `/studio/production-desk${query}` }
}

function buildDependencies(input: {
  scenes: LoadState<Scene[]>
  jobs: LoadState<RenderJob[]>
  cut: LoadState<FilmCutVersion>
  delivery: LoadState<AssemblyStatusResponse>
  packages: LoadState<FinalShortFilmPackage[]>
  reports: LoadState<ProductionAcceptanceReport[]>
  guard: LoadState<PackageApprovalGuardResult | null>
  screening: LoadState<ScreeningManifest>
}): DependencyRow[] {
  const { scenes, jobs, cut, delivery, packages, reports, guard, screening } = input
  const board = '/studio/production-board'
  const page = '/studio/writers-room'
  const theater = '/studio/screening-room'
  const rows: DependencyRow[] = []

  // 1. Saved scenes — foundation of every downstream contract.
  const scenesLoaded = scenes.status === 'loaded'
  const sceneRows = scenesLoaded ? scenes.value : []
  rows.push({
    id: 'scenes',
    name: 'Saved project scenes',
    state: scenes.status === 'unavailable' ? 'unavailable' : scenesLoaded && sceneRows.length === 0 ? 'missing' : scenesLoaded ? 'satisfied' : 'not_established',
    detail: scenes.status === 'unavailable'
      ? scenes.message
      : scenesLoaded
        ? `${sceneRows.length} scene${sceneRows.length === 1 ? '' : 's'} in the project execution summary`
        : 'Scene list has not loaded.',
    evidenceSource: 'GET /projects/{id}/scenes',
    dependsOn: 'Scene coverage, rendering, scene delivery, and full-film assembly all reference this list.',
    action: { label: 'Open The Page', to: page },
  })

  // 2. Playable renders per scene — derived strictly from saved render jobs.
  const jobsLoaded = jobs.status === 'loaded'
  const jobRows = jobsLoaded ? jobs.value : []
  const playableScenes = new Set(
    jobRows
      .filter((job) => normalizeJobStatus(job.status) === 'complete' && Boolean(job.output_payload?.asset_url || job.output_url))
      .map((job) => (job.shot_id || '').split('_shot_')[0]),
  )
  const coveredScenes = scenesLoaded ? sceneRows.filter((scene) => playableScenes.has(scene.scene_id)).length : 0
  const coverageKnown = scenesLoaded && jobsLoaded
  const coverageComplete = coverageKnown && sceneRows.length > 0 && coveredScenes === sceneRows.length
  const failedJobs = jobRows.filter((job) => normalizeJobStatus(job.status) === 'failed').length
  rows.push({
    id: 'renders',
    name: 'Playable scene renders',
    state: jobs.status === 'unavailable' || scenes.status === 'unavailable'
      ? 'unavailable'
      : !coverageKnown
        ? 'not_established'
        : failedJobs > 0
          ? 'blocked'
          : coverageComplete
            ? 'satisfied'
            : sceneRows.length === 0
              ? 'not_established'
              : 'partial',
    detail: coverageKnown
      ? `${coveredScenes}/${sceneRows.length} scene${sceneRows.length === 1 ? '' : 's'} have a complete render with a saved media URL${failedJobs ? ` · ${failedJobs} failed job${failedJobs === 1 ? '' : 's'}` : ''}`
      : 'Render coverage could not be established from the loaded records.',
    evidenceSource: 'GET /render/jobs?project_id={id}',
    dependsOn: 'Scene delivery refuses to compose a scene whose selected shots are unfinished.',
    waitingOn: scenesLoaded && sceneRows.length === 0 ? 'Saved project scenes' : undefined,
    action: { label: 'Open scene board', to: board },
  })

  // 3. Approved Film Cut — hard prerequisite for full-film delivery.
  const cutApproved = cut.status === 'loaded' && cut.value.status === 'approved'
  rows.push({
    id: 'film-cut',
    name: 'Approved Film Cut',
    state: cut.status === 'unavailable' ? 'unavailable' : cutApproved ? 'satisfied' : cut.status === 'loaded' ? 'missing' : 'not_established',
    detail: cut.status === 'unavailable'
      ? cut.message
      : cut.status === 'loaded'
        ? `Cut ${cut.value.cut_id} · v${cut.value.version_number} · ${cut.value.status} · ${cut.value.scene_order.length} scene slots`
        : 'Film Cut status has not loaded.',
    evidenceSource: 'GET /projects/{id}/film-cut',
    dependsOn: 'Full-film assembly refuses to run without an explicitly approved current cut.',
    action: { label: 'Open editorial in The Theater', to: theater },
  })

  // 4. Scene compositions + full-film assembly.
  const assemblyUnavailable = delivery.status === 'unavailable'
  const assemblyLoaded = delivery.status === 'loaded'
  rows.push({
    id: 'assembly',
    name: 'Scene compositions & film assembly',
    state: assemblyUnavailable
      ? 'unavailable'
      : !assemblyLoaded
        ? 'not_established'
        : delivery.value.film_outdated
          ? 'stale'
          : delivery.value.film_assembled
            ? 'satisfied'
            : 'missing',
    detail: assemblyUnavailable
      ? delivery.message
      : assemblyLoaded
        ? `${delivery.value.scenes_with_compositions}/${delivery.value.scenes_total} scene compositions current · film ${delivery.value.film_assembled ? 'assembled' : 'not assembled'}${delivery.value.film_outdated ? ' · recorded film is outdated' : ''}${delivery.value.film_url ? ` · ${delivery.value.film_url}` : ''}`
        : 'Assembly status has not loaded.',
    evidenceSource: 'GET /projects/{id}/assembly-status',
    dependsOn: 'A traceable final package is built from this assembly, and acceptance inspects that package.',
    waitingOn: assemblyUnavailable && cut.status === 'loaded' && !cutApproved
      ? 'Approved Film Cut'
      : !coverageComplete && coverageKnown && sceneRows.length > 0
        ? 'Playable scene renders'
        : undefined,
    action: { label: 'Open delivery in The Theater', to: theater },
  })

  // 5. Final package.
  const packageRows = packages.status === 'loaded' ? packages.value : []
  const latestPackage = packageRows[0]
  rows.push({
    id: 'package',
    name: 'Traceable final package',
    state: packages.status === 'unavailable' ? 'unavailable' : latestPackage ? 'satisfied' : packages.status === 'loaded' ? 'missing' : 'not_established',
    detail: packages.status === 'unavailable'
      ? packages.message
      : latestPackage
        ? `${latestPackage.package_id} · ${latestPackage.package_status} · ${latestPackage.scene_count} scenes · created ${latestPackage.created_at || 'unknown'}`
        : 'No final package record exists for this project.',
    evidenceSource: 'GET /projects/{id}/final-short-film-packages',
    dependsOn: 'Production Integrity acceptance is scoped to one package; Screening selection requires an accepted package.',
    waitingOn: !latestPackage && assemblyLoaded && !delivery.value.film_assembled ? 'Scene compositions & film assembly' : undefined,
    action: { label: 'Open delivery workflow', to: theater },
  })

  // 6. Production Integrity acceptance report.
  const reportRows = reports.status === 'loaded' ? reports.value : []
  const latestReport = reportRows[0]
  rows.push({
    id: 'acceptance',
    name: 'Production Integrity acceptance',
    state: reports.status === 'unavailable'
      ? 'unavailable'
      : !latestReport
        ? reports.status === 'loaded' ? 'missing' : 'not_established'
        : latestReport.stale
          ? 'stale'
          : latestReport.disposition === 'blocked'
            ? 'blocked'
            : latestReport.disposition === 'insufficient_data'
              ? 'missing'
              : 'satisfied',
    detail: reports.status === 'unavailable'
      ? reports.message
      : latestReport
        ? `${latestReport.acceptance_id} · disposition ${latestReport.disposition}${latestReport.stale ? ' · stale' : ''} · generated ${latestReport.generated_at || 'unknown'} by ${latestReport.generated_by || 'backend'}`
        : 'No acceptance report has ever been produced for this project.',
    evidenceSource: 'GET /projects/{id}/production-acceptance',
    dependsOn: 'Screening can only select a current final when the exact package carries a current, allowed acceptance.',
    waitingOn: !latestReport && !latestPackage && packages.status === 'loaded' ? 'Traceable final package' : undefined,
    action: { label: 'Open acceptance workflow', to: theater },
  })

  // 7. Package approval guard — the backend decision that gates selection.
  const guardValue = guard.status === 'loaded' ? guard.value : null
  rows.push({
    id: 'guard',
    name: 'Package approval guard',
    state: guard.status === 'unavailable'
      ? 'unavailable'
      : !latestPackage
        ? 'not_established'
        : guardValue === null
          ? 'not_established'
          : guardValue.allowed
            ? 'satisfied'
            : 'blocked',
    detail: guard.status === 'unavailable'
      ? guard.message
      : !latestPackage
        ? 'No final package exists, so no approval guard can be evaluated.'
        : guardValue
          ? `${guardValue.guard_level} · ${guardValue.reason}${guardValue.latest_acceptance_id ? ` · evidence ${guardValue.latest_acceptance_id}` : ''}`
          : 'Guard evaluation has not loaded.',
    evidenceSource: 'GET /final-short-film-packages/{package_id}/acceptance-guard',
    dependsOn: 'Selecting and approving a current final in Screening requires an allowed guard for that exact package.',
    waitingOn: !guardValue && !latestReport && reports.status === 'loaded' ? 'Production Integrity acceptance' : undefined,
    action: { label: 'Open Screening Room', to: theater },
  })

  // 8. Selected current final.
  const screeningLoaded = screening.status === 'loaded'
  const currentFinal = screeningLoaded ? screening.value.current_final_output : null
  rows.push({
    id: 'current-final',
    name: 'Selected current final',
    state: screening.status === 'unavailable'
      ? 'unavailable'
      : !screeningLoaded
        ? 'not_established'
        : currentFinal
          ? 'satisfied'
          : 'missing',
    detail: screening.status === 'unavailable'
      ? screening.message
      : currentFinal
        ? `${currentFinal.screening_output_id} · source ${currentFinal.source_type}:${currentFinal.source_id} · ${currentFinal.approved ? 'approved' : 'awaiting creator approval'} · media ${currentFinal.media_status}`
        : 'Screening has no selected current final for this project.',
    evidenceSource: 'GET /projects/{id}/screening/manifest?refresh=false',
    dependsOn: 'Playback and approval stay scoped to this exact output once it is selected.',
    waitingOn: !currentFinal && (guard.status !== 'loaded' || (guardValue !== null && !guardValue.allowed)) ? 'Package approval guard' : undefined,
    action: { label: 'Open Screening Room', to: theater },
  })

  return rows
}

function buildBlockers(input: {
  projectId: string
  gate: LoadState<StudioDecisionGate>
  reports: LoadState<ProductionAcceptanceReport[]>
  dependencies: DependencyRow[]
}): BlockerItem[] {
  const { projectId, gate, reports, dependencies } = input
  const items: BlockerItem[] = []

  if (gate.status === 'loaded') {
    gate.value.blockers.forEach((text, index) => {
      items.push({
        id: `gate-${index}`,
        origin: 'decision-gate',
        title: text,
        evidence: `Reported by the read-only Studio Decision Gate for project ${gate.value.project_id} (advisory, stage ${gate.value.current_stage}).`,
        missing: 'The gate reports the condition but does not expose a remediation record.',
        remediation: [],
        action: routeForAdvisoryBlocker(text, projectId),
      })
    })
  }

  const latestReport = reports.status === 'loaded' ? reports.value[0] : undefined
  if (latestReport) {
    latestReport.checks
      .filter((check) => check.severity === 'blocker')
      .forEach((check, index) => {
        items.push({
          id: `acceptance-${check.check_id}-${index}`,
          origin: 'acceptance',
          title: check.title,
          evidence: check.summary,
          missing: check.remediation[0] || 'No remediation step was recorded with this check.',
          remediation: check.remediation,
          waitingOn: latestReport.stale ? 'A fresh acceptance run for the current package' : undefined,
          action: { label: 'Open acceptance workflow', to: `/studio/screening-room?project_id=${encodeURIComponent(projectId || '')}` },
        })
      })
  }

  dependencies
    .filter((row) => row.state === 'blocked' || row.state === 'stale' || row.state === 'missing')
    .forEach((row) => {
      items.push({
        id: `dependency-${row.id}`,
        origin: 'dependency',
        title: `${row.name} — ${STATE_LABEL[row.state].toLowerCase()}`,
        evidence: row.detail,
        missing: row.dependsOn,
        remediation: [],
        waitingOn: row.waitingOn,
        action: row.action ? { label: row.action.label, to: `${row.action.to}?project_id=${encodeURIComponent(projectId || '')}` } : undefined,
      })
    })

  return items
}

function Panel({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section aria-label={title} className="border-t border-white/10 pt-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-200/80">{title}</h2>
        {aside}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )
}

function StateChip({ state }: { state: EvidenceState }) {
  return (
    <span data-state={state} className={`inline-flex shrink-0 items-center rounded border px-2 py-1 text-[10px] uppercase tracking-[0.12em] ${STATE_TONE[state]}`}>
      {STATE_LABEL[state]}
    </span>
  )
}

function EngineEvidence({ projectId, projectTitle, projectError }: { projectId: string; projectTitle: string; projectError: string }) {
  const scope = useRef(projectId)

  const [scenes, setScenes] = useState<LoadState<Scene[]>>(empty())
  const [jobs, setJobs] = useState<LoadState<RenderJob[]>>(empty())
  const [cut, setCut] = useState<LoadState<FilmCutVersion>>(empty())
  const [delivery, setDelivery] = useState<LoadState<AssemblyStatusResponse>>(empty())
  const [packages, setPackages] = useState<LoadState<FinalShortFilmPackage[]>>(empty())
  const [reports, setReports] = useState<LoadState<ProductionAcceptanceReport[]>>(empty())
  const [summary, setSummary] = useState<LoadState<ProductionAcceptanceSummary>>(empty())
  const [gate, setGate] = useState<LoadState<StudioDecisionGate>>(empty())
  const [guard, setGuard] = useState<LoadState<PackageApprovalGuardResult | null>>(empty())
  const [screening, setScreening] = useState<LoadState<ScreeningManifest>>(empty())
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    if (!projectId) return
    const requestedProjectId = projectId
    scope.current = projectId
    const guarded = <T,>(promise: Promise<T>, set: (state: LoadState<T>) => void, message: string): Promise<T | null> =>
      promise.then((value) => { if (scope.current === requestedProjectId) set({ status: 'loaded', value }); return value })
        .catch((error: unknown) => {
          if (scope.current === requestedProjectId) set({ status: 'unavailable', message: error instanceof Error ? error.message : message })
          return null
        })

    const [packageRows] = await Promise.all([
      guarded(listFinalShortFilmPackagesForProject(projectId).then((result) => result.packages), setPackages, 'Final package records unavailable'),
      guarded(listScenes(projectId).then((result) => {
        if (result.error) throw new Error(result.error)
        return result.scenes
      }), setScenes, 'Scene list unavailable'),
      guarded(listRenderJobs(projectId), setJobs, 'Render queue unavailable'),
      guarded(getCurrentFilmCut(projectId).then((result) => result.film_cut), setCut, 'Film Cut unavailable'),
      guarded(getAssemblyStatus(projectId), setDelivery, 'Delivery status unavailable'),
      guarded(listProductionAcceptanceReports(projectId).then((result) => result.reports), setReports, 'Acceptance evidence unavailable'),
      guarded(getLatestProductionAcceptanceSummary(projectId).then((result) => result.summary), setSummary, 'Acceptance summary unavailable'),
      guarded(getProjectDecisionGate(projectId), setGate, 'Decision gate unavailable'),
      guarded(getScreeningManifest(projectId, false), setScreening, 'Screening registration unavailable'),
    ])

    const latestPackageId = packageRows && packageRows[0] ? packageRows[0].package_id : ''
    await guarded(
      latestPackageId
        ? getPackageAcceptanceGuard(latestPackageId).then((result) => result.guard)
        : Promise.resolve<PackageApprovalGuardResult | null>(null),
      setGuard,
      'Approval guard unavailable',
    )
  }, [projectId])

  useEffect(() => {
    void load()
  }, [load])

  const dependencies = useMemo(() => buildDependencies({ scenes, jobs, cut, delivery, packages, reports, guard, screening }), [scenes, jobs, cut, delivery, packages, reports, guard, screening])
  const gateFlow = useMemo(() => buildPipelineGateFlow({ jobs, gate, reports }), [jobs, gate, reports])
  const integrityAccent = getProceduralRoomStyle('integrity').tokens.accent
  const normalizationWarningCount = useMemo(() => gateFlow
    .flatMap((stage) => stage.logs)
    .filter((entry) => /normali|auto-optimi|optim/i.test(`${entry.label} ${entry.detail}`)).length, [gateFlow])
  const blockers = useMemo(() => buildBlockers({ projectId, gate, reports, dependencies }), [projectId, gate, reports, dependencies])

  const reportRows = useMemo(() => (reports.status === 'loaded' ? reports.value : []), [reports])
  const latestReport = reportRows[0]
  const checks = useMemo(() => (latestReport ? latestReport.checks : []), [latestReport])
  const severityCounts = useMemo(() => {
    const counts: Record<string, number> = { blocker: 0, warning: 0, pass: 0, not_applicable: 0 }
    checks.forEach((check) => { counts[check.severity] = (counts[check.severity] || 0) + 1 })
    return counts
  }, [checks])

  const packageRows = packages.status === 'loaded' ? packages.value : []
  const latestPackage = packageRows[0]
  const guardValue = guard.status === 'loaded' ? guard.value : null
  const acceptanceEstablished = Boolean(latestReport)
  const readinessEstablished = acceptanceEstablished && Boolean(guardValue?.allowed) && Boolean(screening.status === 'loaded' && screening.value.current_final_output)

  const verdicts = [
    {
      key: 'gate',
      label: 'Advisory decision gate',
      value: gate.status === 'loaded' ? gate.value.gate_status.replace('_', ' ') : gate.status === 'loading' ? 'Loading…' : 'Unavailable',
      tone: gate.status === 'loaded'
        ? gate.value.gate_status === 'blocked' ? 'text-rose-200' : gate.value.gate_status === 'ready' ? 'text-emerald-200' : gate.value.gate_status === 'needs_review' ? 'text-amber-200' : 'text-zinc-300'
        : 'text-zinc-500',
      note: gate.status === 'loaded' ? `Advisory only · stage ${gate.value.current_stage}` : gate.status === 'unavailable' ? gate.message : 'Read-only studio gate',
    },
    {
      key: 'acceptance',
      label: 'Production Integrity acceptance',
      value: summary.status === 'loaded'
        ? `${summary.value.disposition.replace('_', ' ')}${summary.value.stale ? ' · stale' : ''}`
        : summary.status === 'loading' ? 'Loading…' : 'Unavailable',
      tone: summary.status === 'loaded'
        ? summary.value.disposition === 'not_run' ? 'text-zinc-400' : summary.value.disposition === 'ready_for_creator_approval' && !summary.value.stale ? 'text-emerald-200' : summary.value.disposition === 'blocked' || summary.value.stale ? 'text-rose-200' : 'text-amber-200'
        : 'text-zinc-500',
      note: summary.status === 'loaded'
        ? summary.value.recommended_action || 'No recommendation recorded.'
        : summary.status === 'unavailable' ? summary.message : 'Latest package-scoped report',
    },
    {
      key: 'guard',
      label: 'Current-final eligibility',
      value: guard.status === 'loaded'
        ? guardValue === null ? 'No package' : guardValue.allowed ? 'Guard allows' : `Guard ${guardValue.guard_level}s`
        : guard.status === 'loading' ? 'Loading…' : 'Unavailable',
      tone: guard.status === 'loaded'
        ? guardValue === null ? 'text-zinc-400' : guardValue.allowed ? 'text-emerald-200' : 'text-rose-200'
        : 'text-zinc-500',
      note: guard.status === 'loaded'
        ? guardValue ? guardValue.reason : 'No final package exists, so no guard was evaluated.'
        : guard.status === 'unavailable' ? guard.message : 'Backend approval guard',
    },
    {
      key: 'freshness',
      label: 'Acceptance evidence',
      value: reports.status === 'loaded'
        ? latestReport ? (latestReport.stale ? 'Stale' : 'Current') : 'None recorded'
        : reports.status === 'loading' ? 'Loading…' : 'Unavailable',
      tone: reports.status === 'loaded'
        ? !latestReport ? 'text-zinc-400' : latestReport.stale ? 'text-amber-200' : 'text-emerald-200'
        : 'text-zinc-500',
      note: reports.status === 'loaded'
        ? latestReport ? `Generated ${latestReport.generated_at || 'unknown'} by ${latestReport.generated_by || 'backend'}` : 'Acceptance has never run for this project.'
        : reports.status === 'unavailable' ? reports.message : 'Newest report first',
    },
  ]

  const loading = [scenes, jobs, cut, delivery, packages, reports, summary, gate, guard, screening].some((state) => state.status === 'loading')
  const linkClass = 'inline-flex min-h-10 items-center gap-1.5 text-sm text-cyan-200'
  const query = `?project_id=${encodeURIComponent(projectId || '')}`

  return (
    <StudioShell title="Production Integrity Engine" subtitle="Evidence, dependencies, and provenance behind every integrity decision.">
      <ProjectGuard>
        <RoomBackdrop roomKey="integrity" testid="integrity-room">
        <main className="mx-auto max-w-6xl space-y-5 px-4 pb-12 pt-4 sm:px-6">
          <header className="border-b border-white/15 pb-5" style={{ borderColor: `${integrityAccent}33` }}>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div className="min-w-0">
                <p className="text-xs uppercase tracking-[0.18em] text-violet-300/80">Verification console</p>
                <p className="mt-2 text-xs uppercase tracking-[0.15em] text-amber-200/80">{projectTitle}</p>
                <h1 className="mt-1 text-3xl font-medium text-zinc-100">Production Integrity Engine</h1>
                <p className="mt-2 max-w-2xl text-sm text-zinc-400">A read-only view of the checks, dependencies, and provenance the Studio has actually recorded. The Production Integrity Gate remains the authoritative enforcement boundary; this room never approves, repairs, or overrides anything.</p>
              </div>
              <button
                type="button"
                onClick={() => { setRefreshing(true); void load().finally(() => setRefreshing(false)) }}
                disabled={!projectId || refreshing}
                className="inline-flex min-h-11 items-center gap-2 rounded-md border border-white/15 px-4 text-sm font-medium text-zinc-200 transition-colors hover:border-white/30 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {refreshing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
                Refresh evidence
              </button>
            </div>

            <div className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {verdicts.map((verdict) => (
                <div key={verdict.key} className="border-l-2 border-white/15 pl-4" aria-label={`${verdict.label} verdict`}>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">{verdict.label}</p>
                  <p className={`mt-1.5 text-lg capitalize ${verdict.tone}`}>{verdict.value}</p>
                  <p className="mt-1 text-xs leading-relaxed text-zinc-500">{verdict.note}</p>
                </div>
              ))}
            </div>
          </header>

          {projectError && <p role="alert" className="rounded-lg border border-amber-300/20 bg-amber-300/5 p-4 text-sm text-amber-100">{projectError}</p>}
          {!projectId && !projectError && <p role="status" className="rounded-lg border border-white/10 p-4 text-sm text-zinc-400">Choose a project to inspect its recorded integrity evidence.</p>}
          {loading && <p role="status" className="flex items-center gap-2 text-sm text-zinc-400"><Loader2 size={16} className="animate-spin" />Reading persisted integrity evidence…</p>}

          <Panel title="Readiness explanation" aside={<span className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">Backend decisions only</span>}>
            <div className="space-y-4">
              <div className="border-l-2 border-white/15 pl-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="flex items-center gap-2 text-sm text-zinc-100"><ShieldCheck size={15} className="text-violet-200" />Studio Decision Gate <span className="font-mono text-[11px] text-zinc-500">(advisory)</span></p>
                  {gate.status === 'loaded' && <span className={`rounded border border-white/15 px-2 py-1 text-[10px] uppercase tracking-[0.12em] ${gate.value.gate_status === 'blocked' ? 'text-rose-200' : gate.value.gate_status === 'ready' ? 'text-emerald-200' : 'text-amber-200'}`}>{gate.value.gate_status.replace('_', ' ')}</span>}
                </div>
                {gate.status === 'unavailable' && <p role="status" className="mt-2 text-sm text-amber-100">Decision gate unavailable: {gate.message}</p>}
                {gate.status === 'loaded' && (
                  <div className="mt-3 space-y-2 text-sm">
                    <p className="text-zinc-200">{gate.value.recommended_next_action}</p>
                    <p className="text-xs text-zinc-500">Stage {gate.value.current_stage} · advisory_only {String(gate.value.advisory_only)}</p>
                    {gate.value.blockers.length + gate.value.warnings.length + gate.value.ready_signals.length === 0 && <p className="text-xs text-zinc-500">The gate recorded no blockers, warnings, or ready signals for this project.</p>}
                    <ul className="space-y-1.5 text-xs">
                      {gate.value.blockers.map((text, index) => <li key={`b-${index}`} className="flex gap-2 text-rose-200"><AlertTriangle size={14} className="mt-0.5 shrink-0" />{text}</li>)}
                      {gate.value.warnings.map((text, index) => <li key={`w-${index}`} className="flex gap-2 text-amber-200"><ShieldAlert size={14} className="mt-0.5 shrink-0" />{text}</li>)}
                      {gate.value.ready_signals.map((text, index) => <li key={`r-${index}`} className="flex gap-2 text-emerald-200"><CheckCircle2 size={14} className="mt-0.5 shrink-0" />{text}</li>)}
                    </ul>
                  </div>
                )}
              </div>

              <div className="border-l-2 border-white/15 pl-4">
                <p className="flex items-center gap-2 text-sm text-zinc-100"><ShieldCheck size={15} className="text-violet-200" />Production Integrity acceptance</p>
                {!acceptanceEstablished && reports.status === 'loaded' && (
                  <p role="status" className="mt-2 text-sm text-amber-100">Overall delivery readiness has not been established: no acceptance report exists for this project, so no package has been evaluated.</p>
                )}
                {reports.status === 'unavailable' && <p role="status" className="mt-2 text-sm text-amber-100">Acceptance evidence unavailable: {reports.message}</p>}
                {acceptanceEstablished && latestReport && (
                  <div className="mt-3 space-y-2 text-sm">
                    <p className="text-zinc-200">{latestReport.summary}</p>
                    {latestReport.co_director_note && <p className="text-xs italic text-zinc-400">{latestReport.co_director_note}</p>}
                    {latestReport.stale && latestReport.stale_reasons.length > 0 && (
                      <ul className="space-y-1 text-xs text-amber-100">{latestReport.stale_reasons.map((reason) => <li key={reason}>· {reason}</li>)}</ul>
                    )}
                    <p className="text-xs text-zinc-500">Report <span className="font-mono">{latestReport.acceptance_id}</span> · package <span className="font-mono">{latestReport.package_id || 'none'}</span> · disposition {latestReport.disposition} · generated {latestReport.generated_at || 'unknown'}</p>
                  </div>
                )}
              </div>

              <div className="border-l-2 border-white/15 pl-4">
                <p className="flex items-center gap-2 text-sm text-zinc-100"><ShieldCheck size={15} className="text-violet-200" />Overall readiness</p>
                {readinessEstablished ? (
                  <p className="mt-2 text-sm text-emerald-200">The backend has recorded every element it requires: a current acceptance report, an allowed approval guard, and a selected current final.</p>
                ) : (
                  <p role="status" className="mt-2 text-sm text-amber-100">
                    Overall readiness has not been established. This room reports the backend's own records and does not compute a readiness score.
                    {!acceptanceEstablished && ' No acceptance report exists.'}
                    {acceptanceEstablished && !guardValue?.allowed && ' The package approval guard has not allowed approval.'}
                    {Boolean(guardValue?.allowed) && !(screening.status === 'loaded' && screening.value.current_final_output) && ' No current final is selected in Screening.'}
                  </p>
                )}
                <p className="mt-2 text-xs text-zinc-500">A healthy-looking console is not evidence of readiness. Only the records above establish state, and the Production Integrity Gate enforces them on the server.</p>
              </div>
            </div>
          </Panel>

          <Panel
            title="Validation evidence"
            aside={<span className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">{latestReport ? `${checks.length} checks evaluated` : 'No report'}</span>}
          >
            {reports.status === 'unavailable' && <p role="status" className="text-sm text-amber-100">Acceptance evidence unavailable: {reports.message}</p>}
            {reports.status === 'loaded' && !latestReport && (
              <p role="status" className="text-sm text-zinc-400">No checks have been evaluated for this project. An absent report is unknown evidence, not a pass.</p>
            )}
            {latestReport && (
              <>
                <div className="flex flex-wrap gap-3">
                  {SEVERITY_ORDER.map((severity) => (
                    <span key={severity} data-severity-count={severity} className={`rounded border px-2 py-1 text-xs ${SEVERITY_TONE[severity]}`}>
                      <span className="tabular-nums">{severityCounts[severity] || 0}</span> {severity === 'not_applicable' ? 'not applicable' : `${severity}${(severityCounts[severity] || 0) === 1 ? '' : 's'}`}
                    </span>
                  ))}
                  <span className="rounded border border-white/15 px-2 py-1 text-xs text-zinc-400"><span className="tabular-nums">{checks.length}</span> evaluated</span>
                </div>
                <p className="mt-3 text-xs leading-relaxed text-zinc-500">Only checks present in report <span className="font-mono">{latestReport.acceptance_id}</span> were evaluated. A check that does not appear here is unknown — never treat its absence as a pass.</p>

                <div className="mt-4 space-y-3">
                  {SEVERITY_ORDER.map((severity) => {
                    const group = checks.filter((check) => check.severity === severity)
                    if (group.length === 0) return null
                    return (
                      <div key={severity}>
                        <h3 className={`text-[11px] uppercase tracking-[0.16em] ${severity === 'blocker' ? 'text-rose-200' : severity === 'warning' ? 'text-amber-200' : severity === 'pass' ? 'text-emerald-200' : 'text-zinc-400'}`}>
                          {severity === 'not_applicable' ? 'Not applicable' : severity === 'pass' ? 'Passed' : severity === 'blocker' ? 'Blockers' : 'Warnings'}
                        </h3>
                        <ul className="mt-2 space-y-2">
                          {group.map((check, index) => (
                            <li key={`${check.check_id}-${index}`} data-severity={check.severity} className="border-l-2 border-white/10 pl-4 py-1">
                              <details>
                                <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2 text-sm text-zinc-100">
                                  <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] ${SEVERITY_TONE[check.severity]}`}>{check.severity}</span>
                                  <span className="min-w-0 flex-1">{check.title}</span>
                                  <span className="font-mono text-[11px] text-zinc-500">{check.check_id}@{check.check_version} · {check.category}</span>
                                  <ChevronRight size={14} className="text-zinc-500" />
                                </summary>
                                <div className="space-y-3 border-t border-white/10 px-3 py-3 text-xs">
                                  <p className="leading-relaxed text-zinc-300">{check.summary}</p>
                                  {check.co_director_note && check.co_director_note !== check.summary && <p className="italic leading-relaxed text-zinc-400">{check.co_director_note}</p>}
                                  {(check.affected_scenes.length > 0 || check.affected_shots.length > 0) && (
                                    <p className="flex flex-wrap gap-2 text-zinc-400">
                                      {check.affected_scenes.map((scene) => <span key={scene} className="rounded border border-white/15 px-1.5 py-0.5 font-mono text-[11px] text-zinc-300">{scene}</span>)}
                                      {check.affected_shots.map((shot) => <span key={shot} className="rounded border border-white/15 px-1.5 py-0.5 font-mono text-[11px] text-zinc-300">{shot}</span>)}
                                    </p>
                                  )}
                                  {check.evidence.length > 0 && (
                                    <div>
                                      <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Evidence recorded by the backend</p>
                                      <ul className="mt-1.5 space-y-1">
                                        {check.evidence.slice(0, 8).map((ref, refIndex) => (
                                          <li key={`${ref.source_type}-${ref.source_id}-${refIndex}`} className="flex flex-wrap gap-2 text-[11px]">
                                            <span className="font-mono text-violet-200">{ref.source_type}</span>
                                            {ref.source_id && <span className="font-mono text-zinc-500">{ref.source_id}</span>}
                                            {ref.field_path && <span className="text-zinc-500">{ref.field_path}</span>}
                                            {formatObserved(ref.observed_value) && <span className="text-zinc-300">{formatObserved(ref.observed_value)}</span>}
                                          </li>
                                        ))}
                                      </ul>
                                      {check.evidence.length > 8 && <p className="mt-1 text-[11px] text-zinc-500">Showing 8 of {check.evidence.length} recorded evidence references.</p>}
                                    </div>
                                  )}
                                  {check.remediation.length > 0 && (
                                    <div>
                                      <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Remediation recorded by the backend</p>
                                      <ul className="mt-1.5 space-y-1 text-zinc-300">{check.remediation.map((step) => <li key={step}>· {step}</li>)}</ul>
                                    </div>
                                  )}
                                  <p className="text-[11px] text-zinc-500">Source: {latestReport.generated_by || 'production_acceptance_service'} · report generated {latestReport.generated_at || 'at an unstamped time'} · check version {check.check_version}</p>
                                </div>
                              </details>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )
                  })}
                </div>

                {reportRows.length > 1 && (
                  <details className="mt-4 border-t border-white/10 pt-3 text-xs text-zinc-500">
                    <summary className="cursor-pointer">Earlier acceptance reports ({reportRows.length - 1})</summary>
                    <ul className="mt-2 space-y-1">
                      {reportRows.slice(1, 6).map((report) => (
                        <li key={report.acceptance_id} className="flex flex-wrap gap-2">
                          <span className="font-mono text-zinc-400">{report.acceptance_id}</span>
                          <span>{report.disposition}{report.stale ? ' · stale' : ''}</span>
                          <span className="text-zinc-600">package {report.package_id || 'none'}</span>
                          <span className="text-zinc-600">{report.generated_at || 'unstamped'}</span>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </>
            )}
          </Panel>

          <Panel title="Pipeline gate flow" aside={<span className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">Recorded evidence per stage</span>}>
            <p data-testid="socket-isolation-status" role="status" className="mb-3 rounded-md border border-violet-400/35 bg-violet-500/10 px-3 py-2 text-[11px] leading-relaxed text-zinc-300 shadow-[0_0_24px_rgba(109,40,217,0.25)]">
              Socket isolation: enforced server-side (<span className="font-mono text-zinc-200">R43K_SOCKET_ONLY=1</span>) ·{' '}
              <span className="font-mono text-zinc-200">ROUTER_PAYLOAD_NORMALIZED</span>: {normalizationWarningCount} recorded normalization event{normalizationWarningCount === 1 ? '' : 's'} ·{' '}
              <a href={`/studio/integrity${query}#gate-stage-detail`} className="text-cyan-200 underline decoration-cyan-200/40 underline-offset-2 hover:text-cyan-100">per-stage preflight logs below</a>. Select a node for the full record.
            </p>
            <PipelineGateFlow stages={gateFlow} loading={jobs.status === 'loading'} projectId={projectId} />
          </Panel>

          <Panel title="Dependency inspection" aside={<span className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">Ordered by the backend contract</span>}>
            <ol className="space-y-3">
              {dependencies.map((row) => (
                <li key={row.id} data-dependency={row.id} className="border-l-2 border-white/10 pl-4 py-1">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="flex items-center gap-2 text-sm text-zinc-100">{row.name}</p>
                      <p className="mt-1 text-xs leading-relaxed text-zinc-400">{row.detail}</p>
                      <p className="mt-1 text-[11px] text-zinc-500">Evidence: {row.evidenceSource}</p>
                      <p className="mt-1 text-[11px] text-zinc-500">What depends on it: {row.dependsOn}</p>
                      {row.waitingOn && <p className="mt-1 flex items-center gap-1.5 text-[11px] text-amber-200"><Clock3 size={12} />Waiting on: {row.waitingOn} — the creator cannot advance this line until that prerequisite is satisfied.</p>}
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-2">
                      <StateChip state={row.state} />
                      {row.action && (
                        <Link className="text-xs text-cyan-200" to={`${row.action.to}?project_id=${encodeURIComponent(projectId || '')}`}>
                          {row.action.label} <ArrowRight size={12} className="inline" />
                        </Link>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </Panel>

          <Panel title="Provenance & continuity" aside={<span className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">Recorded relationships only</span>}>
            {!latestReport && (
              <p role="status" className="text-sm text-zinc-400">
                Acceptance provenance is only recorded when acceptance runs. No report exists for this project, so package fingerprints, input hashes, and lineage cannot be shown here.
              </p>
            )}
            {latestReport && (
              <div className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="border-l-2 border-white/10 pl-4 py-1">
                    <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Acceptance context</p>
                    <ul className="mt-2 space-y-1 text-xs text-zinc-300">
                      <li>Package <span className="font-mono text-zinc-100">{latestReport.context.package_id || 'none'}</span></li>
                      <li>Final output <span className="font-mono break-all text-zinc-100">{latestReport.context.final_output_url || 'none recorded'}</span></li>
                      <li>Output fingerprint <span className="font-mono break-all text-zinc-100">{latestReport.context.final_output_fingerprint || 'not recorded'}</span></li>
                      <li>Input hash <span className="font-mono break-all text-zinc-100">{latestReport.context.acceptance_input_hash || 'not recorded'}</span></li>
                      <li>Review <span className="font-mono text-zinc-100">{latestReport.context.review_id || 'none'}</span> · {latestReport.context.review_decision || 'no decision'}</li>
                    </ul>
                  </div>
                  <div className="border-l-2 border-white/10 pl-4 py-1">
                    <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Lineage captured with the report</p>
                    <ul className="mt-2 space-y-1 text-xs text-zinc-300">
                      <li><span className="tabular-nums">{latestReport.context.scene_ids.length}</span> scene IDs · <span className="tabular-nums">{latestReport.context.render_job_ids.length}</span> render jobs · <span className="tabular-nums">{latestReport.context.revision_ids.length}</span> revisions</li>
                      <li>Evidence counts: {Object.entries(latestReport.context.evidence_counts).map(([key, value]) => `${key} ${value}`).join(' · ') || 'none recorded'}</li>
                    </ul>
                    {(latestReport.context.scene_ids.length > 0 || latestReport.context.render_job_ids.length > 0) && (
                      <details className="mt-2 text-[11px] text-zinc-500">
                        <summary className="cursor-pointer">Identifiers</summary>
                        <p className="mt-1 break-words font-mono">{[...latestReport.context.scene_ids, ...latestReport.context.render_job_ids, ...latestReport.context.revision_ids].join(', ')}</p>
                      </details>
                    )}
                  </div>
                </div>

                <div className="border-l-2 border-white/10 pl-4 py-1">
                  <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Editorial & delivery lineage</p>
                  <ul className="mt-2 space-y-1 text-xs text-zinc-300">
                    <li>Current cut <span className="font-mono text-zinc-100">{cut.status === 'loaded' ? `${cut.value.cut_id} v${cut.value.version_number} (${cut.value.status})` : cut.status === 'unavailable' ? `unavailable — ${cut.message}` : 'not loaded'}</span></li>
                    <li>Package source cut <span className="font-mono text-zinc-100">{latestPackage ? String((latestPackage.metadata || {}).source_cut_id || 'not recorded on this package') : 'no package recorded'}</span></li>
                    <li>Delivery manifest hash <span className="font-mono break-all text-zinc-100">{latestPackage ? String((latestPackage.metadata || {}).delivery_manifest_hash || 'not recorded on this package') : 'no package recorded'}</span></li>
                  </ul>
                  <p className="mt-2 flex items-start gap-1.5 text-[11px] text-zinc-500"><Link2 size={12} className="mt-0.5 shrink-0" />Identifiers above come from stored records. Where a field is absent it is reported as not recorded rather than inferred.</p>
                </div>

                <div className="border-l-2 border-white/10 pl-4 py-1">
                  <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Screening lineage</p>
                  {screening.status === 'unavailable' && <p className="mt-2 text-xs text-amber-100">Screening registration unavailable: {screening.message}</p>}
                  {screening.status === 'loaded' && (
                    <>
                      <p className="mt-2 text-xs text-zinc-300">
                        {screening.value.outputs.length} registered output{screening.value.outputs.length === 1 ? '' : 's'} ·
                        {' '}{screening.value.current_final_output ? `current final ${screening.value.current_final_output.screening_output_id} from ${screening.value.current_final_output.source_type}:${screening.value.current_final_output.source_id}` : 'no current final selected'}
                      </p>
                      <details className="mt-2 text-[11px] text-zinc-500">
                        <summary className="cursor-pointer">Output sources</summary>
                        <ul className="mt-1 space-y-1">
                          {screening.value.outputs.slice(0, 12).map((output) => (
                            <li key={output.screening_output_id} className="flex flex-wrap gap-2">
                              <span className="font-mono text-violet-200">{output.source_type}</span>
                              <span className="font-mono text-zinc-500">{output.source_id}</span>
                              <span>{output.output_type}</span>
                              <span className={output.media_status === 'available' ? 'text-emerald-200' : 'text-amber-200'}>media {output.media_status}</span>
                            </li>
                          ))}
                        </ul>
                      </details>
                    </>
                  )}
                </div>
              </div>
            )}
          </Panel>

          <Panel title="Blockers & resolution" aside={<span className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">{blockers.length} recorded</span>}>
            {gate.status === 'unavailable' && reports.status === 'unavailable' && (
              <p role="status" className="text-sm text-amber-100">Blocker sources unavailable: decision gate and acceptance evidence both failed to load. Absence of blockers here does not mean the project is clear.</p>
            )}
            {blockers.length === 0 && gate.status === 'loaded' && !acceptanceEstablished && (
              <p role="status" className="text-sm text-zinc-400">No blockers were recorded by the decision gate, and no acceptance report exists to evaluate. This is an absence of evidence, not a verified clear state.</p>
            )}
            {blockers.length === 0 && gate.status === 'loaded' && acceptanceEstablished && (
              <p className="text-sm text-emerald-200">No blockers in the loaded evidence: the advisory gate reported none and the latest acceptance report contains no blocker checks.</p>
            )}
            {gate.status === 'loading' && reports.status === 'loading' && <p className="text-sm text-zinc-400">Blocker evidence is loading.</p>}
            <ul className="space-y-3">
              {blockers.map((item) => (
                <li key={item.id} data-blocker-origin={item.origin} className="border-l-2 border-white/10 pl-4 py-1">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="flex items-start gap-2 text-sm text-zinc-100">
                        {item.origin === 'acceptance' ? <ShieldAlert size={15} className="mt-0.5 shrink-0 text-rose-200" /> : <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-200" />}
                        {item.title}
                      </p>
                      <p className="mt-1 pl-6 text-xs leading-relaxed text-zinc-400">{item.evidence}</p>
                      <p className="mt-1 pl-6 text-[11px] text-zinc-500">Missing or required: {item.missing}</p>
                      {item.remediation.length > 0 && (
                        <ul className="mt-1.5 space-y-1 pl-6 text-[11px] text-zinc-300">{item.remediation.map((step) => <li key={step}>· {step}</li>)}</ul>
                      )}
                      <p className="mt-1.5 pl-6 text-[11px] text-zinc-500">
                        Source: {item.origin === 'decision-gate' ? 'Studio Decision Gate (advisory)' : item.origin === 'acceptance' ? 'Production Integrity acceptance report' : 'Dependency contract'}
                        {' · '}
                        {item.waitingOn ? `Waiting on ${item.waitingOn}` : 'You can act on this now in the linked workflow'}
                      </p>
                    </div>
                    {item.action && <Link className={`${linkClass} shrink-0 text-xs`} to={item.action.to}>{item.action.label} <ArrowRight size={13} /></Link>}
                  </div>
                </li>
              ))}
            </ul>
          </Panel>

          <div className="flex flex-wrap gap-3">
            <Link className={linkClass} to={`/studio/production-desk${query}`}>Open Production Desk <ArrowRight size={14} /></Link>
            <Link className={linkClass} to={`/studio/production-board${query}`}>Open scene board <ArrowRight size={14} /></Link>
            <Link className={linkClass} to={`/studio/screening-room${query}`}>Open Screening Room <ArrowRight size={14} /></Link>
          </div>

          <p className="flex items-start gap-2 border-t border-white/10 pt-4 text-xs leading-relaxed text-zinc-500">
            <CircleHelp size={14} className="mt-0.5 shrink-0" />
            Every value on this page was read from a persisted Studio record. Nothing here approves work, runs acceptance, selects takes, alters the Film Cut, or bypasses the Production Integrity Gate.
          </p>
          <details className="text-xs text-zinc-500">
            <summary className="cursor-pointer">Project context</summary>
            <ProjectContextBar roomName="production integrity engine" />
          </details>
        </main>
        </RoomBackdrop>
      </ProjectGuard>
    </StudioShell>
  )
}

/**
 * Route entry point. The evidence console is remounted per project so a project
 * switch never mixes one film's records with another's.
 */
export default function ProductionIntegrityEngine() {
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const { activeProject } = useStudio()
  const { projectId, projectError } = useProjectRouteContext(queryProjectId)
  return (
    <EngineEvidence
      key={projectId || 'no-project'}
      projectId={projectId}
      projectTitle={activeProject?.title || projectId || 'No project selected'}
      projectError={projectError}
    />
  )
}
