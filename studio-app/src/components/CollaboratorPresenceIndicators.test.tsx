import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import CollaboratorPresenceIndicators from './CollaboratorPresenceIndicators'

describe('CollaboratorPresenceIndicators', () => {
  it('renders honest empty state when no collaborators are active', () => {
    const html = renderToStaticMarkup(<CollaboratorPresenceIndicators />)
    expect(html).toContain('Collaborators Live')
    expect(html).toContain('No active collaborators right now.')
  })

  it('renders provided collaborator rows when real data exists', () => {
    const html = renderToStaticMarkup(
      <CollaboratorPresenceIndicators
        collaboration={{
          presence: [
            { user_id: 'user-1', display_name: 'Alex', role: 'director', room: 'study' },
            { user_id: 'user-2', display_name: 'Jordan', role: 'editor', room: 'previs' },
          ],
        }}
      />,
    )

    expect(html).toContain('Alex')
    expect(html).toContain('director · study')
    expect(html).toContain('Jordan')
    expect(html).toContain('editor · previs')
  })
})
