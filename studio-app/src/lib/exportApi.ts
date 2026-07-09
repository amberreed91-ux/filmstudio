/**
 * Final Export API client
 *
 * POST /api/f51/studio/projects/{id}/export
 * GET  /api/f51/studio/projects/{id}/export/status
 * GET  /api/f51/studio/projects/{id}/export/download
 */

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8010'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ExportOptions {
  include_title_card?: boolean
  title_card_duration?: number
  include_end_card?: boolean
  end_card_duration?: number
  resolution?: '720p' | '1080p' | '4K'
  format?: 'mp4' | 'mov'
  quality?: 'low' | 'medium' | 'high'
  filmmaker_name?: string
}

export interface ExportJob {
  job_id: string
  project_id: string
  status: 'pending' | 'running' | 'complete' | 'failed' | 'not_started'
  progress: number
  options: ExportOptions
  output_path: string | null
  output_url: string | null
  error: string | null
  started_at: number | null
  finished_at: number | null
  advisory: string
  mock_mode?: boolean
}

export interface ExportTriggerResponse {
  job: ExportJob
  advisory: string
}

export interface ExportDownloadResponse {
  output_url: string
  download_url: string
  mock_mode: boolean
  advisory: string
}

// ---------------------------------------------------------------------------
// Fetch helper
// ---------------------------------------------------------------------------

async function fetchExport<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`Export API ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/** Trigger a final export with the given options. */
export async function triggerExport(
  projectId: string,
  options: ExportOptions = {},
): Promise<ExportTriggerResponse> {
  return fetchExport<ExportTriggerResponse>(
    `/api/f51/studio/projects/${projectId}/export`,
    { method: 'POST', body: JSON.stringify(options) },
  )
}

/** Poll export job status. */
export async function getExportStatus(projectId: string): Promise<ExportJob> {
  return fetchExport<ExportJob>(
    `/api/f51/studio/projects/${projectId}/export/status`,
  )
}

/** Get download info for the exported film. */
export async function getExportDownload(
  projectId: string,
): Promise<ExportDownloadResponse | null> {
  try {
    return await fetchExport<ExportDownloadResponse>(
      `/api/f51/studio/projects/${projectId}/export/download`,
    )
  } catch {
    return null
  }
}
