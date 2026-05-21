import { Link } from 'react-router-dom'

type PrevisCinematicShowcaseProps = {
  projectId: string
  sceneId: string
  sceneTitle: string
  cinematicIntent: string
  emotionalBeat: string
  referenceConfidenceLabel: string
  currentStatus: string
  hasDirectorSignature: boolean
  relatedMemoryCount: number
  continuityIssueCount: number
  styleDriftIssueCount: number
  visualEvidenceCount: number
  decisionGateStatus: string
  isDemoProject: boolean
}

function withProject(path: string, projectId: string): string {
  return `${path}?project_id=${encodeURIComponent(projectId)}`
}

function shotToCutLabel(props: Pick<PrevisCinematicShowcaseProps, 'hasDirectorSignature' | 'relatedMemoryCount' | 'continuityIssueCount' | 'styleDriftIssueCount' | 'visualEvidenceCount'>): string {
  if (props.visualEvidenceCount < 1 || props.relatedMemoryCount < 1) return 'Needs visual evidence'
  if (props.continuityIssueCount > 0) return 'Continuity risk'
  if (props.styleDriftIssueCount > 0) return 'Style drift watch'
  if (props.hasDirectorSignature) return 'Strong alignment'
  return 'Developing alignment'
}

function coDirectorNote(props: Pick<PrevisCinematicShowcaseProps, 'isDemoProject' | 'continuityIssueCount' | 'styleDriftIssueCount' | 'decisionGateStatus' | 'relatedMemoryCount'>): string {
  if (props.isDemoProject && props.relatedMemoryCount > 0) {
    return 'The Studio has enough visual memory to begin shaping the scene. Shot intent is aligned with the current director signature. Move to Production Board when the preview plan feels ready to render.'
  }
  if (props.continuityIssueCount > 0) {
    return 'Before production, resolve continuity risks so this scene can connect cleanly with surrounding beats.'
  }
  if (props.styleDriftIssueCount > 0) {
    return 'Visual language is close, but style drift is visible. Tighten tone and composition before render execution.'
  }
  if (props.decisionGateStatus === 'ready') {
    return 'This scene reads production-ready. Confirm pacing and hand off to Screening once render outputs are stable.'
  }
  return 'Co-Director analysis is still gathering enough evidence to lock scene intent with confidence.'
}

function whyThisShotMatters(props: Pick<PrevisCinematicShowcaseProps, 'sceneTitle' | 'relatedMemoryCount' | 'visualEvidenceCount' | 'continuityIssueCount' | 'styleDriftIssueCount' | 'decisionGateStatus' | 'hasDirectorSignature'>): string {
  const subject = props.sceneTitle || 'This shot'
  if (props.visualEvidenceCount < 1 || props.relatedMemoryCount < 1) {
    return `${subject} still matters, but the Studio needs more visual evidence before trusting the cut.`
  }
  if (props.continuityIssueCount > 0 || props.styleDriftIssueCount > 0) {
    return `${subject} connects emotional pressure to the final review, but continuity and style need one more pass.`
  }
  if (props.decisionGateStatus === 'ready' && props.hasDirectorSignature) {
    return `${subject} is ready because visual evidence, memory, and review state now agree.`
  }
  return `${subject} carries the visual memory of the project into the cut.`
}

export default function PrevisCinematicShowcase(props: PrevisCinematicShowcaseProps) {
  const confidence = shotToCutLabel(props)

  return (
    <section className="rounded-2xl border border-zinc-700/70 bg-gradient-to-br from-zinc-950 via-zinc-900 to-black p-4 shadow-[0_20px_60px_rgba(0,0,0,0.45)]" data-testid="previs-cinematic-showcase">
      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <div className="rounded-xl border border-white/10 bg-zinc-950/70 p-4">
          <div className="text-[11px] uppercase tracking-[0.16em] text-cyan-200">Shot Intent Hero</div>
          <h3 className="mt-1 text-lg font-semibold text-zinc-100">{props.sceneTitle || 'Scene intent in progress'}</h3>
          <div className="mt-1 text-xs uppercase tracking-[0.12em] text-zinc-400">{props.sceneId || 'scene_unknown'}</div>
          <p className="mt-2 text-sm text-zinc-300">{props.cinematicIntent}</p>
          <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Emotional beat: <span className="text-zinc-100">{props.emotionalBeat}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Visual source: <span className="text-zinc-100">{props.referenceConfidenceLabel}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Current status: <span className="text-zinc-100">{props.currentStatus}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Shot-to-cut: <span className="text-zinc-100">{confidence}</span></div>
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-zinc-950/70 p-4">
          <div className="text-[11px] uppercase tracking-[0.16em] text-fuchsia-200">Co-Director Shot Notes</div>
          <p className="mt-2 text-sm text-zinc-300">{coDirectorNote(props)}</p>
          <p className="mt-2 text-sm text-zinc-200">Why this shot matters: {whyThisShotMatters(props)}</p>
          <div className="mt-3 space-y-2 text-xs text-zinc-300">
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Memory references: <span className="text-zinc-100">{props.relatedMemoryCount}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Continuity issues: <span className="text-zinc-100">{props.continuityIssueCount}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Style drift issues: <span className="text-zinc-100">{props.styleDriftIssueCount}</span></div>
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-zinc-700/70 bg-black/35 p-3">
        <div className="text-[11px] uppercase tracking-[0.14em] text-zinc-400">Shot Progression Strip</div>
        <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4" data-testid="previs-stage-strip">
          {['Study', 'Previs', 'Production', 'Screening'].map((stage) => (
            <div
              key={stage}
              className={`rounded-md border px-2 py-1 text-center uppercase tracking-[0.12em] ${stage === 'Previs' ? 'border-cyan-400/60 bg-cyan-500/16 text-cyan-100' : 'border-white/10 bg-white/5 text-zinc-400'}`}
            >
              {stage}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Link to={withProject('/studio/production-board', props.projectId)} className="rounded-md border border-cyan-400/45 bg-cyan-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline">Open Production Board</Link>
        <Link to={withProject('/studio/screening-room', props.projectId)} className="rounded-md border border-fuchsia-400/45 bg-fuchsia-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-fuchsia-100 no-underline">Open Screening Room</Link>
        <Link to={withProject('/studio/study-room', props.projectId)} className="rounded-md border border-zinc-400/45 bg-zinc-700/22 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-100 no-underline">Return to Study Room</Link>
      </div>
    </section>
  )
}
