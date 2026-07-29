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
  // Emotional intelligence signals
  emotionalPacingLabel?: string
  tensionTrend?: string
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
  
  // Use existing loaded signals: memory count, continuity/style drift, gate state, director signature
  // Co-director voice: emotionally perceptive, cinematically literate, no scores
  
  if (props.visualEvidenceCount < 1 || props.relatedMemoryCount < 1) {
    return `${subject} needs more visual evidence before trusting the cut.`
  }
  
  if (props.continuityIssueCount > 0 && props.styleDriftIssueCount > 0) {
    return `${subject} connects the emotional thread, but continuity and visual consistency both need tightening.`
  }
  
  if (props.continuityIssueCount > 0) {
    return `${subject} carries weight, but the continuity break risks weakening the handoff to the next beat.`
  }
  
  if (props.styleDriftIssueCount > 0) {
    return `${subject} holds tension well, though the visual language drifts from the signature you're building.`
  }
  
  if (props.decisionGateStatus === 'ready' && props.hasDirectorSignature && props.relatedMemoryCount > 2) {
    return `${subject} is ready because visual evidence, memory, and review state now agree.`
  }
  
  if (props.hasDirectorSignature && props.relatedMemoryCount > 1) {
    return `${subject} reinforces a recurring motif that deepens the emotional continuity across the cut.`
  }
  
  if (props.relatedMemoryCount > 2) {
    return `${subject} connects to multiple earlier beats, creating a subtle callback that rewards attention.`
  }
  
  return `${subject} carries the visual memory of the project forward, building coherence across scenes.`
}

// Emotional pacing summary - advisory pacing label per scene transition
// Uses existing signals: emotional flow state, scene duration, continuity warnings
// One word or short phrase only, no scores - co-director voice
function emotionalPacingAdvisory(pacingLabel: string | undefined): string {
  if (!pacingLabel) return 'Pacing read is still gathering evidence from scene transitions.'
  
  const normalized = pacingLabel.trim().toLowerCase()
  
  if (normalized === 'rising' || normalized === 'building') {
    return 'Tension builds naturally into the next beat.'
  }
  if (normalized === 'flat' || normalized === 'steady') {
    return 'Emotional carryover feels steady, though the cut could use more dynamic shift.'
  }
  if (normalized === 'overloaded' || normalized === 'rushed') {
    return 'The transition feels rushed—consider allowing more breathing room before the next scene.'
  }
  if (normalized === 'dropping' || normalized === 'releasing') {
    return 'Tension releases here, which can work if earned by prior build.'
  }
  
  return 'Pacing transition is developing—the Studio needs more scene context to read the flow.'
}

// Scene tension tracking - simple tension trend indicator
// Uses existing signals: audio_tension, dread_score, continuity warnings
// Plain language only, no scores - co-director voice
function tensionTrendAdvisory(tensionTrend: string | undefined): string {
  if (!tensionTrend) return 'Tension read is gathering from audio and continuity signals.'
  
  const normalized = tensionTrend.trim().toLowerCase()
  
  if (normalized === 'rising' || normalized === 'climbing' || normalized === 'building') {
    return 'Tension is building across this scene—the dread curve supports the escalation.'
  }
  if (normalized === 'high' || normalized === 'sustained' || normalized === 'holding') {
    return 'Tension holds at a sustained level—avoid letting it plateau too long without payoff.'
  }
  if (normalized === 'dropping' || normalized === 'releasing' || normalized === 'falling') {
    return 'Tension releases here—make sure the prior build earned this moment of relief.'
  }
  if (normalized === 'flat' || normalized === 'low' || normalized === 'calm') {
    return 'Tension remains low, which can work for breathing room but risks losing momentum.'
  }
  if (normalized === 'unstable' || normalized === 'inconsistent') {
    return 'Tension feels inconsistent—audio and continuity signals are misaligned.'
  }
  
  return 'Tension tracking is still reading signals from audio profile and scene flow.'
}

export default function PrevisCinematicShowcase(props: PrevisCinematicShowcaseProps) {
  const confidence = shotToCutLabel(props)
  const pacingNote = emotionalPacingAdvisory(props.emotionalPacingLabel)
  const tensionNote = tensionTrendAdvisory(props.tensionTrend)

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
          {props.emotionalPacingLabel ? (
            <div className="mt-3 rounded-md border border-amber-400/30 bg-amber-500/8 px-2 py-1.5">
              <div className="text-[10px] uppercase tracking-[0.12em] text-amber-300">Pacing transition</div>
              <div className="mt-0.5 text-xs text-zinc-200">{props.emotionalPacingLabel}</div>
            </div>
          ) : null}
          {props.tensionTrend ? (
            <div className="mt-2 rounded-md border border-rose-400/30 bg-rose-500/8 px-2 py-1.5">
              <div className="text-[10px] uppercase tracking-[0.12em] text-rose-300">Tension trend</div>
              <div className="mt-0.5 text-xs text-zinc-200">{props.tensionTrend}</div>
            </div>
          ) : null}
        </div>

        <div className="rounded-xl border border-white/10 bg-zinc-950/70 p-4">
          <div className="text-[11px] uppercase tracking-[0.16em] text-fuchsia-200">Co-Director Shot Notes</div>
          <p className="mt-2 text-sm text-zinc-300">{coDirectorNote(props)}</p>
          <p className="mt-2 text-sm text-zinc-200">Why this shot matters: {whyThisShotMatters(props)}</p>
          {props.emotionalPacingLabel ? (
            <p className="mt-2 text-xs text-zinc-400">{pacingNote}</p>
          ) : null}
          {props.tensionTrend ? (
            <p className="mt-2 text-xs text-zinc-400">{tensionNote}</p>
          ) : null}
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
