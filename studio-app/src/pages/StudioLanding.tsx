import { useEffect, useRef, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeftRight,
  Plus,
  Clapperboard,
  Edit,
  Camera,
  Film,
  Music2,
} from 'lucide-react'
import { useStudio } from '../context/StudioContext'
import { useRenderActivity } from '../context/RenderActivityContext'
import { createProject, getProductionQueueSummary, type ProductionQueueSummary } from '../lib/studioApi'
import { STUDIO_API_BASE } from '../lib/studioApi'
import { getQueueStatusCounts } from '../lib/studioSelectors'

/* ─── Agent definitions ─────────────────────────────────────────────── */
interface AgentInfo {
  key: string
  name: string
  icon: React.ReactNode
  role: string
}

const AGENTS: AgentInfo[] = [
  { key: 'director', name: 'Director', icon: <Clapperboard size={16} />, role: 'Creative vision and approval' },
  { key: 'writer', name: 'Writer', icon: <Edit size={16} />, role: 'Narrative and scene structure' },
  { key: 'cinematographer', name: 'Cinematographer', icon: <Camera size={16} />, role: 'Visual style and framing' },
  { key: 'editor', name: 'Editor', icon: <Film size={16} />, role: 'Pacing and structure' },
  { key: 'composer', name: 'Composer', icon: <Music2 size={16} />, role: 'Score and audio landscape' },
]

function computeAgentActivity(): Record<string, boolean> {
  const hasScript = !!localStorage.getItem('studio:lastScript')
  const hasBundleScenes = (() => {
    try {
      const raw = localStorage.getItem('studio:lastBundle')
      if (!raw) return false
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed?.scenes) && parsed.scenes.length > 0
    } catch {
      return false
    }
  })()
  const hasPrevis = hasBundleScenes
  const hasFilm = !!localStorage.getItem('studio_approved_scenes')
  const hasAudio = !!localStorage.getItem('studio:audioGenerated')
  return {
    director: true,
    writer: hasScript,
    cinematographer: hasPrevis,
    editor: hasFilm,
    composer: hasAudio,
  }
}

