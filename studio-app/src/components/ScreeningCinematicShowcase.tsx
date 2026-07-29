import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { StudioDecisionGate, CoDirectorDebateEntry } from '../lib/studioApi'
import { saveCreativeDecisionMemory, triggerDebate } from '../lib/studioApi'
import ScreeningEditorialComparisonPanel from './ScreeningEditorialComparisonPanel'
import SaveDecisionMemoryModal from './SaveDecisionMemoryModal'
import DirectorDebatePanel from './DirectorDebatePanel'
import { useTasteMemory } from '../hooks/useTasteMemory'
import type { InferredTradeoff, CreativeDecisionMemory } from '../types/creativeMemory'

type RevisionItem = {
  id: string
  label: string
  status: string
  runtimeSeconds: number
  previewUrl?: string
  outputUrl?: string
  createdAt?: string
  notes?: string
}

type RevisionEmphasis = 'emotional_residue' | 'structural_clarity'

type JournalPrompt = 'Why this cut?' | 'What changed emotionally?' | 'What should survive the next revision?'

type ScreeningCinematicShowcaseProps = {
  projectId: string
  projectTitle: string
  heroPreviewUrl: string
  heroVideoUrl: string
  activeSceneId: string
  gateStatus: string
  decisionGate: StudioDecisionGate | null
  renderStatusLabel: string
  runtimeEstimateLabel: string
  revisionCount: number
  renderJobsCount: number
  reviewsCount: number
  packagesCount: number
  continuityIssuesCount: number
  styleDriftIssuesCount: number
  memoryRecordsCount: number
  hasDirectorSignature: boolean
  revisions: RevisionItem[]
  initialRevisionEmphasis?: RevisionEmphasis
  initialTastePreviewHidden?: boolean
  initialSessionTasteCleared?: boolean
  // Emotional intelligence signals
  tensionTrend?: string
  onApproveCut: () => void
  onRequestRevision: () => void
  onCompareRevision: () => void
  onExportPackage: () => void
}

function toRoomUrl(path: string, projectId: string): string {
  return `${path}?project_id=${encodeURIComponent(projectId)}`
}

function sentenceCaseStatus(status: string): string {
  const normalized = status.trim().toLowerCase()
  if (!normalized) return 'Unknown'
  return normalized.replace(/_/g, ' ')
}

function gateSummary(gate: StudioDecisionGate | null): string {
  if (!gate) return 'The studio is still gathering enough evidence for a confident screening verdict.'
  if (gate.gate_status === 'ready') return 'The cut is ready because visual evidence, memory, and review state now agree.'
  if (gate.gate_status === 'needs_review') return 'The cut is close, but a focused review pass should tighten audience impact.'
  if (gate.gate_status === 'blocked') return 'The cut is blocked by unresolved production concerns and needs intervention.'
  return 'The studio needs more visual evidence before trusting the cut.'
}

function creativeRead(props: Pick<ScreeningCinematicShowcaseProps, 'continuityIssuesCount' | 'styleDriftIssuesCount' | 'memoryRecordsCount' | 'hasDirectorSignature'>): string {
  if (props.continuityIssuesCount > 0) {
    return 'Continuity remains unstable between revisions. Tighten visual match cuts before final audience review.'
  }
  if (props.styleDriftIssuesCount > 0) {
    return 'Visual motif consistency is emerging, but style drift is still visible in key transitions.'
  }
  if (props.memoryRecordsCount >= 3 && props.hasDirectorSignature) {
    return 'Performance tension rises with confident visual recall. The co-director read sees a coherent cinematic identity.'
  }
  if (props.memoryRecordsCount > 0) {
    return 'The film memory is forming, but the studio still needs stronger recurring motifs for a locked signature.'
  }
  return 'Co-Director analysis is still gathering visual evidence across your cut.'
}

function recommendation(gateStatus: string): { label: string; href: string; message: string } {
  if (gateStatus === 'ready') {
    return {
      label: 'Open Screening Room',
      href: '/studio/screening-room',
      message: 'The cut is ready, review it in Screening Room.',
    }
  }
  if (gateStatus === 'blocked') {
    return {
      label: 'Open Production Board',
      href: '/studio/production-board',
      message: 'Production needs attention before screening.',
    }
  }
  if (gateStatus === 'insufficient_data') {
    return {
      label: 'Open Study Room',
      href: '/studio/study-room',
      message: 'The studio is preparing the next screening cut.',
    }
  }
  if (gateStatus === 'needs_review') {
    return {
      label: 'Open Screening Room',
      href: '/studio/screening-room',
      message: 'The cut needs review notes before final package lock.',
    }
  }
  return {
    label: 'Open Previs',
    href: '/studio/previs',
    message: 'Open Previs to inspect the scene plan and tighten pacing.',
  }
}

function revisionEmphasisGuidance(
  emphasis: RevisionEmphasis,
  props: Pick<ScreeningCinematicShowcaseProps, 'continuityIssuesCount' | 'styleDriftIssuesCount' | 'memoryRecordsCount'>,
): string {
  if (emphasis === 'structural_clarity') {
    if (props.continuityIssuesCount > 0) return 'Structural clarity improves pacing consistency, though continuity needs one more tightening pass.'
    return 'Structural clarity improves pacing consistency and keeps the sequence easier to read.'
  }
  if (props.memoryRecordsCount > 0) return 'This emphasis preserves more emotional carryover between revisions.'
  return 'The quieter pause can carry emotional tension once more visual evidence is available.'
}

