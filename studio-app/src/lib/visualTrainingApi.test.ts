import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  cancelVisualTrainingJob,
  createVisualTrainingJob,
  defaultTriggerWordFor,
  eligibleKindsForTarget,
  getShotReferenceConfirmation,
  getVisualTrainingJob,
  isActiveTrainingStatus,
  isTerminalTrainingStatus,
  listEligibleReferences,
  listReferenceAssets,
  listSceneReferenceConfirmations,
  listTrainingProviders,
  listVisualModels,
  recordShotReferenceConfirmation,
  trainingCapableProviders,
  trainingStatusLabel,
  validateTriggerWord,
  visualTrainingError,
  type ReferenceAsset,
  type TrainingProviderInfo,
} from './visualTrainingApi'

afterEach(() => vi.unstubAllGlobals())

function stubJson(body: unknown, ok = true) {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: ok ? 200 : 400 }))
  vi.stubGlobal('fetch', request)
  return request
}

const ref = (over: Partial<ReferenceAsset> = {}): ReferenceAsset => ({
  ref_id: 'ref_1',
  kind: 'character_face',
  image_url: '/outputs/ref.png',
  project_id: 'film-a',
  ...over,
})

describe('visual training API contract', () => {
  it('lists training providers from the shared provider infrastructure', async () => {
    const request = stubJson({ providers: [{ provider_id: 'local_training', name: 'Local', is_simulated: true, capabilities: ['visual_training'], models: ['local-visual-v1'] }] })
    const result = await listTrainingProviders()
    expect(request.mock.calls[0][0]).toContain('/api/f51/studio/visual-training/providers')
    expect(result.providers[0].provider_id).toBe('local_training')
  })

  it('creates a job with the exact backend DTO body and project scope', async () => {
    const request = stubJson({ job_id: 'job-1', visual_model_id: 'vm_1', project_id: 'film-a', target_type: 'character', status: 'pending', message: 'created' })
    const payload = {
      project_id: 'film-a',
      target_type: 'character' as const,
      trigger_word: 'MAYA',
      source_asset_ids: ['ref_1', 'ref_2'],
      provider: 'local_training',
      provider_model: 'local-visual-v1',
      visual_model_id: null,
      configuration: { canonical_target_id: 'maya', canonical_target_name: 'Maya' },
    }
    await createVisualTrainingJob(payload)
    expect(request.mock.calls[0][0]).toContain('/api/f51/studio/visual-training/jobs')
    expect(request.mock.calls[0][1].method).toBe('POST')
    // The request body must match the backend CreateTrainingJobRequest exactly.
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual(payload)
  })

  it('fetches a single job by id', async () => {
    const request = stubJson({ job_id: 'job-1', status: 'training' })
    await getVisualTrainingJob('job 1')
    expect(request.mock.calls[0][0]).toContain('/visual-training/jobs/job%201')
  })

  it('lists visual models scoped to a single project and target type', async () => {
    const request = stubJson({ models: [] })
    await listVisualModels('film-a', { target_type: 'scene', status: 'complete' })
    const url = request.mock.calls[0][0] as string
    // Project isolation: the project id is always part of the query.
    expect(url).toContain('/visual-training/models?')
    expect(url).toContain('project_id=film-a')
    expect(url).toContain('target_type=scene')
    expect(url).toContain('status=complete')
  })

  it('cancels a job through the existing endpoint', async () => {
    const request = stubJson({ job_id: 'job-1', status: 'cancelled', message: 'cancelled' })
    await cancelVisualTrainingJob('job-1')
    expect(request.mock.calls[0][0]).toContain('/visual-training/jobs/job-1/cancel')
    expect(request.mock.calls[0][1].method).toBe('POST')
  })

  it('lists confirmed reference assets from the project reference registry', async () => {
    const request = stubJson({ reference_assets: [ref()], count: 1 })
    const result = await listReferenceAssets('film-a')
    expect(request.mock.calls[0][0]).toContain('/api/f51/studio/projects/film-a/reference-assets')
    expect(result.reference_assets[0].ref_id).toBe('ref_1')
  })
})

