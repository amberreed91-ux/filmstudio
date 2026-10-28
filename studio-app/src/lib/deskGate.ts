// Read-only board aggregate (one GET per load) shared by the Production Desk
// and the Production Integrity Engine.
//
// Shape mirrors GET /api/f51/studio/projects/{id}/desk-gate-summary. The Desk
// only reads this payload; it never writes, submits, or confirms anything
// through it. Next-action buttons are plain navigation links.
import { fetchJson } from './studioApi'

export type DeskGateShot = {
  shot_id: string
  shot_number: number | null
  d4_state: string
  d4_ready: boolean
  d6_state: string
  d6_ready: boolean
  setting_anchor: 'set' | 'blocked' | 'unknown'
  approval_state: string
  latest_job_status: string | null
  latest_job_id: string | null
  has_media: boolean
  binding_confirmation: string
  blockers: string[]
}

export type DeskGateScene = {
  scene_id: string
  scene_name: string
  approval_status: string
  board_state: string
  shot_count?: number
  ready_shot_count?: number
  shots: DeskGateShot[]
  next_action: string
  blockers: string[]
}

export type DeskGateSummary = {
  project_id: string
  scene_count: number
  scenes: DeskGateScene[]
  next_action: string | null
}

export async function getDeskGateSummary(projectId: string): Promise<DeskGateSummary> {
  return fetchJson<DeskGateSummary>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/desk-gate-summary`,
  )
}

// Assembly 409 ("Approve the current Film Cut before assembling") is a normal
// waiting state, never a broken panel. The fetch wrapper surfaces the detail
// as an Error message, so match its wording here.
export function isWaitingOnCutApproval(message: string): boolean {
  return /approve[^.]*film cut|film cut[^.]*approv|waiting on cut|state_error/i.test(message || '')
}
