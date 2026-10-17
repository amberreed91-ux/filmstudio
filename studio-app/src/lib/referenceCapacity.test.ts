import { describe, expect, it } from 'vitest'
import { REFERENCE_CAPACITY_MAX, referenceCapacityStatus } from './referenceCapacity'

describe('referenceCapacityStatus', () => {
  it('pins the ceiling to the router video capacity of 4', () => {
    expect(REFERENCE_CAPACITY_MAX).toBe(4)
  })

  it('labels usage as "X of 4 references used"', () => {
    expect(referenceCapacityStatus(0).label).toBe('0 of 4 references used')
    expect(referenceCapacityStatus(3).label).toBe('3 of 4 references used')
    expect(referenceCapacityStatus(4).label).toBe('4 of 4 references used')
  })

  it('distinguishes empty / within / at / over states', () => {
    expect(referenceCapacityStatus(0).state).toBe('empty')
    expect(referenceCapacityStatus(2).state).toBe('within')
    expect(referenceCapacityStatus(4).state).toBe('at')
    expect(referenceCapacityStatus(5).state).toBe('over')
    expect(referenceCapacityStatus(6).overBy).toBe(2)
  })

  it('reports remaining headroom without going negative', () => {
    expect(referenceCapacityStatus(1).remaining).toBe(3)
    expect(referenceCapacityStatus(4).remaining).toBe(0)
    expect(referenceCapacityStatus(7).remaining).toBe(0)
  })

  it('sanitizes hostile input instead of throwing', () => {
    expect(referenceCapacityStatus(NaN).used).toBe(0)
    expect(referenceCapacityStatus(-3).used).toBe(0)
    expect(referenceCapacityStatus('x' as unknown as number).used).toBe(0)
    expect(referenceCapacityStatus(undefined).used).toBe(0)
    expect(referenceCapacityStatus(2.9).used).toBe(2)
  })
})
