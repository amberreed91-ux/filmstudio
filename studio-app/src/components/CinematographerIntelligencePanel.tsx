import { Aperture, Camera, ClipboardList, Eye, Loader2, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  buildCameraGrammarRenderContext,
  createCameraGrammarAssessment,
  createCameraGrammarObservation,
  createCameraGrammarPlan,
  type CameraGrammarAssessment,
  type CameraGrammarPlan,
  type CameraGrammarRenderContext,
} from '../lib/studioApi'
import CinematographerInspectionDrawer from './CinematographerInspectionDrawer'

type CinematographerIntelligencePanelProps = {
  projectId: string
  sceneId?: string
  shotId?: string
  assetId?: string
  renderJobId?: string
  sceneContext?: Record<string, unknown>
}

function formatLabel(value: string | null | undefined) {
  return (value || 'unspecified').replace(/_/g, ' ')
}

function SlotPreview({ context }: { context: CameraGrammarRenderContext | null }) {
  if (!context) return null
  return (
    <div className="grid gap-2 md:grid-cols-2">
      <div className="rounded-md border border-zinc-700/60 bg-zinc-950/50 p-3">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-cyan-300">Camera Slot</div>
        <p className="mt-1 text-sm text-zinc-300">{context.camera_direction || 'No camera slot suggestion yet.'}</p>
      </div>
      <div className="rounded-md border border-zinc-700/60 bg-zinc-950/50 p-3">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-300">Lighting Slot</div>
        <p className="mt-1 text-sm text-zinc-300">{context.lighting_direction || 'No lighting slot suggestion yet.'}</p>
      </div>
    </div>
  )
}

function PlanView({ plan }: { plan: CameraGrammarPlan }) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-zinc-700/60 bg-zinc-900/50 p-3">
        <p className="text-sm text-zinc-300">{plan.creator_note}</p>
        <div className="mt-2 text-xs text-zinc-500">{formatLabel(plan.confidence_label)} evidence</div>
      </div>
      <div className="grid gap-2 md:grid-cols-5">
        {[
          ['Composition', plan.composition_intent],
          ['Lens', plan.lens_intent],
          ['Movement', plan.movement_intent],
          ['Lighting', plan.lighting_intent],
          ['Framing', plan.framing_intent],
        ].map(([label, value]) => (
          <div key={label} className="rounded-md border border-zinc-700/60 bg-zinc-950/40 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{label}</div>
            <div className="mt-1 text-sm text-zinc-200">{formatLabel(value)}</div>
          </div>
        ))}
      </div>
      <div className="grid gap-2 md:grid-cols-3">
        <p className="rounded-md border border-zinc-700/50 bg-zinc-900/40 p-3 text-xs text-zinc-400">{plan.depth_strategy}</p>
        <p className="rounded-md border border-zinc-700/50 bg-zinc-900/40 p-3 text-xs text-zinc-400">{plan.blocking_strategy}</p>
        <p className="rounded-md border border-zinc-700/50 bg-zinc-900/40 p-3 text-xs text-zinc-400">{plan.screen_direction_strategy}</p>
      </div>
      <div className="rounded-md border border-zinc-700/50 bg-zinc-900/40 p-3">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Evidence</div>
        <div className="mt-2 space-y-1">
          {plan.evidence_refs.slice(0, 4).map((ref) => (
            <div key={`${ref.ref_type}-${ref.ref_id}`} className="text-xs text-zinc-400">
              <span className="text-zinc-300">{ref.label || ref.ref_type}</span>
              {ref.summary ? `: ${ref.summary}` : null}
            </div>
          ))}
          {!plan.evidence_refs.length ? <p className="text-xs text-zinc-500">Evidence is still thin for this plan.</p> : null}
        </div>
      </div>
    </div>
  )
}

