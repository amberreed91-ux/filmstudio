import { useCallback, useEffect, useRef, useState } from 'react'
import {
  listVisualModels,
  visualTrainingError,
  type VisualTrainingJob,
} from '../lib/visualTrainingApi'

/**
 * Loads the complete (ready) visual identities for a project across both
 * target types so Previs can offer them as opt-in production assets. This is a
 * read-only fetch hook; it never creates or mutates identities. Project scoped
 * by construction (the backend filters by project_id).
 */
export interface AvailableIdentities {
  characterIdentities: VisualTrainingJob[]
  settingIdentities: VisualTrainingJob[]
  loading: boolean
  error: string
  refresh: () => Promise<void>
}

export function useAvailableIdentities(projectId: string, refreshKey: number = 0): AvailableIdentities {
  const [characterIdentities, setCharacterIdentities] = useState<VisualTrainingJob[]>([])
  const [settingIdentities, setSettingIdentities] = useState<VisualTrainingJob[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const scope = useRef({ projectId, generation: 0, mounted: true })

  const refresh = useCallback(async () => {
    if (!projectId) {
      setCharacterIdentities([])
      setSettingIdentities([])
      return
    }
    const generation = ++scope.current.generation
    setLoading(true)
    setError('')
    try {
      const [characters, settings] = await Promise.all([
        listVisualModels(projectId, { target_type: 'character', status: 'complete' }),
        listVisualModels(projectId, { target_type: 'scene', status: 'complete' }),
      ])
      if (!scope.current.mounted || scope.current.generation !== generation) return
      setCharacterIdentities(characters.models || [])
      setSettingIdentities(settings.models || [])
    } catch (err) {
      if (!scope.current.mounted || scope.current.generation !== generation) return
      setError(visualTrainingError(err))
    } finally {
      if (scope.current.mounted && scope.current.generation === generation) setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    scope.current = { projectId, generation: scope.current.generation + 1, mounted: true }
    void refresh()
    return () => {
      scope.current.mounted = false
      scope.current.generation += 1
    }
    // `refreshKey` lets a host view force a refetch after a sibling trains a new
    // identity in the same session (e.g. Previs setting training → opt-in picker).
  }, [projectId, refreshKey, refresh])

  return { characterIdentities, settingIdentities, loading, error, refresh }
}
