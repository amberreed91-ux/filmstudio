import { describe, expect, it } from 'vitest'
import { buildPipelineGateFlow, type LoadStateLike } from './pipelineGateFlow'
import type { ProductionAcceptanceReport, RenderJob, StudioDecisionGate } from './studioApi'

function job(over: Partial<RenderJob> = {}): RenderJob {
  return {
    id: 'job-a',
    project_id: 'project-a',
    shot_id: 'scene_001_shot_001',
    provider: 'runway',
    status: 'complete',
    progress: 100,
    retry_count: 0,
    created_at: '2026-10-17T10:00:00Z',
    updated_at: '2026-10-17T10:05:00Z',
    ...over,
  }
}

const loaded = <T,>(value: T): LoadStateLike<T> => ({ status: 'loaded', value })

const readyGate = {
  project_id: 'project-a',
  gate_status: 'ready',
  current_stage: 'production',
  blockers: [],
  warnings: [],
  ready_signals: [],
  recommended_next_action: 'Ready.',
  evidence: {},
  advisory_only: true,
  auto_approval_triggered: false,
  auto_regeneration_triggered: false,
} as StudioDecisionGate

function flow(over: { jobs?: LoadStateLike<RenderJob[]>; gate?: LoadStateLike<StudioDecisionGate>; reports?: LoadStateLike<ProductionAcceptanceReport[]> } = {}) {
  return buildPipelineGateFlow({
    jobs: over.jobs ?? loaded([]),
    gate: over.gate ?? loaded(readyGate),
    reports: over.reports ?? loaded([]),
  })
}

describe('pipelineGateFlow', () => {
  it('always reports the five provider-path stages in order', () => {
    const stages = flow()
    expect(stages.map((stage) => stage.id)).toEqual([
      'socket_isolation',
      'preflight_authorization',
      'generic_mint',
      'payload_normalizer',
      'runway_router',
    ])
    expect(stages.map((stage) => stage.order)).toEqual([1, 2, 3, 4, 5])
  })

  it('never reports a stage as cleared when no record exists', () => {
    const stages = flow()
    expect(stages.every((stage) => stage.state === 'not_established')).toBe(true)
    expect(stages[2].detail).toMatch(/not re-derived here/)
  })

  it('marks the isolation stage cleared when submissions are recorded without refusal', () => {
    const stages = flow({
      jobs: loaded([job({ metadata: { router_execution: { submission_attempted: true, router_config_id: 'cfg-1' } } })]),
    })
    expect(stages[0].state).toBe('cleared')
    expect(stages[0].detail).toMatch(/1 submission attempted/)
  })

  it('surfaces a recorded direct-submission refusal as fail-closed with its log', () => {
    const stages = flow({
      jobs: loaded([job({ metadata: { router_execution: { reason: 'direct_runway_submission_disabled', submission_attempted: false } } })]),
    })
    expect(stages[0].state).toBe('fail_closed')
    expect(stages[0].logs[0].detail).toBe('direct_runway_submission_disabled')
  })

  it('attributes contract refusals to preflight authorization', () => {
    const stages = flow({
      jobs: loaded([job({ metadata: { router_execution: { reason: 'frozen_generation_contract_unavailable' } } })]),
    })
    expect(stages[1].state).toBe('fail_closed')
    expect(stages[1].logs.map((log) => log.detail)).toContain('frozen_generation_contract_unavailable')
    // A contract refusal is not an isolation refusal.
    expect(stages[0].state).not.toBe('fail_closed')
  })

  it('reports normalization as cleared with warnings rather than a silent pass', () => {
    const stages = flow({
      jobs: loaded([job({
        metadata: {
          router_execution: {
            router_config_id: 'cfg-1',
            payload_normalized: true,
            payload_normalization_warnings: ['router_payload_normalized: secondary_references_dropped'],
          },
        },
      })]),
    })
    const normalizer = stages[3]
    expect(normalizer.state).toBe('cleared')
    expect(normalizer.detail).toMatch(/auto-optimized/)
    expect(normalizer.logs[0].detail).toContain('secondary_references_dropped')
  })

  it('reports provider identity mismatches as router fail-closed', () => {
    const stages = flow({
      jobs: loaded([job({ metadata: { router_execution: { reason: 'provider_output_identity_mismatch' } } })]),
    })
    expect(stages[4].state).toBe('fail_closed')
  })

  it('shows router configuration from recorded execution metadata', () => {
    const stages = flow({
      jobs: loaded([job({ metadata: { router_execution: { router_config_id: 'cfg-9', resolved_model: 'gen4.5', routing_provider: 'runway', runway_task_id: 'task-1' } } })]),
    })
    expect(stages[4].state).toBe('cleared')
    expect(stages[4].detail).toContain('gen4.5')
    expect(stages[4].detail).toContain('runway')
  })

  it('reads mint blockers from the decision gate instead of inventing a mint result', () => {
    const stages = flow({
      gate: loaded({
        ...readyGate,
        gate_status: 'blocked',
        blockers: ['Scene 002 confirmation digest is stale — prepare the scene again.'],
      } as StudioDecisionGate),
    })
    expect(stages[2].state).toBe('fail_closed')
    expect(stages[2].logs[0].detail).toMatch(/confirmation digest is stale/)
  })

  it('marks job-derived stages unavailable when the render queue read fails', () => {
    const stages = flow({ jobs: { status: 'unavailable', message: 'queue offline' } })
    expect(stages[0].state).toBe('unavailable')
    expect(stages[0].detail).toBe('queue offline')
    expect(stages[4].state).toBe('unavailable')
    // Mint does not depend on the render queue, so it stays honest about its own gap.
    expect(stages[2].state).toBe('not_established')
  })

  it('records provider failures as fail-closed logs without scoring anything', () => {
    const stages = flow({
      jobs: loaded([job({
        metadata: {
          provider_failure: { category: 'rate_limit', message: 'Provider is busy.' },
          pipeline_reliability: { failure_location: { phase: 'submit', reason: '429' } },
        },
      })]),
    })
    const logs = stages.flatMap((stage) => stage.logs)
    expect(logs.some((log) => log.label === 'rate_limit' && log.detail === 'Provider is busy.')).toBe(true)
    expect(logs.some((log) => log.label === 'Failure at submit')).toBe(true)
    expect(JSON.stringify(stages)).not.toMatch(/score|rating|percentage/i)
  })
})
