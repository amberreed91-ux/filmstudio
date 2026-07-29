import { BrainCircuit, Check, Loader2, Sparkles, UserPlus, UsersRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  approveCastingDecision,
  buildCastingRoles,
  createAuditionPackage,
  createTalentProfile,
  evaluateAudition,
  getCastingDepartmentSignal,
  getCastingProjection,
  listCastingRoles,
  listTalentProfiles,
  recommendCasting,
  submitAudition,
  type AuditionEvaluation,
  type AuditionPackage,
  type AuditionSubmission,
  type CastingDecision,
  type CastingDepartmentSignal,
  type CastingModality,
  type CastingProjection,
  type CastingRecommendation,
  type CastingRoleBreakdown,
  type TalentProfile,
} from '../lib/castingIntelligenceApi'

type CastingIntelligencePanelProps = {
  projectId: string
}

function label(value: string | undefined | null) {
  return (value || 'pending').replace(/_/g, ' ')
}

function readinessClass(value: string) {
  if (value === 'ready') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
  if (value === 'blocked') return 'border-amber-500/30 bg-amber-500/10 text-amber-300'
  return 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300'
}

function RoleRow({
  role,
  selected,
  onSelect,
}: {
  role: CastingRoleBreakdown
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-md border p-3 text-left transition-colors ${
        selected ? 'border-amber-400/70 bg-amber-400/10' : 'border-zinc-700/60 bg-zinc-950/40 hover:border-zinc-500'
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-zinc-100">{role.character_name}</div>
          <div className="mt-1 text-xs text-zinc-500">{label(role.role_size)} · {role.scene_ids.length} scene{role.scene_ids.length === 1 ? '' : 's'}</div>
        </div>
        <span className={`rounded border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide ${readinessClass(role.readiness_label)}`}>
          {label(role.readiness_label)}
        </span>
      </div>
      <p className="mt-2 text-xs text-zinc-400">{role.performance_demands[0] || 'Performance demands pending.'}</p>
    </button>
  )
}

function TalentForm({ onCreate, busy }: { onCreate: (name: string, modality: CastingModality) => void; busy: boolean }) {
  const [name, setName] = useState('AI Stand-In')
  const [modality, setModality] = useState<CastingModality>('placeholder')
  return (
    <div className="rounded-md border border-zinc-700/60 bg-zinc-950/45 p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-zinc-100">
        <UserPlus size={14} className="text-cyan-300" />
        Talent
      </div>
      <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="h-9 rounded-md border border-zinc-700 bg-zinc-950 px-3 text-sm text-zinc-200 outline-none focus:border-cyan-400"
          aria-label="Talent name"
        />
        <select
          value={modality}
          onChange={(event) => setModality(event.target.value as CastingModality)}
          className="h-9 rounded-md border border-zinc-700 bg-zinc-950 px-3 text-sm text-zinc-200 outline-none focus:border-cyan-400"
          aria-label="Talent modality"
        >
          <option value="placeholder">Placeholder</option>
          <option value="human">Human</option>
          <option value="ai">AI</option>
          <option value="hybrid">Hybrid</option>
          <option value="voice_only">Voice Only</option>
          <option value="visual_only">Visual Only</option>
        </select>
        <button
          type="button"
          onClick={() => onCreate(name, modality)}
          disabled={busy || !name.trim()}
          className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-cyan-400/50 bg-cyan-500/10 px-3 text-xs font-semibold text-cyan-100 transition-colors hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <UserPlus size={14} />}
          Add
        </button>
      </div>
    </div>
  )
}

