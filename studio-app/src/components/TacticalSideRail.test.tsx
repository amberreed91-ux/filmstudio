// @vitest-environment jsdom
import { createElement } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import TacticalSideRail from './TacticalSideRail'
import { useTacticalTelemetry } from '../hooks/useTacticalTelemetry'

vi.mock('../hooks/useTacticalTelemetry', () => ({
  useTacticalTelemetry: vi.fn(),
}))

const mockedTelemetry = vi.mocked(useTacticalTelemetry)

function liveTelemetry() {
  mockedTelemetry.mockReturnValue({
    isLive: true,
    loading: false,
    queueCounts: { active: 7, waiting: 3, blocked: 0, failed: 1, complete: 9 },
    queueTotal: 20,
    credits: { realized: 1200, estimated: 300, realizedJobs: 4, estimatedOnlyJobs: 2, unpricedJobs: 0 },
    feeds: [
      { key: 'q1', roomId: 'production', title: 'RENDER SHOT', code: '…abc123 · runway', status: 'running' },
    ],
    healthy: true,
  })
}

function stagingTelemetry() {
  mockedTelemetry.mockReturnValue({
    isLive: false,
    loading: false,
    queueCounts: null,
    queueTotal: 0,
    credits: null,
    feeds: [],
    healthy: false,
  })
}

afterEach(cleanup)

describe('TacticalSideRail live telemetry', () => {
  it('renders live queue counts, credit spend, feeds, and port status', () => {
    liveTelemetry()
    render(createElement(TacticalSideRail, { projectId: 'proj-001' }))
    expect(screen.getByTestId('tactical-live-badge')).toHaveTextContent('LIVE')
    expect(screen.getByTestId('tactical-active-slots')).toHaveTextContent('7')
    // Realized 1200 + estimated 300 from render job records — spend, not a balance.
    expect(screen.getByTestId('tactical-cr-spend')).toHaveTextContent('1,500')
    expect(screen.getByTestId('tactical-feed-live-0')).toHaveTextContent('RENDER SHOT')
    expect(screen.getByTestId('tactical-port-status')).toHaveTextContent('ONLINE')
    expect(screen.getByTestId('tactical-queue-gauge')).toHaveAttribute('data-pct', '35')
    expect(screen.getByTestId('telemetry-source-log')).toHaveTextContent('LIVE · 20 tracked')
  })

  it('falls back to labeled staging dressing when the backend is unreachable', () => {
    stagingTelemetry()
    render(createElement(TacticalSideRail, { projectId: '' }))
    expect(screen.getByTestId('tactical-live-badge')).toHaveTextContent('STAGING')
    expect(screen.getByTestId('tactical-active-slots')).toHaveTextContent('166')
    expect(screen.queryByTestId('tactical-cr-spend')).not.toBeInTheDocument()
    expect(screen.getByTestId('tactical-feed-previs')).toBeInTheDocument()
    expect(screen.getByTestId('tactical-port-status')).toHaveTextContent('OFFLINE')
    expect(screen.getByTestId('telemetry-source-log')).toHaveTextContent('STAGING')
  })

  it('keeps rig calibration and re-center triggers working on live data', () => {
    liveTelemetry()
    const focusSpy = vi.fn()
    const listener = (e: Event) => focusSpy((e as CustomEvent).detail)
    window.addEventListener('focus-room', listener)
    try {
      render(createElement(TacticalSideRail, { projectId: 'proj-001' }))
      fireEvent.click(screen.getByText('RIG CALIBRATION'))
      expect(screen.getByTestId('rig-status')).toHaveTextContent('CALIBRATING...')
      fireEvent.click(screen.getByTestId('tactical-feed-live-0'))
      expect(focusSpy).toHaveBeenCalledWith({ roomId: 'production' })
    } finally {
      window.removeEventListener('focus-room', listener)
    }
  })
})
