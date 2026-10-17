import { SceneDirectionPanel } from './SceneDirectionPanel'
import { SettingReferenceAuthorityPanel } from './SettingReferenceAuthorityPanel'

type Props = {
  projectId: string
  sceneId?: string | null
  versionId?: string | null
  activeShotNumber: number
  onSaved: () => void
}

/**
 * The creator decision interface for a scene.
 *
 * It composes — without merging — the three separate creator decisions:
 *
 *  1. Setting authority: register / approve / designate an exact environment
 *     reference for the exact setting entity. Opening it performs no mutation.
 *  2. Scene Direction: explicitly select the exact setting reference ID for
 *     this scene. Nothing is preselected and the approved source version is
 *     never modified — saving creates a versioned DRAFT successor.
 *  3. Coverage decisions: every obligation stays UNRESOLVED until the creator
 *     decides it. Nothing is inferred, defaulted, or auto-saved.
 *
 * Setting authority lives in its own panel because approval and canonical
 * designation are distinct creator actions from the Scene Direction
 * reference selection. This interface never marks a scene READY.
 */
export function CreatorDecisionWorkspace({ projectId, sceneId, versionId, activeShotNumber, onSaved }: Props) {
  return (
    <section
      aria-label="Creator decision workspace"
      data-testid="creator-decision-workspace"
      className="mt-5 space-y-4 rounded-lg border border-amber-200/25 p-4"
    >
      <header className="space-y-1">
        <p className="text-[11px] font-medium uppercase tracking-[0.15em] text-amber-100/80">Creator decision capture</p>
        <h2 className="text-sm font-medium text-zinc-100">Three separate decisions — nothing is decided for you</h2>
        <ol className="list-decimal space-y-1 pl-5 text-xs leading-relaxed text-zinc-400">
          <li><strong className="text-zinc-200">Setting authority</strong> — register, approve, and designate canonical an exact environment reference for the exact setting entity. Opening this makes no change.</li>
          <li><strong className="text-zinc-200">Scene Direction</strong> — explicitly select the exact reference ID for this scene. No reference is preselected, and saving creates a versioned draft successor.</li>
          <li><strong className="text-zinc-200">Coverage decisions</strong> — resolve every coverage obligation yourself, then review and commit. Unresolved stays unresolved until you decide.</li>
        </ol>
      </header>

      <div>
        <p className="mb-1 text-[11px] font-medium uppercase tracking-[0.15em] text-amber-100/70">Decision 1 · Setting authority</p>
        <SettingReferenceAuthorityPanel projectId={projectId} />
      </div>

      <div className="space-y-2">
        <p className="text-[11px] font-medium uppercase tracking-[0.15em] text-amber-100/70">Decisions 2 &amp; 3 · Scene Direction and coverage</p>
        {sceneId && versionId ? (
          <SceneDirectionPanel
            key={`${projectId}/${sceneId}/${versionId}`}
            projectId={projectId}
            sceneId={sceneId}
            versionId={versionId}
            activeShotNumber={activeShotNumber}
            onSaved={onSaved}
          />
        ) : (
          <p role="status" className="text-xs text-zinc-400">Select a scene with a storyboard version to capture Scene Direction and coverage decisions.</p>
        )}
      </div>
    </section>
  )
}

export default CreatorDecisionWorkspace
