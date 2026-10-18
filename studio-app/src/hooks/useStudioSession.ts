import { useEffect, useState } from 'react'

const SESSION_CHECK_RETRIES_MS = [500, 1_000, 2_000]

type StartupDiagnostic =
  | { stage: 'access_mode' | 'session'; kind: 'network' }
  | { stage: 'access_mode' | 'session'; kind: 'http'; status: number }

function waitForRetry(delay: number, signal: AbortSignal) {
  return new Promise<void>(resolve => {
    const finish = () => {
      clearTimeout(timer)
      signal.removeEventListener('abort', finish)
      resolve()
    }
    const timer = setTimeout(finish, delay)
    signal.addEventListener('abort', finish, { once: true })
    if (signal.aborted) finish()
  })
}

export function useStudioSession() {
  const [status, setStatus] = useState<'checking' | 'signed_out' | 'ready' | 'unavailable'>('checking')
  const [error, setError] = useState('')
  const [diagnostic, setDiagnostic] = useState<StartupDiagnostic | null>(null)
  const [busy, setBusy] = useState(false)
  const [retryKey, setRetryKey] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      for (let attempt = 0; attempt <= SESSION_CHECK_RETRIES_MS.length; attempt += 1) {
        let mode: Response | undefined
        try {
          mode = await fetch('/api/f51/studio/auth/access-mode', { signal: controller.signal })
        } catch {
          if (controller.signal.aborted) return
          setDiagnostic({ stage: 'access_mode', kind: 'network' })
        }
        if (mode) {
          if (!mode.ok) {
            setDiagnostic({ stage: 'access_mode', kind: 'http', status: mode.status })
          } else {
            setDiagnostic(null)
            try {
              if ((await mode.json() as { local_access?: boolean }).local_access) {
                setError('')
                setStatus('ready')
                return
              }
            } catch {
              if (controller.signal.aborted) return
            }
          }
        }

        try {
          const response = await fetch('/api/f51/studio/auth/session', { signal: controller.signal, credentials: 'same-origin' })
          if (response.status === 401) {
            setError('')
            setDiagnostic(null)
            setStatus('signed_out')
            return
          }
          if (response.ok) {
            setError('')
            setDiagnostic(null)
            setStatus('ready')
            return
          }
          setDiagnostic({ stage: 'session', kind: 'http', status: response.status })
        } catch {
          if (controller.signal.aborted) return
          setDiagnostic({ stage: 'session', kind: 'network' })
        }

        if (attempt < SESSION_CHECK_RETRIES_MS.length) {
          await waitForRetry(SESSION_CHECK_RETRIES_MS[attempt], controller.signal)
          if (controller.signal.aborted) return
        }
      }

      if (!controller.signal.aborted) {
        setError('The studio backend is temporarily unavailable. Your session has not been confirmed as signed out. Try again when the backend is available.')
        setStatus('unavailable')
      }
    })()
    return () => controller.abort()
  }, [retryKey])
  function retrySessionCheck() {
    setError('')
    setDiagnostic(null)
    setStatus('checking')
    setRetryKey(key => key + 1)
  }
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
  return { status, error, diagnostic, busy, signIn, retrySessionCheck }
}
