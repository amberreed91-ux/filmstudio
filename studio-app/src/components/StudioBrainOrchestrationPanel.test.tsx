import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import StudioBrainOrchestrationPanel from './StudioBrainOrchestrationPanel'

describe('StudioBrainOrchestrationPanel', () => {
  it('renders orchestration timeline and reasoning trace from execution summary', () => {
    const html = renderToStaticMarkup(
      <StudioBrainOrchestrationPanel
        executionSummary={{
          studio_brain_orchestration: {
            orchestration_timeline: [
              { role: 'Director', status: 'active', signal: 'approve', advisory_only: true },
              { role: 'Provider Router', status: 'active', signal: 'runway', advisory_only: true },
            ],
            creative_reasoning_trace: [
              { role: 'Director', focus: 'intent', advisory: 'Keep tone restrained.', advisory_only: true },
            ],
            deterministic_audit: { deterministic: true },
          },
        }}
      />,
    )

    expect(html).toContain('Studio Brain Orchestration')
    expect(html).toContain('Orchestration Timeline')
    expect(html).toContain('Creative Reasoning Trace')
    expect(html).toContain('Director')
    expect(html).toContain('runway')
    expect(html).toContain('Keep tone restrained.')
  })
})
