/**
 * useProactiveCoDirector
 *
 * Calls the proactive co-director backend and manages card state.
 *
 * Rules:
 *  - Silent by default — only surfaces when should_surface: true
 *  - Once dismissed, never re-appears in the same session (sessionStorage key)
 *  - Never throws — errors are swallowed silently
 *
 * Usage:
 *   const { check, card, dismiss, saveToNotes } = useProactiveCoDirector()
 *
 *   // On scene save:
 *   await check('scene_save', { sceneId: 'scene_001' })
 *
 *   // On project open:
 *   await check('project_open', { lastEdited: project.updated_at })
 *
 *   // On Screening Room mount:
 *   await check('cut_assembly')
 */

import { useCallback, useState } from 'react'
import { buildStudioApiUrl } from '../lib/studioApi'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TriggerType = 'scene_save' | 'project_open' | 'cut_assembly'

export interface ProactiveCheck {
  should_surface: boolean
  message: string
  trigger_type: TriggerType
  save_to_notes: boolean
}

export interface ProactiveCard {
  message: string
  trigger_type: TriggerType
  save_to_notes: boolean
}

interface CheckOptions {
  sceneId?: string
  lastEdited?: string
}

// ---------------------------------------------------------------------------
// Session-level dismiss tracking (survives re-renders, resets on tab close)
// ---------------------------------------------------------------------------

function getDismissKey(projectId: string, triggerType: TriggerType): string {
  return `proactive_dismissed:${projectId}:${triggerType}`
}

function isDismissed(projectId: string, triggerType: TriggerType): boolean {
  try {
    return sessionStorage.getItem(getDismissKey(projectId, triggerType)) === '1'
  } catch {
    return false
  }
}

function markDismissed(projectId: string, triggerType: TriggerType): void {
  try {
    sessionStorage.setItem(getDismissKey(projectId, triggerType), '1')
  } catch {
    // sessionStorage unavailable — ignore
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useProactiveCoDirector(projectId: string) {
  const [card, setCard] = useState<ProactiveCard | null>(null)

  const check = useCallback(
    async (triggerType: TriggerType, options: CheckOptions = {}) => {
      if (!projectId) return

      // Already dismissed this trigger in this session
      if (isDismissed(projectId, triggerType)) return

      try {
        const body: Record<string, string> = { trigger_type: triggerType }
        if (options.sceneId) body.scene_id = options.sceneId
        if (options.lastEdited) body.last_edited = options.lastEdited

        const res = await fetch(
          buildStudioApiUrl(`/api/f51/studio/projects/${projectId}/co-director/proactive-check`),
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          },
        )

        if (!res.ok) return

        const data: ProactiveCheck = await res.json()

        if (data.should_surface && data.message) {
          setCard({
            message: data.message,
            trigger_type: data.trigger_type,
            save_to_notes: data.save_to_notes,
          })
        }
      } catch {
        // Silent — never block the user's workflow
      }
    },
    [projectId],
  )

  const dismiss = useCallback(() => {
    if (card) {
      markDismissed(projectId, card.trigger_type)
    }
    setCard(null)
  }, [card, projectId])

  const saveToNotes = useCallback(
    async (onSaved?: () => void) => {
      // Dismiss the card regardless
      dismiss()
      // Caller can handle the actual save (e.g. append to director memory)
      onSaved?.()
    },
    [dismiss],
  )

  return { check, card, dismiss, saveToNotes }
}
