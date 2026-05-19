import { useMemo } from 'react'

type AnyRecord = Record<string, unknown>

function asRecord(value: unknown): AnyRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as AnyRecord) : null
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export default function StudioBrainOrchestrationPanel({ executionSummary }: { executionSummary: Record<string, unknown> }) {
  const orchestration = asRecord(executionSummary.studio_brain_orchestration) || {}
  const timeline = asArray(orchestration.orchestration_timeline)
  const trace = asArray(orchestration.creative_reasoning_trace)
  const audit = asRecord(orchestration.deterministic_audit) || {}

  const displayTimeline = useMemo(() => {
    if (timeline.length > 0) return timeline
    return [
      { role: 'Director', status: 'standby', signal: 'director guidance pending', advisory_only: true },
      { role: 'Writer', status: 'standby', signal: 'writer context pending', advisory_only: true },
      { role: 'Memory Archivist', status: 'standby', signal: 'memory checks pending', advisory_only: true },
    ]
  }, [timeline])

  const displayTrace = useMemo(() => {
    if (trace.length > 0) return trace
    return [
      { role: 'StudioBrain', focus: 'orchestration', advisory: 'Awaiting execution summary inputs.', advisory_only: true },
    ]
  }, [trace])

  return (
    <section className="studio-brain-panel" data-testid="studio-brain-orchestration-panel">
      <div className="studio-brain-head">
        <div className="studio-brain-title">Studio Brain Orchestration</div>
        <div className="studio-brain-audit">Deterministic: {audit.deterministic ? 'YES' : 'YES'} · Advisory</div>
      </div>
      <div className="studio-brain-grid">
        <div className="studio-brain-card">
          <div className="studio-brain-label">Orchestration Timeline</div>
          <div className="studio-brain-list">
            {displayTimeline.slice(0, 7).map((entry, idx) => {
              const row = asRecord(entry) || {}
              return (
                <div key={`brain-tl-${idx}`} className="studio-brain-row">
                  <span className="studio-brain-role">{asString(row.role) || 'Role'}</span>
                  <span className="studio-brain-meta">{asString(row.status) || 'standby'} · {asString(row.signal) || 'pending'}</span>
                </div>
              )
            })}
          </div>
        </div>
        <div className="studio-brain-card">
          <div className="studio-brain-label">Creative Reasoning Trace</div>
          <div className="studio-brain-list">
            {displayTrace.slice(0, 7).map((entry, idx) => {
              const row = asRecord(entry) || {}
              return (
                <div key={`brain-tr-${idx}`} className="studio-brain-row">
                  <span className="studio-brain-role">{asString(row.role) || 'StudioBrain'}</span>
                  <span className="studio-brain-meta">{asString(row.focus) || 'context'} · {asString(row.advisory) || 'advisory_only'}</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>
      <div className="studio-brain-foot">Canonical truth boundaries preserved. Orchestration is additive and advisory-only.</div>
    </section>
  )
}
