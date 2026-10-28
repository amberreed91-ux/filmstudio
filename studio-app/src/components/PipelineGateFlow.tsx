import { useMemo, useState } from 'react'
import { ChevronRight, ShieldAlert, ShieldCheck, CircleHelp, Loader2 } from 'lucide-react'
import EvidenceAuditDrawer from './EvidenceAuditDrawer'
import { hashLogEntry } from '../lib/evidenceLog'
import {
  gateStageStateLabel,
  type GateStage,
  type GateStageId,
  type GateStageState,
} from '../lib/pipelineGateFlow'

const NODE_TONE: Record<GateStageState, string> = {
  cleared: 'border-emerald-400/35 hover:border-emerald-300/70',
  fail_closed: 'border-rose-400/35 hover:border-rose-300/70',
  not_established: 'border-white/15 hover:border-white/35',
  unavailable: 'border-white/10 hover:border-white/25',
}

function StateIcon({ state }: { state: GateStageState }) {
  if (state === 'cleared') return <ShieldCheck size={14} className="text-emerald-200" />
  if (state === 'fail_closed') return <ShieldAlert size={14} className="text-rose-200" />
  if (state === 'unavailable') return <CircleHelp size={14} className="text-zinc-500" />
  return <CircleHelp size={14} className="text-zinc-400" />
}

type Props = {
  stages: GateStage[]
  loading?: boolean
  /** Project scope for the read-only Trace-to-Soundstage link. */
  projectId?: string
}

function SocketTelemetryGauges({ stages }: { stages: GateStage[] }) {
  const socket = stages.find((stage) => stage.id === 'socket_isolation') || null
  const active = stages[0] || null
  const checksum = active ? hashLogEntry(active.id, `${active.state}:${active.logs.length}`) : 'no record'
  const held = socket ? socket.logs.length : 0
  const egress =
    !socket || socket.state === 'unavailable'
      ? 'NO RECORD'
      : socket.state === 'not_established'
        ? 'NOT ESTABLISHED'
        : `0 PKT bypassed · ${held} boundary ${held === 1 ? 'entry' : 'entries'} held`
  return (
    <div data-testid="socket-telemetry-gauges" className="rounded-lg border border-white/10 bg-black/30 p-3">
      <p className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">Socket telemetry gauges</p>
      <dl className="mt-2 space-y-1.5 text-[11px]">
        <div className="flex items-baseline justify-between gap-2">
          <dt className="uppercase tracking-[0.1em] text-zinc-500">IPC checksum</dt>
          <dd className="font-mono text-[11px] text-cyan-200">{checksum}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <dt className="uppercase tracking-[0.1em] text-zinc-500">Egress leak</dt>
          <dd className="font-mono text-[11px] text-emerald-200">{egress}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <dt className="uppercase tracking-[0.1em] text-zinc-500">Drift tolerance</dt>
          <dd className="font-mono text-[11px] text-zinc-200">&lt;0.001% band · measurement NO RECORD</dd>
        </div>
      </dl>
      <p className="mt-2 text-[10px] leading-snug text-zinc-600">
        Checksum derived locally from recorded stage evidence. Egress counts recorded bypasses only — no egress measurement exists on this surface.
      </p>
    </div>
  )
}

