import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  HANDOFF_ROOMS,
  HANDOFF_STATUS,
  roomHandoffPath,
  type HandoffRoom,
  type HandoffStatus,
  type HandoffTone,
} from '../../lib/roomHandoff'

const TONE_CLASS: Record<HandoffTone, string> = {
  idle: 'border-white/15 bg-white/5 text-zinc-300',
  waiting: 'border-amber-400/40 bg-amber-500/10 text-amber-200',
  attention: 'border-rose-400/40 bg-rose-500/10 text-rose-200',
  ok: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200',
}

type RoomHandoffBadgeProps = {
  room: HandoffRoom
  status: HandoffStatus
  projectId?: string | null
  /** Optional room-specific line; falls back to the vocabulary's own detail. */
  detail?: string
}

/**
 * The same status chip and the same "Next: …" wording in every pipeline room,
 * so a creator reads one vocabulary from Previs through the Production Desk.
 */
export default function RoomHandoffBadge({ room, status, projectId, detail }: RoomHandoffBadgeProps) {
  const copy = HANDOFF_STATUS[status]
  const next = HANDOFF_ROOMS[room].next

  return (
    <div
      data-testid="room-handoff"
      data-room={room}
      data-status={status}
      className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-zinc-400"
    >
      <span role="status" className={`rounded border px-2 py-0.5 font-medium ${TONE_CLASS[copy.tone]}`}>
        {copy.label}
      </span>
      <span className="leading-relaxed text-zinc-500">{detail || copy.detail}</span>
      {next && (
        <Link
          to={roomHandoffPath(next, projectId)}
          className="inline-flex items-center gap-1 font-medium text-amber-200 underline decoration-amber-200/40 underline-offset-4 hover:text-amber-100"
        >
          Next: {HANDOFF_ROOMS[next].label}
          <ArrowRight size={12} aria-hidden />
        </Link>
      )}
    </div>
  )
}
