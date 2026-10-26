// @vitest-environment jsdom
import { createElement } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import fs from 'node:fs'
import path from 'node:path'
import ReferenceBoard from './ReferenceBoard'
import { APP_ROUTES } from '../routes'

const fetchJsonMock = vi.fn()

vi.mock('../lib/studioApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/studioApi')>()
  return {
    ...actual,
    fetchJson: (...args: unknown[]) => (fetchJsonMock as (...a: unknown[]) => unknown)(...args),
    buildStudioApiUrl: (p: string) => p,
  }
})

function boardAssets(projectId: string) {
  if (projectId === 'film-b') {
    return {
      reference_assets: [
        {
          ref_id: 'ref_b_1',
          kind: 'environment',
          image_url: '/outputs/reference-assets/b-wide.jpg',
          source_shot_id: null,
          project_id: 'film-b',
          target_type: 'setting',
          target_id: 'loc-b',
          category: 'wide',
          approval_state: 'approved',
          canonical: true,
          source_kind: 'confirmed',
        },
      ],
      count: 1,
    }
  }
  return {
    reference_assets: [
      {
        ref_id: 'ref_settled_1',
        kind: 'environment',
        image_url: 'https://cdn.test/settled.jpg',
        source_shot_id: null,
        project_id: projectId,
        target_type: 'setting',
        target_id: 'loc-c8f88b9c',
        category: 'environment',
        approval_state: 'approved',
        canonical: true,
        source_kind: 'confirmed',
      },
      {
        ref_id: 'ref_set_99caf0f5fd1a471eb3c89d4fb9cac11c',
        kind: 'environment',
        image_url: '/outputs/reference-assets/uploads/abc/local-rejected.jpg',
        source_shot_id: null,
        project_id: projectId,
        target_type: 'setting',
        target_id: 'loc-c8f88b9c',
        category: 'environment',
        approval_state: 'rejected',
        canonical: true,
        source_kind: 'confirmed',
      },
      {
        ref_id: 'ref_char_1',
        kind: 'character_face',
        image_url: '/outputs/reference-assets/uploads/xyz/local-face.jpg',
        source_shot_id: 'scene_001_shot_001',
        project_id: projectId,
        target_type: 'character',
        target_id: 'char-maya',
        category: 'face',
        approval_state: 'candidate',
        canonical: false,
        source_kind: 'uploaded',
      },
    ],
    count: 3,
  }
}

function renderBoard(initialPath: string) {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries: [initialPath] },
      createElement(Routes, null, createElement(Route, { path: '/studio/reference-board', element: createElement(ReferenceBoard) })),
    ),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  fetchJsonMock.mockImplementation((url: unknown) => {
    const u = String(url)
    const m = u.match(/projects\/([^/]+)\/reference-assets/)
    const projectId = m ? decodeURIComponent(m[1]) : 'film-a'
    return Promise.resolve(boardAssets(projectId))
  })
})
afterEach(cleanup)

