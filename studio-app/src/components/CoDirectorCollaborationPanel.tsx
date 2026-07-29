import { useMemo } from 'react'

type AnyRecord = Record<string, unknown>

type CollaborationMode = 'passive' | 'advisory' | 'collaborative' | 'experimental'

function asRecord(value: unknown): AnyRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as AnyRecord
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((entry) => asString(entry)).filter(Boolean)
}

function normalizeMode(value: unknown): CollaborationMode {
  const mode = asString(value).toLowerCase()
  if (mode === 'advisory' || mode === 'collaborative' || mode === 'experimental') return mode
  return 'passive'
}

export default function CoDirectorCollaborationPanel({
  workflow,
  room,
}: {
  workflow?: unknown
  room: 'director' | 'screening' | 'writer'
}) {
  const root = asRecord(workflow)
  const collaboration = asRecord(root?.collaboration)
  const mode = normalizeMode(root?.mode || root?.current_mode)

  const disagreementRows = asStringList(collaboration?.creative_disagreements)
  const alternateRows = asStringList(collaboration?.alternate_scene_suggestions)
  const visualRows = asStringList(collaboration?.visual_experiments)
  const thematicRows = asStringList(collaboration?.thematic_proposals)

  const hasLive = disagreementRows.length > 0 || alternateRows.length > 0 || visualRows.length > 0 || thematicRows.length > 0

  const display = useMemo(() => {
    if (hasLive) {
      return {
        disagreements: disagreementRows,
        alternates: alternateRows,
        visuals: visualRows,
        themes: thematicRows,
      }
    }
    return {
      disagreements: [],
      alternates: [],
      visuals: [],
      themes: [],
    }
  }, [alternateRows, disagreementRows, hasLive, thematicRows, visualRows])

  return (
    <section className="co-director-collab-panel" data-testid={`co-director-collab-${room}`}>
      <div className="co-director-collab-head">
        <div className="co-director-collab-title">AI Co-Director Collaboration</div>
        <div className="co-director-collab-mode">Mode: {mode.toUpperCase()}</div>
      </div>
      <div className="co-director-collab-grid">
        <article className="co-director-collab-card">
          <div className="co-director-collab-label">Creative Disagreements</div>
          <p>{display.disagreements[0] || 'No active disagreements.'}</p>
        </article>
        <article className="co-director-collab-card">
          <div className="co-director-collab-label">Alternate Scene Suggestion</div>
          <p>{display.alternates[0] || 'No alternate suggestions yet.'}</p>
        </article>
        <article className="co-director-collab-card">
          <div className="co-director-collab-label">Visual Experimentation</div>
          <p>{display.visuals[0] || 'No visual experiments available.'}</p>
        </article>
        <article className="co-director-collab-card">
          <div className="co-director-collab-label">Thematic Proposal</div>
          <p>{display.themes[0] || 'No thematic proposals available.'}</p>
        </article>
      </div>
      <div className="co-director-collab-footer">Advisory only. Creator approval remains authoritative.</div>
    </section>
  )
}
