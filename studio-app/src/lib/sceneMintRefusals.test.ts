import { describe, expect, it } from 'vitest'
import {
  CONFIRMATION_DIGEST_MISMATCH,
  ENVIRONMENT_BASIS_GAP,
  extractSceneMintRefusalCode,
  friendlyRefusalError,
  isSceneMintRefusalCode,
  REJECTED_BASIS_EMPTY,
  SCENE_MINT_REFUSAL_CODES,
  SCENE_NOT_MINTED,
  sceneMintRefusalGuidance,
  sceneMintRefusalMessage,
} from './sceneMintRefusals'

describe('sceneMintRefusals', () => {
  it('covers all four machine-stable backend codes', () => {
    expect([...SCENE_MINT_REFUSAL_CODES].sort()).toEqual(
      [
        CONFIRMATION_DIGEST_MISMATCH,
        ENVIRONMENT_BASIS_GAP,
        REJECTED_BASIS_EMPTY,
        SCENE_NOT_MINTED,
      ].sort(),
    )
  })

  it('explains that bindings changed after confirmation', () => {
    const message = sceneMintRefusalMessage(CONFIRMATION_DIGEST_MISMATCH)
    expect(message).toMatch(/changed after confirmation|bindings changed/i)
    expect(message).toMatch(/re-confirm/i)
    expect(message).not.toContain(CONFIRMATION_DIGEST_MISMATCH)
  })

  it('guides re-preparation when a new environment reference appeared', () => {
    const message = sceneMintRefusalMessage(ENVIRONMENT_BASIS_GAP)
    expect(message).toMatch(/environment/i)
    expect(message).toMatch(/prepare the scene again/i)
    expect(message).not.toContain(ENVIRONMENT_BASIS_GAP)
  })

  it('states the single-environment basis requirement', () => {
    const message = sceneMintRefusalMessage(REJECTED_BASIS_EMPTY)
    expect(message).toMatch(/rejected environment/i)
    expect(message).toMatch(/prepare the scene again/i)
    expect(message).not.toContain(REJECTED_BASIS_EMPTY)
  })

  it('notifies that authorization preflight did not mint a pass', () => {
    const message = sceneMintRefusalMessage(SCENE_NOT_MINTED)
    expect(message).toMatch(/confirmation/i)
    expect(message).toMatch(/prepare the scene again/i)
    expect(message).not.toContain(SCENE_NOT_MINTED)
  })

  it('falls back to safe generic guidance for unknown input', () => {
    for (const input of [undefined, null, '', 'SOME_OTHER_CODE', 42, {}, []]) {
      const message = sceneMintRefusalMessage(input)
      expect(message).toMatch(/can\u2019t be submitted/i)
      expect(sceneMintRefusalGuidance(input)).toBeNull()
    }
  })

  it('returns headline + message + next step guidance per code', () => {
    for (const code of SCENE_MINT_REFUSAL_CODES) {
      const guidance = sceneMintRefusalGuidance(code)
      expect(guidance?.code).toBe(code)
      expect(guidance?.headline.length).toBeGreaterThan(0)
      expect(guidance?.message.length).toBeGreaterThan(0)
      expect(guidance?.nextStep.length).toBeGreaterThan(0)
    }
  })

  it('extracts codes from payload shapes without throwing', () => {
    expect(extractSceneMintRefusalCode({ refusal_code: SCENE_NOT_MINTED })).toBe(SCENE_NOT_MINTED)
    expect(extractSceneMintRefusalCode({ failure_code: ENVIRONMENT_BASIS_GAP })).toBe(
      ENVIRONMENT_BASIS_GAP,
    )
    expect(extractSceneMintRefusalCode({ code: REJECTED_BASIS_EMPTY })).toBe(REJECTED_BASIS_EMPTY)
    expect(
      extractSceneMintRefusalCode(`Batch refused: ${CONFIRMATION_DIGEST_MISMATCH} at preflight`),
    ).toBe(CONFIRMATION_DIGEST_MISMATCH)
    expect(extractSceneMintRefusalCode({ message: 'boom: SCENE_NOT_MINTED' })).toBe(
      SCENE_NOT_MINTED,
    )
    expect(extractSceneMintRefusalCode({ refusal_code: 'other_project' })).toBeNull()
    expect(extractSceneMintRefusalCode(null)).toBeNull()
    expect(extractSceneMintRefusalCode('plain failure text')).toBeNull()
  })

  it('maps failures to creator text and passes other messages through', () => {
    expect(friendlyRefusalError(new Error(`refused: ${SCENE_NOT_MINTED}`), 'fallback')).toContain(
      'prepare the scene again',
    )
    expect(friendlyRefusalError({ refusal_code: ENVIRONMENT_BASIS_GAP }, 'fallback')).toContain(
      'environment',
    )
    expect(friendlyRefusalError(new Error('no approved canonical reference'), 'fallback')).toBe(
      'no approved canonical reference',
    )
    expect(friendlyRefusalError(null, 'fallback')).toBe('fallback')
    expect(friendlyRefusalError('', 'fallback')).toBe('fallback')
  })

  it('never throws on hostile input', () => {
    expect(() => isSceneMintRefusalCode({ toString: () => { throw new Error('x') } })).not.toThrow()
    expect(extractSceneMintRefusalCode([SCENE_NOT_MINTED])).toBeNull()
    expect(extractSceneMintRefusalCode(42)).toBeNull()
  })
})
