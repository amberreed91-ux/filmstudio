import { useCallback, useEffect, useRef, useState } from 'react'
import {
  cancelVisualTrainingJob,
  createVisualTrainingJob,
  getVisualTrainingJob,
  isActiveTrainingStatus,
  isTerminalTrainingStatus,
  listEligibleReferences,
  listReferenceAssets,
  listTrainingProviders,
  listVisualModels,
  trainingCapableProviders,
  visualTrainingError,
  type CreateTrainingJobRequest,
  type ReferenceAsset,
  type TrainingProviderInfo,
  type VisualTrainingJob,
  type VisualTrainingTargetType,
} from '../lib/visualTrainingApi'

/**
 * Data-fetching + async-state owner for the Visual Training workflow.
 *
 * Components own presentation; this hook owns the lifecycle:
 *  - load training providers (existing provider infrastructure — never hardcoded)
 *  - load confirmed, eligible reference assets for the target type
 *  - load registered visual identities (models) for the project + target type
 *  - create a training job and poll it to a terminal state (bounded)
 *  - cancel an active job when the provider supports it
 *
 * The canonical target (character_id / scene_id) is recorded in the job's
 * free-form `configuration` so an existing identity can be matched to a
 * specific character or setting without duplicating canonical records or
 * changing the backend schema. Polling is bounded and cleaned up on unmount;
 * it never continues after a terminal state.
 */

/** Poll cadence and bound for training jobs. Terminal states stop polling. */
const POLL_INTERVAL_MS = 3000
const POLL_TIMEOUT_MS = 15 * 60 * 1000

/** Fields the panel needs to start a job, minus project/target/provider wiring. */
export interface StartTrainingInput {
  /** Canonical entity id (character_id or scene_id) — recorded in configuration. */
  canonicalTargetId: string
  /** Human name for confirmation UI + configuration provenance. */
  canonicalTargetName: string
  triggerWord: string
  sourceAssetIds: string[]
  provider: string
  providerModel: string
  /** Optional existing visual model id to reuse (retraining). */
  visualModelId?: string | null
}

export interface VisualTrainingController {
  projectId: string
  targetType: VisualTrainingTargetType

  providers: TrainingProviderInfo[]
  providersLoading: boolean
  providersError: string

  references: ReferenceAsset[]
  referencesLoading: boolean
  referencesError: string

  models: VisualTrainingJob[]
  modelsLoading: boolean
  modelsError: string

  activeJob: VisualTrainingJob | null
  submitting: boolean
  submitError: string
  cancelling: boolean

