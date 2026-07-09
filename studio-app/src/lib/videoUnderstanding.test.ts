import { describe, expect, it } from 'vitest'
import { resolveVideoUnderstandingBanner } from './videoUnderstanding'

describe('resolveVideoUnderstandingBanner', () => {
  it('describes staging when understanding is not enabled yet', () => {
    const text = resolveVideoUnderstandingBanner([
      {
        asset_id: 'a1',
        ingestion_complete: true,
        keyframes_complete: true,
        analysis_complete: false,
        memory_complete: true,
        understanding_enabled: false,
      },
    ])
    expect(text.toLowerCase()).toContain('still staging')
    expect(text.toLowerCase()).toContain('keyframes')
  })

  it('switches banner when any asset has true understanding enabled', () => {
    const text = resolveVideoUnderstandingBanner([
      {
        asset_id: 'a1',
        ingestion_complete: true,
        keyframes_complete: true,
        analysis_complete: true,
        memory_complete: true,
        understanding_enabled: true,
      },
    ])
    expect(text.toLowerCase()).toContain('visual intelligence is active')
  })
})
