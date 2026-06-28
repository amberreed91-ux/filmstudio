import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { WifiOff, RefreshCw } from 'lucide-react'
import { checkBackendHealth, STUDIO_API_BASE } from '../lib/studioApi'

const POLL_INTERVAL = 15_000 // 15 seconds

export default function BackendDownStatusBar() {
  const [offline, setOffline] = useState(false)
  const [checking, setChecking] = useState(false)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const mountedRef = useRef(true)

  const checkHealth = async () => {
    if (checking) return
    setChecking(true)
    try {
      const res = await fetch(`${STUDIO_API_BASE}/health`, {
        method: 'GET',
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(5000),
      })
      if (mountedRef.current) {
        if (res.ok) {
          setOffline(false)
        } else {
          setOffline(true)
        }
      }
    } catch {
      if (mountedRef.current) {
        setOffline(true)
      }
    } finally {
      if (mountedRef.current) {
        setChecking(false)
      }
    }
  }

  useEffect(() => {
    mountedRef.current = true
    // Initial check
    checkHealth()

    // Start polling
    pollingRef.current = setInterval(checkHealth, POLL_INTERVAL)

    return () => {
      mountedRef.current = false
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
      }
    }
  }, [])

  const handleRefresh = () => {
    checkHealth()
  }

  return (
    <AnimatePresence>
      {offline && (
        <motion.div
          initial={{ y: 36 }}
          animate={{ y: 0 }}
          exit={{ y: 36 }}
          transition={{ duration: 0.3, ease: 'easeInOut' }}
          className="fixed bottom-0 left-0 right-0 z-[200] flex items-center justify-between px-6"
          style={{
            height: 36,
            background: 'rgba(147, 0, 10, 0.9)',
            backdropFilter: 'blur(12px)',
            WebkitBackdropFilter: 'blur(12px)',
            borderTop: '1px solid rgba(255, 180, 171, 0.3)',
          }}
        >
          {/* Center content */}
          <div className="flex items-center gap-2 mx-auto font-status-xs text-status-xs">
            <WifiOff size={12} className="text-[#ffb4ab]" />
            <span style={{ color: '#ffdad6' }}>
              BACKEND OFFLINE — Generation and analysis unavailable
            </span>
          </div>

          {/* Refresh button */}
          <button
            type="button"
            onClick={handleRefresh}
            disabled={checking}
            className="flex items-center justify-center w-6 h-6 rounded text-[#ffdad6] hover:text-white transition-colors disabled:opacity-50"
            aria-label="Re-check backend connection"
          >
            <RefreshCw size={12} className={checking ? 'animate-spin' : ''} />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}