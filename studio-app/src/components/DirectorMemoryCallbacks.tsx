/**
 * Inline co-director callbacks for the scene detail view.
 *
 * Scans the provided scene against Director's Memory and renders advisory
 * suggestions. Never displays numeric scores or percentages.
 */

import { useEffect, useState } from 'react'

import type { DirectorMemoryCallback } from '../types/directorMemory'
import { scanSceneForDirectorMemory } from '../lib/studioApi'

export interface DirectorMemoryCallbacksProps {
  projectId: string
  scene: Record<string, unknown> | null | undefined
  sceneIndex?: number
}

export default function DirectorMemoryCallbacks({
  projectId,
  scene,
  sceneIndex,
}: DirectorMemoryCallbacksProps) {
  const [callbacks, setCallbacks] = useState<DirectorMemoryCallback[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    if (!projectId || !scene) {
      setCallbacks([])
      return () => {
        cancelled = true
      }
    }
    setLoading(true)
    setError(null)
    scanSceneForDirectorMemory(projectId, scene, sceneIndex)
      .then((result) => {
        if (!cancelled) setCallbacks(result.callbacks ?? [])
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to scan memory')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [projectId, scene, sceneIndex])

  if (!scene) return null
  if (loading) {
    return (
      <div className="text-[11px] text-zinc-400">Consulting director's memory…</div>
    )
  }
  if (error) {
    return (
      <div className="rounded border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-100">
        {error}
      </div>
    )
  }
  if (callbacks.length === 0) return null

  return (
    <aside
      className="director-memory-callbacks rounded border border-amber-400/30 bg-amber-500/5 px-3 py-2"
      aria-label="Director's memory callbacks"
    >
      <div className="text-[10px] uppercase tracking-[0.12em] text-amber-200">
        Co-director — memory callbacks
      </div>
      <ul className="mt-2 space-y-1.5">
        {callbacks.map((callback, index) => (
          <li
            key={`${callback.kind}-${callback.entry_id ?? 'na'}-${index}`}
            className="text-[12px] leading-snug text-amber-50"
          >
            <span className="mr-1 text-[10px] uppercase tracking-[0.1em] text-amber-300/80">
              {callback.kind}
            </span>
            {callback.message}
          </li>
        ))}
      </ul>
    </aside>
  )
}
