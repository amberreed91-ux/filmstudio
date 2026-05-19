import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useRenderActivity } from '../context/RenderActivityContext'
import { useStudio } from '../context/StudioContext'
import { formatProviderLabel } from '../lib/providerDisplay'

type CrewAgentId = 'director' | 'writer' | 'memory_archivist' | 'evaluator' | 'provider_router'

type CrewAgent = {
  id: CrewAgentId
  name: string
  icon: string
  activity: string
  confidence: number
}

const MOCK_UPDATES: Array<Record<CrewAgentId, string>> = [
  {
    director: 'Director adjusting pacing...',
    writer: 'Writer refining dramatic beats...',
    memory_archivist: 'Memory Archivist checking continuity...',
    evaluator: 'Evaluator scoring scene coherence...',
    provider_router: 'Provider Router selecting Runway...',
  },
  {
    director: 'Director tuning camera rhythm...',
    writer: 'Writer tightening scene objective...',
    memory_archivist: 'Memory Archivist linking prior motifs...',
    evaluator: 'Evaluator reviewing emotional flow...',
    provider_router: 'Provider Router checking provider readiness...',
  },
]

function confidenceClass(confidence: number): string {
  if (confidence >= 0.85) return 'crew-confidence-high'
  if (confidence >= 0.65) return 'crew-confidence-medium'
  return 'crew-confidence-low'
}

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
  const [mockIndex, setMockIndex] = useState(0)
  const [typingTick, setTypingTick] = useState(0)
  const availableProviderIds = useMemo(() => providers.map((provider) => provider.provider_id.toLowerCase()), [providers])

  useEffect(() => {
    // Reduced frequency from 3.6s to 8s for mock updates
    const mockTimer = window.setInterval(() => setMockIndex((prev) => (prev + 1) % MOCK_UPDATES.length), 8000)
    // Reduced frequency from 420ms to 1s for typing animation
    const typingTimer = window.setInterval(() => setTypingTick((prev) => (prev + 1) % 4), 1000)
    return () => {
      window.clearInterval(mockTimer)
      window.clearInterval(typingTimer)
    }
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
      { id: 'director', name: 'Director', icon: 'D', activity: directorText || routeBase, confidence: activity?.isActive ? 0.9 : 0.74 },
      { id: 'writer', name: 'Writer', icon: 'W', activity: writerText, confidence: activity?.isActive ? 0.82 : 0.68 },
      { id: 'memory_archivist', name: 'Memory Archivist', icon: 'M', activity: memoryText, confidence: activity?.isActive ? 0.8 : 0.66 },
      { id: 'evaluator', name: 'Evaluator', icon: 'E', activity: evaluatorText, confidence: activity?.status === 'failed' ? 0.57 : 0.77 },
      { id: 'provider_router', name: 'Provider Router', icon: 'P', activity: providerText, confidence: activity?.isActive ? 0.88 : 0.72 },
    ]
  }, [activity, availableProviderIds, location.pathname, mockIndex])

  const dots = '.'.repeat((typingTick % 3) + 1)

  return (
    <aside className="ai-crew-presence" aria-live="polite" aria-label="AI Crew Presence">
      <div className="ai-crew-radio" />
      <div className="relative z-10">
        <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-[0.14em] text-zinc-300">
          <span>AI Crew Presence</span>
          <span className="rounded-full border border-white/15 bg-black/25 px-2 py-0.5 text-[9px]">radio link stable</span>
        </div>
        <div className="space-y-1.5">
          {agents.map((agent) => (
            <div key={agent.id} className={`ai-crew-agent ${confidenceClass(agent.confidence)}`}>
              <div className="ai-crew-avatar">{agent.icon}</div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[10px] uppercase tracking-[0.12em] text-zinc-100">{agent.name}</div>
                <div className="truncate text-[11px] text-zinc-300">{agent.activity}</div>
              </div>
              <div className="text-[10px] text-cyan-200">{dots}</div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  )
}
