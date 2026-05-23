import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { ComponentProps } from 'react'
import ProductionExecutionBay from './ProductionExecutionBay'

function renderBay(overrides: Partial<ComponentProps<typeof ProductionExecutionBay>> = {}) {
  return renderToStaticMarkup(
    <MemoryRouter>
      <ProductionExecutionBay
        projectId="demo_studio_cinematic_001"
        projectTitle="Demo Production"
        decisionGate={null}
        renderJobs={[]}
        onRetryFailedRender={() => {}}
        {...overrides}
      />
    </MemoryRouter>,
  )
}

describe('ProductionExecutionBay', () => {
  it('renders execution bay structure', () => {
    const html = renderBay()
    expect(html).toContain('Execution Hero')
    expect(html).toContain('Render Queue Timeline')
    expect(html).toContain('Studio Ops Notes')
  })

  it('shows honest empty job copy', () => {
    const html = renderBay({ renderJobs: [] })
    expect(html).toContain('No render jobs yet. Move from Previs into production.')
  })

  it('shows screening-ready guidance for completed jobs', () => {
    const html = renderBay({
      renderJobs: [
        {
          id: 'job-1',
          project_id: 'demo_studio_cinematic_001',
          shot_id: 'shot_001',
          provider: 'mock_success',
          status: 'completed',
          progress: 100,
          retry_count: 0,
          created_at: '2026-05-21T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
          output_payload: { asset_url: '/outputs/mock-video/sample.mp4', thumbnail_url: '/outputs/mock-video/sample.mp4', metadata: {} },
        },
      ],
    })
    expect(html).toContain('ready for screening')
    expect(html).toContain('/studio/screening-room?project_id=demo_studio_cinematic_001')
  })

  it('renders selected job hosted video preview when output exists', () => {
    const html = renderBay({
      renderJobs: [
        {
          id: 'job-hosted',
          project_id: 'demo_studio_cinematic_001',
          shot_id: 'shot_001',
          provider: 'runway',
          status: 'completed',
          progress: 100,
          retry_count: 0,
          created_at: '2026-05-21T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
          output_payload: {
            asset_url: 'https://cdn.hosted.example.com/shot.mp4',
            metadata: {
              provider_response_normalized: { metadata: { provider_mode: 'hosted_api' } },
            },
          },
        },
      ],
    })
    expect(html).toContain('<video')
    expect(html).toContain('https://cdn.hosted.example.com/shot.mp4')
  })

  it('prefers hosted output from render pool for selected shot context', () => {
    const html = renderBay({
      renderJobs: [
        {
          id: 'job-local-first',
          project_id: 'demo_studio_cinematic_001',
          shot_id: 'shot_001',
          provider: 'mock_success',
          status: 'completed',
          progress: 100,
          retry_count: 0,
          created_at: '2026-05-21T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
          output_payload: {
            asset_url: '/outputs/mock-video/sample.mp4',
            metadata: { provider_response_normalized: { metadata: { provider_mode: 'mock_success' } } },
          },
        },
        {
          id: 'job-hosted-second',
          project_id: 'demo_studio_cinematic_001',
          shot_id: 'shot_001',
          provider: 'runway',
          status: 'completed',
          progress: 100,
          retry_count: 0,
          created_at: '2026-05-21T00:05:00Z',
          updated_at: '2026-05-21T00:05:00Z',
          output_payload: {
            asset_url: 'https://cdn.hosted.example.com/hosted-priority.mp4',
            metadata: { provider_response_normalized: { metadata: { provider_mode: 'hosted_api' } } },
          },
        },
      ],
    })
    expect(html).toContain('https://cdn.hosted.example.com/hosted-priority.mp4')
  })

  it('prefers hosted output even when hosted shot id differs from first selected local job', () => {
    const html = renderBay({
      renderJobs: [
        {
          id: 'job-local-first',
          project_id: 'demo_studio_cinematic_001',
          shot_id: 'scene_001_shot_001',
          provider: 'mock_success',
          status: 'completed',
          progress: 100,
          retry_count: 0,
          created_at: '2026-05-21T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
          output_payload: {
            asset_url: '/outputs/final_films/route_keyframe_demo.mp4',
            metadata: { provider_response_normalized: { metadata: { provider_mode: 'mock_success' } } },
          },
        },
        {
          id: 'job-hosted-other-shot',
          project_id: 'demo_studio_cinematic_001',
          shot_id: 'scene_001_shot_hosted_smoke',
          provider: 'runway',
          status: 'completed',
          progress: 100,
          retry_count: 0,
          created_at: '2026-05-21T00:05:00Z',
          updated_at: '2026-05-21T00:05:00Z',
          output_payload: {
            asset_url: 'https://dnznrvs05pmza.cloudfront.net/hosted.mp4',
            metadata: { provider_response_normalized: { metadata: { provider_mode: 'hosted_api' } } },
          },
        },
      ],
    })
    expect(html).toContain('https://dnznrvs05pmza.cloudfront.net/hosted.mp4')
  })

  it('shows failed render recovery guidance', () => {
    const html = renderBay({
      renderJobs: [
        {
          id: 'job-failed',
          project_id: 'demo_studio_cinematic_001',
          shot_id: 'shot_002',
          provider: 'mock_success',
          status: 'failed',
          progress: 100,
          retry_count: 1,
          created_at: '2026-05-21T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
          output_payload: { metadata: {} },
        },
      ],
    })
    expect(html).toContain('A failed render needs recovery before review.')
    expect(html).toContain('Retry Failed Render')
  })

  it('labels mock provider mode honestly', () => {
    const html = renderBay({
      providerStatuses: [
        {
          provider_id: 'runway',
          name: 'Runway',
          status: 'available',
          is_simulated: false,
          capabilities: ['video_generation'],
          active_jobs: 0,
          queued_jobs: 0,
          provider_mode: 'mock_success',
          display_label: 'Runway: Mock Success Mode',
        },
      ],
      renderJobs: [
        {
          id: 'job-mock',
          project_id: 'demo_studio_cinematic_001',
          shot_id: 'scene_001_shot_001',
          provider: 'runway',
          status: 'complete',
          progress: 100,
          retry_count: 0,
          created_at: '2026-05-21T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
          output_payload: {
            asset_url: '/outputs/mock-video/sample.mp4',
            metadata: {
              provider_response_normalized: { metadata: { provider_mode: 'mock_success' } },
            },
          },
        },
      ],
    })
    expect(html).toContain('Provider mode:')
    expect(html).toContain('Mock Success Mode')
  })

  it('preserves project id in CTAs', () => {
    const html = renderBay({
      projectId: 'proj_123',
      renderJobs: [
        {
          id: 'job-1',
          project_id: 'proj_123',
          shot_id: 'shot_001',
          provider: 'mock_success',
          status: 'completed',
          progress: 100,
          retry_count: 0,
          created_at: '2026-05-21T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
          output_payload: { asset_url: '/outputs/mock-video/sample.mp4', metadata: {} },
        },
      ],
    })
    expect(html).toContain('/studio/screening-room?project_id=proj_123')
    expect(html).toContain('/studio/previs?project_id=proj_123')
  })
})
