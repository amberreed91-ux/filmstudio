import { afterEach, describe, expect, it, vi } from 'vitest'
import { cameraPlanFromVisualPlan, getCameraPresets } from './cameraPresetApi'
import { generateSceneStoryboard } from './studioApi'

afterEach(() => vi.unstubAllGlobals())
describe('camera planning API', () => {
  it('hydrates the canonical backend visual plan without losing the saved camera move', () => {
    expect(cameraPlanFromVisualPlan({ camera_movement: 'Track behind the subject.', framing: 'Wide shot.', environment: 'Forest' }))
      .toEqual({ camera: 'Track behind the subject.', framing: 'Wide shot.' })
    expect(cameraPlanFromVisualPlan({ camera_movement: '', framing: null })).toEqual({})
    expect(cameraPlanFromVisualPlan()).toEqual({})
  })
  it('sends explicit empty camera edits without dropping them', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ image_url: '/frame.png' })))
    vi.stubGlobal('fetch', fetch)
    await generateSceneStoryboard('film', 'scene', 'runway', 1, { camera: '' })
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ camera: '' })
  })
  it('loads the server catalog and surfaces failures', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Catalog unavailable' }), { status: 503 }))
    vi.stubGlobal('fetch', fetch)
    await expect(getCameraPresets()).rejects.toThrow('Catalog unavailable')
    expect(fetch.mock.calls[0][0]).toContain('/api/camera-presets')
  })
  it('sends the chosen camera and framing with the requested storyboard shot', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ image_url: '/frame.png' })))
    vi.stubGlobal('fetch', fetch)
    const plan = { camera: 'Orbit around the seated subject.', framing: 'Medium shot.' }
    await generateSceneStoryboard('film', 'scene', 'runway', 3, plan)
    expect(fetch.mock.calls[0][0]).toContain('shot_number=3')
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(plan)
    expect(fetch.mock.calls[0][1].headers['Content-Type']).toBe('application/json')
  })
  it('preserves legacy bodyless image generation when there is no camera override', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ image_url: '/frame.png' })))
    vi.stubGlobal('fetch', fetch)
    await generateSceneStoryboard('film', 'scene')
    expect(fetch.mock.calls[0][1].body).toBeUndefined()
  })
})
