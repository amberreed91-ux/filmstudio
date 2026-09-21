/**
 * Scene emotional guidance — advisory only.
 *
 * Surfaces the emotional work a scene is doing and, only when a concrete
 * signal is present, a single actionable risk. Never displays numeric scores
 * or percentages, and stays silent when the signals are too thin to say
 * anything specific.
 */

import { useEffect, useState } from 'react'

import type { SceneEmotionalGuidance } from '../lib/studioApi'
import { getSceneEmotionalGuidance } from '../lib/studioApi'

export interface SceneEmotionalGuidancePanelProps {
  sceneId: string | null | undefined
  /** Optional preloaded guidance for controlled parents and tests. */
  guidance?: SceneEmotionalGuidance | null
  className?: string
}

interface LoadedGuidance {
  sceneId: string
  value: SceneEmotionalGuidance | null
}

export default function SceneEmotionalGuidancePanel({
  sceneId,
  guidance,
  className,
}: SceneEmotionalGuidancePanelProps) {
  const controlled = guidance !== undefined
  const [loaded, setLoaded] = useState<LoadedGuidance | null>(null)

  useEffect(() => {
    if (controlled || !sceneId) return
    let cancelled = false
    getSceneEmotionalGuidance(sceneId)
      .then((result) => {
        if (!cancelled) setLoaded({ sceneId, value: result })
      })
      .catch(() => {
        if (!cancelled) setLoaded({ sceneId, value: null })
      })
    return () => {
      cancelled = true
    }
  }, [sceneId, controlled])

  if (!controlled && !sceneId) return null

  // Loading is derived, never set in an effect: when the loaded payload does
  // not belong to the current scene the fetch is still in flight. Tagging the
  // payload with its scene id also keeps a previous scene's guidance from
  // flashing while the next one loads.
  const value = controlled
    ? guidance ?? null
    : loaded && loaded.sceneId === sceneId
      ? loaded.value
      : null
  const loading = !controlled && Boolean(sceneId) && loaded?.sceneId !== sceneId
  const callbacks = value?.callbacks ?? []
  const hasContent = Boolean(value?.emotional_work || value?.guidance || value?.risk || callbacks.length)

  if (!hasContent) {
    if (loading) {
      return <p className="text-[11px] text-zinc-400">Reading the scene’s emotional work…</p>
    }
    return null
  }

  return (
    <section
      className={
        className ??
        'rounded-xl border border-white/10 bg-black/30 p-4 text-sm leading-relaxed text-zinc-300'
      }
      data-testid="scene-emotional-guidance"
      aria-label="Scene emotional guidance"
    >
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-200/80">
        Emotional guidance
      </p>
      {value?.emotional_work && <p>{value.emotional_work}</p>}
      {value?.guidance && (
        <div className="mt-3">
          <p className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">Guidance</p>
          <p className="mt-0.5">{value.guidance}</p>
        </div>
      )}
      {value?.risk && (
        <div className="mt-3 border-l-2 border-amber-200/40 pl-3">
          <p className="text-[10px] uppercase tracking-[0.12em] text-amber-200/70">Risk</p>
          <p className="mt-0.5 text-amber-50">{value.risk}</p>
        </div>
      )}
      {callbacks.length > 0 && (
        <div className="mt-3">
          <p className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">Memory callbacks</p>
          <ul className="mt-1.5 space-y-1.5">
            {callbacks.map((callback, index) => (
              <li key={`${callback.kind}-${index}`} className="text-[12px] leading-snug text-zinc-300">
                <span className="mr-1 text-[10px] uppercase tracking-[0.1em] text-amber-300/80">
                  {callback.kind}
                </span>
                {callback.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
