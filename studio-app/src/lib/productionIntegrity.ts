// Per-shot integrity gates (one GET per shot, read-only) shared by the
// Production Integrity Engine and its fixtures.
//
// Shape mirrors GET /api/f51/studio/projects/{id}/shots/{shotId}/integrity-gates.
// The Engine only reads these payloads; it never prepares, submits, confirms,
// prices, or cancels anything through them.
import type { DeskGateShot } from './deskGate'
import type { ShotGateInput } from './statusCopy'
import { fetchJson } from './studioApi'

export type IntegrityGateState = 'pass' | 'blocked' | 'cant_check' | 'not_yet'

export type IntegrityGate = {
  state: IntegrityGateState
  label: string
  detail: string
}

export type ShotIntegrityGates = {
  project_id: string
  shot_id: string
  scene_id: string
  gates: Record<string, IntegrityGate>
  spend: { estimated_credits: number | null; cost_status?: string | null }
  duplicate: { runway_task_id: string | null }
  binding_digest: string | null
  latest_job_id: string | null
  latest_job_status: string | null
  next_action: string
  blockers: string[]
}

export const INTEGRITY_GATE_ORDER = [
  'image',
  'words',
  'look',
  'settled',
  'contract',
  'preflight',
  'spend',
  'duplicate',
] as const

export async function getShotIntegrityGates(projectId: string, shotId: string): Promise<ShotIntegrityGates> {
  return fetchJson<ShotIntegrityGates>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/shots/${encodeURIComponent(shotId)}/integrity-gates`,
  )
}

/** Map one integrity-gates payload (+ its Desk row) onto the shared five chips. */
export function gatesToChipInput(gates: ShotIntegrityGates | null, row?: DeskGateShot): ShotGateInput {
  const stateOf = (name: string): IntegrityGateState => gates?.gates?.[name]?.state ?? 'not_yet'
  const look = stateOf('look')
  const settled = stateOf('settled')
  return {
    d4_ready: stateOf('image') === 'pass',
    d6_ready: stateOf('words') === 'pass',
    setting_anchor: look === 'pass' ? 'set' : look === 'blocked' ? 'blocked' : 'unknown',
    binding_confirmation:
      settled === 'pass' ? 'confirmed' : settled === 'blocked' ? 'stale' : 'missing',
    has_media: row?.has_media ?? false,
    latest_job_status: row?.latest_job_status ?? gates?.latest_job_status ?? null,
  }
}

export type EngineGateNext = { label: string; to: string | null; plain?: string }

/** One plain next step per blocked gate. Links are navigation only. */
export function engineGateNext(
  gateName: string,
  projectId: string,
): EngineGateNext {
  const q = encodeURIComponent(projectId || '')
  const previs = `/studio/previs?project_id=${q}`
  const vault = `/studio/vault?project_id=${q}`
  const desk = `/studio/production-desk?project_id=${q}`
  const board = `/studio/production-board?project_id=${q}`
  switch (gateName) {
    case 'image':
      return { label: 'Open Previs to approve the image prompts', to: previs }
    case 'words':
      return { label: 'Open Previs to approve the send text', to: previs }
    case 'look':
      return { label: 'Open the Vault to settle the setting look', to: vault }
    case 'settled':
      return { label: 'Confirm this binding on the Desk', to: desk }
    case 'contract':
    case 'preflight':
      return { label: 'Prepare the scene in Previs', to: previs }
    case 'spend':
      return {
        label: '',
        to: null,
        plain: 'Wait for a recorded price — this view never prices a shot itself.',
      }
    case 'duplicate':
      return { label: 'Check the scene board before retrying', to: board }
    default:
      return { label: 'Check the scene board', to: board }
  }
}

export function blockedGates(gates: ShotIntegrityGates | null): string[] {
  if (!gates) return []
  return INTEGRITY_GATE_ORDER.filter((name) => gates.gates?.[name]?.state === 'blocked')
}

/** A shot is ready only when every gate passes and finished media is saved. */
export function isShotReady(gates: ShotIntegrityGates | null, row?: DeskGateShot): boolean {
  if (!gates) return false
  const allPass = INTEGRITY_GATE_ORDER.every((name) => gates.gates?.[name]?.state === 'pass')
  return allPass && (row?.has_media ?? false)
}
