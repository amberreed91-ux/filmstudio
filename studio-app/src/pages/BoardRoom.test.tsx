// @vitest-environment jsdom
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import BoardRoom, { buildShotWall } from './BoardRoom'

vi.mock('../components/StudioShell', () => ({
  default: ({ children }: { children: ReactNode }) => createElement('div', null, children),
}))

const studioState = vi.hoisted(() => ({
  activeProject: null as { project_id: string; title: string } | null,
  activeProjectId: null as string | null,
}))

vi.mock('../context/StudioContext', () => ({
  useStudio: () => ({
    activeProject: studioState.activeProject,
    activeProjectId: studioState.activeProjectId,
    loadProject: vi.fn().mockResolvedValue(undefined),
  }),
}))

const apiMocks = vi.hoisted(() => ({
  listScenes: vi.fn(),
}))

vi.mock('../lib/studioApi', () => apiMocks)

const SCENES = [
  {
    scene_id: 'scene_001',
    scene_name: 'Neon Arrival',
    status: 'storyboarded',
    storyboard_image: '/boards/scene-001.png',
    storyboard_images: {
      scene_001_shot_002: '/boards/scene-001-shot-2.png',
      scene_001_shot_001: '/boards/scene-001-shot-1.png',
    },
  },
  {
    scene_id: 'scene_002',
    scene_name: 'Power Cut',
    status: 'written',
  },
]

function renderBoard(initialEntries = ['/studio/board?project_id=proj_1']) {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries },
      createElement(
        Routes,
        null,
        createElement(Route, { path: '/studio/board', element: createElement(BoardRoom) }),
      ),
    ),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  studioState.activeProject = { project_id: 'proj_1', title: 'Neon Dreams' }
  studioState.activeProjectId = 'proj_1'
  apiMocks.listScenes.mockResolvedValue({ scenes: SCENES })
})

afterEach(cleanup)

describe('buildShotWall', () => {
  it('orders per-shot frames numerically and appends the scene board once', () => {
    const shots = buildShotWall(SCENES as never)
    expect(shots.map((shot) => shot.shotId)).toEqual([
      'scene_001_shot_001',
      'scene_001_shot_002',
      'scene_001_board',
    ])
  })

  it('skips scenes without any board art', () => {
    expect(buildShotWall([])).toEqual([])
  })
})

describe('BoardRoom', () => {
  it('renders metrics, the shot wall, and the inspector', async () => {
    renderBoard()
    expect(await screen.findByTestId('board-shot-scene_001_shot_001')).toBeInTheDocument()
    expect(screen.getByTestId('board-metrics')).toHaveTextContent('3')
    expect(screen.getByTestId('board-metrics')).toHaveTextContent('100%')
    expect(screen.getByTestId('board-inspector')).toHaveTextContent('Select any frame')
  })

  it('inspects the selected shot', async () => {
    renderBoard()
    fireEvent.click(await screen.findByTestId('board-shot-scene_001_shot_002'))
    const inspector = screen.getByTestId('board-inspector')
    expect(inspector).toHaveTextContent('scene_001_shot_002')
    expect(inspector).toHaveTextContent('Neon Arrival')
    expect(inspector).toHaveTextContent('Boarded')
  })

  it('asks for a film when no project is linked', async () => {
    studioState.activeProject = null
    studioState.activeProjectId = null
    renderBoard(['/studio/board'])
    expect(await screen.findByTestId('board-empty')).toBeInTheDocument()
  })
})
