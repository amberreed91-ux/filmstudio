// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

afterEach(cleanup)
import EvidenceAuditDrawer from './EvidenceAuditDrawer'
import { hashLogEntry } from '../lib/evidenceLog'
import type { GateStage } from '../lib/pipelineGateFlow'

function stage(over: Partial<GateStage> = {}): GateStage {
  return {
    id: 'preflight_authorization',
    order: 2,
    label: 'Preflight Authorization',
    configuration: 'A frozen generation contract must exist.',
    evidenceSource: 'Render job metadata · router_execution.router_config_id, reason',
    state: 'fail_closed',
    detail: '1 job was refused before a request was built.',
    logs: [
      {
        id: 'job-b:reason',
        label: 'Refused before submission',
        detail: 'frozen_generation_contract_unavailable',
        at: '2026-10-17T10:06:00Z',
      },
    ],
    ...over,
  }
}

describe('EvidenceAuditDrawer', () => {
  it('returns null without a pinned stage', () => {
    const { container } = render(<EvidenceAuditDrawer stage={null} onClose={() => {}} />)
    expect(container.firstChild).toBeNull()
  })

  it('pins stage status, timestamps, log hashes, and raw JSON without mutating backend', () => {
    const onClose = vi.fn()
    render(<EvidenceAuditDrawer stage={stage()} onClose={onClose} />)
    expect(screen.getByTestId('evidence-audit-drawer')).toBeInTheDocument()
    expect(screen.getByTestId('evidence-audit-state')).toHaveTextContent('Fail-closed')
    expect(screen.getByText('frozen_generation_contract_unavailable')).toBeInTheDocument()
    expect(screen.getByText(/2026-10-17 10:06:00 UTC/)).toBeInTheDocument()
    expect(screen.getByText(new RegExp(hashLogEntry('job-b:reason', 'frozen_generation_contract_unavailable')))).toBeInTheDocument()
    expect(screen.getByTestId('evidence-raw-digest').textContent).toContain('preflight_authorization')
    expect(screen.getByText(/never approves work, runs scans, or mutates backend state/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /unpin preflight authorization evidence/i }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('surfaces normalization warnings separately and reports absent timestamps honestly', () => {
    render(
      <EvidenceAuditDrawer
        stage={stage({
          id: 'payload_normalizer',
          order: 4,
          label: 'Payload Normalizer',
          state: 'cleared',
          logs: [
            { id: 'job-a:normalization', label: 'Payload auto-optimized', detail: 'ROUTER_PAYLOAD_NORMALIZED: secondary_references_dropped' },
          ],
        })}
        onClose={() => {}}
      />,
    )
    expect(screen.getByText(/Normalization warnings \(1\)/)).toBeInTheDocument()
    expect(screen.getAllByText(/ROUTER_PAYLOAD_NORMALIZED/).length).toBeGreaterThan(0)
    expect(screen.getByText(/timestamp not recorded/)).toBeInTheDocument()
  })

  it('never renders scores or ratings', () => {
    render(<EvidenceAuditDrawer stage={stage()} onClose={() => {}} />)
    const drawers = screen.getAllByTestId('evidence-audit-drawer')
    const latest = drawers[drawers.length - 1]
    expect(latest.textContent).not.toMatch(/score|rating|percentage|[0-9]+\/10/i)
  })
})
