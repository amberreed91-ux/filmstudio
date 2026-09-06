import { useCallback, useEffect, useRef, useState } from 'react'
import { getSceneDirection, saveSceneDirection, type AssignedDialogue, type SceneDirection, type ShotHandoff } from '../lib/sceneDirectionApi'

export function useSceneDirection(project: string, scene: string, version: string) {
  const [data, setData] = useState<SceneDirection | null>(null)
  const [busy, setBusy] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const request = useRef(0)
  const invalidateRequest = useCallback(() => { ++request.current }, [])
  const scope = `${project}/${scene}/${version}`
  const activeScope = useRef(scope)
  activeScope.current = scope
  useEffect(() => {
    const sequence = ++request.current
    let disposed = false
    setData(null); setDirty(false); setError(''); setBusy(true)
    getSceneDirection(project, scene).then(value => {
      if (!disposed && sequence === request.current) setData(value)
    }).catch(reason => {
      if (!disposed && sequence === request.current) setError(reason instanceof Error ? reason.message : 'Could not load scene direction')
    }).finally(() => { if (!disposed && sequence === request.current) setBusy(false) })
    return () => { disposed = true; invalidateRequest() }
  }, [project, scene, version, reload, invalidateRequest])
  const editLine = useCallback((id: string, patch: Partial<AssignedDialogue>) => {
    setData(value => value && ({ ...value, dialogue: value.dialogue.map(line => line.line_id === id ? { ...line, ...patch } : line) })); setDirty(true)
  }, [])
  const removeLine = useCallback((id: string) => {
    setData(value => value && ({ ...value, dialogue: value.dialogue.filter(line => line.line_id !== id) })); setDirty(true)
  }, [])
  const addLine = useCallback(() => {
    setData(value => value && ({ ...value, dialogue: [...value.dialogue, { line_id: `line_${crypto.randomUUID()}`, character: '', text: '', shot_id: null }] })); setDirty(true)
  }, [])
  const editHandoff = useCallback((id: string, patch: Partial<ShotHandoff>) => {
    setData(value => value && ({ ...value, shots: value.shots.map(shot => shot.shot_id === id ? { ...shot, ...patch } : shot) })); setDirty(true)
  }, [])
  const save = async () => {
    if (!data || busy) return null
    const sequence = ++request.current
    setBusy(true); setError('')
    try {
      const result = await saveSceneDirection(project, scene, {
        expected_version_id: data.version_id, dialogue: data.dialogue,
        handoffs: data.shots.map(({ shot_id, opening_state, action_change, ending_state }) => ({ shot_id, opening_state, action_change, ending_state })),
      })
      if (scope !== activeScope.current || sequence !== request.current) return null
      setData(result); setDirty(false)
      return result
    } catch (reason) {
      if (scope === activeScope.current && sequence === request.current) setError(reason instanceof Error ? reason.message : 'Could not save scene direction')
      return null
    } finally { if (scope === activeScope.current && sequence === request.current) setBusy(false) }
  }
  return { data, busy, dirty, error, editLine, removeLine, addLine, editHandoff, save, reload: () => setReload(value => value + 1) }
}
