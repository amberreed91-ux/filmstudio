// LABELED FIXTURE — desk-board-ready-fixture (pass 1, read-only).
// The ready-state component test and the ready screenshot MUST use only this
// fixture for board data (never hand-built inline objects). Plain language,
// no scores, no percentages.
import type { DeskGateSummary } from '../ProductionDesk'

export const DESK_BOARD_READY_FIXTURE_LABEL = 'desk-board-ready-fixture'

export const deskBoardReadyFixture: DeskGateSummary = {
  project_id: 'project-ready-fixture',
  scene_count: 2,
  next_action: null,
  scenes: [
    {
      scene_id: 'scene_001',
      scene_name: 'Morning Light',
      approval_status: 'approved',
      board_state: 'ready',
      shot_count: 2,
      ready_shot_count: 2,
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
        {
          shot_id: 'scene_001_shot_002',
          shot_number: 2,
          d4_state: 'ready',
          d4_ready: true,
          d6_state: 'ready',
          d6_ready: true,
          setting_anchor: 'set',
          approval_state: 'approved',
          latest_job_status: 'complete',
          latest_job_id: 'job-ready-2',
          has_media: true,
          binding_confirmation: 'confirmed',
          blockers: [],
        },
      ],
    },
    {
      scene_id: 'scene_002',
      scene_name: 'Night Window',
      approval_status: 'approved',
      board_state: 'ready',
      shot_count: 1,
      ready_shot_count: 1,
      next_action: 'ready',
      blockers: [],
      shots: [
        {
          shot_id: 'scene_002_shot_001',
          shot_number: 1,
          d4_state: 'ready',
          d4_ready: true,
          d6_state: 'ready',
          d6_ready: true,
          setting_anchor: 'set',
          approval_state: 'approved',
          latest_job_status: 'complete',
          latest_job_id: 'job-ready-3',
          has_media: true,
          binding_confirmation: 'confirmed',
          blockers: [],
        },
      ],
    },
  ],
}

export const deskBoardReadyCut = {
  cut_id: 'cut-ready-1',
  project_id: 'project-ready-fixture',
  version_number: 2,
  status: 'approved',
  scene_order: ['scene_001', 'scene_002'],
  timeline: [],
  metadata: {},
  created_at: '2026-10-24T00:00:00Z',
  updated_at: '2026-10-24T00:00:00Z',
}

export const deskBoardReadyAssembly = {
  scenes_with_compositions: 2,
  scenes_total: 2,
  film_assembled: true,
  film_url: null,
  has_audio: false,
  film_outdated: false,
  scenes_needing_assembly: [],
}

export const deskBoardReadyScreening = {
  project_id: 'project-ready-fixture',
  outputs: [],
  current_final_output: null,
  completion_status: 'in_progress',
  warnings: [],
}

export const deskBoardReadyAcceptance = {
  project_id: 'project-ready-fixture',
  package_id: '',
  latest_acceptance_id: '',
  disposition: 'not_run',
  stale: false,
  blocker_count: 0,
  warning_count: 0,
  generated_at: '2026-10-24T00:00:00Z',
  recommended_action: 'Run acceptance after a traceable final package exists.',
}
