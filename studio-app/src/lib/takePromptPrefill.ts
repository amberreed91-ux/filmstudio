import type { StoryboardImagePromptEntry, StoryboardShot } from './studioApi'

export type TakePromptPrefill = {
  /** Text to place in the take box. Empty when blocked — never board text. */
  text: string
  /**
   * False when no approved image prompt backs this shot. The take box must
   * stay empty and rendering must stop with the notice, never silently fall
   * back to the board's provider_neutral_prompt.
   */
  ready: boolean
  /** Clear message shown when blocked. Stale states name re-approval. */
  notice: string | null
}

/**
 * Resolve the "Direct the action" take-box prefill for one board shot.
 *
 * The take box reads the approved, hash-linked image prompt — the same text
 * the generation manifest sends verbatim. Anything else (missing, a
 * proposal awaiting approval, a stale prompt after board edits, an
 * over-limit prompt) blocks with directions instead of prefilling the stale
 * board prompt. Shots with no board (null shot) pass through: the caller's
 * derived scene-text flow owns those.
 */
export function resolveTakePromptPrefill(
  shot: StoryboardShot | null | undefined,
  entry: StoryboardImagePromptEntry | null | undefined,
): TakePromptPrefill {
  if (!shot) return { text: '', ready: true, notice: null }
  const state = entry?.state ?? 'missing'
  const text = (entry?.image_prompt ?? '').trim()
  if (state === 'ready') {
    if (text) return { text, ready: true, notice: null }
    return {
      text: '',
      ready: false,
      notice: `Shot ${shot.shot_number}: the approved image prompt is empty. Derive or write one, then approve it in the storyboard panel.`,
    }
  }
  const shotLabel = `Shot ${shot.shot_number}`
  switch (state) {
    case 'missing':
      return {
        text: '',
        ready: false,
        notice: `${shotLabel}: no approved image prompt yet. Derive or write one, then approve it in the storyboard panel — the take box stays empty until then.`,
      }
    case 'unapproved':
      return {
        text: '',
        ready: false,
        notice: `${shotLabel}: this image prompt is a proposal awaiting approval (saving is not approving). Approve it in the storyboard panel to direct takes.`,
      }
    case 'stale':
      return {
        text: '',
        ready: false,
        notice: `${shotLabel}: the board text changed since this prompt was approved. Re-derive or re-approve it in the storyboard panel before directing takes.`,
      }
    case 'over_limit':
      return {
        text: '',
        ready: false,
        notice: `${shotLabel}: this image prompt is over the Runway limit. Shorten and re-approve it in the storyboard panel.`,
      }
    default: {
      const backendMessage = (entry?.gate_message ?? '').trim()
      return {
        text: '',
        ready: false,
        notice: backendMessage || `${shotLabel}: the approved image prompt is not render-ready. Review it in the storyboard panel.`,
      }
    }
  }
}
