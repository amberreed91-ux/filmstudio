import { ArrowRight, ChevronDown } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import type { MouseEvent } from 'react'
import { withProductionContext } from '../lib/projectContext'

type ProductionContext = { projectId?: string | null; sceneId?: string | null; shotNumber?: number | null }

const stages = [
  { title: 'Prepare', route: '/studio/study-room', purpose: 'Add the Bibles and references that define your film.' },
  { title: 'Write', route: '/studio/writers-room', purpose: 'Shape the script, prepare profiles, and lock character looks.' },
  { title: 'Storyboard & render', route: '/studio/previs', purpose: 'Approve the storyboard, direct each take, and assemble the scene.' },
  { title: 'Review & deliver', route: '/studio/screening-room', purpose: 'Watch your footage, make revisions, and prepare the final film.' },
]

function currentStage(pathname: string): number {
  if (pathname.includes('/study-room')) return 0
  if (pathname.includes('/writers-room')) return 1
  if (pathname.includes('/previs') || pathname.includes('/development-room')) return 2
  if (pathname.includes('/screening-room')) return 3
  return -1
}

export default function ProductionJourneyGuide({ pathname, context, beforeNavigate }: { pathname: string; context: ProductionContext; beforeNavigate?: () => Promise<boolean> }) {
  const navigate = useNavigate()
  const follow = async (event: MouseEvent<HTMLAnchorElement>, route: string) => {
    if (!beforeNavigate || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    if (await beforeNavigate()) navigate(withProductionContext(route, context))
  }
  const index = currentStage(pathname)
  const support = pathname.includes('/universe')
    ? { title: 'Story atlas', purpose: 'Explore relationships here. Prepare profiles and lock physical looks in The Page.', next: 1 }
    : pathname.includes('/production-board')
      ? { title: 'Production monitor', purpose: 'Check scenes and render jobs. Open a scene in Previs to direct its shots.', next: 2 }
      : pathname.includes('/archive')
        ? { title: 'Film library', purpose: 'Browse your projects and assets. Review and finish a film in Theatre.', next: 3 }
        : /^\/studio\/project\/[^/]+$/.test(pathname)
          ? { title: 'Production workspace', purpose: 'Review production gates and keep a planning checklist for this film.', next: 0 }
          : null
  if (index < 0 && !support) return null
  const nextIndex = index >= 0 ? Math.min(index + 1, stages.length - 1) : support!.next
  const next = stages[nextIndex]
  const link = (route: string) => withProductionContext(route, context)

  return (
    <aside aria-label="Your production path" className="border-b border-white/10 bg-zinc-950/70 px-4 py-3 md:px-6">
      <div className="mx-auto flex max-w-[1480px] flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          <p className="text-xs font-medium text-amber-100">{index >= 0 ? `Production ${index + 1} of 4 · ${stages[index].title}` : support!.title}</p>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-zinc-400">{index >= 0 ? stages[index].purpose : support!.purpose}</p>
        </div>
        {index !== 3 && context.projectId && (
          <Link to={link(next.route)} onClick={(event) => void follow(event, next.route)} className="inline-flex shrink-0 items-center gap-2 rounded px-2 py-2 text-xs text-zinc-200 underline decoration-white/25 underline-offset-4 hover:text-amber-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-200">
            {index >= 0 ? 'Next: ' : 'Open '}{next.title}<ArrowRight size={13} />
          </Link>
        )}
        <details className="w-full">
          <summary className="flex w-fit cursor-pointer list-none items-center gap-1.5 py-1 text-[11px] text-zinc-400 hover:text-zinc-200">See the full production path<ChevronDown size={12} /></summary>
          <ol className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {stages.map((stage, stageIndex) => (
              <li key={stage.route}>
                <Link to={link(stage.route)} onClick={(event) => void follow(event, stage.route)} aria-current={stageIndex === index ? 'step' : undefined} className={`block rounded-md border px-3 py-3 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-200 ${stageIndex === index ? 'border-amber-200/30 bg-amber-200/5 text-amber-100' : 'border-white/10 text-zinc-300 hover:border-white/25'}`}>
                  <span className="font-medium">{stageIndex + 1}. {stage.title}</span><span className="mt-1 block leading-relaxed text-zinc-400">{stage.purpose}</span>
                </Link>
              </li>
            ))}
          </ol>
          <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 pb-1 text-[11px] text-zinc-500">
            Supporting rooms
            <Link className="text-zinc-300 underline underline-offset-4" to={link('/studio/universe-graph')} onClick={(event) => void follow(event, '/studio/universe-graph')}>Universe · story atlas</Link>
            <Link className="text-zinc-300 underline underline-offset-4" to={link('/studio/production-board')} onClick={(event) => void follow(event, '/studio/production-board')}>Board · production monitor</Link>
            <Link className="text-zinc-300 underline underline-offset-4" to={link('/studio/archive')} onClick={(event) => void follow(event, '/studio/archive')}>Archive · film library</Link>
          </p>
        </details>
      </div>
    </aside>
  )
}
