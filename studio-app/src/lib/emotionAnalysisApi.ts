import { fetchOptionalJson } from './optionalStudioApi'
import { fetchJson } from './studioApi'

export type EmotionMetricGroup = {
  engagement: number
  tension: number
  emotional_impact: number
}

export type EmotionAnalysisResult = {
  scene_id: string
  general: EmotionMetricGroup
  cinephile: EmotionMetricGroup
  genre_fan: EmotionMetricGroup
}

export type EmotionAnalysisEnvelope = {
  analysis_id: string
  project_id: string
  scene_id: string
  context_hash: string
  provider: string
  model: string
  cached: boolean
  provider_call: boolean
  created_at: string
  updated_at: string
  analysis: EmotionAnalysisResult
}

function scenePath(projectId: string, sceneId: string): string {
  return `/api/f51/studio/emotion-analysis/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}`
}

export async function getCachedSceneEmotion(
  projectId: string,
  sceneId: string,
  signal?: AbortSignal,
): Promise<EmotionAnalysisEnvelope | null> {
  return fetchOptionalJson<EmotionAnalysisEnvelope>(scenePath(projectId, sceneId), signal)
}

export async function analyzeSceneEmotion(
  projectId: string,
  sceneId: string,
  options: { force?: boolean } = {},
): Promise<EmotionAnalysisEnvelope> {
  return fetchJson<EmotionAnalysisEnvelope>(`${scenePath(projectId, sceneId)}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmed: true, force: options.force === true }),
    timeoutLabel: 'Emotion analysis',
  })
}
