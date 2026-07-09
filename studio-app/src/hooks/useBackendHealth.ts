import { useCallback, useEffect, useRef, useState } from 'react'
import { STUDIO_API_BASE } from '../lib/studioApi'

const NORMAL_POLL_MS = 8_000
const RESTART_POLL_MS = 2_000
const HEALTH_TIMEOUT_MS = 4_000
const ADMIN_TOKEN = 'studio-restart-2026'

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
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* ── restart action ──────────────────────────────────────────────── */
  const restart = useCallback(() => {
    setRestarting(true)
    setHealthy(false)

    // Fire-and-forget the restart POST (server will die immediately)
    fetch(`${STUDIO_API_BASE}/api/f51/studio/admin/restart`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Admin-Token': ADMIN_TOKEN,
      },
    }).catch(() => {
      /* expected — server terminates the connection */
    })

    // Switch to fast polling after a short grace period for the process to die
    setTimeout(() => {
      if (mountedRef.current) startPolling(RESTART_POLL_MS)
    }, 1_500)
  }, [startPolling])

  return { healthy, restarting, restart }
}