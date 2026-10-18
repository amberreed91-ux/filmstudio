import { useState } from 'react'
import {
  stageScene,
  applySceneStaging,
  type StageSceneShotProposal,
} from '../lib/studioApi'
import CameraFrustumGizmo, { type CameraFrustumParams } from './CameraFrustumGizmo'

const STAGING_FIELDS = [
  'action', 'camera_angle', 'lens_language', 'blocking',
  'composition', 'lighting', 'color_palette', 'props',
] as const

type Props = {
  projectId: string
  sceneId: string
  // Called after staging is applied, so the parent can refresh if it wants.
  onApplied?: (applied: number) => void
}

/**
 * Scene Staging — a previs assist that turns each shot's beat into the
 * camera / lighting / action fields the render prompt reads (visual_plan),
 * which the storyboard generator leaves empty. Self-contained: it owns its
 * button, review state and modal, so it can be dropped next to the other
 * previs assists without touching the surrounding page.
 *
 * Review-before-apply: nothing is written until the director clicks Apply.
 * A blank field is one the beat did not specify, shown as "—" and left for the
 * director to fill, never invented.
 */
export default function StageScenePanel({ projectId, sceneId, onApplied }: Props) {
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [proposals, setProposals] = useState<StageSceneShotProposal[] | null>(null)
  // Live camera frustum params steered by the gizmo. Local preview state —
  // staging apply below never sends these; the render step owns its inputs.
  const [frustum, setFrustum] = useState<CameraFrustumParams>({ fov: 48, tilt: 8 })

  const disabled = !sceneId || loading || applying

  const runStaging = async () => {
    setError(null)
    setNotice(null)
    setLoading(true)
    try {
      const result = await stageScene(projectId, sceneId)
      if (result.all_blank) {
        setError(
          'The model returned nothing usable for any shot. Try again, or check ' +
          'that the scene has a storyboard with beat text.',
        )
        setProposals(null)
      } else {
        setProposals(result.proposals)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Staging failed')
      setProposals(null)
    } finally {
      setLoading(false)
    }
  }

  const applyStaging = async () => {
    if (!proposals) return
    setApplying(true)
    setError(null)
    try {
      const result = await applySceneStaging(
        projectId,
        sceneId,
        proposals.map((p) => ({ shot_id: p.shot_id, staging: p.staging })),
      )
      setNotice(`Applied staging to ${result.applied} shot(s).`)
      setProposals(null)
      onApplied?.(result.applied)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Apply failed')
    } finally {
      setApplying(false)
    }
  }

  const fieldValue = (staging: Record<string, unknown>, key: string): string => {
    const v = staging[key]
    if (Array.isArray(v)) return v.join(', ')
    return String(v ?? '').trim()
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-zinc-100">Scene Staging</div>
          <div className="text-xs text-zinc-400">
            Fills each shot's camera, lighting and action so the render describes
            your shot, not the style bible. Review before it's saved.
          </div>
        </div>
        <button
          type="button"
          onClick={runStaging}
          disabled={disabled}
          className="shrink-0 rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Staging…' : 'Stage Scene (AI)'}
        </button>
      </div>

      <details className="mt-3">
        <summary className="cursor-pointer text-xs text-zinc-400">Camera frustum gizmo · fov {frustum.fov}° · tilt {frustum.tilt}°</summary>
        <div className="mt-2">
          <CameraFrustumGizmo initial={frustum} onChange={setFrustum} />
        </div>
      </details>

      {error && (
        <div className="mt-2 rounded-md border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}
      {notice && (
        <div className="mt-2 rounded-md border border-emerald-900/60 bg-emerald-950/40 px-3 py-2 text-xs text-emerald-300">
          {notice}
        </div>
      )}

      {proposals && (
        <div className="mt-3 space-y-3">
          <div className="text-xs text-zinc-400">
            Reviewing {proposals.length} shot(s). A dash means the beat did not
            specify that field — yours to fill later, not guessed.
          </div>
          <div className="max-h-96 space-y-3 overflow-y-auto pr-1">
            {proposals.map((p) => (
              <div key={p.shot_id} className="rounded-md border border-zinc-800 bg-zinc-950/60 p-3">
                <div className="mb-2 flex items-baseline justify-between gap-2">
                  <div className="text-xs font-medium text-zinc-200">
                    Shot {p.shot_number} · {p.shot_id}
                  </div>
                  {p.left_blank.length > 0 && (
                    <div className="text-[10px] text-zinc-500">
                      {p.left_blank.length} blank
                    </div>
                  )}
                </div>
                <div className="grid gap-1">
                  {STAGING_FIELDS.map((field) => {
                    const value = fieldValue(p.staging, field)
                    return (
                      <div key={field} className="grid grid-cols-[110px_1fr] gap-2 text-[11px]">
                        <div className="text-zinc-500">{field}</div>
                        <div className={value ? 'text-zinc-200' : 'text-zinc-600'}>
                          {value || '—'}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={applyStaging}
              disabled={applying}
              className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              {applying ? 'Applying…' : 'Apply to shots'}
            </button>
            <button
              type="button"
              onClick={() => setProposals(null)}
              disabled={applying}
              className="rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
            >
              Discard
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