describe('reference eligibility filtering', () => {
  it('character training only allows approved face/full-body references', () => {
    const assets = [
      ref({ ref_id: 'a', kind: 'character_face', approval_state: 'approved' }),
      ref({ ref_id: 'b', kind: 'character_full', approval_state: 'approved' }),
      ref({ ref_id: 'c', kind: 'environment', approval_state: 'approved' }),
      ref({ ref_id: 'd', kind: 'style', approval_state: 'approved' }),
    ]
    const eligible = listEligibleReferences(assets, 'character')
    expect(eligible.map((a) => a.ref_id)).toEqual(['a', 'b'])
    expect(eligibleKindsForTarget('character')).toEqual(['character_face', 'character_full'])
  })

  it('setting training only allows approved environment references, independently of character refs', () => {
    const assets = [
      ref({ ref_id: 'a', kind: 'character_face', approval_state: 'approved' }),
      ref({ ref_id: 'b', kind: 'environment', approval_state: 'approved' }),
      ref({ ref_id: 'c', kind: 'environment', approval_state: 'approved' }),
    ]
    const eligible = listEligibleReferences(assets, 'scene')
    expect(eligible.map((a) => a.ref_id)).toEqual(['b', 'c'])
    expect(eligibleKindsForTarget('scene')).toEqual(['environment'])
  })

  it('keeps synced generated candidates out of training until they are approved', () => {
    const assets = [
      ref({ ref_id: 'gen-cand', kind: 'character_face', approval_state: 'candidate', source_kind: 'generated' }),
      ref({ ref_id: 'gen-ok', kind: 'character_face', approval_state: 'approved', source_kind: 'generated' }),
    ]
    expect(listEligibleReferences(assets, 'character').map((a) => a.ref_id)).toEqual(['gen-ok'])
  })

  it('excludes candidate, rejected, and unknown-state assets even when the kind matches', () => {
    const assets = [
      ref({ ref_id: 'ok', kind: 'character_face', approval_state: 'approved' }),
      ref({ ref_id: 'cand', kind: 'character_face', approval_state: 'candidate' }),
      ref({ ref_id: 'rej', kind: 'character_face', approval_state: 'rejected' }),
      ref({ ref_id: 'unknown', kind: 'character_face', approval_state: undefined }),
      ref({ ref_id: 'env-ok', kind: 'environment', approval_state: 'approved' }),
      ref({ ref_id: 'env-cand', kind: 'environment', approval_state: 'candidate' }),
    ]
    expect(listEligibleReferences(assets, 'character').map((a) => a.ref_id)).toEqual(['ok'])
    expect(listEligibleReferences(assets, 'scene').map((a) => a.ref_id)).toEqual(['env-ok'])
  })
})

describe('training-capable provider filtering', () => {
  const provider = (over: Partial<TrainingProviderInfo> = {}): TrainingProviderInfo => ({
    provider_id: 'p',
    name: 'P',
    is_simulated: false,
    capabilities: [],
    models: [],
    ...over,
  })

  it('keeps only providers that report the visual_training capability', () => {
    const providers = [
      provider({ provider_id: 'runway', name: 'Runway', capabilities: ['video_generation', 'image_to_video'] }),
      provider({ provider_id: 'local_training', name: 'Local Visual Training', is_simulated: true, capabilities: ['visual_training'], models: ['local-visual-v1'] }),
    ]
    const capable = trainingCapableProviders(providers)
    expect(capable.map((p) => p.provider_id)).toEqual(['local_training'])
    expect(capable[0].models).toEqual(['local-visual-v1'])
  })

  it('returns an empty list when no provider can train (drives the unavailable empty state)', () => {
    const providers = [
      provider({ provider_id: 'runway', capabilities: ['video_generation'] }),
      provider({ provider_id: 'wan', capabilities: ['text_to_video'] }),
    ]
    expect(trainingCapableProviders(providers)).toEqual([])
  })

  it('tolerates null/undefined input', () => {
    expect(trainingCapableProviders(undefined)).toEqual([])
    expect(trainingCapableProviders(null)).toEqual([])
  })
})

describe('training status helpers', () => {
  it('treats complete/failed/cancelled as terminal so polling stops', () => {
    expect(isTerminalTrainingStatus('complete')).toBe(true)
    expect(isTerminalTrainingStatus('failed')).toBe(true)
    expect(isTerminalTrainingStatus('cancelled')).toBe(true)
    expect(isTerminalTrainingStatus('pending')).toBe(false)
    expect(isTerminalTrainingStatus('training')).toBe(false)
  })

  it('treats pending/training as active so polling continues', () => {
    expect(isActiveTrainingStatus('pending')).toBe(true)
    expect(isActiveTrainingStatus('training')).toBe(true)
    expect(isActiveTrainingStatus('complete')).toBe(false)
  })

  it('maps status to filmmaker-facing labels without percentages', () => {
    expect(trainingStatusLabel('pending')).toBe('Preparing')
    expect(trainingStatusLabel('training')).toBe('Training')
    expect(trainingStatusLabel('complete')).toBe('Ready')
    expect(trainingStatusLabel('failed')).toBe('Failed')
    expect(trainingStatusLabel('cancelled')).toBe('Cancelled')
  })
})

