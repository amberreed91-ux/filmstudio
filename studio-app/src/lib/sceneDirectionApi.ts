import { fetchJson } from './studioApi'

export type AssignedDialogue = { line_id: string; character: string; text: string; shot_id: string | null; character_id?: string; emotional_subtext?: string; pacing_tag?: string; voice_style_hint?: string }
export type ShotHandoff = { shot_id: string; opening_state: string; action_change: string; ending_state: string }
export type DirectionShot = ShotHandoff & { shot_number: number; locked: boolean; frame_url: string | null; saved_frame_url: string | null; frame_changed: boolean; previous_ending_state: string }
export type SceneDirection = { project_id: string; scene_id: string; version_id: string; version_status: string; dialogue: AssignedDialogue[]; unassigned_line_ids: string[]; shots: DirectionShot[]; saved: boolean }
export type SaveSceneDirection = { expected_version_id: string; dialogue: AssignedDialogue[]; handoffs: ShotHandoff[] }
const endpoint = (project: string, scene: string) => `/api/f51/studio/projects/${encodeURIComponent(project)}/scenes/${encodeURIComponent(scene)}/direction`
export const getSceneDirection = (project: string, scene: string): Promise<SceneDirection> => fetchJson(endpoint(project, scene))
export const saveSceneDirection = (project: string, scene: string, payload: SaveSceneDirection): Promise<SceneDirection> => fetchJson(endpoint(project, scene), { method: 'PUT', body: JSON.stringify(payload) })
