import { Boxes, Eye, Layers3, Loader2, PaintBucket, Search } from 'lucide-react'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  buildProductionDesignRenderContext,
  createProductionDesignAssessment,
  createProductionDesignObservation,
  createProductionDesignPlan,
  type ProductionDesignAssessment,
  type ProductionDesignPlan,
  type ProductionDesignRenderContext,
} from '../lib/studioApi'
import ProductionDesignInspectionDrawer from './ProductionDesignInspectionDrawer'

type ProductionDesignIntelligencePanelProps = {
  projectId: string
  sceneId?: string
  shotId?: string
  assetId?: string
  renderJobId?: string
  sceneContext?: Record<string, unknown>
}

function label(value: string | null | undefined) {
  return (value || 'unspecified').replace(/_/g, ' ')
}

function Pill({ children }: { children: string }) {
  return <span className="rounded border border-zinc-700 bg-zinc-950/50 px-2 py-1 text-xs text-zinc-300">{children}</span>
}

function RenderContextView({ context }: { context: ProductionDesignRenderContext | null }) {
  if (!context) return null
  return (
    <div className="grid gap-2 md:grid-cols-2">
      <div className="rounded-md border border-zinc-700/60 bg-zinc-950/50 p-3">
        <div className="text-[11px] font-semibold uppercase text-emerald-300">Environment</div>
        <p className="mt-1 text-sm text-zinc-300">{context.environment_direction || 'No environment direction yet.'}</p>
      </div>
      <div className="rounded-md border border-zinc-700/60 bg-zinc-950/50 p-3">
        <div className="text-[11px] font-semibold uppercase text-rose-300">Negative Design</div>
        <p className="mt-1 text-sm text-zinc-300">{context.negative_design_direction || 'No negative design constraints yet.'}</p>
      </div>
    </div>
  )
}

