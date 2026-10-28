// Read-only board aggregate (one GET per load) shared by the Production Desk
// and the Production Integrity Engine.
//
// Shape mirrors GET /api/f51/studio/projects/{id}/desk-gate-summary. The Desk
// only reads this payload; it never writes, submits, or confirms anything
// through it. Next-action buttons are plain navigation links.
import { fetchJson } from './studioApi'
import { readShotNarrative } from './shotNarrative'

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
  /** One-line purpose carried from the board card. Optional in older payloads. */
  shotIntent?: string
  /** Visual motif the board tagged this shot with. Optional. */
  motifRef?: string
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
  /** Card-level purpose. A shot without its own intent inherits this. */
  shotIntent?: string
  /** Card-level motif tag. A shot without its own tag inherits this. */
  motifRef?: string
}

export type DeskGateSummary = {
  project_id: string
  scene_count: number
  scenes: DeskGateScene[]
  next_action: string | null
}

function narrativeFields(source: unknown): Pick<DeskGateShot, 'shotIntent' | 'motifRef'> {
  const { shotIntent, motifRef } = readShotNarrative(source)
  return {
    ...(shotIntent ? { shotIntent } : {}),
    ...(motifRef ? { motifRef } : {}),
  }
}

/**
 * Lift the optional narrative fields onto the typed aggregate. The wire sends
 * `shot_intent` / `motif_ref`; the board card may hand over camelCase. Both
 * land on the same two fields so every reader below the fetch boundary sees
 * one shape. Unknown fields pass through untouched.
 */
export function normalizeDeskGateSummary(raw: DeskGateSummary): DeskGateSummary {
  const scenes = Array.isArray(raw?.scenes) ? raw.scenes : []
  if (scenes.length === 0) return raw
  return {
    ...raw,
    scenes: scenes.map((scene) => ({
      ...scene,
      ...narrativeFields(scene),
      shots: (Array.isArray(scene?.shots) ? scene.shots : []).map((shot) => ({
        ...shot,
        ...narrativeFields(shot),
      })),
    })),
  }
}

export async function getDeskGateSummary(projectId: string): Promise<DeskGateSummary> {
  const summary = await fetchJson<DeskGateSummary>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/desk-gate-summary`,
  )
  return normalizeDeskGateSummary(summary)
}

// Assembly 409 ("Approve the current Film Cut before assembling") is a normal
// waiting state, never a broken panel. The fetch wrapper surfaces the detail
// as an Error message, so match its wording here.
export function isWaitingOnCutApproval(message: string): boolean {
  return /approve[^.]*film cut|film cut[^.]*approv|waiting on cut|state_error/i.test(message || '')
}
