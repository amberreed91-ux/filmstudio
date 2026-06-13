import { useEffect, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { Film, User, ChevronDown, Volume2, VolumeX, Users, History } from 'lucide-react'
import { useStudio } from '../context/StudioContext'
import { useAudioUX } from '../context/AudioUXContext'
import { PRIMARY_NAV_ROUTES } from '../routes'
import { isStudioDevMode } from '../lib/devMode'
import { persistActiveProjectId, readPersistedActiveProjectId, resolveActiveProjectId, withProjectQuery } from '../lib/projectContext'
import { STUDIO_API_BASE, triggerDebate, listDebates } from '../lib/studioApi'
import type { CoDirectorDebateEntry } from '../types/directorMemory'
import DirectorDebatePanel from './DirectorDebatePanel'
import { DropdownMenu } from './StudioShell'

interface TopNavProps {
  title?: string
  subtitle?: string
  showProjectPicker?: boolean
}

export default function TopNav({ title, subtitle, showProjectPicker }: TopNavProps) {
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
  const devModeEnabled = isStudioDevMode()

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
      <header style={{ background: 'var(--bg-panel)', borderBottom: '1px solid var(--border)' }}
        className="flex items-center justify-between px-6 h-14 flex-shrink-0">
        <div className="flex items-center gap-4">
          <Link to="/studio" className="flex items-center gap-2 text-white no-underline">
            <Film size={18} style={{ color: 'var(--accent-cyan)' }} />
            {showProjectPicker ? (
              <span className="flex items-center gap-1 text-sm font-medium text-white p-0">
                <Film size={14} className="mr-1" style={{ color: 'var(--accent-cyan)' }} />
                Project: {activeProject?.title || 'No active project'}
                <ChevronDown size={14} style={{ color: 'var(--text-secondary)' }} />
              </span>
            ) : (
              <span className="text-sm font-semibold tracking-widest uppercase" style={{ color: 'var(--accent-cyan)', letterSpacing: '0.12em' }}>
                {title || 'FilmOS Studio'}
              </span>
            )}
          </Link>
          {subtitle && (
            <span className="text-xs sr-only" style={{ color: 'var(--text-muted)' }}>{subtitle}</span>
          )}
        </div>

        <nav className="flex items-center gap-1">
          {PRIMARY_NAV_ROUTES.map((route) => {
            const active = isRouteActive(route.path)
            const getRoomIconClass = (path: string) => {
              if (path.includes('lobby') || path === '/studio') return 'room-icon-home'
              if (path.includes('writers-room')) return 'room-icon-writers'
              if (path.includes('previs')) return 'room-icon-previs'
              if (path.includes('approval-room') || path === '/studio/dashboard' || path === '/studio/approval') return 'room-icon-approval'
              if (path.includes('study-room') || path === '/studio/study') return 'room-icon-study'
              if (path.includes('scheduler') || path.includes('crew')) return 'room-icon-crew'
              if (path.includes('cost')) return 'room-icon-cost'
              if (path.includes('workspace') || path.includes('project')) return 'room-icon-workspace'
              if (path.includes('production-board') || path.includes('scenes')) return 'room-icon-previs'
              if (path.includes('screening-room') || path.includes('watch')) return 'room-icon-approval'
              if (path.includes('archive')) return 'room-icon-study'
              return ''
            }
            const roomIconClass = getRoomIconClass(route.path)
            return (
              <Link
                key={route.path}
                to={withProjectQuery(route.path, activeProjectId)}
                className={`studio-nav-link px-4 py-1.5 text-sm rounded transition-all no-underline ${roomIconClass}`}
                style={{
                  color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                  borderBottom: active ? '2px solid var(--accent-cyan)' : '2px solid transparent',
                  fontWeight: active ? 500 : 400,
                }}
              >
                {route.icon && <span className="mr-1.5">{route.icon}</span>}
                {route.label}
              </Link>
            )
          })}
          {activeProject?.project_id && (
            <Link
              to={withProjectQuery(`/studio/project/${activeProject.project_id}`, activeProjectId)}
              className="studio-nav-link room-icon-workspace px-4 py-1.5 text-sm rounded transition-all no-underline"
              style={{
                color: location.pathname.startsWith('/studio/project/') ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                borderBottom: location.pathname.startsWith('/studio/project/') ? '2px solid var(--accent-cyan)' : '2px solid transparent',
                fontWeight: location.pathname.startsWith('/studio/project/') ? 500 : 400,
              }}
            >
              Workspace
            </Link>
          )}
        </nav>

        <div className="flex items-center gap-3">
          {activeProjectId && (
            <div className="flex items-center gap-2 mr-4">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleConvene()}
                placeholder="Ask co-directors..."
                className="bg-black/40 border border-white/10 rounded px-3 py-1 text-xs text-white focus:outline-none focus:border-indigo-500/50 w-48"
              />
              <button
                type="button"
                onClick={handleConvene}
                disabled={isConvening || !query.trim()}
                className="flex items-center gap-2 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 border border-indigo-500/30 rounded px-3 py-1 text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-50"
              >
                <Users size={14} />
                <span>Convene</span>
              </button>
              {debateHistory.length > 0 && (
                <div className="relative group">
                  <button className="flex items-center justify-center rounded border border-white/10 bg-black/40 p-1.5 text-zinc-400 hover:text-white transition-colors">
                    <History size={14} />
                  </button>
                  <div className="absolute right-0 top-full mt-1 hidden group-hover:block w-64 rounded-lg border border-white/10 bg-zinc-900 shadow-2xl z-[110] overflow-hidden">
                    <div className="px-3 py-2 border-b border-white/5 bg-zinc-950/50 text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                      Recent Debates
                    </div>
                    <div className="max-h-64 overflow-y-auto">
                      {debateHistory.map((d) => (
                        <button
                          key={d.debate_id}
                          onClick={() => setActiveDebate(d)}
                          className="w-full text-left px-3 py-2 border-b border-white/5 hover:bg-white/5 transition-colors"
                        >
                          <div className="text-[10px] text-zinc-300 font-medium truncate">{d.query}</div>
                          <div className="text-[8px] text-zinc-500 mt-0.5">{new Date(d.created_at).toLocaleDateString()}</div>
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
            className="studio-icon-chip flex items-center gap-1.5 rounded px-2 py-1.5 text-xs text-zinc-200"
            title={muted ? 'Enable studio audio hooks' : 'Mute studio audio hooks'}
          >
            {muted ? <VolumeX size={13} /> : <Volume2 size={13} />}
            <span>{muted ? 'Audio Off' : 'Audio On'}</span>
          </button>
          <div className="studio-icon-chip flex items-center gap-2 px-3 py-1.5 rounded text-xs" style={{
            background: studioStatus.background,
            border: studioStatus.border,
            color: studioStatus.color,
          }}>
            <span className="status-dot inline-block" style={{ background: studioStatus.color }}></span>
            <span>{studioStatus.label}</span>
          </div>
          <div className="studio-icon-chip flex items-center gap-2 px-3 py-1.5 rounded" style={{ background: 'rgba(255,255,255,0.05)' }}>
            <User size={14} style={{ color: 'var(--text-secondary)' }} />
            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>Admin | FilmOS</span>
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
