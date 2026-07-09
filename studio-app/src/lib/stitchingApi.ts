/**
 * Stitching API client
 *
 * POST /api/f51/studio/projects/{id}/stitch
 * GET  /api/f51/studio/projects/{id}/stitch/status
 * GET  /api/f51/studio/projects/{id}/stitch/download
 */

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8010'

export interface StitchJob {
  job_id: string
  project_id: string
  status: 'pending' | 'running' | 'complete' | 'failed' | 'not_started'
  progress: number
  current_scene: string | null
  scenes_total: number
  scenes_done: number
  output_path: string | null
  output_url: string | null
  error: string | null
  transitions_used: string[]
  scene_count: number
  started_at: number | null
  finished_at: number | null
  advisory: string
  mock_mode?: boolean
}

export interface StitchTriggerResponse {
  job: StitchJob
  advisory: string
}

export interface StitchDownloadResponse {
  output_url: string
  download_url: string
  mock_mode: boolean
  advisory: string
}

async function fetchStitch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`Stitch API ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

/** Trigger a full film stitch for the project. */
export async function triggerStitch(projectId: string): Promise<StitchTriggerResponse> {
  return fetchStitch<StitchTriggerResponse>(
    `/api/f51/studio/projects/${projectId}/stitch`,
    { method: 'POST' },
  )
}

/** Poll stitching job status. */
export async function getStitchStatus(projectId: string): Promise<StitchJob> {
  return fetchStitch<StitchJob>(`/api/f51/studio/projects/${projectId}/stitch/status`)
}

/** Get download URL for the final stitched film. */
export async function getStitchDownload(
  projectId: string,
): Promise<StitchDownloadResponse | null> {
  try {
    return await fetchStitch<StitchDownloadResponse>(
      `/api/f51/studio/projects/${projectId}/stitch/download`,
    )
  } catch {
    return null
  }
}
