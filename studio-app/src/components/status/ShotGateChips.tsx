import { DOT_CLASS, GATE_TONE_CLASS, type GateTone } from './gateTones'

/**
 * Minimal structural shot for gate chips. Both the Desk board aggregate
 * (`DeskGateShot`) and the Engine integrity-gates view satisfy this shape,
 * so the same chips render in both rooms.
 */
export type ShotGateInput = {
  d4_ready?: boolean
  d6_ready?: boolean
  setting_anchor?: string
  binding_confirmation?: string
  has_media?: boolean
  latest_job_status?: string | null
}

export type GateChip = { key: string; label: string; tone: GateTone }

/** Plain gate chips: icon + color + one short label each. Anchor "unknown" is neutral, never a stop sign. */
export function shotGateChips(shot: ShotGateInput): Array<GateChip> {
  const d4 = shot.d4_ready
    ? { key: 'd4', label: 'Image ready', tone: 'ok' as GateTone }
    : { key: 'd4', label: 'Image waiting', tone: 'waiting' as GateTone }
  const d6 = shot.d6_ready
    ? { key: 'd6', label: 'Words ready', tone: 'ok' as GateTone }
    : { key: 'd6', label: 'Words waiting', tone: 'waiting' as GateTone }
  const anchor =
    shot.setting_anchor === 'set'
      ? { key: 'anchor', label: 'Look set', tone: 'ok' as GateTone }
      : shot.setting_anchor === 'blocked'
        ? { key: 'anchor', label: 'Look needed', tone: 'waiting' as GateTone }
        : { key: 'anchor', label: "Can't check", tone: 'idle' as GateTone }
  const confirmed = String(shot.binding_confirmation || 'missing').toLowerCase() === 'confirmed'
    ? { key: 'confirm', label: 'Confirmed', tone: 'ok' as GateTone }
    : String(shot.binding_confirmation || 'missing').toLowerCase() === 'missing'
      ? { key: 'confirm', label: 'Not confirmed yet', tone: 'idle' as GateTone }
      : { key: 'confirm', label: 'Changed since confirmed', tone: 'waiting' as GateTone }
  const job = shot.has_media
    ? { key: 'job', label: 'Media ready', tone: 'ok' as GateTone }
    : String(shot.latest_job_status || '').toLowerCase() === 'failed'
      ? { key: 'job', label: 'Try again', tone: 'attention' as GateTone }
      : ['pending', 'queued', 'rendering'].includes(String(shot.latest_job_status || '').toLowerCase())
        ? { key: 'job', label: 'Making now', tone: 'waiting' as GateTone }
        : { key: 'job', label: 'No media yet', tone: 'idle' as GateTone }
  return [d4, d6, anchor, confirmed, job]
}

export default function ShotGateChips({ shot }: { shot: ShotGateInput }) {
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {shotGateChips(shot).map((gate) => (
        <span
          key={gate.key}
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${GATE_TONE_CLASS[gate.tone]}`}
        >
          <span aria-hidden="true" className={`inline-block h-1.5 w-1.5 rounded-full ${DOT_CLASS[gate.tone]}`} />
          {gate.label}
        </span>
      ))}
    </div>
  )
}
