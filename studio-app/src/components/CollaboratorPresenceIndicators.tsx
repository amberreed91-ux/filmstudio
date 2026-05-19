import { useMemo } from 'react'
import type { CollaborationState } from '../lib/studioApi'

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

export default function CollaboratorPresenceIndicators({ collaboration }: { collaboration?: CollaborationState | null }) {
  const rows = useMemo(() => {
    const source = Array.isArray(collaboration?.presence) ? collaboration?.presence : []
    const parsed = source
      .map((entry) => asRecord(entry))
      .filter(Boolean)
      .map((entry) => ({
        userId: asString(entry?.user_id),
        name: asString(entry?.display_name) || 'Collaborator',
        role: asString(entry?.role) || 'reviewer',
        room: asString(entry?.room) || 'lobby',
      }))
      .filter((entry) => Boolean(entry.userId))
    
    return parsed.slice(0, 6)
  }, [collaboration?.presence])

  return (
    <aside className="collab-presence" data-testid="collab-presence-indicators">
      <div className="collab-presence-title">Collaborators Live</div>
      <div className="collab-presence-list">
        {rows.length > 0 ? (
          rows.map((row) => (
            <div key={row.userId} className="collab-presence-row">
              <span className="collab-presence-dot" />
              <span className="collab-presence-name">{row.name}</span>
              <span className="collab-presence-meta">{row.role} · {row.room}</span>
            </div>
          ))
        ) : (
          <div className="collab-presence-empty text-zinc-400">No active collaborators right now.</div>
        )}
      </div>
    </aside>
  )
}
