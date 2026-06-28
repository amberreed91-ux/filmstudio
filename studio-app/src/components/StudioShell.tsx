import { useEffect, useRef, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import BackendDownStatusBar from './BackendDownStatusBar'
import { Link, matchPath, useLocation, useNavigate } from 'react-router-dom'
import {
  Clapperboard,
  FileEdit,
  Eye,
  Camera,
  MonitorPlay,
  Share2,
  Archive,
  BookOpen,
  Search,
  Settings,
  Bell,
  User,
  Filter,
} from 'lucide-react'
import { lazyLoad } from './LazyLoad'
import { useRenderActivity } from '../context/RenderActivityContext'
import { useAudioUX } from '../context/AudioUXContext'
import { getRouteByPath, getRouteLabel } from '../routes'
import { persistActiveProjectId, readPersistedActiveProjectId, resolveActiveProjectId, withProjectQuery } from '../lib/projectContext'
import { roomDescription } from '../lib/userFacingText'
import { useRenderStatusStore } from '../stores/renderStatusStore'
import CoDirectorDrawer from './CoDirectorDrawer'

const LazyAICrewPresence = lazyLoad(
  () => import('./AICrewPresence'),
  <div className="animate-pulse bg-zinc-800/50 h-24 rounded-lg mb-4" />,
)

// eslint-disable-next-line react-refresh/only-export-components
export const AGENTS = {
  director: {
    name: 'Director',
    icon: '🎬',
    role: 'Creative vision and approval',
  },
  cinematographer: {
    name: 'Cinematographer',
    icon: '🎥',
    role: 'Visual style and framing',
  },
  editor: {
    name: 'Editor',
    icon: '✂️',
    role: 'Pacing and structure',
  },
  story_analyst: {
    name: 'Story Analyst',
    icon: '📖',
    role: 'Narrative and emotional beats',
  },
  continuity: {
    name: 'Continuity Supervisor',
    icon: '🔗',
    role: 'Consistency and logic',
  },
  archivist: {
    name: 'Memory Archivist',
    icon: '🧠',
    role: 'Reference memory and patterns',
  },
} as const

interface StudioShellProps {
  title?: string
  subtitle?: string
  transparent?: boolean
  children: ReactNode
}

type TabOption<T extends string> = { id: T; label: string }

export function TabGroup<T extends string>({
  value,
  options,
  onChange,
  className = '',
}: {
  value: T
  options: TabOption<T>[]
  onChange: (next: T) => void
  className?: string
}) {
  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => onChange(option.id)}
          className={`rounded-md border px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] transition-colors ${
            value === option.id ? 'border-cyan-300/60 bg-cyan-500/14 text-cyan-100' : 'border-zinc-700 bg-zinc-900/60 text-zinc-400'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function CollapsibleSection({
  title,
  children,
  defaultOpen = false,
}: {
  title: string
  children: ReactNode
  defaultOpen?: boolean
}) {
  return (
    <details open={defaultOpen} className="rounded-xl border border-zinc-700/70 bg-zinc-900/60">
      <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-300">
        {title}
      </summary>
      <div className="px-3 pb-3">{children}</div>
    </details>
  )
}

export function DropdownMenu({
  value,
  options,
  onChange,
  label,
  className = '',
}: {
  value: string
  options: Array<{ value: string; label: string }>
  onChange: (next: string) => void
  label?: string
  className?: string
}) {
  return (
    <label className={`flex items-center gap-2 ${className}`}>
      {label ? <span className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">{label}</span> : null}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-md border border-zinc-600 bg-zinc-900/80 px-2 py-1 text-[11px] text-zinc-200 focus:outline-none focus:ring-1 focus:ring-cyan-400/50"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

export function MetricCard({
  label,
  value,
  status,
  accentClass = 'text-zinc-300',
  barClass = 'from-zinc-500 to-zinc-400',
}: {
  label: string
  value: number | string
  status?: string
  accentClass?: string
  barClass?: string
}) {
  const numericValue = typeof value === 'number' ? Math.max(0, Math.min(100, value)) : 0
  return (
    <article className="rounded-2xl border border-white/10 bg-zinc-900/50 p-4 shadow-xl backdrop-blur-sm">
      <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">{label}</div>
      <div className="mt-2 flex items-end justify-between">
        <div className="text-3xl font-semibold text-zinc-100">{value}</div>
        {status ? <div className={`text-xs uppercase tracking-[0.12em] ${accentClass}`}>{status}</div> : null}
      </div>
      <div className="mt-3 h-1.5 rounded bg-zinc-800">
        <div className={`h-1.5 rounded bg-gradient-to-r ${barClass}`} style={{ width: `${numericValue}%` }} />
      </div>
    </article>
  )
}

export function EmptyStateCard({
  title,
  message,
  cta,
}: {
  title: string
  message: string
  cta?: ReactNode
}) {
  return (
    <div className="rounded-lg border border-dashed border-zinc-700 bg-black/25 px-4 py-4 text-sm text-zinc-300">
      <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">{title}</div>
      <div className="mt-1">{message}</div>
      {cta ? <div className="mt-2">{cta}</div> : null}
    </div>
  )
}

/* ─── Room definitions for side nav ─────────────────────────────────────── */
interface RoomNavItem {
  key: string
  label: string
  stitchName: string
  icon: ReactNode
  to: string
}

const ROOM_NAV_ITEMS: RoomNavItem[] = [
  { key: 'gate', label: 'The Gate', stitchName: 'The Gate', icon: <Clapperboard size={20} />, to: '/' },
  { key: 'page', label: 'The Page', stitchName: 'The Page', icon: <FileEdit size={20} />, to: '/studio/writers-room' },
  { key: 'board', label: 'The Board', stitchName: 'The Board', icon: <Eye size={20} />, to: '/studio/production-board' },
  { key: 'previs', label: 'The Previs Bay', stitchName: 'The Previs Bay', icon: <Camera size={20} />, to: '/studio/previs' },
  { key: 'theater', label: 'The Theater', stitchName: 'The Theater', icon: <MonitorPlay size={20} />, to: '/studio/screening-room' },
  { key: 'universe', label: 'The Universe', stitchName: 'The Universe', icon: <Share2 size={20} />, to: '/studio/universe-graph' },
  { key: 'vault', label: 'The Vault', stitchName: 'The Vault', icon: <Archive size={20} />, to: '/studio/archive' },
  { key: 'study', label: 'The Study', stitchName: 'The Study', icon: <BookOpen size={20} />, to: '/studio/study-room' },
]

/* ─── Rooms that use full r3f environments (no CSS background image) ──────── */
const R3F_ROOMS = new Set(['/studio/writers-room', '/studio/screening-room'])

/* ─── Route-to-background map ────────────────────────────────────────────── */
const roomBackgrounds: Record<string, string> = {
  '/': 'url("/backgrounds/the-gate-bg.png")',
  '/studio/production-board': 'url("/backgrounds/the-board-bg.png")',
  '/studio/previs': 'url("/backgrounds/the-previs-bg.png")',
  '/studio/universe-graph': 'url("/backgrounds/the-universe-bg.png")',
  '/studio/archive': 'url("/backgrounds/the-vault-bg.png")',
  '/studio/study-room': 'url("/backgrounds/the-study-bg.png")',
}

/**
 * Resolve the background key from a pathname.
 * Tries exact match first, then falls back to prefix match against studio routes,
 * then falls back to '/' (Gate).
 */
function resolveBackgroundKey(pathname: string): string {
  if (roomBackgrounds[pathname]) return pathname
  // try prefix match against known studio routes
  for (const route of Object.keys(roomBackgrounds)) {
    if (route !== '/' && pathname.startsWith(route)) return route
  }
  // studio sub-paths that don't match a specific room get the Gate background
  if (pathname.startsWith('/studio')) return '/'
  return '/'
}

export default function StudioShell({ title, subtitle, transparent, children }: StudioShellProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const { activity } = useRenderActivity()
  const { emitAudioEvent } = useAudioUX()
  const prevPathRef = useRef(location.pathname)
  const prevRenderStatusRef = useRef(activity?.status || null)
  const { status: renderStatus, setStatus } = useRenderStatusStore()
  const [hoveredRoom, setHoveredRoom] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [codirectorOpen, setCodirectorOpen] = useState(false)

  // Sync render status from RenderActivityContext into zustand store
  useEffect(() => {
    if (!activity) {
      setStatus('idle')
      return
    }
    const s = activity.status
    if (s === 'generating' || s === 'polling' || s === 'preparing' || s === 'queued') {
      setStatus('running', activity.jobId)
    } else if (s === 'completed') {
      setStatus('complete', activity.jobId)
    } else if (s === 'failed') {
      setStatus('failed', activity.jobId)
    }
  }, [activity, setStatus])

  const activeTitle = title || getRouteByPath(location.pathname)?.title || 'Studio'
  const projectMatch = matchPath({ path: '/studio/project/:projectId/*' }, location.pathname)
  const projectId = projectMatch?.params?.projectId
  const activeProjectId = resolveActiveProjectId({
    queryProjectId: new URLSearchParams(location.search).get('project_id'),
    routeProjectId: projectId,
    locationState: location.state,
    persistedProjectId: readPersistedActiveProjectId(),
  })
  useEffect(() => {
    if (activeProjectId) persistActiveProjectId(activeProjectId)
  }, [activeProjectId])

  // ── Parallax effect: all .glass-panel lean on mousemove ──
  useEffect(() => {
    function handleMouseMove(e: MouseEvent) {
      const x = (e.clientX / window.innerWidth - 0.5) * 2   // -1 to 1
      const y = (e.clientY / window.innerHeight - 0.5) * 2   // -1 to 1
      const panels = document.querySelectorAll('.glass-panel')
      for (const panel of panels) {
        const el = panel as HTMLElement
        el.style.transform = `rotateY(${x * 1.5}deg) rotateX(${y * -1.5}deg)`
      }
    }
    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [])

  useEffect(() => {
    if (prevPathRef.current !== location.pathname) {
      if (import.meta.env.DEV) {
        console.log('[RouteDebug] location changed', {
          from: prevPathRef.current,
          to: location.pathname,
        })
      }
      emitAudioEvent('room_transition', { from: prevPathRef.current, to: location.pathname })
      prevPathRef.current = location.pathname
    }
  }, [emitAudioEvent, location.pathname])

  /* Keyboard shortcut: Cmd+D / Ctrl+D toggles co-director drawer */
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'd') {
        e.preventDefault()
        setCodirectorOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  useEffect(() => {
    const prev = prevRenderStatusRef.current
    const next = activity?.status || null
    if (prev === next) return
    if (next === 'generating' || next === 'queued' || next === 'preparing' || next === 'polling') {
      emitAudioEvent('render_started', { status: next })
    } else if (next === 'completed') {
      emitAudioEvent('render_completed', { status: next })
    } else if (next === 'failed') {
      emitAudioEvent('render_failed', { status: next })
    }
    prevRenderStatusRef.current = next
  }, [activity?.status, emitAudioEvent])

  /* ── Render status pill ───────────────────────────────────────────── */
  const statusPill = (() => {
    switch (renderStatus) {
      case 'running':
        return (
          <span className="status-chip" style={{ color: '#4cd7f6', border: '1px solid rgba(76,215,246,0.3)' }}>
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#4cd7f6] mr-1.5 animate-pulse" />
            RENDERING
          </span>
        )
      case 'complete':
        return (
          <span className="status-chip" style={{ color: '#ffd165', border: '1px solid rgba(255,209,101,0.3)' }}>
            ✓ READY
          </span>
        )
      case 'failed':
        return (
          <span className="status-chip" style={{ color: '#ffb4ab', border: '1px solid rgba(255,180,171,0.3)' }}>
            ✗ FAILED
          </span>
        )
      default:
        return (
          <span className="status-chip" style={{ color: '#9b8f79', border: '1px solid rgba(155,143,121,0.3)' }}>
            IDLE
          </span>
        )
    }
  })()

  /* ── Determine if studio route (don't show side nav on landing) ──── */
  const isStudioRoute = location.pathname.startsWith('/studio') || location.pathname === '/'

  /* ── Check if current room uses r3f environment instead of CSS bg ──── */
  const isR3fRoom = R3F_ROOMS.has(location.pathname)

  /* ── Background key for the current route ─────────────────────────── */
  const bgKey = resolveBackgroundKey(location.pathname)
  return (
    <>
      {/* ── Atmospheric Background (lifted up, never unmounts) ─────────── */}
      {/* Background image — crossfades on route change via Framer Motion */}
      {/* Only rendered for non-r3f rooms — The Page and The Theater use their own 3D canvas */}
      {!isR3fRoom && (
        <AnimatePresence mode="wait">
          <motion.div
            key={bgKey}
            className="fixed inset-0 z-[-2] bg-cover bg-center pointer-events-none"
            style={{ backgroundImage: roomBackgrounds[bgKey] ?? 'none' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
          />
        </AnimatePresence>
      )}

      {/* Fog overlay — never changes between rooms */}
      <div className="bg-atmos-fog" />

      {/* Film grain overlay — never changes between rooms */}
      <div className="bg-film-grain" />

      {/* ── Recording bar (full-width, top of interface) ── */}
      {renderStatus === 'running' && (
        <div
          className="recording-bar fixed top-0 left-0 w-full z-[60]"
          style={{ height: '2px', backgroundColor: '#93000a' }}
        />
      )}

      {/* ── Backend offline status bar ── */}
      <BackendDownStatusBar />

      <div className="flex min-h-screen" style={{ background: transparent ? 'transparent' : 'var(--bg-deep)' }}>
        {/* ── SIDE NAV (fixed left, 72px, glass-panel) ── */}
        {isStudioRoute && (
          <nav
            className="glass-panel fixed left-4 top-1/2 -translate-y-1/2 z-50 flex flex-col items-center gap-3 py-6 px-3 rounded-full"
            style={{ width: '72px' }}
          >
            {ROOM_NAV_ITEMS.map((room) => {
              /* Match: exact path or the route starts with the room path structure */
              const isActive =
                location.pathname === room.to ||
                (room.to !== '/' && location.pathname.startsWith(room.to)) ||
                (room.to === '/' && location.pathname === '/') ||
                /* Special case: handle /studio prefix for all studio-internal routes */
                (room.to.startsWith('/studio/') && location.pathname.startsWith(room.to))

              return (
                <div key={room.key} className="relative flex items-center justify-center">
                  <button
                    type="button"
                    onClick={() => navigate(room.to)}
                    onMouseEnter={() => setHoveredRoom(room.key)}
                    onMouseLeave={() => setHoveredRoom(null)}
                    onFocus={() => setHoveredRoom(room.key)}
                    onBlur={() => setHoveredRoom(null)}
                    className={`flex items-center justify-center w-10 h-10 rounded-full transition-all duration-200 ${
                      isActive
                        ? 'bg-[#03b5d3] text-[#003640] scale-110 shadow-[0_0_20px_rgba(76,215,246,0.4)]'
                        : 'text-[#d3c5ac] opacity-60 hover:bg-[#3a3939] hover:opacity-100'
                    }`}
                  >
                    {room.icon}
                  </button>
                  {hoveredRoom === room.key && (
                    <div
                      className="glass-panel absolute left-full ml-3 px-3 py-1.5 rounded-lg whitespace-nowrap pointer-events-none z-50"
                      style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '10px', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase' }}
                    >
                      {room.stitchName}
                    </div>
                  )}
                </div>
              )
            })}
          </nav>
        )}

        {/* ── MAIN CONTENT AREA ── */}
        <div className={`flex-1 flex flex-col ${isStudioRoute ? 'ml-[88px]' : ''}`}>
          {/* ── TOP BAR ── */}
          {isStudioRoute && (
            <header className="flex items-center justify-between px-6 h-14 flex-shrink-0" style={{ background: 'transparent' }}>
              {/* Left: STUDIO logo */}
              <Link to="/studio" className="flex items-center gap-2 no-underline">
                <span
                  className="text-lg font-bold tracking-[0.3em] amber-glow"
                  style={{ fontFamily: 'Geist, sans-serif', color: '#ffd165' }}
                >
                  STUDIO
                </span>
              </Link>

              {/* Right: search, status pill, icons */}
              <div className="flex items-center gap-4">
                {/* Search input (cyber-input style) */}
                <div className="relative">
                  <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2" style={{ color: '#9b8f79' }} />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search archive..."
                    className="cyber-input pl-8 pr-2 py-1.5 text-xs"
                    style={{ width: '180px' }}
                  />
                </div>

                {/* Render status pill */}
                {statusPill}

                {/* Settings icon */}
                <button type="button" className="flex items-center justify-center w-8 h-8 rounded-full transition-colors text-[#d3c5ac] opacity-60 hover:opacity-100 hover:bg-[#3a3939]">
                  <Settings size={16} />
                </button>

                {/* Notifications bell with badge dot */}
                <button type="button" className="relative flex items-center justify-center w-8 h-8 rounded-full transition-colors text-[#d3c5ac] opacity-60 hover:opacity-100 hover:bg-[#3a3939]">
                  <Bell size={16} />
                  {/* Badge dot: pending render jobs */}
                  {activity?.isActive && (
                    <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#93000a]" />
                  )}
                </button>

                {/* Co-Director toggle (movie_filter) */}
                <button
                  type="button"
                  onClick={() => setCodirectorOpen((prev) => !prev)}
                  aria-label="Toggle Co-Director Brain (Cmd+D)"
                  aria-pressed={codirectorOpen}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full font-status-xs transition-all ${
                    codirectorOpen
                      ? 'bg-primary/20 text-primary shadow-[0_0_18px_rgba(255,209,101,0.55)] amber-glow'
                      : 'text-on-surface-variant opacity-70 hover:opacity-100 hover:bg-[#3a3939]'
                  }`}
                >
                  <Filter size={13} />
                  <span>CO-DIRECTOR</span>
                </button>

                {/* Account circle */}
                <button type="button" className="flex items-center justify-center w-8 h-8 rounded-full transition-colors text-[#d3c5ac] opacity-60 hover:opacity-100 hover:bg-[#3a3939]">
                  <User size={16} />
                </button>
              </div>
            </header>
          )}

          {/* ── CHILDREN ── */}
          <main className="flex-1 w-full">
            <div className="relative z-10 min-h-full">
              {children}
            </div>
          </main>
          <LazyAICrewPresence />
        </div>

        <CoDirectorDrawer
          isOpen={codirectorOpen}
          onClose={() => setCodirectorOpen(false)}
          activeProjectId={activeProjectId}
          activeRoomName={activeTitle}
        />
      </div>
    </>
  )
}