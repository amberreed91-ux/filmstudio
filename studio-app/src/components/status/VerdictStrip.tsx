export type VerdictState = 'verified' | 'blocked' | 'stale' | 'unavailable' | 'unverified'

export type VerdictStage = {
  key: string
  label: string
  state: VerdictState
  detail: string
  note: string
}

/** Project summary strip: one verdict per stage, plain detail, no scores. */
export default function VerdictStrip({ stages }: { stages: VerdictStage[] }) {
  return (
    <div className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
      {stages.map((stage) => (
        <div key={stage.key} className="border-l-2 border-white/15 pl-4" aria-label={`${stage.label} stage`}>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">{stage.label}</p>
          <p
            className={`mt-1.5 text-lg ${
              stage.state === 'verified'
                ? 'text-emerald-200'
                : stage.state === 'blocked' || stage.state === 'stale'
                  ? 'text-amber-200'
                  : stage.state === 'unavailable'
                    ? 'text-zinc-500'
                    : 'text-zinc-200'
            }`}
          >
            {stage.detail}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-zinc-500">{stage.note}</p>
        </div>
      ))}
    </div>
  )
}
