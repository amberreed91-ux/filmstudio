import { describe, expect, it } from 'vitest'
import { isLegacyPrevisRunwayPicker, resolveLegacyPrevisProvider } from './legacyPrevisProvider'

describe('legacy previs provider (R4.3L Policy A)', () => {
  it.each(['runway', 'runway_router', 'runway_direct', 'Runway', 'RUNWAY_ROUTER'])(
    'never forwards a Runway-family picker value (%s)',
    (picker) => {
      expect(isLegacyPrevisRunwayPicker(picker)).toBe(true)
      expect(resolveLegacyPrevisProvider(picker)).toBe('simulated')
    },
  )

  it('passes allowed picker values through unchanged', () => {
    expect(resolveLegacyPrevisProvider(undefined)).toBeUndefined()
    expect(resolveLegacyPrevisProvider('')).toBeUndefined()
    expect(resolveLegacyPrevisProvider('simulated')).toBe('simulated')
    expect(resolveLegacyPrevisProvider('happyhorse')).toBe('happyhorse')
    expect(resolveLegacyPrevisProvider('wan')).toBe('wan')
  })
})
