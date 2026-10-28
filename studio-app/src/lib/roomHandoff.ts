/**
 * Room-to-room handoff vocabulary.
 *
 * Previs → Scenes → Watch → Production Desk share one status vocabulary and
 * one empty-state shape. Rooms read these strings instead of inventing their
 * own, so a creator sees the same five words at every handoff:
 *
 *   Not started · Waiting on you · Making now · Ready · Needs attention
 *
 * "Can't check" stays neutral on purpose: missing evidence is not a failure.
 *
 * Co-director rules apply to every string here: no scores, ratings, or
 * percentages, and no praise. Status describes what a creator can do next.
 */

export type HandoffRoom = 'previs' | 'scenes' | 'watch' | 'desk'

export type HandoffStatus =
  | 'not_started'
  | 'waiting'
  | 'making'
  | 'ready'
  | 'needs_attention'
  | 'cant_check'

export type HandoffTone = 'idle' | 'waiting' | 'attention' | 'ok'

export type HandoffStatusCopy = {
  label: string
  tone: HandoffTone
  /** One line a creator can act on. Never a score or a grade. */
  detail: string
}

/** The single status vocabulary used by every handoff surface. */
export const HANDOFF_STATUS: Record<HandoffStatus, HandoffStatusCopy> = {
  not_started: { label: 'Not started', tone: 'idle', detail: 'Nothing saved for this step yet.' },
  waiting: { label: 'Waiting on you', tone: 'waiting', detail: 'The next move is yours.' },
  making: { label: 'Making now', tone: 'waiting', detail: 'Work is moving; no action needed.' },
  ready: { label: 'Ready', tone: 'ok', detail: 'This step is complete and ready to hand off.' },
  needs_attention: { label: 'Needs attention', tone: 'attention', detail: 'Something stopped short and can be tried again.' },
  cant_check: { label: 'Can’t check', tone: 'idle', detail: 'The saved data does not say yet.' },
}

export type HandoffRoomDefinition = {
  label: string
  path: string
  purpose: string
  next: HandoffRoom | null
}

/** Pipeline order. `desk` is the terminal room. */
export const HANDOFF_ROOMS: Record<HandoffRoom, HandoffRoomDefinition> = {
  previs: {
    label: 'Previs',
    path: '/studio/previs',
    purpose: 'Approve the storyboard, direct each take, and assemble the scene.',
    next: 'scenes',
  },
  scenes: {
    label: 'Scenes',
    path: '/studio/production-board',
    purpose: 'Check scenes and render jobs, then open a scene in Previs to direct its shots.',
    next: 'watch',
  },
  watch: {
    label: 'Watch',
    path: '/studio/screening-room',
    purpose: 'Watch the footage, make revisions, and prepare the final film.',
    next: 'desk',
  },
  desk: {
    label: 'Production Desk',
    path: '/studio/production-desk',
    purpose: 'Read the evidence for every scene and shot before delivery.',
    next: null,
  },
}

export const HANDOFF_ORDER: HandoffRoom[] = ['previs', 'scenes', 'watch', 'desk']

/** Carries the active film across a room boundary. */
export function handoffHref(path: string, projectId?: string | null): string {
  const id = (projectId || '').trim()
  return id ? `${path}?project_id=${encodeURIComponent(id)}` : path
}

export function roomHandoffPath(room: HandoffRoom, projectId?: string | null): string {
  return handoffHref(HANDOFF_ROOMS[room].path, projectId)
}

export type PipelineCounts = {
  sceneCount: number
  /** Scenes that are fully ready to hand off. */
  readyCount?: number
  /** Scenes with work actively moving. */
  makingCount?: number
  /** Scenes that stopped short. */
  attentionCount?: number
  /** True when the payload itself could not be read. */
  unreadable?: boolean
}

/**
 * Derives one handoff status from pipeline counts.
 *
 * Precedence: unreadable → needs_attention → making → not_started → ready →
 * waiting. Trouble outranks motion so a stalled scene is never hidden behind
 * a spinner.
 */
/** Counts arrive from loosely-shaped payloads; keep NaN out of comparisons. */
function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0
}

export function handoffStatusForPipeline(counts: PipelineCounts): HandoffStatus {
  const sceneCount = count(counts.sceneCount)
  const readyCount = count(counts.readyCount)
  const makingCount = count(counts.makingCount)
  const attentionCount = count(counts.attentionCount)

  if (counts.unreadable) return 'cant_check'
  if (attentionCount > 0) return 'needs_attention'
  if (makingCount > 0) return 'making'
  if (sceneCount === 0) return 'not_started'
  if (readyCount >= sceneCount) return 'ready'
  return 'waiting'
}

/** Status for a single shot, using the same vocabulary as the pipeline. */
export function handoffStatusForShot(shot: {
  has_media?: boolean
  latest_job_status?: string | null
}): HandoffStatus {
  if (shot.has_media) return 'ready'
  const raw = String(shot.latest_job_status || '').trim().toLowerCase()
  if (!raw) return 'not_started'
  if (['failed', 'error', 'cancelled', 'canceled'].includes(raw)) return 'needs_attention'
  if (['pending', 'queued', 'rendering', 'processing', 'running', 'in_progress'].includes(raw)) return 'making'
  if (['complete', 'completed', 'success', 'rendered'].includes(raw)) return 'cant_check'
  return 'waiting'
}

export type RoomEmptyState = {
  title: string
  body: string
  /** One primary action. `null` means the room has nothing to offer yet. */
  action: { label: string; path: string } | null
}

/**
 * The four primary empty states. Same shape, same tone, one action each:
 * what this room is for, what is missing, and the single next move.
 */
export const ROOM_EMPTY_STATES = {
  scenes: {
    title: 'Your scene wall starts with a script',
    body: 'No scenes yet. Generate your script in The Page to begin.',
    action: { label: 'Open The Page', path: '/studio/writers-room' },
  },
  watch: {
    title: 'Your film starts with a scene',
    body: 'Add your script in The Page, then storyboard and render in Previs.',
    action: { label: 'Open The Page', path: '/studio/writers-room' },
  },
  previsScene: {
    title: 'Choose a scene to direct',
    body: 'Pick a scene above. Its shots stay in order from storyboard to take.',
    action: null,
  },
  previsTakes: {
    title: 'No takes for this shot yet',
    body: 'Render a take in step 3, then return here to review it.',
    action: null,
  },
  desk: {
    title: 'No saved scenes yet',
    body: 'Start in The Page, then return here for shot-by-shot coverage.',
    action: { label: 'Open The Page', path: '/studio/writers-room' },
  },
} satisfies Record<string, RoomEmptyState>
