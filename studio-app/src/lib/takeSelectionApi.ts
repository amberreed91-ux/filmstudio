import { fetchJson } from './studioApi'

export type SceneTakeChoices = {
  project_id: string
  scene_id: string
  choices: { shot_number: number; job_id: string | null }[]
}

const endpoint = (projectId: string, sceneId: string) =>
  `/api/f51/studio/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}/take-choices`

export function getTakeChoices(projectId: string, sceneId: string): Promise<SceneTakeChoices> {
  return fetchJson(endpoint(projectId, sceneId))
}

export function chooseTake(projectId: string, sceneId: string, shotNumber: number, jobId: string | null): Promise<SceneTakeChoices> {
  return fetchJson(`${endpoint(projectId, sceneId)}/${shotNumber}`, {
    method: 'PUT', body: JSON.stringify({ job_id: jobId }),
  })
}
