import { normalizeJobStatus } from './jobStatus'
import type { RenderJob } from './studioApi'

// Match app.utils.helpers for manual and auto-split pipeline identifiers.
export function parseShotIdentity(shotId: string): { sceneId: string; shotNumber: number } {
  const sceneId = shotId.match(/scene_\d+/)?.[0]
    ?? (shotId.includes('_') ? shotId.split('_').slice(0, 2).join('_') : shotId)
  return { sceneId, shotNumber: Number(shotId.match(/_(\d+)$/)?.[1] ?? 0) }
}

export function sceneShotTakes(jobs: RenderJob[], projectId: string, sceneId: string): Record<number, RenderJob[]> {
  const grouped: Record<number, RenderJob[]> = {}
  const seen = new Set<string>()
  const ordered = [...jobs].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '') || b.id.localeCompare(a.id))
  for (const job of ordered) {
    if (job.project_id !== projectId || normalizeJobStatus(job.status) !== 'complete' || !job.output_payload?.asset_url?.trim() || seen.has(job.id)) continue
    const identity = parseShotIdentity(job.shot_id || job.input_payload?.shot_id || '')
    if (identity.sceneId !== sceneId || identity.shotNumber <= 0) continue
    seen.add(job.id)
    const takes = grouped[identity.shotNumber] ??= []
    takes.push(job)
  }
  return grouped
}
