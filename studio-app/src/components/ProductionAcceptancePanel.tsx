import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, ShieldCheck } from 'lucide-react'
import {
  runProductionAcceptance,
  type FinalShortFilmPackage,
  type ProductionAcceptanceReport,
} from '../lib/studioApi'

type ProductionAcceptancePanelProps = {
  projectId: string
  finalPackage: FinalShortFilmPackage | null
  report: ProductionAcceptanceReport | null
  onReport: (report: ProductionAcceptanceReport) => void
  loading: boolean
  setLoading: (loading: boolean) => void
  error: string
  setError: (error: string) => void
}

const dispositionCopy: Record<string, { label: string; tone: string }> = {
  ready_for_creator_approval: { label: 'Ready for creator approval', tone: 'text-emerald-300 border-emerald-400/30 bg-emerald-500/10' },
  needs_attention: { label: 'Needs attention', tone: 'text-amber-300 border-amber-400/30 bg-amber-500/10' },
  blocked: { label: 'Blocked', tone: 'text-rose-300 border-rose-400/30 bg-rose-500/10' },
  insufficient_data: { label: 'Insufficient data', tone: 'text-zinc-300 border-zinc-500/30 bg-zinc-500/10' },
}

function severityClass(severity: string) {
  if (severity === 'blocker') return 'border-rose-400/30 bg-rose-500/10 text-rose-200'
  if (severity === 'warning') return 'border-amber-400/30 bg-amber-500/10 text-amber-200'
  if (severity === 'pass') return 'border-emerald-400/25 bg-emerald-500/10 text-emerald-200'
  return 'border-white/10 bg-white/5 text-zinc-300'
}

export default function ProductionAcceptancePanel({
  projectId,
  finalPackage,
  report,
  onReport,
  loading,
  setLoading,
  error,
  setError,
}: ProductionAcceptancePanelProps) {
  async function handleRunAcceptance() {
    if (!projectId) return
    setLoading(true)
    setError('')
    try {
      const result = await runProductionAcceptance(projectId, {
        package_id: finalPackage?.package_id,
        include_advisory_checks: true,
        strict: true,
        metadata: { requested_from: 'screening_room' },
      })
      onReport(result.report)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Production acceptance could not complete.')
    } finally {
      setLoading(false)
    }
  }

  const blockers = report?.checks.filter((check) => check.severity === 'blocker') ?? []
  const warnings = report?.checks.filter((check) => check.severity === 'warning') ?? []
  const headline = report
    ? dispositionCopy[report.stale ? 'needs_attention' : report.disposition] ?? dispositionCopy.needs_attention
    : { label: 'Not run', tone: 'text-zinc-300 border-white/10 bg-white/5' }

  return (
    <section className="rounded-xl border border-white/10 bg-black/30 p-4" data-testid="production-acceptance-panel">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.16em] text-cyan-200">
            <ShieldCheck size={14} />
            Production Acceptance
          </div>
          <div className={`mt-3 inline-flex rounded-md border px-2.5 py-1 text-xs font-semibold ${headline.tone}`}>
            {report?.stale ? 'Stale acceptance' : headline.label}
          </div>
        </div>
        <button
          type="button"
          onClick={handleRunAcceptance}
          disabled={loading || !projectId}
          className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-3 py-2 text-xs font-bold uppercase tracking-[0.12em] text-cyan-100 transition hover:bg-cyan-500/20 disabled:opacity-50"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          {report ? 'Re-run' : 'Run'}
        </button>
      </div>

      {error ? (
        <div className="mt-3 rounded-md border border-rose-400/30 bg-rose-500/10 p-3 text-xs text-rose-200">
          {error}
        </div>
      ) : null}

      {!report ? (
        <p className="mt-3 text-sm leading-relaxed text-zinc-400">
          Verify the final package before approval. The studio will inspect package integrity, media availability, lineage, review state, revisions, and Studio Brain findings.
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          <p className="text-sm leading-relaxed text-zinc-200">{report.co_director_note || report.summary}</p>
          {report.stale && report.stale_reasons.length > 0 ? (
            <div className="rounded-md border border-amber-400/30 bg-amber-500/10 p-3 text-xs text-amber-100">
              {report.stale_reasons[0]}
            </div>
          ) : null}
          <div className="grid grid-cols-2 gap-2 text-xs text-zinc-300">
            <div className="rounded-md border border-white/10 bg-white/5 p-2">
              <div className="text-zinc-500">Blockers</div>
              <div className="mt-1 text-zinc-100">{blockers.length}</div>
            </div>
            <div className="rounded-md border border-white/10 bg-white/5 p-2">
              <div className="text-zinc-500">Warnings</div>
              <div className="mt-1 text-zinc-100">{warnings.length}</div>
            </div>
          </div>
          <div className="space-y-2">
            {report.checks
              .filter((check) => check.severity === 'blocker' || check.severity === 'warning')
              .slice(0, 4)
              .map((check) => (
                <div key={check.check_id} className={`rounded-md border p-3 text-xs ${severityClass(check.severity)}`}>
                  <div className="flex items-center gap-2 font-semibold">
                    {check.severity === 'blocker' ? <AlertTriangle size={13} /> : <CheckCircle2 size={13} />}
                    {check.title}
                  </div>
                  <div className="mt-1 text-zinc-300">{check.summary}</div>
                  {check.remediation[0] ? <div className="mt-2 text-zinc-400">{check.remediation[0]}</div> : null}
                </div>
              ))}
          </div>
        </div>
      )}
    </section>
  )
}
