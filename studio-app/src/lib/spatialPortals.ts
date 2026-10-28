/**
 * Navigation targets for the 12 tactical room bays in the 3D soundstage.
 *
 * Kept out of SpatialStudioCanvas.tsx so that file only exports React
 * components (React Fast Refresh requirement). `to` values mirror real
 * APP_ROUTES paths in studio-app/src/routes.tsx; backend routes and studio.db
 * isolation are untouched — these are navigation targets only.
 */

export interface SpatialPortal {
  key: string
  label: string
  sub: string
  to: string
  color: string
  angle: number
  position: [number, number, number]
}

const PORTAL_RADIUS = 6.4

function portalPosition(angle: number): [number, number, number] {
  return [Math.cos(angle) * PORTAL_RADIUS, 0, Math.sin(angle) * PORTAL_RADIUS]
}

// 12 tactical room bays. Angles mirror the standalone ANIMATION_8 staging.
export const SPATIAL_PORTALS: SpatialPortal[] = [
  { key: 'atrium', label: 'The Atrium', sub: 'glass entry pavilion', to: '/studio', color: '#e0e7ff', angle: -Math.PI * 0.64, position: portalPosition(-Math.PI * 0.64) },
  { key: 'gate', label: 'Gate Intake', sub: 'holographic orb vessel', to: '/studio/gate', color: '#38bdf8', angle: -Math.PI * 0.45, position: portalPosition(-Math.PI * 0.45) },
  { key: 'page', label: 'Page', sub: "screenwriter's office", to: '/studio/page', color: '#f59e0b', angle: -Math.PI * 0.3, position: portalPosition(-Math.PI * 0.3) },
  { key: 'board', label: 'Board', sub: 'narrative shot wall', to: '/studio/board', color: '#ec4899', angle: -Math.PI * 0.15, position: portalPosition(-Math.PI * 0.15) },
  { key: 'previs', label: 'Previs Bay', sub: 'virtual production stage', to: '/studio/previs', color: '#a855f7', angle: 0.0, position: portalPosition(0.0) },
  { key: 'screening', label: 'Screening', sub: 'cinema 4K DCP review', to: '/studio/screening-room', color: '#ffffff', angle: Math.PI * 0.16, position: portalPosition(Math.PI * 0.16) },
  { key: 'universe', label: 'Universe', sub: 'spatial constellation graph', to: '/studio/universe-graph', color: '#818cf8', angle: Math.PI * 0.32, position: portalPosition(Math.PI * 0.32) },
  { key: 'vault', label: 'The Vault', sub: 'spatial helix cold store', to: '/studio/archive', color: '#38bdf8', angle: Math.PI * 0.48, position: portalPosition(Math.PI * 0.48) },
  { key: 'production', label: 'Production Desk', sub: 'command telemetry desk', to: '/studio/production-desk', color: '#2dd4bf', angle: Math.PI * 0.64, position: portalPosition(Math.PI * 0.64) },
  { key: 'integrity', label: 'Integrity Engine', sub: 'laser quarantine chamber', to: '/studio/integrity', color: '#10b981', angle: Math.PI * 0.82, position: portalPosition(Math.PI * 0.82) },
  { key: 'reference', label: 'Reference Atelier', sub: 'visual dev mood boards', to: '/studio/reference-space', color: '#f43f5e', angle: Math.PI * 0.98, position: portalPosition(Math.PI * 0.98) },
  { key: 'project', label: 'Project Room', sub: 'focus enclave workstation', to: '/studio/slate', color: '#8b5cf6', angle: -Math.PI * 0.82, position: portalPosition(-Math.PI * 0.82) },
]
