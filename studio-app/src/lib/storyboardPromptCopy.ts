// Plain-language copy for the per-shot image prompt panel: what the
// compactor removed, and an honest label for each backend state.
import type { StoryboardImagePromptEntry } from './studioApi'

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