describe('Reference Board (read-only)', () => {
  it('shows a neutral pick-a-project state when no project_id is present', () => {
    renderBoard('/studio/reference-board')
    expect(screen.getByRole('status')).toHaveTextContent(/Pick a project/i)
    expect(fetchJsonMock).not.toHaveBeenCalled()
  })

  it('fetches with sync=0 only and renders people, places, verdicts, and delivery tags', async () => {
    renderBoard('/studio/reference-board?project_id=film-a')
    expect(await screen.findByText(/Who and where the film remembers/i)).toBeInTheDocument()
    await waitFor(() => expect(fetchJsonMock).toHaveBeenCalledTimes(1))
    const calledUrl = String(fetchJsonMock.mock.calls[0][0])
    expect(calledUrl).toContain('/reference-assets')
    expect(calledUrl).toContain('sync=0')
    // Only one network call, only the registry list — no library fan-out.
    expect(fetchJsonMock.mock.calls.every((c) => String(c[0]).includes('sync=0'))).toBe(true)

    // Groups per mockup (exact section labels; verdict strip uses "People stage" / "Places stage")
    expect(await screen.findByLabelText('People', { exact: true })).toBeInTheDocument()
    expect(screen.getByLabelText('Places', { exact: true })).toBeInTheDocument()
    // Verdict strip: settled + saved
    expect(screen.getByText(/1 settled/)).toBeInTheDocument()
    expect(screen.getByText(/3 kept/)).toBeInTheDocument()
    // Local files stay local
    expect(screen.getAllByText(/Local file — not ready to send/).length).toBeGreaterThanOrEqual(2)
    // Canonical + rejected rows need a look, never hidden
    const rejectedChips = await screen.findAllByTestId('reference-chip-ref_set_99caf0f5fd1a471eb3c89d4fb9cac11c')
    expect(rejectedChips[0]).toHaveTextContent(/Needs a look/)
    // Settled canonical stays settled
    expect(screen.getByTestId('reference-chip-ref_settled_1')).toHaveTextContent(/Settled/)
    // Plain language only outside the drawer; machine detail stays inside <details>
    expect(screen.queryByText(/score|rating|\d+%/i)).toBeNull()
  })

  it('explains what the headers and the strip count in the details drawer', async () => {
    renderBoard('/studio/reference-board?project_id=film-a')
    expect(await screen.findByText(/Counts: headers count saved rows; the strip counts distinct people and places\./)).toBeInTheDocument()
  })

  it('loads a second project independently', async () => {
    renderBoard('/studio/reference-board?project_id=film-b')
    await waitFor(() => expect(fetchJsonMock).toHaveBeenCalledTimes(1))
    expect(String(fetchJsonMock.mock.calls[0][0])).toContain('film-b')
    expect(await screen.findByTestId('reference-card-ref_b_1')).toBeInTheDocument()
    expect(screen.queryByTestId('reference-card-ref_settled_1')).toBeNull()
  })

  it('explains an empty registry without an error', async () => {
    fetchJsonMock.mockResolvedValueOnce({ reference_assets: [], count: 0 })
    renderBoard('/studio/reference-board?project_id=film-empty')
    expect(await screen.findByText(/No saved references yet/i)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('reports an unavailable backend honestly', async () => {
    fetchJsonMock.mockRejectedValueOnce(new Error('backend offline'))
    renderBoard('/studio/reference-board?project_id=film-a')
    expect(await screen.findByRole('alert')).toHaveTextContent(/backend offline/i)
  })

  it('registers the board route without disturbing existing rooms', () => {
    const board = APP_ROUTES.find((r) => r.path === '/studio/reference-board')
    expect(board?.title).toBe('Reference Board')
    expect(board?.element).toBeTruthy()
    const space = APP_ROUTES.find((r) => r.path === '/studio/reference-space')
    const desk = APP_ROUTES.find((r) => r.path === '/studio/production-desk')
    const engine = APP_ROUTES.find((r) => r.path === '/studio/integrity')
    expect(space?.title).toBe('Reference Space')
    expect(desk?.title).toBe('Production Desk')
    expect(engine?.title).toBe('Production Integrity Engine')
  })

  it('guard: board sources issue only GET registry reads with sync=0 — no writes, jobs, or provider URLs', () => {
    const root = path.resolve(__dirname, '..')
    const files = [
      'lib/referenceBoardApi.ts',
      'pages/ReferenceBoard.tsx',
      'components/reference/ReferenceCard.tsx',
      'components/reference/GroupRow.tsx',
      'components/reference/DeliveryTag.tsx',
    ]
    const sources = files.map((f) => fs.readFileSync(path.join(root, f), 'utf8'))
    const all = sources.join('\n')
    // Every registry URL carries sync=0
    expect(all).toContain('sync=0')
    expect(all).not.toMatch(/sync=1/)
    // No non-GET requests: no method override, no fetch init, no mutation helpers.
    // (Prose may mention Runway as the sender; endpoint plumbing may not.)
    expect(all).not.toMatch(/method\s*:/i)
    expect(all).not.toMatch(/fetchJson\([^)]*,/s)
    expect(all).not.toMatch(/fetch\s*\(/i)
    expect(all).not.toMatch(/axios\s*\./i)
    // No mutation/job/provider endpoint strings on the board.
    expect(all).not.toMatch(/\/jobs|\/render\b|\/providers?\b|runway:\/\/|higgsfield/i)
    expect(all).not.toMatch(/\/generate|\/upload|\/approve|\/confirm|\/canonical|\/reject/i)
    // No scores, ratings, or percentages anywhere on the board
    expect(all).not.toMatch(/score|rating|percent/i)
  })
})
