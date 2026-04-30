import { useState, type ReactNode } from 'react'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { Link, matchPath, useLocation, useNavigate } from 'react-router-dom'
import Breadcrumbs from './Breadcrumbs'
import TopNav from './TopNav'
import { getRouteByPath, getRouteLabel } from '../routes'

export const AGENTS = {
  director: {
    name: 'Director',
    icon: '🎬',
    role: 'Creative vision and approval',
  },
  cinematographer: {
    name: 'Cinematographer',
    icon: '🎥',
    role: 'Visual style and framing',
  },
  editor: {
    name: 'Editor',
    icon: '✂️',
    role: 'Pacing and structure',
  },
  story_analyst: {
    name: 'Story Analyst',
    icon: '📖',
    role: 'Narrative and emotional beats',
  },
  continuity: {
    name: 'Continuity Supervisor',
    icon: '🔗',
    role: 'Consistency and logic',
  },
  archivist: {
    name: 'Memory Archivist',
    icon: '🧠',
    role: 'Reference memory and patterns',
  },
} as const

interface StudioShellProps {
  title?: string
  subtitle?: string
  children: ReactNode
}

type TabOption<T extends string> = { id: T; label: string }

export function TabGroup<T extends string>({
  value,
  options,
  onChange,
  className = '',
}: {
  value: T
  options: TabOption<T>[]
  onChange: (next: T) => void
  className?: string
}) {
  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => onChange(option.id)}
          className={`rounded-md border px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] transition-colors ${
            value === option.id ? 'border-cyan-300/60 bg-cyan-500/14 text-cyan-100' : 'border-zinc-700 bg-zinc-900/60 text-zinc-400'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function CollapsibleSection({
  title,
  children,
  defaultOpen = false,
}: {
  title: string
  children: ReactNode
  defaultOpen?: boolean
}) {
  return (
    <details open={defaultOpen} className="rounded-xl border border-zinc-700/70 bg-zinc-900/60">
      <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-300">
        {title}
      </summary>
      <div className="px-3 pb-3">{children}</div>
    </details>
  )
}

export function DropdownMenu({
  value,
  options,
  onChange,
  label,
  className = '',
}: {
  value: string
  options: Array<{ value: string; label: string }>
  onChange: (next: string) => void
  label?: string
  className?: string
}) {
  return (
    <label className={`flex items-center gap-2 ${className}`}>
      {label ? <span className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">{label}</span> : null}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-md border border-zinc-600 bg-zinc-900/80 px-2 py-1 text-[11px] text-zinc-200 focus:outline-none focus:ring-1 focus:ring-cyan-400/50"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

export function MetricCard({
  label,
  value,
  status,
  accentClass = 'text-zinc-300',
  barClass = 'from-zinc-500 to-zinc-400',
}: {
  label: string
  value: number | string
  status?: string
  accentClass?: string
  barClass?: string
}) {
  const numericValue = typeof value === 'number' ? Math.max(0, Math.min(100, value)) : 0
  return (
    <article className="rounded-2xl border border-white/10 bg-zinc-900/50 p-4 shadow-xl backdrop-blur-sm">
      <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">{label}</div>
      <div className="mt-2 flex items-end justify-between">
        <div className="text-3xl font-semibold text-zinc-100">{value}</div>
        {status ? <div className={`text-xs uppercase tracking-[0.12em] ${accentClass}`}>{status}</div> : null}
      </div>
      <div className="mt-3 h-1.5 rounded bg-zinc-800">
        <div className={`h-1.5 rounded bg-gradient-to-r ${barClass}`} style={{ width: `${numericValue}%` }} />
      </div>
    </article>
  )
}

export function EmptyStateCard({
  title,
  message,
  cta,
}: {
  title: string
  message: string
  cta?: ReactNode
}) {
  return (
    <div className="rounded-lg border border-dashed border-zinc-700 bg-black/25 px-4 py-4 text-sm text-zinc-300">
      <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">{title}</div>
      <div className="mt-1">{message}</div>
      {cta ? <div className="mt-2">{cta}</div> : null}
    </div>
  )
}

export default function StudioShell({ title, subtitle, children }: StudioShellProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const route = getRouteByPath(location.pathname)
  const breadcrumbs = (route?.breadcrumbs || [{ label: 'Studio Home' }]).filter((item, index, list) => {
    if (index === 0) return true
    const current = item.label.trim().toLowerCase()
    const previous = (list[index - 1]?.label || '').trim().toLowerCase()
    return current !== previous
  })
  const activeTitle = title || route?.title || 'Studio'
  const showBreadcrumbs =
    breadcrumbs.length > 1 ||
    breadcrumbs[0]?.label?.trim().toLowerCase() !== activeTitle.trim().toLowerCase()
  const contextualLinks = (route?.contextualLinks || []).map((link) => ({
    to: link.to,
    label: link.label || getRouteLabel(link.to),
  }))
  const projectMatch = matchPath({ path: '/studio/project/:projectId/*' }, location.pathname)
  const projectId = projectMatch?.params?.projectId
  const previsTo = projectId ? `/studio/project/${projectId}/previs` : '/studio/previs'
  const isPrevisRoute =
    Boolean(matchPath({ path: '/studio/previs', end: true }, location.pathname)) ||
    Boolean(matchPath({ path: '/studio/project/:projectId/previs', end: true }, location.pathname))
  const roomNav = [
    { label: 'Overview', to: '/studio/overview' },
    { label: 'Approval Room', to: '/studio/approval' },
    { label: "Writer's Room", to: '/studio/writers-room' },
    { label: 'Study Room', to: '/studio/study-room' },
    { label: 'Previs Room', to: previsTo },
    { label: 'Production Board', to: '/studio/production-board' },
    { label: 'Screening Room', to: '/studio/screening-room' },
    { label: 'Archive', to: '/studio/archive' },
  ]
  const [studioStatusOpen, setStudioStatusOpen] = useState(false)
  const hasGeneratedScenesFlag = localStorage.getItem('studio_scenes_generated') === '1'
  const hasApprovedScenesFlag = localStorage.getItem('studio_approved_scenes') === '1'
  const hasScriptFlag = localStorage.getItem('studio_script_exists') === '1'
  const lastScript = localStorage.getItem('studio:lastScript') || ''
  const lastBundleRaw = localStorage.getItem('studio:lastBundle') || ''
  let hasBundleScenes = false
  try {
    const parsed = JSON.parse(lastBundleRaw)
    hasBundleScenes = Array.isArray(parsed?.scenes) && parsed.scenes.length > 0
  } catch {
    hasBundleScenes = false
  }
  const approvedSceneMap = (() => {
    const raw = localStorage.getItem('studio_approved_scene_map')
    if (!raw) return {} as Record<string, boolean>
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, boolean>) : {}
    } catch {
      return {} as Record<string, boolean>
    }
  })()
  const approvedSceneCount = Object.values(approvedSceneMap).filter(Boolean).length
  const hasApprovedScenes = hasApprovedScenesFlag || approvedSceneCount > 0
  const hasScript = hasScriptFlag || lastScript.trim().length > 0
  const hasGeneratedScenes = hasGeneratedScenesFlag || hasBundleScenes
  const latestAgentAction = localStorage.getItem('studio:lastAgentAction') || ''

  const flowSteps = [
    { label: 'Script', to: '/studio/writers-room' },
    { label: 'Scenes', to: '/studio/writers-room' },
    { label: 'Previs', to: previsTo },
    { label: 'Review', to: '/studio/production-board' },
    { label: 'Cut', to: '/studio/screening-room' },
    { label: 'Archive', to: '/studio/archive' },
  ]
  const isWritersRoute = Boolean(matchPath({ path: '/studio/writers-room', end: true }, location.pathname))
  const isProductionRoute = Boolean(matchPath({ path: '/studio/production-board', end: true }, location.pathname))
  const isScreeningRoute = Boolean(matchPath({ path: '/studio/screening-room', end: true }, location.pathname))
  const isArchiveRoute = Boolean(matchPath({ path: '/studio/archive', end: true }, location.pathname))
  const activeStepIndex = isArchiveRoute
    ? 5
    : isScreeningRoute
      ? 4
      : isProductionRoute
        ? 3
        : isPrevisRoute
          ? 2
          : isWritersRoute
            ? (hasScript ? 1 : 0)
            : hasApprovedScenes
              ? 4
              : hasGeneratedScenes
                ? 2
                : hasScript
                  ? 1
                  : 0

  const nextStep = !hasScript
    ? { text: "Start by adding a script in Writer’s Room", cta: "Go to Writer's Room", to: '/studio/writers-room' }
    : !hasGeneratedScenes
      ? { text: 'Generate scenes to continue', cta: 'Generate Scenes', to: '/studio/writers-room' }
      : !hasApprovedScenes
        ? { text: 'Review and approve scenes in Previs', cta: 'Go to Previs', to: previsTo }
        : { text: 'Watch your film in Screening Room', cta: 'Go to Screening', to: '/studio/screening-room' }

  function handleBack() {
    if (window.history.length > 1) {
      navigate(-1)
      return
    }
    navigate('/studio')
  }

  const roomVisualClass =
    location.pathname.includes('/studio/overview')
      ? 'shell-overview'
      : location.pathname.includes('/studio/writers-room')
        ? 'shell-writers'
        : location.pathname.includes('/studio/previs')
          ? 'shell-previs'
          : location.pathname.includes('/studio/production-board')
            ? 'shell-production'
            : location.pathname.includes('/studio/screening-room')
              ? 'shell-screening'
              : location.pathname.includes('/studio/archive')
                ? 'shell-archive'
                : location.pathname.includes('/studio/study-room')
                  ? 'shell-study'
                  : 'shell-default'

  const currentStepLabel = flowSteps[activeStepIndex]?.label || 'Script'

  return (
    <div className={`studio-room-shell ${roomVisualClass} relative flex min-h-screen flex-col overflow-visible`} style={{ background: 'var(--bg-deep)' }}>
      <TopNav title={activeTitle} subtitle={subtitle || route?.purpose} />
      {showBreadcrumbs ? <Breadcrumbs items={breadcrumbs} /> : null}

      <div className="cinematic-panel mx-4 mt-3 px-3 py-2">
        <div className="flex min-h-[48px] flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.12em]">
          <span className="rounded border border-white/15 bg-black/25 px-2 py-1 text-zinc-100">Room: {activeTitle}</span>
          <span className="rounded border border-amber-300/35 bg-amber-500/10 px-2 py-1 text-amber-100">Current Step: {currentStepLabel}</span>
          <span className="rounded border border-cyan-300/35 bg-cyan-500/10 px-2 py-1 text-cyan-100">Next: {nextStep.text}</span>
          <span className="rounded border border-zinc-500/40 bg-zinc-700/25 px-2 py-1 text-zinc-200">Approved: {approvedSceneCount}</span>
          <button
            type="button"
            onClick={() => setStudioStatusOpen((prev) => !prev)}
            className="ml-auto rounded border border-white/20 bg-black/35 px-2.5 py-1 text-zinc-100 transition-colors hover:border-cyan-300/45"
          >
            {studioStatusOpen ? 'Collapse ▴' : 'Open ▾'}
          </button>
        </div>

        {studioStatusOpen ? (
          <div className="mt-2 max-h-[55vh] overflow-y-auto rounded-lg border border-white/10 bg-black/20 p-3">
            <div className="flex flex-wrap items-center gap-2">
              {flowSteps.map((step, index) => {
                const isCurrent = index === activeStepIndex
                const isCompleted = index < activeStepIndex
                return (
                  <div
                    key={step.label}
                    className="rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.12em]"
                    style={
                      isCurrent
                        ? { color: 'var(--text-primary)', border: '1px solid rgba(214,169,92,0.6)', background: 'rgba(214,169,92,0.16)' }
                        : isCompleted
                          ? { color: 'rgb(167 243 208)', border: '1px solid rgba(16,185,129,0.4)', background: 'rgba(16,185,129,0.12)' }
                          : { color: 'var(--text-muted)', border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.03)' }
                    }
                  >
                    {step.label}
                  </div>
                )
              })}
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                onClick={handleBack}
                title="Go back"
                className="btn-ghost text-xs px-3 py-1.5 inline-flex items-center gap-1"
                type="button"
              >
                <ArrowLeft size={12} />
                Back
              </button>
              <Link to="/studio" className="btn-ghost text-xs px-3 py-1.5 no-underline">
                Studio Home
              </Link>
              <Link
                to={nextStep.to}
                className="rounded-md border border-cyan-300/45 bg-cyan-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline"
              >
                {nextStep.cta}
              </Link>
              {contextualLinks.map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className="inline-flex items-center gap-1 rounded-lg border px-3 py-1.5 text-[11px] uppercase tracking-[0.1em] no-underline transition-all duration-200 hover:scale-[1.02]"
                  style={{ background: 'rgba(214,169,92,0.08)', color: 'var(--accent-amber)', border: '1px solid rgba(214,169,92,0.3)' }}
                >
                  {link.label}
                  <ArrowRight size={12} />
                </Link>
              ))}
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/10 pt-3">
              {roomNav.map((item) => {
                const isActive = item.label === 'Previs Room'
                  ? isPrevisRoute
                  : Boolean(matchPath({ path: item.to, end: true }, location.pathname))
                return (
                  <Link
                    key={item.label}
                    to={item.to}
                    className={`rounded-md border px-2.5 py-1.5 text-[11px] uppercase tracking-[0.12em] no-underline ${isActive ? 'border-cyan-300/55 bg-cyan-500/14 text-cyan-100' : 'border-white/10 bg-black/20 text-zinc-300'}`}
                  >
                    {item.label}
                  </Link>
                )
              })}
            </div>

            <div className="mt-3 rounded-xl border border-white/10 bg-zinc-900/35 px-4 py-3">
              <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-300">Active Crew</div>
              <div className="mt-2 grid grid-cols-1 gap-2 text-xs text-zinc-200 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded border border-white/10 bg-black/25 px-2 py-1.5">🎬 Director — reviewing scenes</div>
                <div className="rounded border border-indigo-300/30 bg-indigo-500/10 px-2 py-1.5">🎥 Cinematographer — adjusting visuals</div>
                <div className="rounded border border-cyan-300/30 bg-cyan-500/10 px-2 py-1.5">✂️ Editor — analyzing pacing</div>
                <div className="rounded border border-emerald-300/30 bg-emerald-500/10 px-2 py-1.5">🧠 Archivist — applying references</div>
              </div>
              {latestAgentAction ? <div className="mt-2 text-[11px] text-amber-200">Most recent: {latestAgentAction}</div> : null}
            </div>
          </div>
        ) : null}
      </div>

      <main className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden pb-6">
        {children}
      </main>
    </div>
  )
}