describe('durable shot confirmation contract (R4.2)', () => {
  it('records an explicit confirmation with only the digest in the body', async () => {
    const request = stubJson({ project_id: 'film-a', scene_id: 'scene_001', shot_id: 'scene_001_shot_001', status: 'confirmed', confirmed_digest: 'abc', current_digest: 'abc', created_at: '', updated_at: '' })
    const result = await recordShotReferenceConfirmation('film-a', 'scene_001_shot_001', 'abc')
    expect(request.mock.calls[0][0]).toContain('/api/f51/studio/projects/film-a/shots/scene_001_shot_001/reference-binding-confirmation')
    expect(request.mock.calls[0][1].method).toBe('POST')
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ expected_digest: 'abc' })
    expect(result.status).toBe('confirmed')
  })

  it('recovers one shot confirmation read-only', async () => {
    const request = stubJson({ project_id: 'film-a', scene_id: 'scene_001', shot_id: 'scene_001_shot_001', status: 'stale', confirmed_digest: 'abc', current_digest: 'def', created_at: '', updated_at: '' })
    const result = await getShotReferenceConfirmation('film-a', 'scene_001_shot_001')
    expect(request.mock.calls[0][0]).toContain('/api/f51/studio/projects/film-a/shots/scene_001_shot_001/reference-binding-confirmation')
    expect(request.mock.calls[0][1]?.method ?? 'GET').not.toBe('POST')
    expect(result.status).toBe('stale')
  })

  it('recovers every scene confirmation with the scene scope in the query', async () => {
    const request = stubJson({ project_id: 'film-a', scene_id: 'scene_001', confirmations: [], count: 0 })
    const result = await listSceneReferenceConfirmations('film-a', 'scene_001')
    expect(request.mock.calls[0][0]).toContain('/api/f51/studio/projects/film-a/reference-binding-confirmations?scene_id=scene_001')
    expect(result.count).toBe(0)
  })
})

describe('trigger word + error helpers', () => {
  it('derives a letters-only default identity token from a target name', () => {
    expect(defaultTriggerWordFor('Maya')).toBe('MAYA')
    expect(defaultTriggerWordFor('Abandoned Chicago Apartment')).toBe('ABANDONEDCHICAGOAPARTMENT')
    expect(defaultTriggerWordFor('')).toBe('IDENTITY')
    // The suggested default must satisfy the frontend validator (backend contract).
    expect(validateTriggerWord(defaultTriggerWordFor('Maya'))).toBe('')
  })

  it('rejects tokens the backend would reject, with an actionable error', () => {
    expect(validateTriggerWord('')).toMatch(/trigger word/i)
    expect(validateTriggerWord('MAYA_IDENTITY')).toMatch(/letters only/i)
    expect(validateTriggerWord('mrz07')).toMatch(/letters only/i)
    expect(validateTriggerWord('AB')).toMatch(/3–32/i)
    expect(validateTriggerWord('MAYA')).toBe('')
  })

  it('surfaces the real backend error message', () => {
    expect(visualTrainingError(new Error('Provider not configured'))).toBe('Provider not configured')
    expect(visualTrainingError(undefined)).toMatch(/unavailable/i)
  })
})

describe('previs render opt-in contract', () => {
  it('sends visual_model_id only when a trained identity is explicitly chosen', async () => {
    const { generatePrevisScene } = await import('./studioApi')
    const request = stubJson({ job_id: 'r1', status: 'pending', scene_id: 'scene_1', duplicate: false })
    await generatePrevisScene('film-a', 'scene_1', {
      renderSettings: { duration_seconds: 4, resolution: '720p', visual_model_id: 'vm_1' },
    })
    const body = JSON.parse(request.mock.calls[0][1].body)
    expect(body.visual_model_id).toBe('vm_1')
  })

  it('leaves the render payload unchanged when no identity is selected (backward compatible)', async () => {
    const { generatePrevisScene } = await import('./studioApi')
    const request = stubJson({ job_id: 'r1', status: 'pending', scene_id: 'scene_1', duplicate: false })
    await generatePrevisScene('film-a', 'scene_1', {
      renderSettings: { duration_seconds: 4, resolution: '720p', visual_model_id: undefined },
    })
    const body = JSON.parse(request.mock.calls[0][1].body)
    expect('visual_model_id' in body).toBe(false)
  })
})
