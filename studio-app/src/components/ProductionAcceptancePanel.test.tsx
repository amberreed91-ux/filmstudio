import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ProductionAcceptancePanel from './ProductionAcceptancePanel'
import type { FinalShortFilmPackage, ProductionAcceptanceReport } from '../lib/studioApi'

const pkg: FinalShortFilmPackage = {
  package_id: 'package-test',
  project_id: 'project-test',
  film_title: 'Acceptance Test',
  final_output_url: 'https://cdn.example.com/final.mp4',
  review_decision: 'approved',
  scene_count: 1,
  shot_count: 1,
  render_job_ids: ['render-1'],
  revision_ids: [],
  has_title_card: false,
  has_end_card: false,
  has_soundtrack: false,
  package_status: 'ready_for_review',
  created_at: '2026-07-27T00:00:00Z',
  updated_at: '2026-07-27T00:00:00Z',
  metadata: {},
}

function report(overrides: Partial<ProductionAcceptanceReport> = {}): ProductionAcceptanceReport {
  return {
    acceptance_id: 'acceptance-test',
    project_id: 'project-test',
    package_id: 'package-test',
    disposition: 'blocked',
    stale: false,
    stale_reasons: [],
    summary: 'Production acceptance found blockers.',
    co_director_note: 'The approval gate is pointing at an absent cut.',
    generated_at: '2026-07-27T00:00:00Z',
    generated_by: 'production_acceptance_service',
    metadata: {},
    context: {
      project_id: 'project-test',
      package_id: 'package-test',
      package_updated_at: '2026-07-27T00:00:00Z',
      final_output_url: 'https://cdn.example.com/final.mp4',
      final_output_fingerprint: 'https://cdn.example.com/final.mp4',
      review_id: 'review-test',
      review_decision: 'approved',
      render_job_ids: ['render-1'],
      revision_ids: [],
      scene_ids: ['scene_001'],
      acceptance_input_hash: 'hash',
      evidence_counts: {},
    },
    checks: [
      {
        check_id: 'final_output_reachable',
        check_version: '1.0',
        category: 'media',
        severity: 'blocker',
        title: 'Final output file missing',
        summary: 'The package points to a local output that is not present on disk.',
        co_director_note: 'The approval gate is pointing at an absent cut.',
        affected_scenes: [],
        affected_shots: [],
        evidence: [],
        remediation: ['Regenerate or restitch the final output.'],
        metadata: {},
      },
    ],
    ...overrides,
  }
}

function renderPanel(activeReport: ProductionAcceptanceReport | null) {
  return renderToStaticMarkup(
    <ProductionAcceptancePanel
      projectId="project-test"
      finalPackage={pkg}
      report={activeReport}
      onReport={() => {}}
      loading={false}
      setLoading={() => {}}
      error=""
      setError={() => {}}
    />,
  )
}

describe('ProductionAcceptancePanel', () => {
  it('renders not-run state', () => {
    const html = renderPanel(null)
    expect(html).toContain('Production Acceptance')
    expect(html).toContain('Not run')
    expect(html).toContain('Verify the final package before approval')
  })

  it('renders blocker state with remediation', () => {
    const html = renderPanel(report())
    expect(html).toContain('Blocked')
    expect(html).toContain('Final output file missing')
    expect(html).toContain('Regenerate or restitch the final output.')
  })

  it('renders stale acceptance state', () => {
    const html = renderPanel(report({
      stale: true,
      stale_reasons: ['Final package was updated after acceptance.'],
    }))
    expect(html).toContain('Stale acceptance')
    expect(html).toContain('Final package was updated after acceptance.')
  })
})
