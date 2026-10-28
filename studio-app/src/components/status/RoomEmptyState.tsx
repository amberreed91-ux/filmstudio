import type { LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { handoffHref, type RoomEmptyState as RoomEmptyStateCopy } from '../../lib/roomHandoff'

type RoomEmptyStateProps = {
  state: RoomEmptyStateCopy
  icon: LucideIcon
  projectId?: string | null
  testId?: string
  /** Overrides the state's link when the next move is local (clear, reset). */
  action?: { label: string; onClick: () => void } | null
}

/**
 * One empty-state pattern for every pipeline room: one icon, one sentence of
 * context, one primary action. Rooms pass their copy from ROOM_EMPTY_STATES so
 * the pattern cannot drift between Previs, Scenes, Watch, and the Desk.
 */
export default function RoomEmptyState({ state, icon: Icon, projectId, testId, action }: RoomEmptyStateProps) {
  const localAction = action ?? null
  const linkAction = action === undefined ? state.action : null

  return (
    <div
      data-testid={testId}
      className="rounded-lg border border-dashed border-white/15 px-6 py-10 text-center"
    >
      <Icon size={28} aria-hidden className="mx-auto mb-3 text-zinc-500" />
      <h2 className="text-xl font-medium text-zinc-200">{state.title}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-zinc-400">{state.body}</p>
      {localAction ? (
        <button
          type="button"
          onClick={localAction.onClick}
          className="mt-5 min-h-11 rounded-md bg-amber-200 px-4 py-2 text-sm font-medium text-zinc-950"
        >
          {localAction.label}
        </button>
      ) : linkAction ? (
        <Link
          to={handoffHref(linkAction.path, projectId)}
          className="mt-5 inline-flex min-h-11 items-center rounded-md bg-amber-200 px-4 py-2 text-sm font-medium text-zinc-950"
        >
          {linkAction.label}
        </Link>
      ) : null}
    </div>
  )
}
