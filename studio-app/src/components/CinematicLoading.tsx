type CinematicLoadingProps = {
  title?: string
  lines?: string[]
  compact?: boolean
}

const DEFAULT_LINES = [
  'Analyzing scene composition...',
  'Preparing cinematic lighting...',
  'Rendering motion frames...',
]

export default function CinematicLoading({ title = 'Cinematic Pipeline Active', lines = DEFAULT_LINES, compact = false }: CinematicLoadingProps) {
  return (
    <div className={`cinematic-loading ${compact ? 'cinematic-loading-compact' : ''}`} role="status" aria-live="polite">
      <div className="cinematic-loading-grain" />
      <div className="cinematic-loading-projector" />
      <div className="relative z-10">
        <div className="text-[10px] uppercase tracking-[0.14em] text-amber-200">{title}</div>
        <div className="mt-2 space-y-1">
          {lines.map((line) => (
            <div key={line} className="text-xs text-zinc-200">{line}</div>
          ))}
        </div>
        <div className="mt-3 flex gap-1">
          <span className="cinematic-loading-bar" />
          <span className="cinematic-loading-bar" />
          <span className="cinematic-loading-bar" />
        </div>
      </div>
    </div>
  )
}
