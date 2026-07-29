import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import ProfessionalStudioWorkflowPanel from './ProfessionalStudioWorkflowPanel'
import type { StudioWorkflowSummary } from '../lib/studioApi'

const summary: StudioWorkflowSummary = {
  project_state: {
    project_id: 'project_s9',
    current_phase: 'screening',
    workflow_status: 'waiting_creator',
    active_version_id: 'sw_ver_1',
    active_gate_id: 'sw_gate_1',
    metadata: {},
    created_at: '2026-07-27T00:00:00Z',
    updated_at: '2026-07-27T00:00:00Z',
  },
  collaborators: [
    {
      collaborator_id: 'sw_col_1',
      project_id: 'project_s9',
      actor_id: 'producer',
      display_name: 'Producer',
      role: 'producer',
      permission_scope: 'project',
      status: 'active',
      created_at: '2026-07-27T00:00:00Z',
      updated_at: '2026-07-27T00:00:00Z',
    },
  ],
  active_versions: [
    {
      version_id: 'sw_ver_1',
      project_id: 'project_s9',
      artifact_type: 'scene',
      artifact_id: 'scene_001',
      version_number: 2,
      status: 'submitted',
      created_at: '2026-07-27T00:00:00Z',
      updated_at: '2026-07-27T00:00:00Z',
    },
  ],
  active_gates: [
    {
      gate_id: 'sw_gate_1',
      project_id: 'project_s9',
      gate_type: 'scene_review',
      target_type: 'scene',
      target_id: 'scene_001',
      version_id: 'sw_ver_1',
      status: 'ready',
      required_role: 'producer',
      required_decision: 'approve',
      latest_evaluation: { blockers: [], warnings: [], evidence: [] },
      created_at: '2026-07-27T00:00:00Z',
      updated_at: '2026-07-27T00:00:00Z',
    },
  ],
  open_tasks: [],
  recent_events: [
    {
      event_id: 'sw_evt_1',
      project_id: 'project_s9',
      event_type: 'gate_created',
      message: 'Opened scene review gate.',
      created_at: '2026-07-27T00:00:00Z',
    },
  ],
}

describe('ProfessionalStudioWorkflowPanel', () => {
  it('renders workflow phase, gates, versions, and collaborator count', () => {
    const html = renderToStaticMarkup(
      <ProfessionalStudioWorkflowPanel projectId="project_s9" initialSummary={summary} />,
    )

    expect(html).toContain('Studio Workflow')
    expect(html).toContain('Screening')
    expect(html).toContain('Waiting Creator')
    expect(html).toContain('Scene Review')
    expect(html).toContain('Scene v2')
    expect(html).toContain('Opened scene review gate.')
  })

  it('renders blocked gate evidence', () => {
    const blockedSummary: StudioWorkflowSummary = {
      ...summary,
      active_gates: [
        {
          ...summary.active_gates[0],
          status: 'blocked',
          latest_evaluation: { blockers: ['Run production acceptance before approving this package.'] },
        },
      ],
    }
    const html = renderToStaticMarkup(
      <ProfessionalStudioWorkflowPanel projectId="project_s9" initialSummary={blockedSummary} />,
    )

    expect(html).toContain('Run production acceptance before approving this package.')
  })
})