  refresh: () => Promise<void>
  startTraining: (input: StartTrainingInput) => Promise<VisualTrainingJob | null>
  cancelTraining: () => Promise<void>
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export function useVisualTraining(
  projectId: string,
  targetType: VisualTrainingTargetType,
): VisualTrainingController {
  const [providers, setProviders] = useState<TrainingProviderInfo[]>([])
  const [providersLoading, setProvidersLoading] = useState(false)
  const [providersError, setProvidersError] = useState('')

  const [references, setReferences] = useState<ReferenceAsset[]>([])
  const [referencesLoading, setReferencesLoading] = useState(false)
  const [referencesError, setReferencesError] = useState('')

  const [models, setModels] = useState<VisualTrainingJob[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [modelsError, setModelsError] = useState('')

  const [activeJob, setActiveJob] = useState<VisualTrainingJob | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [cancelling, setCancelling] = useState(false)

  // Scope guard: discard stale async results across project/target changes.
  const scope = useRef({ projectId, targetType, generation: 0, mounted: true })

  useEffect(() => {
    scope.current = { projectId, targetType, generation: scope.current.generation + 1, mounted: true }
    setActiveJob(null)
    setSubmitError('')
    return () => {
      scope.current.mounted = false
      scope.current.generation += 1
    }
  }, [projectId, targetType])

  const loadProviders = useCallback(async () => {
    if (!projectId) return
    const generation = scope.current.generation
    setProvidersLoading(true)
    setProvidersError('')
    try {
      const result = await listTrainingProviders()
      if (!scope.current.mounted || scope.current.generation !== generation) return
      // Only providers that report the visual_training capability can train an
      // identity. The backend lists every enabled provider, so filter here to
      // avoid offering (or defaulting to) providers that cannot train.
      setProviders(trainingCapableProviders(result.providers))
    } catch (error) {
      if (!scope.current.mounted || scope.current.generation !== generation) return
      setProvidersError(visualTrainingError(error))
    } finally {
      if (scope.current.mounted && scope.current.generation === generation) setProvidersLoading(false)
    }
  }, [projectId])

  const loadReferences = useCallback(async () => {
    if (!projectId) return
    const generation = scope.current.generation
    setReferencesLoading(true)
    setReferencesError('')
    try {
      const result = await listReferenceAssets(projectId)
      if (!scope.current.mounted || scope.current.generation !== generation) return
      setReferences(listEligibleReferences(result.reference_assets || [], targetType))
    } catch (error) {
      if (!scope.current.mounted || scope.current.generation !== generation) return
      setReferencesError(visualTrainingError(error))
    } finally {
      if (scope.current.mounted && scope.current.generation === generation) setReferencesLoading(false)
    }
  }, [projectId, targetType])

  const loadModels = useCallback(async () => {
    if (!projectId) return
    const generation = scope.current.generation
    setModelsLoading(true)
    setModelsError('')
    try {
      // Backend only returns complete models from this endpoint.
      const result = await listVisualModels(projectId, { target_type: targetType, status: 'complete' })
      if (!scope.current.mounted || scope.current.generation !== generation) return
      setModels(result.models || [])
    } catch (error) {
      if (!scope.current.mounted || scope.current.generation !== generation) return
      setModelsError(visualTrainingError(error))
    } finally {
      if (scope.current.mounted && scope.current.generation === generation) setModelsLoading(false)
    }
  }, [projectId, targetType])

  const refresh = useCallback(async () => {
    await Promise.all([loadProviders(), loadReferences(), loadModels()])
  }, [loadProviders, loadReferences, loadModels])

  useEffect(() => {
    if (!projectId) return
    void refresh()
  }, [projectId, refresh])

  /**
   * Bounded poll of a single job until it reaches a terminal state, the timeout
   * elapses, or the hook unmounts / scope changes. Returns the last seen job.
   */
  const pollJob = useCallback(async (jobId: string, generation: number): Promise<VisualTrainingJob | null> => {
    const startedAt = Date.now()
    let current: VisualTrainingJob | null = null
    while (scope.current.mounted && scope.current.generation === generation) {
      try {
        current = await getVisualTrainingJob(jobId)
      } catch (error) {
        if (!scope.current.mounted || scope.current.generation !== generation) return null
        setSubmitError(visualTrainingError(error))
        return null
      }
      if (!scope.current.mounted || scope.current.generation !== generation) return null
      setActiveJob(current)
      if (isTerminalTrainingStatus(current.status)) return current
      if (Date.now() - startedAt > POLL_TIMEOUT_MS) return current
      await sleep(POLL_INTERVAL_MS)
    }
    return current
  }, [])

  const startTraining = useCallback(async (input: StartTrainingInput): Promise<VisualTrainingJob | null> => {
    if (!projectId) return null
    const generation = scope.current.generation
    setSubmitting(true)
    setSubmitError('')
    try {
      const payload: CreateTrainingJobRequest = {
        project_id: projectId,
        target_type: targetType,
        trigger_word: input.triggerWord.trim(),
        source_asset_ids: input.sourceAssetIds,
        provider: input.provider,
        provider_model: input.providerModel,
        visual_model_id: input.visualModelId ?? null,
        // Provenance only — never mutates canonical story truth. Lets the UI
        // match a registered identity back to this specific character/setting.
        configuration: {
          canonical_target_id: input.canonicalTargetId,
          canonical_target_name: input.canonicalTargetName,
        },
      }
      const created = await createVisualTrainingJob(payload)
      if (!scope.current.mounted || scope.current.generation !== generation) return null
      // Seed an active-job view from the create response, then poll for real state.
      setActiveJob({
        job_id: created.job_id,
        project_id: created.project_id,
        visual_model_id: created.visual_model_id,
        target_type: created.target_type,
        trigger_word: input.triggerWord.trim(),
        source_asset_ids: input.sourceAssetIds,
        provider: input.provider,
        provider_model: input.providerModel,
        configuration: payload.configuration ?? {},
        status: created.status,
        created_at: new Date().toISOString(),
        completed_at: null,
        error: null,
        trained_model_id: null,
      })
      const finalJob = isActiveTrainingStatus(created.status)
        ? await pollJob(created.job_id, generation)
        : await getVisualTrainingJob(created.job_id).catch(() => null)
      if (finalJob) setActiveJob(finalJob)
      // Refresh registered identities so a completed model shows as reusable.
      await loadModels()
      return finalJob
    } catch (error) {
      if (scope.current.mounted && scope.current.generation === generation) {
        setSubmitError(visualTrainingError(error))
      }
      return null
    } finally {
      if (scope.current.mounted && scope.current.generation === generation) setSubmitting(false)
    }
  }, [projectId, targetType, pollJob, loadModels])

  const cancelTraining = useCallback(async () => {
    const job = activeJob
    if (!job || !isActiveTrainingStatus(job.status)) return
    const generation = scope.current.generation
    setCancelling(true)
    setSubmitError('')
    try {
      await cancelVisualTrainingJob(job.job_id)
      if (!scope.current.mounted || scope.current.generation !== generation) return
      const updated = await getVisualTrainingJob(job.job_id).catch(() => null)
      if (updated && scope.current.mounted && scope.current.generation === generation) {
        setActiveJob(updated)
      }
    } catch (error) {
      if (scope.current.mounted && scope.current.generation === generation) {
        setSubmitError(visualTrainingError(error))
      }
    } finally {
      if (scope.current.mounted && scope.current.generation === generation) setCancelling(false)
    }
  }, [activeJob])

  return {
    projectId,
    targetType,
    providers,
    providersLoading,
    providersError,
    references,
    referencesLoading,
    referencesError,
    models,
    modelsLoading,
    modelsError,
    activeJob,
    submitting,
    submitError,
    cancelling,
    refresh,
    startTraining,
    cancelTraining,
  }
}

/**
 * Match a registered visual identity to a specific canonical target using the
 * provenance recorded in `configuration` at creation time. Returns the most
 * recently created complete model for that target, or null.
 */
export function findModelForTarget(
  models: VisualTrainingJob[],
  canonicalTargetId: string,
): VisualTrainingJob | null {
  if (!canonicalTargetId) return null
  const matches = models.filter(
    (model) => model.configuration?.canonical_target_id === canonicalTargetId,
  )
  if (matches.length === 0) return null
  return matches.reduce((latest, candidate) =>
    (candidate.created_at || '') > (latest.created_at || '') ? candidate : latest,
  )
}

export type { VisualTrainingJob, TrainingProviderInfo, ReferenceAsset }
