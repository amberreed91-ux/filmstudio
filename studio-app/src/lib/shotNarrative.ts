/**
 * Shot narrative fields carried across room boundaries.
 *
 * Previs records why a shot exists and which motif it carries; the Board and
 * the Production Desk read that back instead of re-deriving meaning from
 * status flags. Payloads arrive from more than one layer, so each value is
 * accepted in the shape its producer uses:
 *
 *   intent  → `shotIntent` · `shot_intent` · `intent`
 *   motif   → `motifRef` · `motif_ref` · `motif`
 *
 * Missing or malformed input resolves to an empty value. Nothing here invents
 * a rationale: an untagged shot stays untagged so the room can say so plainly.
 */

export type ShotNarrative = {
  /** One-line purpose for the shot. Empty when no intent was saved. */
  shotIntent: string
  /** Raw motif reference, exactly as the board card carried it. */
  motifRef: string
  /** `motifRef` split into individual, de-duplicated tags. */
  motifs: string[]
}

const MOTIF_SEPARATOR = /\s*[,;|·]\s*/

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asText(value: unknown): string {
  if (typeof value !== 'string') return ''
  return value.replace(/\s+/g, ' ').trim()
}

function firstText(source: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const text = asText(source[key])
    if (text) return text
  }
  return ''
}

/** Split a motif reference into individual tags, preserving arrival order. */
export function parseMotifRefs(value: unknown): string[] {
  const text = asText(value)
  if (!text) return []
  const seen = new Set<string>()
  const motifs: string[] = []
  for (const part of text.split(MOTIF_SEPARATOR)) {
    const motif = asText(part)
    if (!motif) continue
    const key = motif.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    motifs.push(motif)
  }
  return motifs
}

/**
 * Read the narrative fields from a board card, a desk shot row, or any other
 * loosely-shaped payload. A nested `intent` object is ignored — only a string
 * is treated as an authored rationale.
 */
export function readShotNarrative(source: unknown): ShotNarrative {
  const record = asRecord(source)
  if (!record) return { shotIntent: '', motifRef: '', motifs: [] }

  const metadata = asRecord(record.metadata)
  const shotIntent =
    firstText(record, ['shotIntent', 'shot_intent', 'intent']) ||
    (metadata ? firstText(metadata, ['intent_rationale', 'intentRationale', 'shot_intent', 'shotIntent']) : '')
  const motifRef = firstText(record, ['motifRef', 'motif_ref', 'motif'])

  return { shotIntent, motifRef, motifs: parseMotifRefs(motifRef) }
}
