// LABELED FIXTURE — engine-board-ready-fixture (pass 1, read-only).
// The ready-state component test and the ready screenshot MUST use only this
// fixture for board + gate data (never hand-built inline objects, never live
// data). Plain language, no scores, no percentages, no "ready to send".
import type { DeskGateSummary } from '../ProductionDesk'
import type { ShotIntegrityGates } from '../ProductionIntegrityEngine'

export const ENGINE_BOARD_READY_FIXTURE_LABEL = 'engine-board-ready-fixture'

function readyGates(shotId: string, sceneId: string): ShotIntegrityGates {
  const gate = (label: string, detail: string) => ({ state: 'pass' as const, label, detail })
  return {
    project_id: 'project-ready-fixture',
    shot_id: shotId,
    scene_id: sceneId,
    gates: {
      image: gate('Image ready', 'The approved image prompt is current.'),
      words: gate('Words ready', 'The send text passed the provider gate.'),
      look: gate('Look set', 'The setting look is settled on an approved canonical reference.'),
      settled: gate('Confirmed', 'The binding was explicitly confirmed and still matches.'),
      contract: gate(
        'Contract on file',
        'A frozen contract is persisted; it was enforced at creation/submission, not re-checked here.',
      ),
      preflight: gate(
        'Last send authorized',
        'Job job-ready-1 was authorized when sent; a new send always needs a fresh preparation.',
      ),
      spend: gate('Price on file', 'Runway priced this shot at 12 credits (recorded estimate, advisory).'),
      duplicate: gate('No duplicate risk', 'The recorded upstream task completed.'),
    },
    spend: { estimated_credits: 12, cost_status: 'estimated' },
    duplicate: { runway_task_id: 'task-ready-1' },
    binding_digest: `digest-${shotId}`,
    latest_job_id: 'job-ready-1',
    latest_job_status: 'complete',
    next_action: 'no_action',
    blockers: [],
  }
}

export const engineBoardReadyDesk: DeskGateSummary = {
  project_id: 'project-ready-fixture',
  scene_count: 1,
  next_action: null,
  scenes: [
    {
      scene_id: 'scene_001',
      scene_name: 'Morning Light',
      approval_status: 'approved',
      board_state: 'ready',
      shot_count: 1,
      ready_shot_count: 1,
      next_action: 'ready',
      blockers: [],
      shots: [
        {
          shot_id: 'scene_001_shot_001',
          shot_number: 1,
          d4_state: 'ready',
          d4_ready: true,
          d6_state: 'ready',
          d6_ready: true,
          setting_anchor: 'set',
          approval_state: 'approved',
          latest_job_status: 'complete',
          latest_job_id: 'job-ready-1',
          has_media: true,
          binding_confirmation: 'confirmed',
          blockers: [],
        },
      ],
    },
  ],
}

export const engineBoardReadyGates: Record<string, ShotIntegrityGates> = {
  scene_001_shot_001: readyGates('scene_001_shot_001', 'scene_001'),
}

export const engineBoardReadyCut = {
  cut_id: 'cut-ready-1',
  project_id: 'project-ready-fixture',
  version_number: 2,
  status: 'approved',
  scene_order: ['scene_001'],
  timeline: [],
  metadata: {},
  created_at: '2026-10-26T00:00:00Z',
  updated_at: '2026-10-26T00:00:00Z',
}

export const engineBoardReadyAssembly = {
  scenes_with_compositions: 1,
  scenes_total: 1,
  film_assembled: true,
  film_url: null,
  has_audio: false,
  film_outdated: false,
  scenes_needing_assembly: [],
}

export const engineBoardReadyScreening = {
  project_id: 'project-ready-fixture',
  outputs: [],
  current_final_output: {
    screening_output_id: 'out-ready-1',
    approved: true,
  },
  completion_status: 'complete',
  warnings: [],
}
