import { useEffect, useRef, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import BackendDownStatusBar from './BackendDownStatusBar'
import { Link, matchPath, useLocation, useNavigate } from 'react-router-dom'
import { useBackendHealth } from '../hooks/useBackendHealth'
import {
  Clapperboard,
  FileEdit,
  Eye,
  Camera,
  MonitorPlay,
  Share2,
  Archive,
  BookOpen,
  LayoutDashboard,
  Factory,
  ShieldCheck,
  Images,
  Search,
  Settings,
  Bell,
  User,
  Filter,
  Home,
  LayoutGrid,
  Box,
  Loader2,
} from 'lucide-react'
import { lazyLoad } from './LazyLoad'
import { useRenderActivity } from '../context/RenderActivityContext'
import { useAudioUX } from '../context/AudioUXContext'
import { getRouteByPath } from '../routes'
import { persistActiveProjectId, readPersistedActiveProjectId, resolveActiveProjectId, withProductionContext } from '../lib/projectContext'
import { useRenderStatusStore } from '../stores/renderStatusStore'
import CoDirectorDrawer from './CoDirectorDrawer'
import ProductionJourneyGuide from './ProductionJourneyGuide'
import { useStudio } from '../context/StudioContext'

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
  beforeNavigate?: () => Promise<boolean>
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
            value === option.id ? 'border-amber-300/50 bg-amber-300/10 text-amber-100' : 'border-zinc-700 bg-zinc-900/60 text-zinc-400'
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

/* ─── Persistent lobby navigation — always visible across all studio pages ─
 * Studio Workspace -> /studio · 2D Lobby -> /studio/lobby · 3D Lobby -> /studio/lobby-3d
 * Rendered as a dedicated cluster above the room rail so users never type URLs. */
const LOBBY_NAV_ITEMS: RoomNavItem[] = [
  { key: 'studio-workspace', label: 'Studio Workspace', stitchName: 'Studio Workspace', icon: <Home size={20} />, to: '/studio' },
  { key: 'lobby-2d', label: '2D Lobby', stitchName: '2D Lobby', icon: <LayoutGrid size={20} />, to: '/studio/lobby' },
  { key: 'lobby-3d', label: '3D Lobby', stitchName: '3D Lobby', icon: <Box size={20} />, to: '/studio/lobby-3d' },
]

const ROOM_NAV_ITEMS: RoomNavItem[] = [
  { key: 'gate', label: 'The Gate', stitchName: 'The Gate', icon: <Clapperboard size={20} />, to: '/' },
  { key: 'overview', label: 'Overview', stitchName: 'Overview', icon: <LayoutDashboard size={20} />, to: '/studio/overview' },
  { key: 'page', label: 'The Page', stitchName: 'The Page', icon: <FileEdit size={20} />, to: '/studio/writers-room' },
  { key: 'board', label: 'The Board', stitchName: 'The Board', icon: <Eye size={20} />, to: '/studio/production-board' },
  { key: 'production-desk', label: 'Production Desk', stitchName: 'Production Desk', icon: <Factory size={20} />, to: '/studio/production-desk' },
  { key: 'integrity', label: 'Integrity Engine', stitchName: 'Integrity Engine', icon: <ShieldCheck size={20} />, to: '/studio/integrity' },
  { key: 'reference-space', label: 'Reference Space', stitchName: 'Reference Space', icon: <Images size={20} />, to: '/studio/reference-space' },
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
  '/studio/overview': 'url("/backgrounds/the-gate-bg.png")',
  '/studio/production-board': 'url("/backgrounds/the-board-bg.png")',
  '/studio/production-desk': 'url("/backgrounds/the-board-bg.png")',
  '/studio/integrity': 'url("/backgrounds/the-board-bg.png")',
  '/studio/reference-space': 'url("/backgrounds/the-vault-bg.png")',
  '/studio/previs': 'url("/backgrounds/the-previs-bg.png")',
  '/studio/universe-graph': 'url("/backgrounds/the-universe-bg.png")',
  '/studio/archive': 'url("/backgrounds/the-vault-bg.png")',
  '/studio/vault': 'url("/backgrounds/the-vault-bg.png")',
  '/studio/study-room': 'url("/backgrounds/the-study-bg.png")',
  '/studio': 'url("/backgrounds/the-gate-bg.png")',
  '/studio/lobby': 'url("/backgrounds/the-gate-bg.png")',
  '/studio/lobby-3d': 'url("/backgrounds/the-gate-bg.png")',
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

export default function StudioShell({ title, transparent, children, beforeNavigate }: StudioShellProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const { activity } = useRenderActivity()
  const { emitAudioEvent } = useAudioUX()
  const prevPathRef = useRef(location.pathname)
  const prevRenderStatusRef = useRef(activity?.status || null)
  const { status: renderStatus, setStatus } = useRenderStatusStore()
  const [hoveredRoom, setHoveredRoom] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [mobileToolsExpanded, setMobileToolsExpanded] = useState(false)
  const [codirectorOpen, setCodirectorOpen] = useState(false)
  const { healthy, restarting, restart } = useBackendHealth()

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

  const { activeProjectId: contextProjectId } = useStudio()
  const routeSearch = new URLSearchParams(location.search)
  const activeTitle = title || getRouteByPath(location.pathname)?.title || 'Studio'
  const projectMatch = matchPath({ path: '/studio/project/:projectId/*' }, location.pathname)
  const projectId = projectMatch?.params?.projectId
  const activeProjectId = resolveActiveProjectId({
    queryProjectId: new URLSearchParams(location.search).get('project_id'),
    routeProjectId: projectId,
    locationState: location.state,
    contextProjectId,
    persistedProjectId: contextProjectId ? null : readPersistedActiveProjectId(),
  })
  const productionContext = { projectId: activeProjectId, sceneId: routeSearch.get('scene') || routeSearch.get('scene_id'), shotNumber: Number.parseInt(routeSearch.get('shot') || '', 10) || null }
  const roomUrl = (path: string) => withProductionContext(path, productionContext)
  const [navigatingTo, setNavigatingTo] = useState<string | null>(null)
  const navigateToRoom = async (path: string) => {
    if (navigatingTo) return
    setNavigatingTo(path)
    try {
      if (beforeNavigate && !(await beforeNavigate())) return
      navigate(roomUrl(path))
    } finally {
      setNavigatingTo(null)
    }
  }
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
            aria-label="Studio rooms"
            className="liquid-panel fixed left-3 top-1/2 z-50 flex flex-col items-center gap-2 py-4 px-2 md:left-4 md:gap-3 md:py-6 md:px-3"
            style={{ width: '60px', transform: 'translateY(-50%)' }}
          >
            <span aria-hidden="true" className="liquid-edge" />
            <span aria-hidden="true" className="liquid-spec" />
            <span aria-hidden="true" className="liquid-glow" />
            <div className="relative z-10 flex flex-col items-center gap-2 md:gap-3">
            {/* ── Persistent lobby navigation (Studio / 2D Lobby / 3D Lobby) ── */}
            <div aria-label="Lobby navigation" className="flex flex-col items-center gap-2 md:gap-3">
            {LOBBY_NAV_ITEMS.map((room) => {
              const isActive = location.pathname === room.to
              return (
                <div key={room.key} className="relative flex items-center justify-center">
                  <button
                    type="button"
                    onClick={() => void navigateToRoom(room.to)}
                    disabled={navigatingTo !== null}
                    aria-busy={navigatingTo === room.to}
                    aria-label={room.stitchName}
                    aria-current={isActive ? 'page' : undefined}
                    data-testid={`lobby-nav-${room.key}`}
                    onMouseEnter={() => setHoveredRoom(room.key)}
                    onMouseLeave={() => setHoveredRoom(null)}
                    onFocus={() => setHoveredRoom(room.key)}
                    onBlur={() => setHoveredRoom(null)}
                    className={`flex items-center justify-center w-9 h-9 md:w-10 md:h-10 rounded-full transition-all duration-200 ${
                      isActive
                        ? 'bg-[#ffd165] text-[#3a2c00] scale-110 shadow-[0_0_22px_rgba(255,209,101,0.6)] ring-1 ring-inset ring-white/40'
                        : 'text-amber-100/85 hover:text-amber-100 hover:bg-white/10 hover:ring-1 hover:ring-inset hover:ring-amber-200/30'
                    }`}
                  >
                    {navigatingTo === room.to ? <Loader2 size={16} className="animate-spin" /> : room.icon}
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
            </div>
            <div aria-hidden="true" className="h-px w-8 bg-white/10" />
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
                    onClick={() => void navigateToRoom(room.to)}
                    disabled={navigatingTo !== null}
                    aria-busy={navigatingTo === room.to}
                    aria-label={room.stitchName}
                    aria-current={isActive ? 'page' : undefined}
                    onMouseEnter={() => setHoveredRoom(room.key)}
                    onMouseLeave={() => setHoveredRoom(null)}
                    onFocus={() => setHoveredRoom(room.key)}
                    onBlur={() => setHoveredRoom(null)}
                    className={`flex items-center justify-center w-9 h-9 md:w-10 md:h-10 rounded-full transition-all duration-200 ${
                      isActive
                        ? 'bg-[#ffd165] text-[#3a2c00] scale-110 shadow-[0_0_22px_rgba(255,209,101,0.6)] ring-1 ring-inset ring-white/40'
                        : 'text-amber-100/85 hover:text-amber-100 hover:bg-white/10 hover:ring-1 hover:ring-inset hover:ring-amber-200/30'
                    }`}
                  >
                    {navigatingTo === room.to ? <Loader2 size={16} className="animate-spin" /> : room.icon}
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
            </div>
          </nav>
        )}

        {/* ── MAIN CONTENT AREA ── */}
        <div className={`min-w-0 flex-1 flex flex-col ${isStudioRoute ? 'pl-[76px] md:pl-[88px]' : ''}`}>
          {/* ── TOP BAR ── */}
          {isStudioRoute && (
            <header className="flex min-w-0 flex-wrap items-center justify-between gap-3 px-4 py-3 flex-shrink-0 lg:h-14 lg:flex-nowrap lg:px-6 lg:py-0" style={{ background: 'transparent' }}>
              {/* Left: STUDIO logo */}
              <Link to="/studio" className="flex items-center gap-2 no-underline">
                <span
                  className="text-lg font-bold tracking-[0.3em] amber-glow"
                  style={{ fontFamily: 'Geist, sans-serif', color: '#ffd165' }}
                >
                  STUDIO
                </span>
              </Link>

              {/* Co-Director toggle (movie_filter) */}
              <button
                type="button"
                onClick={() => setCodirectorOpen((prev) => !prev)}
                aria-label="Toggle Co-Director Brain (Cmd+D)"
                aria-pressed={codirectorOpen}
                className={`lg:order-3 inline-flex items-center gap-1.5 min-h-11 rounded-lg px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] transition-all ${
                  codirectorOpen
                    ? 'bg-gradient-to-br from-[rgba(255,209,101,0.32)] to-[rgba(255,209,101,0.14)] text-[#f7f4ef] border border-[rgba(255,209,101,0.45)] shadow-[0_0_18px_rgba(255,209,101,0.55),inset_0_1px_0_rgba(255,255,255,0.18)]'
                    : 'text-zinc-200 border border-white/10 bg-white/[0.04] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] hover:border-[rgba(255,209,101,0.3)] hover:bg-white/[0.07]'
                }`}
              >
                <Filter size={13} />
                <span>Co-director</span>
              </button>

              <button type="button" onClick={() => setMobileToolsExpanded((expanded) => !expanded)} aria-expanded={mobileToolsExpanded} aria-controls="studio-header-tools" className="rounded border border-white/15 px-3 py-2 text-xs text-zinc-300 lg:hidden">Studio tools</button>

              {/* Right: search, status pill, icons */}
              <div id="studio-header-tools" className={`${mobileToolsExpanded ? 'flex' : 'hidden'} min-w-0 w-full flex-wrap items-center gap-3 lg:ml-auto lg:flex lg:w-auto lg:flex-nowrap lg:gap-4`}>
                {/* Search input (cyber-input style) */}
                <div className="relative">
                  <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2" style={{ color: '#9b8f79' }} />
                  <input
                    type="text"
                    aria-label="Search archive"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search archive..."
                    className="cyber-input pl-8 pr-2 py-1.5 text-xs"
                    style={{ width: '180px' }}
                  />
                </div>

                {/* Render status pill */}
                {statusPill}

                {/* Backend health pill + restart button */}
                {restarting ? (
                  <span
                    className="status-chip flex items-center gap-1.5"
                    style={{ color: '#ffd165', border: '1px solid rgba(255,209,101,0.3)' }}
                  >
                    <span className="inline-block w-3 h-3 animate-spin rounded-full border-2 border-[#ffd165] border-t-transparent" />
                    RESTARTING…
                  </span>
                ) : healthy ? (
                  <span
                    className="status-chip"
                    style={{ color: '#4ade80', border: '1px solid rgba(74,222,128,0.3)' }}
                  >
                    <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#4ade80] mr-1.5" />
                    LIVE
                  </span>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <span
                      className="status-chip"
                      style={{ color: '#fff', background: 'rgba(220,38,38,0.85)', border: '1px solid rgba(220,38,38,0.5)' }}
                    >
                      OFFLINE
                    </span>
                    <button
                      type="button"
                      onClick={restart}
                      className="status-chip cursor-pointer transition-colors"
                      style={{
                        color: '#fff',
                        background: 'rgba(220,38,38,0.7)',
                        border: '1px solid rgba(220,38,38,0.5)',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = 'rgba(220,38,38,0.95)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'rgba(220,38,38,0.7)'
                      }}
                    >
                      RESTART
                    </button>
                  </div>
                )}

                {/* Settings icon */}
                <button type="button" aria-label="Settings" className="flex items-center justify-center w-8 h-8 rounded-full transition-colors text-[#d3c5ac] opacity-60 hover:opacity-100 hover:bg-[#3a3939]">
                  <Settings size={16} />
                </button>

                {/* Notifications bell with badge dot */}
                <button type="button" aria-label="Notifications" className="relative flex items-center justify-center w-8 h-8 rounded-full transition-colors text-[#d3c5ac] opacity-60 hover:opacity-100 hover:bg-[#3a3939]">
                  <Bell size={16} />
                  {/* Badge dot: pending render jobs */}
                  {activity?.isActive && (
                    <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#93000a]" />
                  )}
                </button>

                {/* Account circle */}
                <button type="button" aria-label="Account" className="flex items-center justify-center w-8 h-8 rounded-full transition-colors text-[#d3c5ac] opacity-60 hover:opacity-100 hover:bg-[#3a3939]">
                  <User size={16} />
                </button>
              </div>
            </header>
          )}

          {isStudioRoute && <nav aria-label="Studio rooms on mobile" className="border-y border-white/10 px-4 py-2 md:hidden"><details><summary className="cursor-pointer text-xs text-zinc-300">Rooms <span className="ml-2 text-zinc-500">{activeTitle}</span></summary><div className="grid grid-cols-2 gap-2 pb-2 pt-3">{[...LOBBY_NAV_ITEMS, ...ROOM_NAV_ITEMS].map((room) => <button type="button" key={room.key} onClick={() => void navigateToRoom(room.to)} disabled={navigatingTo !== null} aria-busy={navigatingTo === room.to} aria-label={room.stitchName} className="flex items-center gap-2 rounded border border-white/10 px-3 py-2 text-left text-xs text-zinc-300 hover:bg-white/5 disabled:opacity-50">{navigatingTo === room.to ? <Loader2 size={16} className="animate-spin" /> : room.icon}<span>{room.stitchName}</span></button>)}</div></details></nav>}

          <ProductionJourneyGuide pathname={location.pathname} context={productionContext} beforeNavigate={beforeNavigate} />

          {/* ── CHILDREN ── */}
          <main className="min-w-0 flex-1 w-full">
            <div className="relative z-10 min-h-full">
              {children}
            </div>
          </main>
          <LazyAICrewPresence compact={isStudioRoute} projectId={activeProjectId} />
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
