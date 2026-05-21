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
    expect(html).toContain('Open Previs')
  })

  it('shows ready-state guidance and preserves project links', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DemoCoDirectorPanel projectId="demo_studio_cinematic_001" data={readyData()} />
      </MemoryRouter>,
    )
    expect(html).toContain('Co-Director Guidance')
    expect(html).toContain('ready for screening and package polish')
    expect(html).toContain('/studio/previs?project_id=demo_studio_cinematic_001')
    expect(html).toContain('/studio/production-board?project_id=demo_studio_cinematic_001')
    expect(html).toContain('/studio/screening-room?project_id=demo_studio_cinematic_001')
  })
})
