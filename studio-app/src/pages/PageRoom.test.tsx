// @vitest-environment jsdom
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import PageRoom from './PageRoom'

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
  listCharacters: vi.fn(),
  updateScene: vi.fn(),
}))

vi.mock('../lib/studioApi', () => apiMocks)

const SCENES = [
  {
    scene_id: 'scene_001',
    scene_name: 'Neon Arrival',
    heading: 'INT. ARCADE - NIGHT',
    description: 'Mara enters the arcade.',
    location: 'Arcade',
    time_of_day: 'NIGHT',
    emotional_tone: 'uneasy wonder',
    characters: ['Mara'],
  },
  {
    scene_id: 'scene_002',
    scene_name: 'Power Cut',
    heading: 'INT. ARCADE - LATER',
    description: 'The lights die.',
    location: 'Arcade',
    time_of_day: 'NIGHT',
    emotional_tone: 'dread',
    characters: ['Mara', 'Theo'],
  },
]

function renderPage(initialEntries = ['/studio/page?project_id=proj_1']) {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries },
      createElement(
        Routes,
        null,
        createElement(Route, { path: '/studio/page', element: createElement(PageRoom) }),
      ),
    ),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  studioState.activeProject = { project_id: 'proj_1', title: 'Neon Dreams' }
  studioState.activeProjectId = 'proj_1'
  apiMocks.listScenes.mockResolvedValue({ scenes: SCENES })
  apiMocks.listCharacters.mockResolvedValue({
    characters: [{ id: 'char_mara', name: 'Mara', core_desire: 'To disappear', energy: 'coiled' }],
  })
  apiMocks.updateScene.mockResolvedValue({ scene: { ...SCENES[0], description: 'Edited.' } })
})

afterEach(cleanup)

describe('PageRoom', () => {
  it('shows navigator, editor, and inspector for a project', async () => {
    renderPage()
    expect(await screen.findByTestId('page-scene-scene_001')).toBeInTheDocument()
    expect(screen.getByTestId('page-scene-scene_002')).toBeInTheDocument()
    expect(await screen.findByDisplayValue('Mara enters the arcade.')).toHaveAttribute('data-testid', 'page-editor')
    expect(screen.getByTestId('page-character-char_mara')).toHaveTextContent('Mara')
    expect(screen.getByTestId('page-intent')).toHaveTextContent('uneasy wonder')
  })

  it('switches the editor and intent cards between scenes', async () => {
    renderPage()
    fireEvent.click(await screen.findByTestId('page-scene-scene_002'))
    expect(screen.getByTestId('page-editor')).toHaveValue('The lights die.')
    expect(screen.getByTestId('page-intent')).toHaveTextContent('dread')
  })

  it('saves editor changes back to the scene', async () => {
    renderPage()
    await screen.findByTestId('page-scene-scene_001')
    fireEvent.change(screen.getByTestId('page-editor'), { target: { value: 'Edited.' } })
    fireEvent.click(screen.getByTestId('page-save'))
    await waitFor(() => {
      expect(apiMocks.updateScene).toHaveBeenCalledWith('proj_1', 'scene_001', { description: 'Edited.' })
    })
    expect(await screen.findByTestId('page-save-message')).toHaveTextContent('Saved to the screenplay.')
  })

  it('asks for a film when no project is linked', async () => {
    studioState.activeProject = null
    studioState.activeProjectId = null
    render(
      createElement(
        MemoryRouter,
        { initialEntries: ['/studio/page'] },
        createElement(
          Routes,
          null,
          createElement(Route, { path: '/studio/page', element: createElement(PageRoom) }),
        ),
      ),
    )
    expect(await screen.findByTestId('page-empty')).toBeInTheDocument()
  })
})
