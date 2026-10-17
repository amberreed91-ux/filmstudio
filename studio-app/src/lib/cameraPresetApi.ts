import { fetchJson } from './studioApi'

export type CameraPreset = { id: string; label: string; category: string; description: string; camera: string; framing: string }
export type CameraLens = { id: string; label: string; category: string; description: string; lens_language: string }
export type CameraFocalLength = { id: string; label: string; mm: number; framing_hint: string }
export type CameraAperture = { id: string; label: string; f_stop: string; depth_hint: string }
export type CameraPresetCatalog = {
  presets: CameraPreset[]
  views: Array<{ id: string; label: string; camera: string }>
  framings: Array<{ id: string; label: string; framing: string }>
  lenses: CameraLens[]
  focal_lengths: CameraFocalLength[]
  apertures: CameraAperture[]
}
export type CameraPlan = { camera: string; framing: string; lens?: string; focal_length?: string; aperture?: string }
export type CameraShotRecommendation = {
  preset_id: string
  preset_label: string
  view_id: string
  framing_id: string
  lens_id: string
  focal_length_id: string
  aperture_id: string
  camera: string
  framing: string
  lens_language: string
  focal_length: string
  aperture: string
  shot_label: string
  why: string
}

export function recommendCameraForShot(scene: Record<string, unknown>, shotNumber: number, totalShots?: number) {
  return fetchJson<CameraShotRecommendation>('/api/camera-presets/recommend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scene,
      shot_number: Math.max(1, shotNumber || 1),
      ...(totalShots && totalShots > 0 ? { total_shots: totalShots } : {}),
    }),
  })
}

export type CameraSceneRecommendations = { total_shots: number; recommendations: CameraShotRecommendation[] }

export function recommendCamerasForScene(scene: Record<string, unknown>, totalShots: number) {
  return fetchJson<CameraSceneRecommendations>('/api/camera-presets/recommend-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scene, total_shots: Math.max(1, Math.min(12, totalShots || 3)) }),
  })
}

export function getCameraPresets(signal?: AbortSignal) {
  return fetchJson<CameraPresetCatalog>('/api/camera-presets', { signal })
}

/** Map the persisted storyboard DTO into the editable camera plan. */
export function cameraPlanFromVisualPlan(visualPlan?: Record<string, unknown>): Partial<CameraPlan> {
  return {
    ...(typeof visualPlan?.camera_movement === 'string' && visualPlan.camera_movement.trim() ? { camera: visualPlan.camera_movement } : {}),
    ...(typeof visualPlan?.framing === 'string' && visualPlan.framing.trim() ? { framing: visualPlan.framing } : {}),
    ...(typeof visualPlan?.lens_language === 'string' && visualPlan.lens_language.trim() ? { lens: visualPlan.lens_language } : {}),
    ...(typeof visualPlan?.aperture === 'string' && visualPlan.aperture.trim() ? { aperture: visualPlan.aperture } : {}),
    ...(typeof visualPlan?.focal_length_mm === 'number' ? { focal_length: `${visualPlan.focal_length_mm}mm` } : {}),
  }
}
