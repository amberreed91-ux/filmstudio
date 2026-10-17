/**
 * Pure planning logic for the Previs Room: shot-count normalization and
 * camera-plan merging.
 *
 * Extracted from PrevisRoom so the "UI said all 1 shots / shot strip stuck
 * at 1" family of bugs is regression testable: a shot-count recommendation
 * must flow into the shot strip and the camera planner (never shrinking a
 * count the filmmaker already raised), and a whole-scene camera plan must
 * land on the correct per-shot overrides with Shot-N numbering.
 */

/**
 * Coerce any shot-count-shaped value into a safe positive integer.
 * Handles strings, floats, zero/negative, and NaN from untrusted payloads.
 */
export function normalizeShotCount(value: unknown): number {
  const parsed = typeof value === 'number' ? value : parseInt(String(value ?? ''), 10)
  if (!Number.isFinite(parsed)) return 1
  return Math.max(1, Math.floor(parsed))
}

/**
 * Adopt a recommended shot count without shrinking a count the filmmaker
 * already raised manually. This is the invariant behind "3 shots
 * recommended" flowing into the shot strip and the "Suggest cameras for
 * all N shots" label agreeing with it.
 */
export function adoptShotCount(currentTotalShots: number, recommendedCount: unknown): number {
  return Math.max(normalizeShotCount(currentTotalShots), normalizeShotCount(recommendedCount))
}

/** Camera fields a per-shot recommendation contributes to planning details. */
export type CameraRecommendationFields = {
  camera: string
  framing: string
  lens_language: string
  focal_length: string
  aperture: string
}

/** Per-shot planning overrides, keyed by 1-based shot number. */
export type ShotOverrides = Record<number, Record<string, string>>

/** Merge one recommendation into the override for a specific shot. */
export function mergeCameraRecIntoOverrides(
  overrides: ShotOverrides,
  rec: CameraRecommendationFields,
  shotNumber: number,
): ShotOverrides {
  const shot = normalizeShotCount(shotNumber)
  return {
    ...overrides,
    [shot]: {
      ...(overrides[shot] || {}),
      camera: rec.camera,
      framing: rec.framing,
      lens: rec.lens_language,
      focal_length: rec.focal_length,
      aperture: rec.aperture,
    },
  }
}

/**
 * Apply a whole-scene camera plan: recommendation index i (0-based) targets
 * Shot i+1. Preserves any non-camera overrides already present per shot.
 */
export function mergeCameraPlanIntoOverrides(
  overrides: ShotOverrides,
  recommendations: readonly CameraRecommendationFields[],
): ShotOverrides {
  let next = overrides
  recommendations.forEach((rec, index) => {
    next = mergeCameraRecIntoOverrides(next, rec, index + 1)
  })
  return next
}
