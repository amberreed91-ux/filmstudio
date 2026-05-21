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
