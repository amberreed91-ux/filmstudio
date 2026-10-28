import { ArrowRight, ChevronDown } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import type { MouseEvent } from 'react'
import { withProductionContext } from '../lib/projectContext'

type ProductionContext = { projectId?: string | null; sceneId?: string | null; shotNumber?: number | null }

const stages = [
  { title: 'Overview', route: '/studio/overview', purpose: 'Check project health, active risks, and room-level progress at a glance.' },
  { title: 'Prepare', route: '/studio/study-room', purpose: 'Add the Bibles and references that define your film.' },
  { title: 'Write', route: '/studio/writers-room', purpose: 'Shape the script, prepare profiles, and lock character looks.' },
  { title: 'Storyboard & render', route: '/studio/previs', purpose: 'Approve the storyboard, direct each take, and assemble the scene.' },
  { title: 'Review & deliver', route: '/studio/screening-room', purpose: 'Watch your footage, make revisions, and prepare the final film.' },
]

function currentStage(pathname: string): number {
  if (pathname.includes('/overview')) return 0
  if (pathname.includes('/study-room')) return 1
  if (pathname.includes('/writers-room')) return 2
  if (pathname.includes('/previs') || pathname.includes('/development-room')) return 3
  if (pathname.includes('/screening-room')) return 4
  return -1
}

function supportFor(pathname: string) {
  if (pathname.includes('/universe'))
    return { title: 'Story atlas', purpose: 'Explore relationships here. Prepare profiles and lock physical looks in The Page.', next: 2 }
  if (pathname.includes('/production-board'))
    return { title: 'Production monitor', purpose: 'Check scenes and render jobs. Open a scene in Previs to direct its shots.', next: 3 }
  if (pathname.includes('/archive'))
    return { title: 'Film library', purpose: 'Browse your projects and assets. Review and finish a film in Theatre.', next: 4 }
  if (/^\/studio\/project\/[^/]+$/.test(pathname))
    return { title: 'Production workspace', purpose: 'Review production gates and keep a planning checklist for this film.', next: 0 }
  return null
}

function stageDotClass(stageIndex: number, currentIndex: number) {
  if (stageIndex === currentIndex) return 'liquid-stage-dot'
  if (stageIndex < currentIndex) return 'liquid-stage-dot liquid-stage-dot--done'
  return 'liquid-stage-dot liquid-stage-dot--idle'
}

