import { describe, expect, it } from 'vitest'
import {
  buildPrevisScenePipelinePayload,
  buildSingleTakeIdempotencyKey,
  canGeneratePrevisScenePipeline,
} from './scenePipeline'

describe('Previs scene pipeline payload', () => {
  it('builds a dialogue-only scene pipeline payload by default', () => {
    expect(buildPrevisScenePipelinePayload('none', '/tmp/ignored-score.wav')).toEqual({
      overwrite: true,
      on_audio_overrun: 'freeze_last_frame',
      score_ambient_provider: 'none',
      soundtrack: {
        enabled: false,
        audio_source_type: 'none',
      },
    })
  })

  it('builds a manual post-render soundtrack payload when selected', () => {
    expect(buildPrevisScenePipelinePayload('manual_post_render', '  /tmp/score.wav  ')).toEqual({
      overwrite: true,
      on_audio_overrun: 'freeze_last_frame',
      score_ambient_provider: 'manual_post_render',
      soundtrack: {
        enabled: true,
        audio_source_type: 'local_file',
        local_audio_path: '/tmp/score.wav',
        volume: 0.18,
        fade_in_seconds: 0.5,
        fade_out_seconds: 0.75,
        loop_to_duration: true,
        style_label: 'manual_post_render',
      },
    })
  })

  it('requires a concrete path before manual post-render generation', () => {
    expect(canGeneratePrevisScenePipeline('none', '')).toBe(true)
    expect(canGeneratePrevisScenePipeline('manual_post_render', '')).toBe(false)
    expect(canGeneratePrevisScenePipeline('manual_post_render', ' /tmp/score.wav ')).toBe(true)
  })
})

describe('single-take idempotency key', () => {
  it('scopes the key to the snapshot and the selected shots', () => {
    expect(buildSingleTakeIdempotencyKey('snap-1', ['sbs-002'])).toBe('take:snap-1:sbs-002')
    expect(buildSingleTakeIdempotencyKey('snap-1', ['sbs-002'])).toBe(
      buildSingleTakeIdempotencyKey('snap-1', ['sbs-002']),
    )
  })

  it('mints a new key when the snapshot changes', () => {
    expect(buildSingleTakeIdempotencyKey('snap-1', ['sbs-002'])).not.toBe(
      buildSingleTakeIdempotencyKey('snap-2', ['sbs-002']),
    )
  })

  it('orders and trims shot ids, falling back without a snapshot', () => {
    expect(buildSingleTakeIdempotencyKey(null, [' sbs-002 ', 'sbs-001'])).toBe(
      'take:no-snapshot:sbs-001,sbs-002',
    )
  })
})
