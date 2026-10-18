/**
 * Procedural CSS/SVG fallback engine for studio rooms.
 *
 * Provides atmospheric color tokens, titles, subtitles, and radial-gradient
 * backdrops so every room has a cinematic identity even when WebGL is
 * unavailable. No external image downloads required.
 */

export interface ProceduralRoomTokens {
  accent: string
  accentDeep: string
  ink: string
  veil: string
}

export interface ProceduralRoomStyle {
  key: string
  title: string
  subtitle: string
  tokens: ProceduralRoomTokens
  /** Atmospheric CSS background (layered radial gradients over a deep base). */
  background: string
  /** Soft outer glow usable for borders / shadows. */
  glow: string
}

function style(
  key: string,
  title: string,
  subtitle: string,
  accent: string,
  accentDeep: string,
  extraGlow?: string,
): ProceduralRoomStyle {
  const ink = '#04060d'
  const veil = 'rgba(4,6,13,0.72)'
  return {
    key,
    title,
    subtitle,
    tokens: { accent, accentDeep, ink, veil },
    background: [
      `radial-gradient(ellipse 90% 60% at 50% -10%, ${accent}33 0%, transparent 60%)`,
      `radial-gradient(ellipse 70% 55% at 85% 110%, ${accentDeep}44 0%, transparent 62%)`,
      `radial-gradient(ellipse 60% 50% at 8% 100%, ${accent}1f 0%, transparent 60%)`,
      `linear-gradient(180deg, #070b16 0%, ${ink} 100%)`,
    ].join(', '),
    glow: extraGlow ?? `0 0 32px ${accent}44, 0 18px 60px rgba(0,0,0,0.55)`,
  }
}

const ROOM_STYLES: Record<string, ProceduralRoomStyle> = {
  // ---- Spatial portal keys (12 illuminated arches) ----
  atrium: style('atrium', 'Atrium', 'Grand entry · choose your stage door', '#a78bfa', '#4c1d95'),
  gate: style('gate', 'Gate', 'Home hearth · return to the lobby', '#e8a020', '#7c4a03'),
  page: style('page', 'Page', "Writer's room · story, beats and intent", '#d08383', '#5b2323'),
  board: style('board', 'Board', 'Scene execution and stage-state monitoring', '#78b38a', '#1e4632'),
  previs: style('previs', 'Previs Bay', 'Scenes, shots and approvals before rendering', '#d6a95c', '#6b4a1c'),
  screening: style('screening', 'Screening Room', 'Playback and review of scene cuts', '#5b8dd9', '#1e3a6e'),
  universe: style('universe', 'Universe', 'Characters, locations, lore and objects', '#38b2c8', '#134e5a'),
  vault: style('vault', 'Vault', 'Archive · history, snapshots and provenance', '#9f8dc5', '#3b2f5e'),
  study: style('study', 'Study', 'Structure, health, pacing and lessons', '#7ad6d1', '#1e4a48'),
  desk: style('desk', 'Production Desk', 'Status, blockers and delivery evidence', '#e8a020', '#6b4405'),
  integrity: style('integrity', 'Integrity Engine', 'Verification console for blockers and provenance', '#6D28D9', '#2d2350'),
  reference: style('reference', 'Reference Space', 'Canonical character and setting references', '#7ad6d1', '#164e4b'),

  // ---- Legacy lobby node ids (kept for Interactive3DLobby fallbacks) ----
  'production-desk': style('production-desk', 'Production Desk', 'Status, blockers and delivery evidence', '#e8a020', '#6b4405'),
  'reference-space': style('reference-space', 'Reference Space', 'Canonical character and setting references', '#7ad6d1', '#164e4b'),
  'screening-room': style('screening-room', 'Screening Room', 'Playback and review of scene cuts', '#5b8dd9', '#1e3a6e'),
  'writers-room': style('writers-room', "Writer's Room", 'Story structure, beats and continuity intent', '#d08383', '#5b2323'),
  overview: style('overview', 'Overview', 'Film health, risks and room progress', '#e8edf5', '#3a4763'),
  universe_alias: style('universe_alias', 'Universe', 'Characters, locations, lore and objects', '#38b2c8', '#134e5a'),

  // ---- Route-keyed aliases (room selection handlers navigate here) ----
  '/studio': style('/studio', 'Studio', 'Room-based entry point for the whole pipeline', '#a78bfa', '#4c1d95'),
  '/studio/lobby': style('/studio/lobby', 'Home', 'Room-based entry for every workflow', '#e8a020', '#7c4a03'),
  '/studio/previs': style('/studio/previs', 'Previs Bay', 'Scenes, shots and approvals before rendering', '#d6a95c', '#6b4a1c'),
  '/studio/screening': style('/studio/screening', 'Screening Room', 'Playback and review of scene cuts', '#5b8dd9', '#1e3a6e'),
  '/studio/production-desk': style('/studio/production-desk', 'Production Desk', 'Status, blockers and delivery evidence', '#e8a020', '#6b4405'),
  '/studio/integrity-engine': style('/studio/integrity-engine', 'Integrity Engine', 'Verification console for blockers and provenance', '#6D28D9', '#2d2350'),
  '/studio/reference-space': style('/studio/reference-space', 'Reference Space', 'Canonical character and setting references', '#7ad6d1', '#164e4b'),
}

/**
 * Forensic verification branding for the Integrity Engine: dark graphite
 * (#0B0F17) over obsidian (#050505) with deep violet (#6D28D9) accents.
 * Applied to both integrity room keys so `RoomBackdrop roomKey="integrity"`
 * and the route alias render the same forensic identity.
 */
function applyIntegrityForensicBranding(): void {
  const forensicBackground = [
    'radial-gradient(ellipse 90% 60% at 50% -10%, #6D28D933 0%, transparent 60%)',
    'radial-gradient(ellipse 70% 55% at 85% 110%, #2d235044 0%, transparent 62%)',
    'radial-gradient(ellipse 60% 50% at 8% 100%, #6D28D91f 0%, transparent 60%)',
    'linear-gradient(180deg, #0B0F17 0%, #050505 100%)',
  ].join(', ')
  for (const key of ['integrity', '/studio/integrity-engine'] as const) {
    const current = ROOM_STYLES[key]
    if (!current) continue
    ROOM_STYLES[key] = {
      ...current,
      tokens: { ...current.tokens, accent: '#6D28D9', accentDeep: '#2d2350', ink: '#050505' },
      background: forensicBackground,
      glow: '0 0 32px #6D28D944, 0 18px 60px rgba(0,0,0,0.55)',
    }
  }
}

applyIntegrityForensicBranding()

const FALLBACK = style(
  'fallback',
  'Studio',
  'An atmospheric spatial hub for the film pipeline',
  '#8b5cf6',
  '#4c1d95',
)

/**
 * Returns color tokens, titles, subtitles, and an atmospheric CSS background
 * for any studio room key. Unknown keys resolve to a violet/obsidian fallback
 * so callers never need to null-check.
 */
export function getProceduralRoomStyle(roomKey: string): ProceduralRoomStyle {
  const normalized = roomKey.trim().toLowerCase()
  return ROOM_STYLES[normalized] ?? { ...FALLBACK, key: roomKey }
}

export const PROCEDURAL_ROOM_KEYS = Object.keys(ROOM_STYLES)