/* ─── Format helpers ─────────────────────────────────────────────────── */
function formatTimeAgo(dateStr?: string): string {
  if (!dateStr) return '—'
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diff = now - then
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

/* ─── New Project Modal ──────────────────────────────────────────────── */
function NewProjectModal({ onClose }: { onClose: () => void }) {
  const [title, setTitle] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const { setActiveProject } = useStudio()

  async function handleCreate() {
    if (!title.trim()) {
      setError('Film title is required')
      return
    }
    setCreating(true)
    setError('')
    try {
      const result = await createProject({ title: title.trim() })
      if (result.error) {
        setError(result.error)
      } else if (result.project) {
        await setActiveProject(result.project.project_id)
        navigate(`/studio/writers-room?project_id=${result.project.project_id}`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create project')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl p-8" style={{
        background: 'rgba(32, 31, 31, 0.45)',
        backdropFilter: 'blur(30px)',
        WebkitBackdropFilter: 'blur(30px)',
        borderTop: '1px solid rgba(255,255,255,0.15)',
        borderLeft: '1px solid rgba(255,255,255,0.10)',
        borderRight: '1px solid rgba(0,0,0,0.3)',
        borderBottom: '1px solid rgba(0,0,0,0.4)',
        boxShadow: '0 40px 80px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.05)',
      }}>
        <h2 className="text-xl font-bold mb-1" style={{ fontFamily: 'Geist, sans-serif', color: '#e5e2e1' }}>
          New Film
        </h2>
        <p className="text-sm mb-6" style={{ color: '#d3c5ac' }}>
          Give your film a working title to begin.
        </p>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Film title"
          className="cyber-input w-full mb-2 text-sm py-2"
          onKeyDown={(e) => e.key === 'Enter' && !creating && title.trim() && handleCreate()}
          autoFocus
        />
        {error && <p className="text-xs mb-2" style={{ color: '#ffb4ab' }}>{error}</p>}
        <div className="flex gap-3 mt-4">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-lg py-2 text-sm font-bold uppercase tracking-[0.12em] transition-colors"
            style={{ background: 'rgba(255,255,255,0.05)', color: '#d3c5ac', border: '1px solid rgba(155,143,121,0.3)' }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleCreate}
            disabled={creating || !title.trim()}
            aria-busy={creating}
            className="flex-1 rounded-lg py-2 text-sm font-bold uppercase tracking-[0.12em] transition-all disabled:opacity-50"
            style={{
              background: 'linear-gradient(135deg, rgba(255,209,101,0.25), rgba(255,209,101,0.1))',
              color: '#ffd165',
              border: '1px solid rgba(255,209,101,0.4)',
              boxShadow: '0 0 20px rgba(255,209,101,0.15)',
            }}
          >
            {creating ? 'Creating...' : 'Create Film'}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ─── Type for backend health ────────────────────────────────────────── */
interface BackendHealth {
  status: string
  uptime?: string
  db?: string
  projects_count?: number
}

/* ═══════════════════════════════════════════════════════════════════════
   MAIN GATE PAGE
   ═══════════════════════════════════════════════════════════════════════ */
export default function StudioLanding() {
  const navigate = useNavigate()
  const { project, overview, activeProjectId, setActiveProject } = useStudio()
  const { activity } = useRenderActivity()
  const [showNewProject, setShowNewProject] = useState(false)
  const [continuing, setContinuing] = useState(false)
  const continueInFlightRef = useRef(false)
  const [health, setHealth] = useState<BackendHealth | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [queueSummary, setQueueSummary] = useState<ProductionQueueSummary | null>(null)

  const agentStatus = computeAgentActivity()

  /* ── Backend health poll ──────────────────────────────────────────── */
  useEffect(() => {
    let cancelled = false
    async function check() {
      try {
        const res = await fetch(`${STUDIO_API_BASE}/health`, { headers: { Accept: 'application/json' } })
        if (!cancelled && res.ok) {
          const data = await res.json()
          setHealth(data)
        }
      } catch {
        if (!cancelled) setHealth(null)
      } finally {
        if (!cancelled) setHealthLoading(false)
      }
    }
    check()
    const timer = setInterval(check, 15_000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    if (!activeProjectId) {
      setQueueSummary(null)
      return
    }
    let cancelled = false
    getProductionQueueSummary(activeProjectId)
      .then((summary) => {
        if (!cancelled) setQueueSummary(summary)
      })
      .catch(() => {
        if (!cancelled) setQueueSummary(null)
      })
    return () => { cancelled = true }
  }, [activeProjectId])

  /* ── Derive project metadata ──────────────────────────────────────── */
  const scenesCount = project?.source_stats?.scene_count ?? overview?.projects?.[0]?.scene_count ?? 0
  const runtime = project?.source_stats?.target_runtime_minutes ?? null
  const lastModified = project?.updated_at ?? overview?.projects?.[0]?.updated_at ?? null
  const latestProjectTitle = project?.title ?? overview?.projects?.[0]?.title ?? null

  /* ── Queue count ──────────────────────────────────────────────────── */
  const queueCounts = getQueueStatusCounts(queueSummary)
  const queueCount = queueSummary
    ? queueCounts.active + queueCounts.waiting + queueCounts.blocked + queueCounts.failed
    : project?.render_queue?.length ?? 0

  /* ── Glass panel style (FIX 2) ───────────────────────────────────── */
  const glassStyle: React.CSSProperties = {
    background: 'rgba(32, 31, 31, 0.45)',
    backdropFilter: 'blur(30px)',
    WebkitBackdropFilter: 'blur(30px)',
    borderTop: '1px solid rgba(255,255,255,0.15)',
    borderLeft: '1px solid rgba(255,255,255,0.10)',
    borderRight: '1px solid rgba(0,0,0,0.3)',
    borderBottom: '1px solid rgba(0,0,0,0.4)',
    boxShadow: '0 40px 80px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.05)',
  }

  return (
    <>
      {/* ── New Project Modal ── */}
      {showNewProject && <NewProjectModal onClose={() => setShowNewProject(false)} />}

      {/* FIX 1: Atmospheric two-layer background */}
      <div style={{
        position: 'fixed',
        inset: 0,
        zIndex: -2,
        backgroundImage: "url('https://lh3.googleusercontent.com/aida-public/AB6AXuBt3bUhPez0cyCEBuC0mf0c0kaHpS5sv1G4Q6saiUoOm_5XjQrSrCOg8DpQbrFBNashyIKN9tSzlS2-C5A-PHLeb72f5BHUKsQZu5s7CoTc4HmkaF57qqODwyjGx24gNj76Ecbj7ytytGjUvbc-Xj3l6ytI-o2gqbyxmopMh0cK9ptkGY-7cylp5ZckB7RNfrPGQ-f_1syp8nBPuFaQp41ZGuqa5DaoNq_7oez9NSvH3NYnZTokvNNEzHrNXvcIPG0edi1UgRnpRdE')",
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        pointerEvents: 'none',
      }} />
      <div className="fixed inset-0 z-[-1] pointer-events-none" style={{
        background: 'linear-gradient(to top, #131313, #131313/80, transparent)',
      }} />

      <div className="mx-auto w-full max-w-7xl px-8 py-8">
        {/* ── 12-column grid ── */}
        <div className="grid grid-cols-12 gap-6">

          {/* ══════════════════════════════════════════════════════════
              LEFT PANEL (col-span-4) — Active Production
              ══════════════════════════════════════════════════════════ */}
          <div className="col-span-4">
            {/* FIX 2: glass-panel with explicit cinematic glass style */}
            <div className="rounded-2xl p-6 flex flex-col gap-5 h-full" style={glassStyle}>
              {/* Chip */}
              <div className="flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full bg-[#4cd7f6] shadow-[0_0_8px_rgba(76,215,246,0.6)]" />
                <span
                  className="status-chip"
                  style={{ color: '#4cd7f6', border: '1px solid rgba(76,215,246,0.3)' }}
                >
                  ACTIVE PRODUCTION
                </span>
              </div>

              {/* Project title */}
              <h1
                className="text-3xl font-bold leading-tight"
                style={{ fontFamily: 'Geist, sans-serif', fontWeight: 600, color: '#e5e2e1', letterSpacing: '-0.02em' }}
              >
                {latestProjectTitle || 'No active film'}
              </h1>

              {/* Divider gradient line */}
              <div className="h-px w-full" style={{
                background: 'linear-gradient(90deg, rgba(255,209,101,0.4) 0%, rgba(255,209,101,0.05) 100%)',
              }} />

              {/* Metadata rows */}
              <div className="flex flex-col gap-2">
                <div className="rounded-xl px-4 py-3 flex items-center justify-between" style={{ ...glassStyle, padding: '12px 16px', border: '1px solid rgba(255,255,255,0.05)', background: 'rgba(32,31,31,0.25)' }}>
                  <span className="text-xs uppercase tracking-[0.12em]" style={{ color: '#d3c5ac' }}>Last Modified</span>
                  <span className="text-sm font-medium" style={{ color: '#e5e2e1', fontFamily: "'JetBrains Mono', monospace" }}>
                    {formatTimeAgo(lastModified ?? undefined)}
                  </span>
                </div>
                <div className="rounded-xl px-4 py-3 flex items-center justify-between" style={{ ...glassStyle, padding: '12px 16px', border: '1px solid rgba(255,255,255,0.05)', background: 'rgba(32,31,31,0.25)' }}>
                  <span className="text-xs uppercase tracking-[0.12em]" style={{ color: '#d3c5ac' }}>Scenes</span>
                  <span className="text-sm font-medium" style={{ color: '#e5e2e1', fontFamily: "'JetBrains Mono', monospace" }}>
                    {scenesCount}
                  </span>
                </div>
                <div className="rounded-xl px-4 py-3 flex items-center justify-between" style={{ ...glassStyle, padding: '12px 16px', border: '1px solid rgba(255,255,255,0.05)', background: 'rgba(32,31,31,0.25)' }}>
                  <span className="text-xs uppercase tracking-[0.12em]" style={{ color: '#d3c5ac' }}>Runtime</span>
                  <span className="text-sm font-medium" style={{ color: '#e5e2e1', fontFamily: "'JetBrains Mono', monospace" }}>
                    {runtime ? `${runtime} min` : '—'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* ══════════════════════════════════════════════════════════
              CENTER PANEL (col-span-5) — Primary Actions
              ══════════════════════════════════════════════════════════ */}
          <div className="col-span-5 flex flex-col gap-4">
              {/* Continue Film */}
              <button
                type="button"
                disabled={continuing}
                aria-busy={continuing || undefined}
                onClick={async () => {
                  if (continueInFlightRef.current) return
                  continueInFlightRef.current = true
                  setContinuing(true)
                  try {
                    const projectId = activeProjectId || (overview?.projects?.[0]?.project_id) || (project?.project_id)
                    if (projectId) {
                      await setActiveProject(projectId)
                      navigate(`/studio/overview?project_id=${projectId}`)
                    } else {
                      navigate('/studio')
                    }
                  } finally {
                    continueInFlightRef.current = false
                    setContinuing(false)
                  }
                }}
              className="w-full rounded-full py-5 flex items-center justify-center gap-4 transition-all duration-200 hover:scale-[1.01] active:scale-[0.99]"
              style={{
                ...glassStyle,
                border: '1px solid rgba(255,209,101,0.4)',
                boxShadow: '0 0 30px rgba(255,209,101,0.2), inset 0 1px 0 rgba(255,255,255,0.05)',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget.style.boxShadow = '0 0 50px rgba(255,209,101,0.4), inset 0 1px 0 rgba(255,255,255,0.05)')
              }}
              onMouseLeave={(e) => {
                (e.currentTarget.style.boxShadow = '0 0 30px rgba(255,209,101,0.2), inset 0 1px 0 rgba(255,255,255,0.05)')
              }}
            >
              <svg width="32" height="32" viewBox="0 0 24 24" fill="#ffd165" style={{ display: 'block' }}>
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z" />
              </svg>
              <span className="text-2xl font-bold" style={{ fontFamily: 'Geist, sans-serif', fontWeight: 700, color: '#ffd165', letterSpacing: '-0.02em' }}>
                {continuing ? 'OPENING…' : 'CONTINUE FILM'}
              </span>
            </button>

            {/* Secondary actions row */}
            <div className="flex gap-4 flex-1">
              {/* Switch Project */}
              <button
                type="button"
                onClick={() => navigate('/studio/lobby')}
                className="flex-1 rounded-xl flex flex-col items-center justify-center gap-2 py-6 transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                style={glassStyle}
              >
                <ArrowLeftRight size={24} style={{ color: '#d3c5ac' }} />
                <span className="text-xs font-bold uppercase tracking-[0.12em]" style={{ color: '#d3c5ac' }}>
                  Switch Project
                </span>
              </button>

              {/* Start New Film */}
              <button
                type="button"
                onClick={() => setShowNewProject(true)}
                className="flex-1 rounded-xl flex flex-col items-center justify-center gap-2 py-6 transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                style={glassStyle}
              >
                <Plus size={24} style={{ color: '#d3c5ac' }} />
                <span className="text-xs font-bold uppercase tracking-[0.12em]" style={{ color: '#d3c5ac' }}>
                  Start New Film
                </span>
              </button>
            </div>
          </div>

          {/* ══════════════════════════════════════════════════════════
              RIGHT PANEL (col-span-3) — AI Crew HUD
              ══════════════════════════════════════════════════════════ */}
          <div className="col-span-3">
            {/* FIX 2: glass-panel with cinematic style */}
            <div className="rounded-2xl p-5 flex flex-col gap-3 h-full" style={glassStyle}>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-bold uppercase tracking-[0.14em]" style={{ color: '#d3c5ac', fontFamily: "'JetBrains Mono', monospace" }}>
                  AI CREW
                </span>
              </div>

              {AGENTS.map((agent) => {
                const active = agentStatus[agent.key] ?? false
                return (
                  <div
                    key={agent.key}
                    className="rounded-xl px-4 py-3 flex items-center justify-between"
                    style={{
                      ...glassStyle,
                      border: active
                        ? '1px solid rgba(76,215,246,0.2)'
                        : '1px solid rgba(155,143,121,0.15)',
                      background: active
                        ? 'rgba(76,215,246,0.05)'
                        : 'rgba(32,31,31,0.2)',
                    }}
                  >
                    <div className="flex items-center gap-3">
                      {/* FIX 4: director dot gets cyan/pulse, others get idle brown */}
                      <span
                        className={`inline-block rounded-full ${agent.key === 'director' ? 'w-2 h-2 bg-[#4cd7f6] shadow-[0_0_8px_rgba(76,215,246,0.8)] animate-pulse' : 'w-2 h-2 bg-[#4f4633]'}`}
                      />
                      {agent.icon}
                      <div className="flex flex-col">
                        <span className="text-xs font-semibold" style={{ color: '#e5e2e1' }}>{agent.name}</span>
                        <span className="text-xs" style={{ color: '#9b8f79' }}>{agent.role}</span>
                      </div>
                    </div>
                    {/* FIX 4: ACTIVE/IDLE badges with JetBrains Mono, 10px, 700 weight, uppercase, 0.1em letter-spacing */}
                    <span
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: '10px',
                        fontWeight: 700,
                        letterSpacing: '0.1em',
                        textTransform: 'uppercase',
                        color: active ? '#4cd7f6' : '#9b8f79',
                      }}
                    >
                      {active ? 'ACTIVE' : 'IDLE'}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* ══════════════════════════════════════════════════════════════
            BOTTOM PANEL (full width) — Pipeline Status
            ══════════════════════════════════════════════════════════════ */}
        <div className="rounded-2xl p-4 mt-6" style={glassStyle}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              {/* Backend status */}
              <div className="flex items-center gap-2">
                <span
                  className="inline-block w-2 h-2 rounded-full"
                  style={{
                    background: health ? '#4cd7f6' : '#ffb4ab',
                    boxShadow: health ? '0 0 8px rgba(76,215,246,0.6)' : '0 0 8px rgba(255,180,171,0.4)',
                  }}
                />
                <span style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '10px',
                  fontWeight: 700,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  color: health ? '#4cd7f6' : '#ffb4ab',
                }}>
                  Backend: {healthLoading ? 'CHECKING...' : health ? 'ONLINE' : 'OFFLINE'}
                </span>
              </div>

              <span className="text-[#4f4633]">|</span>

              {/* Last Render */}
              <div className="flex items-center gap-2">
                <span style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '10px',
                  fontWeight: 700,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  color: '#9b8f79',
                }}>
                  Last Render: {(() => { const ts = activity?.updatedAt; return ts ? formatTimeAgo(new Date(ts).toISOString()) : '—' })()}
                </span>
              </div>

              <span className="text-[#4f4633]">|</span>

              {/* Queue */}
              <div className="flex items-center gap-2">
                <span style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '10px',
                  fontWeight: 700,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  color: '#9b8f79',
                }}>
                  Queue: {queueCount} job{queueCount !== 1 ? 's' : ''}
                </span>
              </div>
            </div>

            {/* View Queue button */}
            <Link
              to="/studio/scheduler"
              className="no-underline transition-all duration-200 hover:opacity-80"
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '10px',
                fontWeight: 700,
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                color: '#ffd165',
                border: '1px solid rgba(255,209,101,0.3)',
                padding: '2px 8px',
                borderRadius: '2px',
              }}
            >
              VIEW QUEUE →
            </Link>
          </div>
        </div>
      </div>
    </>
  )
}
