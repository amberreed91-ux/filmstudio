import { describe, expect, it, vi } from 'vitest'
import { BACKEND_RESTART_PATH, requestBackendRestart } from './useBackendHealth'

describe('requestBackendRestart', () => {
  it('uses the frontend supervisor while the backend is unavailable', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 202 }))

    await expect(requestBackendRestart(fetchMock)).resolves.toBe('supervisor')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      BACKEND_RESTART_PATH,
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-Admin-Token': 'studio-restart-2026' }),
      }),
    )
  })

  it('falls back to the backend restart route when no frontend supervisor exists', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }))

    await expect(requestBackendRestart(fetchMock)).resolves.toBe('backend')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(String(fetchMock.mock.calls[1][0])).toContain('/api/f51/studio/admin/restart')
  })
})
