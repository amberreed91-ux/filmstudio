import { describe, expect, it } from 'vitest'
import { planPrevisFocus } from './previsFocusPlan'

/**
 * Regression tests for the Previs Room's codirector_note URL param.
 *
 * Bug being locked in: APPLY TO SHOT (Screening Room) navigates to
 * /studio/previs?scene=…&shot=…&codirector_note=…. The note was applied but
 * the param was never removed from the URL, so the scene-reset and
 * auto-populate effects — which skip while the param is present — stayed
 * skipped forever. Every later scene switch looked like "nothing happens"
 * until a manual reload.
 *
 * The fix consumes the param in the same pass that applies the note. The
 * consumption happens in PrevisRoom's effect (it owns setSearchParams);
 * these tests lock the decision the effect acts on:
 * consumeCodirectorNote === true exactly when the param is present.
 */

const baseParams = () => new URLSearchParams('project_id=film_1&scene=scene_002&shot=3')

describe('Previs focus plan from URL / route state', () => {
  it('flags codirector_note for consumption whenever the param is present', () => {
    const params = baseParams()
    params.set('codirector_note', 'Hold on her hands a beat longer')

    const plan = planPrevisFocus({ searchParams: params, sceneIds: ['scene_001', 'scene_002'] })

    expect(plan).not.toBeNull()
    expect(plan!.codirectorNote).toBe('Hold on her hands a beat longer')
    expect(plan!.consumeCodirectorNote).toBe(true)
  })

  it('does not flag consumption without the param (scene links stay clean)', () => {
    const plan = planPrevisFocus({ searchParams: baseParams(), sceneIds: ['scene_001', 'scene_002'] })

    expect(plan!.codirectorNote).toBeNull()
    expect(plan!.consumeCodirectorNote).toBe(false)
  })

  it('decodes an encoded note and caps its length', () => {
    const params = baseParams()
    params.set('codirector_note', encodeURIComponent('Cut wider — let the room breathe. '.repeat(20)))

    const plan = planPrevisFocus({ searchParams: params, sceneIds: ['scene_002'] })

    expect(plan!.codirectorNote).toContain('Cut wider')
    expect(plan!.codirectorNote!.length).toBeLessThanOrEqual(200)
  })

  it('survives malformed percent-encoding instead of crashing the room', () => {
    const params = baseParams()
    params.set('codirector_note', '%zz-broken')

    const plan = planPrevisFocus({ searchParams: params, sceneIds: ['scene_002'] })

    expect(plan!.codirectorNote).toBe('%zz-broken')
    expect(plan!.consumeCodirectorNote).toBe(true)
  })

  it('reads focus scene from route state and shot from the URL', () => {
    const plan = planPrevisFocus({
      searchParams: baseParams(),
      locationState: { focus_scene_id: 'scene_005' },
      sceneIds: ['scene_005'],
    })

    expect(plan!.sceneId).toBe('scene_005')
    expect(plan!.shotNumber).toBe(3)
  })

  it('ignores invalid shot numbers (zero, negative, non-numeric)', () => {
    for (const shot of ['0', '-2', 'abc']) {
      const params = baseParams()
      params.set('shot', shot)
      expect(planPrevisFocus({ searchParams: params, sceneIds: ['scene_002'] })!.shotNumber).toBeNull()
    }
  })

  it('returns no plan when the scene is missing, unknown, or the project has no scenes', () => {
    expect(planPrevisFocus({ searchParams: new URLSearchParams('project_id=film_1'), sceneIds: ['scene_001'] })).toBeNull()
    expect(planPrevisFocus({ searchParams: baseParams(), sceneIds: ['scene_001'] })).toBeNull() // scene not in list
    expect(planPrevisFocus({ searchParams: baseParams(), sceneIds: [] })).toBeNull() // scenes not loaded yet
  })
})
