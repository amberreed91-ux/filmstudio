import { DOT_CLASS, GATE_TONE_CLASS } from './gateTones'
import { shotGateChips, type ShotGateInput } from '../../lib/statusCopy'

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
