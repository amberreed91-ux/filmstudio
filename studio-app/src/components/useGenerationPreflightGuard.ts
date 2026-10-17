import { useCallback, useEffect, useRef, useState } from 'react'
import { getGenerationPreflight, type GenerationPreflight } from '../lib/studioApi'

export type PreflightGuardStatus = 'idle' | 'checking' | 'ready' | 'blocked' | 'error' | 'stale'

/**
 * Single-shot generation guard over the backend's own preflight.
 *
 * No readiness decisions are made here: the hook fetches the backend's
 * batch preflight for the scene and reports the verdict for the requested
 * shot exactly as the backend returned it. The Generate action re-runs the
 * preflight first (final preflight before generation) and is refused when
 * the shot is blocked, the backend errored, or the result went stale.
 */
export function useGenerationPreflightGuard(
  projectId: string,
  sceneId: string,
  shotNumber: number,
  provider?: string,
  revision?: number,
) {
  const [preflight, setPreflight] = useState<GenerationPreflight | null>(null)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState('')
  const [stale, setStale] = useState(false)
  const keyRef = useRef('')

  const check = useCallback(async () => {
    if (!projectId || !sceneId) return
    setChecking(true)
    setError('')
    try {
      const result = await getGenerationPreflight(projectId, sceneId, provider || undefined)
      setPreflight(result)
      setStale(false)
      return result
    } catch (err) {
      setPreflight(null)
      setError(err instanceof Error ? err.message : 'Generation preflight is unavailable')
      return null
    } finally {
      setChecking(false)
    }
  }, [projectId, sceneId, provider])

  useEffect(() => {
    void check()
  }, [check])

  // Scene/provider changes invalidate the displayed verdict immediately.
  useEffect(() => {
    const key = `${projectId}::${sceneId}::${provider || ''}`
    if (keyRef.current === '') {
      keyRef.current = key
      return
    }
    if (keyRef.current !== key) {
      keyRef.current = key
      setStale(true)
    }
  }, [projectId, sceneId, provider])

  // External revision bumps (storyboard/scene mutations) invalidate the
  // displayed verdict and immediately re-run the read-only preflight.
  const revisionRef = useRef(revision)
  useEffect(() => {
    if (revisionRef.current === revision) return
    revisionRef.current = revision
    if (projectId && sceneId) {
      setStale(true)
      void check()
    }
  }, [revision, check, projectId, sceneId])

  const markStale = useCallback(() => setStale(true), [])

  const entry =
    preflight?.entries?.find(
      (candidate) => String(candidate.shot_id || '').endsWith(`_shot_${String(shotNumber).padStart(3, '0')}`),
    ) || null
  const shotBlockers = entry?.blockers || []

  // Batch authorization (R4.1A) is all-or-nothing: when the backend refuses
  // to authorize any shot in the scene, this shot is blocked too.
  const authorizationReady = !preflight?.authorization || preflight.authorization.ready === true

  const status: PreflightGuardStatus = checking
    ? 'checking'
    : error
      ? 'error'
      : stale
        ? 'stale'
        : preflight
          ? (preflight.ready && authorizationReady && shotBlockers.length === 0 ? 'ready' : 'blocked')
          : 'idle'

  /**
   * Final preflight before generation. Runs a FRESH backend check and
   * authorizes the render only from that fresh result. When it returns
   * ``authorized: false`` the caller must not generate and should display
   * the returned backend blockers.
   */
  const authorizeFinal = useCallback(async (): Promise<{ authorized: boolean; blockers: string[] }> => {
    const fresh = await check()
    if (!fresh) {
      return { authorized: false, blockers: [error || 'Generation preflight is unavailable'] }
    }    if (!fresh.ready) {
      return { authorized: false, blockers: fresh.blockers || [] }
    }
    if (fresh.authorization && fresh.authorization.ready === false) {
      const failures = (fresh.authorization.shots || [])
        .filter((shot) => !shot.ok)
        .map((shot) => shot.message || shot.shot_id || 'This shot failed batch authorization.')
      return {
        authorized: false,
        blockers: failures.length > 0 ? failures : ['The batch failed authorization preflight.'],
      }
    }
    const freshEntry =
      fresh.entries?.find(
        (candidate) => String(candidate.shot_id || '').endsWith(`_shot_${String(shotNumber).padStart(3, '0')}`),
      ) || null
    const blockers = freshEntry?.blockers || []
    return { authorized: blockers.length === 0, blockers }
  }, [check, shotNumber, error])

  return { preflight, status, checking, error, stale, shotBlockers, entry, check, markStale, authorizeFinal }
}
