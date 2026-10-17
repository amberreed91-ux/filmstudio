import { useState } from 'react'
import { AlertTriangle, Camera, CheckCircle2, Loader2, ShieldCheck } from 'lucide-react'
import {
  approveAiCamera,
  type StoryboardShot,
} from '../lib/studioApi'

type Props = {
  projectId: string
  sceneId: string
  shot: StoryboardShot
  approvedBy?: string
  /** Refreshed after a successful approval so the readiness panel re-runs. */
  onApproved: () => void
}

/**
 * Per-shot creator control for the pending AI camera suggestion.
 *
 * The backend's provenance rules hold template board framings out of
 * renderable camera until the creator explicitly approves them (P0-2). This
 * control exposes exactly that existing approval — one shot per decision:
 *
 * - shows the current AI-suggested framing verbatim and marks it AI_SUGGESTED;
 * - states what approving locks (framing only — never invented camera data)
 *   and that approval creates a new DRAFT board version requiring re-approval;
 * - the action is a deliberate creator click; nothing approves on load;
 * - the decision is bound to the board version on screen, so a stale request
 *   is refused by the backend rather than applied elsewhere.
 */
export default function AiCameraApproval({ projectId, sceneId, shot, approvedBy = 'creator', onApproved }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [approved, setApproved] = useState<Record<string, string> | null>(null)

  const structured = (shot.render_contract?.structured_parameters || {}) as Record<string, unknown>
  const creatorPlan = structured.camera_plan as Record<string, string> | undefined
  const alreadyApproved = Boolean(creatorPlan && Object.values(creatorPlan).some((v) => String(v || '').trim()))
  const framing = String(shot.visual_plan?.framing || '').trim()
  const versionId = shot.version_id

  const approve = async () => {
    if (!projectId || !sceneId || !shot.storyboard_shot_id || busy || alreadyApproved) return
    setBusy(true)
    setError('')
    try {
      const result = await approveAiCamera(projectId, sceneId, shot.storyboard_shot_id, {
        approvedBy,
        // Bind to the exact version the creator is looking at.
        expectedVersionId: versionId || null,
      })
      setApproved(result.approved_camera || {})
      onApproved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Camera approval failed')
    } finally {
      setBusy(false)
    }
  }

  if (alreadyApproved) {
    return (
      <div className="rounded-lg border border-emerald-400/25 bg-emerald-500/[0.06] p-3" data-testid={`ai-camera-approved-${shot.shot_number}`}>
        <div className="flex items-center gap-2">
          <CheckCircle2 size={15} className="shrink-0 text-emerald-300" />
          <p className="text-xs font-medium text-emerald-100">Camera decision approved</p>
        </div>
        <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-400">
          Creator-approved camera plan: {Object.entries(creatorPlan || {}).filter(([, v]) => String(v || '').trim()).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'locked'}
        </p>
      </div>
    )
  }

  if (approved) {
    return (
      <div className="rounded-lg border border-emerald-400/25 bg-emerald-500/[0.06] p-3" data-testid={`ai-camera-approved-${shot.shot_number}`}>
        <div className="flex items-center gap-2">
          <CheckCircle2 size={15} className="shrink-0 text-emerald-300" />
          <p className="text-xs font-medium text-emerald-100">Camera decision approved for this shot</p>
        </div>
        <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-400">
          Locked: {Object.entries(approved).map(([k, v]) => `${k}: ${v}`).join(' · ')}
        </p>
        <p className="mt-1 text-[11px] leading-relaxed text-zinc-500">
          A new draft storyboard version was created. Run continuity review and approve it to return this scene to the approved production chain.
        </p>
      </div>
    )
  }

  if (!framing) {
    return (
      <p className="rounded-lg border border-white/10 bg-white/[0.025] p-3 text-[11px] leading-relaxed text-zinc-500">
        No pending AI camera suggestion on this shot.
      </p>
    )
  }

  return (
    <div className="rounded-lg border border-amber-200/25 bg-amber-200/[0.04] p-3" data-testid={`ai-camera-approval-${shot.shot_number}`}>
      <div className="flex items-center gap-2">
        <Camera size={15} className="shrink-0 text-amber-200" />
        <p className="text-xs font-medium text-amber-100">Camera decision · AI suggestion</p>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-300">
        <span className="font-mono text-[10px] uppercase tracking-wide text-amber-200/80">AI_SUGGESTED</span> — {framing}
      </p>
      <ul className="mt-2 space-y-1 text-[11px] leading-relaxed text-zinc-500">
        <li>Approving locks this framing as the creator camera plan. No other camera values are invented.</li>
        <li className="flex items-start gap-1.5"><AlertTriangle size={12} className="mt-0.5 shrink-0 text-amber-200/70" />Approval creates a <span className="font-medium text-zinc-300">new draft storyboard version</span>; the approved version stays untouched. Continuity review + board approval are required before rendering.</li>
      </ul>
      {error && <p className="mt-2 text-[11px] leading-relaxed text-rose-300" role="alert">{error}</p>}
      <button
        type="button"
        onClick={() => void approve()}
        disabled={busy}
        data-testid={`approve-ai-camera-${shot.shot_number}`}
        className="mt-3 flex w-full items-center justify-center gap-2 rounded-md border border-amber-200/40 bg-amber-200/10 px-3 py-2 text-xs font-medium text-amber-100 hover:bg-amber-200/15 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
        Approve this camera decision
      </button>
    </div>
  )
}
