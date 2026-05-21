import { Link } from 'react-router-dom'
import type { StudioDecisionGate } from '../lib/studioApi'

export type DemoCoDirectorPanelData = {
  visualAssetsCount: number | null
  frameAnalysesCount: number | null
  memoryRecordsCount: number | null
  embeddingsCount: number | null
  continuityIssuesCount: number | null
  styleDriftIssuesCount: number | null
  hasDirectorSignature: boolean
  decisionGate: StudioDecisionGate | null
}

function describeReadiness(gate: StudioDecisionGate | null): string {
  if (!gate) return 'Still gathering enough visual evidence.'
  if (gate.gate_status === 'ready') return 'The cut is coherent and ready for screening and package polish.'
  if (gate.gate_status === 'needs_review') return 'The material is promising, but it needs review passes before final package.'
  if (gate.gate_status === 'blocked') return 'Pipeline blockers are present; clear failed steps before pushing forward.'
  return 'Still gathering enough visual evidence.'
}

function describeSignal(data: DemoCoDirectorPanelData): string {
  const analyses = data.frameAnalysesCount ?? 0
  const memory = data.memoryRecordsCount ?? 0
  const embeddings = data.embeddingsCount ?? 0
  if (analyses > 0 && memory > 0 && embeddings > 0) {
    return 'Strongest signal: visual continuity and mood are consistently represented across analyzed frames.'
  }
  if (analyses > 0) {
    return 'Strongest signal: frame-level composition and mood reads are beginning to stabilize.'
  }
  return 'Strongest signal is still forming as visual evidence is collected.'
}

function describeNextMove(gate: StudioDecisionGate | null): string {
  if (!gate) return 'Open Previs and confirm keyframes and frame analysis coverage.'
  if (gate.gate_status === 'ready') return 'Open Screening Room and validate the review-to-package loop.'
  if (gate.gate_status === 'needs_review') return 'Open Production Board to review issues, then continue in Screening Room.'
  if (gate.gate_status === 'blocked') return 'Open Production Board first and resolve blockers before screening.'
  return 'Open Previs and continue building visual evidence.'
}

export default function DemoCoDirectorPanel({ projectId, data }: { projectId: string; data: DemoCoDirectorPanelData }) {
  if (projectId !== 'demo_studio_cinematic_001') return null

  const gateLabel = data.decisionGate ? data.decisionGate.gate_status.replace('_', ' ') : 'checking'

  return (
    <section className="mt-4 rounded-xl border border-cyan-300/35 bg-cyan-500/10 p-4">
      <div className="text-xs uppercase tracking-[0.14em] text-cyan-100">Co-Director Guidance</div>
      <p className="mt-1 text-xs text-zinc-200">The Studio reads your cinematic signals and suggests the strongest next move.</p>

      <div className="mt-3 grid gap-2 md:grid-cols-2">
        <div className="rounded-lg border border-white/15 bg-black/25 p-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-cyan-100">What the Studio understands</div>
          <div className="mt-2 space-y-1 text-[11px] text-zinc-100">
            <div>Visual evidence: {data.visualAssetsCount ?? 'Checking...'}</div>
            <div>Frame analysis coverage: {data.frameAnalysesCount ?? 'Checking...'}</div>
            <div>Memory records: {data.memoryRecordsCount ?? 'Checking...'}</div>
            <div>Embeddings: {data.embeddingsCount ?? 'Checking...'}</div>
            <div>Decision gate: {gateLabel}</div>
          </div>
        </div>

        <div className="rounded-lg border border-white/15 bg-black/25 p-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-cyan-100">Co-Director Read</div>
          <p className="mt-2 text-[11px] text-zinc-100">{describeReadiness(data.decisionGate)}</p>
          <p className="mt-2 text-[11px] text-zinc-200">{describeSignal(data)}</p>
          <p className="mt-2 text-[11px] text-cyan-100">{describeNextMove(data.decisionGate)}</p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-[10px] uppercase tracking-[0.1em]">
        <Link to={`/studio/previs?project_id=${projectId}`} className="rounded border border-cyan-300/45 bg-cyan-500/15 px-2 py-1 text-cyan-100 no-underline">
          Open Previs
        </Link>
        <Link
          to={`/studio/production-board?project_id=${projectId}`}
          className="rounded border border-amber-300/45 bg-amber-500/15 px-2 py-1 text-amber-100 no-underline"
        >
          Open Production Board
        </Link>
        <Link
          to={`/studio/screening-room?project_id=${projectId}`}
          className="rounded border border-emerald-300/45 bg-emerald-500/15 px-2 py-1 text-emerald-100 no-underline"
        >
          Open Screening Room
        </Link>
      </div>

      {(data.continuityIssuesCount ?? 0) > 0 || (data.styleDriftIssuesCount ?? 0) > 0 || !data.hasDirectorSignature ? (
        <p className="mt-2 text-[11px] text-zinc-300">
          Attention points:
          {!data.hasDirectorSignature ? ' style signature still forming;' : ''}
          {(data.continuityIssuesCount ?? 0) > 0 ? ` ${data.continuityIssuesCount} continuity issue(s);` : ''}
          {(data.styleDriftIssuesCount ?? 0) > 0 ? ` ${data.styleDriftIssuesCount} style drift flag(s).` : ''}
        </p>
      ) : null}
    </section>
  )
}
