import type { AssignedDialogue, CoverageDecision, CoverageObligation, DirectionShot, SceneDirection } from '../../lib/sceneDirectionApi'

/**
 * Disposable Scene 002-shaped fixture for creator interface tests.
 *
 * Mirrors the live contract: 40 content obligations, 10 dialogue obligations,
 * 5 shot content obligations, 5 shot dialogue obligations — 60 decisions, all
 * UNRESOLVED, with five approved shots. No live database, no providers.
 */
export const SCENE002_FIXTURE_PROJECT_ID = 'project_5907c60cddbc'
export const SCENE002_FIXTURE_SCENE_ID = 'scene_002'
export const SCENE002_FIXTURE_VERSION_ID = 'sbv_a6096cb1fea5'
export const SCENE002_FIXTURE_SETTING_ID = 'loc-c8f88b9c'

const CONTENT_COUNT = 40
const DIALOGUE_COUNT = 10
const SHOT_COUNT = 5

export function buildScene002Fixture(): SceneDirection {
  const shots: DirectionShot[] = Array.from({ length: SHOT_COUNT }, (_, index) => ({
    shot_id: `scene_002_shot_00${index + 1}`,
    shot_number: index + 1,
    // Shot 1 is the only establishing shot: the contract only permits
    // intentional content silence on establishing/transition shots.
    shot_kind: index === 0 ? 'establishing' : 'medium_shot',
    locked: false,
    opening_state: '',
    action_change: '',
    ending_state: '',
    frame_url: null,
    saved_frame_url: null,
    frame_changed: false,
    previous_ending_state: '',
    dialogue_disposition: 'UNASSIGNED',
    dialogue_disposition_reason: '',
  }))

  const contentObligations: CoverageObligation[] = Array.from({ length: CONTENT_COUNT }, (_, index) => ({
    obligation_type: 'content',
    obligation_id: `content_${String(index + 1).padStart(2, '0')}`,
    source_text: `Canonical source unit ${index + 1}.`,
    source_start: index * 10,
    source_end: index * 10 + 9,
    status: 'UNASSIGNED',
    shot_id: null,
    reason: '',
    reason_required: false,
  }))

  const dialogue: AssignedDialogue[] = Array.from({ length: DIALOGUE_COUNT }, (_, index) => ({
    line_id: `line_${String(index + 1).padStart(2, '0')}`,
    character: index % 2 === 0 ? 'MAYA' : 'DRE',
    text: `Canonical dialogue line ${index + 1}.`,
    shot_id: null,
  }))

  const coverageDecisions: CoverageDecision[] = [
    ...contentObligations.map(row => ({ obligation_type: 'content' as const, obligation_id: row.obligation_id, status: 'UNASSIGNED' as const, shot_id: null, reason: '' })),
    ...dialogue.map(line => ({ obligation_type: 'dialogue' as const, obligation_id: line.line_id, status: 'UNASSIGNED' as const, shot_id: null, reason: '' })),
    ...shots.map(shot => ({ obligation_type: 'shot_content' as const, obligation_id: shot.shot_id, status: 'UNASSIGNED' as const, shot_id: null, reason: '' })),
    ...shots.map(shot => ({ obligation_type: 'shot_dialogue' as const, obligation_id: shot.shot_id, status: 'UNASSIGNED' as const, shot_id: null, reason: '' })),
  ]

  return {
    project_id: SCENE002_FIXTURE_PROJECT_ID,
    scene_id: SCENE002_FIXTURE_SCENE_ID,
    version_id: SCENE002_FIXTURE_VERSION_ID,
    version_status: 'approved',
    canonical_setting_id: SCENE002_FIXTURE_SETTING_ID,
    setting_reference_decision: null,
    setting_reference_options: [],
    dialogue,
    coverage_obligations: contentObligations,
    coverage_decisions: coverageDecisions,
    coverage_blocked: true,
    coverage_blockers: ['coverage unresolved'],
    unassigned_line_ids: dialogue.map(line => line.line_id),
    shots,
    saved: true,
  }
}
