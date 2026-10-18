type Props = {
  /** Sum of provider-reported realized credits (already derived in lib/renderTelemetry). */
  realized: number
  /** Sum of estimates for jobs with no realized cost yet. */
  estimated: number
  /** Jobs contributing realized cost. */
  realizedJobs: number
  /** Jobs contributing estimate-only cost. */
  estimatedOnlyJobs: number
}

/**
 * Pooled compute-credit radial gauge.
 *
 * Pure presentation: every number arrives pre-derived from saved job
 * records (`creditTelemetry` in lib/renderTelemetry.ts). The pooled share is
 * realized / (realized + estimated); when nothing is priced the wheel reads
 * 0% rather than inventing a pool.
 */
export default function CreditRadialGauge({ realized, estimated, realizedJobs, estimatedOnlyJobs }: Props) {
  const pooled = realized + estimated
  const share = pooled > 0 ? (realized / pooled) * 100 : 0
  const radius = 34
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - share / 100)
  const bufferDelta = estimated - realized
  const size = 96

  return (
    <div className="flex items-center gap-4">
      <svg
        role="img"
        aria-label={`Pooled credit share: ${share.toFixed(1)} percent realized of ${pooled.toLocaleString()} pooled credits`}
        data-testid="credit-radial-gauge"
        data-pooled-share={share.toFixed(1)}
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="shrink-0"
      >
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={9} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#8B5CF6"
          strokeWidth={9}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text x={size / 2} y={size / 2 - 1} textAnchor="middle" dominantBaseline="central" fill="#E2E8F0" fontSize={15} fontWeight={700} fontFamily="'JetBrains Mono', monospace">
          {share.toFixed(1)}%
        </text>
        <text x={size / 2} y={size / 2 + 15} textAnchor="middle" dominantBaseline="central" fill="#94A3B8" fontSize={8} letterSpacing={1.5}>
          POOLED
        </text>
      </svg>
      <dl className="min-w-0 space-y-1 text-[11px]">
        <div className="flex items-baseline justify-between gap-3">
          <dt className="uppercase tracking-[0.12em] text-zinc-500">Realized CR</dt>
          <dd className="font-mono tabular-nums text-zinc-100" data-testid="credit-gauge-realized">{realized.toLocaleString()}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <dt className="uppercase tracking-[0.12em] text-zinc-500">Estimated Alloc</dt>
          <dd className="font-mono tabular-nums text-zinc-100" data-testid="credit-gauge-estimated">{estimated.toLocaleString()}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <dt className="uppercase tracking-[0.12em] text-zinc-500">Buffer Δ</dt>
          <dd className={`font-mono tabular-nums ${bufferDelta < 0 ? 'text-amber-200' : 'text-emerald-200'}`} data-testid="credit-gauge-buffer">
            {bufferDelta < 0 ? '−' : '+'}{Math.abs(bufferDelta).toLocaleString()}
          </dd>
        </div>
        <p className="pt-0.5 text-[10px] leading-snug text-zinc-600">
          {realizedJobs} realized · {estimatedOnlyJobs} estimated
        </p>
      </dl>
    </div>
  )
}