function sessionTasteMemoryNote(emphasis: RevisionEmphasis): string {
  if (emphasis === 'structural_clarity') {
    return 'For this session, the Studio is reading this as a preference toward structural clarity. This session read is based on revision emphasis and comparison behavior only. It is not saved.'
  }
  return 'For this session, the Studio is reading this as a preference toward emotional residue. This session read is based on revision emphasis and comparison behavior only. It is not saved.'
}

function emergingTasteRead(
  emphasis: RevisionEmphasis,
  props: Pick<ScreeningCinematicShowcaseProps, 'gateStatus' | 'memoryRecordsCount' | 'continuityIssuesCount' | 'styleDriftIssuesCount'>,
  disagreementVisible: boolean,
): string {
  const lowSignal = props.memoryRecordsCount < 2 || (props.continuityIssuesCount === 0 && props.styleDriftIssuesCount === 0 && !disagreementVisible)
  if (lowSignal) {
    return 'Taste read is still emerging. The Studio needs more revision choices before saying more.'
  }
  if (emphasis === 'structural_clarity') {
    if (props.gateStatus === 'needs_review' || props.continuityIssuesCount > 0) {
      return 'Your current review posture favors structural clarity over lingering ambiguity.'
    }
    return 'For this session, the Studio is noticing a lean toward structural clarity.'
  }
  if (disagreementVisible) {
    return 'For this session, the Studio is noticing a lean toward emotional residue.'
  }
  return 'For this session, the Studio is reading this as a tentative preference toward emotional residue.'
}

function whyThisShotMatters(props: Pick<ScreeningCinematicShowcaseProps, 'activeSceneId' | 'gateStatus' | 'memoryRecordsCount' | 'continuityIssuesCount' | 'styleDriftIssuesCount' | 'hasDirectorSignature' | 'renderJobsCount' | 'reviewsCount' | 'packagesCount'>): string {
  const subject = props.activeSceneId ? `Scene ${props.activeSceneId}` : 'This cut'
  
  // Use existing loaded signals: memory count, continuity/style drift, gate state, director signature, review/package readiness
  // Co-director voice: emotionally perceptive, cinematically literate, no scores
  
  if (props.memoryRecordsCount < 1) {
    return `${subject} needs more visual evidence before trusting the cut.`
  }
  
  if (props.continuityIssuesCount > 0 && props.styleDriftIssuesCount > 0) {
    return `${subject} connects emotional beats across the timeline, but both continuity and visual consistency need tightening before final review.`
  }
  
  if (props.continuityIssuesCount > 0) {
    return `${subject} holds its moment well, but the continuity risk could weaken the transition into the next sequence.`
  }
  
  if (props.styleDriftIssuesCount > 0) {
    return `${subject} carries tension effectively, though the visual language drifts from the signature the film is building.`
  }
  
  if (props.gateStatus === 'ready' && props.renderJobsCount > 0 && props.reviewsCount > 0 && props.packagesCount > 0 && props.hasDirectorSignature && props.memoryRecordsCount > 2) {
    return `${subject} is ready because visual evidence, memory, and review state now agree.`
  }
  
  if (props.reviewsCount > 0 && props.packagesCount > 0 && props.hasDirectorSignature) {
    return `${subject} has earned its approval through coherent visual memory and consistent director signature.`
  }
  
  if (props.memoryRecordsCount > 2 && props.hasDirectorSignature) {
    return `${subject} reinforces a recurring visual motif that deepens the emotional throughline of the entire cut.`
  }
  
  if (props.gateStatus === 'ready' && props.renderJobsCount > 0) {
    return `${subject} is gate-ready with stable render outputs, waiting for final review confirmation.`
  }
  
  return `${subject} carries the accumulated visual memory of the project into the final screening.`
}

// Scene tension tracking - simple tension trend indicator for Screening
// Uses existing signals: audio_tension, dread_score, continuity warnings
// Plain language only, no scores - co-director voice
function tensionTrendAdvisory(tensionTrend: string | undefined): string {
  if (!tensionTrend) return 'Tension read is gathering from dread curve and audio signals.'
  
  const normalized = tensionTrend.trim().toLowerCase()
  
  if (normalized === 'rising' || normalized === 'climbing' || normalized === 'building') {
    return 'Tension builds across the cut—the dread curve supports this escalation into the climax.'
  }
  if (normalized === 'high' || normalized === 'sustained' || normalized === 'holding') {
    return 'Tension sustains at a high level—the cut needs a release or payoff soon to avoid fatigue.'
  }
  if (normalized === 'dropping' || normalized === 'releasing' || normalized === 'falling') {
    return 'Tension releases in this sequence—confirm the prior build earned this relief.'
  }
  if (normalized === 'flat' || normalized === 'low' || normalized === 'calm') {
    return 'Tension remains low, offering breathing room but risking momentum loss if held too long.'
  }
  if (normalized === 'unstable' || normalized === 'inconsistent' || normalized === 'erratic') {
    return 'Tension feels inconsistent across the cut—audio and scene flow signals are misaligned.'
  }
  if (normalized === 'peaking' || normalized === 'climax') {
    return 'Tension peaks here—this beat should earn its place as the emotional high point.'
  }
  
  return 'Tension tracking is reading dread curve and audio profile across the cut.'
}

