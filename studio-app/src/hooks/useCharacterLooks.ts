import { useCallback, useEffect, useRef, useState } from 'react'
import {
  approveCharacterLook, characterLookError, getCharacterLook, listCharacterLooks, reviseCharacterLook,
  uploadCharacterLookReference, type CharacterLook,
  generateCharacterCasting, type CharacterCastingRequest,
} from '../lib/characterLookApi'

type LookState = { projectId: string; looks: CharacterLook[]; loading: boolean; error: string; busy: boolean }

/** Server approvals are authoritative; stale responses never cross film boundaries. */
export function useCharacterLooks(projectId: string) {
  const [state, setState] = useState<LookState>({ projectId, looks: [], loading: true, error: '', busy: false })
  const scope = useRef({ projectId, generation: 0, mounted: true })
  const mutation = useRef(false)
  const castingRequests = useRef(new Map<string, CharacterCastingRequest>())
  const refresh = useCallback(async () => {
    const generation = ++scope.current.generation
    if (!projectId) return
    setState((previous) => ({ ...previous, projectId, loading: true, error: '' }))
    try {
      const response = await listCharacterLooks(projectId)
      if (!scope.current.mounted || scope.current.projectId !== projectId || scope.current.generation !== generation) return
      setState((previous) => ({ ...previous, projectId, looks: response.looks, loading: false, error: '' }))
    } catch (error) {
      if (!scope.current.mounted || scope.current.projectId !== projectId || scope.current.generation !== generation) return
      setState((previous) => ({ ...previous, loading: false, error: characterLookError(error) }))
    }
  }, [projectId])

  useEffect(() => {
    scope.current = { projectId, generation: scope.current.generation + 1, mounted: true }
    mutation.current = false
    castingRequests.current.clear()
    setState({ projectId, looks: [], loading: Boolean(projectId), error: '', busy: false })
    void refresh()
    return () => { scope.current.mounted = false; scope.current.generation += 1 }
  }, [projectId, refresh])

  const run = useCallback(async <T,>(action: () => Promise<T>, apply: (result: T) => void): Promise<T | null> => {
    if (mutation.current || !projectId) return null
    mutation.current = true
    scope.current.generation += 1
    const operationScope = scope.current
    setState((previous) => ({ ...previous, busy: true, error: '' }))
    try {
      const result = await action()
      if (scope.current !== operationScope || !scope.current.mounted) return null
      // Any older read cannot replace a newly saved approval.
      scope.current.generation += 1
      apply(result)
      return result
    } catch (error) {
      if (scope.current === operationScope && scope.current.mounted) {
        setState((previous) => ({ ...previous, error: characterLookError(error) }))
      }
      return null
    } finally {
      if (scope.current === operationScope && scope.current.mounted) {
        mutation.current = false
        setState((previous) => ({ ...previous, busy: false, loading: false }))
      }
    }
  }, [projectId])

  const replace = useCallback((look: CharacterLook) => {
    setState((previous) => ({ ...previous, looks: previous.looks.map((item) => item.character_id === look.character_id ? look : item) }))
  }, [])
  const approve = useCallback((look: CharacterLook, faceImageUrl: string, bodyImageUrl: string | null) => run(
    () => approveCharacterLook(projectId, look.character_id, { expected_profile_revision: look.profile_revision, face_image_url: faceImageUrl, body_image_url: bodyImageUrl }), replace,
  ), [projectId, run, replace])
  const revise = useCallback((look: CharacterLook) => run(
    () => reviseCharacterLook(projectId, look.character_id, look.profile_revision), replace,
  ), [projectId, run, replace])
  const upload = useCallback(async (look: CharacterLook, file: File) => {
    const result = await run(async () => {
      const reference = await uploadCharacterLookReference(projectId, look.character_id, file)
      const updatedLook = await getCharacterLook(projectId, look.character_id)
      return { ...reference, look: updatedLook }
    }, (reference) => replace(reference.look))
    return result?.image_url ?? null
  }, [projectId, run, replace])

  const generate = useCallback(async (look: CharacterLook, direction = '') => {
    const operationScope = scope.current
    const previous = castingRequests.current.get(look.character_id)
    // A transport error can occur after the backend accepted the request. Keep
    // its ID until we have observed it, so a manual retry cannot pay twice.
    const observed = look.casting_generations?.some((job) => job.id === previous?.request_id)
    const request = previous && previous.direction === direction.trim() && previous.expected_profile_revision === look.profile_revision && !observed
      ? previous
      : { request_id: crypto.randomUUID(), direction: direction.trim(), expected_profile_revision: look.profile_revision }
    castingRequests.current.set(look.character_id, request)
    const result = await run(() => generateCharacterCasting(projectId, look.character_id, request), replace)
    if (result) castingRequests.current.delete(look.character_id)
    else if (scope.current === operationScope && scope.current.mounted) {
      // Recover only by reading. Never repeat image generation on a timer.
      const generation = scope.current.generation
      try {
        const recovered = await getCharacterLook(projectId, look.character_id)
        if (scope.current === operationScope && scope.current.mounted && !mutation.current && scope.current.generation === generation) replace(recovered)
      } catch { /* The original submission error remains visible with Refresh. */ }
    }
    return result
  }, [projectId, run, replace])

  const pending = state.projectId === projectId && state.looks.some((look) => look.casting_generations?.some((job) => job.status === 'queued' || job.status === 'running'))
  useEffect(() => {
    if (!pending || state.busy || state.loading || !projectId) return
    const operationScope = scope.current
    let cancelled = false
    let failures = 0
    const deadline = Date.now() + 12 * 60 * 1000
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      if (Date.now() >= deadline) {
        if (!cancelled) setState((previous) => ({ ...previous, error: 'Casting status took too long. Refresh to check the saved progress.' }))
        return
      }
      const generation = scope.current.generation
      try {
        const response = await listCharacterLooks(projectId)
        if (cancelled || scope.current !== operationScope || !scope.current.mounted || mutation.current || scope.current.generation !== generation) return
        setState((previous) => ({ ...previous, looks: response.looks, error: '' }))
        failures = 0
      } catch (error) {
        failures += 1
        if (!cancelled && scope.current === operationScope && scope.current.mounted && !mutation.current) {
          setState((previous) => ({ ...previous, error: characterLookError(error) }))
        }
      } finally {
        if (!cancelled && failures < 3) timer = setTimeout(() => { void poll() }, 3000)
      }
    }
    timer = setTimeout(() => { void poll() }, 1500)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [pending, projectId, state.busy, state.loading])

  const current = state.projectId === projectId ? state : { projectId, looks: [], loading: Boolean(projectId), error: '', busy: false }
  return { ...current, refresh, approve, revise, upload, generate }
}

export type CharacterLooksController = ReturnType<typeof useCharacterLooks>
