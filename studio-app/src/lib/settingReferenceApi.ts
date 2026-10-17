import { fetchJson } from './studioApi'

/**
 * Exact entity scope for the Scene 002 setting authority lifecycle.
 *
 * Every helper below is hard-wired to this project + setting pair: the setting
 * ID is never inferred from a scene ID, a shot, a URI, an image, or legacy sync
 * output. The legacy scene-targeted reference ID is named only so callers can
 * reject it — no helper may ever mutate or select it.
 */
export const SCENE002_PROJECT_ID = 'project_5907c60cddbc'
export const SCENE002_SETTING_ID = 'loc-c8f88b9c'
export const LEGACY_SCENE002_REFERENCE_ID = 'ref_env_6b726885ed67ae4d'

export type SettingReferenceAsset = {
  ref_id: string
  project_id: string
  kind: string
  image_url: string
  source_shot_id?: string | null
  target_type: string
  target_id: string
  category?: string | null
  approval_state: string
  canonical: boolean
  source_kind?: string
  created_at?: string | null
}

export type SettingReferenceListResponse = {
  project_id: string
  target_type: 'setting'
  target_id: string
  reference_assets: SettingReferenceAsset[]
  count: number
}

/** Exact-target rows only: anything outside setting/loc-c8f88b9c in this project is dropped. */
export function exactSettingReferenceRows(
  projectId: string,
  rows: SettingReferenceAsset[] | undefined | null,
): SettingReferenceAsset[] {
  if (!Array.isArray(rows)) return []
  return rows.filter(row =>
    row !== null
    && typeof row === 'object'
    && row.project_id === projectId
    && row.target_type === 'setting'
    && row.target_id === SCENE002_SETTING_ID
    && row.kind === 'environment'
    && row.ref_id !== LEGACY_SCENE002_REFERENCE_ID,
  )
}

function requireExactProject(projectId: string): string {
  if (projectId !== SCENE002_PROJECT_ID) {
    throw new Error('Setting authority references are scoped to the exact Scene 002 project')
  }
  return projectId
}

function requireExactReferenceId(referenceId: string): string {
  const id = String(referenceId || '').trim()
  if (!id || id === LEGACY_SCENE002_REFERENCE_ID) {
    throw new Error('A fresh exact-setting reference ID is required')
  }
  return id
}

const scopePath = (projectId: string, settingId: string = SCENE002_SETTING_ID) =>
  `/api/f51/studio/projects/${encodeURIComponent(requireExactProject(projectId))}/setting-references/${encodeURIComponent(settingId)}`

/**
 * Sync-free scoped read. This endpoint never runs creator reference sync, and
 * this client deliberately has no helper for the legacy reference-library GET.
 */
export function listSettingReferences(projectId: string): Promise<SettingReferenceListResponse> {
  return fetchJson<SettingReferenceListResponse>(scopePath(projectId))
}

/** Register an image URI as a fresh candidate for the exact setting. */
export function createSettingReference(projectId: string, imageUrl: string, category: string = 'environment'): Promise<{ reference_asset: SettingReferenceAsset }> {
  const image_url = String(imageUrl || '').trim()
  if (!image_url) throw new Error('An image URI is required')
  return fetchJson<{ reference_asset: SettingReferenceAsset }>(scopePath(projectId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_url, category }),
  })
}

/** Register an uploaded image as a fresh candidate for the exact setting (create-only). */
export function uploadSettingReference(projectId: string, file: File, category: string = 'environment'): Promise<{ reference_asset: SettingReferenceAsset }> {
  const form = new FormData()
  form.append('file', file)
  form.append('category', category)
  return fetchJson<{ reference_asset: SettingReferenceAsset }>(`${scopePath(projectId)}/upload`, {
    method: 'POST',
    body: form,
    timeoutMs: 60000,
    timeoutLabel: 'Setting reference upload',
  })
}

/** Durable rejection. Changes only this exact reference's approval state. */
export function rejectSettingReference(projectId: string, referenceId: string): Promise<{ reference_asset: SettingReferenceAsset }> {
  const refId = requireExactReferenceId(referenceId)
  return fetchJson<{ reference_asset: SettingReferenceAsset }>(`${scopePath(projectId)}/${encodeURIComponent(refId)}/reject`, { method: 'POST' })
}

/** Explicit approval. Changes approval state only — never canonical, never retargeted. */
export function approveSettingReference(projectId: string, referenceId: string): Promise<{ reference_asset: SettingReferenceAsset }> {
  const refId = requireExactReferenceId(referenceId)
  return fetchJson<{ reference_asset: SettingReferenceAsset }>(`${scopePath(projectId)}/${encodeURIComponent(refId)}/approve`, { method: 'POST' })
}

/** Explicit canonical designation. Requires an already-approved exact-target environment reference. */
export function designateSettingReferenceCanonical(projectId: string, referenceId: string): Promise<{ reference_asset: SettingReferenceAsset }> {
  const refId = requireExactReferenceId(referenceId)
  return fetchJson<{ reference_asset: SettingReferenceAsset }>(`${scopePath(projectId)}/${encodeURIComponent(refId)}/canonical`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ canonical: true }),
  })
}
