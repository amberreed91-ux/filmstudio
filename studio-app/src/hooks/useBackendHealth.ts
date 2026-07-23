import { useCallback, useEffect, useRef, useState } from 'react'
import { STUDIO_API_BASE } from '../lib/studioApi'

const NORMAL_POLL_MS = 8_000
const RESTART_POLL_MS = 2_000
const HEALTH_TIMEOUT_MS = 4_000
const RESTART_TIMEOUT_MS = 45_000
const ADMIN_TOKEN = 'studio-restart-2026'
export const BACKEND_RESTART_PATH = '/__studio/backend/restart'

export async function requestBackendRestart(
  fetchImpl: typeof fetch = fetch,
): Promise<'supervisor' | 'backend'> {
  try {
    const response = await fetchImpl(BACKEND_RESTART_PATH, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Admin-Token': ADMIN_TOKEN,
      },
    })
    if (response.ok) return 'supervisor'
  } catch {
    // Fall through to deployments that expose only the backend restart route.
  }

  await fetchImpl(`${STUDIO_API_BASE}/api/f51/studio/admin/restart`, {
    method: 'POST',
    headers: { 'X-Admin-Token': ADMIN_TOKEN },
  })
  return 'backend'
}

export interface BackendHealthState {
  /** true when GET /health returns 2xx */
  healthy: boolean
  /** true between clicking RESTART and health coming back */
  restarting: boolean
  /** call to trigger a server restart + fast poll recovery */
  restart: () => void
}

/**
 * Polls the backend /health endpoint.
 * - Normal: every 8 s
 * - After restart: every 2 s until healthy again
 *
 * Uses raw fetch (not fetchJson) so network errors surface as offline
 * rather than being masked by error-handling wrappers.
 */
export function useBackendHealth(): BackendHealthState {
  const [healthy, setHealthy] = useState(true)
  const [restarting, setRestarting] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const restartPollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const restartTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  /* ── single health probe ─────────────────────────────────────────── */
  const probe = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch(`${STUDIO_API_BASE}/health`, {
        method: 'GET',
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
      })
      return res.ok
    } catch {
      return false
    }
  }, [])

  /* ── start / restart the polling loop ────────────────────────────── */
  const startPolling = useCallback(
    (intervalMs: number) => {
      if (intervalRef.current) clearInterval(intervalRef.current)

      // immediate first check
      probe().then((ok) => {
        if (mountedRef.current) setHealthy(ok)
      })

      intervalRef.current = setInterval(async () => {
        const ok = await probe()
        if (!mountedRef.current) return
        setHealthy(ok)
        // If we were restarting and health came back, stop fast polling
        if (ok) {
          setRestarting((prev) => {
            if (prev) {
              if (restartTimeoutRef.current) {
                clearTimeout(restartTimeoutRef.current)
                restartTimeoutRef.current = null
              }
              // switch back to normal poll rate
              startPolling(NORMAL_POLL_MS)
              return false
            }
            return prev
          })
        }
      }, intervalMs)
    },
    [probe],
  )

  /* ── mount / unmount ─────────────────────────────────────────────── */
  useEffect(() => {
    mountedRef.current = true
    startPolling(NORMAL_POLL_MS)
    return () => {
      mountedRef.current = false
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (restartPollTimerRef.current) clearTimeout(restartPollTimerRef.current)
      if (restartTimeoutRef.current) clearTimeout(restartTimeoutRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* ── restart action ──────────────────────────────────────────────── */
  const restart = useCallback(() => {
    setRestarting(true)
    setHealthy(false)

    // This endpoint belongs to Vite, which remains reachable while the Python
    // backend is down. A backend cannot restart itself after it has stopped.
    requestBackendRestart().catch(() => {
      /* health polling below will keep the UI in the recoverable offline state */
    })

    // Switch to fast polling after a short grace period for the process to die
    restartPollTimerRef.current = setTimeout(() => {
      if (mountedRef.current) startPolling(RESTART_POLL_MS)
    }, 1_500)

    // Never strand the control in RESTARTING if startup fails.
    restartTimeoutRef.current = setTimeout(() => {
      if (!mountedRef.current) return
      setRestarting(false)
      startPolling(NORMAL_POLL_MS)
    }, RESTART_TIMEOUT_MS)
  }, [startPolling])

  return { healthy, restarting, restart }
}
