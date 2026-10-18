import { fetchJson } from './studioApi'

export type AssignedDialogue = { line_id: string; character: string; text: string; shot_id: string | null; character_id?: string; emotional_subtext?: string; pacing_tag?: string; voice_style_hint?: string }
export type CoverageStatus = 'UNASSIGNED' | 'ASSIGNED' | 'EXPLICITLY_OMITTED' | 'INTENTIONAL_SILENCE'
export type CoverageObligationStatus = Exclude<CoverageStatus, 'INTENTIONAL_SILENCE'>
export type CoverageDecision = { obligation_type: 'content' | 'dialogue' | 'shot_dialogue' | 'shot_content'; obligation_id: string; status: CoverageStatus; shot_id: string | null; reason: string }
export type CoverageObligation = { obligation_type: 'content' | 'dialogue'; obligation_id: string; source_text: string; source_speaker?: string | null; source_start: number | null; source_end: number | null; status: CoverageObligationStatus; shot_id: string | null; reason: string; reason_required: boolean }
export type ShotHandoff = { shot_id: string; opening_state: string; action_change: string; ending_state: string }
export type SettingReferenceDecision = { canonical_setting_id: string; reference_id: string }
export type SettingReferenceOption = { ref_id: string; image_url: string; target_type: string; target_id: string; kind: string; approval_state: string; canonical: boolean }
export type DirectionShot = ShotHandoff & { shot_number: number; locked: boolean; frame_url: string | null; saved_frame_url: string | null; frame_changed: boolean; previous_ending_state: string; shot_kind: string; dialogue_disposition: CoverageStatus; dialogue_disposition_reason: string }
export type SceneDirection = { project_id: string; scene_id: string; version_id: string; version_status: string; canonical_setting_id: string | null; setting_reference_decision: SettingReferenceDecision | null; setting_reference_options: SettingReferenceOption[]; dialogue: AssignedDialogue[]; coverage_obligations: CoverageObligation[]; coverage_decisions: CoverageDecision[]; unassigned_line_ids: string[]; coverage_blocked: boolean; coverage_blockers: string[]; shots: DirectionShot[]; saved: boolean }
export type SaveSceneDirection = { expected_version_id: string; dialogue: AssignedDialogue[]; coverage_decisions: CoverageDecision[]; handoffs: ShotHandoff[]; setting_reference_decision?: SettingReferenceDecision | null }
const endpoint = (project: string, scene: string) => `/api/f51/studio/projects/${encodeURIComponent(project)}/scenes/${encodeURIComponent(scene)}/direction`
export const getSceneDirection = (project: string, scene: string): Promise<SceneDirection> => fetchJson(endpoint(project, scene))
export const saveSceneDirection = (project: string, scene: string, payload: SaveSceneDirection): Promise<SceneDirection> => fetchJson(endpoint(project, scene), {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
})
