import type { GateTone } from '../components/status/gateTones'

export type NextActionCopy = { label: string; detail: string; to: string | null; toLabel: string | null }

/** One plain-language next action per scene. No counts-as-judgment, no jargon. */
export function nextActionCopy(projectId: string, nextAction: string, sceneId: string): NextActionCopy {
  const q = encodeURIComponent(projectId || '')
  const page = `/studio/writers-room?project_id=${q}`
  const previs = `/studio/previs?project_id=${q}`
  const board = `/studio/production-board?project_id=${q}`
  const theater = `/studio/screening-room?project_id=${q}`
  const vault = `/studio/vault?project_id=${q}`
  switch (nextAction) {
    case 'add_scenes':
      return { label: 'Add scenes to begin', detail: 'This project has no saved scenes yet. Start in The Page.', to: page, toLabel: 'Open The Page' }
    case 'create_board':
      return { label: 'Sketch the shot plan', detail: `${sceneId} has no shot plan yet. Sketch shots in Previs to begin.`, to: previs, toLabel: 'Open Previs' }
    case 'approve_image_prompts':
      return { label: 'Approve the image prompts', detail: 'Some shots still carry proposed prompts. Approve them in Previs.', to: previs, toLabel: 'Open Previs' }
    case 'reapprove_stale_prompts':
      return { label: 'Look again at the changed prompts', detail: 'A prompt changed after approval. Look again and approve in Previs.', to: previs, toLabel: 'Open Previs' }
    case 'confirm_setting_anchor':
      return { label: 'Settle the setting look', detail: 'The setting look is not settled. Check the look in the Vault.', to: vault, toLabel: 'Open the Vault' }
    case 'check_project_data':
      return { label: 'Check the project data', detail: 'The setting look could not be checked from the saved data.', to: null, toLabel: null }
    case 'retry_failed_jobs':
      return { label: 'Try the failed shot again', detail: 'A render failed. Try it again from the scene board.', to: board, toLabel: 'Open scene board' }
    case 'await_media':
      return { label: 'Wait for the media to land', detail: 'Shots are moving. Wait for finished media before the next step.', to: board, toLabel: 'Open scene board' }
    case 'ready':
      return { label: 'Ready to screen', detail: 'Every check passed. Watch it in the Screening Room.', to: theater, toLabel: 'Open Screening Room' }
    default:
      return { label: 'Check this scene', detail: 'Something needs a look before this scene can move on.', to: board, toLabel: 'Open scene board' }
  }
}

/**
 * Minimal structural shot for gate chips. Both the Desk board aggregate
 * (`DeskGateShot`) and the Engine integrity-gates view satisfy this shape,
 * so the same chips render in both rooms.
 */
export type ShotGateInput = {
  d4_ready?: boolean
  d6_ready?: boolean
  setting_anchor?: string
  binding_confirmation?: string
  has_media?: boolean
  latest_job_status?: string | null
}

export type GateChip = { key: string; label: string; tone: GateTone }

/** Plain gate chips: icon + color + one short label each. Anchor "unknown" is neutral, never a stop sign. */
export function shotGateChips(shot: ShotGateInput): Array<GateChip> {
  const d4 = shot.d4_ready
    ? { key: 'd4', label: 'Image ready', tone: 'ok' as GateTone }
    : { key: 'd4', label: 'Image waiting', tone: 'waiting' as GateTone }
  const d6 = shot.d6_ready
    ? { key: 'd6', label: 'Words ready', tone: 'ok' as GateTone }
    : { key: 'd6', label: 'Words waiting', tone: 'waiting' as GateTone }
  const anchor =
    shot.setting_anchor === 'set'
      ? { key: 'anchor', label: 'Look set', tone: 'ok' as GateTone }
      : shot.setting_anchor === 'blocked'
        ? { key: 'anchor', label: 'Look needed', tone: 'waiting' as GateTone }
        : { key: 'anchor', label: "Can't check", tone: 'idle' as GateTone }
  const confirmed = String(shot.binding_confirmation || 'missing').toLowerCase() === 'confirmed'
    ? { key: 'confirm', label: 'Confirmed', tone: 'ok' as GateTone }
    : String(shot.binding_confirmation || 'missing').toLowerCase() === 'missing'
      ? { key: 'confirm', label: 'Not confirmed yet', tone: 'idle' as GateTone }
      : { key: 'confirm', label: 'Changed since confirmed', tone: 'waiting' as GateTone }
  const job = shot.has_media
    ? { key: 'job', label: 'Media ready', tone: 'ok' as GateTone }
    : String(shot.latest_job_status || '').toLowerCase() === 'failed'
      ? { key: 'job', label: 'Try again', tone: 'attention' as GateTone }
      : ['pending', 'queued', 'rendering'].includes(String(shot.latest_job_status || '').toLowerCase())
        ? { key: 'job', label: 'Making now', tone: 'waiting' as GateTone }
        : { key: 'job', label: 'No media yet', tone: 'idle' as GateTone }
  return [d4, d6, anchor, confirmed, job]
}
