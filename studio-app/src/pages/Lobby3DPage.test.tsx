// @vitest-environment jsdom
import { createElement, type ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import Lobby3DPage from './Lobby3DPage'
import { APP_ROUTES } from '../routes'
import { LOBBY_ROOMS } from '../components/Interactive3DLobby'

vi.mock('../components/StudioShell', () => ({
  default: ({ children }: { children: ReactNode }) => createElement('div', null, children),
}))

function LocationProbe() {
  const location = useLocation()
  return createElement('div', { 'data-testid': 'location-probe' }, location.pathname)
}

function renderLobby(initialEntries = ['/studio/lobby-3d']) {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries },
      createElement(
        Routes,
        null,
        createElement(Route, { path: '/studio/lobby-3d', element: createElement(Lobby3DPage) }),
        createElement(Route, { path: '/studio/production-desk', element: createElement(LocationProbe) }),
        createElement(Route, { path: '/studio/reference-space', element: createElement(LocationProbe) }),
        createElement(Route, { path: '/studio/previs', element: createElement(LocationProbe) }),
        createElement(Route, { path: '/studio/integrity', element: createElement(LocationProbe) }),
        createElement(Route, { path: '/studio/universe-graph', element: createElement(LocationProbe) }),
        createElement(Route, { path: '/studio/production-board', element: createElement(LocationProbe) }),
        createElement(Route, { path: '/studio/writers-room', element: createElement(LocationProbe) }),
        createElement(Route, { path: '/studio/screening-room', element: createElement(LocationProbe) }),
        createElement(Route, { path: '/studio/overview', element: createElement(LocationProbe) }),
      ),
    ),
  )
}

afterEach(cleanup)

describe('Lobby3DPage', () => {
  it('registers the /studio/lobby-3d route without touching backend or 2D room paths', () => {
    const lobby = APP_ROUTES.find((entry) => entry.path === '/studio/lobby-3d')
    expect(lobby).toBeTruthy()
    expect(lobby?.placement).toBe('hidden-system')
    // Every hotspot must point at a real registered room route.
    for (const room of LOBBY_ROOMS) {
      expect(APP_ROUTES.some((entry) => entry.path === room.to)).toBe(true)
    }
  })

  it('covers all primary studio room routes', () => {
    const targets = new Set(LOBBY_ROOMS.map((room) => room.to))
    for (const to of [
      '/studio/production-desk',
      '/studio/reference-space',
      '/studio/previs',
      '/studio/integrity',
      '/studio/universe-graph',
      '/studio/production-board',
    ]) {
      expect(targets.has(to)).toBe(true)
    }
  })

  it('renders the 3D stage with a 2D fallback toggle', async () => {
    renderLobby()
    expect(screen.getByText('Walk the studio floor')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Switch to 2D List View' })).toBeInTheDocument()
    // jsdom has no WebGL: the component degrades to an accessible room grid
    // instead of crashing, and every hotspot stays keyboard-reachable.
    await waitFor(() => {
      expect(screen.getByTestId('lobby-3d-fallback')).toBeInTheDocument()
    })
    expect(screen.getByTestId('lobby-3d-node-production-desk')).toBeInTheDocument()
  })

  it('routes a 3D hotspot straight to its existing 2D room', async () => {
    renderLobby()
    const node = await screen.findByTestId('lobby-3d-node-production-desk')
    fireEvent.click(node)
    expect(await screen.findByTestId('location-probe')).toHaveTextContent('/studio/production-desk')
  })

  it('toggles between the spatial view and the 2D list view', async () => {
    renderLobby()
    fireEvent.click(screen.getByRole('button', { name: 'Switch to 2D List View' }))
    expect(await screen.findByTestId('lobby-2d-list')).toBeInTheDocument()
    expect(screen.getByTestId('lobby-2d-node-reference-space')).toHaveAttribute(
      'href',
      '/studio/reference-space',
    )
    fireEvent.click(screen.getByRole('button', { name: '3D Studio Lobby' }))
    await waitFor(() => {
      expect(screen.queryByTestId('lobby-2d-list')).not.toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'Switch to 2D List View' })).toBeInTheDocument()
  })

  it('routes a 2D list entry to its existing room', async () => {
    renderLobby()
    fireEvent.click(screen.getByRole('button', { name: 'Switch to 2D List View' }))
    const entry = await screen.findByTestId('lobby-2d-node-previs')
    fireEvent.click(entry)
    expect(await screen.findByTestId('location-probe')).toHaveTextContent('/studio/previs')
  })
})
