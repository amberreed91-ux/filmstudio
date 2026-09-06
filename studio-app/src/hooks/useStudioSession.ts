import { useEffect, useState } from 'react'

export function useStudioSession() {
  const [status, setStatus] = useState<'loading' | 'signed_out' | 'ready'>('loading')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      try {
        const mode = await fetch('/api/f51/studio/auth/access-mode', { signal: controller.signal })
        if (mode.ok && (await mode.json()).local_access) { setStatus('ready'); return }
        const response = await fetch('/api/f51/studio/auth/session', { signal: controller.signal, credentials: 'same-origin' })
        setStatus(response.ok ? 'ready' : 'signed_out')
      } catch {
        if (!controller.signal.aborted) { setError('The studio could not connect. Try signing in again.'); setStatus('signed_out') }
      }
    })()
    return () => controller.abort()
  }, [])
  async function signIn(username: string, password: string, email?: string) {
    setBusy(true); setError('')
    try {
      const response = await fetch(`/api/f51/studio/auth/${email ? 'register' : 'login'}`, {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, ...(email ? { email } : {}) }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Unable to sign in')
      setStatus('ready')
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to sign in') }
    finally { setBusy(false) }
  }
  return { status, error, busy, signIn }
}
