import { useEffect, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { Film, User, ChevronDown, Volume2, VolumeX, Users, History } from 'lucide-react'
import { motion } from 'framer-motion'
import { useStudio } from '../context/StudioContext'
import { useAudioUX } from '../context/AudioUXContext'
import { PRIMARY_NAV_ROUTES } from '../routes'
import { persistActiveProjectId, readPersistedActiveProjectId, resolveActiveProjectId, withProjectQuery } from '../lib/projectContext'
import { STUDIO_API_BASE, triggerDebate, listDebates } from '../lib/studioApi'
import type { CoDirectorDebateEntry } from '../types/directorMemory'
import DirectorDebatePanel from './DirectorDebatePanel'

interface TopNavProps {
  showProjectPicker?: boolean
}

export default function TopNav({ showProjectPicker }: TopNavProps) {
  const apiBaseUrl = STUDIO_API_BASE
  const [backendStatus, setBackendStatus] = useState<'checking' | 'available' | 'unavailable'>('checking')
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const { loading, project, overview, isDemoMode } = useStudio()
  const { muted, toggleMuted } = useAudioUX()
  const activeProject = project || overview?.latest_project || null
  const activeProjectId = resolveActiveProjectId({
    queryProjectId: searchParams.get('project_id'),
    persistedProjectId: readPersistedActiveProjectId(),
    contextProjectId: activeProject?.project_id || '',
    overviewProjectId: overview?.latest_project?.project_id || '',
  })
  useEffect(() => {
    if (activeProjectId) persistActiveProjectId(activeProjectId)
  }, [activeProjectId])

  useEffect(() => {
    let cancelled = false

    async function checkBackend() {
      const normalizedBase = apiBaseUrl.replace(/\/+$/, '')
      try {
        const healthResponse = await fetch(`${normalizedBase}/health`, { headers: { Accept: 'application/json' } })
        if (healthResponse.ok) {
          if (!cancelled) setBackendStatus('available')
          return
        }
      } catch {
        // Fall back to the root Studio API probe below.
      }

      try {
        const rootResponse = await fetch(`${normalizedBase}/`, { headers: { Accept: 'application/json' } })
        const rootBody = await rootResponse.json().catch(() => null)
        if (rootResponse.ok && rootBody?.message === 'Studio API running') {
          if (!cancelled) setBackendStatus('available')
          return
        }
      } catch {
        // The unavailable state below is the visible signal.
      }

      if (!cancelled) setBackendStatus('unavailable')
    }

    setBackendStatus('checking')
    checkBackend()

    return () => {
      cancelled = true
    }
  }, [apiBaseUrl])

  const studioStatus = backendStatus === 'unavailable'
    ? { label: 'Backend unavailable', color: '#ef4444', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)' }
    : loading || backendStatus === 'checking'
      ? { label: 'Syncing studio...', color: 'var(--accent-cyan)', background: 'rgba(0,200,255,0.1)', border: '1px solid rgba(0,200,255,0.2)' }
      : isDemoMode
        ? { label: 'Demo Mode', color: '#f59e0b', background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)' }
        : { label: 'Studio connected', color: '#22c55e', background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.2)' }

  function isRouteActive(routePath: string) {
    if (location.pathname === routePath) return true
    if (routePath === '/studio/approval-room') {
      return location.pathname === '/studio/dashboard' || location.pathname === '/studio/approval'
    }
    return false
  }

  const [activeDebate, setActiveDebate] = useState<CoDirectorDebateEntry | null>(null)
  const [isConvening, setIsConvening] = useState(false)
  const [query, setQuery] = useState('')
  const [debateHistory, setDebateHistory] = useState<CoDirectorDebateEntry[]>([])

  const loadHistory = async () => {
    if (!activeProjectId) return
    try {
      const { debates } = await listDebates(activeProjectId)
      setDebateHistory(debates.slice(-5).reverse())
    } catch (err: any) {
      // Silently ignore 404 and other errors - no console logging
      return
    }
  }

  useEffect(() => {
    if (activeProjectId) loadHistory()
  }, [activeProjectId])

  const handleConvene = async () => {
    if (!activeProjectId || !query.trim()) return
    try {
      setIsConvening(true)
      const { debate } = await triggerDebate({
        project_id: activeProjectId,
        query: query,
        is_full_project: true
      })
      setActiveDebate(debate)
      setQuery('')
      loadHistory()
    } catch (err) {
      console.error('Failed to convene co-directors:', err)
    } finally {
      setIsConvening(false)
    }
  }

  return (
    <>
      <header
        style={{ background: '#0f0f0f', borderBottom: '0.5px solid #1e1e1e' }}
        className="flex items-center justify-between px-4 h-12 flex-shrink-0"
      >
        <div className="flex items-center gap-6">
          <Link to="/studio" className="flex items-center gap-2 text-white no-underline">
            {showProjectPicker ? (
              <span className="flex items-center gap-1 text-sm font-medium text-white p-0">
                <Film size={14} style={{ color: 'var(--color-accent)' }} />
                Project: {activeProject?.title || 'No active project'}
                <ChevronDown size={14} style={{ color: 'var(--color-text-secondary)' }} />
              </span>
            ) : (
              <span
                className="text-xs font-semibold tracking-widest uppercase"
                style={{ color: 'var(--color-accent)', letterSpacing: '0.12em' }}
              >
                STUDIO
              </span>
            )}
          </Link>
        </div>

        <nav className="flex items-center gap-6">
          {PRIMARY_NAV_ROUTES.map((route) => {
            const active = isRouteActive(route.path)
            return (
              <Link
                key={route.path}
                to={withProjectQuery(route.path, activeProjectId)}
                className="text-xs no-underline transition-colors"
                style={{
                  color: active ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
                  position: 'relative',
                }}
              >
                {route.label}
                {active && (
                  <motion.div
                    layoutId="active-tab"
                    style={{
                      position: 'absolute',
                      bottom: -4,
                      left: 0,
                      right: 0,
                      height: '1.5px',
                      backgroundColor: 'var(--color-accent)',
                    }}
                    transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                  />
                )}
              </Link>
            )
          })}
          {activeProject?.project_id && (
            <Link
              to={withProjectQuery(`/studio/project/${activeProject.project_id}`, activeProjectId)}
              className="text-xs no-underline transition-colors"
              style={{
                color: location.pathname.startsWith('/studio/project/')
                  ? 'var(--color-text-primary)'
                  : 'var(--color-text-muted)',
                position: 'relative',
              }}
            >
              Workspace
              {location.pathname.startsWith('/studio/project/') && (
                <motion.div
                  layoutId="active-tab"
                  style={{
                    position: 'absolute',
                    bottom: -4,
                    left: 0,
                    right: 0,
                    height: '1.5px',
                    backgroundColor: 'var(--color-accent)',
                  }}
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                />
              )}
            </Link>
          )}
        </nav>

        <div className="flex items-center gap-3">
          {activeProjectId && (
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleConvene()}
                placeholder="Ask co-directors..."
                className="bg-[#1a1a1a] border border-[#1e1e1e] rounded px-3 py-1 text-xs text-white focus:outline-none focus:border-[#00d4aa] transition-all w-[180px] focus:w-[240px]"
              />
              <button
                type="button"
                onClick={handleConvene}
                disabled={isConvening || !query.trim()}
                className="flex items-center gap-2 bg-[#1a1a1a] hover:bg-[#222] text-[#888] border border-[#1e1e1e] rounded px-3 py-1 text-xs transition-all disabled:opacity-50"
              >
                <Users size={14} />
              </button>
              {debateHistory.length > 0 && (
                <div className="relative group">
                  <button className="flex items-center justify-center rounded border border-[#1e1e1e] bg-[#1a1a1a] p-1.5 text-[#444] hover:text-white transition-colors">
                    <History size={14} />
                  </button>
                  <div className="absolute right-0 top-full mt-1 hidden group-hover:block w-64 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] shadow-2xl z-[110] overflow-hidden">
                    <div className="px-3 py-2 border-b border-[#1e1e1e] bg-[#080808] text-[10px] font-bold uppercase tracking-widest text-[#444]">
                      Recent Debates
                    </div>
                    <div className="max-h-64 overflow-y-auto">
                      {debateHistory.map((d) => (
                        <button
                          key={d.debate_id}
                          onClick={() => setActiveDebate(d)}
                          className="w-full text-left px-3 py-2 border-b border-[#1e1e1e] hover:bg-[#1a1a1a] transition-colors"
                        >
                          <div className="text-[10px] text-[#888] font-medium truncate">{d.query}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
          <button
            type="button"
            onClick={toggleMuted}
            className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-[#888] border border-[#1e1e1e] bg-[#1a1a1a] hover:border-[#00d4aa] transition-colors"
            title={muted ? 'Enable studio audio hooks' : 'Mute studio audio hooks'}
          >
            {muted ? <VolumeX size={13} /> : <Volume2 size={13} />}
          </button>
          <div className="flex items-center gap-2 rounded-full px-3 py-1.5 text-xs border border-[#1e1e1e] bg-[#1a1a1a]" style={{
            color: studioStatus.color === '#22c55e' ? '#22c55e' : studioStatus.color,
          }}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: studioStatus.color === '#22c55e' ? '#22c55e' : studioStatus.color }}></span>
            <span>{studioStatus.label}</span>
          </div>
          <div className="flex items-center gap-2 rounded-full px-3 py-1.5 text-xs border border-[#1e1e1e] bg-[#1a1a1a] text-[#888]">
            <User size={14} />
            <span>Admin</span>
          </div>
        </div>
      </header>

      {activeDebate && (
        <DirectorDebatePanel
          projectId={activeProjectId || ''}
          debate={activeDebate}
          onDismiss={() => setActiveDebate(null)}
        />
      )}
    </>
  )
}
