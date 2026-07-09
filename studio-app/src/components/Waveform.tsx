interface WaveformProps {
  points?: number[]
  color?: string
  height?: number
  width?: number
}

export default function Waveform({ points = [20,35,15,40,28,50,33,45,20,38], color = '#00c8ff', height = 32, width = 120 }: WaveformProps) {
  const max = Math.max(...points)
  const step = width / (points.length - 1)
  const d = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${i * step} ${height - (p / max) * height}`)
    .join(' ')

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <defs>
        <linearGradient id={`wave-${color.replace('#','')}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="50%" stopColor={color} stopOpacity="0.8" />
          <stop offset="100%" stopColor={color} stopOpacity="0.3" />
        </linearGradient>
      </defs>
      <path d={d} stroke={color} fill="none" strokeWidth="1.5" opacity="0.8" />
    </svg>
  )
}
