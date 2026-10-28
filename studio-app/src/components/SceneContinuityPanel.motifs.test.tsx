// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import SceneContinuityPanel from './SceneContinuityPanel'

const continuity = {
  project_id: 'project-a',
  mode: 'passive',
  strictness: 'medium',
  transition_reads: [],
  overall_status: 'clean',
  advisory_notes: [],
  advisory_only: true,
  auto_regeneration_triggered: false,
}

const motifThreads = {
  motifs: [
    {
      motif: 'rain',
      introduced_at: 'scene_001',
      reinforced_at: [],
      last_seen_at: 'scene_001',
      status: 'resolved',
      thread_read: 'The rain closes with the argument.',
      uncertainty_note: null,
      scene_appearances: ['scene_001'],
    },
    {
      motif: 'brass key',
      introduced_at: 'scene_001',
      reinforced_at: [],
      last_seen_at: 'scene_001',
      status: 'active',
      thread_read: 'The key stays in frame between the two holds.',
      uncertainty_note: null,
      scene_appearances: ['scene_001'],
    },
  ],
  unresolved_motifs: [],
  dominant_motif: 'brass key',
  advisory: 'One motif is still carrying the scene.',
  echoes_edges: [],
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(async (input: RequestInfo | URL) => ({
    ok: true,
    json: async () => (String(input).includes('/motif-threads') ? motifThreads : continuity),
  } as Response))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('SceneContinuityPanel motif indicators', () => {
  it('marks the motifs the active project still carries', async () => {
    render(
      <SceneContinuityPanel
        filmId="project-a"
        scenes={[{ scene_id: 'scene_001' }]}
        scenePairs={[['scene_001', 'scene_002'] as [string, string]]}
        onRevisionProposalAccepted={() => {}}
      />,
    )

    expect(await screen.findByTestId('active-motifs')).toBeInTheDocument()
    expect(screen.getAllByTestId('active-motif-chip').map((chip) => chip.textContent)).toEqual(['brass key'])
    expect(screen.getByTestId('motifs-section')).toHaveTextContent('rain')
    // The resolved thread is still listed, just not claimed as active.
    expect(screen.getByTestId('motif-status-resolved')).toBeInTheDocument()
  })

  it('reads motif threads for the active project only', async () => {
    render(
      <SceneContinuityPanel
        filmId="project-b"
        scenes={[{ scene_id: 'scene_001' }]}
        scenePairs={[['scene_001', 'scene_002'] as [string, string]]}
        onRevisionProposalAccepted={() => {}}
      />,
    )

    await screen.findByTestId('active-motifs')
    const motifCall = fetchMock.mock.calls
      .map((call) => String(call[0]))
      .find((url) => url.includes('/motif-threads'))
    expect(motifCall).toContain('/projects/project-b/')
  })
})
