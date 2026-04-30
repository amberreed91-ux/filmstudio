import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { Settings, MoreHorizontal, TrendingUp, RefreshCw } from 'lucide-react'
import { useStudio } from '../context/StudioContext'
import { retryRenderJob, setRenderMode } from '../lib/studioApi'
import StudioShell from '../components/StudioShell'
import { getProviderSummaries, getRenderQueueRows } from '../lib/studioSelectors'

const COST_SETTINGS_KEY = 'studio:cost-settings'

interface Provider {
  id: string
  name: string
  instance: string
  load: number
  jobs: number
  color: string
  billedLabel: string
}

function ProviderCard({ provider, onMore }: { provider: Provider; onMore?: (provider: Provider) => void }) {
  const isFeatured = provider.jobs > 0

  return (
    <div className="p-4 rounded-xl mb-3" style={{
      background: 'var(--bg-card)',
      border: `1px solid ${isFeatured ? `${provider.color}35` : 'var(--border)'}`,
      boxShadow: isFeatured ? `0 0 20px ${provider.color}10` : 'none',
    }}>
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded flex items-center justify-center text-xs font-bold"
            style={{ background: `${provider.color}20`, color: provider.color, border: `1px solid ${provider.color}30` }}>
            {provider.id === 'aws' ? 'aws' : provider.id === 'runpod' ? '◎' : '⊡'}
          </div>
          <div>
            <div className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>{provider.name}</div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {isFeatured && (
            <span className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>{provider.jobs}</span>
          )}
          <button className="p-1 rounded hover:bg-white/5" onClick={() => onMore?.(provider)}>
            <MoreHorizontal size={12} style={{ color: 'var(--text-muted)' }} />
          </button>
        </div>
      </div>

      <div className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>{provider.instance}</div>
      <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>
        <span>Load: {provider.load}%</span>
        <span className="mx-2">·</span>
        <span>Active Jobs: {provider.jobs}</span>
      </div>
      <div className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>
        Billing: <span style={{ color: 'var(--text-primary)' }}>{provider.billedLabel}</span>
      </div>

      {/* Mini chart */}
      {isFeatured ? (
        <svg viewBox="0 0 120 30" width="100%" height="30">
          <path d="M0 25 Q15 20 30 18 Q45 16 60 20 Q75 24 90 15 Q105 6 120 10"
            stroke={provider.color} fill="none" strokeWidth="1.5" opacity="0.8" />
        </svg>
      ) : (
        <div className="progress-bar mt-1">
          <div style={{ height: 3, width: `${provider.load}%`, borderRadius: 2, background: provider.color }}></div>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const isRendering = status === 'Rendering'
  return (
    <span className="text-xs px-1.5 py-0.5 rounded-sm font-medium"
      style={{
        background: isRendering ? 'rgba(0,200,255,0.12)' : 'rgba(255,255,255,0.05)',
        color: isRendering ? 'var(--accent-cyan)' : 'var(--text-muted)',
      }}>
      {status}
    </span>
  )
}

function ProgressBar({ pct, priority }: { pct: number; priority?: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-20 h-1.5 rounded-full" style={{ background: 'rgba(255,255,255,0.06)' }}>
        <div style={{
          width: `${pct}%`, height: '100%', borderRadius: 9999,
          background: priority ? 'linear-gradient(90deg, #f97316, #ef4444)' : 'linear-gradient(90deg, var(--accent-cyan), var(--accent-purple))',
        }}></div>
      </div>
      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{pct}%</span>
    </div>
  )
}

export default function Cost() {
  const [activeTab, setActiveTab] = useState('Dashboard')
  const [budgetCap, setBudgetCap] = useState(() => {
    const stored = window.localStorage.getItem(COST_SETTINGS_KEY)
    return stored ? JSON.parse(stored).budgetCap || 500 : 500
  })
  const [speedPriority, setSpeedPriority] = useState(() => {
    const stored = window.localStorage.getItem(COST_SETTINGS_KEY)
    return stored ? JSON.parse(stored).speedPriority || 75 : 75
  })
  const [notice, setNotice] = useState<string | null>(null)
  const tabs = ['Dashboard', 'Queue', 'Providers', 'Settings']
  const { project, overview } = useStudio()
  const activeProject = project || overview?.latest_project || null
  const providerSummaries = useMemo(() => getProviderSummaries(activeProject), [activeProject])
  const renderRows = useMemo(() => getRenderQueueRows(activeProject), [activeProject])
  const providerExecution = (activeProject?.interactive_modules?.provider_execution as Record<string, unknown> | undefined) || {}
  const routingLog = [
    ...(Array.isArray(activeProject?.producer_dashboard?.priority_focus) ? activeProject.producer_dashboard.priority_focus : []),
    ...(Array.isArray(activeProject?.producer_dashboard?.blockers) ? activeProject.producer_dashboard.blockers : []),
  ].slice(0, 4)

  const chartW = 320
  const chartH = 80

  const queueTrend = (renderRows.length ? renderRows : [{ progress: 0 } as { progress: number }]).map((row, i, rows) => {
    const x = rows.length === 1 ? chartW / 2 : (i / (rows.length - 1)) * chartW
    const y = chartH - ((row.progress / 100) * chartH)
    return `${x},${y}`
  }).join(' ')

  const activeRenderJob = renderRows.find((job) => !job.status.toLowerCase().includes('complete')) || renderRows[0] || null

  useEffect(() => {
    window.localStorage.setItem(COST_SETTINGS_KEY, JSON.stringify({ budgetCap, speedPriority }))
  }, [budgetCap, speedPriority])

  async function handleRetryTopJob() {
    if (!activeProject?.project_id || !activeRenderJob) return
    setNotice(`Retrying ${activeRenderJob.renderId}...`)
    try {
      await retryRenderJob(activeProject.project_id, activeRenderJob.renderId)
      setNotice(`Retry queued for ${activeRenderJob.renderId}.`)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Retry failed.')
    }
  }

  async function handleApplyRenderMode() {
    if (!activeProject?.project_id) return
    setNotice('Applying render mode...')
    try {
      const nextLiveMode = speedPriority >= 50
      await setRenderMode(activeProject.project_id, nextLiveMode, activeProject.render_provider?.provider_name)
      setNotice(nextLiveMode ? 'Live render mode enabled.' : 'Planning mode restored.')
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Render mode update failed.')
    }
  }

  return (
    <StudioShell>

      <div className="flex flex-1 overflow-hidden">
        {/* Left: Multi-Provider Monitoring */}
        <aside className="w-72 flex flex-col p-4 overflow-y-auto flex-shrink-0"
          style={{ borderRight: '1px solid var(--border)' }}>
          <h2 className="text-xs font-bold tracking-widest uppercase mb-3" style={{ color: 'var(--text-primary)' }}>Multi-Provider Monitoring</h2>
          {providerSummaries.map(provider => (
            <ProviderCard key={provider.id} provider={provider} onMore={() => {
              setActiveTab('Settings')
              setNotice(`${provider.name} routing settings opened.`)
            }} />
          ))}
        </aside>

        {/* Center: Render Queue & Cost Tracking */}
        <main className="flex-1 flex flex-col p-4 gap-4 overflow-y-auto">
          <div className="rounded-xl p-4 flex items-center justify-between gap-4" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div className="flex items-center gap-3">
              <Settings size={16} style={{ color: 'var(--text-muted)' }} />
              <div>
                <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {activeProject ? `${activeProject.title} cost controls` : 'Studio cost controls'}
                </div>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {activeProject?.render_provider?.provider_name || 'demo_realtime'} | Studio X
                </div>
              </div>
            </div>
            <nav className="flex items-center gap-1">
              {tabs.map(tab => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className="px-4 py-1.5 text-sm rounded transition-all"
                  style={{
                    color: activeTab === tab ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                    borderBottom: activeTab === tab ? '2px solid var(--accent-cyan)' : '2px solid transparent',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                  } as CSSProperties}
                >
                  {tab}
                </button>
              ))}
            </nav>
          </div>

          <div className="rounded-xl p-4 flex-1" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                {activeTab === 'Dashboard' && 'Render Queue & Cost Tracking'}
                {activeTab === 'Queue' && 'Queue Inspector'}
                {activeTab === 'Providers' && 'Provider Routing'}
                {activeTab === 'Settings' && 'Routing Settings'}
              </h2>
              {notice && (
                <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(0,200,255,0.1)', color: 'var(--accent-cyan)', border: '1px solid rgba(0,200,255,0.2)' }}>
                  {notice}
                </span>
              )}
            </div>

            {/* Table */}
            <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--border)' }}>
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid var(--border)' }}>
                    {['Scene ID','Status','Progress','ETA','Real-time Cost'].map(h => (
                      <th key={h} className="px-3 py-2 text-left font-medium" style={{ color: 'var(--text-muted)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {renderRows.map((job, i) => (
                    <tr key={i}
                      style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', background: job.priority ? 'rgba(249,115,22,0.05)' : 'transparent' }}>
                      <td className="px-3 py-2 font-mono" style={{ color: job.priority ? '#f97316' : 'var(--accent-cyan)' }}>{job.shotId}</td>
                      <td className="px-3 py-2"><StatusBadge status={job.status} /></td>
                      <td className="px-3 py-2"><ProgressBar pct={job.progress} priority={job.priority} /></td>
                      <td className="px-3 py-2" style={{ color: 'var(--text-muted)' }}>{job.etaLabel}</td>
                      <td className="px-3 py-2" style={{ color: job.priority ? '#f97316' : 'var(--text-muted)' }}>
                        {job.billingLabel}
                        {job.priority && <span className="ml-1 text-xs" style={{ color: '#ef4444' }}>(High Priority)</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {activeTab === 'Dashboard' && (
              <div className="mt-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>Render Queue Health</h3>
                  <div className="flex items-center gap-1 text-xs" style={{ color: 'var(--accent-cyan)' }}>
                    <TrendingUp size={11} />
                    {renderRows.filter((row) => row.progress >= 90).length} review-ready
                  </div>
                </div>
                <div className="rounded-lg p-3 relative" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', height: 120 }}>
                  {renderRows.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>No render queue data available.</span>
                    </div>
                  ) : (
                    <>
                      <div className="absolute left-1 top-1 flex flex-col justify-between h-full text-xs" style={{ color: 'var(--text-muted)', fontSize: 9 }}>
                        <span>100%</span>
                        <span>75%</span>
                        <span>50%</span>
                        <span>25%</span>
                      </div>
                      <svg viewBox={`0 0 ${chartW} ${chartH}`} width="100%" height="100%" style={{ marginLeft: 16 }}>
                        <defs>
                          <linearGradient id="cost-grad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="var(--accent-cyan)" stopOpacity="0.3" />
                            <stop offset="100%" stopColor="var(--accent-cyan)" stopOpacity="0" />
                          </linearGradient>
                        </defs>
                        <polygon points={`0,${chartH} ${queueTrend} ${chartW},${chartH}`} fill="url(#cost-grad)" />
                        <polyline points={queueTrend} fill="none" stroke="var(--accent-cyan)" strokeWidth="1.5" />
                        {[0.2, 0.4, 0.6, 0.8].map(y => (
                          <line key={y} x1="0" y1={y * chartH} x2={chartW} y2={y * chartH} stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
                        ))}
                      </svg>
                      <div className="flex justify-between mt-1 ml-4 text-xs" style={{ color: 'var(--text-muted)', fontSize: 9 }}>
                        {renderRows.slice(0, 6).map((row) => <span key={row.renderId}>{row.renderId}</span>)}
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}

            {activeTab === 'Queue' && (
              <div className="mt-4 rounded-lg p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>Selected Render Job</h3>
                  <button className="text-xs px-2 py-0.5 rounded" onClick={handleRetryTopJob} style={{ background: 'rgba(0,200,255,0.12)', color: 'var(--accent-cyan)', border: '1px solid rgba(0,200,255,0.25)' }}>
                    <RefreshCw size={11} className="inline mr-1" />
                    Retry Top Job
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                    <div style={{ color: 'var(--text-muted)' }}>Scene</div>
                    <div style={{ color: 'var(--text-primary)' }}>{activeRenderJob?.shotId || 'No active job'}</div>
                  </div>
                  <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                    <div style={{ color: 'var(--text-muted)' }}>Status</div>
                    <div style={{ color: 'var(--text-primary)' }}>{activeRenderJob?.status || 'Unknown'}</div>
                  </div>
                  <div className="rounded-lg p-2 col-span-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                    <div style={{ color: 'var(--text-muted)' }}>Queue Tip</div>
                    <div style={{ color: 'var(--text-secondary)' }}>{activeRenderJob ? `${activeRenderJob.renderId} is mapped to ${activeRenderJob.providerName}. Retry writes back to the backend render queue.` : 'Load a project to inspect queue state.'}</div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'Providers' && (
              <div className="mt-4 grid grid-cols-3 gap-3">
                {providerSummaries.map(provider => (
                  <ProviderCard key={provider.id} provider={provider} onMore={() => {
                    setActiveTab('Settings')
                    setNotice(`${provider.name} routing settings opened.`)
                  }} />
                ))}
              </div>
            )}

            {activeTab === 'Settings' && (
              <div className="mt-4 rounded-lg p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                    <div className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Budget Cap</div>
                    <input type="range" min={100} max={1000} step={50} value={budgetCap} onChange={e => setBudgetCap(Number(e.target.value))} className="w-full" />
                    <div className="mt-1" style={{ color: 'var(--text-secondary)' }}>${budgetCap}/day</div>
                  </div>
                  <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                    <div className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Speed Priority</div>
                    <input type="range" min={0} max={100} value={speedPriority} onChange={e => setSpeedPriority(Number(e.target.value))} className="w-full" />
                    <div className="mt-1" style={{ color: 'var(--text-secondary)' }}>{speedPriority >= 50 ? 'High' : 'Cost focused'}</div>
                  </div>
                  <div className="rounded-lg p-2 col-span-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                    <div className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Render Mode</div>
                    <div className="flex items-center justify-between gap-3">
                      <div style={{ color: 'var(--text-secondary)' }}>
                        Current backend mode: {providerExecution.live_mode ? 'live' : 'planning'}.
                        {` `}
                        {speedPriority >= 50 ? 'Apply will request live mode.' : 'Apply will request planning mode.'}
                      </div>
                      <button className="btn-primary text-xs px-3 py-1.5" onClick={() => void handleApplyRenderMode()}>
                        Apply
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>

        {/* Right: Routing Optimizer */}
        <aside className="w-64 flex flex-col p-4 gap-3 overflow-y-auto flex-shrink-0"
          style={{ borderLeft: '1px solid var(--border)' }}>
          <h2 className="text-xs font-bold tracking-widest uppercase" style={{ color: 'var(--text-primary)' }}>Routing Optimizer</h2>

          {/* Provider diagram */}
          <div className="rounded-xl p-4 flex items-center justify-center" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', height: 140 }}>
            <svg viewBox="0 0 180 110" width="100%" height="100%">
              {/* Central hub */}
              <circle cx="90" cy="30" r="18" fill="rgba(0,200,255,0.15)" stroke="var(--accent-cyan)" strokeWidth="1.5" />
              <text x="90" y="27" textAnchor="middle" fill="var(--accent-cyan)" fontSize="7" fontWeight="bold">AI</text>
              <text x="90" y="37" textAnchor="middle" fill="var(--accent-cyan)" fontSize="7">Central Hub</text>

              {/* Provider nodes */}
              {providerSummaries.slice(0, 3).map((provider, index) => {
                const x = [10, 67, 124][index] || 10
                const cx = [33, 90, 147][index] || 33
                return (
                  <g key={provider.id}>
                    <rect x={x} y="65" width="46" height="32" rx="6" fill={`${provider.color}20`} stroke={provider.color} strokeWidth="1" />
                    <text x={cx} y="78" textAnchor="middle" fill={provider.color} fontSize="7">{provider.name.slice(0, 8)}</text>
                    <text x={cx} y="88" textAnchor="middle" fill={provider.color} fontSize="7">{provider.jobs} jobs</text>
                    <line x1="90" y1="48" x2={cx} y2="65" stroke={provider.color} strokeWidth="1" strokeDasharray="3 2" opacity="0.5" />
                  </g>
                )
              })}

            </svg>
          </div>

          {/* Optimizer settings */}
          <div className="flex flex-col gap-2">
            {[
              { label: 'Current Provider', value: activeProject?.render_provider?.provider_name || 'provider_agnostic' },
              { label: 'Routing Status', value: String(providerExecution.status || 'planning_only') },
              { label: 'Budget Limit', value: `${budgetCap}/day local operator cap`, highlight: true },
              { label: 'Speed Priority', value: speedPriority >= 50 ? 'High' : 'Cost focused' },
            ].map(({ label, value, highlight }) => (
              <div key={label} className="rounded-lg px-3 py-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                <div className="text-xs font-medium mb-0.5" style={{ color: 'var(--text-muted)' }}>{label}</div>
                <div className="text-xs" style={{ color: highlight ? 'var(--accent-cyan)' : 'var(--text-secondary)' }}>{value}</div>
                {label === 'Speed Priority' && (
                  <div className="mt-1.5 progress-bar">
                    <div style={{ height: 3, width: `${speedPriority}%`, borderRadius: 2, background: 'var(--accent-cyan)' }}></div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Log */}
          <div className="rounded-xl p-3" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div className="text-xs font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>Log</div>
            <div className="flex flex-col gap-2">
              {routingLog.length ? routingLog.map((entry, i) => (
                <div key={i} className="text-xs leading-relaxed">
                  <span style={{ color: 'var(--text-muted)' }}>[live] </span>
                  <span style={{ color: 'var(--text-secondary)' }}>{entry}</span>
                </div>
              )) : (
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Routing events will appear here when the backend supplies focus notes or blockers.</div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </StudioShell>
  )
}
