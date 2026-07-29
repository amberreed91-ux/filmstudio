import { useState } from 'react'
import { CheckCircle, AlertTriangle, Clock, Loader2 } from 'lucide-react'
import type { Scene, ApprovalStatus } from '../lib/studioApi'
import { updateSceneApproval } from '../lib/studioApi'
import { canApprove } from './CollaboratorRoleBadge'
import type { CollaboratorRole } from '../lib/studioApi'

type ApprovalControlsProps = {
  scene: Scene
  currentUserRole: CollaboratorRole
  currentUserEmail: string
  onApprovalUpdated?: (approval: { status: ApprovalStatus; notes?: string }) => void
}

const APPROVAL_CONFIG: Record<ApprovalStatus, { label: string; icon: React.ReactNode; color: string }> = {
  pending: {
    label: 'Pending Review',
    icon: <Clock size={14} className="text-amber-400" />,
    color: 'text-amber-400',
  },
  approved: {
    label: 'Approved',
    icon: <CheckCircle size={14} className="text-emerald-400" />,
    color: 'text-emerald-400',
  },
  changes_requested: {
    label: 'Changes Requested',
    icon: <AlertTriangle size={14} className="text-rose-400" />,
    color: 'text-rose-400',
  },
}

export default function ApprovalControls({
  scene,
  currentUserRole,
  onApprovalUpdated,
}: ApprovalControlsProps) {
  const [isUpdating, setIsUpdating] = useState(false)
  const [notes, setNotes] = useState('')
  const [showNotesInput, setShowNotesInput] = useState(false)

  const canApproveHere = canApprove(currentUserRole)
  const currentStatus = scene.approval?.status || 'pending'

  async function handleApproval(status: ApprovalStatus) {
    if (!scene.scene_id || isUpdating) return

    try {
      setIsUpdating(true)
      const updatedApproval = await updateSceneApproval(
        scene.scene_id,
        status,
        showNotesInput ? notes : undefined
      )
      setNotes('')
      setShowNotesInput(false)
      onApprovalUpdated?.(updatedApproval)
    } catch (error) {
      console.error('Failed to update approval:', error)
    } finally {
      setIsUpdating(false)
    }
  }

  function getStatusBadge() {
    const config = APPROVAL_CONFIG[currentStatus]
    return (
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${config.color} bg-current/10 border border-current/20`}
      >
        {config.icon}
        {config.label}
      </span>
    )
  }

  if (!canApproveHere) {
    return (
      <div className="mt-4 pt-4 border-t border-white/10">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Approval Status</span>
          {getStatusBadge()}
        </div>
        {scene.approval?.approved_by && (
          <p className="text-[10px] text-zinc-500 mt-1">
            {scene.approval.status === 'approved'
              ? `Approved by ${scene.approval.approved_by}`
              : `Changes requested by ${scene.approval.requested_changes_by}`}
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="mt-4 pt-4 border-t border-white/10">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] uppercase tracking-wider text-zinc-500">Approval Status</span>
        {getStatusBadge()}
      </div>

      {showNotesInput ? (
        <div className="space-y-2">
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Add approval notes (optional)..."
            className="w-full bg-zinc-800/50 border border-white/10 rounded-md px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-cyan-400/50 resize-none"
            rows={2}
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setShowNotesInput(false)}
              className="px-3 py-1.5 text-xs font-medium rounded-md border border-zinc-600 bg-zinc-800/50 text-zinc-300 hover:bg-zinc-700/50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleApproval('approved')}
              disabled={isUpdating}
              className="px-3 py-1.5 text-xs font-medium rounded-md border border-emerald-400/40 bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50 transition-colors flex items-center gap-1"
            >
              {isUpdating ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />}
              Approve
            </button>
            <button
              type="button"
              onClick={() => void handleApproval('changes_requested')}
              disabled={isUpdating}
              className="px-3 py-1.5 text-xs font-medium rounded-md border border-rose-400/40 bg-rose-500/15 text-rose-200 hover:bg-rose-500/20 disabled:opacity-50 transition-colors flex items-center gap-1"
            >
              {isUpdating ? <Loader2 size={12} className="animate-spin" /> : <AlertTriangle size={12} />}
              Request Changes
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void handleApproval('approved')}
            disabled={isUpdating || currentStatus === 'approved'}
            className="flex-1 px-3 py-1.5 text-xs font-medium rounded-md border border-emerald-400/40 bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-1"
          >
            {isUpdating ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />}
            Approve
          </button>
          <button
            type="button"
            onClick={() => {
              setShowNotesInput(true)
              setNotes(scene.approval?.notes || '')
            }}
            disabled={isUpdating}
            className="flex-1 px-3 py-1.5 text-xs font-medium rounded-md border border-amber-400/40 bg-amber-500/15 text-amber-200 hover:bg-amber-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-1"
          >
            <Clock size={12} />
            Request Changes
          </button>
        </div>
      )}

      {scene.approval && (
        <div className="mt-2 text-[10px] text-zinc-500">
          {scene.approval.approved_at && (
            <p>Approved by {scene.approval.approved_by} on {new Date(scene.approval.approved_at).toLocaleString()}</p>
          )}
          {scene.approval.requested_changes_at && (
            <p>Changes requested by {scene.approval.requested_changes_by} on {new Date(scene.approval.requested_changes_at).toLocaleString()}</p>
          )}
          {scene.approval.notes && (
            <p className="text-zinc-400 mt-1">{scene.approval.notes}</p>
          )}
        </div>
      )}
    </div>
  )
}

// Helper to get approval status label
// eslint-disable-next-line react-refresh/only-export-components
export function getApprovalLabel(status: ApprovalStatus): string {
  return APPROVAL_CONFIG[status].label
}

// Helper to get approval icon
// eslint-disable-next-line react-refresh/only-export-components
export function getApprovalIcon(status: ApprovalStatus): React.ReactNode {
  return APPROVAL_CONFIG[status].icon
}
