// @vitest-environment jsdom
import { cleanup, render, renderHook, screen, waitFor, act } from '@testing-library/react'
import { createElement } from 'react'
import { StudioSessionGate } from '../components/StudioSessionGate'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useStudioSession } from './useStudioSession'

function response(status: number, body: Record<string, unknown> = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response
}

function setupFetch(
  sessionResults: Array<Response | Error | Promise<Response>>,
  accessModeResults: Array<Response | Error> = [],
) {
  const fetchMock = vi.fn<typeof fetch>().mockImplementation(async input => {
    const result = String(input).endsWith('/access-mode')
      ? accessModeResults.shift() ?? response(404)
      : await (sessionResults.shift() ?? response(503))
    if (result instanceof Error) throw result
    return result
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function sessionCallCount(fetchMock: ReturnType<typeof setupFetch>) {
  return fetchMock.mock.calls.filter(([input]) => String(input).endsWith('/session')).length
}

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('useStudioSession initialization', () => {
  it('reaches ready through the access-mode and session checks', async () => {
    const fetchMock = setupFetch([response(200)], [response(200, { local_access: false })])
    const { result } = renderHook(() => useStudioSession())

    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(fetchMock.mock.calls.map(([input]) => String(input))).toEqual([
      '/api/f51/studio/auth/access-mode',
      '/api/f51/studio/auth/session',
    ])
    expect(result.current.error).toBe('')
    expect(result.current.diagnostic).toBeNull()
  })

  it('keeps local access-mode success as an authenticated shortcut', async () => {
    const fetchMock = setupFetch([], [response(200, { local_access: true })])
    const { result } = renderHook(() => useStudioSession())

    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(result.current.diagnostic).toBeNull()
  })

  it('treats HTTP 401 as signed out without retrying', async () => {
    const fetchMock = setupFetch([response(401)])
    const { result } = renderHook(() => useStudioSession())

    await waitFor(() => expect(result.current.status).toBe('signed_out'))
    expect(sessionCallCount(fetchMock)).toBe(1)
    expect(result.current.diagnostic).toBeNull()
  })

  it('keeps checking after a network failure instead of immediately signing out', async () => {
    let completeRetry!: (result: Response) => void
    const pendingRetry = new Promise<Response>(resolve => { completeRetry = resolve })
    const fetchMock = setupFetch([new Error('network unavailable'), pendingRetry])
    const { result } = renderHook(() => useStudioSession())

    expect(result.current.status).toBe('checking')
    await waitFor(() => expect(sessionCallCount(fetchMock)).toBe(2), { timeout: 2_000 })
    expect(result.current.status).toBe('checking')
    await act(async () => { completeRetry(response(200)) })
    await waitFor(() => expect(result.current.status).toBe('ready'))
  })

  it('keeps checking after HTTP 500 instead of treating it as signed out', async () => {
    let completeRetry!: (result: Response) => void
    const pendingRetry = new Promise<Response>(resolve => { completeRetry = resolve })
    const fetchMock = setupFetch([response(500), pendingRetry])
    const { result } = renderHook(() => useStudioSession())

    await waitFor(() => expect(sessionCallCount(fetchMock)).toBe(2), { timeout: 2_000 })
    expect(result.current.status).toBe('checking')
    await act(async () => { completeRetry(response(200)) })
    await waitFor(() => expect(result.current.status).toBe('ready'))
  })

  it('recovers from a temporary network failure followed by HTTP 200 and clears the diagnostic', async () => {
    setupFetch([new Error('connection reset'), response(200)])
    const { result } = renderHook(() => useStudioSession())

    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(result.current.diagnostic).toBeNull()
  })

  it('recovers from a temporary HTTP 500 followed by HTTP 200', async () => {
    setupFetch([response(500), response(200)])
    const { result } = renderHook(() => useStudioSession())

    await waitFor(() => expect(result.current.status).toBe('ready'))
  })

  it('shows login after a temporary failure is followed by HTTP 401 without an unavailable diagnostic', async () => {
    const fetchMock = setupFetch([new Error('connection reset'), response(401)])
    const { result } = renderHook(() => useStudioSession())

    await waitFor(() => expect(result.current.status).toBe('signed_out'))
    expect(sessionCallCount(fetchMock)).toBe(2)
    expect(result.current.diagnostic).toBeNull()
  })

  it.each([
    ['network', () => new Error('private network details: https://secret.invalid/token?abc=1'), { stage: 'session', kind: 'network' }],
    ['HTTP 500', () => response(500, { detail: 'fake-secret-500' }), { stage: 'session', kind: 'http', status: 500 }],
    ['HTTP 502', () => response(502, { detail: 'fake-secret-502' }), { stage: 'session', kind: 'http', status: 502 }],
    ['HTTP 503', () => response(503, { detail: 'fake-secret-503' }), { stage: 'session', kind: 'http', status: 503 }],
  ] as const)('records only a safe session classification after retries for %s', async (_label, createFailure, expected) => {
    const fetchMock = setupFetch(Array.from({ length: 4 }, () => createFailure()))
    const { result } = renderHook(() => useStudioSession())

    await waitFor(() => expect(result.current.status).toBe('unavailable'), { timeout: 7_000 })
    expect(sessionCallCount(fetchMock)).toBe(4)
    expect(result.current.diagnostic).toEqual(expected)
    expect(result.current.diagnostic).not.toBeInstanceOf(Error)
    expect(JSON.stringify(result.current.diagnostic)).not.toMatch(/private network|secret|token|https?:/i)
  }, 8_000)

  it('records an access-mode network classification while the session check is pending', async () => {
    let completeSession!: (result: Response) => void
    const pendingSession = new Promise<Response>(resolve => { completeSession = resolve })
    setupFetch([pendingSession], [new Error('private access-mode failure')])
    const { result } = renderHook(() => useStudioSession())

    await waitFor(() => expect(result.current.diagnostic).toEqual({ stage: 'access_mode', kind: 'network' }))
    expect(result.current.status).toBe('checking')
    await act(async () => { completeSession(response(200)) })
    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(result.current.diagnostic).toBeNull()
  })

  it('records only the HTTP status for an access-mode response', async () => {
    let completeSession!: (result: Response) => void
    const pendingSession = new Promise<Response>(resolve => { completeSession = resolve })
    setupFetch([pendingSession], [response(503, { detail: 'fake-access-secret' })])
    const { result } = renderHook(() => useStudioSession())

    await waitFor(() => expect(result.current.diagnostic).toEqual({ stage: 'access_mode', kind: 'http', status: 503 }))
    await act(async () => { completeSession(response(200)) })
    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(result.current.diagnostic).toBeNull()
  })

  it('renders only the safe classification in the unavailable UI', async () => {
    const secretBody = 'Set-Cookie=fake-cookie; token=fake-token; session_id=fake-session'
    setupFetch(Array.from({ length: 4 }, () => response(502, { detail: secretBody })))
    render(createElement(StudioSessionGate, { children: createElement('div', null, 'authenticated studio') }))

    await waitFor(() => expect(screen.getByTestId('studio-session-diagnostic').textContent).toBe('Session check failed: HTTP 502'), { timeout: 7_000 })
    expect(document.body.textContent).not.toContain(secretBody)
    expect(document.body.textContent).not.toContain('fake-cookie')
    expect(document.body.textContent).not.toContain('fake-token')
  }, 8_000)

  it('never retains response bodies or raw errors in unavailable diagnostics', async () => {
    const secretBody = 'COOKIE=fake-cookie; token=fake-token; user_id=fake-user'
    const fakeResponse = response(500, { detail: secretBody })
    const fetchMock = setupFetch(Array.from({ length: 4 }, () => fakeResponse))
    const { result } = renderHook(() => useStudioSession())

    await waitFor(() => expect(result.current.status).toBe('unavailable'), { timeout: 7_000 })
    expect(result.current.diagnostic).toEqual({ stage: 'session', kind: 'http', status: 500 })
    expect(JSON.stringify(result.current.diagnostic)).not.toContain(secretBody)
    expect(result.current.diagnostic).not.toBeInstanceOf(Error)
    expect(fakeResponse.json).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledTimes(8)
  }, 8_000)

  it('stops after the bounded retry budget and preserves the existing retry count and delays', async () => {
    const timeoutSpy = vi.spyOn(globalThis, 'setTimeout')
    const fetchMock = setupFetch(Array.from({ length: 10 }, () => new Error('backend unavailable')))
    const { result } = renderHook(() => useStudioSession())

    await waitFor(() => expect(result.current.status).toBe('unavailable'), { timeout: 7_000 })
    expect(sessionCallCount(fetchMock)).toBe(4)
    expect(result.current.error).toMatch(/backend is temporarily unavailable/i)
    expect(timeoutSpy.mock.calls.map(([, delay]) => Number(delay)).filter(delay => [500, 1_000, 2_000].includes(delay))).toEqual([500, 1_000, 2_000])
    timeoutSpy.mockRestore()
  }, 8_000)

  it('does not mark a previously authenticated session signed out during a transient recheck', async () => {
    let completeRetry!: (result: Response) => void
    const pendingRetry = new Promise<Response>(resolve => { completeRetry = resolve })
    const fetchMock = setupFetch([response(200), new Error('backend restarting'), pendingRetry])
    const { result } = renderHook(() => useStudioSession())
    await waitFor(() => expect(result.current.status).toBe('ready'))

    act(() => { result.current.retrySessionCheck() })
    await waitFor(() => expect(sessionCallCount(fetchMock)).toBe(2), { timeout: 2_000 })
    expect(result.current.status).toBe('checking')
    await waitFor(() => expect(sessionCallCount(fetchMock)).toBe(3), { timeout: 2_000 })
    expect(result.current.status).toBe('checking')

    await act(async () => { completeRetry(response(200)) })
    await waitFor(() => expect(result.current.status).toBe('ready'))
  })

  it('preserves login and registration behavior', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response(200))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useStudioSession())

    await act(async () => { await result.current.signIn('maker', 'secret') })
    expect(fetchMock).toHaveBeenCalledWith('/api/f51/studio/auth/login', expect.objectContaining({ method: 'POST' }))
    expect(result.current.status).toBe('ready')
    expect(result.current.busy).toBe(false)

    await act(async () => { await result.current.signIn('new-maker', 'new-secret', 'maker@example.test') })
    expect(fetchMock).toHaveBeenLastCalledWith('/api/f51/studio/auth/register', expect.objectContaining({ method: 'POST' }))
    expect(result.current.status).toBe('ready')
    expect(result.current.busy).toBe(false)
  })
})
