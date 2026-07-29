import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

function createMockStorage(): Storage {
  const store = new Map<string, string>()
  return {
    get length() { return store.size },
    clear() { store.clear() },
    getItem(key: string) { return store.get(key) ?? null },
    setItem(key: string, value: string) { store.set(key, String(value)) },
    removeItem(key: string) { store.delete(key) },
    key(index: number) { return [...store.keys()][index] ?? null },
  }
}

beforeEach(() => {
  const mockStorage = createMockStorage()
  vi.stubGlobal('localStorage', mockStorage)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

import {
  STORAGE_KEYS,
  getActiveProjectId,
  setActiveProjectId,
  getSelectedProjectId,
  setSelectedProjectId,
  getDevMode,
  setDevMode,
  getOnboardingDismissed,
  setOnboardingDismissed,
  cleanupStaleStorage,
} from './localStorage'

describe('localStorage utilities', () => {
  describe('STORAGE_KEYS', () => {
    it('has expected keys', () => {
      expect(STORAGE_KEYS.ACTIVE_PROJECT_ID).toBe('studio:active-project-id')
      expect(STORAGE_KEYS.DEV_MODE).toBe('devMode')
      expect(STORAGE_KEYS.ONBOARDING_DISMISSED).toBe('studio:onboarding:dismissed')
    })
  })

  describe('getActiveProjectId / setActiveProjectId', () => {
    it('returns null when not set', () => {
      expect(getActiveProjectId()).toBeNull()
    })

    it('stores and retrieves project ID', () => {
      setActiveProjectId('proj-123')
      expect(getActiveProjectId()).toBe('proj-123')
    })

    it('removes key when null is set', () => {
      setActiveProjectId('proj-123')
      expect(getActiveProjectId()).toBe('proj-123')
      setActiveProjectId(null)
      expect(getActiveProjectId()).toBeNull()
    })
  })

  describe('getSelectedProjectId / setSelectedProjectId', () => {
    it('returns null when not set', () => {
      expect(getSelectedProjectId()).toBeNull()
    })

    it('stores and retrieves selected project ID', () => {
      setSelectedProjectId('proj-456')
      expect(getSelectedProjectId()).toBe('proj-456')
    })

    it('removes key when null is set', () => {
      setSelectedProjectId('proj-456')
      setSelectedProjectId(null)
      expect(getSelectedProjectId()).toBeNull()
    })
  })

  describe('getDevMode / setDevMode', () => {
    it('defaults to false', () => {
      expect(getDevMode()).toBe(false)
    })

    it('stores true', () => {
      setDevMode(true)
      expect(getDevMode()).toBe(true)
    })

    it('stores false', () => {
      setDevMode(true)
      setDevMode(false)
      expect(getDevMode()).toBe(false)
    })
  })

  describe('getOnboardingDismissed / setOnboardingDismissed', () => {
    it('defaults to false', () => {
      expect(getOnboardingDismissed()).toBe(false)
    })

    it('stores dismissed state', () => {
      setOnboardingDismissed(true)
      expect(getOnboardingDismissed()).toBe(true)
    })
  })

  describe('cleanupStaleStorage', () => {
    it('removes studio: prefixed keys not in known set', () => {
      localStorage.setItem('studio:old-key', 'old-value')
      localStorage.setItem('studio:active-project-id', 'proj-1')
      localStorage.setItem('other:key', 'keep')

      cleanupStaleStorage()

      expect(localStorage.getItem('studio:old-key')).toBeNull()
      expect(localStorage.getItem('studio:active-project-id')).toBe('proj-1')
      expect(localStorage.getItem('other:key')).toBe('keep')
    })

    it('does not remove non-studio: keys', () => {
      localStorage.setItem('some-random-key', 'value')
      cleanupStaleStorage()
      expect(localStorage.getItem('some-random-key')).toBe('value')
    })

    it('preserves all known storage keys', () => {
      Object.values(STORAGE_KEYS).forEach((key) => {
        localStorage.setItem(key, 'test')
      })

      cleanupStaleStorage()

      Object.values(STORAGE_KEYS).forEach((key) => {
        expect(localStorage.getItem(key)).toBe('test')
      })
    })
  })
})
