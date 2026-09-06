import { fetchJson } from './studioApi'

export type CharacterCastingGeneration = {
  id: string
  status: 'queued' | 'running' | 'complete' | 'partial' | 'failed'
  requested_count: number
  completed_count: number
  direction: string
  error: string | null
  created_at: string
  matches_current_profile: boolean
}

export type CharacterLook = {
  character_id: string
  project_id: string
  name: string
  age: string | null
  description: string
  physical_description: string
  visual_prompt_summary: string
  status: 'draft' | 'locked'
  version: number
  profile_revision: string
  face_image_url: string | null
  body_image_url: string | null
  approved_at: string | null
  candidates: Array<{ image_url: string; role: string; source: string; generation_id?: string | null; matches_current_profile?: boolean }>
  casting_generations?: CharacterCastingGeneration[]
}

export type CharacterCastingRequest = { expected_profile_revision: string; request_id: string; direction: string }

export function generateCharacterCasting(projectId: string, characterId: string, payload: CharacterCastingRequest) {
  return fetchJson<CharacterLook>(`${lookPath(projectId, characterId)}/casting`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  })
}

export function characterLookError(error: unknown): string {
  const message = error instanceof Error ? error.message : 'Could not update this character look. Please try again.'
  try {
    const detail: unknown = JSON.parse(message)
    if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') return detail.message
  } catch { /* Shared fetchJson also returns ordinary message strings. */ }
  return message
}

const projectPath = (projectId: string) => `/api/f51/studio/projects/${encodeURIComponent(projectId)}`
const lookPath = (projectId: string, characterId: string) => `${projectPath(projectId)}/characters/${encodeURIComponent(characterId)}/look`

export function listCharacterLooks(projectId: string) {
  return fetchJson<{ looks: CharacterLook[] }>(`${projectPath(projectId)}/character-looks`)
}

export function getCharacterLook(projectId: string, characterId: string) {
  return fetchJson<CharacterLook>(lookPath(projectId, characterId))
}

export function uploadCharacterLookReference(projectId: string, characterId: string, file: File) {
  const body = new FormData()
  body.append('file', file)
  return fetchJson<{ image_url: string }>(`${lookPath(projectId, characterId)}/reference`, { method: 'POST', body })
}

export function approveCharacterLook(projectId: string, characterId: string, payload: {
  expected_profile_revision: string
  face_image_url: string
  body_image_url?: string | null
}) {
  return fetchJson<CharacterLook>(`${lookPath(projectId, characterId)}/approve`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  })
}

export function reviseCharacterLook(projectId: string, characterId: string, profileRevision: string) {
  return fetchJson<CharacterLook>(`${lookPath(projectId, characterId)}/revise`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ expected_profile_revision: profileRevision }),
  })
}
