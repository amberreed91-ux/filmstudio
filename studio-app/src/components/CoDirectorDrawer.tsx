import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import {
  buildCoDirectorChatPayload,
  formatMemoryProvenance,
  type CoDirectorContext as Context,
  type CoDirectorSceneSummary as SceneSummary,
  type CoDirectorSpecialist as Specialist,
} from '../lib/coDirectorDrawerContext'
import {
  Clapperboard,
  Edit3,
  MemoryStick,
  BarChart3,
  Network,
  Send,
  X,
  ArrowLeftRight,
  Filter,
} from 'lucide-react'

interface Message {
  role: 'user' | 'agent'
  text: string
  specialist?: Specialist
  timestamp: number
}

interface CoDirectorDrawerProps {
  isOpen: boolean
  onClose: () => void
  activeProjectId?: string
  activeRoomName?: string
}

interface SpecialistDef {
  id: Specialist
  label: string
  icon: typeof Clapperboard
  prompt: string
}

const SPECIALISTS: SpecialistDef[] = [
  { id: 'director', label: 'Director', icon: Clapperboard, prompt: 'You are the Director. Guide creative vision and scene approval.' },
  { id: 'writer', label: 'Writer', icon: Edit3, prompt: 'You are the Writer. Advise on dialogue, structure, and narrative beats.' },
  { id: 'memory_archivist', label: 'Memory Archivist', icon: MemoryStick, prompt: 'You are the Memory Archivist. Reference memory and patterns.' },
  { id: 'evaluator', label: 'Evaluator', icon: BarChart3, prompt: 'You are the Evaluator. Assess quality, coherence, and emotional impact.' },
  { id: 'provider_router', label: 'Provider Router', icon: Network, prompt: 'You are the Provider Router. Manage render provider selection.' },
]

const CONTEXT_LABELS: Record<Context, string> = {
  current_scene: 'Current Scene',
  full_script: 'Full Script',
  project_overview: 'Project Overview',
  custom: 'Custom',
}

interface DirectorMemoryBundle {
  symbols?: unknown[]
  motifs?: unknown[]
  characters?: unknown[]
  themes?: unknown[]
  notes?: unknown[]
  debates?: unknown[]
}

function countMemoryEntries(bundle: DirectorMemoryBundle | null | undefined): number {
  if (!bundle) return 0
  let total = 0
  for (const key of ['symbols', 'motifs', 'characters', 'themes', 'notes', 'debates'] as const) {
    const list = bundle[key]
    if (Array.isArray(list)) total += list.length
  }
  return total
}

interface ProjectScenesResponse {
  scenes?: SceneSummary[]
}

function deriveSceneContextLabel(
  context: Context,
  scenes: SceneSummary[] | undefined,
  activeSceneId?: string,
): string {
  if (context === 'current_scene') {
    if (!scenes || scenes.length === 0) return 'CURRENT SCENE'
    const idx = scenes.findIndex((s) => s.scene_id === activeSceneId)
    const scene = idx >= 0 ? scenes[idx] : scenes[0]
    const num = String(idx >= 0 ? idx + 1 : 1).padStart(2, '0')
    const title = scene.location || scene.scene_name || scene.scene_id
    return `SCENE ${num} — ${String(title).toUpperCase()}`
  }
  if (context === 'full_script') return 'FULL SCRIPT'
  if (context === 'project_overview') return 'FULL PROJECT'
  return 'CUSTOM CONTEXT'
}

