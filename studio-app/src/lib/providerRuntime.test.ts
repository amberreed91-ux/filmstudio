import { describe, expect, it } from 'vitest'
import { generateSceneOutcomeCopy, providerModeFromJob, providerTruthLabel } from './providerRuntime'

describe('provider runtime truth labels', () => {
  it('labels mock success providers clearly', () => {
    expect(
      providerTruthLabel({
        provider_id: 'runway',
        name: 'Runway',
        status: 'available',
        is_simulated: false,
        capabilities: [],
        active_jobs: 0,
        queued_jobs: 0,
        provider_mode: 'mock_success',
      }),
    ).toContain('Mock Success Mode')
  })

  it('labels hosted api key missing clearly', () => {
    expect(
      providerTruthLabel({
        provider_id: 'runway',
        name: 'Runway',
        status: 'available',
        is_simulated: false,
        capabilities: [],
        active_jobs: 0,
        queued_jobs: 0,
        provider_mode: 'unavailable',
        missing_requirements: ['api_key'],
      }),
    ).toContain('api_key required')
  })

  it('extracts provider mode from normalized job metadata', () => {
    expect(
      providerModeFromJob({
        id: 'job-1',
        project_id: 'p1',
        shot_id: 's1',
        provider: 'runway',
        status: 'complete',
        progress: 100,
        input_payload: { shot_id: 's1', prompt: '', referenceAssets: [], parameters: {} },
        output_payload: {
          asset_url: '/outputs/mock-video/sample.mp4',
          thumbnail_url: '/outputs/mock-video/sample.mp4',
          metadata: {
            provider_response_normalized: {
              metadata: { provider_mode: 'mock_success' },
            },
          },
        },
        retry_count: 0,
        created_at: '',
        updated_at: '',
      }),
    ).toBe('mock_success')
  })

  it('generate scene copy distinguishes mock and hosted modes', () => {
    expect(generateSceneOutcomeCopy('mock_success')).toContain('mock preview')
    expect(generateSceneOutcomeCopy('hosted_api')).toContain('Submitting to Runway')
  })
})
