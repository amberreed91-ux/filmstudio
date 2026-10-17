// @vitest-environment jsdom
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import StudioLobby from './StudioLobby'

vi.mock('../components/StudioShell', () => ({
  default: ({ children }: { children: ReactNode }) => createElement('div', null, children),
}))

vi.mock('../components/LazyLoad', () => ({
  lazyLoad: () => () => null,
}))

vi.mock('../context/StudioContext', () => ({
  useStudio: () => ({ setActiveProject: vi.fn() }),
}))

const apiMocks = vi.hoisted(() => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
  deleteProject: vi.fn(),
}))

vi.mock('../lib/studioApi', () => apiMocks)

function LocationProbe() {
  const location = useLocation()
  return createElement('div', { 'data-testid': 'location-probe' }, location.pathname)
}

function renderLobby() {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries: ['/studio/lobby'] },
      createElement(
        Routes,
        null,
        createElement(Route, { path: '/studio/lobby', element: createElement(StudioLobby) }),
        createElement(Route, { path: '/studio/lobby-3d', element: createElement(LocationProbe) }),
        createElement(Route, { path: '/studio/previs', element: createElement(LocationProbe) }),
      ),
    ),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMocks.listProjects.mockResolvedValue({ projects: [], error: '' })
})

afterEach(cleanup)

describe('StudioLobby 3D entry button', () => {
  it('renders a discoverable 3D Studio Lobby button pointing at /studio/lobby-3d', async () => {
    renderLobby()
    const button = await screen.findByTestId('enter-3d-lobby')
    expect(button).toHaveTextContent('3D Studio Lobby')
    expect(button).toHaveAttribute('href', '/studio/lobby-3d')
  })

  it('navigates to the 3D lobby when the button is clicked', async () => {
    renderLobby()
    fireEvent.click(await screen.findByTestId('enter-3d-lobby'))
    expect(await screen.findByTestId('location-probe')).toHaveTextContent('/studio/lobby-3d')
  })

  it('leaves existing 2D room card routing untouched', async () => {
    renderLobby()
    await screen.findByTestId('enter-3d-lobby')
    const storyboard = screen.getByText('Storyboard').closest('a')
    expect(storyboard).toHaveAttribute('href', '/studio/previs')
    fireEvent.click(storyboard!)
    expect(await screen.findByTestId('location-probe')).toHaveTextContent('/studio/previs')
  })
})