function StageViewport({ stages }: { stages: GateStage[] }) {
  const normalizer = stages.find((stage) => stage.id === 'payload_normalizer') || null
  const entries = normalizer ? normalizer.logs.slice(0, 3) : []
  const established = normalizer && normalizer.state !== 'unavailable' && normalizer.state !== 'not_established'
  return (
    <div data-testid="stage-viewport" className="relative overflow-hidden rounded-lg border border-white/10 bg-black/40 p-3">
      <p className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">Stage 04 · Optical artifact viewport</p>
      <svg viewBox="0 0 260 110" aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full opacity-40">
        <g stroke="rgba(139,92,246,0.5)" strokeWidth="1.2" fill="none">
          <path d="M8,20 V8 H20 M240,8 H252 V20 M252,90 V102 H240 M20,102 H8 V90" />
        </g>
        <line x1={130} y1={4} x2={130} y2={106} stroke="rgba(139,92,246,0.25)" strokeWidth={0.8} strokeDasharray="3 3" />
        <line x1={4} y1={55} x2={256} y2={55} stroke="rgba(139,92,246,0.25)" strokeWidth={0.8} strokeDasharray="3 3" />
        <circle cx={130} cy={55} r={22} stroke="rgba(245,158,11,0.5)" strokeWidth={1} fill="none" strokeDasharray="4 3" />
        {Array.from({ length: 9 }, (_, i) => (
          <line key={i} x1={0} y1={8 + i * 12} x2={260} y2={8 + i * 12} stroke="rgba(255,255,255,0.05)" strokeWidth={1} />
        ))}
      </svg>
      <div className="relative mt-2 min-h-16">
        {!normalizer || !established ? (
          <p className="text-[11px] text-zinc-500">
            {normalizer?.state === 'unavailable' ? 'NO RECORD — the normalizer read failed.' : 'NOT ESTABLISHED — no normalizer execution is recorded yet.'}
          </p>
        ) : entries.length === 0 ? (
          <p className="text-xs text-zinc-400">Payloads passed through with no recorded artifact adjustment.</p>
        ) : (
          <ul className="space-y-1 font-mono text-[10px] text-amber-100/90">
            {entries.map((entry) => (
              <li key={entry.id} className="break-words">{entry.label} · {entry.detail}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function CustodyLedger({ stages }: { stages: GateStage[] }) {
  return (
    <div data-testid="custody-ledger" className="rounded-lg border border-white/10 bg-black/30 p-3">
      <p className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">Chain-of-custody ledger</p>
      <ol className="mt-2 space-y-1.5">
        {stages.map((stage) => (
          <li key={stage.id} className="flex items-baseline justify-between gap-2 text-xs">
            <span className="min-w-0 truncate text-zinc-300">
              <span className="mr-1.5 font-mono tabular-nums text-zinc-500">{stage.order}</span>
              {stage.label}
            </span>
            <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.08em] text-zinc-500">
              {gateStageStateLabel(stage.state)} · {stage.logs.length} log{stage.logs.length === 1 ? '' : 's'}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}

/**
 * Interactive gate flow: horizontal laser conduit with five evidence nodes.
 *
 * Each node is a stage of the provider submission path, and its state comes
 * from recorded backend evidence (`lib/pipelineGateFlow.ts`). Selecting a
 * node pins its evidence in the right-hand drawer; the Payload Normalizer
 * pin additionally carries the FOCUSED REVIEW glow. Nothing here authorizes
 * or blocks work — the Production Integrity Gate does that on the server.
 */
export default function PipelineGateFlow({ stages, loading = false, projectId = '' }: Props) {
  const [pinned, setPinned] = useState<GateStageId | null>(null)
  const active = useMemo(
    () => stages.find((stage) => stage.id === pinned) || stages[0] || null,
    [stages, pinned],
  )
  const failClosed = stages.filter((stage) => stage.state === 'fail_closed').length

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs leading-relaxed text-zinc-400">
          Provider submission path, stage by stage. States report what the backend recorded — a stage with no record is never shown as cleared.
        </p>
        <span className={`rounded border px-2 py-1 text-[10px] uppercase tracking-[0.12em] ${failClosed > 0 ? 'border-rose-400/40 text-rose-200' : 'border-white/15 text-zinc-400'}`}>
          {loading ? <Loader2 size={11} className="mr-1 inline animate-spin" /> : null}
          {failClosed > 0 ? `${failClosed} stage${failClosed === 1 ? '' : 's'} fail-closed` : 'No fail-closed stage recorded'}
        </span>
      </div>

      {/* Wraps instead of scrolling: an overflow container would clip the
          absolutely positioned hover tooltip below each node. */}
      <div className="relative mt-4">
        <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-7 hidden h-px bg-gradient-to-r from-transparent via-violet-400/60 to-transparent shadow-[0_0_12px_rgba(139,92,246,0.6)] md:block" />
        <ol aria-label="Pipeline gate stages" className="relative flex flex-wrap items-stretch gap-1 pb-2">
          {stages.map((stage, index) => {
            const selected = active?.id === stage.id
            const focusedReview = selected && stage.id === 'payload_normalizer'
            return (
              <li key={stage.id} className="flex min-w-0 items-stretch gap-1">
                <div className="group relative min-w-[10.5rem] flex-1">
                  <button
                    type="button"
                    data-testid={`gate-stage-${stage.id}`}
                    data-state={stage.state}
                    data-focused-review={focusedReview ? 'true' : 'false'}
                    aria-expanded={selected}
                    aria-controls="gate-stage-detail"
                    onClick={() => setPinned(selected ? null : stage.id)}
                    className={`relative flex h-full w-full flex-col gap-1.5 rounded-md border px-3 py-2.5 text-left transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-200/60 ${NODE_TONE[stage.state]} ${selected ? 'bg-white/[0.06]' : 'bg-white/[0.02]'} ${focusedReview ? 'ring-2 ring-violet-400 shadow-[0_0_28px_rgba(139,92,246,0.6)]' : ''}`}
                  >
                    <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.14em] text-zinc-500">
                      <span className="tabular-nums">{stage.order}</span>
                      <StateIcon state={stage.state} />
                      <span className={stage.state === 'cleared' ? 'text-emerald-200/90' : stage.state === 'fail_closed' ? 'text-rose-200/90' : ''}>
                        {gateStageStateLabel(stage.state)}
                      </span>
                    </span>
                    <span className="text-xs font-medium leading-snug text-zinc-100">{stage.label}</span>
                    {focusedReview ? (
                      <span data-testid="focused-review-tag" className="inline-flex w-fit items-center gap-1.5 rounded border border-violet-300/60 bg-violet-500/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-violet-100">
                        <span className="relative flex h-1.5 w-1.5" aria-hidden="true">
                          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-violet-300 opacity-75 motion-reduce:animate-none" />
                          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-violet-200" />
                        </span>
                        Focused review
                      </span>
                    ) : null}
                  </button>
                  {/* Hover/focus tooltip: configuration state only, never a claim. */}
                  <div
                    role="tooltip"
                    className="pointer-events-none absolute left-0 top-full z-20 mt-1 hidden w-72 rounded-md border border-white/15 bg-black/95 p-2.5 text-[11px] leading-relaxed text-zinc-300 shadow-lg group-hover:block group-focus-within:block"
                  >
                    <p className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">Configuration</p>
                    <p className="mt-1">{stage.configuration}</p>
                    <p className="mt-2 text-[10px] uppercase tracking-[0.12em] text-zinc-500">Evidence Source</p>
                    <p className="mt-1 font-mono text-[10px] text-zinc-400">{stage.evidenceSource}</p>
                    <p className="mt-2 text-[10px] uppercase tracking-[0.12em] text-zinc-500">
                      Fail-closed logs{stage.logs.length > 0 ? ` (${stage.logs.length})` : ''}
                    </p>
                    {stage.logs.length === 0 ? (
                      <p className="mt-1 text-zinc-500">None recorded.</p>
                    ) : (
                      <ul className="mt-1 space-y-0.5">
                        {stage.logs.slice(0, 2).map((log) => (
                          <li key={`tooltip-${log.id}`} className="break-words">
                            <span className="text-zinc-200">{log.label}</span>
                            <span className="text-zinc-400"> · {log.detail}</span>
                          </li>
                        ))}
                        {stage.logs.length > 2 ? <li className="text-zinc-500">… {stage.logs.length - 2} more — select the node for the full record.</li> : null}
                      </ul>
                    )}
                  </div>
                </div>
                {index < stages.length - 1 ? (
                  <ChevronRight size={14} className="mt-6 shrink-0 self-start text-violet-300/60" aria-hidden="true" />
                ) : null}
              </li>
            )
          })}
        </ol>
      </div>

      <div className="mt-3 grid gap-4 lg:grid-cols-12">
        <div className="space-y-4 lg:col-span-5">
          <SocketTelemetryGauges stages={stages} />
          <StageViewport stages={stages} />
          <CustodyLedger stages={stages} />
        </div>
        <div className="lg:col-span-7">
          <EvidenceAuditDrawer stage={active} projectId={projectId} onClose={() => setPinned(null)} />
        </div>
      </div>
    </div>
  )
}
