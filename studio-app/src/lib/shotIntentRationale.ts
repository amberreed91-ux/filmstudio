/**
 * Shot intent rationale resolver.
 *
 * Pure, zero-throw helper that derives a one-sentence "Why this shot matters"
 * rationale from existing shot / narrative metadata signals. Priority order:
 *   1. Explicit `shot.intent` (string) or `shot.metadata.intent_rationale`
 *   2. `shot.director_notes` / `shot.narrative_function`
 *      (also checks nested `intent` object for the same keys, matching the
 *      backend storyboard shape where intent is an object)
 *   3. Derived synthesis from `shot.prompt`/`description` or camera action
 *   4. High-quality fallback string
 *
 * Co-director voice: no scores, ratings, or percentages. Never throws —
 * missing / null / malformed input always resolves to the fallback.
 */

export type ShotIntentInput = {
  intent?: unknown;
  metadata?: unknown;
  director_notes?: unknown;
  narrative_function?: unknown;
  prompt?: unknown;
  description?: unknown;
  camera?: unknown;
  camera_notes?: unknown;
  camera_action?: unknown;
  shot_type?: unknown;
  [key: string]: unknown;
};

export const SHOT_INTENT_FALLBACK =
  'Establishes key visual beats and emotional tone for this scene transition.';

const MAX_SYNTHESIS_CHARS = 140;

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function asNonEmptyString(value: unknown): string {
  if (typeof value !== 'string') return '';
  const trimmed = value.replace(/\s+/g, ' ').trim();
  return trimmed;
}

/** Collapse to a single concise sentence ending with a period. */
function toSingleSentence(value: string): string {
  const cleaned = value.replace(/\s+/g, ' ').trim();
  if (!cleaned) return '';
  // Take the first sentence so multi-sentence notes stay one sentence.
  const match = cleaned.match(/^[^.!?]+[.!?]/);
  let first = (match ? match[0] : cleaned).trim();
  // Strip trailing punctuation then re-add a single period.
  first = first.replace(/[.!?]+$/, '').trim();
  if (!first) return '';
  return `${first}.`;
}

function truncateMiddle(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1).trimEnd()}…`;
}

function intentObjectField(intent: unknown, keys: string[]): string {
  const record = asRecord(intent);
  if (!record) return '';
  for (const key of keys) {
    const text = asNonEmptyString(record[key]);
    if (text) return text;
  }
  return '';
}

export function getShotIntentRationale(shot: unknown): string {
  try {
    const record = asRecord(shot);
    if (!record) return SHOT_INTENT_FALLBACK;

    // Tier 1 — explicit intent or metadata rationale.
    const explicitIntent = asNonEmptyString(record.intent);
    if (explicitIntent) {
      const sentence = toSingleSentence(explicitIntent);
      if (sentence) return sentence;
    }
    const metadata = asRecord(record.metadata);
    const metadataRationale = metadata
      ? asNonEmptyString(metadata.intent_rationale ?? metadata.intentRationale)
      : '';
    if (metadataRationale) {
      const sentence = toSingleSentence(metadataRationale);
      if (sentence) return sentence;
    }
    // Backend storyboard shape: intent is an object carrying the rationale.
    const nestedIntent = intentObjectField(record.intent, [
      'intent_rationale',
      'rationale',
      'narrative_function',
      'purpose',
      'text',
    ]);
    if (nestedIntent) {
      const sentence = toSingleSentence(nestedIntent);
      if (sentence) return sentence;
    }

    // Tier 2 — director notes / narrative function.
    const directorNotes = asNonEmptyString(record.director_notes);
    if (directorNotes) {
      const sentence = toSingleSentence(directorNotes);
      if (sentence) return sentence;
    }
    const narrativeFunction =
      asNonEmptyString(record.narrative_function) ||
      intentObjectField(record.intent, ['narrative_function', 'purpose']);
    if (narrativeFunction) {
      const sentence = toSingleSentence(narrativeFunction);
      if (sentence) return sentence;
    }

    // Tier 3 — derived synthesis from prompt or camera action.
    const promptText =
      asNonEmptyString(record.prompt) || asNonEmptyString(record.description);
    const cameraText =
      asNonEmptyString(record.camera_action) ||
      asNonEmptyString(record.camera) ||
      asNonEmptyString(record.camera_notes) ||
      asNonEmptyString(record.shot_type);
    if (promptText && cameraText) {
      return `Uses ${toSingleSentence(cameraText).replace(/\.$/, '')} to carry ${truncateMiddle(toSingleSentence(promptText).replace(/\.$/, ''), MAX_SYNTHESIS_CHARS)} into the next beat.`;
    }
    if (promptText) {
      return `Translates ${truncateMiddle(toSingleSentence(promptText).replace(/\.$/, ''), MAX_SYNTHESIS_CHARS)} into a focused visual beat that moves the scene forward.`;
    }
    if (cameraText) {
      return `Uses ${toSingleSentence(cameraText).replace(/\.$/, '')} to carry the scene's emotional momentum into the next beat.`;
    }

    // Tier 4 — fallback.
    return SHOT_INTENT_FALLBACK;
  } catch {
    return SHOT_INTENT_FALLBACK;
  }
}
