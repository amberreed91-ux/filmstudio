import { describe, expect, it } from 'vitest'
import {
  adoptShotCount,
  mergeCameraPlanIntoOverrides,
  mergeCameraRecIntoOverrides,
  normalizeShotCount,
} from './previsPlanning'

/**
 * Regression tests for the Previs planning logic extracted from
 * PrevisRoom. The user-facing bug family being locked in: the shot strip
 * and the camera planner disagreed ("3 shots recommended" while the button
 * said "Plan cameras for all 1 shots"), because recommendations were
 * display-only and ad-hoc Math.max adoption drifted between call sites.
 */

describe('normalizeShotCount', () => {
  it('coerces untrusted count payloads into positive integers', () => {
    expect(normalizeShotCount(3)).toBe(3)
    expect(normalizeShotCount('4')).toBe(4)
    expect(normalizeShotCount(2.7)).toBe(2)
    expect(normalizeShotCount(0)).toBe(1)
    expect(normalizeShotCount(-5)).toBe(1)
    expect(normalizeShotCount('abc')).toBe(1)
    expect(normalizeShotCount(undefined)).toBe(1)
    expect(normalizeShotCount(null)).toBe(1)
  })
})

describe('adoptShotCount', () => {
  it('raises the shot strip to the recommended count (was display-only)', () => {
    expect(adoptShotCount(1, 3)).toBe(3)
    expect(adoptShotCount(1, '5')).toBe(5)
  })

  it('never shrinks a count the filmmaker already raised', () => {
    expect(adoptShotCount(6, 3)).toBe(6)
  })

  it('keeps at least one shot for garbage recommendations', () => {
    expect(adoptShotCount(1, 'not-a-number')).toBe(1)
  })
})

describe('mergeCameraRecIntoOverrides', () => {
  const rec = {
    camera: 'Slow push in',
    framing: 'Wide',
    lens_language: 'Wide cinema prime',
    focal_length: '24mm',
    aperture: 'f/2.8',
  }

  it('lands the recommendation fields on the requested shot', () => {
    const next = mergeCameraRecIntoOverrides({}, rec, 2)
    expect(next[2]).toMatchObject({
      camera: 'Slow push in',
      framing: 'Wide',
      lens: 'Wide cinema prime',
      focal_length: '24mm',
      aperture: 'f/2.8',
    })
  })

  it('preserves unrelated fields and other shots when merging', () => {
    const previous = {
      2: { camera: 'Handheld', sound: 'rain' },
      3: { camera: 'Static' },
    }
    const next = mergeCameraRecIntoOverrides(previous, rec, 2)
    expect(next[2].camera).toBe('Slow push in')
    expect(next[2].sound).toBe('rain') // untouched override survives
    expect(next[3].camera).toBe('Static') // other shot untouched
  })

  it('never writes shot 0 for untrusted shot numbers', () => {
    const next = mergeCameraRecIntoOverrides({}, rec, 0)
    expect(next[0]).toBeUndefined()
    expect(next[1]).toBeDefined()
  })
})

describe('mergeCameraPlanIntoOverrides', () => {
  const plan = [
    { camera: 'Wide hold', framing: 'Wide', lens_language: 'l1', focal_length: '24mm', aperture: 'f/5.6' },
    { camera: 'Push in', framing: 'Medium', lens_language: 'l2', focal_length: '50mm', aperture: 'f/2.8' },
    { camera: 'Detail insert', framing: 'Close-up', lens_language: 'l3', focal_length: '85mm', aperture: 'f/2' },
  ]

  it('maps recommendation index i to Shot i+1 (the Shot-N labeling fix)', () => {
    const next = mergeCameraPlanIntoOverrides({}, plan)
    expect(next[1].camera).toBe('Wide hold')
    expect(next[2].camera).toBe('Push in')
    expect(next[3].camera).toBe('Detail insert')
    expect(Object.keys(next).sort()).toEqual(['1', '2', '3'])
  })

  it('keeps non-camera overrides already present per shot', () => {
    const previous = { 1: { sound: 'wind' } }
    const next = mergeCameraPlanIntoOverrides(previous, plan)
    expect(next[1].camera).toBe('Wide hold')
    expect(next[1].sound).toBe('wind')
  })

  it('applies an empty plan without disturbing existing overrides', () => {
    const previous = { 1: { camera: 'Static' } }
    expect(mergeCameraPlanIntoOverrides(previous, [])).toEqual(previous)
  })
})
