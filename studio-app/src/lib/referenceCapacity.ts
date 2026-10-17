/**
 * Reference capacity visibility (Phase 2, additive alignment).
 *
 * Mirrors `ROUTER_VIDEO_MAX_REFERENCE_IMAGES = 4` from
 * `studio-backend/app/services/providers/runway_router_provider.py`.
 * Pure and presentational only: this never drops, reorders, or substitutes
 * references — it only describes how the current count relates to the
 * ceiling so over-capacity is visible before submission.
 */

/** Maximum references the video router forwards per shot. */
export const REFERENCE_CAPACITY_MAX = 4

export type ReferenceCapacityState = 'empty' | 'within' | 'at' | 'over'

export interface ReferenceCapacityStatus {
  used: number
  max: number
  remaining: number
  state: ReferenceCapacityState
  /** Badge text, e.g. "3 of 4 references used". */
  label: string
  overBy: number
}

export function referenceCapacityStatus(used: unknown, max: number = REFERENCE_CAPACITY_MAX): ReferenceCapacityStatus {
  const count = typeof used === 'number' && Number.isFinite(used) ? Math.max(0, Math.floor(used)) : 0
  const ceiling = typeof max === 'number' && Number.isFinite(max) && max > 0 ? Math.floor(max) : REFERENCE_CAPACITY_MAX
  const overBy = Math.max(0, count - ceiling)
  const state: ReferenceCapacityState =
    count === 0 ? 'empty' : overBy > 0 ? 'over' : count === ceiling ? 'at' : 'within'
  return {
    used: count,
    max: ceiling,
    remaining: Math.max(0, ceiling - count),
    state,
    label: `${count} of ${ceiling} references used`,
    overBy,
  }
}
