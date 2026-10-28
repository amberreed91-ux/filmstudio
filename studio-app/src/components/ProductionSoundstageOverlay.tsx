import { normalizeJobStatus } from '../lib/jobStatus'

export type SoundstageRig = {
  id: string
  shotId: string
  status: string
}

type Props = {
  /** Active (queued/rendering/pending) jobs to plot as camera rigs. */
  rigs: SoundstageRig[]
  /** Currently inspected job id — drives the Rig Alpha marker and focal volume. */
  selectedJobId: string | null
  /** Select a job for local inspection (same selection as the execution queue). */
  onSelect: (jobId: string) => void
}

function isActiveStatus(status: string): boolean {
  return ['pending', 'queued', 'rendering'].includes(normalizeJobStatus(status))
}

/**
 * 3D production soundstage spatial overlay.
 *
 * Presentational HUD only: isometric grid, dolly track, LiDAR sweep, and one
 * rig marker per active job. Dolly coordinates are deterministic layout slots
 * (not measured stage positions) and rig selection reuses the desk's local
 * job-inspection state. Performs no network operations.
 */
export default function ProductionSoundstageOverlay({ rigs, selectedJobId, onSelect }: Props) {
  const active = rigs.filter((rig) => isActiveStatus(rig.status)).slice(0, 8)
  const selectedIndex = Math.max(0, active.findIndex((rig) => rig.id === selectedJobId))
  const slot = (index: number) => ({
    x: 40 + ((index * 53) % 220),
    y: 44 + ((index * 37) % 72),
  })
  const selected = slot(selectedIndex)

  return (
    <div
      className="relative overflow-hidden rounded-xl border border-[#1E293B] bg-[#0B0F17]/80"
      data-testid="production-soundstage"
      role="img"
      aria-label={active.length === 0
        ? 'Soundstage overlay: no active rigs. The stage is idle.'
        : `Soundstage overlay: ${active.length} active camera rig${active.length === 1 ? '' : 's'} plotted from the live queue.`}
    >
      <svg viewBox="0 0 300 160" className="block h-44 w-full sm:h-52" aria-hidden="true">
        <defs>
          <pattern id="hud-iso-grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M0,20 L20,0 M-5,5 L5,-5 M15,25 L25,15" stroke="rgba(139,92,246,0.16)" strokeWidth="0.7" />
            <path d="M0,0 L20,20" stroke="rgba(139,92,246,0.08)" strokeWidth="0.5" />
          </pattern>
          <radialGradient id="hud-lidar-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(56,189,248,0.35)" />
            <stop offset="100%" stopColor="rgba(56,189,248,0)" />
          </radialGradient>
        </defs>

        <rect x={0} y={0} width={300} height={160} fill="url(#hud-iso-grid)" />
        <ellipse cx={150} cy={128} rx={120} ry={20} fill="none" stroke="rgba(226,232,240,0.14)" strokeWidth={1} />
        <ellipse cx={150} cy={128} rx={84} ry={13} fill="none" stroke="rgba(226,232,240,0.1)" strokeWidth={1} />
        <line x1={16} y1={128} x2={284} y2={128} stroke="rgba(245,158,11,0.4)" strokeWidth={1.5} strokeDasharray="6 4" />

        {active.map((rig, index) => {
          const p = slot(index)
          const isSelected = rig.id === selectedJobId || (selectedJobId === null && index === 0)
          return (
            <g key={rig.id}>
              <line x1={p.x} y1={128} x2={p.x} y2={p.y} stroke="rgba(148,163,184,0.35)" strokeWidth={1} />
              <rect x={p.x - 7} y={p.y - 6} width={14} height={10} rx={2} fill={isSelected ? 'rgba(139,92,246,0.5)' : 'rgba(30,41,59,0.9)'} stroke={isSelected ? '#d0bcff' : '#334155'} strokeWidth={1.2} />
              <circle cx={p.x} cy={p.y - 9} r={2.4} fill={isSelected ? '#F59E0B' : '#64748B'} />
              {isSelected ? <ellipse cx={p.x} cy={p.y} rx={20} ry={12} fill="none" stroke="rgba(245,158,11,0.65)" strokeWidth={1.2} strokeDasharray="4 3" /> : null}
            </g>
          )
        })}

        <g className="hud-lidar-sweep" style={{ transformOrigin: '252px 30px' }}>
          <circle cx={252} cy={30} r={22} fill="url(#hud-lidar-glow)" />
          <line x1={252} y1={30} x2={272} y2={18} stroke="rgba(56,189,248,0.8)" strokeWidth={1.4} />
          <circle cx={252} cy={30} r={3} fill="#38BDF8" />
        </g>
        <text x={238} y={60} fill="#7DD3FC" fontSize={7} letterSpacing={1.2} fontFamily="'JetBrains Mono', monospace">LIDAR</text>
      </svg>

      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-2.5 text-[10px] font-mono">
        <span className="rounded border border-violet-400/40 bg-black/55 px-1.5 py-0.5 uppercase tracking-[0.12em] text-violet-200" data-testid="soundstage-rig-alpha">
          Rig Alpha [Dolly] · x {selected.x} · y {selected.y}
        </span>
        <span className="rounded border border-sky-400/40 bg-black/55 px-1.5 py-0.5 uppercase tracking-[0.12em] text-sky-200">
          {active.length} active rig{active.length === 1 ? '' : 's'}
        </span>
      </div>

      <div className="absolute inset-x-0 bottom-0 flex flex-wrap gap-1.5 p-2.5">
        {active.length === 0 ? (
          <span className="text-xs text-zinc-500">Stage idle — rigs appear here while jobs queue or render.</span>
        ) : (
          active.map((rig) => (
            <button
              key={rig.id}
              type="button"
              onClick={() => onSelect(rig.id)}
              aria-pressed={rig.id === selectedJobId}
              aria-label={`Focus rig for job ${rig.shotId}`}
              data-testid={`soundstage-rig-${rig.id}`}
              className={`pointer-events-auto min-h-8 rounded border px-2 font-mono text-[10px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-200/60 ${rig.id === selectedJobId ? 'border-amber-300/60 bg-amber-300/10 text-amber-100' : 'border-white/15 bg-black/55 text-zinc-300 hover:border-white/30'}`}
            >
              {rig.shotId}
            </button>
          ))
        )}
      </div>
      <style>{`@keyframes hud-lidar-spin { to { transform: rotate(360deg); } } .hud-lidar-sweep { animation: hud-lidar-spin 5s linear infinite; } @media (prefers-reduced-motion: reduce) { .hud-lidar-sweep { animation: none; } }`}</style>
    </div>
  )
}
