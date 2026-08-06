import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchOptionalJson } from './optionalStudioApi'

describe('fetchOptionalJson', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('treats a missing optional resource as an empty result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 404 })))

    await expect(fetchOptionalJson('/api/optional')).resolves.toBeNull()
  })

  it('returns JSON when the optional resource exists', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ value: 'ready' })))

    await expect(fetchOptionalJson<{ value: string }>('/api/optional')).resolves.toEqual({ value: 'ready' })
  })

  it('still surfaces non-404 failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: 'provider unavailable' }, { status: 503 })))

    await expect(fetchOptionalJson('/api/optional')).rejects.toThrow('provider unavailable')
  })
})
