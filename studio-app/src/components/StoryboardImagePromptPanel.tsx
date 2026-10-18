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

type Props = {
  blueprintId: string
  shot: StoryboardShot
  entry?: StoryboardImagePromptEntry | null
  disabled?: boolean
  onChanged: () => void
}

function parseStringList(raw: string | null | undefined): string[] {
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.map((item) => String(item)) : []
  } catch {
    return []
  }
}

export function removedSummary(entry: StoryboardImagePromptEntry | null | undefined): string | null {
  if (!entry || entry.origin === 'human') return null
  const rules = parseStringList(entry.rules_applied_json)
  const dropped = parseStringList(entry.dropped_segments_json)
  const removed = entry.chars_removed ?? 0
  if (!rules.length && !dropped.length && !removed) return null
  const parts = [`compactor removed ${removed} chars`]
  if (rules.length) parts.push(`rules: ${rules.join(', ')}`)
  if (dropped.length) parts.push(`${dropped.length} segment${dropped.length === 1 ? '' : 's'} dropped`)
  return parts.join(' · ')
}

// Honest state labels: the badge names the actual situation (including what
// the creator must do next) instead of echoing backend state words.
const STATE_LABELS: Record<string, string> = {
  missing: 'No image prompt yet — derive or write one, then approve',
  unapproved: 'Proposal — awaiting approval (saving is not approving)',
  stale: 'Board text changed — re-approve this prompt against the new text',
  over_limit: 'Over the Runway limit — shorten, then approve',
  ready: 'render-ready',
}

export function stateLabel(state: string): string {
  return STATE_LABELS[state] ?? state.replaceAll('_', ' ')
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
      {summary && <p className="text-[11px] leading-relaxed text-zinc-500">{summary}</p>}
      {entry?.origin && (
        <p className="text-[11px] text-zinc-500">
          {entry.origin === 'human' ? 'Hand-edited proposal' : 'Compactor proposal'}
          {entry.status === 'approved' ? ` · approved${entry.approved_by ? ` by ${entry.approved_by}` : ''}` : ' · awaiting approval'}
          {entry.reapproved_at ? ` · re-approved against rebuilt text${entry.reapproved_by ? ` by ${entry.reapproved_by}` : ''}` : ''}
        </p>
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
        <span className={`text-[11px] tabular-nums ${draftOverLimit ? 'font-medium text-rose-300' : 'text-zinc-500'}`} data-testid={`image-prompt-count-${shot.shot_number}`}>
          {draftLength}/{RUNWAY_IMAGE_PROMPT_LIMIT} UTF-16{draftOverLimit ? ' — over the limit' : ''}
        </span>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void run('derive')}
            disabled={disabled || busy !== null}
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
      {error && <p className="text-[11px] leading-relaxed text-rose-300" role="alert">{error}</p>}
    </div>
  )
}
