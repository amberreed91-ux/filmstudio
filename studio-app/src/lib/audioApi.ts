/**
 * Audio Generation API client
 *
 * Wraps the backend audio generation endpoints:
 *   POST /api/f51/studio/projects/{id}/scenes/{scene_id}/audio/generate
 *   GET  /api/f51/studio/projects/{id}/scenes/{scene_id}/audio/status
 *   GET  /api/f51/studio/projects/{id}/audio/status
 *   GET  /api/f51/studio/audio/capabilities
 */

const BASE = '/api/f51/studio'

export type TrackStatus = 'pending' | 'generating' | 'complete' | 'failed' | 'skipped' | 'mock'

export interface TrackResult {
  track?: string
  status: TrackStatus
  file_path?: string
  file_url?: string
  prompt_used?: string
  text_used?: string
  advisory?: string
  error?: string
}

export interface AudioJobResult {
  job_id: string
  project_id: string
  scene_id: string
  status: 'pending' | 'generating' | 'complete' | 'failed'
  mock_mode: boolean
  advisory: string
  tracks: {
    dialogue?: TrackResult
    score?: TrackResult
    ambient?: TrackResult
  }
  started_at?: string
  completed_at?: string
  error?: string
}

export interface AudioCapabilities {
  mock_mode: boolean
  tts_available: boolean
  audiocraft_available: boolean
  torch_available: boolean
  tts_model: string
  musicgen_model: string
  apple_silicon_supported: boolean
  install_hint: string | null
}

export interface AudioGenerateRequest {
  scene_description?: string
  mood?: string
  score_notes?: string
  ambient_notes?: string
  silence_flag?: boolean
  /** Regenerate a single track: "dialogue" | "score" | "ambient" */
  track?: 'dialogue' | 'score' | 'ambient'
}

async function fetchAudio<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`Audio API ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

export function generateSceneAudio(
  projectId: string,
  sceneId: string,
  body: AudioGenerateRequest = {},
): Promise<AudioJobResult> {
  return fetchAudio<AudioJobResult>(
    `${BASE}/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}/audio/generate`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function getSceneAudioStatus(
  projectId: string,
  sceneId: string,
): Promise<AudioJobResult> {
  return fetchAudio<AudioJobResult>(
    `${BASE}/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}/audio/status`,
  )
}

export function getProjectAudioStatus(projectId: string): Promise<{
  project_id: string
  mock_mode: boolean
  scenes: Record<string, AudioJobResult>
  total_scenes: number
}> {
  return fetchAudio(
    `${BASE}/projects/${encodeURIComponent(projectId)}/audio/status`,
  )
}

export function getAudioCapabilities(): Promise<AudioCapabilities> {
  return fetchAudio<AudioCapabilities>(`${BASE}/audio/capabilities`)
}
