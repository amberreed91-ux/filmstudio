// @vitest-environment jsdom
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import GateRoom from './GateRoom'

vi.mock('../components/StudioShell', () => ({
  default: ({ children }: { children: ReactNode }) => createElement('div', null, children),
}))

const studioMocks = vi.hoisted(() => ({
  setActiveProject: vi.fn(),
}))

vi.mock('../context/StudioContext', () => ({
  useStudio: () => ({ setActiveProject: studioMocks.setActiveProject, activeProject: null }),
}))

const apiMocks = vi.hoisted(() => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
}))

vi.mock('../lib/studioApi', () => apiMocks)

function LocationProbe() {
  const location = useLocation()
  return createElement('div', { 'data-testid': 'location-probe' }, `${location.pathname}${location.search}`)
}

function renderGate() {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries: ['/studio/gate'] },
      createElement(
        Routes,
        null,
        createElement(Route, { path: '/studio/gate', element: createElement(GateRoom) }),
        createElement(Route, { path: '/studio/page', element: createElement(LocationProbe) }),
        createElement(Route, { path: '/studio', element: createElement(LocationProbe) }),
      ),
    ),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  studioMocks.setActiveProject.mockResolvedValue(undefined)
  apiMocks.listProjects.mockResolvedValue({
    projects: [{ project_id: 'proj_reborn', title: 'I Was Reborn', updated_at: new Date().toISOString() }],
    error: '',
  })
  apiMocks.createProject.mockResolvedValue({ project: { project_id: 'proj_new', title: 'New Film' } })
})

afterEach(cleanup)

describe('GateRoom', () => {
  it('renders the dossier form and the vessel frame', async () => {
    renderGate()
    expect(screen.getByTestId('gate-dossier-form')).toBeInTheDocument()
    expect(screen.getByTestId('gate-title')).toBeInTheDocument()
    expect(screen.getByTestId('gate-format')).toBeInTheDocument()
    expect(screen.getByTestId('gate-genre')).toBeInTheDocument()
    expect(screen.getByTestId('gate-brief')).toBeInTheDocument()
    expect(screen.getByTestId('gate-vessel-panel')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByTestId('vessel-bay-proj_reborn')).toBeInTheDocument()
    })
  })

  it('blocks submission without a title', async () => {
    renderGate()
    fireEvent.click(screen.getByTestId('gate-submit'))
    expect(await screen.findByTestId('gate-error')).toBeInTheDocument()
    expect(apiMocks.createProject).not.toHaveBeenCalled()
  })

  it('creates the project and routes it to the Page', async () => {
    renderGate()
    fireEvent.change(screen.getByTestId('gate-title'), { target: { value: 'Neon Dreams' } })
    fireEvent.change(screen.getByTestId('gate-brief'), { target: { value: 'A synth-drenched elegy.' } })
    fireEvent.click(screen.getByTestId('gate-submit'))
    await waitFor(() => {
      expect(apiMocks.createProject).toHaveBeenCalledWith({ title: 'Neon Dreams' })
    })
    expect(await screen.findByTestId('location-probe')).toHaveTextContent('/studio/page?project_id=proj_new')
  })

  it('opens a docked bay on the Page', async () => {
    renderGate()
    fireEvent.click(await screen.findByTestId('vessel-bay-proj_reborn'))
    expect(await screen.findByTestId('location-probe')).toHaveTextContent(
      '/studio/page?project_id=proj_reborn',
    )
  })
})
