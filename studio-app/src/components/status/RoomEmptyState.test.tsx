import { describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { Camera } from 'lucide-react'
import { MemoryRouter } from 'react-router-dom'
import RoomEmptyState from './RoomEmptyState'
import { ROOM_EMPTY_STATES } from '../../lib/roomHandoff'

function render(node: ReactNode) {
  return renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>)
}

describe('RoomEmptyState', () => {
  it('renders one title, one sentence, and one action with project context', () => {
    const html = render(
      <RoomEmptyState state={ROOM_EMPTY_STATES.scenes} icon={Camera} projectId="project_1" testId="scenes-empty" />,
    )
    expect(html).toContain('Your scene wall starts with a script')
    expect(html).toContain('No scenes yet.')
    expect(html).toContain('href="/studio/writers-room?project_id=project_1"')
    expect(html).toContain('data-testid="scenes-empty"')
    expect(html.match(/<button|<a /g)).toHaveLength(1)
  })

  it('swaps the link for a local action when the next move is in-room', () => {
    const onClick = vi.fn()
    const html = render(
      <RoomEmptyState
        state={{ title: 'No matching scenes', body: 'Clear the filter to see every scene.', action: null }}
        icon={Camera}
        action={{ label: 'Clear filter', onClick }}
      />,
    )
    expect(html).toContain('Clear filter')
    expect(html).toContain('<button')
    expect(html).not.toContain('href=')
  })

  it('renders no action when the room has nothing to offer yet', () => {
    const html = render(<RoomEmptyState state={ROOM_EMPTY_STATES.previsTakes} icon={Camera} />)
    expect(html).toContain('No takes for this shot yet')
    expect(html).not.toMatch(/<button|<a /)
  })
})
