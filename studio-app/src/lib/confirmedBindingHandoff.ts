/**
 * Production Desk → generation room handoff for Desk-confirmed per-shot
 * reference binding digests (Phase C5).
 *
 * Carrier: react-router location.state — the same route-state mechanism rooms
 * already use for cross-room focus (focus_scene_id, see ProductionBoard →
 * Previs and planPrevisFocus). No new global state system, no persistence
 * table, no browser storage: the confirmation travels with the navigation
 * that takes the filmmaker to generation, and the server independently
 * re-resolves and re-verifies every digest before any job is created. A
 * confirmation lost to reload or fresh navigation simply means confirming
 * again on the Desk — the server fails closed on anything stale or missing.
 *
 * All helpers are pure and defensive: hostile or foreign route state can
 * never throw and never yields a binding.
 */

export type ConfirmedReferenceBindingMap = Record<string, string>

export type DeskConfirmedBindingState = {
  focus_scene_id?: string
  confirmed_reference_bindings?: ConfirmedReferenceBindingMap
  confirmed_reference_bindings_project?: string
}

function clean(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

/**
 * Build the route state a Desk confirmation carries into the generation
 * room. Returns undefined when there is nothing confirmable to carry — the
 * caller passes that straight to the Link/navigate `state` prop, leaving
 * navigation exactly as it is today.
 */
export function buildDeskConfirmedBindingState(input: {
  projectId: string
  sceneId: string
  shotId: string
  digest: string
}): DeskConfirmedBindingState | undefined {
  const projectId = clean(input.projectId)
  const sceneId = clean(input.sceneId)
  const shotId = clean(input.shotId)
  const digest = clean(input.digest)
  if (!projectId || !sceneId || !shotId || !digest) return undefined
  return {
    focus_scene_id: sceneId,
    confirmed_reference_bindings: { [shotId]: digest },
    confirmed_reference_bindings_project: projectId,
  }
}

/**
 * Adopt a carried confirmation for the given project. Returns the
 * shot-ID → digest map, or null when nothing was carried, the carrier
 * belongs to another project, or the shape is not a confirmation.
 * Cross-project carriers are dropped: a digest confirmed under project A
 * is never attached to project B's generation request.
 */
export function readDeskConfirmedBindings(
  locationState: unknown,
  projectId: string,
): ConfirmedReferenceBindingMap | null {
  const current = clean(projectId)
  if (!current) return null
  const state = asRecord(locationState)
  if (!state) return null
  if (clean(state.confirmed_reference_bindings_project) !== current) return null
  const raw = asRecord(state.confirmed_reference_bindings)
  if (!raw) return null
  const bindings: ConfirmedReferenceBindingMap = {}
  for (const [shotId, digest] of Object.entries(raw)) {
    const key = clean(shotId)
    const value = clean(digest)
    if (key && value) bindings[key] = value
  }
  return Object.keys(bindings).length > 0 ? bindings : null
}

/**
 * Recognize the server's fail-closed reference-confirmation rejections so
 * the generation room can distinguish "confirmation missing or stale" from
 * any other generation failure. Matches the texts raised by
 * ReferenceAssetService.verify_confirmed_binding (stale / unresolvable)
 * without coupling to their exact punctuation.
 */
export function isBindingConfirmationRejection(message: unknown): boolean {
  if (typeof message !== 'string' || !message) return false
  return (
    /confirmed reference binding/i.test(message) &&
    /(stale|does not match|cannot be verified|unresolvable)/i.test(message)
  )
}
