import { Eye, Loader2, Palette, SlidersHorizontal, Sparkles, SwatchBook } from 'lucide-react'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  buildColorRenderContext,
  createColorGradeObservation,
  createColorLookBible,
  createColorMatchAssessment,
  createColoristLookPlan,
  createColorFinalVerification,
  type ColorFinalVerification,
  type ColorLookBible,
  type ColorMatchAssessment,
  type ColorRenderContext,
  type ColoristLookPlan,
} from '../lib/studioApi'
import ColoristInspectionDrawer from './ColoristInspectionDrawer'

type ColoristIntelligencePanelProps = {
  projectId: string
  sceneId?: string
  shotId?: string
  assetId?: string
  renderJobId?: string
  sceneContext?: Record<string, unknown>
}

function label(value: string | null | undefined) {
  return (value || 'pending').replace(/_/g, ' ')
}

function PaletteChips({ colors }: { colors: string[] }) {
  if (!colors.length) return <p className="text-xs text-zinc-500">Palette evidence is still thin.</p>
  return (
    <div className="flex flex-wrap gap-2">
      {colors.slice(0, 8).map((color) => (
        <span key={color} className="rounded border border-zinc-700 bg-zinc-950/50 px-2 py-1 text-xs text-zinc-300">
          {color}
        </span>
      ))}
    </div>
  )
}

