import { useCallback, useEffect, useRef, useState } from 'react'
import { chooseTake, getTakeChoices, type SceneTakeChoices } from '../lib/takeSelectionApi'

export function useTakeSelection(projectId: string, sceneId: string) {
  const scope = `${projectId}/${sceneId}`
  const activeScope = useRef(scope)
  activeScope.current = scope
  const request = useRef(0)
  const [state, setState] = useState<{ scope: string; data?: SceneTakeChoices; busy: boolean; error: string }>({ scope, busy: true, error: '' })
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let disposed = false
    const sequence = ++request.current
    if (!projectId || !sceneId) return
    setState({ scope, busy: true, error: '' })
    getTakeChoices(projectId, sceneId).then(data => {
      if (!disposed && sequence === request.current) setState({ scope, data, busy: false, error: '' })
    }).catch(error => {
      if (!disposed && sequence === request.current) setState({ scope, busy: false, error: error instanceof Error ? error.message : 'Could not load take choices' })
    })
    return () => { disposed = true }
  }, [projectId, sceneId, scope])
  const save = useCallback(async (shotNumber: number, jobId: string | null) => {
    const sequence = ++request.current
    setState(previous => ({ ...previous, scope, busy: true, error: '' }))
    try {
      const data = await chooseTake(projectId, sceneId, shotNumber, jobId)
      if (activeScope.current === scope && sequence === request.current) {
        setState({ scope, data, busy: false, error: '' })
        setRevision(value => value + 1)
      }
    } catch (error) {
      if (activeScope.current === scope && sequence === request.current) setState(previous => ({ ...previous, busy: false, error: error instanceof Error ? error.message : 'Could not save take choice' }))
    }
  }, [projectId, sceneId, scope])
  return { choices: state.scope === scope ? state.data?.choices ?? [] : [], busy: state.scope !== scope || state.busy, error: state.scope === scope ? state.error : '', save, revision }
}
