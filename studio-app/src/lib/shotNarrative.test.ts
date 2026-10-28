import { describe, expect, it } from 'vitest'
import { parseMotifRefs, readShotNarrative } from './shotNarrative'

describe('readShotNarrative', () => {
  it('accepts the camelCase shape a board card carries', () => {
    expect(readShotNarrative({ shotIntent: 'Holds on the empty chair.', motifRef: 'empty chair' })).toEqual({
      shotIntent: 'Holds on the empty chair.',
      motifRef: 'empty chair',
      motifs: ['empty chair'],
    })
  })

  it('accepts the snake_case shape the aggregate sends', () => {
    expect(readShotNarrative({ shot_intent: 'Delays the reveal by one beat.', motif_ref: 'rain' }).shotIntent)
      .toBe('Delays the reveal by one beat.')
    expect(readShotNarrative({ shot_intent: 'Delays the reveal by one beat.', motif_ref: 'rain' }).motifs)
      .toEqual(['rain'])
  })

  it('never treats a structured intent object as an authored rationale', () => {
    expect(readShotNarrative({ intent: { purpose: 'something' } }).shotIntent).toBe('')
  })

  it('stays empty for missing or malformed payloads instead of inventing one', () => {
    expect(readShotNarrative(null)).toEqual({ shotIntent: '', motifRef: '', motifs: [] })
    expect(readShotNarrative('shot')).toEqual({ shotIntent: '', motifRef: '', motifs: [] })
    expect(readShotNarrative({ shotIntent: 42, motifRef: [] })).toEqual({ shotIntent: '', motifRef: '', motifs: [] })
  })

  it('collapses whitespace in the carried rationale', () => {
    expect(readShotNarrative({ shotIntent: '  Holds   the\nframe  ' }).shotIntent).toBe('Holds the frame')
  })
})

describe('parseMotifRefs', () => {
  it('splits a reference into tags and keeps arrival order', () => {
    expect(parseMotifRefs('brass key, rain; mirror | brass key')).toEqual(['brass key', 'rain', 'mirror'])
  })

  it('returns nothing for an empty or non-string reference', () => {
    expect(parseMotifRefs('')).toEqual([])
    expect(parseMotifRefs(undefined)).toEqual([])
    expect(parseMotifRefs(['rain'])).toEqual([])
  })
})
