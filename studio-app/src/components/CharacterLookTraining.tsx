import { useState } from 'react'
import { Sparkles, Check, Loader2 } from 'lucide-react'
import type { CharacterLook } from '../lib/characterLookApi'
import { useVisualTraining, findModelForTarget } from '../hooks/useVisualTraining'
import VisualTrainingPanel from './VisualTrainingPanel'
import ReferenceLibraryPanel from './ReferenceLibraryPanel'

/**
 * Character identity training entry point, embedded in the approved/locked
 * Character Look workflow. "Train This Look" is the natural next step after a
 * look is locked. If a reusable identity already exists for this character, it
 * is shown as a production asset and never auto-recreated — retraining is an
 * explicit choice made inside the panel.
 *
 * All lifecycle state lives in `useVisualTraining`; this component owns only
 * presentation + open/close UI state.
 */
export default function CharacterLookTraining({ projectId, look }: { projectId: string; look: CharacterLook }) {
  const controller = useVisualTraining(projectId, 'character')
  const [open, setOpen] = useState(false)
  const existing = findModelForTarget(controller.models, look.character_id)

  const secondaryButton =
    'inline-flex items-center justify-center gap-2 rounded-md border border-white/20 px-3 py-2.5 text-xs font-medium text-zinc-200 hover:border-white/35 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 disabled:cursor-not-allowed disabled:opacity-40'

  return (
    <div className="mt-4" data-testid="character-look-training">
      {existing ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-emerald-400/25 bg-emerald-500/[0.06] px-4 py-3">
          <div className="min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-[0.15em] text-emerald-300/80">Visual identity ready</p>
            <p className="mt-0.5 truncate font-mono text-sm text-zinc-100">{existing.trigger_word}</p>
            <p className="mt-1 text-[11px] text-zinc-400">
              {existing.provider} · {existing.provider_model} · {existing.source_asset_ids.length} {existing.source_asset_ids.length === 1 ? 'reference' : 'references'}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[11px] text-emerald-200"><Check size={12} />Ready</span>
            <button type="button" onClick={() => setOpen(true)} className={secondaryButton}>
              <Sparkles size={14} />View / retrain
            </button>
          </div>
        </div>
      ) : (
        <div>
          <button type="button" onClick={() => setOpen(true)} className={secondaryButton} data-testid="train-this-look">
            {controller.modelsLoading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            Train This Look
          </button>
          <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">
            Turn {look.name}’s approved references into a reusable visual identity for Previs and rendering.
          </p>
        </div>
      )}

      <ReferenceLibraryPanel projectId={projectId} targetType="character" targetId={look.character_id} />

      {open && (
        <VisualTrainingPanel
          controller={controller}
          canonicalTargetId={look.character_id}
          targetName={look.name}
          targetSubtitle={`Approved look · version ${look.version}`}
          previewImageUrl={look.face_image_url}
          approvalLabel="Look locked"
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  )
}
