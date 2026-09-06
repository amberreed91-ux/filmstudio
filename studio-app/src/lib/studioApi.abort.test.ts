import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchJson } from './studioApi'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

function pendingFetch() {
  vi.stubGlobal('fetch', vi.fn((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
    if (init.signal?.aborted) return reject(new DOMException('Aborted', 'AbortError'))
    init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })))
}

describe('API cancellation and deadlines together', () => {
  it('still times out when a caller supplies a cancellation signal', async () => {
    vi.useFakeTimers(); pendingFetch()
    const caller = new AbortController()
    const result = expect(fetchJson('/test', { signal: caller.signal, timeoutMs: 100, timeoutLabel: 'Co-Director' })).rejects.toThrow('Co-Director timed out')
    await vi.advanceTimersByTimeAsync(100)
    await result
    expect(caller.signal.aborted).toBe(false)
  })

  it('cancels immediately when the user leaves the request scope', async () => {
    pendingFetch()
    const caller = new AbortController()
    const result = expect(fetchJson('/test', { signal: caller.signal })).rejects.toThrow('Request aborted.')
    caller.abort()
    await result
  })

  it('removes the caller abort listener after a successful request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}')))
    const caller = new AbortController()
    const remove = vi.spyOn(caller.signal, 'removeEventListener')
    await fetchJson('/test', { signal: caller.signal })
    expect(remove).toHaveBeenCalledWith('abort', expect.any(Function))
  })
})
