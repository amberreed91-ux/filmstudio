import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import CrewIntelligencePanel from './CrewIntelligencePanel'
import type { CrewIntelligenceOverview } from '../lib/studioApi'

function overview(): CrewIntelligenceOverview {
  return {
    project_id: 'project-crew-1',
    generated_at: '2026-07-27T00:00:00',
    summary: 'Department handoffs are active and carrying production context forward.',
    canonical_sources: {
      crew_reasoning_records: true,
      crew_handoffs: true,
    },
    departments: [],
    recent_reasoning: [
      {
        reasoning_id: 'reasoning-1',
        project_id: 'project-crew-1',
        task_id: 'task-1',
        agent_role: 'memory_archivist',
        department_name: 'Memory Archivist',
        reasoning_type: 'memory_recall',
        scene_id: 'scene-001',
        shot_id: null,
        asset_id: null,
        observation: 'The pause carries a callback.',
        context_used: ['memory'],
        inference: 'Shortening the pause may weaken residue.',
        recommendation_summary: 'Keep the callback legible.',
        creator_note: 'This pause is carrying the mirror callback.',
        evidence_refs: [],
        memory_refs: [],
        spine_refs: [],
        risks: [],
        downstream_departments: ['director'],
        requires_creator_decision: false,
        status: 'active',
        confidence_label: 'emerging',
        advisory_only: true,
        trace_id: 'trace-1',
        created_at: '2026-07-27T00:00:00',
        metadata: {},
      },
      {
        reasoning_id: 'reasoning-audio',
        project_id: 'project-crew-1',
        task_id: 'task-audio',
        agent_role: 'sound_designer',
        department_name: 'Performance Audio',
        reasoning_type: 'plan',
        scene_id: 'scene-001',
        shot_id: null,
        asset_id: null,
        observation: 'Dialogue needs room tone underneath it.',
        context_used: ['performance_audio'],
        inference: 'The ambience should hold pressure without covering the line.',
        recommendation_summary: 'Keep dialogue foregrounded.',
        creator_note: 'Performance Audio keeps dialogue foregrounded while room tone carries the scene pressure underneath.',
        evidence_refs: [],
        memory_refs: [],
        spine_refs: [],
        risks: [],
        downstream_departments: ['editor'],
        requires_creator_decision: false,
        status: 'active',
        confidence_label: 'emerging',
        advisory_only: true,
        trace_id: 'trace-audio',
        created_at: '2026-07-27T00:00:00',
        metadata: {},
      },
    ],
    active_handoffs: [
      {
        handoff_id: 'handoff-1',
        project_id: 'project-crew-1',
        source_role: 'editor',
        target_role: 'memory_archivist',
        source_task_id: 'task-1',
        target_task_id: null,
        scene_id: 'scene-001',
        context_summary: 'Check whether the shorter cut preserves the callback.',
        requirements: [],
        open_questions: [],
        risks: [],
        status: 'awaiting_acknowledgement',
        created_at: '2026-07-27T00:00:00',
        updated_at: '2026-07-27T00:00:00',
      },
    ],
    open_deliberations: [],
    creator_attention: [
      {
        attention_id: 'attention-1',
        project_id: 'project-crew-1',
        source_type: 'deliberation',
        source_id: 'deliberation-1',
        title: 'Crew deliberation needs your decision',
        summary: 'Should this pass favor residue or clarity?',
        recommended_action: 'Choose the revision emphasis.',
        severity: 'needs_attention',
        created_at: '2026-07-27T00:00:00',
      },
    ],
  }
}

describe('CrewIntelligencePanel', () => {
  it('renders reasoning, handoffs, and creator attention from backend overview', () => {
    const html = renderToStaticMarkup(<CrewIntelligencePanel overview={overview()} />)
    expect(html).toContain('Crew Intelligence')
    expect(html).toContain('Memory Archivist')
    expect(html).toContain('Performance Audio')
    expect(html).toContain('room tone carries the scene pressure')
    expect(html).toContain('Check whether the shorter cut preserves the callback.')
    expect(html).toContain('Should this pass favor residue or clarity?')
  })

  it('renders a quiet empty state without an overview', () => {
    const html = renderToStaticMarkup(<CrewIntelligencePanel overview={null} />)
    expect(html).toContain('Crew intelligence is waiting for a project signal.')
  })
})
