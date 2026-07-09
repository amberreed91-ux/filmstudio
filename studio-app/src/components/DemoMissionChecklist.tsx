import { Link } from 'react-router-dom'
import type { StudioDecisionGate } from '../lib/studioApi'

export type DemoMissionChecklistData = {
  visualAssetsCount: number | null
  keyframesCount: number | null
  frameAnalysesCount: number | null
  memoryRecordsCount: number | null
  embeddingsCount: number | null
  renderJobsCount: number | null
  decisionGate: StudioDecisionGate | null
}

type MissionItem = {
  label: string
  ready: boolean | null
  explanation: string
  ctaLabel?: string
  ctaPath?: string
}

function statusClasses(ready: boolean | null): string {
  if (ready === true) return 'border-emerald-300/45 bg-emerald-500/15 text-emerald-100'
  if (ready === false) return 'border-amber-300/45 bg-amber-500/15 text-amber-100'
  return 'border-zinc-500/40 bg-zinc-800/50 text-zinc-200'
}

function statusText(ready: boolean | null): string {
  if (ready === true) return 'Ready'
  if (ready === false) return 'Needs attention'
  return 'Checking...'
}

export default function DemoMissionChecklist({ projectId, data }: { projectId: string; data: DemoMissionChecklistData }) {
  if (projectId !== 'demo_studio_cinematic_001') return null

  const gateCounts = data.decisionGate?.evidence?.counts as Record<string, unknown> | undefined
  const reviewCount = typeof gateCounts?.reviews === 'number' ? gateCounts.reviews : null
  const packageCount = typeof gateCounts?.final_packages === 'number' ? gateCounts.final_packages : null
  const gateReady = data.decisionGate?.gate_status === 'ready'

  const items: MissionItem[] = [
    {
      label: 'Visual Evidence Loaded',
      ready: data.visualAssetsCount === null ? null : data.visualAssetsCount > 0,
      explanation: data.visualAssetsCount === null ? 'Checking uploaded/generated assets.' : `${data.visualAssetsCount} visual asset(s) detected.`,
      ctaLabel: 'Study Room',
      ctaPath: `/studio/study-room?project_id=${projectId}`,
    },
    {
      label: 'Keyframes Ready',
      ready: data.keyframesCount === null ? null : data.keyframesCount > 0,
      explanation: data.keyframesCount === null ? 'Checking keyframe extraction status.' : `${data.keyframesCount} keyframe(s) available.`,
      ctaLabel: 'Previs',
      ctaPath: `/studio/previs?project_id=${projectId}`,
    },
    {
      label: 'Frame Analysis Complete',
      ready: data.frameAnalysesCount === null ? null : data.frameAnalysesCount > 0,
      explanation: data.frameAnalysesCount === null ? 'Checking frame analysis output.' : `${data.frameAnalysesCount} frame analysis record(s) available.`,
      ctaLabel: 'Previs',
      ctaPath: `/studio/previs?project_id=${projectId}`,
    },
    {
      label: 'Cinematic Memory Built',
      ready:
        data.memoryRecordsCount === null || data.embeddingsCount === null
          ? null
          : data.memoryRecordsCount > 0 && data.embeddingsCount > 0,
      explanation:
        data.memoryRecordsCount === null || data.embeddingsCount === null
          ? 'Checking embeddings and memory records.'
          : `${data.embeddingsCount} embedding(s) and ${data.memoryRecordsCount} memory record(s) ready.`,
      ctaLabel: 'Crew Ops',
      ctaPath: `/studio/scheduler?project_id=${projectId}`,
    },
    {
      label: 'Decision Gate Ready',
      ready: data.decisionGate ? gateReady : null,
      explanation: data.decisionGate ? data.decisionGate.recommended_next_action : 'Checking decision gate state.',
      ctaLabel: 'Production Board',
      ctaPath: `/studio/production-board?project_id=${projectId}`,
    },
    {
      label: 'Render Jobs Available',
      ready: data.renderJobsCount === null ? null : data.renderJobsCount > 0,
      explanation: data.renderJobsCount === null ? 'Checking render queue status.' : `${data.renderJobsCount} render job(s) available.`,
      ctaLabel: 'Production Board',
      ctaPath: `/studio/production-board?project_id=${projectId}`,
    },
    {
      label: 'Review + Package Ready',
      ready: reviewCount === null || packageCount === null ? null : reviewCount > 0 && packageCount > 0,
      explanation:
        reviewCount === null || packageCount === null
          ? 'Checking review/package readiness.'
          : `${reviewCount} review(s) and ${packageCount} package(s) detected.`,
      ctaLabel: 'Screening Room',
      ctaPath: `/studio/screening-room?project_id=${projectId}`,
    },
  ]

  return (
    <section className="mt-4 rounded-xl border border-violet-300/35 bg-violet-500/10 p-4">
      <div className="text-xs uppercase tracking-[0.14em] text-violet-100">Demo Mission</div>
      <p className="mt-1 text-xs text-zinc-200">Follow this checklist to walk the full seeded cinematic workflow.</p>
      <div className="mt-3 grid gap-2 md:grid-cols-2">
        {items.map((item) => (
          <div key={item.label} className={`rounded-lg border px-3 py-2 ${statusClasses(item.ready)}`}>
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-semibold uppercase tracking-[0.12em]">{item.label}</div>
              <span className="rounded border border-current/40 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em]">
                {statusText(item.ready)}
              </span>
            </div>
            <p className="mt-1 text-[11px] text-zinc-100">{item.explanation}</p>
            {item.ctaLabel && item.ctaPath ? (
              <Link to={item.ctaPath} className="mt-2 inline-flex rounded border border-current/45 px-2 py-1 text-[10px] uppercase tracking-[0.1em] no-underline">
                {item.ctaLabel}
              </Link>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  )
}
