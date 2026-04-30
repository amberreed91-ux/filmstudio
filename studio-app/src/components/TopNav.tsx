import { Link, useLocation } from 'react-router-dom'
import { Film, User, ChevronDown } from 'lucide-react'
import { useStudio } from '../context/StudioContext'
import { PRIMARY_NAV_ROUTES } from '../routes'

interface TopNavProps {
  title?: string
  subtitle?: string
  showProjectPicker?: boolean
}

export default function TopNav({ title, subtitle, showProjectPicker }: TopNavProps) {
  const location = useLocation()
  const { loading, error, project, overview, isDemoMode } = useStudio()
  const activeProject = project || overview?.latest_project || null
  const studioStatus = error
    ? { label: 'Backend unavailable', color: '#ef4444', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)' }
    : loading
      ? { label: 'Syncing studio...', color: 'var(--accent-cyan)', background: 'rgba(0,200,255,0.1)', border: '1px solid rgba(0,200,255,0.2)' }
      : isDemoMode
        ? { label: 'Demo Mode', color: '#f59e0b', background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)' }
        : { label: 'Studio connected', color: '#22c55e', background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.2)' }

  return (
    <header style={{ background: 'var(--bg-panel)', borderBottom: '1px solid var(--border)' }}
      className="flex items-center justify-between px-6 h-14 flex-shrink-0">
      <div className="flex items-center gap-4">
        <Link to="/studio" className="flex items-center gap-2 text-white no-underline">
          <Film size={18} style={{ color: 'var(--accent-cyan)' }} />
          {showProjectPicker ? (
            <span className="flex items-center gap-1 text-sm font-medium text-white p-0">
              <Film size={14} className="mr-1" style={{ color: 'var(--accent-cyan)' }} />
              Project: Neon Dreams v2.4
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
        <span className="rounded border border-amber-300/45 bg-amber-500/12 px-2 py-0.5 text-[10px] font-semibold tracking-[0.08em] text-amber-100">
          LIVE UI MARKER 2026-04-29 17:54
        </span>
      </div>

      <nav className="flex items-center gap-1">
        {PRIMARY_NAV_ROUTES.map((route) => {
          const active = location.pathname === route.path
          return (
            <Link
              key={route.path}
              to={route.path}
              className="px-4 py-1.5 text-sm rounded transition-all no-underline"
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
            to={`/studio/project/${activeProject.project_id}`}
            className="px-4 py-1.5 text-sm rounded transition-all no-underline"
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
        <div className="flex items-center gap-2 px-3 py-1.5 rounded text-xs" style={{
          background: studioStatus.background,
          border: studioStatus.border,
          color: studioStatus.color,
        }}>
          <span className="status-dot inline-block" style={{ background: studioStatus.color }}></span>
          <span>{studioStatus.label}</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded" style={{ background: 'rgba(255,255,255,0.05)' }}>
          <User size={14} style={{ color: 'var(--text-secondary)' }} />
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>Admin | FilmOS</span>
        </div>
      </div>
    </header>
  )
}
