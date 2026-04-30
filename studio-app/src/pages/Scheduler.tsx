import { useMemo, useState } from 'react'
import { Search, ChevronLeft, ChevronRight, CheckCircle } from 'lucide-react'
import { CREW } from '../data/mock'
import Waveform from '../components/Waveform'
import { useStudio } from '../context/StudioContext'
import StudioShell from '../components/StudioShell'
import { getDailiesItems, getPipelineStages, getProviderSummaries } from '../lib/studioSelectors'

type CrewViewModel = {
  id: string
  name: string
  task: string
  color: string
  bg: string
  icon: string
  waveform: number[]
}

type DailyViewModel = {
  id: string
  label: string
  reviewed: boolean
}

function readText(value: unknown, fallback: string) {
  return typeof value === 'string' && value.trim() ? value : fallback
}

type PipelineNodeStage = {
  id: string
  label: string
  status: 'complete' | 'active' | 'pending'
  progress: number
  detail?: string
}

function PipelineNode({ stage, isActive, isLast }: { stage: PipelineNodeStage; isActive: boolean; isLast: boolean }) {
  const isComplete = stage.status === 'complete'
  const isPending = stage.status === 'pending'

  return (
    <div className="flex items-center gap-2">
      <div className="flex flex-col items-center gap-1">
        <div className={`px-3 py-2 rounded-lg text-center min-w-28 relative`}
          style={{
            background: isActive ? 'rgba(0,200,255,0.1)' : isComplete ? 'rgba(34,197,94,0.08)' : 'rgba(255,255,255,0.03)',
            border: isActive ? '1px solid rgba(0,200,255,0.4)' : isComplete ? '1px solid rgba(34,197,94,0.2)' : '1px solid rgba(255,255,255,0.08)',
          }}>
          <div className="text-xs font-semibold" style={{ color: isActive ? 'var(--accent-cyan)' : isPending ? 'var(--text-muted)' : 'var(--text-primary)' }}>
            {stage.label}
          </div>
          <div className="text-xs mt-0.5" style={{ color: isComplete ? '#22c55e' : isPending ? 'var(--text-muted)' : 'var(--accent-cyan)' }}>
            {isComplete ? '(Complete)' : isActive ? `(In Progress: ${stage.progress}%)` : '(Pending)'}
          </div>
          {isActive && stage.progress > 0 && (
            <div className="mt-1 progress-bar">
              <div className="progress-fill" style={{ width: `${stage.progress}%` }}></div>
            </div>
          )}
        </div>
        {isActive && stage.detail && (
          <div className="rounded p-2 text-xs" style={{ background: 'rgba(0,200,255,0.06)', border: '1px solid rgba(0,200,255,0.15)', color: 'var(--text-secondary)', maxWidth: 140 }}>
            {stage.detail.split(' • ').map((line, i) => (
              <div key={i} className="flex items-center gap-1">
                {i === 0 ? <span>≡</span> : i === 1 ? <span>👤</span> : <CheckCircle size={10} style={{ color: '#22c55e' }} />}
                <span>{line}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      {!isLast && (
        <div className="flex items-center" style={{ color: 'var(--text-muted)', marginBottom: 16 }}>→</div>
      )}
    </div>
  )
}

function CrewCard({ crew }: { crew: typeof CREW[0] }) {
  return (
    <div className="p-3 rounded-xl mb-3 flex flex-col gap-2"
      style={{ background: crew.bg, border: `1px solid ${crew.color}30` }}>
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm"
          style={{ background: `${crew.color}20`, border: `1px solid ${crew.color}40` }}>
          {crew.id === 'director' ? '⬡' : crew.id === 'storyboard' ? '◷' : crew.id === 'editor' ? '✂' : crew.id === 'cinematographer' ? '◉' : '♪'}
        </div>
        <div>
          <div className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>{crew.name}</div>
          <div className="text-xs" style={{ color: crew.color }}>{crew.task}</div>
        </div>
      </div>
      <Waveform points={crew.waveform} color={crew.color} height={28} width={180} />
    </div>
  )
}

export default function Scheduler() {
  const [dailyIdx, setDailyIdx] = useState(0)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedDailyId, setSelectedDailyId] = useState<string | null>(null)
  const [reviewStatus, setReviewStatus] = useState<string | null>(null)
  const { project, overview, recordDailiesSelect, loadProject } = useStudio()
  const activeProject = project || overview?.latest_project || null
  const livePipeline = useMemo(() => getPipelineStages(activeProject), [activeProject])
  const providerSummaries = useMemo(() => getProviderSummaries(activeProject), [activeProject])
  const dailiesFeed = useMemo(() => getDailiesItems(activeProject), [activeProject])
  const liveCrew = activeProject?.crew_agents?.length
    ? activeProject.crew_agents.slice(0, 5).map((rawAgent, index): CrewViewModel => {
        const agent = rawAgent as Record<string, unknown>

        return {
        id: String(agent.agent || index),
        name: `${String(agent.agent || 'Crew')}`.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
        task: readText(agent.current_task, readText(agent.status, 'Ready')),
        color: ['#22c55e', '#a855f7', '#3b82f6', '#f97316', '#06b6d4'][index % 5],
        bg: ['#052e16', '#2e1065', '#1e3a5f', '#431407', '#083344'][index % 5],
        icon: readText(agent.agent, 'crew'),
        waveform: [20, 35, 15, 40, 28, 50, 33, 45, 20, 38].map((n, i) => n + ((index + i) % 3) * 2),
      }
    })
    : CREW
  const liveDailies: DailyViewModel[] = dailiesFeed.length
    ? dailiesFeed.map((item) => ({
        id: item.renderId,
        label: `${item.shotId} • ${item.previewLabel}`,
        reviewed: item.selected || item.status.includes('approved'),
      }))
    : []
  const query = searchQuery.trim().toLowerCase()
  const filteredCrew = query
    ? liveCrew.filter((crew) => `${crew.name} ${crew.task}`.toLowerCase().includes(query))
    : liveCrew
  const filteredDailies = query
    ? liveDailies.filter((shot) => shot.label.toLowerCase().includes(query))
    : liveDailies
  const maxDailyIdx = Math.max(0, filteredDailies.length - 3)
  const clampedDailyIdx = Math.min(dailyIdx, maxDailyIdx)
  const visibleDailies = filteredDailies.slice(clampedDailyIdx, clampedDailyIdx + 3)
  const activeStageIdx = livePipeline.findIndex((s) => s.status === 'active')
  const producerDashboard = activeProject?.producer_dashboard
  const rightsBoard = activeProject?.rights_safety_clearance_board
  const priorityFocus = Array.isArray(producerDashboard?.priority_focus) ? producerDashboard.priority_focus : []
  const blockers = Array.isArray(producerDashboard?.blockers) ? producerDashboard.blockers : []
  const sceneFlags = Array.isArray(rightsBoard?.scene_flags) ? rightsBoard.scene_flags : []

  return (
    <StudioShell>

      <div className="flex flex-1 overflow-hidden">
        {/* Left: AI Crew */}
        <aside className="w-56 flex flex-col p-4 overflow-y-auto flex-shrink-0"
          style={{ borderRight: '1px solid var(--border)' }}>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>AI Crew</h2>
            {!activeProject?.crew_agents?.length && (
              <span className="text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(245,158,11,0.1)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.2)' }}>
                Demo
              </span>
            )}
          </div>
          {filteredCrew.map((crew) => <CrewCard key={crew.id} crew={crew} />)}
          {!filteredCrew.length && (
            <div className="text-xs p-3 rounded-lg" style={{ color: 'var(--text-muted)', border: '1px solid var(--border)', background: 'rgba(255,255,255,0.03)' }}>
              No crew or dailies match “{searchQuery}”.
            </div>
          )}
        </aside>

        {/* Center: Pipeline + Dailies */}
        <main className="flex-1 flex flex-col p-4 gap-4 overflow-y-auto">
          <div className="rounded-xl p-4 flex items-center justify-between gap-4" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-5 h-5 rounded flex-shrink-0" style={{ background: 'var(--accent-cyan)', opacity: 0.8 }}></div>
              <button
                className="flex items-center gap-1.5 text-sm font-medium"
                onClick={async () => {
                  if (activeProject?.project_id) {
                    setReviewStatus('Refreshing project from backend...')
                    try {
                      await loadProject(activeProject.project_id)
                      setReviewStatus('Project refreshed from backend.')
                    } catch (err) {
                      setReviewStatus(err instanceof Error ? err.message : 'Project refresh failed.')
                    }
                  }
                }}
                style={{ color: 'var(--text-primary)', background: 'none', border: 'none', cursor: 'pointer' }}
              >
                Project: {activeProject?.title || 'Neon Dreams v2.4'}
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M2 4L6 8L10 4" stroke="currentColor" strokeWidth="1.5" />
                </svg>
              </button>
            </div>
            <div className="flex-1 max-w-xs">
              <div className="relative">
                <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
                <input type="text" placeholder="Search crew or dailies"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 rounded-lg text-xs"
                  style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', color: 'var(--text-primary)', outline: 'none' }} />
              </div>
            </div>
          </div>

          {/* Production Pipeline */}
          <div className="rounded-xl p-4" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Production Pipeline</h2>
              {!activeProject?.project_dashboard?.cards?.length && (
                <span className="text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(245,158,11,0.1)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.2)' }}>
                  Demo stages
                </span>
              )}
            </div>
            <div className="flex items-start gap-3 flex-wrap">
              {livePipeline.map((stage, i) => (
                <PipelineNode
                  key={stage.id}
                  stage={stage}
                  isActive={i === activeStageIdx}
                  isLast={i === livePipeline.length - 1}
                />
              ))}
            </div>
          </div>

          {/* Render Provider Routing */}
          <div className="rounded-xl p-4" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <h2 className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>Render Provider Routing</h2>
            <p className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>Derived from live render queue assignments</p>
            <div className="grid grid-cols-3 gap-3">
              {providerSummaries.map((provider) => (
                <div key={provider.id} className="rounded-lg p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                  <div className="flex justify-between items-baseline mb-1">
                    <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>{provider.name}</span>
                    <span className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>{provider.jobs}</span>
                  </div>
                  <div className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>{provider.instance} · Load {provider.load}%</div>
                  <div className="progress-bar">
                    <div style={{ height: 3, width: `${provider.load}%`, borderRadius: 2, background: provider.color }}></div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Live Dailies */}
          <div className="rounded-xl p-4" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Live Dailies</h2>
              <div className="flex gap-1">
                <button className="p-1 rounded hover:bg-white/5" onClick={() => setDailyIdx(Math.max(0, clampedDailyIdx - 1))}>
                  <ChevronLeft size={14} style={{ color: 'var(--text-muted)' }} />
                </button>
                <button className="p-1 rounded hover:bg-white/5" onClick={() => setDailyIdx(Math.min(maxDailyIdx, clampedDailyIdx + 1))}>
                  <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
                </button>
              </div>
            </div>
            {reviewStatus && (
              <div className="mb-2 text-xs px-3 py-2 rounded-lg" style={{ background: 'rgba(0,200,255,0.06)', border: '1px solid rgba(0,200,255,0.15)', color: 'var(--text-secondary)' }}>
                {reviewStatus}
              </div>
            )}
            <div className="flex gap-3 overflow-hidden">
              {visibleDailies.map((shot, i: number) => (
                <div key={shot.id} className="flex-1 rounded-xl overflow-hidden" style={{ border: `1px solid ${shot.id === selectedDailyId || i === 1 ? 'rgba(168,85,247,0.5)' : 'var(--border)'}` }}>
                  <div className="relative" style={{ height: 120, background: `linear-gradient(135deg, hsl(${200 + i * 15}, 40%, ${6 + i * 2}%), hsl(${220 + i * 10}, 50%, ${10 + i}%))` }}>
                    {shot.reviewed && (
                      <div className="absolute top-2 left-2">
                        <CheckCircle size={14} style={{ color: '#22c55e' }} />
                      </div>
                    )}
                    <div className="absolute bottom-0 left-0 right-0 p-2 flex items-end justify-between"
                      style={{ background: 'linear-gradient(transparent, rgba(0,0,0,0.7))' }}>
                      <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>{shot.label}</span>
                      <button
                        className="text-xs px-2 py-0.5 rounded"
                        onClick={async () => {
                          setSelectedDailyId(shot.id)
                          setReviewStatus(`Reviewing ${shot.id}...`)
                          try {
                            await recordDailiesSelect(shot.id, true, 92, 'Marked from Live Dailies review control.')
                            setReviewStatus(`Queued ${shot.id} for review and marked selected.`)
                          } catch (err) {
                            setReviewStatus(err instanceof Error ? err.message : 'Dailies review failed.')
                          }
                        }}
                        style={{ background: 'rgba(0,200,255,0.15)', color: 'var(--accent-cyan)', border: '1px solid rgba(0,200,255,0.3)' }}
                      >
                        Review
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </main>

        {/* Right rail: Creative Learning */}
        <aside className="w-64 flex flex-col p-4 gap-3 overflow-y-auto flex-shrink-0"
          style={{ borderLeft: '1px solid var(--border)' }}>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Creative Learning</h2>

          {/* Preference card */}
          <div className="rounded-xl p-3" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div className="text-xs font-medium mb-1" style={{ color: 'var(--text-primary)' }}>Preference:</div>
            <div className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>{priorityFocus[0] || 'Waiting for new study and approval signals.'}</div>
            <svg viewBox="0 0 160 40" width="100%" height="40">
              <path d="M0 30 Q20 28 40 20 Q60 12 80 18 Q100 24 120 15 Q140 6 160 12"
                stroke="var(--accent-cyan)" fill="none" strokeWidth="1.5" />
              <circle cx="100" cy="17" r="3" fill="var(--accent-cyan)" />
            </svg>
          </div>

          {/* Adaptation card */}
          <div className="rounded-xl p-3" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div className="flex items-center gap-2 mb-1">
              <div className="w-6 h-6 rounded flex items-center justify-center" style={{ background: 'rgba(59,130,246,0.15)' }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              </div>
              <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>Adaptation:</span>
            </div>
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{blockers[0] || 'No active adaptation blockers.'}</div>
          </div>

          {/* Style Profile */}
          <div className="rounded-xl p-3" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div className="text-xs font-medium mb-1" style={{ color: 'var(--text-primary)' }}>Style Profile:</div>
            <div className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>
              {activeProject?.production_bible?.creative_intent || 'No creative intent loaded'}
            </div>
            <div className="rounded-lg overflow-hidden" style={{ height: 50, background: 'linear-gradient(90deg, #0f0a1a, #1a0a2e, #2a1040)' }}>
              <div style={{ height: '100%', background: 'linear-gradient(135deg, rgba(168,85,247,0.3), rgba(0,200,255,0.1))' }}></div>
            </div>
          </div>

          <div className="rounded-xl p-3" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div className="text-xs font-medium mb-2" style={{ color: 'var(--text-primary)' }}>Scene Flags</div>
            <div className="flex flex-col gap-2">
              {sceneFlags.length ? sceneFlags.slice(0, 3).map((flag, index) => {
                const row = flag as Record<string, unknown>
                return (
                  <div key={index} className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                    <div style={{ color: 'var(--text-primary)' }}>{readText(row.scene_id, 'Scene')}</div>
                    <div style={{ color: 'var(--text-muted)' }}>{Array.isArray(row.notes) ? String(row.notes[0] || '') : 'No notes supplied.'}</div>
                  </div>
                )
              }) : (
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>No scene flags are active right now.</div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </StudioShell>
  )
}
