import { describe, expect, it } from 'vitest'
import { getRouterNormalizationWarnings, isRouterPayloadNormalized } from './routerNormalization'

describe('isRouterPayloadNormalized', () => {
  it('returns true when payload_normalized flag is set', () => {
    expect(
      isRouterPayloadNormalized({
        metadata: { router_execution: { payload_normalized: true } },
      }),
    ).toBe(true)
  })

  it('returns true when normalization warnings are present without the flag', () => {
    expect(
      isRouterPayloadNormalized({
        metadata: {
          router_execution: {
            payload_normalization_warnings: ['secondary_references_sanitized:kept_1_of_3'],
          },
        },
      }),
    ).toBe(true)
  })

  it('returns true for ROUTER_PAYLOAD_NORMALIZED warning strings', () => {
    expect(
      isRouterPayloadNormalized({
        metadata: {
          router_execution: {
            payload_normalization_warnings: ['ROUTER_PAYLOAD_NORMALIZED | stage=pre_submission_normalize'],
          },
        },
      }),
    ).toBe(true)
  })

  it('returns false for standard un-normalized jobs', () => {
    expect(isRouterPayloadNormalized({ metadata: { router_execution: {} } })).toBe(false)
    expect(isRouterPayloadNormalized({ metadata: {} })).toBe(false)
    expect(isRouterPayloadNormalized({})).toBe(false)
    expect(isRouterPayloadNormalized(null)).toBe(false)
    expect(isRouterPayloadNormalized(undefined)).toBe(false)
  })

  it('returns false when payload_normalized is not true', () => {
    expect(
      isRouterPayloadNormalized({
        metadata: { router_execution: { payload_normalized: false } },
      }),
    ).toBe(false)
  })
})

describe('getRouterNormalizationWarnings', () => {
  it('returns warning strings for normalized jobs', () => {
    expect(
      getRouterNormalizationWarnings({
        metadata: {
          router_execution: { payload_normalization_warnings: ['a', 'b'] },
        },
      }),
    ).toEqual(['a', 'b'])
  })

  it('returns an empty array when no warnings exist', () => {
    expect(getRouterNormalizationWarnings({ metadata: {} })).toEqual([])
    expect(getRouterNormalizationWarnings(null)).toEqual([])
  })
})
