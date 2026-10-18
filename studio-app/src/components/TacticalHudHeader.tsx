/**
 * Tactical HUD header — Fee Fee Anne Studios soundstage lobby.
 * Ports the standalone ANIMATION_8 top security bar: quantum hash,
 * studio.db isolation flag, R43K socket guard, latency counter.
 * Display-only; no backend or storage access.
 */
export default function TacticalHudHeader() {
  return (
    <header
      data-testid="tactical-hud-header"
      className="z-20 flex h-10 shrink-0 items-center justify-between border-b border-purple-950/80 bg-[#070312]/90 px-4 text-[11px] tracking-wider"
    >
      <div className="flex items-center space-x-3 font-mono text-purple-300/80">
        <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
        <span className="font-bold text-purple-400">QUANTUM SECURITY:</span>
        <span className="text-slate-400">HASH: 09F41-EE06-CC02</span>
        <span className="text-purple-900">|</span>
        <span className="text-slate-400">
          SVRC: <span className="text-purple-300">studio.db</span>
        </span>
        <span className="rounded border border-purple-800/50 bg-purple-950/80 px-1.5 py-0.5 text-[10px] text-purple-300">
          [ISOLATED]
        </span>
      </div>
      <div className="flex items-center space-x-2 text-xs font-bold tracking-[0.25em] text-white">
        <span className="text-purple-500">[</span>
        <span className="bg-gradient-to-r from-purple-200 via-white to-purple-200 bg-clip-text font-mono font-extrabold tracking-widest text-transparent">
          FEE FEE ANNE STUDIOS
        </span>
        <span className="text-purple-500">]</span>
      </div>
      <div className="flex items-center space-x-3 font-mono text-[11px]">
        <div className="flex items-center space-x-1.5 rounded border border-purple-800/40 bg-purple-950/60 px-2 py-0.5 text-purple-300">
          <span className="text-purple-400">R43K_SOCKET_ONLY=1</span>
          <span className="font-bold text-emerald-400">[STRICT]</span>
        </div>
        <div className="text-slate-400">
          LATENCY: <span className="font-semibold text-emerald-400">1.4ms</span>
        </div>
      </div>
    </header>
  )
}