export default function CoDirectorDrawer({ isOpen, onClose, activeProjectId, activeRoomName }: CoDirectorDrawerProps) {
  const location = useLocation()
  const [specialist, setSpecialist] = useState<Specialist>('director')
  const [context, setContext] = useState<Context>('current_scene')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [showContextMenu, setShowContextMenu] = useState(false)
  const [lastMemoryEntriesSupplied, setLastMemoryEntriesSupplied] = useState<number | null>(null)
  const threadRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const activeSpecialistData = useMemo<SpecialistDef>(
    () => SPECIALISTS.find((s) => s.id === specialist) ?? SPECIALISTS[0],
    [specialist],
  )

  // ── Director's Memory count for indicator ─────────────────────────────────
  const memoryQuery = useQuery<{ memory: DirectorMemoryBundle }>({
    queryKey: ['director-memory', activeProjectId],
    enabled: !!activeProjectId && isOpen,
    queryFn: async () => {
      const res = await fetch(
        `/api/f51/studio/projects/${encodeURIComponent(activeProjectId ?? '')}/director-memory`,
      )
      if (!res.ok) throw new Error(`director-memory ${res.status}`)
      return res.json()
    },
    staleTime: 60 * 1000,
    retry: 1,
  })

  const memoryEntries = countMemoryEntries(memoryQuery.data?.memory)

  // ── Lightweight scene list for context chip ───────────────────────────────
  const scenesQuery = useQuery<ProjectScenesResponse>({
    queryKey: ['project-scenes-light', activeProjectId],
    enabled: !!activeProjectId && isOpen,
    queryFn: async () => {
      const res = await fetch(
        `/api/f51/studio/projects/${encodeURIComponent(activeProjectId ?? '')}/scenes`,
      )
      if (!res.ok) return { scenes: [] }
      return res.json()
    },
    staleTime: 60 * 1000,
    retry: 0,
  })

  const activeSceneId = new URLSearchParams(location.search).get('scene') || undefined
  const contextLabel = deriveSceneContextLabel(context, scenesQuery.data?.scenes, activeSceneId)

  // Auto-scroll on new messages
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight
    }
  }, [messages, loading])

  // Reset thread when specialist changes
  useEffect(() => {
    setMessages([])
    setInput('')
    setLastMemoryEntriesSupplied(null)
  }, [specialist])

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [isOpen, onClose])

  const handleSend = async () => {
    const trimmed = input.trim()
    if (!trimmed || loading) return

    const userMsg: Message = {
      role: 'user',
      text: trimmed,
      specialist,
      timestamp: Date.now(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const payload = buildCoDirectorChatPayload({
        specialist,
        message: trimmed,
        context,
        projectId: activeProjectId,
        systemPrompt: activeSpecialistData.prompt,
        scenes: scenesQuery.data?.scenes,
        activeSceneId,
      })

      const res = await fetch(
        `/api/f51/studio/projects/${encodeURIComponent(activeProjectId ?? '')}/co-director/chat`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      )

      const data = await res.json().catch(() => null)

      if (!res.ok) {
        throw new Error(String(data?.detail || `Co-Director request failed (${res.status})`))
      }

      let replyText = ''
      if (data?.reply) replyText = String(data.reply)
      else if (data?.message) replyText = String(data.message)
      else if (data?.response) replyText = String(data.response)
      if (!replyText.trim()) {
        throw new Error('Co-Director returned an empty response')
      }
      setLastMemoryEntriesSupplied(
        typeof data?.memory_entries_used === 'number' ? data.memory_entries_used : null,
      )

      const agentMsg: Message = {
        role: 'agent',
        text: replyText,
        specialist,
        timestamp: Date.now(),
      }
      setMessages((prev) => [...prev, agentMsg])
    } catch {
      const agentMsg: Message = {
        role: 'agent',
        text: 'The Co-Director could not respond just now. Please retry when the service is available.',
        specialist,
        timestamp: Date.now(),
      }
      setMessages((prev) => [...prev, agentMsg])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const EmptySpecialistIcon = activeSpecialistData.icon
  const showMemoryIndicator = memoryEntries > 0

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-[140] bg-black/60 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            onClick={onClose}
          />

          {/* Drawer */}
          <motion.aside
            role="dialog"
            aria-label="Co-Director Brain"
            className="fixed right-0 top-0 z-[150] h-screen w-[400px] flex flex-col glass-panel"
            style={{
              borderTopLeftRadius: 16,
              borderBottomLeftRadius: 16,
              borderTopRightRadius: 0,
              borderBottomRightRadius: 0,
              borderRight: '1px solid rgba(255,255,255,0.08)',
              overflow: 'hidden',
            }}
            initial={{ x: 400 }}
            animate={{ x: 0 }}
            exit={{ x: 400 }}
            transition={{ type: 'spring', stiffness: 300, damping: 28 }}
          >
            {/* Fresnel edge — light-catch inner stroke */}
            <span className="fresnel-edge" aria-hidden />

            {/* Header */}
            <div className="relative flex items-start justify-between px-5 pt-5 pb-3 z-10">
              <div>
                <h2 className="headline-lg text-primary amber-glow">CO-DIRECTOR BRAIN</h2>
                <p className="font-status-xs text-on-surface-variant mt-1.5">
                  {activeRoomName ?? 'Studio'}
                </p>
              </div>
              <button
                type="button"
                aria-label="Close co-director"
                onClick={onClose}
                className="flex items-center justify-center w-8 h-8 rounded-full glass-panel text-on-surface-variant hover:text-white transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Specialist selector */}
            <div className="flex gap-2 px-5 pb-3 overflow-x-auto scrollbar-thin relative z-10">
              {SPECIALISTS.map(({ id, label, icon: Icon }) => {
                const isActive = specialist === id
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setSpecialist(id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] uppercase tracking-[0.12em] transition-all flex-shrink-0 ${
                      isActive
                        ? 'bg-secondary-container text-[#003640] shadow-[0_0_14px_rgba(0,255,255,0.35)] cyan-glow'
                        : 'glass-panel text-zinc-400 hover:text-white'
                    }`}
                  >
                    <Icon size={14} />
                    <span>{label}</span>
                  </button>
                )
              })}
            </div>

            {/* Memory indicator — only when entries > 0 */}
            {showMemoryIndicator && (
              <div className="px-5 pb-2 relative z-10">
                <span className="font-status-xs text-on-surface-variant inline-flex items-center gap-1.5">
                  <MemoryStick size={11} />
                  {formatMemoryProvenance(memoryEntries, lastMemoryEntriesSupplied)}
                </span>
              </div>
            )}

            {/* Conversation thread */}
            <div
              ref={threadRef}
              className="flex-1 overflow-y-auto px-5 space-y-3 pb-3 scrollbar-thin relative z-10"
            >
              {messages.length === 0 && !loading && (
                <div className="h-full min-h-[280px] flex flex-col items-center justify-center text-center gap-3 py-10">
                  <div className="p-3 rounded-full bg-white/5">
                    <EmptySpecialistIcon size={24} className="text-amber-300" />
                  </div>
                  <p className="text-on-surface-variant text-sm max-w-[260px] leading-relaxed">
                    Ask your <span className="text-white font-medium">{activeSpecialistData.label}</span> anything about this scene.
                  </p>
                </div>
              )}

              {messages.map((msg, idx) => (
                <div
                  key={`${msg.timestamp}-${idx}`}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div className={`max-w-[82%] ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
                    {msg.role === 'agent' && (
                      <span
                        className="status-chip inline-block mb-1"
                        style={{
                          color: 'var(--color-secondary)',
                          borderColor: 'rgba(76, 215, 246, 0.32)',
                          background: 'rgba(76, 215, 246, 0.08)',
                        }}
                      >
                        {SPECIALISTS.find((s) => s.id === msg.specialist)?.label ?? 'AGENT'}
                      </span>
                    )}
                    <div
                      className={`px-3.5 py-2.5 text-sm leading-relaxed ${
                        msg.role === 'user'
                          ? 'bg-[#2a2218] border border-amber-500/25 text-amber-50 shadow-[0_0_18px_rgba(255,209,101,0.08)]'
                          : 'glass-panel text-zinc-200'
                      }`}
                      style={{
                        borderRadius: '14px',
                        borderTopRightRadius: msg.role === 'user' ? '4px' : '14px',
                        borderTopLeftRadius: msg.role === 'agent' ? '4px' : '14px',
                      }}
                    >
                      {msg.text}
                    </div>
                  </div>
                </div>
              ))}

              {/* Typing indicator — three amber dots pulse */}
              {loading && (
                <div className="flex justify-start">
                  <div className="glass-panel px-4 py-3 flex items-center gap-1.5">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <span
                        key={i}
                        className="inline-block w-1.5 h-1.5 rounded-full bg-amber-300 animate-pulse"
                        style={{ animationDelay: `${i * 0.15}s` }}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Context chip */}
            <div className="px-5 pb-2 flex items-center gap-2 relative z-10">
              <span className="status-chip" style={{ color: 'var(--color-on-surface-variant)' }}>
                {contextLabel}
              </span>
              <button
                type="button"
                onClick={() => setShowContextMenu((prev) => !prev)}
                className="inline-flex items-center gap-1 text-[11px] uppercase tracking-[0.12em] text-zinc-400 hover:text-white transition-colors font-status-xs"
                style={{ fontSize: '9px' }}
              >
                <ArrowLeftRight size={11} />
                CHANGE CONTEXT
              </button>

              {showContextMenu && (
                <div className="absolute left-5 bottom-full mb-1 z-20">
                  <div className="glass-panel rounded-lg border border-white/10 py-1 w-44">
                    {(Object.keys(CONTEXT_LABELS) as Context[]).map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => {
                          setContext(c)
                          setShowContextMenu(false)
                        }}
                        className={`block w-full text-left px-3 py-1.5 text-xs hover:bg-white/5 transition-colors ${
                          context === c ? 'text-white' : 'text-zinc-300'
                        }`}
                      >
                        {CONTEXT_LABELS[c]}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Input area */}
            <div className="px-5 pb-5 pt-2 glass-panel border-t border-white/5 relative z-10">
              <div className="relative flex items-end gap-2">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={`Direct your ${activeSpecialistData.label.toLowerCase()}...`}
                  rows={1}
                  className="cyber-input flex-1 resize-none text-sm py-2.5"
                  style={{ minHeight: '40px', maxHeight: '96px' }}
                  onInput={(e) => {
                    const el = e.target as HTMLTextAreaElement
                    el.style.height = 'auto'
                    el.style.height = `${Math.min(el.scrollHeight, 96)}px`
                  }}
                />
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={loading || input.trim().length === 0}
                  aria-label="Send"
                  className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-primary text-xs font-semibold text-black disabled:opacity-40 disabled:cursor-not-allowed hover:brightness-110 transition-all"
                >
                  <Send size={14} />
                  <span className="hidden">SEND</span>
                </button>
              </div>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

// Re-export the Filter icon alias so callers that want a "movie_filter" semantic
// can import from this file without depending on lucide-react directly.
export { Filter as MovieFilterIcon }
