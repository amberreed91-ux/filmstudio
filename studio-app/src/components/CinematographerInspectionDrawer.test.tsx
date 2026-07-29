import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { CameraGrammarPlan } from '../lib/studioApi'
import CinematographerInspectionDrawer from './CinematographerInspectionDrawer'

const plan: CameraGrammarPlan = {
  plan_id: 'cam-plan-1',
  project_id: 'project_cam',
  scene_id: 'scene_001',
  plan_scope: 'scene',
  status: 'active',
  source_fingerprint: 'abc',
  source_summary: 'A quiet close-up.',
  grammar_axes: [],
  composition_intent: 'isolation',
  lens_intent: 'shallow_subjectivity',
  movement_intent: 'locked_observation',
  lighting_intent: 'motivated_practical',
  framing_intent: 'close_up',
  depth_strategy: 'Use shallow depth.',
  blocking_strategy: 'Hold the subject apart.',
  screen_direction_strategy: 'Preserve screen direction.',
  visual_storytelling_rationale: 'The frame keeps the character visually alone.',
  render_slot_suggestions: [
    {
      slot: 'camera',
      suggestion: 'close up framing',
      rationale: 'Keep the beat intimate.',
      budget_limit: 70,
      budget_used: 16,
      evidence_refs: [],
    },
  ],
  evidence_refs: [],
  memory_refs: [],
  spine_refs: [],
  confidence_label: 'emerging',
  creator_note: 'This shot has a clear visual job.',
  advisory_only: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  metadata: {},
}

describe('CinematographerInspectionDrawer', () => {
  it('renders camera grammar inspection details when open', () => {
    const html = renderToStaticMarkup(
      <CinematographerInspectionDrawer open plan={plan} onClose={() => undefined} />,
    )

    expect(html).toContain('Cinematographer Inspection')
    expect(html).toContain('Visual Job')
    expect(html).toContain('Render Slots')
    expect(html).toContain('close up framing')
  })
})
