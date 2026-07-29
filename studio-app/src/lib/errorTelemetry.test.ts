import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

beforeEach(() => {
  vi.stubGlobal('window', { location: { href: 'http://localhost:5000/studio/dashboard' } })
  vi.stubGlobal('navigator', { userAgent: 'test-agent' })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('errorTelemetry', () => {
  describe('reportError', () => {
    it('does nothing when TELEMETRY_ENDPOINT is not configured', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch')
      const { reportError } = await import('./errorTelemetry')
      reportError(new Error('test error'))
      expect(fetchSpy).not.toHaveBeenCalled()
    })

    it('queues errors and flushes when batch reaches 10', async () => {
      vi.stubEnv('VITE_ERROR_TELEMETRY_URL', 'http://localhost:8010')
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))

      const { reportError } = await import('./errorTelemetry')
      for (let i = 0; i < 10; i++) {
        reportError(new Error(`error ${i}`))
      }

      expect(fetchSpy).toHaveBeenCalledTimes(1)
      const [url, init] = fetchSpy.mock.calls[0]
      expect(String(url)).toContain('/api/f51/studio/errors')
      expect(init?.method).toBe('POST')
    })

    it('includes error details in the payload', async () => {
      vi.stubEnv('VITE_ERROR_TELEMETRY_URL', 'http://localhost:8010')
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))

      const { reportError } = await import('./errorTelemetry')
      const error = new Error('specific message')
      error.stack = 'Error: specific message\n  at line 1'
      reportError(error, 'component stack', 'fatal', { scene_id: 'scene_001' })

      for (let i = 0; i < 9; i++) {
        reportError(new Error(`pad ${i}`))
      }

      expect(fetchSpy).toHaveBeenCalledTimes(1)
      const [, init] = fetchSpy.mock.calls[0]
      const body = JSON.parse(String(init?.body))
      const first = body.errors[0]
      expect(first.message).toBe('specific message')
      expect(first.stack).toBe('Error: specific message\n  at line 1')
      expect(first.component_stack).toBe('component stack')
      expect(first.level).toBe('fatal')
      expect(first.context).toEqual({ scene_id: 'scene_001' })
    })

    it('sends the telemetry endpoint URL correctly', async () => {
      vi.stubEnv('VITE_ERROR_TELEMETRY_URL', 'https://telemetry.example.com')
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))

      const { reportError } = await import('./errorTelemetry')
      for (let i = 0; i < 10; i++) {
        reportError(new Error(`err ${i}`))
      }

      const [url] = fetchSpy.mock.calls[0]
      expect(String(url)).toBe('https://telemetry.example.com/api/f51/studio/errors')
    })
  })
})
