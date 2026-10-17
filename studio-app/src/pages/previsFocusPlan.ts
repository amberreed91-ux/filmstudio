/**
 * Pure decision logic for the Previs Room's "navigated from another room"
 * URL handling (Writers Room scene links, Production Board, and the
 * Screening Room's APPLY TO SHOT co-director note).
 *
 * Extracted from PrevisRoom so the stale-param bug is regression testable:
 * the codirector_note param used to stay in the URL forever, which made the
 * scene-reset and auto-populate effects skip on every later render — every
 * scene switch looked like "nothing happens" until a manual reload. The fix
 * consumes the param right after applying it.
 */

export type PrevisFocusPlan = {
  /** Scene to focus/select; '' when there is nothing to focus. */
  sceneId: string
  /** Shot number from the URL (?shot=N); null when absent or invalid. */
  shotNumber: number | null
  /** Decoded, length-capped co-director note; null when no note was passed. */
  codirectorNote: string | null
  /**
   * True whenever a codirector_note param is present. The caller MUST then
   * delete the param from the URL after applying the note — leaving it in
   * place would keep the scene-reset and auto-populate effects skipped
   * forever (the original "scene switching does nothing" bug).
   */
  consumeCodirectorNote: boolean
}

export type PrevisFocusInputs = {
  searchParams: URLSearchParams
  /** react-router's location.state, carrying focus_scene_id from other rooms. */
  locationState?: { focus_scene_id?: string; scene_index?: number } | null
  /** Scene IDs that exist in the loaded project. */
  sceneIds: readonly string[]
}

const MAX_NOTE_LENGTH = 200

function decodeNote(raw: string): string {
  try {
    return decodeURIComponent(raw).slice(0, MAX_NOTE_LENGTH)
  } catch {
    // Malformed percent-encoding must not crash the room; use the raw text.
    return raw.slice(0, MAX_NOTE_LENGTH)
  }
}

export function planPrevisFocus({
  searchParams,
  locationState,
  sceneIds,
}: PrevisFocusInputs): PrevisFocusPlan | null {
  const sceneId = locationState?.focus_scene_id || searchParams.get('scene') || ''
  if (!sceneId || sceneIds.length === 0 || !sceneIds.includes(sceneId)) return null

  const noteParam = searchParams.get('codirector_note')
  const shotParam = searchParams.get('shot')
  const shotNumber = shotParam ? parseInt(shotParam, 10) : NaN

  return {
    sceneId,
    shotNumber: !isNaN(shotNumber) && shotNumber > 0 ? shotNumber : null,
    codirectorNote: noteParam !== null ? decodeNote(noteParam) : null,
    consumeCodirectorNote: noteParam !== null,
  }
}
