import { afterEach, describe, expect, it, vi } from 'vitest'
import { chooseTake, getTakeChoices } from './takeSelectionApi'

afterEach(() => vi.unstubAllGlobals())

describe('persistent take choices', () => {
  it('reads without selecting a take', async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ choices: [] })))
    vi.stubGlobal('fetch', request)
    await getTakeChoices('film / one', 'scene_001')
    expect(request.mock.calls[0][0]).toContain('/projects/film%20%2F%20one/scenes/scene_001/take-choices')
    expect(request.mock.calls[0][1].method).toBeUndefined()
  })
  it('saves the exact job and explicitly clears with null', async () => {
    const request = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ choices: [] }))))
    vi.stubGlobal('fetch', request)
    await chooseTake('p', 'scene_001', 3, 'older-job')
    await chooseTake('p', 'scene_001', 3, null)
    expect(request.mock.calls[0][1].method).toBe('PUT')
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ job_id: 'older-job' })
    expect(JSON.parse(request.mock.calls[1][1].body)).toEqual({ job_id: null })
  })
})
