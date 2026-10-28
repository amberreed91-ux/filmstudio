type Props = {
  /** Render durations in seconds, oldest first (from durationTelemetry). */
  samples: number[]
  /** Accessible description of what the curve shows. */
  label: string
  height?: number
  width?: number
}

/**
 * Render-latency vector curve with peak markers.
 *
 * Pure presentation over the same recorded duration samples as the desk's
 * duration trend. Peaks (local maxima, plus the global max on flat runs)
 * carry native SVG tooltips with their value and cadence position. Renders
 * nothing chart-like when no sample is recorded.
 */
export default function LatencyVectorSparkline({ samples, label, height = 64, width = 280 }: Props) {
  if (samples.length === 0) {
    return <p className="text-xs text-zinc-500">No latency samples are recorded in this window.</p>
  }

  const max = Math.max(...samples)
  const min = Math.min(...samples)
  const span = max - min
  const point = (value: number, index: number) => {
    const x = samples.length === 1 ? width / 2 : (index / (samples.length - 1)) * width
    const normalized = span === 0 ? 0.5 : (value - min) / span
    return { x, y: height - 4 - normalized * (height - 8) }
  }
  const coords = samples.map(point)
  const path = coords.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(2)},${c.y.toFixed(2)}`).join(' ')

  const isPeak = (index: number) => {
    if (samples.length === 1) return true
    const value = samples[index]
    if (value !== max) {
      const left = index === 0 ? Number.NEGATIVE_INFINITY : samples[index - 1]
      const right = index === samples.length - 1 ? Number.NEGATIVE_INFINITY : samples[index + 1]
      return value > left && value >= right
    }
    return true
  }
  const peaks = samples.map((_, index) => index).filter(isPeak)

  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className="w-full overflow-visible"
      data-testid="latency-vector-sparkline"
      data-samples={samples.length}
    >
      <line x1={0} y1={height - 1} x2={width} y2={height - 1} stroke="currentColor" strokeOpacity={0.15} strokeWidth={1} />
      <path d={path} fill="none" stroke="#8B5CF6" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" opacity={0.9} />
      {peaks.map((index) => {
        const c = coords[index]
        return (
          <g key={index} data-testid="latency-vector-peak">
            <title>{`Peak ${Math.round(samples[index])}s · position ${index + 1} of ${samples.length}`}</title>
            <circle cx={c.x} cy={c.y} r={6} fill="rgba(245,158,11,0.15)" />
            <circle cx={c.x} cy={c.y} r={2.5} fill="#F59E0B" />
          </g>
        )
      })}
    </svg>
  )
}
