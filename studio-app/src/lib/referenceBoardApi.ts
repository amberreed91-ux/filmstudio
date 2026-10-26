import { fetchJson } from './studioApi'

/**
 * Read-only reference-board API.
 *
 * Every request is a GET against the confirmed reference registry and always
 * carries `sync=0`, so the board never triggers creator-reference sync
 * writes. No uploads, approvals, designations, confirmations, or generation
 * live here — those stay in their authoritative surfaces.
 */

export type BoardAsset = {
  ref_id: string
  kind: string
  image_url: string
  source_shot_id?: string | null
  project_id: string
  target_type?: 'character' | 'setting' | null
  target_id?: string | null
  category?: string | null
  approval_state?: 'candidate' | 'approved' | 'rejected'
  canonical?: boolean
  source_kind?: 'confirmed' | 'uploaded' | 'generated'
}

export type BoardLibrary = {
  project_id: string
  target_type: 'character' | 'setting'
  target_id: string
  canonical: BoardAsset | null
  supporting: BoardAsset[]
  candidates: BoardAsset[]
  categories: string[]
  coverage: string
}

export type BoardAssetsResponse = {
  reference_assets: BoardAsset[]
  count: number
}

export function listReferenceBoardAssets(projectId: string) {
  return fetchJson<BoardAssetsResponse>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/reference-assets?sync=0`,
  )
}

export function getReferenceBoardLibrary(
  projectId: string,
  targetType: 'character' | 'setting',
  targetId: string,
) {
  return fetchJson<BoardLibrary>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/reference-library/${targetType}/${encodeURIComponent(targetId)}?sync=0`,
  )
}
