/**
 * Creator-facing mapping layer for scene-mint (authorization preflight)
 * refusal codes (Phase 2, additive alignment).
 *
 * Mirrors the machine-stable code vocabulary in
 * `studio-backend/app/services/scene_mint_service.py`:
 *   SCENE_NOT_MINTED, CONFIRMATION_DIGEST_MISMATCH,
 *   ENVIRONMENT_BASIS_GAP, REJECTED_BASIS_EMPTY
 *
 * Presentational only: no API contracts, no preflight invariants, and no
 * backend state are touched here. Callers pass through whatever the backend
 * returned; unknown inputs fall back to a safe generic message so raw
 * technical errors are never shown to creators.
 */

export const SCENE_NOT_MINTED = 'SCENE_NOT_MINTED'
export const CONFIRMATION_DIGEST_MISMATCH = 'CONFIRMATION_DIGEST_MISMATCH'
export const ENVIRONMENT_BASIS_GAP = 'ENVIRONMENT_BASIS_GAP'
export const REJECTED_BASIS_EMPTY = 'REJECTED_BASIS_EMPTY'

export type SceneMintRefusalCode =
  | typeof SCENE_NOT_MINTED
  | typeof CONFIRMATION_DIGEST_MISMATCH
  | typeof ENVIRONMENT_BASIS_GAP
  | typeof REJECTED_BASIS_EMPTY

export const SCENE_MINT_REFUSAL_CODES: readonly SceneMintRefusalCode[] = [
  SCENE_NOT_MINTED,
  CONFIRMATION_DIGEST_MISMATCH,
  ENVIRONMENT_BASIS_GAP,
  REJECTED_BASIS_EMPTY,
] as const

export interface SceneMintRefusalGuidance {
  code: SceneMintRefusalCode
  headline: string
  message: string
  nextStep: string
}

const GUIDANCE: Record<SceneMintRefusalCode, SceneMintRefusalGuidance> = {
  [CONFIRMATION_DIGEST_MISMATCH]: {
    code: CONFIRMATION_DIGEST_MISMATCH,
    headline: 'Shot confirmation changed after this scene was prepared',
    message:
      'The reference bindings changed after confirmation, so the scene can\u2019t be submitted as-is.',
    nextStep: 'Re-confirm the shot on the Production Desk, then prepare the scene again.',
  },
  [ENVIRONMENT_BASIS_GAP]: {
    code: ENVIRONMENT_BASIS_GAP,
    headline: 'A new environment reference appeared after preparation',
    message:
      'A new environment reference was introduced without an updated confirmation, so the scene\u2019s environment list is out of date.',
    nextStep: 'Prepare the scene again so it sees the full current list.',
  },
  [REJECTED_BASIS_EMPTY]: {
    code: REJECTED_BASIS_EMPTY,
    headline: 'Single-environment scene needs its basis recorded',
    message:
      'This scene was prepared without any rejected environments recorded, so it can\u2019t be submitted under the current rule.',
    nextStep: 'Record at least one rejected environment, then prepare the scene again.',
  },
  [SCENE_NOT_MINTED]: {
    code: SCENE_NOT_MINTED,
    headline: 'Scene authorization did not mint a valid pass',
    message:
      'This scene wasn\u2019t prepared with a saved shot confirmation, so it can\u2019t be submitted yet.',
    nextStep: 'Keep the shot confirmation saved, then prepare the scene again.',
  },
}

const GENERIC_FALLBACK =
  'This scene can\u2019t be submitted right now. Check the Production Desk for what changed, then prepare the scene again.'

export function isSceneMintRefusalCode(value: unknown): value is SceneMintRefusalCode {
  return (
    typeof value === 'string' &&
    (SCENE_MINT_REFUSAL_CODES as readonly string[]).includes(value.trim())
  )
}

/** Creator-facing message for a known refusal code, or a safe generic fallback. */
export function sceneMintRefusalMessage(code: unknown): string {
  if (!isSceneMintRefusalCode(code)) return GENERIC_FALLBACK
  const guidance = GUIDANCE[code.trim() as SceneMintRefusalCode]
  return `${guidance.message} ${guidance.nextStep}`
}

/** Full guidance card for a known refusal code, or null when unknown. */
export function sceneMintRefusalGuidance(code: unknown): SceneMintRefusalGuidance | null {
  if (!isSceneMintRefusalCode(code)) return null
  return GUIDANCE[code.trim() as SceneMintRefusalCode]
}

/**
 * Map any backend failure to creator-facing text. When the failure carries
 * a scene-mint refusal code (Error message, raw string, or structured
 * payload), the mapped creator guidance is returned; otherwise the
 * original message (or the fallback when there is none) passes through
 * unchanged. Never throws on hostile input.
 */
export function friendlyRefusalError(error: unknown, fallback: string): string {
  const refusal = extractSceneMintRefusalCode(error)
  if (refusal) return sceneMintRefusalMessage(refusal)
  if (error instanceof Error && error.message.trim()) return error.message
  if (typeof error === 'string' && error.trim()) return error
  return fallback
}

/**
 * Extract a scene-mint refusal code from a backend failure payload.
 * Checks (in order): `refusal_code` / `failure_code` / `code` fields on an
 * object, then a code token embedded in a string message. Returns null when
 * nothing matches — never throws on hostile input.
 */
export function extractSceneMintRefusalCode(payload: unknown): SceneMintRefusalCode | null {
  if (typeof payload === 'string') {
    for (const code of SCENE_MINT_REFUSAL_CODES) {
      if (payload.includes(code)) return code
    }
    return null
  }
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    const record = payload as Record<string, unknown>
    for (const key of ['refusal_code', 'failure_code', 'code']) {
      if (isSceneMintRefusalCode(record[key])) {
        return (record[key] as string).trim() as SceneMintRefusalCode
      }
    }
    for (const key of ['message', 'detail', 'error']) {
      const value = record[key]
      if (typeof value === 'string') {
        const found = extractSceneMintRefusalCode(value)
        if (found) return found
      }
    }
  }
  return null
}
