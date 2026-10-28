import { useEffect, useState } from 'react'
import { Sparkles, Check, Loader2, MapPin } from 'lucide-react'
import type { Scene } from '../lib/studioApi'
import { useVisualTraining, findModelForTarget } from '../hooks/useVisualTraining'
import VisualTrainingPanel from './VisualTrainingPanel'
import ReferenceLibraryPanel from './ReferenceLibraryPanel'
import { getReferenceLibrary } from '../lib/visualTrainingApi'

/**
 * Setting/environment identity training entry point, embedded in the Previs
 * scene workflow. "Train This Setting" turns approved environment references
 * into a reusable setting identity. The trained model stays associated with the
 * canonical scene (via configuration provenance) and never duplicates or
 * replaces scene data. If a setting identity already exists it is shown as a
 * production asset and never auto-recreated.
 */
export default function SceneSettingTraining({ projectId, scene, onIdentityTrained, refreshSignal = 0 }: { projectId: string; scene: Scene; onIdentityTrained?: () => void; refreshSignal?: number }) {
  const controller = useVisualTraining(projectId, 'scene')
  const [open, setOpen] = useState(false)
  const existing = findModelForTarget(controller.models, scene.scene_id)
  const settingName = scene.location?.trim() || scene.heading?.trim() || scene.scene_name || 'This setting'
  const [hasCanonical, setHasCanonical] = useState<boolean | null>(null)

  // The listing endpoint syncs creator approvals (approved previs frames)
  // before reading, so this GET both displays the canonical anchor and keeps
  // the hint honest after a previs approval lands. Read-only.
  useEffect(() => {
    let cancelled = false
    getReferenceLibrary(projectId, 'setting', scene.scene_id)
      .then((library) => {
        if (!cancelled) setHasCanonical(Boolean(library?.canonical))
      })
      .catch(() => {
        if (!cancelled) setHasCanonical(null)
      })
    return () => { cancelled = true }
  }, [projectId, scene.scene_id, refreshSignal])
  const canonicalHint = hasCanonical === false

  const secondaryButton =
    'inline-flex items-center justify-center gap-2 rounded-md border border-white/20 px-3 py-2.5 text-xs font-medium text-zinc-200 hover:border-white/35 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 disabled:cursor-not-allowed disabled:opacity-40'

  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-3" data-testid="scene-setting-training">
      <div className="flex items-start gap-2">
        <MapPin size={15} className="mt-0.5 shrink-0 text-zinc-400" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-zinc-200">Setting identity</p>
          <p className="mt-0.5 text-xs leading-relaxed text-zinc-500">{settingName}</p>
        </div>
      </div>

      {existing ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-md border border-emerald-400/25 bg-emerald-500/[0.06] px-3 py-2.5">
          <div className="min-w-0">
            <p className="truncate font-mono text-xs text-zinc-100">{existing.trigger_word}</p>
            <p className="mt-0.5 text-xs text-zinc-400">{existing.provider} · {existing.provider_model}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded border border-emerald-400/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-200"><Check size={11} />Ready</span>
            <button type="button" onClick={() => setOpen(true)} className={secondaryButton}><Sparkles size={13} />View / retrain</button>
          </div>
        </div>
      ) : (
        <button type="button" onClick={() => setOpen(true)} className={`mt-3 w-full ${secondaryButton}`} data-testid="train-this-setting">
          {controller.modelsLoading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          Train This Setting
        </button>
      )}

      <ReferenceLibraryPanel projectId={projectId} targetType="scene" targetId={scene.scene_id} />

      {canonicalHint && (
        <p className="mt-2 rounded-md border border-amber-200/25 bg-amber-200/[0.05] px-3 py-2 text-[11px] leading-relaxed text-amber-100" data-testid="canonical-setting-hint">
          No canonical setting reference yet. Approving a completed previs/storyboard frame in the Previs bay is the supported way to establish it — the next reference-library sync registers that approved frame as the canonical environment anchor for this scene. There is no manual canonical override.
        </p>
      )}

      {open && (
        <VisualTrainingPanel
          controller={controller}
          canonicalTargetId={scene.scene_id}
          targetName={settingName}
          targetSubtitle={scene.heading || undefined}
          previewImageUrl={scene.storyboard_image || null}
          approvalLabel="Environment references"
          onIdentityReady={onIdentityTrained}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  )
}
