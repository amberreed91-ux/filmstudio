/**
 * Pure decision logic for switching scenes from the script editor.
 *
 * Extracted from WritersRoom so the autosave-race behavior is regression
 * testable without a DOM: an in-flight autosave must never silently strand
 * the scene selector on the old scene.
 */

export type SceneSwitchInputs = {
  /** Scene currently loaded in the editor. */
  activeSceneId: string
  /** Scene the user asked to switch to. */
  requestedSceneId: string
  /** True while a script autosave is in flight. */
  isSaving: boolean
  /**
   * Scene targeted by the in-flight save ('' when nothing is pending).
   * During a save for the scene being left this equals activeSceneId,
   * which makes the switch safe: the draft buffer is per-scene, so the
   * right text still lands on the right scene in the background.
   */
  pendingSaveSceneId: string
  /** Whether a scene with the requested ID actually exists. */
  sceneExists: boolean
}

export type SceneSwitchDecision =
  /** Safe to switch; caller may leave the current scene. */
  | 'switch'
  /** A save for a different scene is in flight; keep the old guard. */
  | 'wait'
  /** Not a real switch (same scene, or the scene does not exist). */
  | 'ignore'

export function decideSceneSwitch({
  activeSceneId,
  requestedSceneId,
  isSaving,
  pendingSaveSceneId,
  sceneExists,
}: SceneSwitchInputs): SceneSwitchDecision {
  if (requestedSceneId === activeSceneId) return 'ignore'
  if (!sceneExists) return 'ignore'
  if (isSaving && pendingSaveSceneId !== activeSceneId) return 'wait'
  return 'switch'
}

// ── Room handoff (StudioShell beforeNavigate) ────────────────────────────────

export type RoomHandoffInputs = {
  /** True while a character look save/training is in flight. */
  characterLooksBusy: boolean
  /** How many unsaved character profile drafts exist. */
  profileDraftCount: number
}

export type RoomHandoffDecision =
  | { ok: true }
  | { ok: false; reason: 'look-busy' | 'profile-drafts'; message: string }

export const ROOM_HANDOFF_MESSAGES = {
  'look-busy': 'Your character look is still saving. Wait for it to finish before leaving The Page.',
  'profile-drafts': 'Save your character profile changes before leaving The Page. Your drafts are still here.',
} as const

/**
 * Gate for leaving The Page via StudioShell navigation. Mirrors the exact
 * order of prepareRoomHandoff: look saves first, then profile drafts, then
 * the script autosave (which the caller still runs via saveCurrentScene).
 */
export function decideRoomHandoff({ characterLooksBusy, profileDraftCount }: RoomHandoffInputs): RoomHandoffDecision {
  if (characterLooksBusy) return { ok: false, reason: 'look-busy', message: ROOM_HANDOFF_MESSAGES['look-busy'] }
  if (profileDraftCount > 0) return { ok: false, reason: 'profile-drafts', message: ROOM_HANDOFF_MESSAGES['profile-drafts'] }
  return { ok: true }
}

// ── Incoming same-room scene links (?scene=… from the Board / nav) ───────────

export type SceneLinkInputs = {
  querySceneId: string
  activeSceneId: string | null
  /** Project the editor last loaded. */
  editorProjectId: string
  /** Project resolved for the current URL. */
  effectiveProjectId: string
  isDirty: boolean
  isSaving: boolean
}

/**
 * Whether to follow an incoming ?scene= link. The editor must already be on
 * this project, and an in-flight save or unsaved edits take precedence —
 * handleSelectScene will not be invoked by the link effect in those cases.
 */
export function shouldFollowSceneLink({
  querySceneId,
  activeSceneId,
  editorProjectId,
  effectiveProjectId,
  isDirty,
  isSaving,
}: SceneLinkInputs): boolean {
  if (!querySceneId) return false
  if (querySceneId === activeSceneId) return false
  if (editorProjectId !== effectiveProjectId) return false
  return !isDirty && !isSaving
}