function AssessmentView({ assessment }: { assessment: CameraGrammarAssessment | null }) {
  if (!assessment) return null
  return (
    <div className="rounded-md border border-zinc-700/60 bg-zinc-900/50 p-3">
      <div className="flex items-center gap-2">
        <Eye size={14} className="text-cyan-300" />
        <div className="text-sm font-semibold text-zinc-100">Observed Output</div>
      </div>
      <p className="mt-2 text-sm text-zinc-300">{assessment.alignment_summary}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {assessment.matched_axes.map((axis) => (
          <span key={`matched-${axis}`} className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-300">
            Held {formatLabel(axis)}
          </span>
        ))}
        {assessment.drift_axes.map((axis) => (
          <span key={`drift-${axis}`} className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs text-amber-300">
            Review {formatLabel(axis)}
          </span>
        ))}
      </div>
      {assessment.revision_suggestions.length ? (
        <div className="mt-3 space-y-2">
          {assessment.revision_suggestions.slice(0, 2).map((suggestion) => (
            <p key={suggestion.suggestion_id} className="rounded border border-zinc-700/50 bg-zinc-950/50 p-2 text-xs text-zinc-400">
              {suggestion.summary}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export default function CinematographerIntelligencePanel({
  projectId,
  sceneId = 'scene_001',
  shotId,
  assetId,
  renderJobId,
  sceneContext = {},
}: CinematographerIntelligencePanelProps) {
  const [plan, setPlan] = useState<CameraGrammarPlan | null>(null)
  const [renderContext, setRenderContext] = useState<CameraGrammarRenderContext | null>(null)
  const [assessment, setAssessment] = useState<CameraGrammarAssessment | null>(null)
  const [inspectionOpen, setInspectionOpen] = useState(false)

  const planMutation = useMutation({
    mutationFn: () => createCameraGrammarPlan(projectId, {
      scene_id: sceneId,
      shot_id: shotId,
      render_job_id: renderJobId,
      plan_scope: shotId ? 'shot' : 'scene',
      scene_context: sceneContext,
      force_refresh: true,
    }),
    onSuccess: (response) => {
      setPlan(response.plan)
      setRenderContext(null)
      setAssessment(null)
    },
  })

  const renderContextMutation = useMutation({
    mutationFn: (activePlan: CameraGrammarPlan) => buildCameraGrammarRenderContext(projectId, {
      plan_id: activePlan.plan_id,
      scene_id: sceneId,
      shot_id: shotId,
      provider: 'runway',
    }),
    onSuccess: setRenderContext,
  })

  const assessmentMutation = useMutation({
    mutationFn: async (activePlan: CameraGrammarPlan) => {
      const observation = await createCameraGrammarObservation(projectId, {
        plan_id: activePlan.plan_id,
        asset_id: assetId,
        render_job_id: renderJobId,
        scene_id: sceneId,
        shot_id: shotId,
      })
      return createCameraGrammarAssessment(projectId, {
        plan_id: activePlan.plan_id,
        observation_id: observation.observation.observation_id,
        create_crew_reasoning: true,
      })
    },
    onSuccess: (response) => setAssessment(response.assessment),
  })

  const busy = planMutation.isPending || renderContextMutation.isPending || assessmentMutation.isPending
  const error = planMutation.error || renderContextMutation.error || assessmentMutation.error

  return (
    <div className="space-y-4 rounded-lg border border-zinc-700/70 bg-zinc-800/30 p-4" data-testid="cinematographer-intelligence-panel">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Aperture size={16} className="text-cyan-300" />
            <h3 className="text-sm font-semibold text-zinc-100">Cinematographer</h3>
          </div>
          <p className="mt-1 text-xs text-zinc-500">Composition, lens, movement, lighting, framing, and visual storytelling.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => planMutation.mutate()}
            disabled={busy || !sceneId.trim()}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-cyan-300 px-3 text-sm font-medium text-zinc-950 transition-colors hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {planMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <ClipboardList size={15} />}
            Plan
          </button>
          <button
            type="button"
            onClick={() => plan && renderContextMutation.mutate(plan)}
            disabled={busy || !plan}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-zinc-600 px-3 text-sm text-zinc-200 transition-colors hover:border-cyan-300 hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <SlidersHorizontal size={15} />
            Slots
          </button>
          <button
            type="button"
            onClick={() => plan && assessmentMutation.mutate(plan)}
            disabled={busy || !plan || (!assetId && !renderJobId)}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-zinc-600 px-3 text-sm text-zinc-200 transition-colors hover:border-amber-300 hover:text-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Camera size={15} />
            Assess
          </button>
          <button
            type="button"
            onClick={() => setInspectionOpen(true)}
            disabled={!plan}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-zinc-600 px-3 text-sm text-zinc-200 transition-colors hover:border-zinc-400 hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Eye size={15} />
            Inspect
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error instanceof Error ? error.message : 'Cinematographer intelligence failed'}
        </div>
      ) : null}

      {plan ? <PlanView plan={plan} /> : (
        <div className="rounded-md border border-dashed border-zinc-700 p-5 text-sm text-zinc-500">
          Generate a camera plan to inspect the shot's visual grammar before render.
        </div>
      )}
      <SlotPreview context={renderContext} />
      <AssessmentView assessment={assessment} />
      <CinematographerInspectionDrawer
        open={inspectionOpen}
        plan={plan}
        assessment={assessment}
        onClose={() => setInspectionOpen(false)}
      />
    </div>
  )
}
