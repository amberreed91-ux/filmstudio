import { Headphones, Loader2, Mic2, Music2, Radio, SlidersHorizontal, Volume2 } from 'lucide-react'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  buildPerformanceAudioExecutionRequest,
  createPerformanceAudioAssessment,
  createPerformanceAudioPlan,
  type AudioExecutionRequest,
  type AudioIntelligenceAssessment,
  type PerformanceAudioPlan,
} from '../lib/performanceAudioApi'

type PerformanceAudioPanelProps = {
  projectId: string
  sceneId?: string
  shotId?: string
  assetId?: string
  renderJobId?: string
  sceneContext?: Record<string, unknown>
}

function label(value: string | undefined | null) {
  return (value || 'pending').replace(/_/g, ' ')
}

function readinessClass(value: string) {
  if (value === 'ready') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
  if (value === 'blocked') return 'border-amber-500/30 bg-amber-500/10 text-amber-300'
  return 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300'
}

function PlanSummary({ plan }: { plan: PerformanceAudioPlan }) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-zinc-700/60 bg-zinc-950/50 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide ${readinessClass(plan.readiness_label)}`}>
            {label(plan.readiness_label)}
          </span>
          {plan.stale ? <span className="rounded border border-zinc-600 px-2 py-1 text-[11px] text-zinc-400">Stale</span> : null}
        </div>
        <p className="mt-2 text-sm text-zinc-300">{plan.summary}</p>
        {plan.blockers.length ? (
          <div className="mt-2 space-y-1">
            {plan.blockers.map((blocker) => (
              <p key={blocker} className="text-xs text-amber-300">{blocker}</p>
            ))}
          </div>
        ) : null}
      </div>

      <div className="grid gap-2 md:grid-cols-3">
        {plan.voice_profiles.slice(0, 3).map((profile) => (
          <div key={profile.profile_id} className="rounded-md border border-zinc-700/60 bg-zinc-900/50 p-3">
            <div className="flex items-center gap-2">
              <Mic2 size={14} className="text-cyan-300" />
              <div className="text-sm font-semibold text-zinc-100">{profile.character_name}</div>
            </div>
            <p className="mt-1 text-xs text-zinc-400">{profile.cadence}</p>
            <p className="mt-1 text-xs text-zinc-500">
              {profile.provider_bindings.length ? `${profile.provider_bindings[0].provider} voice bound` : 'Voice casting not locked'}
            </p>
          </div>
        ))}
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-md border border-zinc-700/60 bg-zinc-900/40 p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-zinc-100">
            <Volume2 size={14} className="text-amber-300" />
            Dialogue Cues
          </div>
          <div className="space-y-2">
            {plan.dialogue_cues.slice(0, 4).map((cue) => (
              <div key={cue.cue_id} className="rounded border border-zinc-700/50 bg-zinc-950/45 p-2">
                <div className="text-xs font-semibold text-zinc-200">{cue.character_name}</div>
                <p className="mt-1 text-xs text-zinc-400">{cue.text}</p>
                <p className="mt-1 text-xs text-zinc-500">{cue.delivery}</p>
              </div>
            ))}
            {!plan.dialogue_cues.length ? <p className="text-xs text-zinc-500">No dialogue cues in this plan.</p> : null}
          </div>
        </div>

        <div className="rounded-md border border-zinc-700/60 bg-zinc-900/40 p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-zinc-100">
            <Music2 size={14} className="text-fuchsia-300" />
            Soundscape
          </div>
          <div className="space-y-2">
            {plan.soundscape_layers.slice(0, 5).map((layer) => (
              <div key={layer.layer_id} className="rounded border border-zinc-700/50 bg-zinc-950/45 p-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-zinc-200">{layer.label}</span>
                  <span className="text-[11px] uppercase tracking-wide text-zinc-500">{label(layer.track_type)}</span>
                </div>
                <p className="mt-1 text-xs text-zinc-400">{layer.intent}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function ExecutionPreview({ request }: { request: AudioExecutionRequest | null }) {
  if (!request) return null
  return (
    <div className="rounded-md border border-zinc-700/60 bg-zinc-950/50 p-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-cyan-300">Execution Request</div>
      <div className="mt-2 grid gap-2 md:grid-cols-3">
        <p className="text-xs text-zinc-400">Mood: {request.mood}</p>
        <p className="text-xs text-zinc-400">Dialogue clips: {request.dialogue_lines.length}</p>
        <p className="text-xs text-zinc-400">Silence: {request.silence_flag ? 'intentional' : 'not marked'}</p>
      </div>
    </div>
  )
}

function AssessmentPreview({ assessment }: { assessment: AudioIntelligenceAssessment | null }) {
  if (!assessment) return null
  return (
    <div className="rounded-md border border-zinc-700/60 bg-zinc-950/50 p-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
        <Radio size={14} className="text-emerald-300" />
        Audio Assessment
      </div>
      <p className="mt-2 text-sm text-zinc-300">{assessment.mix_read}</p>
      {assessment.missing_evidence.length ? (
        <div className="mt-2 space-y-1">
          {assessment.missing_evidence.map((item) => (
            <p key={item} className="text-xs text-zinc-500">{item}</p>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export default function PerformanceAudioPanel({
  projectId,
  sceneId = 'scene_001',
  shotId,
  assetId,
  renderJobId,
  sceneContext = {},
}: PerformanceAudioPanelProps) {
  const [plan, setPlan] = useState<PerformanceAudioPlan | null>(null)
  const [executionRequest, setExecutionRequest] = useState<AudioExecutionRequest | null>(null)
  const [assessment, setAssessment] = useState<AudioIntelligenceAssessment | null>(null)

  const planMutation = useMutation({
    mutationFn: () => createPerformanceAudioPlan(projectId, {
      scene_id: sceneId,
      shot_id: shotId,
      scene_context: sceneContext,
      force_refresh: true,
    }),
    onSuccess: (response) => {
      setPlan(response.plan)
      setExecutionRequest(null)
      setAssessment(null)
    },
  })

  const executionMutation = useMutation({
    mutationFn: (activePlan: PerformanceAudioPlan) => buildPerformanceAudioExecutionRequest(projectId, activePlan.plan_id),
    onSuccess: setExecutionRequest,
  })

  const assessmentMutation = useMutation({
    mutationFn: (activePlan: PerformanceAudioPlan) => createPerformanceAudioAssessment(projectId, {
      plan_id: activePlan.plan_id,
      asset_id: assetId,
      render_job_id: renderJobId,
    }),
    onSuccess: setAssessment,
  })

  const busy = planMutation.isPending || executionMutation.isPending || assessmentMutation.isPending
  const error = planMutation.error || executionMutation.error || assessmentMutation.error

  return (
    <section className="rounded-lg border border-zinc-700/70 bg-zinc-900/60 p-4 text-zinc-100" data-testid="performance-audio-panel">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Headphones size={16} className="text-cyan-300" />
            <h3 className="text-sm font-semibold">Performance Audio</h3>
          </div>
          <p className="mt-1 text-xs text-zinc-500">Voice direction, dialogue cues, music, ambience, silence, and mix handoff.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => planMutation.mutate()}
            disabled={busy}
            className="inline-flex h-8 items-center gap-2 rounded-md border border-cyan-400/40 bg-cyan-500/10 px-3 text-xs font-semibold text-cyan-100 transition-colors hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy && planMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <SlidersHorizontal size={14} />}
            Build Plan
          </button>
          <button
            type="button"
            onClick={() => plan && executionMutation.mutate(plan)}
            disabled={busy || !plan}
            className="inline-flex h-8 items-center gap-2 rounded-md border border-zinc-600 bg-zinc-800/70 px-3 text-xs font-semibold text-zinc-200 transition-colors hover:border-cyan-400/60 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Execution
          </button>
          <button
            type="button"
            onClick={() => plan && assessmentMutation.mutate(plan)}
            disabled={busy || !plan}
            className="inline-flex h-8 items-center gap-2 rounded-md border border-zinc-600 bg-zinc-800/70 px-3 text-xs font-semibold text-zinc-200 transition-colors hover:border-emerald-400/60 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Assess
          </button>
        </div>
      </div>

      {error ? (
        <div className="mt-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error instanceof Error ? error.message : 'Performance audio request failed'}
        </div>
      ) : null}

      <div className="mt-4 space-y-3">
        {plan ? <PlanSummary plan={plan} /> : (
          <div className="rounded-md border border-dashed border-zinc-700 p-5 text-center text-sm text-zinc-500">
            Build a plan to inspect voice, soundscape, and mix intent for this scene.
          </div>
        )}
        <ExecutionPreview request={executionRequest} />
        <AssessmentPreview assessment={assessment} />
      </div>
    </section>
  )
}