function creativeDisagreementAside(
  props: Pick<ScreeningCinematicShowcaseProps, 'continuityIssuesCount' | 'styleDriftIssuesCount' | 'memoryRecordsCount' | 'gateStatus'>,
  compareLeftId: string,
  compareRightId: string,
  revisionCount: number,
  emphasis: RevisionEmphasis,
): string | null {
  const hasComparisonContext = revisionCount > 1 && Boolean(compareLeftId) && Boolean(compareRightId) && compareLeftId !== compareRightId
  const hasTradeoffSignal = props.continuityIssuesCount > 0 || props.styleDriftIssuesCount > 0
  const hasEnoughContext = props.memoryRecordsCount > 0
  const gateSuggestsNuance = props.gateStatus === 'needs_review' || props.gateStatus === 'ready'

  if (!hasComparisonContext || !hasTradeoffSignal || !hasEnoughContext || !gateSuggestsNuance) return null

  if (props.continuityIssuesCount > 0 && props.styleDriftIssuesCount > 0 && emphasis === 'emotional_residue') {
    return 'This revision sharpens the sequence structurally, though the emotional transition feels slightly colder.'
  }
  if (props.continuityIssuesCount > 0 && emphasis === 'emotional_residue') {
    return 'This cut is cleaner, though it loses some emotional residue from the earlier version.'
  }
  if (props.styleDriftIssuesCount > 0 && emphasis === 'emotional_residue') {
    return 'Visual continuity is stronger now, though some intimacy from the earlier framing is reduced.'
  }
  if (emphasis === 'structural_clarity' && props.continuityIssuesCount > 0 && props.styleDriftIssuesCount > 0) {
    return 'The sequence reads cleaner, though the emotional handoff between beats remains delicate.'
  }
  return null
}

// eslint-disable-next-line react-refresh/only-export-components
export function buildJournalEntry(rawDraft: string): string | null {
  const trimmed = rawDraft.trim()
  if (!trimmed) return null
  return trimmed
}

// eslint-disable-next-line react-refresh/only-export-components
export function addJournalEntry(notes: string[], rawDraft: string): { notes: string[]; nextDraft: string } {
  const entry = buildJournalEntry(rawDraft)
  if (!entry) return { notes, nextDraft: rawDraft }
  return { notes: [entry, ...notes], nextDraft: '' }
}

// eslint-disable-next-line react-refresh/only-export-components
export function applyJournalPrompt(prompt: JournalPrompt): string {
  return `${prompt} `
}

export type CandidateMemory = {
  id: string
  note: string
  inferredTradeoffAxis: 'emotional_residue' | 'structural_clarity'
  sessionOrder: number
}

// eslint-disable-next-line react-refresh/only-export-components
export function inferTradeoffAxisFromText(note: string): CandidateMemory['inferredTradeoffAxis'] {
  const text = note.toLowerCase()
  if (text.includes('clarity') || text.includes('structure') || text.includes('pacing')) {
    return 'structural_clarity'
  }
  return 'emotional_residue'
}

// eslint-disable-next-line react-refresh/only-export-components
export function markCandidateMemory(
  currentCandidates: CandidateMemory[],
  note: string,
  fallbackAxis: CandidateMemory['inferredTradeoffAxis'],
): CandidateMemory[] {
  if (!note.trim()) return currentCandidates
  const existing = currentCandidates.find((candidate) => candidate.note === note)
  if (existing) return currentCandidates
  const inferred = inferTradeoffAxisFromText(note)
  return [
    {
      id: `candidate-${currentCandidates.length + 1}`,
      note,
      inferredTradeoffAxis: inferred || fallbackAxis,
      sessionOrder: currentCandidates.length + 1,
    },
    ...currentCandidates,
  ]
}

// eslint-disable-next-line react-refresh/only-export-components
export function removeCandidateMemory(currentCandidates: CandidateMemory[], candidateId: string): CandidateMemory[] {
  return currentCandidates.filter((candidate) => candidate.id !== candidateId)
}

// eslint-disable-next-line react-refresh/only-export-components
export function clearCandidateMemories(): CandidateMemory[] {
  return []
}

