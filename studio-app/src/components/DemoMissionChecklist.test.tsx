import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { renderToStaticMarkup } from 'react-dom/server'
import DemoMissionChecklist from './DemoMissionChecklist'
import type { DemoMissionChecklistData } from './DemoMissionChecklist'

function baseData(): DemoMissionChecklistData {
  return {
    visualAssetsCount: 1,
    keyframesCount: 3,
    frameAnalysesCount: 3,
    embeddingsCount: 3,
    memoryRecordsCount: 3,
    renderJobsCount: 2,
    decisionGate: {
      project_id: 'demo_studio_cinematic_001',
      gate_status: 'ready',
      current_stage: 'package',
      blockers: [],
      warnings: [],
      ready_signals: [],
      recommended_next_action: 'Ready: approved cut can be packaged.',
      evidence: { counts: { reviews: 1, final_packages: 1 } },
      advisory_only: true,
      auto_approval_triggered: false,
      auto_regeneration_triggered: false,
    },
  }
}

describe('DemoMissionChecklist', () => {
  it('is hidden for non-demo projects', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DemoMissionChecklist projectId="other_project" data={baseData()} />
      </MemoryRouter>,
    )
    expect(html).toBe('')
  })

  it('renders checklist and preserves project_id in links for demo project', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DemoMissionChecklist projectId="demo_studio_cinematic_001" data={baseData()} />
      </MemoryRouter>,
    )

    expect(html).toContain('Demo Mission')
    expect(html).toContain('Visual Evidence Loaded')
    expect(html).toContain('Decision Gate Ready')
    expect(html).toContain('/studio/previs?project_id=demo_studio_cinematic_001')
    expect(html).toContain('/studio/production-board?project_id=demo_studio_cinematic_001')
    expect(html).toContain('/studio/screening-room?project_id=demo_studio_cinematic_001')
    expect(html).toContain('/studio/scheduler?project_id=demo_studio_cinematic_001')
  })

  it('renders needs-attention/checking copy from provided data', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DemoMissionChecklist
          projectId="demo_studio_cinematic_001"
          data={{
            ...baseData(),
            visualAssetsCount: 0,
            keyframesCount: null,
          }}
        />
      </MemoryRouter>,
    )

    expect(html).toContain('Needs attention')
    expect(html).toContain('Checking...')
  })
})
