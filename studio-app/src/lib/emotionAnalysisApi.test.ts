import { afterEach, describe, expect, it, vi } from 'vitest'
import { analyzeSceneEmotion, getCachedSceneEmotion } from './emotionAnalysisApi'

const envelope = {
  analysis_id: 'emotion-1',
  project_id: 'project one',
  scene_id: 'scene/1',
  context_hash: 'a'.repeat(64),
  provider: 'qwen',
  model: 'qwen3.7-max',
  cached: false,
  provider_call: true,
  created_at: '2026-08-06T12:00:00Z',
  updated_at: '2026-08-06T12:00:00Z',
  analysis: {
    scene_id: 'scene/1',
    general: { engagement: 70, tension: 60, emotional_impact: 65 },
    cinephile: { engagement: 75, tension: 64, emotional_impact: 72 },
    genre_fan: { engagement: 68, tension: 70, emotional_impact: 66 },
  },
}

describe('emotion analysis API', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('loads cached analysis with a read-only GET', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json(envelope))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getCachedSceneEmotion('project one', 'scene/1')).resolves.toEqual(envelope)

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/projects/project%20one/scenes/scene%2F1')
    expect(init?.method).toBeUndefined()
  })

  it('treats an absent cache as no result without starting analysis', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('', { status: 404 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getCachedSceneEmotion('project', 'scene')).resolves.toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('sends creator confirmation only from the explicit analyze action', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json(envelope))
    vi.stubGlobal('fetch', fetchMock)

    await expect(analyzeSceneEmotion('project one', 'scene/1')).resolves.toEqual(envelope)

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/projects/project%20one/scenes/scene%2F1/analyze')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ confirmed: true, force: false })
  })
})
