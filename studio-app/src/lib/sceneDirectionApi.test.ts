import { afterEach, describe, expect, it, vi } from 'vitest'
import { getSceneDirection, saveSceneDirection } from './sceneDirectionApi'

afterEach(() => vi.unstubAllGlobals())
describe('scene direction contract', () => {
  it('reads the encoded project/scene without saving', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ dialogue: [], shots: [] })))
    vi.stubGlobal('fetch', fetch)
    await getSceneDirection('film / one', 'scene_001')
    expect(fetch.mock.calls[0][0]).toContain('/projects/film%20%2F%20one/scenes/scene_001/direction')
    expect(fetch.mock.calls[0][1].method).toBeUndefined()
  })
  it('sends the expected version and preserves explicit unassigned and empty choices', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}'))
    vi.stubGlobal('fetch', fetch)
    const payload = { expected_version_id: 'version-1', dialogue: [{ line_id: 'line-1', character: 'Maya', text: 'Keep it.', shot_id: null }], coverage_decisions: [{ obligation_type: 'dialogue' as const, obligation_id: 'line-1', status: 'UNASSIGNED' as const, shot_id: null, reason: '' }], handoffs: [{ shot_id: 'shot-1', opening_state: '', action_change: '', ending_state: '' }] }
    await saveSceneDirection('film', 'scene', payload)
    expect(fetch.mock.calls[0][1].method).toBe('PUT')
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(payload)
  })
  it('surfaces a stale version instead of reporting a successful save', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { message: 'The storyboard changed. Reload before saving your direction.' } }), { status: 409 })))
    await expect(saveSceneDirection('film', 'scene', { expected_version_id: 'old', dialogue: [], coverage_decisions: [], handoffs: [] })).rejects.toThrow(/storyboard changed/)
  })
})
