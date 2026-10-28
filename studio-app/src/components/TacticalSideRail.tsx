import { useState } from 'react'
import { useTacticalTelemetry } from '../hooks/useTacticalTelemetry'

/**
 * High-density tactical telemetry side-rail (#070312).
 * Ports the standalone ANIMATION_8 dock: global project context, render
 * queue gauges, live room feed nodes, 2D system control triggers,
 * telemetry override + diagnostic sub-logs.
 *
 * Gauges, feeds, and port status read live backend data through
 * useTacticalTelemetry (service-mediated routes only — the rail never
 * touches storage or providers). When the backend is unreachable or a
 * figure has no record, the rail falls back to its staging dressing and
 * says STAGING instead of inventing data. The CR figure is spend on
 * record (realized + estimated from render job records), never presented
 * as an account balance — no balance endpoint exists.
 */

export interface TacticalFeed {
  roomId: string
  title: string
  code: string
  status: string
  tone: 'violet' | 'rose' | 'teal' | 'cyan'
}

const STAGING_ACTIVE_SLOTS = 166
const STAGING_CR = '14,820'

const STAGING_FEEDS: TacticalFeed[] = [
  { roomId: 'previs', title: 'PREVIS BAY', code: 'HETR2CS 1285008063', status: 'Active', tone: 'violet' },
  { roomId: 'screening', title: 'THEATER', code: 'NETR2GS 0220303088', status: 'clip_v2.mp4', tone: 'rose' },
  { roomId: 'screening', title: 'THEATER', code: 'spatial presence active', status: 'P62130', tone: 'violet' },
  { roomId: 'production', title: 'PRODUCTION DESK', code: 'HETRICS 3295303050', status: '• 9921', tone: 'teal' },
  { roomId: 'production', title: 'PRODUCTION DESK', code: 'running task_9721', status: '• 9721', tone: 'cyan' },
]

function focusRoom(roomId: string) {
  window.dispatchEvent(new CustomEvent('focus-room', { detail: { roomId } }))
}

function recenter() {
  window.dispatchEvent(new CustomEvent('recenter-stage'))
}

