import { describe, expect, it } from 'vitest'
import { activeMotifs, orderMotifs } from './motifIndicators'

const threads = [
  { motif: 'rain', status: 'resolved' },
  { motif: 'mirror', status: 'abandoned' },
  { motif: 'brass key', status: 'active' },
  { motif: 'open door', status: 'active' },
]

describe('orderMotifs', () => {
  it('leads with the motifs the cut still carries and keeps arrival order otherwise', () => {
    expect(orderMotifs(threads).map((motif) => motif.motif)).toEqual(['brass key', 'open door', 'rain', 'mirror'])
  })

  it('does not mutate the payload it was handed', () => {
    const original = [...threads]
    orderMotifs(threads)
    expect(threads).toEqual(original)
  })

  it('treats a missing list as empty instead of throwing', () => {
    expect(orderMotifs(undefined as unknown as typeof threads)).toEqual([])
  })
})

describe('activeMotifs', () => {
  it('returns only active project motifs, in order', () => {
    expect(activeMotifs(threads).map((motif) => motif.motif)).toEqual(['brass key', 'open door'])
  })

  it('returns nothing when every thread has been resolved or abandoned', () => {
    expect(activeMotifs([{ motif: 'rain', status: 'resolved' }])).toEqual([])
  })
})
