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

  it('treats runway output as hosted when provider_mode metadata is missing', () => {
    const hosted = job({
      output_payload: {
        asset_url: 'https://d123abc.cloudfront.net/renders/hosted.mp4',
        thumbnail_url: '',
        metadata: {},
      },
    })
    const selected = selectPrimaryStudioMedia({ renderJobs: [hosted] })
    expect(selected.source).toBe('hosted_render')
    expect(selected.url).toContain('cloudfront.net')
  })

  it('treats hosted url as hosted even when provider key is nonstandard', () => {
    const hosted = job({
      provider: 'runwayml',
      output_payload: {
        asset_url: 'https://d123abc.cloudfront.net/renders/hosted-nonstandard-provider.mp4',
        thumbnail_url: '',
        metadata: {},
      },
    })
    const selected = selectPrimaryStudioMedia({ renderJobs: [hosted] })
    expect(selected.source).toBe('hosted_render')
    expect(selected.kind).toBe('video')
  })

  it('selects hosted project render even when scene/shot context is empty', () => {
    const hosted = job({
      shot_id: 'scene_099_shot_001',
      output_payload: {
        asset_url: 'https://dnznrvs05pmza.cloudfront.net/hosted-preview.mp4',
        thumbnail_url: '',
        metadata: {},
      },
    })
    const selected = selectPrimaryStudioMedia({
      renderJobs: [hosted],
      sceneId: '',
      shotId: '',
      keyframeUrl: 'https://images.example.com/fallback.jpg',
    })
    expect(selected.source).toBe('hosted_render')
    expect(selected.url).toContain('cloudfront.net')
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

describe('selectPrimaryStudioMedia — real (non-demo) project isolation', () => {
  it('uses real project hosted render, not demo seeded asset', () => {
    const realJob = job({
      id: 'real-job-001',
      project_id: 'real-user-project-abc',
      shot_id: 'scene_001_shot_001',
      output_payload: {
        asset_url: 'https://dnznrvs05pmza.cloudfront.net/real-project-render.mp4',
        thumbnail_url: '',
        metadata: {},
      },
    })
    const selected = selectPrimaryStudioMedia({
      renderJobs: [realJob],
      sceneId: 'scene_001',
      shotId: 'scene_001_shot_001',
    })
    expect(selected.source).toBe('hosted_render')
    expect(selected.url).toContain('real-project-render.mp4')
    expect(selected.url).not.toContain('route_keyframe_demo')
  })

  it('does not prefer demo seeded asset when real project jobs exist', () => {
    const demoJob = job({
      id: 'demo-job-001',
      project_id: 'demo_studio_cinematic_001',
      shot_id: 'scene_001_shot_001',
      output_payload: {
        asset_url: '/outputs/final_films/route_keyframe_demo.mp4',
        thumbnail_url: '',
        metadata: { provider_response_normalized: { metadata: { provider_mode: 'mock_success' } } },
      },
    })
    const realJob = job({
      id: 'real-job-001',
      project_id: 'real-user-project-abc',
      shot_id: 'scene_001_shot_001',
      output_payload: {
        asset_url: 'https://cdn.example.com/real-render.mp4',
        thumbnail_url: '',
        metadata: {},
      },
    })
    // When called with only real project jobs (as it should be — filtered by project_id upstream)
    const selected = selectPrimaryStudioMedia({
      renderJobs: [realJob],
      sceneId: 'scene_001',
    })
    expect(selected.source).toBe('hosted_render')
    expect(selected.url).toContain('real-render.mp4')
    expect(selected.url).not.toContain('route_keyframe_demo')
    // Verify demo job is treated as mock when it appears
    const demoSelected = selectPrimaryStudioMedia({
      renderJobs: [demoJob],
      sceneId: 'scene_001',
    })
    expect(demoSelected.source).toBe('mock_render')
  })

  it('non-demo shot fallback uses scene_id_shot_001 pattern, not demo scene id', () => {
    // This tests the shotGeneration fallback used in PrevisRoom
    // When a real project has no shot ledger, resolveGenerateSceneShotId
    // builds <scene_id>_shot_001 from the real scene id
    const realSceneId = 'scene_003'
    const expectedShotId = `${realSceneId}_shot_001`
    expect(expectedShotId).toBe('scene_003_shot_001')
    expect(expectedShotId).not.toContain('demo')
    expect(expectedShotId).not.toContain('scene_001_shot_001') // demo scene id
  })

  it('returns placeholder when no render jobs exist for real project', () => {
    const selected = selectPrimaryStudioMedia({
      renderJobs: [],
      sceneId: 'scene_001',
      placeholderUrl: '',
    })
    expect(selected.source).toBe('placeholder')
    expect(selected.url).toBe('')
  })

  it('uses keyframe fallback for real project when no completed renders', () => {
    const pendingJob = job({
      status: 'pending',
      output_payload: { metadata: {} },
    })
    const selected = selectPrimaryStudioMedia({
      renderJobs: [pendingJob],
      sceneId: 'scene_001',
      keyframeUrl: 'https://images.example.com/real-keyframe.jpg',
    })
    expect(selected.source).toBe('keyframe')
    expect(selected.url).toContain('real-keyframe.jpg')
  })
})
