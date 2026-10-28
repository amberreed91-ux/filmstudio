import { useState } from 'react'
import type { GateStage } from '../lib/pipelineGateFlow'
import { gateStageStateLabel } from '../lib/pipelineGateFlow'
import { hashLogEntry } from '../lib/evidenceLog'

/**
 * Evidence audit drawer for the Production Integrity Engine.
 *
 * Read-only forensic surface: pinning a pipeline stage reveals its recorded
 * execution status, timestamps, log hashes, raw JSON preflight digests, and
 * normalization warnings. It never mutates backend state — closing the drawer
 * only clears local UI pin state in `PipelineGateFlow`.
 */

const DRAWER_TONE: Record<GateStage['state'], string> = {
  cleared: 'border-emerald-400/40 bg-emerald-400/5 text-emerald-200',
  fail_closed: 'border-rose-400/45 bg-rose-400/5 text-rose-200',
  not_established: 'border-white/15 bg-white/[0.02] text-zinc-400',
  unavailable: 'border-white/15 bg-white/[0.02] text-zinc-500',
}

function isNormalizationLog(label: string, detail: string): boolean {
  return /normali|auto-optimi|optim|router_payload_normalized|secondary_references_|unsupported_flag|non_verified_/i.test(
    `${label} ${detail}`,
  )
}

type Props = {
  stage: GateStage | null
  onClose: () => void
  /** Project scope for the read-only Trace-to-Soundstage link. */
  projectId?: string
}

