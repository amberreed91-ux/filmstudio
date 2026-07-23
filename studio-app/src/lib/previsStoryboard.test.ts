import { describe, expect, it } from 'vitest'
import { chooseDurationForProvider, initialStoryboardImageState } from './previsStoryboard'

describe('initialStoryboardImageState', () => {
  it('starts successful image URLs in loading state', () => {
    expect(initialStoryboardImageState('/previs-assets/proj/shot.png', false)).toBe('loading')
  })

  it('shows unavailable for missing URLs', () => {
    expect(initialStoryboardImageState('', false)).toBe('unavailable')
    expect(initialStoryboardImageState(undefined, false)).toBe('unavailable')
  })

  it('keeps generation-in-progress distinct from unavailable', () => {
    expect(initialStoryboardImageState('', true)).toBe('generating')
  })
})

describe('chooseDurationForProvider', () => {
  it('keeps editable custom durations when the provider supports them', () => {
    expect(chooseDurationForProvider(6, {
      provider: 'Wan 2.2',
      supports_custom_duration: true,
      valid_durations_seconds: [4, 8, 12],
      nearest_valid_duration_seconds: 8,
      advisory: 'Editable.',
    }, 4)).toBe(6)
  })

  it('uses the nearest valid option for fixed-duration providers', () => {
    expect(chooseDurationForProvider(7, {
      provider: 'Fixed Provider',
      supports_custom_duration: false,
      valid_durations_seconds: [4, 8, 12],
      nearest_valid_duration_seconds: 8,
      advisory: 'Choose a fixed duration.',
    }, 4)).toBe(8)
  })

  it('clamps malformed direct edits to a usable duration', () => {
    expect(chooseDurationForProvider(Number.NaN, undefined, 4)).toBe(4)
    expect(chooseDurationForProvider(0, undefined, 4)).toBe(1)
    expect(chooseDurationForProvider(90, undefined, 4)).toBe(60)
  })
})
