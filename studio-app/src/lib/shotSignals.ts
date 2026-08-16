import { fetchOptionalJson } from './optionalStudioApi'
import { fetchJson } from './studioApi'

/**
 * Shot signals — what the render pipeline noticed, in director-facing form.
 *
 * The backend records intent fidelity, character identity, the references that
 * conditioned a render, and the exclusions sent with it. Until now nothing read
 * any of it. This is the client for `/render/jobs/{jobId}/signals`.
 *
 * Per AGENTS.md the payload deliberately contains no scores, ratings, or
 * percentages — the underlying records hold those for logging and they stop at
 * the service boundary. Nothing here should reintroduce a number the director
 * has to interpret.
 */

export type ShotSignalKind =
  | 'intent_fidelity'
  | 'character_identity'
  | 'character_references'
  | 'exclusions'

/** `attention` is worth interrupting for. `settled` is context, shown quietly. */
export type ShotSignalStatus = 'attention' | 'settled' | 'quiet'

export type IdentityCharacterReading = {
  character_name: string
  reading: string
  drifted: boolean
}

export type ShotReference = {
  ref_id: string
  role: string
  image_url: string
  source_shot_id?: string | null
}

export type ShotSignal = {
  kind: ShotSignalKind
  status: ShotSignalStatus
  note: string
  dropped_phrases?: string[]
  characters?: IdentityCharacterReading[]
  references?: ShotReference[]
  terms?: string[]
  measures_identity?: boolean
}

export type ShotSignalsEnvelope = {
  job_id: string
  shot_id: string
  project_id: string
  status: ShotSignalStatus
  signals: ShotSignal[]
  quiet_signals: { kind: string; reason: string }[]
}

export async function getShotSignals(
  jobId: string,
  signal?: AbortSignal,
): Promise<ShotSignalsEnvelope | null> {
  return fetchOptionalJson<ShotSignalsEnvelope>(
    `/api/f51/studio/render/jobs/${encodeURIComponent(jobId)}/signals`,
    signal,
  )
}

export type RelockReferenceRequest = {
  project_id: string
  character_id: string
  image_url: string
  reference_role?: string
  character_name?: string
  source_shot_id?: string
  reason?: string
}

/**
 * Replace a character's locked visual reference.
 *
 * Locks used to be permanent — the first render that passed adherence defined a
 * character for the rest of the film, with no way to correct a bad frame.
 */
export async function relockCharacterReference(
  payload: RelockReferenceRequest,
): Promise<{ lock: Record<string, unknown> }> {
  return fetchJson<{ lock: Record<string, unknown> }>(
    '/api/f51/studio/render/character-references/relock',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
}

const SIGNAL_TITLES: Record<ShotSignalKind, string> = {
  intent_fidelity: 'What the prompt dropped',
  character_identity: 'Character likeness',
  character_references: 'References used',
  exclusions: 'Kept out of frame',
}

export type ShotSignalView = {
  kind: ShotSignalKind
  title: string
  note: string
  needsAttention: boolean
  details: string[]
}

/**
 * Turn the envelope into what a panel renders.
 *
 * Kept as a pure function so the presentation rules — ordering, which details
 * are worth showing, and the no-numbers guarantee — are testable without a DOM.
 */
export function buildShotSignalViews(envelope: ShotSignalsEnvelope | null): ShotSignalView[] {
  if (!envelope || !Array.isArray(envelope.signals)) return []

  const views = envelope.signals.map((signal) => {
    const details: string[] = []

    if (signal.kind === 'intent_fidelity') {
      details.push(...(signal.dropped_phrases ?? []))
    } else if (signal.kind === 'character_identity') {
      details.push(
        ...(signal.characters ?? [])
          .filter((row) => row.character_name)
          .map((row) => `${row.character_name} — ${row.reading}`),
      )
    } else if (signal.kind === 'character_references') {
      details.push(
        ...(signal.references ?? []).map((ref) =>
          ref.role === 'general' ? 'primary reference' : ref.role.replace(/_/g, ' '),
        ),
      )
    } else if (signal.kind === 'exclusions') {
      details.push(...(signal.terms ?? []))
    }

    return {
      kind: signal.kind,
      title: SIGNAL_TITLES[signal.kind] ?? signal.kind,
      note: signal.note,
      needsAttention: signal.status === 'attention',
      details,
    }
  })

  // Anything asking for a decision comes first; the rest is background.
  return [
    ...views.filter((view) => view.needsAttention),
    ...views.filter((view) => !view.needsAttention),
  ]
}

/** True when the panel has nothing worth drawing. Silence beats a reassuring row. */
export function shotSignalsAreQuiet(envelope: ShotSignalsEnvelope | null): boolean {
  return !envelope || envelope.signals.length === 0
}
