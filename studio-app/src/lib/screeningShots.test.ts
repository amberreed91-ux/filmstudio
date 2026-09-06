import { describe, expect, it } from 'vitest'
import { parseShotIdentity, sceneShotTakes } from './screeningShots'
import type { RenderJob } from './studioApi'
const job = (id: string, shotId: string, extra = {}): RenderJob => ({ id, project_id: 'film', shot_id: shotId, status: 'complete', created_at: '2026-01-01', output_payload: { asset_url: '/outputs/clip.mp4' }, ...extra } as RenderJob)

describe('Theatre shot identities', () => {
  it.each(['scene_002_shot_003', 'shot_scene_002_003'])('recognizes %s', id => {
    expect(parseShotIdentity(id)).toEqual({ sceneId: 'scene_002', shotNumber: 3 })
  })
  it('groups alternate ID formats as takes of the same shot while retaining their exact IDs', () => {
    const old = job('old', 'scene_002_shot_003')
    const newer = job('new', 'shot_scene_002_003', { created_at: '2026-02-01' })
    expect(sceneShotTakes([old, newer, newer], 'film', 'scene_002')[3].map(j => j.id)).toEqual(['new', 'old'])
  })
  it('keeps every auto-split shot and excludes foreign, failed, empty, and malformed takes', () => {
    const rows = [job('a', 'shot_scene_002_001'), job('b', 'shot_scene_002_002'), job('c', 'shot_scene_002_003'), job('foreign', 'shot_scene_002_004', { project_id: 'another' }), job('failed', 'shot_scene_002_005', { status: 'failed' }), job('empty', 'shot_scene_002_006', { output_payload: { asset_url: ' ' } }), job('bad', 'scene_002_shot_unknown')]
    expect(Object.keys(sceneShotTakes(rows, 'film', 'scene_002'))).toEqual(['1', '2', '3'])
  })
})
