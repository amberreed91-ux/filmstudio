import { describe, expect, it } from 'vitest'
import type { RenderJob, VideoAsset, VideoKeyframe } from './studioApi'
import { resolveVisualForSceneAndShot } from './previsVisualResolver'

function mkRenderJob(overrides: Partial<RenderJob>): RenderJob {
  return {
    id: 'job-1',
    project_id: 'project-1',
    shot_id: 'shot_001',
    provider: 'runway',
    status: 'complete',
    progress: 1,
    retry_count: 0,
    created_at: '2026-05-13T00:00:00Z',
    updated_at: '2026-05-13T00:00:00Z',
    output_payload: {
      asset_url: 'https://cdn.example.com/video.mp4',
      metadata: {},
    },
    ...overrides,
  }
}

function mkAsset(overrides: Partial<VideoAsset>): VideoAsset {
  return {
    asset_id: 'asset-1',
    project_id: 'project-1',
    source_type: 'uploaded_file',
    title: 'Scene 1 Upload',
    status: 'available',
    created_at: '2026-05-13T00:00:00Z',
    updated_at: '2026-05-13T00:00:00Z',
    metadata: {},
    ...overrides,
  }
}

function mkKeyframe(overrides: Partial<VideoKeyframe>): VideoKeyframe {
  return {
    keyframe_id: 'kf-1',
    asset_id: 'asset-1',
    project_id: 'project-1',
    timestamp_seconds: 2,
    frame_path: '/tmp/frame.jpg',
    frame_url: 'https://cdn.example.com/frame.jpg',
    frame_index: 0,
    extraction_reason: 'interval',
    created_at: '2026-05-13T00:00:00Z',
    metadata: {},
    ...overrides,
  }
}

describe('resolveVisualForSceneAndShot', () => {
  const scene = { scene_id: 'scene_001', scene_title: 'Kitchen Argument', heading: 'INT. KITCHEN - NIGHT' }
  const shot = { shot_id: 'shot_001', shot_title: 'Over shoulder closeup' }

  it('matches exact shot_id first', () => {
    const result = resolveVisualForSceneAndShot(
      'project-1',
      scene,
      shot,
      [mkRenderJob({ shot_id: 'shot_001', output_payload: { asset_url: 'https://cdn.example.com/shot.mp4', metadata: {} } })],
      [],
      {},
    )
    expect(result.source_type).toBe('runway_render')
    expect(result.match_reason).toBe('exact shot_id match')
    expect(result.visual_url).toContain('shot.mp4')
  })

  it('matches scene_id from metadata when shot_id differs', () => {
    const result = resolveVisualForSceneAndShot(
      'project-1',
      scene,
      shot,
      [mkRenderJob({ shot_id: 'nonstandard', output_payload: { asset_url: 'https://cdn.example.com/scene.mp4', metadata: { scene_id: 'scene_001' } } })],
      [],
      {},
    )
    expect(result.source_type).toBe('runway_render')
    expect(result.match_reason).toContain('scene_id')
    expect(result.visual_url).toContain('scene.mp4')
  })

  it('matches exact scene_id field when present on render job', () => {
    const job = mkRenderJob({
      shot_id: 'nonstandard',
      output_payload: { asset_url: 'https://cdn.example.com/exact-scene.mp4', metadata: {} },
    }) as RenderJob & { scene_id: string }
    job.scene_id = 'scene_001'
    const result = resolveVisualForSceneAndShot('project-1', scene, shot, [job], [], {})
    expect(result.source_type).toBe('runway_render')
    expect(result.match_reason).toBe('exact scene_id match')
    expect(result.visual_url).toContain('exact-scene.mp4')
  })

  it('matches normalized scene title', () => {
    const result = resolveVisualForSceneAndShot(
      'project-1',
      scene,
      shot,
      [mkRenderJob({ shot_id: 'nonstandard', output_payload: { asset_url: 'https://cdn.example.com/title.mp4', metadata: { scene_title: 'KITCHEN-ARGUMENT' } } })],
      [],
      {},
    )
    expect(result.source_type).toBe('runway_render')
    expect(result.match_reason).toBe('normalized scene title match')
  })

  it('matches normalized shot title', () => {
    const result = resolveVisualForSceneAndShot(
      'project-1',
      scene,
      shot,
      [mkRenderJob({ shot_id: 'nonstandard', output_payload: { asset_url: 'https://cdn.example.com/shot-title.mp4', metadata: { shot_title: 'OVER SHOULDER CLOSEUP' } } })],
      [],
      {},
    )
    expect(result.source_type).toBe('runway_render')
    expect(result.match_reason).toBe('normalized shot title match')
    expect(result.visual_url).toContain('shot-title.mp4')
  })

  it('falls back safely to project-level latest completed render', () => {
    const older = mkRenderJob({ id: 'job-old', shot_id: 'unmatched-old', updated_at: '2026-05-13T00:00:00Z', output_payload: { asset_url: 'https://cdn.example.com/old.mp4', metadata: {} } })
    const newer = mkRenderJob({ id: 'job-new', updated_at: '2026-05-13T00:02:00Z', shot_id: 'unmatched', output_payload: { asset_url: 'https://cdn.example.com/new.mp4', metadata: {} } })
    const result = resolveVisualForSceneAndShot('project-1', scene, shot, [older, newer], [], {})
    expect(result.source_type).toBe('project_level_fallback')
    expect(result.match_reason).toContain('project-level fallback')
    expect(result.visual_url).toContain('new.mp4')
  })

  it('ignores unrelated project outputs', () => {
    const result = resolveVisualForSceneAndShot(
      'project-1',
      scene,
      shot,
      [mkRenderJob({ project_id: 'project-2', output_payload: { asset_url: 'https://cdn.example.com/other.mp4', metadata: { shot_id: 'shot_001' } } })],
      [],
      {},
    )
    expect(result.source_type).toBe('none')
    expect(result.visual_url).toBe('')
  })

  it('matches uploaded keyframe when render jobs are unavailable', () => {
    const asset = mkAsset({ asset_id: 'asset-1', metadata: { shot_id: 'shot_001' } })
    const keyframe = mkKeyframe({ asset_id: 'asset-1', metadata: { shot_id: 'shot_001' } })
    const result = resolveVisualForSceneAndShot('project-1', scene, shot, [], [asset], { 'asset-1': [keyframe] })
    expect(result.source_type).toBe('uploaded_video_keyframe')
    expect(result.match_reason).toContain('keyframe')
    expect(result.visual_url).toContain('frame.jpg')
  })

  it('returns honest empty state when no match exists', () => {
    const result = resolveVisualForSceneAndShot('project-1', scene, shot, [], [], {})
    expect(result.source_type).toBe('none')
    expect(result.visual_url).toBe('')
    expect(result.match_reason).toBe('no visual render yet')
  })
})
