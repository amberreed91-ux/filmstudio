import { Link } from 'react-router-dom'
import StudioShell from '../components/StudioShell'

export default function Study() {
  const hasScenes = localStorage.getItem('studio_scenes_generated') === '1'
  const hasApproved = localStorage.getItem('studio_approved_scenes') === '1'

  const strongestScene = hasApproved ? 'scene_003' : hasScenes ? 'scene_001' : 'n/a'
  const weakestScene = hasScenes ? 'scene_002' : 'n/a'
  const recurringIssue = hasScenes ? 'continuity drift between mid-sequence cuts' : 'no scene diagnostics yet'
  const nextLesson = hasApproved
    ? 'Refine ending cadence to strengthen emotional landing.'
    : hasScenes
      ? 'Escalate scene stakes before committing final cut.'
      : 'Process script first to unlock scene-level analysis.'

  return (
    <StudioShell title="Study Room" subtitle="Review story structure, scene health, pacing, and creative lessons.">
      <div className="w-full min-h-screen overflow-y-auto">
        <div className="mx-auto max-w-7xl space-y-6 px-6 py-6 text-zinc-100">
          <section className="cinematic-panel p-6">
            <h2 className="text-2xl font-semibold uppercase tracking-[0.14em] text-zinc-100">Study Room</h2>
            <p className="mt-2 text-sm text-zinc-300">Review story structure, scene health, pacing, and creative lessons.</p>
          </section>

          <section className="cinematic-panel p-4">
            <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Learning Cards</h3>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              {[
                { title: 'Story Structure', note: hasScenes ? 'Act pacing is readable with one mid-act drag.' : 'Awaiting script processing.' },
                { title: 'Visual Language', note: hasScenes ? 'Contrast choices support mood direction.' : 'No visual profile yet.' },
                { title: 'Continuity', note: hasScenes ? 'Two transitions need consistency fixes.' : 'No continuity data yet.' },
                { title: 'Pacing', note: hasScenes ? 'Early scenes hold longer than needed.' : 'No pacing profile yet.' },
                { title: 'Motif Tracking', note: hasScenes ? 'Motif appears but transformation is uneven.' : 'Motif evolution unavailable.' },
              ].map((card) => (
                <article key={card.title} className="rounded-xl border border-white/10 bg-black/35 p-3">
                  <div className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-100">{card.title}</div>
                  <div className="mt-2 text-xs text-zinc-300">{card.note}</div>
                </article>
              ))}
            </div>
          </section>

          <section className="cinematic-panel p-4">
            <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Current Film Insights</h3>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-lg border border-emerald-400/35 bg-emerald-500/10 px-3 py-2 text-xs">Strongest Scene: <span className="text-emerald-200">{strongestScene}</span></div>
              <div className="rounded-lg border border-rose-400/35 bg-rose-500/10 px-3 py-2 text-xs">Weakest Scene: <span className="text-rose-200">{weakestScene}</span></div>
              <div className="rounded-lg border border-amber-400/35 bg-amber-500/10 px-3 py-2 text-xs">Recurring Issue: <span className="text-amber-100">{recurringIssue}</span></div>
              <div className="rounded-lg border border-cyan-400/35 bg-cyan-500/10 px-3 py-2 text-xs">Next Lesson: <span className="text-cyan-100">{nextLesson}</span></div>
            </div>
          </section>

          <section className="cinematic-panel p-4">
            <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Review Checklist</h3>
            <div className="space-y-2 text-sm">
              {[
                'Does every scene escalate?',
                'Does the motif transform?',
                'Does the ending land?',
                'Does the cut feel coherent?',
              ].map((item) => (
                <label key={item} className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                  <input type="checkbox" className="h-4 w-4" />
                  <span className="text-zinc-200">{item}</span>
                </label>
              ))}
            </div>
          </section>

          <section className="cinematic-panel p-4">
            <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Open Rooms</h3>
            <div className="flex flex-wrap gap-2">
              <Link to="/studio/writers-room" className="rounded-md border border-cyan-300/35 bg-cyan-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline">Open Writer&apos;s Room</Link>
              <Link to="/studio/previs" className="rounded-md border border-amber-300/35 bg-amber-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-100 no-underline">Open Previs Room</Link>
              <Link to="/studio/screening-room" className="rounded-md border border-emerald-300/35 bg-emerald-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-100 no-underline">Open Screening Room</Link>
            </div>
          </section>
        </div>
      </div>
    </StudioShell>
  )
}
