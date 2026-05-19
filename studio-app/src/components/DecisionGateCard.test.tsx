import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { renderToStaticMarkup } from 'react-dom/server'
import DecisionGateCard from './DecisionGateCard'
import type { StudioDecisionGate } from '../lib/studioApi'

function htmlFor(gate: StudioDecisionGate): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <DecisionGateCard projectId="project-test" gate={gate} loading={false} error="" />
    </MemoryRouter>,
  )
}

const baseGate: StudioDecisionGate = {
  project_id: 'project-test',
  gate_status: 'needs_review',
  current_stage: 'screening',
  blockers: [],
  warnings: [],
  ready_signals: [],
  recommended_next_action: 'Needs review: completed clips are ready for approval.',
  evidence: {},
  advisory_only: true,
  auto_approval_triggered: false,
  auto_regeneration_triggered: false,
}

describe('DecisionGateCard', () => {
  it('renders blocked status', () => {
    const html = htmlFor({ ...baseGate, gate_status: 'blocked', blockers: ['Blocked: failed render'] })
    expect(html).toContain('Blocked')
    expect(html).toContain('failed render')
  })

  it('renders needs_review status', () => {
    const html = htmlFor(baseGate)
    expect(html).toContain('Needs Review')
    expect(html).toContain('ready for approval')
  })

  it('renders ready status', () => {
    const html = htmlFor({ ...baseGate, gate_status: 'ready', recommended_next_action: 'Ready: approved cut can be packaged.' })
    expect(html).toContain('Ready')
    expect(html).toContain('approved cut can be packaged')
  })

  it('renders insufficient data status', () => {
    const html = htmlFor({ ...baseGate, gate_status: 'insufficient_data', recommended_next_action: 'Not enough project data yet. Upload reference footage or generate scenes.' })
    expect(html).toContain('Insufficient Data')
    expect(html).toContain('Not enough project data yet')
  })

  it('renders helpful backend unavailable copy for network errors', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DecisionGateCard projectId="project-test" gate={null} loading={false} error="Failed to fetch" />
      </MemoryRouter>,
    )
    expect(html).toContain('Decision gate unavailable. Check that the Studio backend is running.')
    expect(html).not.toContain('Failed to fetch')
  })

  it('renders project-specific unavailable copy for missing project errors', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DecisionGateCard projectId="project-test" gate={null} loading={false} error="Project not found" />
      </MemoryRouter>,
    )
    expect(html).toContain('Decision gate unavailable for this project.')
  })

  it('renders gate content while loading when gate is already available', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DecisionGateCard projectId="project-test" gate={baseGate} loading={true} error="" />
      </MemoryRouter>,
    )
    expect(html).toContain('Needs review: completed clips are ready for approval.')
    expect(html).toContain('Refreshing gate status...')
  })
})
