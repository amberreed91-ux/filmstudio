import { describe, expect, it } from 'vitest'
import type { RenderJob } from './studioApi'
import { selectPrimaryStudioMedia } from './studioMedia'

function job(overrides: Partial<RenderJob>): RenderJob {
  return {
    id: 'job-1',
    project_id: 'proj-1',
    shot_id: 'scene_001_shot_001',
    provider: 'runway',
    status: 'complete',
    progress: 100,
    retry_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    output_payload: {
      asset_url: '',
      thumbnail_url: '',
      metadata: {},
    },
    ...overrides,
  }
}

describe('selectPrimaryStudioMedia', () => {
  it('prefers hosted render output over keyframe fallback', () => {
    const hosted = job({
      output_payload: {
        asset_url: 'https://cdn.hosted.example.com/render.mp4',
        metadata: {
          provider_response_normalized: { metadata: { provider_mode: 'hosted_api' } },
        },
      },
    })
    const selected = selectPrimaryStudioMedia({
      renderJobs: [hosted],
      keyframeUrl: 'https://images.example.com/frame.jpg',
    })
    expect(selected.source).toBe('hosted_render')
    expect(selected.kind).toBe('video')
    expect(selected.url).toContain('render.mp4')
  })

  it('uses output_url when preview_url is missing', () => {
    const hosted = job({
      output_payload: {
        asset_url: 'https://cdn.hosted.example.com/render-no-preview.mp4',
        thumbnail_url: '',
        metadata: {
          provider_response_normalized: { metadata: { provider_mode: 'hosted_api' } },
        },
      },
    })
    const selected = selectPrimaryStudioMedia({ renderJobs: [hosted] })
    expect(selected.kind).toBe('video')
    expect(selected.url).toContain('render-no-preview.mp4')
  })

  it('treats hosted output as video even when url has no media extension', () => {
    const hosted = job({
      output_payload: {
        asset_url: 'https://cdn.hosted.example.com/output/abc123',
        metadata: {
          provider_response_normalized: { metadata: { provider_mode: 'hosted_api' } },
        },
      },
    })
    const selected = selectPrimaryStudioMedia({ renderJobs: [hosted] })
    expect(selected.source).toBe('hosted_render')
    expect(selected.kind).toBe('video')
    expect(selected.url).toContain('/output/abc123')
  })

  it('keeps mock output path working when hosted output is absent', () => {
    const mock = job({
      output_payload: {
        asset_url: '/outputs/mock-video/sample.mp4',
        metadata: {
          provider_response_normalized: { metadata: { provider_mode: 'mock_success' } },
        },
      },
    })
    const selected = selectPrimaryStudioMedia({ renderJobs: [mock] })
    expect(selected.source).toBe('mock_render')
    expect(selected.url).toBe('/outputs/mock-video/sample.mp4')
  })

  it('falls back to keyframe when no render output exists', () => {
    const selected = selectPrimaryStudioMedia({
      renderJobs: [job({ output_payload: { metadata: {} } })],
      keyframeUrl: 'https://images.example.com/fallback.jpg',
    })
    expect(selected.source).toBe('keyframe')
    expect(selected.kind).toBe('image')
    expect(selected.url).toContain('fallback.jpg')
  })
})
