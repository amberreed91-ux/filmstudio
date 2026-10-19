import type { ScenePipelineGeneratePayload, SceneScoreAmbientProvider } from './studioApi'

export type PrevisSceneScoreMode = Extract<SceneScoreAmbientProvider, 'none' | 'manual_post_render'>

export function buildPrevisScenePipelinePayload(
  scoreMode: PrevisSceneScoreMode,
  manualScorePath: string,
): ScenePipelineGeneratePayload {
  const soundtrackPath = manualScorePath.trim()
  const manualPostRender = scoreMode === 'manual_post_render'

  return {
    overwrite: true,
    on_audio_overrun: 'freeze_last_frame',
    score_ambient_provider: manualPostRender ? 'manual_post_render' : 'none',
    soundtrack: manualPostRender
      ? {
          enabled: true,
          audio_source_type: 'local_file',
          local_audio_path: soundtrackPath,
          volume: 0.18,
          fade_in_seconds: 0.5,
          fade_out_seconds: 0.75,
          loop_to_duration: true,
          style_label: 'manual_post_render',
        }
      : { enabled: false, audio_source_type: 'none' },
  }
}

export function canGeneratePrevisScenePipeline(
  scoreMode: PrevisSceneScoreMode,
  manualScorePath: string,
): boolean {
  return scoreMode !== 'manual_post_render' || manualScorePath.trim().length > 0
}

/**
 * Client idempotency key for a single-take submit, scoped to the fresh
 * preflight snapshot and the selected board shots. A same-tick double
 * confirm replays the identical key, so the backend reuses one job row;
 * a new preflight (new snapshot) mints a new key. The backend always
 * appends the frozen manifest fingerprint and shot id server-side.
 */
export function buildSingleTakeIdempotencyKey(
  preparedSnapshotId: string | null | undefined,
  storyboardShotIds: string[],
): string {
  const snapshot = (preparedSnapshotId || '').trim() || 'no-snapshot'
  const shots = [...storyboardShotIds].map((id) => id.trim()).filter(Boolean).sort().join(',')
  return `take:${snapshot}:${shots}`
}
