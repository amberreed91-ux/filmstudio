import StudioShell from '../components/StudioShell'
import { Link } from 'react-router-dom'

export default function StudioLobby() {
  const hasScript = localStorage.getItem('studio_script_exists') === '1'
  const hasScenes = localStorage.getItem('studio_scenes_generated') === '1'
  const hasApproved = localStorage.getItem('studio_approved_scenes') === '1'
  const approvedSceneMap = (() => {
    const raw = localStorage.getItem('studio_approved_scene_map')
    if (!raw) return {} as Record<string, boolean>
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, boolean>) : {}
    } catch {
      return {} as Record<string, boolean>
    }
  })()
  const approvedCount = Object.values(approvedSceneMap).filter(Boolean).length
  const currentCut = hasApproved ? 'iteration-ready' : hasScenes ? 'draft cut' : 'none'
  const archiveSnapshots = hasScenes ? 3 : 0

  return (
    <StudioShell title="Studio Lobby" subtitle="Central room for navigating writing, previs, production, screening, and archive workflows.">
      <div className="w-full overflow-visible bg-background">
        <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6 bg-gradient-to-b from-zinc-950 via-slate-950 to-black text-zinc-100">
          <section className="rounded-2xl border border-zinc-800/70 bg-zinc-900/45 p-6 shadow-2xl backdrop-blur-md">
            <h2 className="text-2xl font-semibold tracking-wide text-zinc-100">Studio Lobby</h2>
            <p className="mt-2 text-sm text-zinc-300">Home base for your film creation workflow from script to final cut.</p>
          </section>

          <section className="rounded-2xl border border-cyan-300/25 bg-cyan-500/10 p-4 shadow-xl">
            <div className="text-xs uppercase tracking-[0.14em] text-cyan-200">Start Here</div>
            <div className="mt-1 text-sm text-zinc-100">Begin in Writer&apos;s Room</div>
            <Link to="/studio/writers-room" className="mt-3 inline-flex rounded-lg border border-cyan-300/45 bg-cyan-500/16 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline">
              Open Writer&apos;s Room
            </Link>
          </section>

          <section className="rounded-2xl border border-amber-300/20 bg-amber-500/8 p-4 shadow-xl">
            <div className="text-xs uppercase tracking-[0.14em] text-amber-200">Current Workflow</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {[
                { label: 'Script', done: hasScript },
                { label: 'Previs', done: hasScenes },
                { label: 'Review', done: hasScenes },
                { label: 'Cut', done: hasApproved },
                { label: 'Archive', done: hasScenes },
              ].map((step) => (
                <span
                  key={step.label}
                  className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${
                    step.done ? 'border-emerald-400/55 bg-emerald-500/14 text-emerald-200' : 'border-zinc-600/60 bg-zinc-800/40 text-zinc-400'
                  }`}
                >
                  {step.label}
                </span>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-white/10 bg-zinc-900/45 p-4 shadow-xl">
            <div className="text-xs uppercase tracking-[0.14em] text-zinc-300">Recent Studio State</div>
            <div className="mt-3 grid grid-cols-1 gap-3 text-xs sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">Scenes Generated: <span className="text-zinc-100">{hasScenes ? 'yes' : 'no'}</span></div>
              <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">Approved Scenes: <span className="text-zinc-100">{approvedCount}</span></div>
              <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">Current Cut: <span className="text-zinc-100">{currentCut}</span></div>
              <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">Archive Snapshots: <span className="text-zinc-100">{archiveSnapshots}</span></div>
            </div>
          </section>

          <section className="rounded-2xl border border-white/10 bg-zinc-900/45 p-4 shadow-xl">
            <div className="text-xs uppercase tracking-[0.14em] text-zinc-300">Room Directory</div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {[
                { title: "Writer's Room", desc: 'Draft and process your script.', to: '/studio/writers-room' },
                { title: 'Previs Room', desc: 'Review scenes, visuals, and suggestions.', to: '/studio/previs' },
                { title: 'Production Board', desc: 'Track scene readiness and blockers.', to: '/studio/production-board' },
                { title: 'Screening Room', desc: 'Play and evaluate the current cut.', to: '/studio/screening-room' },
                { title: 'Archive', desc: 'Review snapshots and version history.', to: '/studio/archive' },
              ].map((room) => (
                <div key={room.title} className="rounded-xl border border-white/10 bg-black/35 p-3">
                  <div className="text-sm font-semibold text-zinc-100">{room.title}</div>
                  <div className="mt-1 text-xs text-zinc-300">{room.desc}</div>
                  <Link to={room.to} className="mt-3 inline-flex rounded-md border border-amber-300/35 bg-amber-500/12 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-100 no-underline">
                    Open Room
                  </Link>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </StudioShell>
  )
}
