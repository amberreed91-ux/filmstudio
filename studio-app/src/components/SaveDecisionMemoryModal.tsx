/**
 * Save Decision Memory Modal
 * 
 * Following AGENTS.md Creative Decision Memory Rules:
 * - Show user exactly what will be saved
 * - Allow editing before saving
 * - Allow discard
 * - Allow session-only mode
 * - Every memory is editable and forgettable
 */

import { useState } from 'react'
import type { CreativeDecisionMemory, DecisionType, InferredTradeoff } from '../types/creativeMemory'

type SaveDecisionMemoryModalProps = {
  isOpen: boolean
  onClose: () => void
  onSave: (memory: Omit<CreativeDecisionMemory, 'memory_id' | 'saved_at'>) => Promise<void>
  onSessionOnly: () => void
  initialNote: string
  inferredTradeoff: InferredTradeoff
  inferredExplanation: string
  sourceContext: CreativeDecisionMemory['source_context']
  projectId: string
}

const DECISION_TYPE_LABELS: Record<DecisionType, string> = {
  cut_revision: 'Cut Revision Decision',
  scene_approval: 'Scene Approval',
  pacing_choice: 'Pacing Choice',
  tension_adjustment: 'Tension Adjustment',
  visual_preference: 'Visual Preference',
  creative_note: 'Creative Note',
}

const TRADEOFF_LABELS: Record<InferredTradeoff, string> = {
  emotional_residue_favored: 'Emotional Residue Favored',
  structural_clarity_favored: 'Structural Clarity Favored',
  balanced_approach: 'Balanced Approach',
  not_inferred: 'No Clear Preference',
}

export default function SaveDecisionMemoryModal(props: SaveDecisionMemoryModalProps) {
  const [userNote, setUserNote] = useState(props.initialNote)
  const [decisionType, setDecisionType] = useState<DecisionType>('creative_note')
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')

  if (!props.isOpen) return null

  const handleSave = async () => {
    if (!userNote.trim()) {
      setError('Note cannot be empty')
      return
    }

    setIsSaving(true)
    setError('')

    try {
      await props.onSave({
        project_id: props.projectId,
        decision_type: decisionType,
        user_note: userNote.trim(),
        inferred_tradeoff: props.inferredTradeoff,
        inferred_tradeoff_explanation: props.inferredExplanation,
        source_context: props.sourceContext,
        editable: true,
        forgettable: true,
      })
      props.onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save decision memory')
    } finally {
      setIsSaving(false)
    }
  }

  const handleSessionOnly = () => {
    props.onSessionOnly()
    props.onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" data-testid="save-decision-memory-modal">
      <div className="w-full max-w-2xl rounded-2xl border border-zinc-700/70 bg-gradient-to-br from-zinc-950 via-zinc-900 to-black p-6 shadow-[0_20px_60px_rgba(0,0,0,0.6)]">
        <div className="text-[11px] uppercase tracking-[0.16em] text-fuchsia-200">Save Decision to Project Memory</div>
        <h2 className="mt-1 text-xl font-semibold text-zinc-100">Review Before Saving</h2>
        <p className="mt-2 text-sm text-zinc-300">
          You can edit this decision before saving it to project memory. This memory will be editable and forgettable.
        </p>

        <div className="mt-4 space-y-4">
          {/* Decision Type */}
          <div>
            <label htmlFor="decision-type" className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">
              Decision Type
            </label>
            <select
              id="decision-type"
              value={decisionType}
              onChange={(e) => setDecisionType(e.target.value as DecisionType)}
              className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950/80 px-3 py-2 text-sm text-zinc-100"
            >
              {Object.entries(DECISION_TYPE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {/* User Note */}
          <div>
            <label htmlFor="user-note" className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">
              Your Note (Required)
            </label>
            <textarea
              id="user-note"
              value={userNote}
              onChange={(e) => setUserNote(e.target.value)}
              placeholder="Describe this creative decision..."
              className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950/80 px-3 py-2 text-sm text-zinc-100"
              rows={4}
            />
          </div>

          {/* Inferred Tradeoff (Read-Only, Language Only) */}
          <div className="rounded-lg border border-white/10 bg-black/25 p-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">Studio's Creative Read</div>
            <p className="mt-1 text-xs text-zinc-300">
              Preference: <span className="text-zinc-100">{TRADEOFF_LABELS[props.inferredTradeoff]}</span>
            </p>
            <p className="mt-1 text-xs text-zinc-400">{props.inferredExplanation}</p>
            <p className="mt-2 text-[10px] text-zinc-500">
              This is the Studio's interpretation based on your choice. No scores or percentages are stored.
            </p>
          </div>

          {/* Source Context (Read-Only) */}
          <div className="rounded-lg border border-white/10 bg-black/25 p-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">Context</div>
            <div className="mt-1 space-y-1 text-xs text-zinc-400">
              {props.sourceContext.scene_id && (
                <div>Scene: <span className="text-zinc-200">{props.sourceContext.scene_id}</span></div>
              )}
              {props.sourceContext.revision_id && (
                <div>Revision: <span className="text-zinc-200">{props.sourceContext.revision_id}</span></div>
              )}
              {props.sourceContext.revision_emphasis && (
                <div>Emphasis: <span className="text-zinc-200">{props.sourceContext.revision_emphasis}</span></div>
              )}
              <div>Source: <span className="text-zinc-200">{props.sourceContext.screen_location}</span></div>
            </div>
          </div>

          {/* Error Display */}
          {error && (
            <div className="rounded-md border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
              {error}
            </div>
          )}

          {/* Important Note */}
          <div className="rounded-md border border-cyan-400/30 bg-cyan-500/8 px-3 py-2">
            <p className="text-xs text-cyan-100">
              <strong>Important:</strong> This memory will be saved to your project and can be edited or deleted at any time.
              It will not affect your workflow or block any actions.
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="mt-6 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving || !userNote.trim()}
            aria-busy={isSaving}
            className="rounded-md border border-fuchsia-400/45 bg-fuchsia-500/14 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-fuchsia-100 disabled:opacity-50"
          >
            {isSaving ? 'Saving...' : 'Save to Project Memory'}
          </button>
          <button
            type="button"
            onClick={handleSessionOnly}
            className="rounded-md border border-amber-400/45 bg-amber-500/14 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-100"
          >
            Keep Session-Only (Don't Save)
          </button>
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md border border-zinc-600/80 bg-zinc-900/70 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-200"
          >
            Discard
          </button>
        </div>
      </div>
    </div>
  )
}