export default function ScreeningCinematicShowcase(props: ScreeningCinematicShowcaseProps) {
  const [selectedRevisionId, setSelectedRevisionId] = useState(props.revisions[0]?.id || '')
  const [compareLeftId, setCompareLeftId] = useState(props.revisions[0]?.id || '')
  const [compareRightId, setCompareRightId] = useState(props.revisions[1]?.id || props.revisions[0]?.id || '')
  const [revisionEmphasis, setRevisionEmphasis] = useState<RevisionEmphasis>(props.initialRevisionEmphasis || 'emotional_residue')
  const [tastePreviewHidden, setTastePreviewHidden] = useState(Boolean(props.initialTastePreviewHidden))
  const [sessionTasteCleared, setSessionTasteCleared] = useState(Boolean(props.initialSessionTasteCleared))
  const [journalDraft, setJournalDraft] = useState('')
  const [journalNotes, setJournalNotes] = useState<string[]>([])
  const [candidateMemories, setCandidateMemories] = useState<CandidateMemory[]>([])
  
  // Creative Decision Memory v1 - Modal state
  const [saveMemoryModalOpen, setSaveMemoryModalOpen] = useState(false)
  const [saveMemoryError, setSaveMemoryError] = useState<string | null>(null)
  const [activeDebate, setActiveDebate] = useState<CoDirectorDebateEntry | null>(null)
  const [triggeringDebate, setTriggeringDebate] = useState(false)

  const handleManualDebate = async () => {
    if (!props.projectId) return
    setTriggeringDebate(true)
    try {
      const query = `Debate revision comparison between ${compareLeft?.label || 'Baseline'} and ${compareRight?.label || 'Comparison'}. Emphasis: ${revisionEmphasis}.`
      const { debate } = await triggerDebate({
        project_id: props.projectId,
        scene_id: props.activeSceneId,
        query,
      })
      setActiveDebate(debate)
    } catch (err) {
      console.error('Failed to trigger manual debate:', err)
    } finally {
      setTriggeringDebate(false)
    }
  }

  // Taste Memory v1 - Frontend session only, tracks revision emphasis choices
  const tasteMemory = useTasteMemory()

  // Record taste observation when revision emphasis changes
  useEffect(() => {
    // Only record if not cleared and we have actual revision context
    if (!sessionTasteCleared && props.revisions.length > 0) {
      tasteMemory.recordObservation(revisionEmphasis, 'revision_emphasis_toggle')
    }
  }, [revisionEmphasis, sessionTasteCleared, props.revisions.length, tasteMemory])

  // Clear taste memory when user explicitly clears session
  useEffect(() => {
    if (sessionTasteCleared) {
      tasteMemory.clearMemory()
    }
  }, [sessionTasteCleared, tasteMemory])

  const selectedRevision = useMemo(
    () => props.revisions.find((item) => item.id === selectedRevisionId) || props.revisions[0] || null,
    [props.revisions, selectedRevisionId],
  )
  const compareLeft = useMemo(() => props.revisions.find((item) => item.id === compareLeftId) || null, [props.revisions, compareLeftId])
  const compareRight = useMemo(() => props.revisions.find((item) => item.id === compareRightId) || null, [props.revisions, compareRightId])
  const nextStep = recommendation(props.gateStatus)
  const disagreementAside = creativeDisagreementAside(props, compareLeftId, compareRightId, props.revisionCount, revisionEmphasis)
  const tasteRead = sessionTasteCleared
    ? 'Taste read is reset for this session. The Studio needs more revision choices before saying more.'
    : emergingTasteRead(revisionEmphasis, props, Boolean(disagreementAside))
  const heroMedia = props.heroVideoUrl || selectedRevision?.outputUrl || ''
  const heroImage = props.heroPreviewUrl || selectedRevision?.previewUrl || ''

  // Creative Decision Memory handlers
  const handleSaveDecisionMemory = async (memory: Omit<CreativeDecisionMemory, 'memory_id' | 'saved_at'>) => {
    setSaveMemoryError(null)
    try {
      await saveCreativeDecisionMemory(props.projectId, memory)
      // Clear journal draft and close modal on success
      setJournalDraft('')
      setSaveMemoryModalOpen(false)
    } catch (error) {
      setSaveMemoryError(error instanceof Error ? error.message : 'Failed to save decision memory')
      throw error
    }
  }

  const handleSessionOnlyDecision = () => {
    // User chose to keep the decision session-only (not save to project)
    // Clear the draft and close modal
    setJournalDraft('')
    setSaveMemoryModalOpen(false)
  }

  const inferTradeoffFromCurrentState = (): InferredTradeoff => {
    // Infer from revision emphasis and taste memory state
    if (revisionEmphasis === 'emotional_residue') {
      return 'emotional_residue_favored'
    }
    if (revisionEmphasis === 'structural_clarity') {
      return 'structural_clarity_favored'
    }
    return 'not_inferred'
  }

  const buildTradeoffExplanation = (): string => {
    // Language only, no scores
    const tradeoff = inferTradeoffFromCurrentState()
    const tasteState = tasteMemory.getTasteState()
    
    if (tradeoff === 'emotional_residue_favored') {
      if (tasteState.confidence === 'strong') {
        return 'You consistently favor emotional residue and longer emotional carryover across cuts.'
      }
      if (tasteState.confidence === 'consistent') {
        return 'You tend to favor emotional residue over structural clarity in your revision choices.'
      }
      return 'For this decision, you leaned toward emotional residue over structural clarity.'
    }
    
    if (tradeoff === 'structural_clarity_favored') {
      if (tasteState.confidence === 'strong') {
        return 'You consistently favor structural clarity and tighter pacing across cuts.'
      }
      if (tasteState.confidence === 'consistent') {
        return 'You tend to favor structural clarity over emotional residue in your revision choices.'
      }
      return 'For this decision, you leaned toward structural clarity over emotional residue.'
    }
    
    return 'The Studio does not have enough context to infer a clear preference from this decision.'
  }

  return (
    <section className="space-y-5" data-testid="screening-cinematic-showcase">
      <SaveDecisionMemoryModal
        isOpen={saveMemoryModalOpen}
        onClose={() => setSaveMemoryModalOpen(false)}
        onSave={handleSaveDecisionMemory}
        onSessionOnly={handleSessionOnlyDecision}
        initialNote={journalDraft}
        inferredTradeoff={inferTradeoffFromCurrentState()}
        inferredExplanation={buildTradeoffExplanation()}
        sourceContext={{
          scene_id: props.activeSceneId,
          revision_id: selectedRevisionId,
          revision_emphasis: revisionEmphasis,
          screen_location: 'screening_room_journal',
        }}
        projectId={props.projectId}
      />
      {activeDebate && (
        <div className="mb-6">
          <DirectorDebatePanel
            projectId={props.projectId}
            debate={activeDebate}
            onDismiss={() => setActiveDebate(null)}
          />
        </div>
      )}
      <div className="relative overflow-hidden rounded-2xl border border-zinc-700/70 bg-gradient-to-br from-zinc-950 via-zinc-900 to-black shadow-[0_28px_80px_rgba(0,0,0,0.55)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(244,114,182,0.16),transparent_45%),radial-gradient(circle_at_bottom_left,rgba(56,189,248,0.14),transparent_42%)]" />
        <div className="relative grid gap-4 p-4 lg:grid-cols-[1.8fr_1fr] lg:p-6">
          <div className="overflow-hidden rounded-xl border border-white/15 bg-black/50 shadow-[inset_0_0_90px_rgba(0,0,0,0.55)]">
            {heroMedia ? (
              <video
                key={heroMedia}
                src={heroMedia}
                className="aspect-video w-full object-cover transition-opacity duration-500"
                controls
                muted
                playsInline
              />
            ) : heroImage ? (
              <img src={heroImage} alt="Featured revision" className="aspect-video w-full object-cover transition-opacity duration-500" />
            ) : (
              <div className="grid aspect-video w-full place-items-center text-sm text-zinc-300">
                The studio is preparing the next screening cut.
              </div>
            )}
          </div>

          <div className="space-y-3 rounded-xl border border-white/10 bg-zinc-950/70 p-4 backdrop-blur">
            <div className="text-[11px] uppercase tracking-[0.18em] text-zinc-400">Screening Showcase</div>
            <h2 className="text-xl font-semibold text-zinc-100">{props.projectTitle || 'Untitled Project'}</h2>
            <p className="text-sm text-zinc-300">{gateSummary(props.decisionGate)}</p>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Runtime: <span className="text-zinc-100">{props.runtimeEstimateLabel}</span></div>
              <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Render: <span className="text-zinc-100">{props.renderStatusLabel}</span></div>
              <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Gate: <span className="text-zinc-100">{sentenceCaseStatus(props.gateStatus)}</span></div>
              <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Revisions: <span className="text-zinc-100">{props.revisionCount}</span></div>
            </div>
            <div className="text-xs text-zinc-400">Focused scene: <span className="text-zinc-200">{props.activeSceneId || 'not selected'}</span></div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <div className="rounded-2xl border border-zinc-700/70 bg-zinc-950/75 p-4 shadow-[0_16px_40px_rgba(0,0,0,0.35)]">
          <div className="text-[11px] uppercase tracking-[0.16em] text-cyan-200">Co-Director Notes</div>
          <p className="mt-2 text-sm text-zinc-200">{creativeRead(props)}</p>
          <p className="mt-2 text-sm text-zinc-200">Why this shot matters: {whyThisShotMatters(props)}</p>
          {props.tensionTrend ? (
            <p className="mt-2 text-xs text-zinc-400">{tensionTrendAdvisory(props.tensionTrend)}</p>
          ) : null}
          <p className="mt-2 text-xs text-zinc-400" data-testid="revision-emphasis-guidance">
            {revisionEmphasisGuidance(revisionEmphasis, props)}
          </p>
          {disagreementAside ? (
            <div className="mt-2 flex items-center justify-between gap-3 rounded border border-indigo-500/20 bg-indigo-500/5 p-2">
              <p className="text-xs text-indigo-200/90" data-testid="creative-disagreement-aside">
                {disagreementAside}
              </p>
              <button
                type="button"
                onClick={handleManualDebate}
                disabled={triggeringDebate}
                className="text-[10px] font-bold uppercase tracking-wider text-indigo-400 hover:text-indigo-300"
              >
                Discuss
              </button>
            </div>
          ) : null}
          {props.tensionTrend ? (
            <div className="mt-3 rounded-md border border-rose-400/30 bg-rose-500/8 px-2 py-1.5">
              <div className="text-[10px] uppercase tracking-[0.12em] text-rose-300">Tension trend</div>
              <div className="mt-0.5 text-xs text-zinc-200">{props.tensionTrend}</div>
            </div>
          ) : null}
          <div className="mt-3 text-sm text-zinc-300">{props.decisionGate?.recommended_next_action || nextStep.message}</div>
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <Link className="rounded-md border border-cyan-400/45 bg-cyan-500/15 px-3 py-1.5 text-cyan-100 no-underline" to={toRoomUrl('/studio/previs', props.projectId)}>Open Previs</Link>
            <Link className="rounded-md border border-amber-400/45 bg-amber-500/15 px-3 py-1.5 text-amber-100 no-underline" to={toRoomUrl('/studio/production-board', props.projectId)}>Open Production Board</Link>
            <Link className="rounded-md border border-fuchsia-400/45 bg-fuchsia-500/15 px-3 py-1.5 text-fuchsia-100 no-underline" to={toRoomUrl('/studio/screening-room', props.projectId)}>Open Screening Room</Link>
          </div>
        </div>

        <div className="rounded-2xl border border-zinc-700/70 bg-zinc-950/75 p-4 shadow-[0_16px_40px_rgba(0,0,0,0.35)]">
          <div className="text-[11px] uppercase tracking-[0.16em] text-emerald-200">Approval Stack</div>
          <div className="mt-2 space-y-2 text-xs text-zinc-300">
            <div className="rounded-md border border-white/10 bg-white/5 px-3 py-2">Review status cards: <span className="text-zinc-100">{props.reviewsCount || 0}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-3 py-2">Package readiness: <span className="text-zinc-100">{props.packagesCount > 0 ? 'ready' : 'needs attention'}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-3 py-2">Decision gate: <span className="text-zinc-100">{sentenceCaseStatus(props.gateStatus)}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-3 py-2">Render jobs available: <span className="text-zinc-100">{props.renderJobsCount}</span></div>
          </div>
          <div className="mt-3 text-xs text-zinc-400">
            {props.packagesCount > 0 ? 'Ready for screening presentation.' : 'No approved packages yet. The film is still evolving.'}
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-zinc-700/70 bg-zinc-950/75 p-4 shadow-[0_16px_40px_rgba(0,0,0,0.35)]">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.16em] text-zinc-400">Revision Timeline</div>
            <div className="mt-1 text-xs text-zinc-500">Select two revisions to compare creative direction.</div>
          </div>
            <button
              type="button"
              onClick={props.onCompareRevision}
              className="rounded-md border border-cyan-400/45 bg-cyan-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100"
            >
              Compare Revision
            </button>
            <button
              type="button"
              onClick={handleManualDebate}
              disabled={triggeringDebate || props.revisions.length < 2}
              className="rounded-md border border-indigo-500/45 bg-indigo-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-indigo-100"
            >
              {triggeringDebate ? 'Preparing Debate...' : 'Debate this Comparison'}
            </button>
        </div>
        {props.revisions.length > 1 ? (
          <div className="mt-3 rounded-lg border border-white/10 bg-black/25 p-2.5" data-testid="revision-emphasis-toggle">
            <div className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Revision Emphasis</div>
            <div className="mt-2 inline-flex rounded-md border border-zinc-700 bg-zinc-900/70 p-1">
              <button
                type="button"
                onClick={() => {
                  setRevisionEmphasis('emotional_residue')
                  setSessionTasteCleared(false)
                }}
                className={`rounded px-2.5 py-1 text-[11px] ${revisionEmphasis === 'emotional_residue' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}`}
              >
                Emotional Residue
              </button>
              <button
                type="button"
                onClick={() => {
                  setRevisionEmphasis('structural_clarity')
                  setSessionTasteCleared(false)
                }}
                className={`rounded px-2.5 py-1 text-[11px] ${revisionEmphasis === 'structural_clarity' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}`}
              >
                Structural Clarity
              </button>
            </div>
            <p className="mt-2 text-[11px] text-zinc-500" data-testid="session-taste-memory-note">
              {sessionTasteMemoryNote(revisionEmphasis)}
            </p>
            <div className="mt-2 rounded-md border border-white/10 bg-zinc-900/40 px-2 py-1.5" data-testid="emerging-taste-read">
              <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">Emerging Taste Read</div>
              {tasteMemory.hasEnoughData() ? (
                <p className="mt-1 text-[11px] text-zinc-400">{tasteMemory.getTendencyMessage()}</p>
              ) : (
                <p className="mt-1 text-[11px] text-zinc-400">{tasteRead}</p>
              )}
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setSessionTasteCleared(true)}
                className="rounded-md border border-zinc-600/80 bg-zinc-900/70 px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-zinc-200"
              >
                Clear Session Read
              </button>
              <button
                type="button"
                onClick={() => setTastePreviewHidden((previous) => !previous)}
                className="rounded-md border border-zinc-600/80 bg-zinc-900/70 px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-zinc-200"
              >
                {tastePreviewHidden ? 'Show Taste Preview' : 'Hide Taste Preview'}
              </button>
            </div>
            <p className="mt-2 text-[11px] text-zinc-500" data-testid="taste-observed-explainer">
              What is being observed? This session read is based on revision emphasis and comparison behavior only. It is not saved. Observations: {tasteMemory.observationCount}
            </p>
            {!tastePreviewHidden ? (
              <div className="mt-2 rounded-md border border-white/10 bg-zinc-900/40 px-2 py-1.5" data-testid="director-taste-session-preview">
                <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">Director Taste Profile, Session Preview</div>
                {tasteMemory.hasEnoughData() ? (
                  <>
                    <p className="mt-1 text-[11px] text-zinc-300">
                      Current leaning: <span className="text-zinc-100">{tasteMemory.currentLeaning === 'emotional_residue' ? 'Emotional Residue' : 'Structural Clarity'}</span>
                    </p>
                    <p className="mt-1 text-[11px] text-zinc-300">
                      Confidence: <span className="text-zinc-100 capitalize">{tasteMemory.confidence}</span>
                    </p>
                    <p className="mt-1 text-[11px] text-zinc-400">{tasteMemory.getTendencyMessage()}</p>
                    <p className="mt-1 text-[11px] text-zinc-500">The Studio is treating this as a temporary creative read, not a permanent profile.</p>
                  </>
                ) : (
                  <>
                    <p className="mt-1 text-[11px] text-zinc-300">
                      Current axis: <span className="text-zinc-100">Emerging</span>
                    </p>
                    <p className="mt-1 text-[11px] text-zinc-400">The Studio is still observing your creative choices to understand your tendencies.</p>
                    <p className="mt-1 text-[11px] text-zinc-500">The Studio is treating this as a temporary creative read, not a permanent profile.</p>
                  </>
                )}
              </div>
            ) : null}

            <div className="mt-3 rounded-md border border-white/10 bg-zinc-900/30 px-2 py-2" data-testid="cut-decision-journal">
              <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">Cut Decision Journal</div>
              <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                {(['Why this cut?', 'What changed emotionally?', 'What should survive the next revision?'] as JournalPrompt[]).map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => setJournalDraft(applyJournalPrompt(prompt))}
                    className="rounded border border-zinc-700/90 bg-zinc-900/60 px-2 py-1 text-zinc-300"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
              <label className="sr-only" htmlFor="cut-decision-journal-input">Add session note</label>
              <textarea
                id="cut-decision-journal-input"
                data-testid="cut-decision-journal-input"
                value={journalDraft}
                onChange={(event) => setJournalDraft(event.target.value)}
                placeholder="Add session note..."
                className="mt-2 w-full rounded-md border border-zinc-700 bg-zinc-950/80 px-2 py-1.5 text-xs text-zinc-100"
                rows={3}
              />
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const updated = addJournalEntry(journalNotes, journalDraft)
                    setJournalNotes(updated.notes)
                    setJournalDraft(updated.nextDraft)
                  }}
                  className="rounded-md border border-cyan-400/45 bg-cyan-500/12 px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan-100"
                >
                  Add Session Note
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (!journalDraft.trim()) {
                      setSaveMemoryError('Please write a note before saving to project memory')
                      return
                    }
                    setSaveMemoryModalOpen(true)
                  }}
                  disabled={!journalDraft.trim()}
                  className="rounded-md border border-fuchsia-400/45 bg-fuchsia-500/14 px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-fuchsia-100 disabled:opacity-50"
                >
                  Save this decision to project memory
                </button>
                <button
                  type="button"
                  onClick={() => setJournalNotes([])}
                  className="rounded-md border border-zinc-600/80 bg-zinc-900/70 px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-zinc-200"
                >
                  Clear Notes
                </button>
              </div>
              {saveMemoryError && (
                <div className="mt-2 rounded-md border border-rose-400/40 bg-rose-500/10 px-2 py-1.5 text-xs text-rose-200">
                  {saveMemoryError}
                </div>
              )}
              <p className="mt-2 text-[11px] text-zinc-500">This journal is session-only and not saved.</p>
              <div className="mt-2 space-y-1.5" data-testid="cut-decision-journal-notes">
                {journalNotes.length > 0 ? journalNotes.map((note, index) => (
                  <div key={`${index}-${note.slice(0, 16)}`} className="rounded border border-white/10 bg-zinc-900/50 px-2 py-1">
                    <p className="text-[11px] text-zinc-300">{note}</p>
                    <button
                      type="button"
                      onClick={() => setCandidateMemories((current) => markCandidateMemory(current, note, revisionEmphasis))}
                      className="mt-1 rounded border border-fuchsia-400/40 bg-fuchsia-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-fuchsia-100"
                    >
                      Mark As Candidate Memory
                    </button>
                  </div>
                )) : (
                  <p className="text-[11px] text-zinc-500">No session notes yet.</p>
                )}
              </div>
              <div className="mt-3 rounded border border-white/10 bg-zinc-900/35 px-2 py-2" data-testid="candidate-project-memories">
                <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">Candidate Project Memories</div>
                <p className="mt-1 text-[11px] text-zinc-500">Candidate memories are not saved permanently.</p>
                <p className="text-[11px] text-zinc-500">The Studio is waiting for explicit save approval.</p>
                <div className="mt-2 space-y-1.5">
                  {candidateMemories.length > 0 ? candidateMemories.map((candidate) => (
                    <div key={candidate.id} className="rounded border border-white/10 bg-zinc-900/60 px-2 py-1.5">
                      <p className="text-[11px] text-zinc-200">{candidate.note}</p>
                      <p className="mt-1 text-[10px] uppercase tracking-[0.12em] text-zinc-500">
                        Axis: {candidate.inferredTradeoffAxis === 'emotional_residue' ? 'Emotional Residue' : 'Structural Clarity'} · Session #{candidate.sessionOrder}
                      </p>
                      <button
                        type="button"
                        onClick={() => setCandidateMemories((current) => removeCandidateMemory(current, candidate.id))}
                        className="mt-1 rounded border border-zinc-600/80 bg-zinc-900/80 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-zinc-200"
                      >
                        Remove Candidate
                      </button>
                    </div>
                  )) : (
                    <p className="text-[11px] text-zinc-500">No candidate memories marked yet.</p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setCandidateMemories(clearCandidateMemories())}
                  className="mt-2 rounded border border-zinc-600/80 bg-zinc-900/70 px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-zinc-200"
                >
                  Clear All Candidates
                </button>
              </div>
            </div>
          </div>
        ) : null}
        <ScreeningEditorialComparisonPanel
          projectId={props.projectId}
          baselineRevisionId={compareLeftId}
          comparisonRevisionId={compareRightId}
          revisionEmphasis={revisionEmphasis}
          revisionCount={props.revisionCount}
        />

        {props.revisions.length === 0 ? (
          <div className="mt-3 rounded-lg border border-dashed border-zinc-700 bg-black/30 px-3 py-6 text-center text-sm text-zinc-400">
            The studio is preparing the next screening cut.
          </div>
        ) : (
          <>
            <div className="mt-3 flex gap-3 overflow-x-auto pb-2">
              {props.revisions.map((revision) => (
                <button
                  key={revision.id}
                  type="button"
                  onClick={() => setSelectedRevisionId(revision.id)}
                  className={`min-w-[210px] rounded-xl border p-3 text-left transition ${selectedRevisionId === revision.id ? 'border-cyan-300/60 bg-cyan-500/12' : 'border-white/10 bg-black/30 hover:border-white/30'}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-semibold text-zinc-100">{revision.label}</div>
                    <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-300">{sentenceCaseStatus(revision.status)}</div>
                  </div>
                  <div className="mt-1 text-xs text-zinc-400">Runtime {Math.max(0, revision.runtimeSeconds)}s</div>
                  <div className="mt-1 text-xs text-zinc-500">{revision.createdAt || 'Timestamp unavailable'}</div>
                </button>
              ))}
            </div>

            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              {[{ side: 'A', value: compareLeftId, setter: setCompareLeftId, data: compareLeft }, { side: 'B', value: compareRightId, setter: setCompareRightId, data: compareRight }].map((slot) => (
                <div key={slot.side} className="rounded-xl border border-white/10 bg-black/30 p-3">
                  <label className="text-[10px] uppercase tracking-[0.14em] text-zinc-400" htmlFor={`revision-${slot.side}`}>Revision {slot.side}</label>
                  <select
                    id={`revision-${slot.side}`}
                    className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-100"
                    value={slot.value}
                    onChange={(event) => slot.setter(event.target.value)}
                  >
                    {props.revisions.map((item) => (
                      <option key={`${slot.side}-${item.id}`} value={item.id}>{item.label}</option>
                    ))}
                  </select>
                  <div className="mt-2 text-xs text-zinc-300">Status: {sentenceCaseStatus(slot.data?.status || 'unknown')}</div>
                  <div className="text-xs text-zinc-400">Runtime: {slot.data?.runtimeSeconds ?? 0}s</div>
                  <div className="mt-1 text-xs text-zinc-500">{slot.data?.notes || 'No revision notes available yet.'}</div>
                </div>
              ))}
            </div>
            <div className="mt-2 text-xs text-zinc-400">
              Visual differences summary: {compareLeft && compareRight && compareLeft.id !== compareRight.id ? 'Comparing pacing, motion confidence, and continuity stability between selected revisions.' : 'Select two different revisions to compare.'}
            </div>
          </>
        )}
      </div>

      <div className="rounded-2xl border border-zinc-700/70 bg-zinc-950/75 p-4 shadow-[0_16px_40px_rgba(0,0,0,0.35)]">
        <div className="text-[11px] uppercase tracking-[0.16em] text-zinc-400">Smart Actions</div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" onClick={props.onApproveCut} className="rounded-md border border-emerald-400/50 bg-emerald-500/15 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-100">Approve Cut</button>
          <button type="button" onClick={props.onRequestRevision} className="rounded-md border border-amber-400/50 bg-amber-500/15 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-100">Request Revision</button>
          <Link to={toRoomUrl('/studio/production-board', props.projectId)} className="rounded-md border border-zinc-400/45 bg-zinc-800/40 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-100 no-underline">Open Production Board</Link>
          <button type="button" onClick={props.onCompareRevision} className="rounded-md border border-cyan-400/45 bg-cyan-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100">Compare Revision</button>
          <button type="button" onClick={props.onExportPackage} className="rounded-md border border-fuchsia-400/45 bg-fuchsia-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-fuchsia-100">Create Final Package</button>
        </div>
        <div className="mt-3 text-xs text-zinc-400">{nextStep.message} <Link to={toRoomUrl(nextStep.href, props.projectId)} className="text-cyan-300">{nextStep.label}</Link></div>
      </div>
    </section>
  )
}
