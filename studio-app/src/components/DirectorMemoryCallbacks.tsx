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
  // One scan result per scene. Tagging the result with the scene it belongs
  // to means a scene switch reads as loading until its own scan lands, with
  // no synchronous state reset inside the effect.
  type ScanState =
    | { scene: Record<string, unknown>; projectId: string; sceneIndex: number | undefined; status: 'ready'; callbacks: DirectorMemoryCallback[] }
    | { scene: Record<string, unknown>; projectId: string; sceneIndex: number | undefined; status: 'error'; message: string }
  const [scan, setScan] = useState<ScanState | null>(null)

  useEffect(() => {
    let cancelled = false
    if (!projectId || !scene) return
    scanSceneForDirectorMemory(projectId, scene, sceneIndex)
      .then((result) => {
        if (!cancelled) {
          setScan({ scene, projectId, sceneIndex, status: 'ready', callbacks: result.callbacks ?? [] })
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setScan({
            scene,
            projectId,
            sceneIndex,
            status: 'error',
            message: error instanceof Error ? error.message : 'Failed to scan memory',
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [projectId, scene, sceneIndex])

  if (!scene) return null
  const current = scan && scan.scene === scene && scan.projectId === projectId && scan.sceneIndex === sceneIndex
    ? scan
    : null
  if (!current) {
    return (
      <div className="text-xs text-zinc-400">Consulting director's memory…</div>
    )
  }
  if (current.status === 'error') {
    return (
      <div className="rounded border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-100">
        {current.message}
      </div>
    )
  }
  const callbacks = current.callbacks
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
