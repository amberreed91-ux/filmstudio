import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { ComponentProps } from 'react'
import CrewOpsPulseBoard from './CrewOpsPulseBoard'

function renderBoard(overrides: Partial<ComponentProps<typeof CrewOpsPulseBoard>> = {}) {
  return renderToStaticMarkup(
    <MemoryRouter>
      <CrewOpsPulseBoard
        projectId="demo_studio_cinematic_001"
        decisionGate={null}
        renderJobsCount={2}
        reviewsCount={1}
        packagesCount={1}
        memoryRecordCount={3}
        continuityIssueCount={0}
        styleDriftIssueCount={0}
        {...overrides}
      />
    </MemoryRouter>,
  )
}

describe('CrewOpsPulseBoard', () => {
  it('renders pulse board for demo project with ready-state copy', () => {
    const html = renderBoard()
    expect(html).toContain('Production Pulse Hero')
    expect(html).toContain('The studio pipeline is assembled and ready for guided playback.')
    expect(html).toContain('Review and package states are aligned for screening.')
  })

  it('preserves project_id in department links', () => {
    const html = renderBoard({ projectId: 'demo_studio_cinematic_001' })
    expect(html).toContain('/studio/study-room?project_id=demo_studio_cinematic_001')
    expect(html).toContain('/studio/previs?project_id=demo_studio_cinematic_001')
    expect(html).toContain('/studio/production-board?project_id=demo_studio_cinematic_001')
    expect(html).toContain('/studio/screening-room?project_id=demo_studio_cinematic_001')
  })

  it('shows low-data fallback copy when signals are thin', () => {
    const html = renderBoard({
      projectId: 'proj_low',
      renderJobsCount: 0,
      reviewsCount: 0,
      packagesCount: 0,
      memoryRecordCount: 0,
      continuityIssueCount: 0,
      styleDriftIssueCount: 0,
    })
    expect(html).toContain('The studio needs active render output before this pipeline can move cleanly into screening.')
  })

  it('avoids raw debug labels in the pulse presentation copy', () => {
    const html = renderBoard()
    expect(html).not.toContain('project_id:')
    expect(html).not.toContain('gate_status')
    expect(html).not.toContain('debug')
  })
})
