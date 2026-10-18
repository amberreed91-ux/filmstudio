import type { ComponentProps } from 'react'
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import ProductionExecutionBay from './ProductionExecutionBay'
import RouterNormalizationBadge from './RouterNormalizationBadge'

function baseJob(overrides: Record<string, unknown> = {}) {
  return {
    id: 'job-1',
    project_id: 'proj_1',
    shot_id: 'scene_001_shot_001',
    provider: 'runway',
    status: 'completed',
    progress: 100,
    retry_count: 0,
    created_at: '2026-05-21T00:00:00Z',
    updated_at: '2026-05-21T00:00:00Z',
    output_payload: { asset_url: 'https://cdn.example.com/shot.mp4', metadata: {} },
    ...overrides,
  }
}

function renderBay(renderJobs: ComponentProps<typeof ProductionExecutionBay>['renderJobs']) {
  return renderToStaticMarkup(
    <MemoryRouter>
      <ProductionExecutionBay
        projectId="proj_1"
        projectTitle="Test Production"
        decisionGate={null}
        renderJobs={renderJobs}
      />
    </MemoryRouter>,
  )
}

describe('RouterNormalizationBadge', () => {
  it('renders the Auto-Optimized chip with the normalization tooltip', () => {
    const html = renderToStaticMarkup(<RouterNormalizationBadge />)
    expect(html).toContain('Auto-Optimized')
    expect(html).toContain(
      'Payload automatically optimized to 1 primary reference image, 16:9 aspect ratio, and 5s duration for Runway router eligibility.',
    )
    expect(html).toContain('data-testid="router-normalization-badge"')
  })

  it('shows the badge for a normalized job in the execution bay', () => {
    const html = renderBay([
      baseJob({
        metadata: {
          router_execution: {
            payload_normalized: true,
            payload_normalization_warnings: ['secondary_references_sanitized:kept_1_of_3'],
          },
        },
      }) as never,
    ])
    expect(html).toContain('data-testid="router-normalization-badge"')
    expect(html).toContain('Auto-Optimized')
  })

  it('hides the badge for a standard un-normalized job', () => {
    const html = renderBay([baseJob({ metadata: {} }) as never])
    expect(html).not.toContain('data-testid="router-normalization-badge"')
    expect(html).not.toContain('Auto-Optimized')
  })
})
