import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { renderToStaticMarkup } from 'react-dom/server'
import DemoCoDirectorPanel, { type DemoCoDirectorPanelData } from './DemoCoDirectorPanel'

function readyData(): DemoCoDirectorPanelData {
  return {
    visualAssetsCount: 1,
    frameAnalysesCount: 3,
    memoryRecordsCount: 3,
    embeddingsCount: 3,
    renderJobsCount: 2,
    continuityIssuesCount: 0,
    styleDriftIssuesCount: 0,
    hasDirectorSignature: true,
    decisionGate: {
      project_id: 'demo_studio_cinematic_001',
      gate_status: 'ready',
      current_stage: 'package',
      blockers: [],
      warnings: [],
      ready_signals: [],
      recommended_next_action: 'Ready: approved cut can be packaged.',
      evidence: {},
      advisory_only: true,
      auto_approval_triggered: false,
      auto_regeneration_triggered: false,
    },
  }
}

describe('DemoCoDirectorPanel', () => {
  it('is hidden for non-demo project', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DemoCoDirectorPanel projectId="proj_other" data={readyData()} />
      </MemoryRouter>,
    )
    expect(html).toBe('')
  })

  it('shows low-data friendly copy', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DemoCoDirectorPanel
          projectId="demo_studio_cinematic_001"
          data={{
            ...readyData(),
            visualAssetsCount: 0,
            frameAnalysesCount: 0,
            memoryRecordsCount: 0,
            embeddingsCount: 0,
            decisionGate: null,
          }}
        />
      </MemoryRouter>,
    )
    expect(html).toContain('Still gathering enough visual evidence.')
    expect(html).toContain('Advance to Next Best Room')
    expect(html).toContain('/studio/study-room?project_id=demo_studio_cinematic_001')
  })

  it('routes ready state to Screening Room', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DemoCoDirectorPanel projectId="demo_studio_cinematic_001" data={readyData()} />
      </MemoryRouter>,
    )
    expect(html).toContain('Co-Director Guidance')
    expect(html).toContain('ready for screening and package polish')
    expect(html).toContain('The cut is ready, review it in Screening Room.')
    expect(html).toContain('/studio/screening-room?project_id=demo_studio_cinematic_001')
  })

  it('routes blocked state to Production Board', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DemoCoDirectorPanel
          projectId="demo_studio_cinematic_001"
          data={{
            ...readyData(),
            decisionGate: {
              ...readyData().decisionGate!,
              gate_status: 'blocked',
            },
          }}
        />
      </MemoryRouter>,
    )
    expect(html).toContain('Production needs attention before screening.')
    expect(html).toContain('/studio/production-board?project_id=demo_studio_cinematic_001')
  })

  it('routes insufficient_data to Study Room', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DemoCoDirectorPanel
          projectId="demo_studio_cinematic_001"
          data={{
            ...readyData(),
            decisionGate: {
              ...readyData().decisionGate!,
              gate_status: 'insufficient_data',
            },
            visualAssetsCount: 0,
            frameAnalysesCount: 0,
            memoryRecordsCount: 0,
            embeddingsCount: 0,
          }}
        />
      </MemoryRouter>,
    )
    expect(html).toContain('The studio needs more visual evidence first.')
    expect(html).toContain('/studio/study-room?project_id=demo_studio_cinematic_001')
  })

  it('routes unknown/default state to Previs', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DemoCoDirectorPanel
          projectId="demo_studio_cinematic_001"
          data={{
            ...readyData(),
            decisionGate: null,
            visualAssetsCount: 1,
            frameAnalysesCount: 2,
            memoryRecordsCount: 1,
            embeddingsCount: 1,
            renderJobsCount: 0,
          }}
        />
      </MemoryRouter>,
    )
    expect(html).toContain('Open Previs to inspect the scene plan.')
    expect(html).toContain('/studio/previs?project_id=demo_studio_cinematic_001')
  })
})
