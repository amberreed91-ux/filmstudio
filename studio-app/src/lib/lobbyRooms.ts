/**
 * Room directory and Blender-export constants for the interactive 3D lobby.
 *
 * Kept out of Interactive3DLobby.tsx so that component file only exports
 * React components (React Fast Refresh requirement). Routes mirror the
 * existing 2D room paths in studio-app/src/routes.tsx exactly — no room load
 * logic is touched. Backend routes + studio.db isolation are untouched;
 * these are navigation targets only.
 */

/**
 * Designated drop-in for custom Blender exports.
 * Place `studio_lobby.glb` (or `.gltf`) in `studio-app/public/models/`.
 */
export const LOBBY_MODEL_URL = '/models/studio_lobby.glb'

export async function isLobbyModelAvailable(url: string = LOBBY_MODEL_URL): Promise<boolean> {
  try {
    const res = await fetch(url, { method: 'HEAD' })
    return res.ok
  } catch {
    return false
  }
}

export interface LobbyRoom {
  id: string
  label: string
  description: string
  to: string
  color: string
  position: [number, number, number]
}

const RADIUS = 5.2

function polar(index: number, total: number, y: number): [number, number, number] {
  const angle = (index / total) * Math.PI * 2 - Math.PI / 2
  return [Math.cos(angle) * RADIUS, y, Math.sin(angle) * RADIUS]
}

// Tactical directory — the 12 soundstage bays from the ANIMATION_8 spec.
export const LOBBY_ROOMS: LobbyRoom[] = [
  { id: 'atrium', label: 'The Atrium', description: 'Glass entry pavilion', to: '/studio', color: '#e0e7ff', position: polar(0, 12, 1.1) },
  { id: 'gate', label: 'Gate Intake', description: 'Holographic orb vessel', to: '/studio/gate', color: '#38bdf8', position: polar(1, 12, 1.1) },
  { id: 'page', label: 'Page', description: "Screenwriter's office", to: '/studio/page', color: '#f59e0b', position: polar(2, 12, 1.1) },
  { id: 'board', label: 'Board', description: 'Narrative shot wall', to: '/studio/board', color: '#ec4899', position: polar(3, 12, 1.1) },
  { id: 'previs', label: 'Previs Bay', description: 'Virtual production stage', to: '/studio/previs', color: '#a855f7', position: polar(4, 12, 1.0) },
  { id: 'screening', label: 'Screening', description: 'Cinema 4K DCP review', to: '/studio/screening-room', color: '#ffffff', position: polar(5, 12, 1.1) },
  { id: 'universe', label: 'Universe', description: 'Spatial constellation graph', to: '/studio/universe-graph', color: '#818cf8', position: polar(6, 12, 1.1) },
  { id: 'vault', label: 'The Vault', description: 'Spatial helix cold store', to: '/studio/archive', color: '#38bdf8', position: polar(7, 12, 1.1) },
  { id: 'production', label: 'Production Desk', description: 'Command telemetry desk', to: '/studio/production-desk', color: '#2dd4bf', position: polar(8, 12, 1.1) },
  { id: 'integrity', label: 'Integrity Engine', description: 'Laser quarantine chamber', to: '/studio/integrity', color: '#10b981', position: polar(9, 12, 1.1) },
  { id: 'reference', label: 'Reference Atelier', description: 'Visual dev mood boards', to: '/studio/reference-space', color: '#f43f5e', position: polar(10, 12, 1.1) },
  { id: 'project', label: 'Project Room', description: 'Focus enclave workstation', to: '/studio/slate', color: '#8b5cf6', position: polar(11, 12, 1.1) },
]