function PlanView({ plan }: { plan: ColoristLookPlan }) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-zinc-700/60 bg-zinc-950/50 p-3">
        <p className="text-sm text-zinc-300">{plan.creator_note}</p>
        <div className="mt-2 text-xs text-zinc-500">{label(plan.confidence_label)} evidence</div>
      </div>
      <PaletteChips colors={plan.intended_palette} />
      <div className="grid gap-2 md:grid-cols-4">
        {[
          ['Contrast', plan.contrast_intent],
          ['Temperature', plan.temperature_intent],
          ['Saturation', plan.saturation_intent],
          ['Skin Tone', plan.skin_tone_intent],
        ].map(([name, value]) => (
          <div key={name} className="rounded-md border border-zinc-700/60 bg-zinc-900/45 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{name}</div>
            <p className="mt-1 text-xs text-zinc-300">{value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function AssessmentView({ assessment }: { assessment: ColorMatchAssessment | null }) {
  if (!assessment) return null
  return (
    <div className="rounded-md border border-zinc-700/60 bg-zinc-950/50 p-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
        <Eye size={14} className="text-emerald-300" />
        Color Match
      </div>
      <p className="mt-2 text-sm text-zinc-300">{assessment.match_summary}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {assessment.held_axes.map((axis) => (
          <span key={`held-${axis}`} className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-300">
            Held {label(axis)}
          </span>
        ))}
        {assessment.drift_axes.map((axis) => (
          <span key={`drift-${axis}`} className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs text-amber-300">
            Review {label(axis)}
          </span>
        ))}
      </div>
      {assessment.revision_suggestions.length ? (
        <p className="mt-3 rounded border border-zinc-700/50 bg-zinc-900/60 p-2 text-xs text-zinc-400">
          {assessment.revision_suggestions[0].summary}
        </p>
      ) : null}
    </div>
  )
}

export default function ColoristIntelligencePanel({
  projectId,
  sceneId = 'scene_001',
  shotId,
  assetId,
  renderJobId,
  sceneContext = {},
}: ColoristIntelligencePanelProps) {
  const [lookBible, setLookBible] = useState<ColorLookBible | null>(null)
  const [plan, setPlan] = useState<ColoristLookPlan | null>(null)
  const [renderContext, setRenderContext] = useState<ColorRenderContext | null>(null)
  const [assessment, setAssessment] = useState<ColorMatchAssessment | null>(null)
  const [verification, setVerification] = useState<ColorFinalVerification | null>(null)
  const [inspectionOpen, setInspectionOpen] = useState(false)

  const lookBibleMutation = useMutation({
    mutationFn: () => createColorLookBible(projectId, {
      scope: 'project',
      project_context: sceneContext,
      force_refresh: true,
    }),
    onSuccess: (response) => {
      setLookBible(response.look_bible)
      setPlan(null)
      setRenderContext(null)
      setAssessment(null)
      setVerification(null)
    },
  })

  const planMutation = useMutation({
    mutationFn: () => createColoristLookPlan(projectId, {
      look_bible_id: lookBible?.look_bible_id,
      scene_id: sceneId,
      shot_id: shotId,
      render_job_id: renderJobId,
      scope: shotId ? 'shot' : 'scene',
      scene_context: sceneContext,
      force_refresh: true,
    }),
    onSuccess: (response) => {
      setPlan(response.plan)
      setRenderContext(null)
      setAssessment(null)
      setVerification(null)
    },
  })

  const renderContextMutation = useMutation({
    mutationFn: (activePlan: ColoristLookPlan) => buildColorRenderContext(projectId, {
      plan_id: activePlan.plan_id,
      scene_id: sceneId,
      shot_id: shotId,
      provider: 'runway',
    }),
    onSuccess: setRenderContext,
  })

  const assessmentMutation = useMutation({
    mutationFn: async (activePlan: ColoristLookPlan) => {
      const observation = await createColorGradeObservation(projectId, {
        plan_id: activePlan.plan_id,
        look_bible_id: activePlan.look_bible_id,
        asset_id: assetId,
        render_job_id: renderJobId,
        scene_id: sceneId,
        shot_id: shotId,
      })
      return createColorMatchAssessment(projectId, {
        plan_id: activePlan.plan_id,
        observation_id: observation.observation.observation_id,
        create_crew_reasoning: true,
      })
    },
    onSuccess: (response) => setAssessment(response.assessment),
  })

  const finalMutation = useMutation({
    mutationFn: () => createColorFinalVerification(projectId, {
      look_bible_id: lookBible?.look_bible_id,
      assessment_ids: assessment ? [assessment.assessment_id] : [],
    }),
    onSuccess: (response) => setVerification(response.verification),
  })

  const busy = lookBibleMutation.isPending || planMutation.isPending || renderContextMutation.isPending || assessmentMutation.isPending || finalMutation.isPending
  const error = lookBibleMutation.error || planMutation.error || renderContextMutation.error || assessmentMutation.error || finalMutation.error

  return (
    <section className="space-y-4 rounded-lg border border-zinc-700/70 bg-zinc-900/60 p-4 text-zinc-100" data-testid="colorist-intelligence-panel">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Palette size={16} className="text-rose-300" />
            <h3 className="text-sm font-semibold">Colorist</h3>
          </div>
          <p className="mt-1 text-xs text-zinc-500">Look development, palette continuity, scene matching, grade consistency, and emotional color.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => lookBibleMutation.mutate()} disabled={busy} className="inline-flex h-8 items-center gap-2 rounded-md border border-rose-400/40 bg-rose-500/10 px-3 text-xs font-semibold text-rose-100 hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-50">
            {lookBibleMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <SwatchBook size={14} />}
            Look
          </button>
          <button type="button" onClick={() => planMutation.mutate()} disabled={busy} className="inline-flex h-8 items-center gap-2 rounded-md border border-zinc-600 bg-zinc-800/70 px-3 text-xs font-semibold text-zinc-200 hover:border-rose-400/60 disabled:cursor-not-allowed disabled:opacity-50">
            <Sparkles size={14} />
            Plan
          </button>
          <button type="button" onClick={() => plan && renderContextMutation.mutate(plan)} disabled={busy || !plan} className="inline-flex h-8 items-center gap-2 rounded-md border border-zinc-600 bg-zinc-800/70 px-3 text-xs font-semibold text-zinc-200 hover:border-cyan-400/60 disabled:cursor-not-allowed disabled:opacity-50">
            <SlidersHorizontal size={14} />
            Slots
          </button>
          <button type="button" onClick={() => plan && assessmentMutation.mutate(plan)} disabled={busy || !plan || (!assetId && !renderJobId)} className="inline-flex h-8 items-center gap-2 rounded-md border border-zinc-600 bg-zinc-800/70 px-3 text-xs font-semibold text-zinc-200 hover:border-emerald-400/60 disabled:cursor-not-allowed disabled:opacity-50">
            Assess
          </button>
          <button type="button" onClick={() => finalMutation.mutate()} disabled={busy} className="inline-flex h-8 items-center gap-2 rounded-md border border-zinc-600 bg-zinc-800/70 px-3 text-xs font-semibold text-zinc-200 hover:border-amber-400/60 disabled:cursor-not-allowed disabled:opacity-50">
            Final
          </button>
          <button type="button" onClick={() => setInspectionOpen(true)} className="inline-flex h-8 items-center gap-2 rounded-md border border-zinc-600 bg-zinc-800/70 px-3 text-xs font-semibold text-zinc-200 hover:border-zinc-400">
            Inspect
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error instanceof Error ? error.message : 'Colorist request failed'}
        </div>
      ) : null}

      {lookBible ? (
        <div className="rounded-md border border-zinc-700/60 bg-zinc-950/45 p-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-rose-300">Look Bible</div>
          <p className="mt-1 text-sm text-zinc-300">{lookBible.creator_note}</p>
          <div className="mt-2">
            <PaletteChips colors={lookBible.palette_families.flatMap((family) => family.colors)} />
          </div>
        </div>
      ) : null}

      {plan ? <PlanView plan={plan} /> : (
        <div className="rounded-md border border-dashed border-zinc-700 p-5 text-center text-sm text-zinc-500">
          Develop a look or build a scene color plan to inspect grade intent.
        </div>
      )}

      {renderContext ? (
        <div className="rounded-md border border-zinc-700/60 bg-zinc-950/50 p-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-cyan-300">Color Slot</div>
          <p className="mt-1 text-sm text-zinc-300">{renderContext.color_direction}</p>
        </div>
      ) : null}

      <AssessmentView assessment={assessment} />

      {verification ? (
        <div className="rounded-md border border-zinc-700/60 bg-zinc-950/50 p-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-300">Final Verification</div>
          <p className="mt-1 text-sm text-zinc-300">{verification.coverage_summary}</p>
          <p className="mt-1 text-xs text-zinc-500">{verification.creator_note}</p>
        </div>
      ) : null}

      <ColoristInspectionDrawer
        open={inspectionOpen}
        onClose={() => setInspectionOpen(false)}
        lookBible={lookBible}
        plan={plan}
        renderContext={renderContext}
        assessment={assessment}
      />
    </section>
  )
}
