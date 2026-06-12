import { useState } from 'react'
import { Send, Trash2, User } from 'lucide-react'
import type { SceneComment, Scene } from '../lib/studioApi'
import { addSceneComment, deleteSceneComment } from '../lib/studioApi'
import { useStudio } from '../context/StudioContext'
import { canDelete, canComment } from './CollaboratorRoleBadge'
import CollaboratorRoleBadge from './CollaboratorRoleBadge'

type CommentSectionProps = {
  scene: Scene
  currentUserRole?: 'owner' | 'editor' | 'viewer'
  currentUserEmail?: string
  onCommentAdded?: (comment: SceneComment) => void
  onCommentDeleted?: (commentId: string) => void
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffInHours = (now.getTime() - date.getTime()) / (1000 * 60 * 60)

  if (diffInHours < 1) {
    const diffInMinutes = Math.floor(diffInHours * 60)
    return diffInMinutes < 1 ? 'Just now' : `${diffInMinutes}m ago`
  }
  if (diffInHours < 24) {
    return `${Math.floor(diffInHours)}h ago`
  }
  if (diffInHours < 24 * 7) {
    return `${Math.floor(diffInHours / 24)}d ago`
  }
  return date.toLocaleDateString()
}

export default function CommentSection({
  scene,
  currentUserRole = 'viewer',
  currentUserEmail = '',
  onCommentAdded,
  onCommentDeleted,
}: CommentSectionProps) {
  const [newComment, setNewComment] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const { activeProject } = useStudio()

  const comments = scene.comments || []
  const canCommentHere = canComment(currentUserRole)

  async function handleAddComment() {
    if (!newComment.trim() || !scene.scene_id || isSubmitting) return

    try {
      setIsSubmitting(true)
      const author = currentUserEmail || activeProject?.title || 'Anonymous'
      const comment = await addSceneComment(scene.scene_id, newComment.trim(), author)
      setNewComment('')
      onCommentAdded?.(comment)
    } catch (error) {
      console.error('Failed to add comment:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleDeleteComment(commentId: string) {
    if (!scene.scene_id) return

    try {
      await deleteSceneComment(scene.scene_id, commentId)
      onCommentDeleted?.(commentId)
    } catch (error) {
      console.error('Failed to delete comment:', error)
    }
  }

  function canDeleteComment(comment: SceneComment): boolean {
    // Owner can delete any comment
    if (currentUserRole === 'owner') return true
    // Users can delete their own comments
    if (comment.author === currentUserEmail) return true
    return false
  }

  if (!canCommentHere && comments.length === 0) {
    return null
  }

  return (
    <div className="mt-4 pt-4 border-t border-white/10">
      <h4 className="text-[10px] uppercase tracking-wider text-zinc-500 mb-3 flex items-center gap-1">
        <User size={12} />
        Comments ({comments.length})
      </h4>

      {/* Comment List */}
      <div className="space-y-3 mb-3">
        {comments.map((comment) => (
          <div
            key={comment.id}
            className="flex gap-2 group"
          >
            {/* Author Avatar */}
            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-zinc-700 flex items-center justify-center">
              <User size={12} className="text-zinc-400" />
            </div>

            {/* Comment Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-xs font-medium text-zinc-300">{comment.author}</span>
                <span className="text-[10px] text-zinc-500">{formatTimestamp(comment.timestamp)}</span>
              </div>
              <p className="text-sm text-zinc-300 bg-zinc-800/50 rounded px-2 py-1">{comment.text}</p>
            </div>

            {/* Delete Button */}
            {canDeleteComment(comment) && (
              <button
                type="button"
                onClick={() => handleDeleteComment(comment.id)}
                className="opacity-0 group-hover:opacity-100 p-1 rounded text-zinc-500 hover:text-rose-300 hover:bg-rose-500/10 transition-all"
                title="Delete comment"
              >
                <Trash2 size={12} />
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Comment Input */}
      {canCommentHere && (
        <div className="flex gap-2">
          <input
            type="text"
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            placeholder="Add a comment..."
            className="flex-1 bg-zinc-800/50 border border-white/10 rounded-md px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-cyan-400/50 focus:bg-zinc-700/50"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                void handleAddComment()
              }
            }}
            disabled={isSubmitting}
          />
          <button
            type="button"
            onClick={void handleAddComment()}
            disabled={!newComment.trim() || isSubmitting}
            className="px-3 py-2 rounded-md border border-white/15 bg-zinc-800/50 text-zinc-300 hover:bg-zinc-700/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-1"
            title="Add comment"
          >
            <Send size={14} />
            <span className="text-xs">Post</span>
          </button>
        </div>
      )}

      {!canCommentHere && comments.length > 0 && (
        <p className="text-[10px] text-zinc-600 mt-2">
          Comments visible but read-only for viewers
        </p>
      )}
    </div>
  )
}

// Export helper for use in other components
export { formatTimestamp, canDeleteComment }