function PlanView({ plan }: { plan: ProductionDesignPlan }) {
  const environment = plan.environment_profile
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-zinc-700/60 bg-zinc-900/50 p-3">
        <p className="text-sm text-zinc-300">{plan.creator_note}</p>
        <div className="mt-2 text-xs text-zinc-500">{label(plan.readiness_label)} design read</div>
      </div>

      <div className="grid gap-2 md:grid-cols-4">
        <div className="rounded-md border border-zinc-700/60 bg-zinc-950/40 p-3">
          <div className="text-[11px] font-semibold uppercase text-zinc-500">Environment</div>
          <div className="mt-1 text-sm text-zinc-200">{environment?.location_name || 'unspecified'}</div>
        </div>
        <div className="rounded-md border border-zinc-700/60 bg-zinc-950/40 p-3">
          <div className="text-[11px] font-semibold uppercase text-zinc-500">Props</div>
          <div className="mt-1 text-sm text-zinc-200">{plan.prop_records.length}</div>
        </div>
        <div className="rounded-md border border-zinc-700/60 bg-zinc-950/40 p-3">
          <div className="text-[11px] font-semibold uppercase text-zinc-500">Costumes</div>
          <div className="mt-1 text-sm text-zinc-200">{plan.costume_records.length}</div>
        </div>
        <div className="rounded-md border border-zinc-700/60 bg-zinc-950/40 p-3">
          <div className="text-[11px] font-semibold uppercase text-zinc-500">Symbolic Refs</div>
          <div className="mt-1 text-sm text-zinc-200">{plan.symbolic_refs.length}</div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {plan.design_axes.slice(0, 8).map((axis) => (
          <Pill key={axis.axis}>{`${label(axis.axis)}: ${axis.intent}`}</Pill>
        ))}
      </div>

      {plan.prop_records.length ? (
        <div className="rounded-md border border-zinc-700/50 bg-zinc-900/40 p-3">
          <div className="text-[11px] font-semibold uppercase text-zinc-500">Tracked Props</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {plan.prop_records.slice(0, 8).map((prop) => <Pill key={prop.prop_record_id}>{prop.prop_name}</Pill>)}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function AssessmentView({ assessment }: { assessment: ProductionDesignAssessment | null }) {
  if (!assessment) return null
  return (
    <div className="rounded-md border border-zinc-700/60 bg-zinc-900/50 p-3">
      <div className="flex items-center gap-2">
        <Eye size={14} className="text-emerald-300" />
        <div className="text-sm font-semibold text-zinc-100">Observed Design</div>
      </div>
      <p className="mt-2 text-sm text-zinc-300">{assessment.alignment_summary}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {assessment.matched_axes.slice(0, 6).map((axis) => <Pill key={`matched-${axis}`}>{`Held ${label(axis)}`}</Pill>)}
        {assessment.drift_axes.slice(0, 6).map((axis) => <Pill key={`drift-${axis}`}>{`Review ${label(axis)}`}</Pill>)}
      </div>
    </div>
  )
}

export default function ProductionDesignIntelligencePanel({
  projectId,
  sceneId = 'scene_001',
  shotId,
  assetId,
  renderJobId,
  sceneContext = {},
}: ProductionDesignIntelligencePanelProps) {
  const [plan, setPlan] = useState<ProductionDesignPlan | null>(null)
  const [renderContext, setRenderContext] = useState<ProductionDesignRenderContext | null>(null)
  const [assessment, setAssessment] = useState<ProductionDesignAssessment | null>(null)
  const [inspectionOpen, setInspectionOpen] = useState(false)

  const planMutation = useMutation({
    mutationFn: () => createProductionDesignPlan(projectId, {
      scene_id: sceneId,
      shot_id: shotId,
      asset_id: assetId,
      render_job_id: renderJobId,
      scope: shotId ? 'shot' : 'scene',
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
    mutationFn: (activePlan: ProductionDesignPlan) => buildProductionDesignRenderContext(projectId, {
      plan_id: activePlan.plan_id,
      scene_id: sceneId,
      shot_id: shotId,
      provider: 'runway',
    }),
    onSuccess: setRenderContext,
  })

  const assessmentMutation = useMutation({
    mutationFn: async (activePlan: ProductionDesignPlan) => {
      const observation = await createProductionDesignObservation(projectId, {
        plan_id: activePlan.plan_id,
        asset_id: assetId,
        render_job_id: renderJobId,
        scene_id: sceneId,
        shot_id: shotId,
      })
      return createProductionDesignAssessment(projectId, {
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
    <div className="space-y-4 rounded-lg border border-zinc-700/70 bg-zinc-800/30 p-4" data-testid="production-design-intelligence-panel">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Layers3 size={16} className="text-emerald-300" />
            <h3 className="text-sm font-semibold text-zinc-100">Production Designer</h3>
          </div>
          <p className="mt-1 text-xs text-zinc-500">Environments, props, costumes, set dressing, symbolism, and visual continuity.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => planMutation.mutate()}
            disabled={busy || !sceneId.trim()}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-emerald-300 px-3 text-sm font-medium text-zinc-950 transition-colors hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {planMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Boxes size={15} />}
            Plan
          </button>
          <button
            type="button"
            onClick={() => plan && renderContextMutation.mutate(plan)}
            disabled={busy || !plan}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-zinc-600 px-3 text-sm text-zinc-200 transition-colors hover:border-emerald-300 hover:text-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <PaintBucket size={15} />
            Slots
          </button>
          <button
            type="button"
            onClick={() => plan && assessmentMutation.mutate(plan)}
            disabled={busy || !plan || (!assetId && !renderJobId)}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-zinc-600 px-3 text-sm text-zinc-200 transition-colors hover:border-amber-300 hover:text-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Eye size={15} />
            Assess
          </button>
          <button
            type="button"
            onClick={() => setInspectionOpen(true)}
            disabled={!plan}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-zinc-600 px-3 text-sm text-zinc-200 transition-colors hover:border-zinc-300 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Search size={15} />
            Inspect
          </button>
        </div>
      </div>

      {error ? <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">{error instanceof Error ? error.message : 'Production design request failed.'}</div> : null}
      {!plan ? <div className="rounded-md border border-zinc-700/60 bg-zinc-950/40 p-4 text-sm text-zinc-500">No production design plan yet.</div> : <PlanView plan={plan} />}
      <RenderContextView context={renderContext} />
      <AssessmentView assessment={assessment} />
      <ProductionDesignInspectionDrawer open={inspectionOpen} onClose={() => setInspectionOpen(false)} plan={plan} assessment={assessment} />
    </div>
  )
}
