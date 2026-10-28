/**
 * Board card → Desk queue conversion.
 *
 * The Desk never re-reads the board's raw payload: it turns each card into a
 * queue item and keeps the shot's rationale and motif tags intact on the way
 * through. A shot that carries neither stays honestly empty — the inspector
 * says so rather than inventing a purpose.
 */
import type { DeskGateScene, DeskGateShot } from './deskGate'
import { readShotNarrative } from './shotNarrative'

export type DeskQueueItem = {
  shotId: string
  sceneId: string
  sceneName: string
  shotNumber: number | null
  /** Primary purpose carried from the board card. Empty when none was saved. */
  intent: string
  /** Visual motifs this shot carries. Empty when none was tagged. */
  motifs: string[]
  hasMedia: boolean
}

function asShotNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/**
 * One queue item per shot. A scene-level card carrying an intent hands it down
 * to its shots, so a board tagged at scene level still reaches the Desk.
 */
export function toDeskQueueItem(scene: DeskGateScene, shot: DeskGateShot): DeskQueueItem {
  const shotNarrative = readShotNarrative(shot)
  const sceneNarrative = readShotNarrative(scene)
  const intent = shotNarrative.shotIntent || sceneNarrative.shotIntent
  const motifs = shotNarrative.motifs.length > 0 ? shotNarrative.motifs : sceneNarrative.motifs

  return {
    shotId: String(shot.shot_id || ''),
    sceneId: String(scene.scene_id || ''),
    sceneName: String(scene.scene_name || ''),
    shotNumber: asShotNumber(shot.shot_number),
    intent,
    motifs,
    hasMedia: Boolean(shot.has_media),
  }
}

/** Flatten the board aggregate into the Desk's shot queue. */
export function toDeskQueueItems(scenes: DeskGateScene[]): DeskQueueItem[] {
  if (!Array.isArray(scenes)) return []
  return scenes.flatMap((scene) => {
    const shots = Array.isArray(scene?.shots) ? scene.shots : []
    return shots.map((shot) => toDeskQueueItem(scene, shot))
  })
}

/** The selected queue item, or null when nothing matches. */
export function findDeskQueueItem(items: DeskQueueItem[], shotId: string | null | undefined): DeskQueueItem | null {
  if (!shotId || !Array.isArray(items)) return null
  return items.find((item) => item.shotId === shotId) ?? null
}
