import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronUp, ChevronDown, EllipsisVertical } from 'lucide-react'
import { useRenderActivity } from '../context/RenderActivityContext'
import { useStudio } from '../context/StudioContext'
import { formatProviderLabel } from '../lib/providerDisplay'

const CREW_KEY = 'crew-presence-collapsed'

type CrewAgentId = 'director' | 'writer' | 'memory_archivist' | 'evaluator' | 'provider_router'

type CrewAgent = {
  id: CrewAgentId
  name: string
  initial: string
  activity: string
  active: boolean
}

const MOCK_UPDATES: Array<Record<CrewAgentId, string>> = [
  {
    director: 'Balancing scene pacing...',
    writer: 'Refining dramatic beats...',
    memory_archivist: 'Checking continuity...',
    evaluator: 'Scoring scene coherence...',
    provider_router: 'Selecting Runway...',
  },
  {
    director: 'Tuning camera rhythm...',
    writer: 'Tightening scene objective...',
    memory_archivist: 'Linking prior motifs...',
    evaluator: 'Reviewing emotional flow...',
    provider_router: 'Checking provider readiness...',
  },
]

function baseByRoom(pathname: string): string {
  if (pathname.includes('/writers-room')) return 'Writer shaping scene intent...'
  if (pathname.includes('/previs')) return 'Director adjusting pacing...'
  if (pathname.includes('/production-board')) return 'Evaluator reviewing blockers...'
  if (pathname.includes('/screening-room')) return 'Evaluator reviewing playback cadence...'
  return 'Director aligning next scene pass...'
}

export default function AICrewPresence() {
  const location = useLocation()
  const { activity } = useRenderActivity()
  const { providers } = useStudio()
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(CREW_KEY) === 'true'
    } catch {
      return false
    }
  })
  const [mockIndex, setMockIndex] = useState(0)
  const availableProviderIds = useMemo(() => providers.map((provider) => provider.provider_id.toLowerCase()), [providers])

  useEffect(() => {
    try {
      if (collapsed) {
        localStorage.setItem(CREW_KEY, 'true')
      } else {
        localStorage.setItem(CREW_KEY, 'false')
      }
    } catch {
      // localStorage unavailable
    }
  }, [collapsed])

  useEffect(() => {
    const mockTimer = window.setInterval(() => setMockIndex((prev) => (prev + 1) % MOCK_UPDATES.length), 8000)
    return () => window.clearInterval(mockTimer)
  }, [])

  const agents = useMemo<CrewAgent[]>(() => {
    const mock = MOCK_UPDATES[mockIndex]
    const providerText = activity?.isActive
      ? `Provider Router selecting ${formatProviderLabel(activity.provider || activity.selectedProvider, availableProviderIds)}...`
      : mock.provider_router
    const directorText = activity?.status === 'generating' || activity?.status === 'polling'
      ? 'Director adjusting pacing...'
      : mock.director
    const writerText = activity?.isActive ? 'Writer refining scene prompt...' : mock.writer
    const memoryText = activity?.isActive ? 'Memory Archivist checking continuity...' : mock.memory_archivist
    const evaluatorText = activity?.status === 'completed'
      ? 'Evaluator validating render quality...'
      : mock.evaluator
    const routeBase = baseByRoom(location.pathname)

    return [
      { id: 'director', name: 'Director', initial: 'D', activity: directorText || routeBase, active: true },
      { id: 'writer', name: 'Writer', initial: 'W', activity: writerText, active: true },
      { id: 'memory_archivist', name: 'Memory Archivist', initial: 'M', activity: memoryText, active: true },
      { id: 'evaluator', name: 'Evaluator', initial: 'E', activity: evaluatorText, active: true },
      { id: 'provider_router', name: 'Provider Router', initial: 'P', activity: providerText, active: true },
    ]
  }, [activity, availableProviderIds, location.pathname, mockIndex])

  return (
    <div className="ai-crew-container">
      <motion.div
        className="glass-panel rounded-xl overflow-hidden relative"
        style={{
          border: '1px solid rgba(255,255,255,0.1)',
          boxShadow: '0 40px 80px rgba(0,0,0,0.5)',
          width: '280px',
        }}
        animate={{ height: collapsed ? 48 : 'auto' }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
      >
        {/* Fresnel edge overlay */}
        <span className="fresnel-edge" aria-hidden />

        {/* Header row */}
        <div className="flex items-center justify-between px-4 py-3" style={{ height: 48 }}>
          <span className="font-status-xs text-status-xs text-on-surface-variant uppercase tracking-widest">
            AI CREW PRESENCE
          </span>
          <div className="flex items-center gap-2">
            <span
              className="status-chip inline-flex items-center gap-1.5"
              style={{
                color: '#4cd7f6',
                border: '1px solid rgba(76,215,246,0.3)',
                background: 'rgba(76,215,246,0.08)',
              }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full bg-[#4cd7f6] shadow-[0_0_6px_rgba(76,215,246,0.8)] animate-pulse"
              />
              RADIO LINK STABLE
            </span>
            <button
              type="button"
              onClick={() => setCollapsed((prev) => !prev)}
              className="flex items-center justify-center w-6 h-6 rounded text-on-surface-variant hover:text-primary transition-colors"
              aria-label={collapsed ? 'Expand crew panel' : 'Collapse crew panel'}
            >
              {collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
            </button>
          </div>
        </div>

        {/* Agent rows */}
        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="px-4 pb-4 space-y-2"
            >
              {agents.map((agent) => (
                <div
                  key={agent.id}
                  className="flex items-center gap-3 p-3 rounded-lg"
                  style={{
                    background: 'rgba(28,27,27,0.4)',
                    border: '1px solid rgba(255,255,255,0.05)',
                  }}
                >
                  {/* Avatar circle */}
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 font-metadata-sm font-bold"
                    style={{
                      background: 'var(--color-surface-container-highest, #353534)',
                      border: agent.active ? '1px solid rgba(76,215,246,0.5)' : '1px solid rgba(255,255,255,0.1)',
                      boxShadow: agent.active ? '0 0 8px rgba(76,215,246,0.4)' : 'none',
                      color: agent.active ? '#4cd7f6' : '#9b8f79',
                    }}
                  >
                    {agent.initial}
                  </div>

                  {/* Name + status */}
                  <div className="min-w-0 flex-1">
                    <div className="font-metadata-sm font-bold text-on-surface truncate">
                      {agent.name}
                    </div>
                    <div className="font-status-xs text-status-xs text-on-surface-variant truncate max-w-full overflow-hidden whitespace-nowrap">
                      {agent.activity}
                    </div>
                  </div>

                  {/* More menu */}
                  <button
                    type="button"
                    className="flex items-center justify-center w-6 h-6 rounded text-outline hover:text-primary transition-colors flex-shrink-0"
                    aria-label={`More options for ${agent.name}`}
                  >
                    <EllipsisVertical size={14} />
                  </button>
                </div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  )
}