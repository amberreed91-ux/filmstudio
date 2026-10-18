import { afterEach, describe, expect, it, vi } from 'vitest'
import { buildStudioApiUrl } from './studioApi'
import {
  buildBoundReferenceCandidate,
  generatePrevisImage,
  getPrevisImagePresets,
  resolveAssetUrl,
  type GeneratedPrevisImage,
} from './previsImageApi'

afterEach(() => vi.unstubAllGlobals())

function stubJson(body: unknown, ok = true) {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: ok ? 200 : 400 }))
  vi.stubGlobal('fetch', request)
  return request
}

const still = (over: Partial<GeneratedPrevisImage> = {}): GeneratedPrevisImage => ({
  project_id: 'film-a',
  mode: 'character',
  image_url: '/outputs/reference_generation/film-a/still.png',
  seed: 314,
  aspect_ratio: '16:9',
  style_preset: 'cinematic_35mm',
  lighting_preset: 'soft_window',
  provider: 'dashscope',
  model: 'qwen-image-max',
  prompt: 'Maya at the loft window',
  created_at: '2026-10-17T00:00:00Z',
  ...over,
})

describe('previsImageApi', () => {
  it('posts the whole generation contract to the backend endpoint', async () => {
    const request = stubJson(still())
    await generatePrevisImage({
      project_id: 'film-a',
      mode: 'setting',
      prompt: 'A rain-slick loading dock',
      aspect_ratio: '9:16',
      style_preset: 'production_plate',
      lighting_preset: 'practical_night',
      seed: 0,
    })
    const [url, init] = request.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/f51/studio/generate-previs-image')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({
      project_id: 'film-a',
      mode: 'setting',
      prompt: 'A rain-slick loading dock',
      aspect_ratio: '9:16',
      style_preset: 'production_plate',
      lighting_preset: 'practical_night',
      seed: 0,
    })
  })

  it('omits the seed when the creator lets the studio draw one', async () => {
    const request = stubJson(still())
    await generatePrevisImage({
      project_id: 'film-a',
      mode: 'character',
      prompt: 'Maya',
      aspect_ratio: '1:1',
      style_preset: 'none',
      lighting_preset: 'none',
      seed: null,
    })
    const body = JSON.parse(String((request.mock.calls[0][1] as RequestInit).body))
    expect(body).not.toHaveProperty('seed')
    expect(body.seed).toBeUndefined()
  })

  it('reads the preset catalogue from the backend rather than a local copy', async () => {
    const request = stubJson({ style_presets: [], lighting_presets: [], aspect_ratios: ['16:9'], max_prompt_chars: 1200 })
    const catalogue = await getPrevisImagePresets()
    expect(String(request.mock.calls[0][0])).toContain('/api/f51/studio/previs-image-presets')
    expect(catalogue.max_prompt_chars).toBe(1200)
  })

  it('builds a candidate binding that carries shot provenance and no authority', () => {
    const candidate = buildBoundReferenceCandidate(still(), { refId: 'ref_gen_1', shotId: 'scene_001_shot_002' })
    expect(candidate.ref_id).toBe('ref_gen_1')
    expect(candidate.approval_state).toBe('candidate')
    expect(candidate.canonical).toBe(false)
    expect(candidate.source_kind).toBe('generated')
    expect(candidate.source_shot_id).toBe('scene_001_shot_002')
    expect(candidate.kind).toBe('character_full')
    expect(candidate.image_url).toBe('/outputs/reference_generation/film-a/still.png')
  })

  it('maps setting stills to environment references and blank shots to no provenance', () => {
    const candidate = buildBoundReferenceCandidate(still({ mode: 'setting' }), { shotId: '   ' })
    expect(candidate.kind).toBe('environment')
    expect(candidate.category).toBe('wide')
    expect(candidate.source_shot_id).toBeNull()
  })

  it('resolves project-relative stills against the API base and leaves absolute URLs alone', () => {
    // Relative outputs go through the shared API-base resolver, whatever it
    // resolves to in this environment; absolute URLs are never rewritten.
    expect(resolveAssetUrl('/outputs/a.png')).toBe(buildStudioApiUrl('/outputs/a.png'))
    expect(resolveAssetUrl('https://cdn.test/a.png')).toBe('https://cdn.test/a.png')
    expect(resolveAssetUrl('   ')).toBeNull()
  })
})
