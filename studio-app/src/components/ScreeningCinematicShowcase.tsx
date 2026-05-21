import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { StudioDecisionGate } from '../lib/studioApi'

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
  if (gate.gate_status === 'ready') return 'The visual language is stable enough for audience review and package polish.'
  if (gate.gate_status === 'needs_review') return 'The cut is close, but a focused review pass should tighten audience impact.'
  if (gate.gate_status === 'blocked') return 'The cut is blocked by unresolved production concerns and needs intervention.'
  return 'The studio needs more visual evidence before it can lock a confident cut.'
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

function whyThisShotMatters(props: Pick<ScreeningCinematicShowcaseProps, 'activeSceneId' | 'gateStatus' | 'memoryRecordsCount' | 'continuityIssuesCount' | 'styleDriftIssuesCount' | 'hasDirectorSignature' | 'renderJobsCount' | 'reviewsCount' | 'packagesCount'>): string {
  const subject = props.activeSceneId ? `Scene ${props.activeSceneId}` : 'This cut'
  if (props.memoryRecordsCount < 1) {
    return `${subject} still matters, but the Studio needs more visual evidence before trusting the cut.`
  }
  if (props.continuityIssuesCount > 0 || props.styleDriftIssuesCount > 0) {
    return `${subject} connects the scene's emotional pressure to final review, but visual consistency still needs tightening.`
  }
  if (props.gateStatus === 'ready' && props.renderJobsCount > 0 && props.reviewsCount > 0 && props.packagesCount > 0 && props.hasDirectorSignature) {
    return `${subject} is ready because visual evidence, memory, and review state now agree.`
  }
  return `${subject} carries the visual memory of the project into the cut.`
}

export default function ScreeningCinematicShowcase(props: ScreeningCinematicShowcaseProps) {
  const [selectedRevisionId, setSelectedRevisionId] = useState(props.revisions[0]?.id || '')
  const [compareLeftId, setCompareLeftId] = useState(props.revisions[0]?.id || '')
  const [compareRightId, setCompareRightId] = useState(props.revisions[1]?.id || props.revisions[0]?.id || '')

  const selectedRevision = useMemo(
    () => props.revisions.find((item) => item.id === selectedRevisionId) || props.revisions[0] || null,
    [props.revisions, selectedRevisionId],
  )
  const compareLeft = useMemo(() => props.revisions.find((item) => item.id === compareLeftId) || null, [props.revisions, compareLeftId])
  const compareRight = useMemo(() => props.revisions.find((item) => item.id === compareRightId) || null, [props.revisions, compareRightId])
  const nextStep = recommendation(props.gateStatus)

  const heroMedia = props.heroVideoUrl || selectedRevision?.outputUrl || ''
  const heroImage = props.heroPreviewUrl || selectedRevision?.previewUrl || ''

  return (
    <section className="space-y-5" data-testid="screening-cinematic-showcase">
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
        </div>

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
          <button type="button" onClick={props.onExportPackage} className="rounded-md border border-fuchsia-400/45 bg-fuchsia-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-fuchsia-100">Export Package</button>
        </div>
        <div className="mt-3 text-xs text-zinc-400">{nextStep.message} <Link to={toRoomUrl(nextStep.href, props.projectId)} className="text-cyan-300">{nextStep.label}</Link></div>
      </div>
    </section>
  )
}
