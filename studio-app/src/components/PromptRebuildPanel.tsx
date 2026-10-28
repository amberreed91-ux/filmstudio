// Phase 1: explicit prompt Rebuild for one board version.
//
// - Rebuilding an approved version mints exactly one new draft and leaves the
//   approved version untouched; rebuilding a draft updates it in place.
// - Shots without a stored builder hash are never overwritten silently: they
//   appear with a before/after diff and an unticked per-shot confirm.
// - Hand-edited shots are skipped; empty locked blocks refuse loudly.
// - Reference-lock rows are shown as information only (the prompt source is
//   the look approval, not the reference lock).
import { useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, Hammer, Loader2 } from 'lucide-react'
import {
  rebuildShotPrompts,
  type PromptRebuildConfirmItem,
  type PromptRebuildSummary,
  type StoryboardShot,
} from '../lib/studioApi'

type Props = {
  blueprintId: string
  versionId: string | null
  versionStatus: string | null
  shots: StoryboardShot[]
  disabled?: boolean
  onChanged: () => void
}

function shotNumberOf(shots: StoryboardShot[], shotId: string): string {
  const found = shots.find((shot) => shot.shot_id === shotId)
  return found ? `Shot ${found.shot_number}` : shotId
}

function ConfirmDiff({ item, shotLabel }: { item: PromptRebuildConfirmItem; shotLabel: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-md border border-white/10 p-2">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        data-testid={`rebuild-diff-toggle-${item.shot_id}`}
        className="w-full text-left text-[11px] font-medium text-zinc-200 hover:text-amber-100"
      >
        {shotLabel} · stored text cannot be proven machine-built {open ? '▾' : '▸'}
      </button>
      {open && (
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-500">Before</p>
            <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap rounded bg-zinc-950 p-2 text-xs leading-relaxed text-zinc-300">{item.before}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-500">After</p>
            <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap rounded bg-zinc-950 p-2 text-xs leading-relaxed text-zinc-300">{item.after}</p>
          </div>
        </div>
      )}
    </div>
  )
}

export default function PromptRebuildPanel({ blueprintId, versionId, versionStatus, shots, disabled, onChanged }: Props) {
  const [summary, setSummary] = useState<PromptRebuildSummary | null>(null)
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const confirmedIds = useMemo(
    () => Object.entries(confirmed).filter(([, value]) => value).map(([shotId]) => shotId),
    [confirmed],
  )

  async function run(confirmedShotIds: string[]) {
    if (!versionId) return
    setBusy(true)
    setError('')
    try {
      const result = await rebuildShotPrompts(blueprintId, versionId, confirmedShotIds)
      setSummary(result)
      setConfirmed({})
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Prompt rebuild failed')
    } finally {
      setBusy(false)
    }
  }

  if (!versionId) return null
  const approved = versionStatus === 'approved'

  return (
    <div className="space-y-2 rounded-lg border border-white/10 bg-white/[0.025] p-3" data-testid="prompt-rebuild-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium text-zinc-100">Rebuild shot prompts</p>
        <button
          type="button"
          onClick={() => void run([])}
          disabled={disabled || busy}
          aria-busy={busy}
          data-testid="prompt-rebuild-run"
          className="flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-1.5 text-[11px] text-zinc-200 hover:bg-white/5 disabled:opacity-40"
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Hammer size={13} />}
          Rebuild with the current builder
        </button>
      </div>
      <p className="text-[11px] leading-relaxed text-zinc-400">
        {approved
          ? 'This version is approved, so rebuilding mints exactly one new draft — the approved version is never touched.'
          : 'This version is a draft, so rebuilding updates its shots in place — no new version.'}
        {' '}Only the canonical board text changes; cameras, coverage, and structured parameters are preserved.
      </p>
      {error && <p className="text-xs leading-relaxed text-rose-300" role="alert">{error}</p>}
      {summary && (
        <div className="space-y-2" data-testid="prompt-rebuild-summary">
          {summary.cloned_from_version_id && (
            <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-emerald-200">
              <CheckCircle2 size={13} className="mt-0.5 shrink-0" />
              New draft version created — re-run continuity review and approve it before rendering.
            </p>
          )}
          {summary.rebuilt.length > 0 && (
            <ul className="space-y-1">
              {summary.rebuilt.map((item) => (
                <li key={item.shot_id} className="flex items-start gap-1.5 text-xs leading-relaxed text-zinc-300">
                  <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-emerald-300" />
                  <span>
                    {shotNumberOf(shots, item.shot_id)} rebuilt
                    {item.block_characters.length > 0 ? ` · locked block: ${item.block_characters.join(', ')}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {summary.skipped_hand_edited.length > 0 && (
            <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-zinc-300">
              <AlertTriangle size={13} className="mt-0.5 shrink-0 text-amber-200" />
              Skipped hand-edited (left exactly as the creator wrote{' '}
              {summary.skipped_hand_edited.map((shotId) => shotNumberOf(shots, shotId)).join(', ')}).
            </p>
          )}
          {summary.refused_empty_block.length > 0 && (
            <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-rose-200" role="alert">
              <AlertTriangle size={13} className="mt-0.5 shrink-0" />
              Refused — no locked character is named for{' '}
              {summary.refused_empty_block.map((shotId) => shotNumberOf(shots, shotId)).join(', ')}. Nothing was written.
            </p>
          )}
          {summary.confirm_required.length > 0 && (
            <div className="space-y-2">
              <p className="text-[11px] font-medium leading-relaxed text-amber-100">
                These shots have no stored builder record, so rebuilding needs an explicit tick per shot. Nothing below is overwritten until you confirm it.
              </p>
              {summary.confirm_required.map((item) => (
                <div key={item.shot_id} className="space-y-1">
                  <label className="flex cursor-pointer items-start gap-2 text-[11px] leading-relaxed text-zinc-200">
                    <input
                      type="checkbox"
                      checked={Boolean(confirmed[item.shot_id])}
                      onChange={(event) => setConfirmed((prev) => ({ ...prev, [item.shot_id]: event.target.checked }))}
                      disabled={disabled || busy}
                      data-testid={`rebuild-confirm-${item.shot_id}`}
                      className="mt-0.5"
                    />
                    <span>Rebuild {shotNumberOf(shots, item.shot_id)} — I reviewed the diff below.</span>
                  </label>
                  <ConfirmDiff item={item} shotLabel={shotNumberOf(shots, item.shot_id)} />
                </div>
              ))}
              <button
                type="button"
                onClick={() => void run(confirmedIds)}
                disabled={disabled || busy || confirmedIds.length === 0}
                aria-busy={busy}
                data-testid="prompt-rebuild-confirmed"
                className="flex items-center gap-1.5 rounded-md border border-amber-200/40 px-3 py-1.5 text-[11px] font-medium text-amber-100 hover:bg-amber-200/10 disabled:opacity-40"
              >
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Hammer size={13} />}
                Rebuild {confirmedIds.length} confirmed shot{confirmedIds.length === 1 ? '' : 's'}
              </button>
            </div>
          )}
          {summary.reference_lock_info.length > 0 && (
            <p className="text-[11px] leading-relaxed text-zinc-500">
              Reference locks on file (information only — the prompt source is the look approval):{' '}
              {summary.reference_lock_info
                .map((row) => `${row.character_name || row.character_id || 'unknown'} (${row.lock_status || 'unknown'})`)
                .join(', ')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
