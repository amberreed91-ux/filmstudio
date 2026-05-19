import { useEffect, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { Film, User, ChevronDown, Volume2, VolumeX } from 'lucide-react'
import { useStudio } from '../context/StudioContext'
import { useAudioUX } from '../context/AudioUXContext'
import { PRIMARY_NAV_ROUTES } from '../routes'
import { isStudioDevMode } from '../lib/devMode'
import { persistActiveProjectId, readPersistedActiveProjectId, resolveActiveProjectId, withProjectQuery } from '../lib/projectContext'

interface TopNavProps {
  title?: string
  subtitle?: string
  showProjectPicker?: boolean
}

export default function TopNav({ title, subtitle, showProjectPicker }: TopNavProps) {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8010'
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

  return (
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
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{subtitle}</span>
        )}
        <span className="text-[10px] uppercase tracking-[0.12em]" style={{ color: 'var(--text-muted)' }}>
          status: {activeProject?.updated_at ? 'active' : 'idle'} • scenes: {activeProject?.source_stats?.scene_count || 0} • renders: {activeProject?.source_stats?.render_count || 0}
        </span>
      </div>

      <nav className="flex items-center gap-1">
        {PRIMARY_NAV_ROUTES.map((route) => {
          const active = isRouteActive(route.path)
          return (
            <Link
              key={route.path}
              to={withProjectQuery(route.path, activeProjectId)}
              className="studio-nav-link px-4 py-1.5 text-sm rounded transition-all no-underline"
              style={{
                color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                borderBottom: active ? '2px solid var(--accent-cyan)' : '2px solid transparent',
                fontWeight: active ? 500 : 400,
              }}
            >
              {route.label}
            </Link>
          )
        })}
        {activeProject?.project_id && (
          <Link
            to={withProjectQuery(`/studio/project/${activeProject.project_id}`, activeProjectId)}
            className="studio-nav-link px-4 py-1.5 text-sm rounded transition-all no-underline"
            style={{
              color: location.pathname.startsWith('/studio/project/') ? 'var(--accent-cyan)' : 'var(--text-secondary)',
              borderBottom: location.pathname.startsWith('/studio/project/') ? '2px solid var(--accent-cyan)' : '2px solid transparent',
              fontWeight: location.pathname.startsWith('/studio/project/') ? 500 : 400,
            }}
          >
            Workspace
          </Link>
        )}
        {devModeEnabled && (
          <Link
            to={withProjectQuery('/studio/devtools', activeProjectId)}
            className="studio-nav-link px-4 py-1.5 text-sm rounded transition-all no-underline"
            style={{
              color: location.pathname === '/studio/devtools' ? 'var(--accent-cyan)' : 'var(--text-secondary)',
              borderBottom: location.pathname === '/studio/devtools' ? '2px solid var(--accent-cyan)' : '2px solid transparent',
              fontWeight: location.pathname === '/studio/devtools' ? 500 : 400,
            }}
          >
            Dev Tools
          </Link>
        )}
      </nav>

      <div className="flex items-center gap-3">
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
  )
}