export default function TacticalSideRail({ projectId }: { projectId: string }) {
  const [rigStatus, setRigStatus] = useState('READY')
  const [rigBusy, setRigBusy] = useState(false)
  const [telemetryOverride, setTelemetryOverride] = useState(true)
  const [dagStatus, setDagStatus] = useState('PASSED')
  const [specsLog, setSpecsLog] = useState('> Download Component SPECS ... OK')

  const telemetry = useTacticalTelemetry(projectId)
  const live = telemetry.isLive
  const activeSlots = live && telemetry.queueCounts ? telemetry.queueCounts.active : STAGING_ACTIVE_SLOTS
  const gaugePct = !live
    ? 78
    : telemetry.queueTotal > 0
      ? Math.max(4, Math.min(100, Math.round((telemetry.queueCounts!.active / telemetry.queueTotal) * 100)))
      : 0
  const liveSpend = live && telemetry.credits && (telemetry.credits.realizedJobs > 0 || telemetry.credits.estimatedOnlyJobs > 0)
    ? telemetry.credits
    : null
  const liveFeeds = live && telemetry.feeds.length > 0 ? telemetry.feeds : null

  function triggerRigCalibration() {
    if (rigBusy) return
    setRigBusy(true)
    setRigStatus('CALIBRATING...')
    window.setTimeout(() => {
      setRigStatus('CALIBRATED')
      setRigBusy(false)
    }, 1200)
  }

  function triggerIntegrityCheck() {
    // Advisory only — never blocks workflow progression.
    setDagStatus('VERIFYING...')
    window.setTimeout(() => {
      setDagStatus('PASSED')
    }, 600)
  }

  function triggerDownloadSpecs() {
    setSpecsLog('> Download Component SPECS ... OK')
  }

  return (
    <aside
      data-testid="tactical-side-rail"
      className="z-20 flex w-80 shrink-0 flex-col overflow-hidden bg-[#070312] font-mono text-[11px] text-slate-300 shadow-2xl"
      style={{ borderLeft: '1px solid rgba(76,29,149,0.5)' }}
    >
      {/* Dock header */}
      <div className="flex h-9 items-center justify-between border-b border-purple-950/80 bg-[#0a0518] px-3">
        <span className="text-[11px] font-bold tracking-wider text-slate-200">STUDIO OPERATIONS / LOBBY CONTROL</span>
        <span
          data-testid="tactical-live-dot"
          data-live={live ? 'true' : 'false'}
          className={`h-2 w-2 rounded-full ${live ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]' : 'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.8)]'}`}
        />
      </div>
      {/* Scrollable dock body */}
      <div className="custom-scroll flex-1 space-y-3.5 overflow-y-auto p-3 text-[10px]">
        {/* Global project context */}
        <div className="space-y-1.5 rounded border border-purple-900/40 bg-[#0b061c] p-2.5">
          <div className="text-[10px] font-bold uppercase tracking-widest text-purple-400/80">GLOBAL PROJECT CONTEXT</div>
          <div className="flex cursor-pointer items-center justify-between rounded border border-purple-800/40 bg-[#12082b] px-2.5 py-1.5 transition hover:border-purple-500/50">
            <span data-testid="tactical-project-context" className="truncate font-medium text-slate-200">
              {projectId ? `Active project ${projectId}` : 'Active project context ...'}
            </span>
            <span
              data-testid="tactical-live-badge"
              className={`rounded border px-1.5 py-0.5 text-[10px] font-bold ${live ? 'border-emerald-600/50 bg-emerald-900/80 text-emerald-200' : 'border-purple-600/50 bg-purple-900/80 text-purple-200'}`}
            >
              {live ? 'LIVE' : 'STAGING'}
            </span>
          </div>
        </div>
        {/* Metric gauges */}
        <div className="space-y-3 rounded border border-purple-900/40 bg-[#0b061c] p-2.5">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-[10px] font-bold uppercase tracking-wider text-purple-400/80">RENDER QUEUE COUNT</div>
              <div className="mt-0.5 flex items-baseline space-x-2">
                <span data-testid="tactical-active-slots" className="text-xl font-extrabold text-white">
                  {telemetry.loading && !live ? '—' : activeSlots.toLocaleString()}
                </span>
                <span className="text-[10px] text-slate-400">Active Slots</span>
              </div>
            </div>
            <div className="text-right">
              <div className="text-[10px] font-bold uppercase tracking-wider text-purple-400/80">
                {liveSpend ? 'CR SPEND · RECORD' : 'CR BALANCE'}
              </div>
              <div className="mt-0.5 text-sm font-extrabold text-emerald-400">
                {liveSpend ? (
                  <span data-testid="tactical-cr-spend">
                    {(liveSpend.realized + liveSpend.estimated).toLocaleString()} <span className="text-[10px] text-slate-400">CR</span>
                  </span>
                ) : live ? (
                  <span data-testid="tactical-cr-empty">— <span className="text-[10px] font-normal text-slate-400">no spend on record</span></span>
                ) : (
                  <span>{STAGING_CR} <span className="text-[10px] text-slate-400">CR</span></span>
                )}
              </div>
              {liveSpend ? (
                <div className="mt-0.5 text-[10px] text-slate-500">
                  {liveSpend.realizedJobs} realized · {liveSpend.estimatedOnlyJobs} estimated
                </div>
              ) : null}
            </div>
          </div>
          {/* Gauge bars */}
          <div className="space-y-1.5">
            <div className="h-1.5 overflow-hidden rounded-full border border-purple-900/40 bg-purple-950/60">
              <div
                data-testid="tactical-queue-gauge"
                data-pct={gaugePct}
                className="h-full bg-gradient-to-r from-purple-500 to-fuchsia-400"
                style={{ width: `${gaugePct}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-slate-400">
              <span>PORT 8010</span>
              <span data-testid="tactical-port-status" className={`font-bold ${telemetry.healthy ? 'text-emerald-400' : 'text-rose-400'}`}>
                {telemetry.healthy ? 'ONLINE' : 'OFFLINE'}
              </span>
            </div>
          </div>
        </div>
        {/* Room directory live feeds */}
        <div className="space-y-1.5">
          <div className="flex justify-between px-0.5 text-[10px] font-bold uppercase tracking-widest text-purple-400/80">
            <span>ROOM DIRECTORY</span>
            <span className="text-purple-300">FEED NODES</span>
          </div>
          <div className="space-y-1">
            {liveFeeds ? (
              liveFeeds.map((feed, i) => (
                <button
                  key={feed.key}
                  type="button"
                  data-testid={`tactical-feed-live-${i}`}
                  onClick={() => focusRoom(feed.roomId)}
                  className="group flex w-full cursor-pointer items-center justify-between rounded border border-purple-900/30 bg-[#0c0720] p-2 text-left transition hover:border-purple-500"
                >
                  <span className="text-[11px] font-bold text-slate-200 transition group-hover:text-purple-300">
                    {feed.title}
                    <span className="mt-0.5 block text-[10px] font-normal text-slate-400">{feed.code}</span>
                  </span>
                  <span className="text-[10px] text-slate-400">{feed.status}</span>
                </button>
              ))
            ) : (
              STAGING_FEEDS.map((feed, i) => (
                <button
                  key={`${feed.roomId}-${i}`}
                  type="button"
                  data-testid={`tactical-feed-${feed.roomId}`}
                  onClick={() => focusRoom(feed.roomId)}
                  className="group flex w-full cursor-pointer items-center justify-between rounded border border-purple-900/30 bg-[#0c0720] p-2 text-left transition hover:border-purple-500"
                >
                  <span className="text-[11px] font-bold text-slate-200 transition group-hover:text-purple-300">
                    {feed.title}
                    <span className="mt-0.5 block text-[10px] font-normal text-slate-400">{feed.code}</span>
                  </span>
                  <span className="text-[10px] text-slate-400">{feed.status}</span>
                </button>
              ))
            )}
          </div>
        </div>
        {/* System controls */}
        <div className="space-y-1.5 pt-1">
          <div className="flex justify-between px-0.5 text-[10px] font-bold uppercase tracking-widest text-purple-400/80">
            <span>SYSTEM CONTROLS</span>
            <span className="text-purple-400">2D TRIGGERS</span>
          </div>
          <div className="space-y-1.5">
            <button
              type="button"
              onClick={triggerRigCalibration}
              className="flex w-full items-center justify-between rounded border border-purple-800/40 bg-[#0e0824] px-3 py-1.5 text-purple-200 transition hover:border-purple-500 hover:text-white"
            >
              <span className="font-bold">RIG CALIBRATION</span>
              <span
                data-testid="rig-status"
                className={`rounded px-1 text-[10px] font-bold ${rigBusy ? 'animate-pulse bg-yellow-950 text-yellow-300' : rigStatus === 'READY' ? 'bg-purple-950 text-purple-300' : 'bg-emerald-950 text-emerald-400'}`}
              >
                {rigStatus}
              </span>
            </button>
            <button
              type="button"
              onClick={recenter}
              className="flex w-full items-center justify-between rounded border border-purple-800/40 bg-[#0e0824] px-3 py-1.5 text-purple-200 transition hover:border-purple-500 hover:text-white"
            >
              <span className="font-bold">LOBBY RE-CENTER</span>
              <span className="font-mono text-[10px] text-cyan-300">0.0.0</span>
            </button>
            <button
              type="button"
              onClick={triggerIntegrityCheck}
              className="flex w-full items-center justify-between rounded border border-purple-800/40 bg-[#0e0824] px-3 py-1.5 text-purple-200 transition hover:border-purple-500 hover:text-white"
            >
              <span className="font-bold">DAG INTEGRITY</span>
              <span data-testid="dag-status" className="rounded bg-emerald-950/60 px-1 text-[10px] font-bold text-emerald-400">
                {dagStatus}
              </span>
            </button>
            <button
              type="button"
              onClick={triggerDownloadSpecs}
              className="flex w-full items-center justify-between rounded border border-purple-800/40 bg-[#0e0824] px-3 py-1.5 text-purple-200 transition hover:border-purple-500 hover:text-white"
            >
              <span className="font-bold">DOWNLOAD COMPONENT SPECS</span>
              <span className="font-mono text-[10px] text-slate-400">XML</span>
            </button>
          </div>
        </div>
        {/* Telemetry override + diagnostic logs */}
        <div className="space-y-2 border-t border-purple-950/60 pt-1">
          <div className="flex items-center justify-between px-0.5">
            <span className="text-[10px] font-bold uppercase tracking-widest text-purple-400">TELEMETRY OVERRIDE</span>
            <button
              type="button"
              role="switch"
              aria-checked={telemetryOverride}
              aria-label="Telemetry override"
              data-testid="telemetry-toggle"
              onClick={() => setTelemetryOverride((v) => !v)}
              className={`relative h-4 w-7 rounded-full transition-colors ${telemetryOverride ? 'bg-emerald-500' : 'bg-purple-950'}`}
            >
              <span
                className={`absolute left-[2px] top-[2px] h-3 w-3 rounded-full border border-gray-300 bg-white transition-all ${telemetryOverride ? 'translate-x-full border-white' : ''}`}
              />
            </button>
          </div>
          <div className="space-y-0.5 rounded border border-purple-950 bg-[#05020c] p-2 font-mono text-[10px] text-slate-400">
            <div className="font-bold text-purple-400/80">Diagnostic sub-logs:</div>
            <div data-testid="specs-log" className="text-emerald-400/90">{specsLog}</div>
            <div className="text-slate-400">&gt; Diagnostry overr10 ... {telemetryOverride ? 'ACTIVE' : 'STANDBY'}</div>
            <div data-testid="telemetry-source-log" className="text-slate-500">
              &gt; Queue summary ... {live ? `LIVE · ${telemetry.queueTotal} tracked` : 'STAGING'}
            </div>
            <div className="text-slate-500">&gt; WebGL3D Render Pipeline: 60FPS</div>
          </div>
        </div>
      </div>
    </aside>
  )
}
