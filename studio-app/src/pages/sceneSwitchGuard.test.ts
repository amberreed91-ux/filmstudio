import { describe, expect, it } from 'vitest'
import { decideRoomHandoff, decideSceneSwitch, shouldFollowSceneLink } from './sceneSwitchGuard'

/**
 * Regression tests for The Page scene selector.
 *
 * Bug being locked in: with a script autosave in flight the old handler
 * bailed out on `if (isSaving) return` before anything else, so every
 * scene selection silently snapped back to the old scene with no error
 * banner. The fix switches immediately when the pending save targets the
 * scene being left (the draft buffer is per-scene, so the right text
 * still lands on the right scene in the background) and keeps the old
 * guard only for a save racing toward a different scene.
 *
 * These inputs mirror handleSelectScene in WritersRoom.tsx:
 *   pendingSaveSceneId = draft.dirty && isSaving ? draft.sceneId : ''
 */
const base = {
  activeSceneId: 'scene_001',
  requestedSceneId: 'scene_002',
  isSaving: false,
  pendingSaveSceneId: '',
  sceneExists: true,
}

describe('The Page scene switch while a script autosave is in flight', () => {
  it('switches even when the pending save is for the scene being left (was silently blocked)', () => {
    // The exact user-facing bug: autosave in flight + user picks another scene.
    expect(decideSceneSwitch({
      ...base,
      isSaving: true,
      pendingSaveSceneId: 'scene_001', // save targets the scene we are leaving
    })).toBe('switch')
  })

  it('does not block the switch merely because isSaving is true', () => {
    // Guard keys on where the save is headed, not the saving flag alone.
    expect(decideSceneSwitch({
      ...base,
      isSaving: true,
      pendingSaveSceneId: 'scene_001', // save targets the scene we are leaving
    })).toBe('switch')
  })

  it('still waits when the in-flight save targets a different scene', () => {
    expect(decideSceneSwitch({
      ...base,
      isSaving: true,
      pendingSaveSceneId: 'scene_003',
    })).toBe('wait')
  })

  it('waits while saving with no scene attributable to the save', () => {
    // Conservative keep-the-guard path: a save is running but the dirty
    // draft does not tell us which scene it is for, so switching could
    // lose work. This preserves the pre-existing behavior for that case.
    expect(decideSceneSwitch({
      ...base,
      isSaving: true,
      pendingSaveSceneId: '',
    })).toBe('wait')
  })

  it('treats a dirty-but-not-saving draft as a plain switch', () => {
    // Unsaved edits before autosave starts must not block navigation;
    // the draft buffer preserves them for the scene being left.
    expect(decideSceneSwitch({
      ...base,
      isSaving: false,
      pendingSaveSceneId: 'scene_001', // dirty draft exists but no save in flight
    })).toBe('switch')
  })

  it('switches freely once the autosave has finished', () => {
    expect(decideSceneSwitch({
      ...base,
      isSaving: false,
      pendingSaveSceneId: '',
    })).toBe('switch')
  })

  it('ignores selecting the scene that is already open', () => {
    expect(decideSceneSwitch({
      ...base,
      requestedSceneId: 'scene_001',
      isSaving: true,
      pendingSaveSceneId: 'scene_001',
    })).toBe('ignore')
  })

  it('ignores requests for scenes that do not exist', () => {
    expect(decideSceneSwitch({
      ...base,
      requestedSceneId: 'scene_404',
      sceneExists: false,
    })).toBe('ignore')
  })
})

describe('leaving The Page while character work is unsaved (prepareRoomHandoff)', () => {
  it('blocks with the exact message while a character look is saving', () => {
    const decision = decideRoomHandoff({ characterLooksBusy: true, profileDraftCount: 0 })
    expect(decision.ok).toBe(false)
    if (!decision.ok) {
      expect(decision.reason).toBe('look-busy')
      expect(decision.message).toContain('character look is still saving')
    }
  })

  it('blocks with the exact message while profile drafts exist, even without a busy look', () => {
    const decision = decideRoomHandoff({ characterLooksBusy: false, profileDraftCount: 2 })
    expect(decision.ok).toBe(false)
    if (!decision.ok) {
      expect(decision.reason).toBe('profile-drafts')
      expect(decision.message).toContain('Save your character profile changes')
    }
  })

  it('checks the look save first when both problems exist', () => {
    const decision = decideRoomHandoff({ characterLooksBusy: true, profileDraftCount: 3 })
    expect(decision.ok).toBe(false)
    if (!decision.ok) expect(decision.reason).toBe('look-busy')
  })

  it('allows the handoff (script save still runs in the caller) when nothing is pending', () => {
    expect(decideRoomHandoff({ characterLooksBusy: false, profileDraftCount: 0 })).toEqual({ ok: true })
  })
})

describe('following incoming ?scene= links into The Page', () => {
  const linkBase = {
    querySceneId: 'scene_002',
    activeSceneId: 'scene_001' as string | null,
    editorProjectId: 'film_1',
    effectiveProjectId: 'film_1',
    isDirty: false,
    isSaving: false,
  }

  it('follows a same-project link when the editor is idle', () => {
    expect(shouldFollowSceneLink(linkBase)).toBe(true)
  })

  it('does not follow while a save is in flight or edits are unsaved', () => {
    expect(shouldFollowSceneLink({ ...linkBase, isSaving: true })).toBe(false)
    expect(shouldFollowSceneLink({ ...linkBase, isDirty: true })).toBe(false)
  })

  it('does not follow links for another project or the already-open scene', () => {
    expect(shouldFollowSceneLink({ ...linkBase, effectiveProjectId: 'film_2' })).toBe(false)
    expect(shouldFollowSceneLink({ ...linkBase, querySceneId: 'scene_001' })).toBe(false)
  })

  it('ignores empty query scenes', () => {
    expect(shouldFollowSceneLink({ ...linkBase, querySceneId: '' })).toBe(false)
  })

  it('still follows the link with no scene open yet (null active scene)', () => {
    expect(shouldFollowSceneLink({ ...linkBase, activeSceneId: null })).toBe(true)
  })
})
