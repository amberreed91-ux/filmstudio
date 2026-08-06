import { buildStudioApiUrl } from './studioApi'

export async function fetchOptionalJson<T>(path: string, signal?: AbortSignal): Promise<T | null> {
  const response = await fetch(buildStudioApiUrl(path), {
    headers: { Accept: 'application/json' },
    signal,
  })

  if (response.status === 404) return null

  const text = await response.text()
  if (!response.ok) {
    let detail = text || `HTTP ${response.status}`
    if (text) {
      try {
        const body = JSON.parse(text) as { detail?: unknown; message?: unknown }
        const candidate = body.detail ?? body.message
        if (typeof candidate === 'string') detail = candidate
      } catch {
        // Preserve the response text when the server did not return JSON.
      }
    }
    throw new Error(detail)
  }

  if (!text) throw new Error(`Empty JSON response from ${path}`)
  try {
    return JSON.parse(text) as T
  } catch {
    throw new Error(`Invalid JSON response from ${path}`)
  }
}