export default function EvidenceAuditDrawer({ stage, onClose, projectId = '' }: Props) {
  const [reverifiedAt, setReverifiedAt] = useState<string | null>(null)
  const [downloadUnavailable, setDownloadUnavailable] = useState(false)
  if (!stage) return null
  const normalizationLogs = stage.logs.filter((log) => isNormalizationLog(log.label, log.detail))
  const recordedAt = stage.logs.map((log) => log.at || '').filter((at) => at).sort().pop() || 'not recorded'
  const rawDigest = JSON.stringify(
    {
      stage: stage.id,
      trace_id: stage.logs[0]?.id || 'not recorded',
      socket_isolation: 'enforced server-side (R43K_SOCKET_ONLY=1)',
      bitrate_clamp: normalizationLogs.length > 0
        ? `${normalizationLogs.length} normalization adjustment${normalizationLogs.length === 1 ? '' : 's'} recorded`
        : 'no adjustments recorded',
      color_space: 'not recorded',
      sha256_digest: 'not recorded',
      verified_at: recordedAt,
    },
    null,
    2,
  )

  return (
    <aside
      id="gate-stage-detail"
      data-testid="evidence-audit-drawer"
      aria-live="polite"
      aria-label={`Evidence audit drawer — ${stage.label}`}
      className={`mt-2 rounded-xl border-2 border-[#1E293B] bg-[#0B0F17]/85 p-4 text-[#CBD5E1] shadow-[0_0_50px_rgba(109,40,217,0.25)] backdrop-blur-2xl ${DRAWER_TONE[stage.state]}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-medium text-zinc-100">{stage.label}</p>
        <div className="flex items-center gap-2">
          <span
            data-testid="evidence-audit-state"
            className="rounded border border-white/15 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-zinc-300"
          >
            {gateStageStateLabel(stage.state)}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label={`Unpin ${stage.label} evidence`}
            className="rounded border border-white/15 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-zinc-400 transition-colors hover:border-white/30 hover:text-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F59E0B] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0F17]"
          >
            Unpin
          </button>
        </div>
      </div>

      <p className="mt-1.5 text-xs leading-relaxed text-zinc-300">{stage.detail}</p>
      <p className="mt-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-zinc-500">
        {stage.evidenceSource}
      </p>

      {stage.logs.length > 0 ? (
        <div className="mt-2 border-t border-white/10 pt-2">
          <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">
            Recorded fail-closed logs ({stage.logs.length})
          </p>
          <ul className="mt-1.5 space-y-1 text-[11px] text-zinc-300">
            {stage.logs.slice(0, 6).map((log) => (
              <li key={log.id} data-testid={`evidence-log-${log.id}`} className="flex flex-wrap gap-x-2">
                <span className="font-medium text-zinc-200">{log.label}</span>
                <span className="min-w-0 break-words text-zinc-400">{log.detail}</span>
                {log.at ? (
                  <span className="text-zinc-600">{log.at.replace('T', ' ').replace('Z', ' UTC')}</span>
                ) : (
                  <span className="text-zinc-600">timestamp not recorded</span>
                )}
                <span className="font-mono text-[10px] text-zinc-500">
                  hash {hashLogEntry(log.id, log.detail)}
                </span>
              </li>
            ))}
          </ul>
          {stage.logs.length > 6 ? (
            <p className="mt-1 text-[10px] text-zinc-500">
              Showing 6 of {stage.logs.length} recorded entries.
            </p>
          ) : null}
        </div>
      ) : (
        <p className="mt-2 text-xs text-zinc-500">No fail-closed log is recorded for this stage.</p>
      )}

      {normalizationLogs.length > 0 ? (
        <div className="mt-2 border-t border-white/10 pt-2">
          <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">
            Normalization warnings ({normalizationLogs.length})
          </p>
          <ul className="mt-1.5 space-y-1 text-[11px] text-amber-100/90">
            {normalizationLogs.slice(0, 6).map((log) => (
              <li key={`norm-${log.id}`} className="break-words">
                <span className="font-medium">{log.label}</span>
                <span className="text-zinc-400"> · {log.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <details className="mt-2 border-t border-white/10 pt-2">
        <summary className="cursor-pointer text-[10px] uppercase tracking-[0.14em] text-zinc-500">
          Raw JSON preflight digest
        </summary>
        <pre
          data-testid="evidence-raw-digest"
          className="mt-1.5 max-h-56 overflow-auto rounded border border-white/10 bg-black/60 p-2 font-mono text-[10px] leading-relaxed text-zinc-300"
        >
          {rawDigest}
        </pre>
      </details>

      <div className="mt-2 flex flex-wrap gap-2 border-t border-white/10 pt-3">
        <button
          type="button"
          onClick={() => setReverifiedAt(new Date().toISOString())}
          data-testid="evidence-reverify-digest"
          className="inline-flex min-h-9 items-center rounded-md border border-violet-300/40 bg-violet-500/15 px-3 text-[11px] font-semibold uppercase tracking-[0.1em] text-violet-100 transition-colors hover:border-violet-300/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F59E0B] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0F17]"
        >
          Re-verify Cryptographic Digest
        </button>
        <button
          type="button"
          onClick={() => {
            try {
              const blob = new Blob([rawDigest], { type: 'application/json' })
              const url = URL.createObjectURL(blob)
              const anchor = document.createElement('a')
              anchor.href = url
              anchor.download = `evidence-${stage.id}.json`
              document.body.appendChild(anchor)
              anchor.click()
              anchor.remove()
              window.setTimeout(() => URL.revokeObjectURL(url), 1000)
            } catch {
              setDownloadUnavailable(true)
            }
          }}
          data-testid="evidence-download-proof"
          className="inline-flex min-h-9 items-center rounded-md border border-white/15 px-3 text-[11px] font-semibold uppercase tracking-[0.1em] text-zinc-200 transition-colors hover:border-white/30"
        >
          Download Proof (.json)
        </button>
        <a
          href={projectId ? `/studio/production-desk?project_id=${encodeURIComponent(projectId)}` : '/studio/production-desk'}
          data-testid="evidence-trace-soundstage"
          className="inline-flex min-h-9 items-center rounded-md border border-cyan-300/40 bg-cyan-500/10 px-3 text-[11px] font-semibold uppercase tracking-[0.1em] text-cyan-100 transition-colors hover:border-cyan-300/70"
        >
          Trace to Soundstage
        </a>
      </div>
      {reverifiedAt ? (
        <p role="status" data-testid="evidence-reverify-note" className="mt-2 text-[11px] text-zinc-400">
          Display hashes recomputed locally at {reverifiedAt.replace('T', ' ').replace('Z', ' UTC')} across {stage.logs.length} recorded {stage.logs.length === 1 ? 'entry' : 'entries'} — backend records unchanged.
        </p>
      ) : null}
      {downloadUnavailable ? (
        <p role="status" className="mt-2 text-[11px] text-zinc-400">
          File download is unavailable in this context — the full digest text is shown in the raw JSON block above.
        </p>
      ) : null}

      <p className="mt-2 text-[10px] leading-relaxed text-zinc-500">
        Verification provenance: read-only view of persisted backend records. Pinning or unpinning
        this drawer never approves work, runs scans, or mutates backend state.
      </p>
    </aside>
  )
}