export default function CastingIntelligencePanel({ projectId }: CastingIntelligencePanelProps) {
  const [roles, setRoles] = useState<CastingRoleBreakdown[]>([])
  const [talent, setTalent] = useState<TalentProfile[]>([])
  const [selectedRoleId, setSelectedRoleId] = useState('')
  const [selectedTalentId, setSelectedTalentId] = useState('')
  const [recommendations, setRecommendations] = useState<CastingRecommendation[]>([])
  const [auditionPackage, setAuditionPackage] = useState<AuditionPackage | null>(null)
  const [audition, setAudition] = useState<AuditionSubmission | null>(null)
  const [evaluation, setEvaluation] = useState<AuditionEvaluation | null>(null)
  const [projection, setProjection] = useState<CastingProjection | null>(null)
  const [decision, setDecision] = useState<CastingDecision | null>(null)
  const [signal, setSignal] = useState<CastingDepartmentSignal | null>(null)

  useEffect(() => {
    listCastingRoles(projectId).then((nextRoles) => {
      setRoles(nextRoles)
      setSelectedRoleId((current) => current || nextRoles[0]?.role_id || '')
    }).catch(() => undefined)
    listTalentProfiles(projectId).then((nextTalent) => {
      setTalent(nextTalent)
      setSelectedTalentId((current) => current || nextTalent[0]?.talent_id || '')
    }).catch(() => undefined)
    getCastingDepartmentSignal(projectId).then(setSignal).catch(() => undefined)
  }, [projectId])

  const buildMutation = useMutation({
    mutationFn: () => buildCastingRoles(projectId),
    onSuccess: (response) => {
      setRoles(response.roles)
      setSelectedRoleId(response.roles[0]?.role_id || '')
      getCastingDepartmentSignal(projectId).then(setSignal).catch(() => undefined)
    },
  })

  const talentMutation = useMutation({
    mutationFn: ({ name, modality }: { name: string; modality: CastingModality }) => createTalentProfile(projectId, {
      display_name: name,
      modality,
      performance_strengths: ['restrained pressure and readable subtext'],
      vocal_characteristics: ['contained delivery'],
      provider_bindings: modality === 'placeholder' ? [{ provider: 'local_tts', voice_id: `${name.toLowerCase().replace(/\s+/g, '-')}-voice` }] : [],
    }),
    onSuccess: (profile) => {
      setTalent((current) => [profile, ...current])
      setSelectedTalentId(profile.talent_id)
    },
  })

  const recommendMutation = useMutation({
    mutationFn: () => recommendCasting(projectId, selectedRoleId, selectedTalentId || undefined),
    onSuccess: setRecommendations,
  })

  const packageMutation = useMutation({
    mutationFn: () => createAuditionPackage(projectId, selectedRoleId),
    onSuccess: (nextPackage) => {
      setAuditionPackage(nextPackage)
      setAudition(null)
      setEvaluation(null)
    },
  })

  const submitMutation = useMutation({
    mutationFn: (activePackage: AuditionPackage) => submitAudition(projectId, activePackage.package_id, {
      talent_id: selectedTalentId,
      submitted_text: `Audition read for ${selectedRole?.character_name || 'the role'}: hold the pressure in the pause before the line.`,
    }),
    onSuccess: (submission) => {
      setAudition(submission)
      setEvaluation(null)
    },
  })

  const evaluationMutation = useMutation({
    mutationFn: (submission: AuditionSubmission) => evaluateAudition(projectId, submission.audition_id),
    onSuccess: setEvaluation,
  })

  const approveMutation = useMutation({
    mutationFn: (recommendation: CastingRecommendation) => approveCastingDecision(projectId, {
      role_id: recommendation.role_id,
      talent_id: recommendation.talent_id,
      recommendation_id: recommendation.recommendation_id,
      decision_rationale: recommendation.rationale,
    }),
    onSuccess: (approved) => {
      setDecision(approved)
      getCastingProjection(projectId, approved.role_id).then(setProjection).catch(() => undefined)
      getCastingDepartmentSignal(projectId).then(setSignal).catch(() => undefined)
    },
  })

  const selectedRole = roles.find((role) => role.role_id === selectedRoleId)
  const selectedTalent = talent.find((profile) => profile.talent_id === selectedTalentId)
  const busy = buildMutation.isPending || talentMutation.isPending || recommendMutation.isPending || approveMutation.isPending || packageMutation.isPending || submitMutation.isPending || evaluationMutation.isPending
  const error = buildMutation.error || talentMutation.error || recommendMutation.error || approveMutation.error || packageMutation.error || submitMutation.error || evaluationMutation.error

  return (
    <section className="rounded-lg border border-zinc-700/70 bg-zinc-900/60 p-4 text-zinc-100" data-testid="casting-intelligence-panel">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <UsersRound size={16} className="text-amber-300" />
            <h3 className="text-sm font-semibold">Casting Intelligence</h3>
          </div>
          <p className="mt-1 text-xs text-zinc-500">Role coverage, talent fit, consent readiness, and active cast projection.</p>
        </div>
        <button
          type="button"
          onClick={() => buildMutation.mutate()}
          disabled={busy}
          className="inline-flex h-8 items-center gap-2 rounded-md border border-amber-400/50 bg-amber-500/10 px-3 text-xs font-semibold text-amber-100 transition-colors hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {buildMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          Build Roles
        </button>
      </div>

      {signal ? (
        <div className="mt-3 rounded-md border border-zinc-700/60 bg-zinc-950/45 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide ${readinessClass(signal.readiness_label)}`}>
              {label(signal.readiness_label)}
            </span>
            <span className="text-xs text-zinc-400">{signal.covered_roles}/{signal.total_roles} roles covered</span>
          </div>
          {signal.advisory ? <p className="mt-2 text-xs text-amber-300">{signal.advisory}</p> : null}
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error instanceof Error ? error.message : 'Casting workflow failed'}
        </div>
      ) : null}

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="space-y-2">
          {roles.map((role) => (
            <RoleRow key={role.role_id} role={role} selected={role.role_id === selectedRoleId} onSelect={() => setSelectedRoleId(role.role_id)} />
          ))}
          {!roles.length ? (
            <div className="rounded-md border border-dashed border-zinc-700 p-4 text-sm text-zinc-500">
              Build casting roles from the current script to begin.
            </div>
          ) : null}
        </div>

        <div className="space-y-3">
          <TalentForm onCreate={(name, modality) => talentMutation.mutate({ name, modality })} busy={talentMutation.isPending} />

          <div className="rounded-md border border-zinc-700/60 bg-zinc-950/45 p-3">
            <div className="mb-2 text-sm font-semibold text-zinc-100">Audition</div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => packageMutation.mutate()}
                disabled={busy || !selectedRole}
                className="inline-flex h-8 items-center gap-2 rounded-md border border-zinc-600 bg-zinc-800/70 px-3 text-xs font-semibold text-zinc-200 transition-colors hover:border-cyan-400/60 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {packageMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                Create Sides
              </button>
              <button
                type="button"
                onClick={() => auditionPackage && submitMutation.mutate(auditionPackage)}
                disabled={busy || !auditionPackage || !selectedTalentId}
                className="inline-flex h-8 items-center gap-2 rounded-md border border-zinc-600 bg-zinc-800/70 px-3 text-xs font-semibold text-zinc-200 transition-colors hover:border-cyan-400/60 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Submit Read
              </button>
              <button
                type="button"
                onClick={() => audition && evaluationMutation.mutate(audition)}
                disabled={busy || !audition}
                className="inline-flex h-8 items-center gap-2 rounded-md border border-zinc-600 bg-zinc-800/70 px-3 text-xs font-semibold text-zinc-200 transition-colors hover:border-amber-400/60 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Evaluate
              </button>
            </div>
            {auditionPackage ? <p className="mt-2 text-xs text-zinc-500">{auditionPackage.performance_intent || auditionPackage.instructions}</p> : null}
            {evaluation ? <p className="mt-2 text-xs text-amber-200">{evaluation.fit_read}</p> : null}
          </div>

          <div className="rounded-md border border-zinc-700/60 bg-zinc-950/45 p-3">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-zinc-100">
              <BrainCircuit size={14} className="text-amber-300" />
              Match
            </div>
            <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
              <select
                value={selectedTalentId}
                onChange={(event) => setSelectedTalentId(event.target.value)}
                className="h-9 rounded-md border border-zinc-700 bg-zinc-950 px-3 text-sm text-zinc-200 outline-none focus:border-amber-400"
                aria-label="Talent profile"
              >
                <option value="">Select talent</option>
                {talent.map((profile) => (
                  <option key={profile.talent_id} value={profile.talent_id}>{profile.display_name} · {label(profile.modality)}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => recommendMutation.mutate()}
                disabled={busy || !selectedRole || !selectedTalent}
                className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-zinc-600 bg-zinc-800/70 px-3 text-xs font-semibold text-zinc-200 transition-colors hover:border-amber-400/60 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {recommendMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                Recommend
              </button>
            </div>
          </div>

          {recommendations.map((recommendation) => (
            <div key={recommendation.recommendation_id} className="rounded-md border border-zinc-700/60 bg-zinc-950/45 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className={`rounded border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide ${readinessClass(recommendation.readiness_label)}`}>
                  {label(recommendation.readiness_label)}
                </span>
                <span className="text-[11px] uppercase tracking-wide text-zinc-500">{label(recommendation.uncertainty_label)}</span>
              </div>
              <p className="mt-2 text-sm text-zinc-300">{recommendation.recommendation}</p>
              <p className="mt-1 text-xs text-zinc-500">{recommendation.rationale}</p>
              {recommendation.blockers.map((blocker) => (
                <p key={blocker} className="mt-1 text-xs text-amber-300">{blocker}</p>
              ))}
              <button
                type="button"
                onClick={() => approveMutation.mutate(recommendation)}
                disabled={busy || recommendation.readiness_label === 'blocked'}
                className="mt-3 inline-flex h-8 items-center gap-2 rounded-md border border-emerald-400/50 bg-emerald-500/10 px-3 text-xs font-semibold text-emerald-100 transition-colors hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {approveMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                Approve Cast
              </button>
            </div>
          ))}

          {decision || projection ? (
            <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3">
              <div className="text-sm font-semibold text-emerald-200">Active Cast</div>
              <p className="mt-1 text-xs text-emerald-100">
                {decision ? `${selectedRole?.character_name || 'Role'} is cast.` : `${projection?.active_decisions.length || 0} active decisions.`}
              </p>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  )
}