export default function ProductionJourneyGuide({ pathname, context, beforeNavigate }: { pathname: string; context: ProductionContext; beforeNavigate?: () => Promise<boolean> }) {
  const navigate = useNavigate()
  const follow = async (event: MouseEvent<HTMLAnchorElement>, route: string) => {
    if (!beforeNavigate || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    if (await beforeNavigate()) navigate(withProductionContext(route, context))
  }
  const index = currentStage(pathname)
  const support = supportFor(pathname)
  if (index < 0 && !support) return null
  const nextIndex = index >= 0 ? Math.min(index + 1, stages.length - 1) : support!.next
  const next = stages[nextIndex]
  const link = (route: string) => withProductionContext(route, context)

  return (
    <aside aria-label="Your production path" className="px-4 py-3 md:px-6">
      <div className="liquid-panel relative mx-auto max-w-[1480px] overflow-hidden p-4 md:p-5">
        <span aria-hidden="true" className="liquid-shimmer" />
        <span aria-hidden="true" className="liquid-edge" />
        <span aria-hidden="true" className="liquid-spec" />
        <span aria-hidden="true" className="liquid-glow" />
        <div className="relative z-10 flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3">
              {index >= 0 ? (
                <>
                  <span className="liquid-chip liquid-chip--amber">Stage {index + 1} of {stages.length}</span>
                  <p className="text-sm font-semibold tracking-tight text-zinc-100">{stages[index].title}</p>
                </>
              ) : (
                <>
                  <span className="liquid-chip liquid-chip--cyan">Supporting room</span>
                  <p className="text-sm font-semibold tracking-tight text-zinc-100">{support!.title}</p>
                </>
              )}
            </div>
            <p className="mt-1.5 max-w-3xl text-xs leading-relaxed text-zinc-300/90">{index >= 0 ? stages[index].purpose : support!.purpose}</p>
          </div>
          {index !== stages.length - 1 && context.projectId && (
            <Link to={link(next.route)} onClick={(event) => void follow(event, next.route)} className="liquid-btn shrink-0">
              {index >= 0 ? 'Next: ' : 'Open '}{next.title}<ArrowRight size={13} />
            </Link>
          )}
        </div>

        {/* Pipeline level only. Deliberately unnumbered: the "Stage N of 5" chip
            above already states the position, and numbering this rail alongside
            the in-room step tabs (1-4) made two different scales look like one.
            The expanded "full production path" list below keeps its numbers. */}
        {index >= 0 && (
          <div className="relative z-10 mt-4 hidden items-center gap-2 lg:flex" role="list" aria-label="Production stages">
            {stages.map((stage, stageIndex) => (
              <div key={stage.route} className="flex flex-1 items-center gap-2" role="listitem">
                <span aria-hidden="true" className={stageDotClass(stageIndex, index)} />
                <Link
                  to={link(stage.route)}
                  onClick={(event) => void follow(event, stage.route)}
                  aria-current={stageIndex === index ? 'step' : undefined}
                  className={`min-w-0 truncate text-[11px] font-semibold uppercase tracking-[0.12em] transition-colors ${
                    stageIndex === index ? 'text-amber-100' : stageIndex < index ? 'text-emerald-200/80 hover:text-emerald-100' : 'text-zinc-500 hover:text-zinc-200'
                  }`}
                >
                  {stage.title}
                </Link>
                {stageIndex < stages.length - 1 && <span aria-hidden="true" className="liquid-stage-line ml-2 flex-1" />}
              </div>
            ))}
          </div>
        )}

        <details className="relative z-10 mt-3 w-full">
          <summary className="flex w-fit cursor-pointer list-none items-center gap-1.5 py-1 text-[11px] text-zinc-400 hover:text-zinc-200">
            See the full production path
            <ChevronDown size={12} />
          </summary>
          <ol className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {stages.map((stage, stageIndex) => {
              const isCurrent = stageIndex === index
              const isDone = stageIndex < index
              return (
                <li key={stage.route}>
                  <Link
                    to={link(stage.route)}
                    onClick={(event) => void follow(event, stage.route)}
                    aria-current={isCurrent ? 'step' : undefined}
                    className={`liquid-panel relative block overflow-hidden rounded-xl p-3 transition-transform hover:-translate-y-0.5 ${
                      isCurrent ? 'ring-1 ring-[rgba(255,209,101,0.5)]' : isDone ? 'ring-1 ring-[rgba(120,179,138,0.3)]' : 'ring-1 ring-white/[0.06]'
                    }`}
                  >
                    <span aria-hidden="true" className="liquid-edge" />
                    <span className="relative z-10 flex items-center gap-2">
                      <span aria-hidden="true" className={stageDotClass(stageIndex, index)} />
                      <span className={`text-[11px] font-semibold uppercase tracking-[0.12em] ${isCurrent ? 'text-amber-100' : isDone ? 'text-emerald-200/90' : 'text-zinc-300'}`}>{stageIndex + 1}. {stage.title}</span>
                    </span>
                    <p className="relative z-10 mt-2 text-xs leading-relaxed text-zinc-400">{stage.purpose}</p>
                  </Link>
                </li>
              )
            })}
          </ol>
          <p className="relative z-10 mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 pb-1 text-xs text-zinc-500">
            Supporting rooms
            <Link className="text-zinc-300 underline decoration-amber-200/40 underline-offset-4 hover:text-amber-100" to={link('/studio/universe-graph')} onClick={(event) => void follow(event, '/studio/universe-graph')}>Universe · story atlas</Link>
            <Link className="text-zinc-300 underline decoration-amber-200/40 underline-offset-4 hover:text-amber-100" to={link('/studio/production-board')} onClick={(event) => void follow(event, '/studio/production-board')}>Board · production monitor</Link>
            <Link className="text-zinc-300 underline decoration-amber-200/40 underline-offset-4 hover:text-amber-100" to={link('/studio/archive')} onClick={(event) => void follow(event, '/studio/archive')}>Archive · film library</Link>
          </p>
        </details>
      </div>
    </aside>
  )
}
