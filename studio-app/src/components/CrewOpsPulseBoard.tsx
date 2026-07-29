import { Link } from 'react-router-dom'
import type { CrewIntelligenceOverview, StudioDecisionGate } from '../lib/studioApi'

type CrewOpsPulseBoardProps = {
  projectId: string
  decisionGate: StudioDecisionGate | null
  renderJobsCount: number
  reviewsCount: number
  packagesCount: number
  memoryRecordCount: number
  continuityIssueCount: number
  styleDriftIssueCount: number
  crewOverview?: CrewIntelligenceOverview | null
}

type DepartmentStatus = {
  name: 'Study' | 'Previs' | 'Production' | 'Screening'
  state: 'ready' | 'needs attention' | 'checking'
  summary: string
  href: string
  cta: string
}

function withProject(path: string, projectId: string): string {
  return `${path}?project_id=${encodeURIComponent(projectId)}`
}

function gateLabel(gate: StudioDecisionGate | null): string {
  const status = gate?.gate_status || 'checking'
  if (status === 'ready') return 'ready'
  if (status === 'needs_review') return 'needs attention'
  if (status === 'blocked') return 'needs attention'
  return 'checking'
}

function pulseRead(props: CrewOpsPulseBoardProps): string {
  if (props.projectId === 'demo_studio_cinematic_001' && props.packagesCount > 0 && props.reviewsCount > 0) {
    return 'The studio pipeline is assembled and ready for guided playback. Review and package states are aligned for screening.'
  }
  if (props.renderJobsCount < 1) return 'The studio needs active render output before this pipeline can move cleanly into screening.'
  if (props.packagesCount < 1 || props.reviewsCount < 1) return 'Production is moving, but review and package readiness still need attention.'
  if (props.continuityIssueCount > 0 || props.styleDriftIssueCount > 0) return 'Core pipeline is active, with creative consistency risks still under observation.'
  return 'The studio is operational and ready for guided handoff into final screening review.'
}

function buildDepartments(props: CrewOpsPulseBoardProps): DepartmentStatus[] {
  const studyReady = props.memoryRecordCount > 0
  const previsReady = props.memoryRecordCount > 0 && props.renderJobsCount > 0
  const productionReady = props.renderJobsCount > 0
  const screeningReady = props.packagesCount > 0 && props.reviewsCount > 0 && gateLabel(props.decisionGate) !== 'checking'

  return [
    {
      name: 'Study',
      state: studyReady ? 'ready' : 'checking',
      summary: studyReady ? 'Visual evidence and memory context are available.' : 'Gathering enough evidence for stronger creative guidance.',
      href: withProject('/studio/study-room', props.projectId),
      cta: 'Open Study',
    },
    {
      name: 'Previs',
      state: previsReady ? 'ready' : 'needs attention',
      summary: previsReady ? 'Shot planning context is connected to current project evidence.' : 'Previs is waiting on stronger render and evidence continuity.',
      href: withProject('/studio/previs', props.projectId),
      cta: 'Open Previs',
    },
    {
      name: 'Production',
      state: productionReady ? 'ready' : 'needs attention',
      summary: productionReady ? 'Render execution is visible with active production context.' : 'Production needs render activity before downstream handoff.',
      href: withProject('/studio/production-board', props.projectId),
      cta: 'Open Production',
    },
    {
      name: 'Screening',
      state: screeningReady ? 'ready' : 'needs attention',
      summary: screeningReady ? 'Review and package states are aligned for screening.' : 'Screening is waiting on review/package readiness.',
      href: withProject('/studio/screening-room', props.projectId),
      cta: 'Open Screening',
    },
  ]
}

function stateBadge(state: DepartmentStatus['state']): string {
  if (state === 'ready') return 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200'
  if (state === 'needs attention') return 'border-amber-400/40 bg-amber-500/15 text-amber-200'
  return 'border-zinc-500/40 bg-zinc-500/15 text-zinc-300'
}

export default function CrewOpsPulseBoard(props: CrewOpsPulseBoardProps) {
  const departments = buildDepartments(props)
  const crewDepartments = props.crewOverview?.departments?.filter((department) => (
    department.state !== 'idle' || department.last_reasoning_id || department.active_handoff_count > 0
  )) || []
  const gate = gateLabel(props.decisionGate)
  return (
    <section className="rounded-2xl border border-white/10 bg-zinc-900/70 p-4" data-testid="crew-ops-pulse-board">
      <div className="rounded-xl border border-white/10 bg-black/25 p-3">
        <div className="text-[11px] uppercase tracking-[0.14em] text-zinc-400">Production Pulse Hero</div>
        <div className="mt-2 text-sm text-zinc-200">{pulseRead(props)}</div>
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
          <div className="rounded border border-white/10 bg-white/5 px-2 py-1">Gate: <span className="text-zinc-100">{gate}</span></div>
          <div className="rounded border border-white/10 bg-white/5 px-2 py-1">Renders: <span className="text-zinc-100">{props.renderJobsCount}</span></div>
          <div className="rounded border border-white/10 bg-white/5 px-2 py-1">Reviews: <span className="text-zinc-100">{props.reviewsCount}</span></div>
          <div className="rounded border border-white/10 bg-white/5 px-2 py-1">Packages: <span className="text-zinc-100">{props.packagesCount}</span></div>
        </div>
      </div>

      <div className="mt-4">
        <div className="text-[11px] uppercase tracking-[0.14em] text-zinc-400">Department Status</div>
        <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {departments.map((department) => (
            <div key={department.name} className="rounded-lg border border-white/10 bg-black/25 p-3 text-xs">
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-zinc-100">{department.name}</div>
                <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] ${stateBadge(department.state)}`}>
                  {department.state}
                </span>
              </div>
              <p className="mt-2 text-zinc-400">{department.summary}</p>
              <Link to={department.href} className="mt-2 inline-block text-cyan-300 no-underline">
                {department.cta}
              </Link>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-white/10 bg-black/25 p-3 text-xs text-zinc-300">
        <div className="text-[11px] uppercase tracking-[0.14em] text-zinc-400">Live Ops Notes</div>
        <p className="mt-1">
          {props.decisionGate?.recommended_next_action || 'The studio is still synchronizing render, review, and package state for the next handoff.'}
        </p>
      </div>

      {props.crewOverview && (
        <div className="mt-4 rounded-lg border border-white/10 bg-black/25 p-3 text-xs text-zinc-300">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] uppercase tracking-[0.14em] text-zinc-400">Crew Intelligence</div>
            <span className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">
              {props.crewOverview.creator_attention.length} needs attention
            </span>
          </div>
          <p className="mt-1 text-zinc-300">{props.crewOverview.summary}</p>
          {crewDepartments.length > 0 && (
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {crewDepartments.slice(0, 4).map((department) => (
                <div key={department.agent_role} className="rounded border border-white/10 bg-white/5 px-2 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-zinc-100">{department.department_name}</span>
                    <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] ${department.needs_creator_attention ? stateBadge('needs attention') : stateBadge(department.active_handoff_count > 0 ? 'checking' : 'ready')}`}>
                      {department.state.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <p className="mt-1 text-zinc-400">{department.current_activity}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
