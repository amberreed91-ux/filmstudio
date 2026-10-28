import { useMemo, useState } from 'react'
import {
  castCollaborationVote,
  createCollaborationSession,
  getCollaborationState,
  postCollaborationComment,
  type CollaborationRole,
  type CollaborationState,
} from '../lib/studioApi'

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

const MOCK_USER = { actor_id: 'owner', actor_name: 'Project Owner', actor_role: 'producer' as CollaborationRole }

export default function MultiUserCollaborationPanel({ projectId, room, sceneId }: { projectId: string; room: string; sceneId?: string }) {
  const [commentText, setCommentText] = useState('')
  const [note, setNote] = useState('')
  const [state, setState] = useState<CollaborationState | null>(null)
  const [busy, setBusy] = useState(false)

  const comments = useMemo(() => {
    const rows = Array.isArray(state?.live_comments) ? state?.live_comments : []
    const parsed = rows.map((entry) => asRecord(entry)).filter((entry): entry is Record<string, unknown> => Boolean(entry))
    if (parsed.length > 0) return parsed.slice(-3).reverse()
    return [{ display_name: 'Memory Archivist', role: 'reviewer', comment: 'Shared room standing by for notes.' }]
  }, [state?.live_comments])

  const votes = useMemo(() => {
    const rows = Array.isArray(state?.approval_votes) ? state?.approval_votes : []
    const sceneVotes = rows
      .map((entry) => asRecord(entry))
      .filter(Boolean)
      .filter((entry) => !sceneId || asString(entry?.scene_id) === sceneId)
    const tally = { approve: 0, revise: 0, regenerate: 0 }
    for (const row of sceneVotes) {
      const vote = asString(row?.vote)
      if (vote === 'approve' || vote === 'revise' || vote === 'regenerate') tally[vote] += 1
    }
    return tally
  }, [sceneId, state?.approval_votes])

  async function refresh() {
    if (!projectId) return
    const loaded = await getCollaborationState(projectId)
    if (loaded.collaboration) setState(loaded.collaboration)
  }

  async function ensureSession() {
    if (!projectId) return
    const created = await createCollaborationSession(projectId, MOCK_USER)
    if (created.collaboration) setState(created.collaboration)
  }

  async function sendComment() {
    if (!projectId || !commentText.trim()) return
    setBusy(true)
    try {
      await ensureSession()
      const result = await postCollaborationComment(projectId, { ...MOCK_USER, room, comment: commentText })
      if (result.collaboration) {
        setState(result.collaboration)
        setCommentText('')
      }
    } finally {
      setBusy(false)
    }
  }

  async function vote(choice: 'approve' | 'revise' | 'regenerate') {
    if (!projectId) return
    setBusy(true)
    try {
      await ensureSession()
      const targetScene = sceneId || 'scene_001'
      const result = await castCollaborationVote(projectId, { ...MOCK_USER, scene_id: targetScene, vote: choice })
      if (result.collaboration) setState(result.collaboration)
    } finally {
      setBusy(false)
    }
  }

  async function addCoDirectionNote() {
    if (!note.trim()) return
    setBusy(true)
    try {
      await ensureSession()
      const result = await postCollaborationComment(projectId, {
        ...MOCK_USER,
        room,
        comment: `[CO-DIRECTION] ${note.trim()}`,
      })
      if (result.collaboration) {
        setState(result.collaboration)
        setNote('')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="collab-panel" data-testid={`collab-panel-${room}`}>
      <div className="collab-panel-head">
        <div className="collab-panel-title">Multi-User Collaboration</div>
        <button type="button" className="collab-mini-btn" onClick={() => void refresh()} disabled={busy} aria-busy={busy}>Sync</button>
      </div>
      <div className="collab-panel-sub">Shared room: {state?.shared_room || room} · Session: {state?.session_id || 'not started'}</div>

      <div className="collab-vote-row">
        <button type="button" className="collab-vote-btn" onClick={() => void vote('approve')} disabled={busy} aria-busy={busy}>Approve ({votes.approve})</button>
        <button type="button" className="collab-vote-btn" onClick={() => void vote('revise')} disabled={busy} aria-busy={busy}>Revise ({votes.revise})</button>
        <button type="button" className="collab-vote-btn" onClick={() => void vote('regenerate')} disabled={busy} aria-busy={busy}>Regenerate ({votes.regenerate})</button>
      </div>

      <div className="collab-comment-box">
        <input
          value={commentText}
          onChange={(event) => setCommentText(event.target.value)}
          placeholder="Live comment..."
          className="collab-input"
        />
        <button type="button" className="collab-mini-btn" onClick={() => void sendComment()} disabled={busy || !commentText.trim()} aria-busy={busy}>Send</button>
      </div>

      <div className="collab-comment-box">
        <input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Co-direction note..."
          className="collab-input"
        />
        <button type="button" className="collab-mini-btn" onClick={() => void addCoDirectionNote()} disabled={busy || !note.trim()} aria-busy={busy}>Add</button>
      </div>

      <div className="collab-feed">
        {comments.map((row, index) => (
          <div key={`collab-comment-${index}`} className="collab-feed-row">
            <span className="collab-feed-author">{asString(row.display_name) || 'Collaborator'} ({asString(row.role) || 'reviewer'})</span>
            <span className="collab-feed-text">{asString(row.comment)}</span>
          </div>
        ))}
      </div>
      <div className="collab-foot">Advisory co-direction only. Project ownership remains authoritative.</div>
    </section>
  )
}
