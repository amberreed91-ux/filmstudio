type Props = {
  /** Duration samples in seconds, oldest first. */
  samples: number[]
  /** Accessible description of what the line shows. */
  label: string
  height?: number
  className?: string
}

/**
 * Minimal sparkline for render durations.
 *
 * Pure presentation: samples arrive already derived from job records
 * (`lib/renderTelemetry.ts`). Flat series render a mid-height line so a run of
 * equal durations still reads as data rather than as a missing chart.
 */
export default function RenderSparkline({ samples, label, height = 36, className = '' }: Props) {
  if (samples.length === 0) {
    return <p className="text-[11px] text-zinc-500">No completed render durations are recorded yet.</p>
  }

  const width = 160
  const max = Math.max(...samples)
  const min = Math.min(...samples)
  const span = max - min
  const points = samples.map((value, index) => {
    const x = samples.length === 1 ? width / 2 : (index / (samples.length - 1)) * width
    const normalized = span === 0 ? 0.5 : (value - min) / span
    const y = height - 3 - normalized * (height - 6)
    return `${x.toFixed(2)},${y.toFixed(2)}`
  })

  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className={`overflow-visible ${className}`}
      data-testid="render-duration-sparkline"
      data-samples={samples.length}
    >
      <line x1={0} y1={height - 1.5} x2={width} y2={height - 1.5} stroke="currentColor" strokeOpacity={0.15} strokeWidth={1} />
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        className="text-amber-200/80"
      />
      {samples.length === 1 ? <circle cx={width / 2} cy={points[0].split(',')[1]} r={2} className="fill-amber-200" /> : null}
    </svg>
  )
}
