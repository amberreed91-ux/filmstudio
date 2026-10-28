// D4: per-shot Runway image prompt panel — creator review surface.
//
// The board's canonical text is never edited here. This panel reviews the
// separate Runway image prompt (<=1000 UTF-16 units): the compactor's removed
// summary, a hand-edit box with a UTF-16 counter, and an explicit Approve.
// Approving an image prompt never approves the board, and vice versa.
import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, ShieldCheck } from 'lucide-react'
import {
  RUNWAY_IMAGE_PROMPT_LIMIT,
  approveShotImagePrompt,
  deriveShotImagePrompt,
  editShotImagePrompt,
  reapproveShotImagePrompt,
  utf16Length,
  type StoryboardImagePromptEntry,
  type StoryboardShot,
} from '../lib/studioApi'
import { removedSummary, stateLabel } from '../lib/storyboardPromptCopy'

type Props = {
  blueprintId: string
  shot: StoryboardShot
  entry?: StoryboardImagePromptEntry | null
  disabled?: boolean
  onChanged: () => void
}

export default function StoryboardImagePromptPanel({ blueprintId, shot, entry, disabled, onChanged }: Props) {
  const canonical = shot.render_contract?.provider_neutral_prompt ?? ''
  const canonicalLength = utf16Length(canonical)
  const state = entry?.state ?? 'missing'
  const current = entry?.image_prompt ?? ''
  const [draft, setDraft] = useState(current)
  const [busy, setBusy] = useState<'save' | 'derive' | 'approve' | 'reapprove' | null>(null)
  const [error, setError] = useState('')
  // Explicit per-shot confirm for re-approval. Always starts unticked and
  // resets whenever the record changes — nothing is re-approved silently.
  const [reapproveConfirmed, setReapproveConfirmed] = useState(false)

  useEffect(() => {
    setDraft(current)
    setError('')
    setReapproveConfirmed(false)
  }, [shot.storyboard_shot_id, current])

  const draftLength = utf16Length(draft)
  const draftOverLimit = draftLength > RUNWAY_IMAGE_PROMPT_LIMIT
  const overBy = draftOverLimit ? draftLength - RUNWAY_IMAGE_PROMPT_LIMIT : 0
  const saveDisabledReason = draftOverLimit
    ? `Save disabled — prompt is ${overBy} unit${overBy === 1 ? '' : 's'} over the ${RUNWAY_IMAGE_PROMPT_LIMIT} UTF-16 limit. Shorten it before saving.`
    : ''
  const dirty = draft !== current
  const summary = useMemo(() => removedSummary(entry), [entry])

  async function run(action: 'save' | 'derive' | 'approve' | 'reapprove') {
    setBusy(action)
    setError('')
    try {
      if (action === 'save') await editShotImagePrompt(blueprintId, shot.storyboard_shot_id, draft)
      if (action === 'derive') await deriveShotImagePrompt(blueprintId, shot.storyboard_shot_id)
      if (action === 'approve') await approveShotImagePrompt(blueprintId, shot.storyboard_shot_id)
      if (action === 'reapprove') {
        await reapproveShotImagePrompt(blueprintId, shot.storyboard_shot_id, reapproveConfirmed)
        setReapproveConfirmed(false)
      }
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Image prompt update failed')
    } finally {
      setBusy(null)
    }
  }

  // Re-approval is offered only when the prompt was already human-approved
  // and went stale solely because a Rebuild changed the canonical text.
  const canReapprove = state === 'stale' && entry?.status === 'approved'
  const rebuildRecord = (shot.metadata as Record<string, unknown> | undefined)?.prompt_rebuild as
    | { before_prompt?: unknown; after_prompt?: unknown }
    | undefined
  const rebuildBefore = typeof rebuildRecord?.before_prompt === 'string' ? rebuildRecord.before_prompt : ''
  const rebuildAfter = typeof rebuildRecord?.after_prompt === 'string' ? rebuildRecord.after_prompt : ''
  const showRebuildDiff = canReapprove && Boolean(rebuildBefore || rebuildAfter)

  const stateBadge = state === 'ready'
    ? (
      <span className="inline-flex items-center gap-1 rounded border border-emerald-400/25 px-2 py-0.5 text-[11px] text-emerald-200">
        <CheckCircle2 size={12} /> render-ready
      </span>
    )
    : (
      <span className="inline-flex items-center gap-1 rounded border border-amber-200/30 px-2 py-0.5 text-[11px] text-amber-100">
        <AlertTriangle size={12} /> {stateLabel(state)}
      </span>
    )

  return (
    <div className="space-y-2 rounded-lg border border-white/10 bg-white/[0.025] p-3" data-testid={`image-prompt-panel-${shot.shot_number}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium text-zinc-100">Runway image prompt · shot {shot.shot_number}</p>
        {stateBadge}
      </div>
      <p className="text-[11px] leading-relaxed text-zinc-400">
        Board text: {canonicalLength} UTF-16 units{canonicalLength > RUNWAY_IMAGE_PROMPT_LIMIT ? ' (over the Runway limit — the board text itself is never changed)' : ''}.
        Runway renders use only the approved prompt below.
      </p>
      {entry?.gate_message && state !== 'ready' && (
        <p className="text-[11px] leading-relaxed text-amber-200/90" role="status">{entry.gate_message}</p>
      )}
      {summary && <p className="text-xs leading-relaxed text-zinc-500">{summary}</p>}
      {entry?.origin && (
        <p className="text-[11px] text-zinc-500">
          {entry.origin === 'human' ? 'Hand-edited proposal' : 'Compactor proposal'}
          {entry.status === 'approved' ? ` · approved${entry.approved_by ? ` by ${entry.approved_by}` : ''}` : ' · awaiting approval'}
          {entry.reapproved_at ? ` · re-approved against rebuilt text${entry.reapproved_by ? ` by ${entry.reapproved_by}` : ''}` : ''}
        </p>
      )}
      {showRebuildDiff && (
        <div className="space-y-1 rounded-md border border-sky-400/25 bg-sky-500/5 p-2">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-sky-200/80">Board text changed by Rebuild</p>
          <div className="grid gap-2 md:grid-cols-2">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-500">Before</p>
              <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap rounded bg-zinc-950 p-2 text-xs leading-relaxed text-zinc-300" data-testid={`image-prompt-rebuild-before-${shot.shot_number}`}>{rebuildBefore}</p>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-500">After</p>
              <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap rounded bg-zinc-950 p-2 text-xs leading-relaxed text-zinc-300" data-testid={`image-prompt-rebuild-after-${shot.shot_number}`}>{rebuildAfter}</p>
            </div>
          </div>
        </div>
      )}
      {canReapprove && (
        <label className="flex cursor-pointer items-start gap-2 rounded-md border border-sky-400/25 bg-sky-500/5 px-3 py-2 text-[11px] leading-relaxed text-sky-100">
          <input
            type="checkbox"
            checked={reapproveConfirmed}
            onChange={(event) => setReapproveConfirmed(event.target.checked)}
            disabled={disabled || busy !== null}
            data-testid={`image-prompt-reapprove-confirm-${shot.shot_number}`}
            className="mt-0.5"
          />
          <span>
            I reviewed the rebuilt board text and want this approved prompt to apply to it.
            The prompt itself does not change.
          </span>
        </label>
      )}
      <label className="block">
        <span className="sr-only">Runway image prompt for shot {shot.shot_number}</span>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          rows={4}
          disabled={disabled || busy !== null}
          data-testid={`image-prompt-edit-${shot.shot_number}`}
          className="w-full rounded-md border border-white/15 bg-zinc-950 px-3 py-2 text-xs leading-relaxed text-zinc-100"
        />
      </label>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={`text-xs tabular-nums ${draftOverLimit ? 'font-medium text-rose-300' : 'text-zinc-500'}`} data-testid={`image-prompt-count-${shot.shot_number}`}>
          {draftLength}/{RUNWAY_IMAGE_PROMPT_LIMIT} UTF-16{draftOverLimit ? ' — over the limit' : ''}
        </span>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void run('derive')}
            disabled={disabled || busy !== null}
            aria-busy={busy === 'derive'}
            data-testid={`image-prompt-derive-${shot.shot_number}`}
            className="flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-1.5 text-[11px] text-zinc-200 hover:bg-white/5 disabled:opacity-40"
          >
            {busy === 'derive' ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            Re-derive
          </button>
          <button
            type="button"
            onClick={() => void run('save')}
            disabled={disabled || busy !== null || !dirty || !draft.trim() || draftOverLimit}
            aria-busy={busy === 'save'}
            title={draftOverLimit ? saveDisabledReason : 'Save hand edit as a proposal (approval is separate)'}
            aria-disabled={disabled || busy !== null || !dirty || !draft.trim() || draftOverLimit}
            data-testid={`image-prompt-save-${shot.shot_number}`}
            className="flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-1.5 text-[11px] text-zinc-200 hover:bg-white/5 disabled:opacity-40"
          >
            {busy === 'save' ? <Loader2 size={13} className="animate-spin" /> : null}
            Save edit
          </button>
          <button
            type="button"
            onClick={() => void run('approve')}
            disabled={disabled || busy !== null || draftOverLimit}
            aria-busy={busy === 'approve'}
            title={draftOverLimit ? saveDisabledReason : 'Approve this prompt for Runway renders'}
            data-testid={`image-prompt-approve-${shot.shot_number}`}
            className="flex items-center gap-1.5 rounded-md border border-emerald-400/40 bg-emerald-500/10 px-3 py-1.5 text-[11px] font-medium text-emerald-100 hover:bg-emerald-500/15 disabled:opacity-40"
          >
            {busy === 'approve' ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
            Approve prompt
          </button>
          {canReapprove && (
            <button
              type="button"
              onClick={() => void run('reapprove')}
              disabled={disabled || busy !== null || !reapproveConfirmed || draftOverLimit}
              aria-busy={busy === 'reapprove'}
              data-testid={`image-prompt-reapprove-${shot.shot_number}`}
              title="Re-anchor this approved prompt to the rebuilt board text. The prompt itself is untouched."
              className="flex items-center gap-1.5 rounded-md border border-sky-400/40 bg-sky-500/10 px-3 py-1.5 text-[11px] font-medium text-sky-100 hover:bg-sky-500/15 disabled:opacity-40"
            >
              {busy === 'reapprove' ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
              Re-approve against rebuilt text
            </button>
          )}
        </div>
      </div>
      {draftOverLimit && (
        <p className="text-[11px] leading-relaxed text-rose-300" role="status" data-testid={`image-prompt-overlimit-${shot.shot_number}`}>{saveDisabledReason}</p>
      )}
      {error && <p className="text-xs leading-relaxed text-rose-300" role="alert">{error}</p>}
    </div>
  )
}
