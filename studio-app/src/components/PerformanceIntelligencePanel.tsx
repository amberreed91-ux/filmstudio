import { useMutation } from '@tanstack/react-query'
import { Brain, ChevronDown, Loader2, Save, Sparkles, Users } from 'lucide-react'
import { useState } from 'react'
import {
  analyzePerformance,
  savePerformanceDecision,
  type CharacterPerformanceBrief,
  type PerformanceAnalysisResponse,
  type PerformanceEvidenceRef,
} from '../lib/studioApi'

type PerformanceIntelligencePanelProps = {
  projectId: string
  initialSceneId?: string
}

function EvidenceList({ refs }: { refs: PerformanceEvidenceRef[] }) {
  if (!refs.length) {
    return <p className="text-xs text-zinc-500">Evidence is still thin for this read.</p>
  }
  return (
    <div className="space-y-2">
      {refs.slice(0, 4).map((ref) => (
        <div key={ref.evidence_id} className="rounded border border-zinc-700/60 bg-zinc-900/60 px-3 py-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-cyan-300">{ref.source_type}</span>
            <span className="text-[11px] text-zinc-500">{ref.reliability_label}</span>
          </div>
          {ref.excerpt ? <p className="mt-1 text-xs text-zinc-300">{ref.excerpt}</p> : null}
          {ref.relevance ? <p className="mt-1 text-xs text-zinc-500">{ref.relevance}</p> : null}
        </div>
      ))}
    </div>
  )
}

function BriefCard({ brief, onSave }: { brief: CharacterPerformanceBrief; onSave: (brief: CharacterPerformanceBrief) => void }) {
  const [showEvidence, setShowEvidence] = useState(false)
  const beat = brief.beats[0]
  return (
    <div className="rounded-lg border border-zinc-700/70 bg-zinc-800/30 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-zinc-100">{brief.character_name}</h4>
          <p className="mt-1 text-xs text-zinc-500">{brief.uncertainty.label.replace(/_/g, ' ')}</p>
        </div>
        <button
          type="button"
          onClick={() => onSave(brief)}
          className="inline-flex items-center gap-1 rounded-md border border-zinc-600 px-2 py-1 text-xs text-zinc-200 transition-colors hover:border-amber-400 hover:text-amber-300"
          title="Save performance decision"
        >
          <Save size={13} />
          Save
        </button>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Objective</div>
          <p className="mt-1 text-sm text-zinc-300">{brief.objective}</p>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Tactic</div>
          <p className="mt-1 text-sm text-zinc-300">{brief.tactic}</p>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Subtext</div>
          <p className="mt-1 text-sm text-zinc-300">{brief.subtext_summary}</p>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Continuity</div>
          <p className="mt-1 text-sm text-zinc-300">{brief.continuity_note}</p>
        </div>
      </div>

      {beat ? (
        <div className="mt-3 rounded border border-zinc-700/50 bg-zinc-900/50 px-3 py-2">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-300">{beat.beat_label}</div>
          <p className="mt-1 text-sm text-zinc-300">{beat.visible_action}</p>
          <p className="mt-1 text-xs text-zinc-500">{beat.voice_direction}</p>
        </div>
      ) : null}

      <button
        type="button"
        onClick={() => setShowEvidence((value) => !value)}
        className="mt-3 inline-flex items-center gap-1 text-xs text-cyan-300 hover:text-cyan-200"
      >
        <ChevronDown size={13} className={showEvidence ? 'rotate-180 transition-transform' : 'transition-transform'} />
        Evidence
      </button>
      {showEvidence ? <div className="mt-3"><EvidenceList refs={brief.evidence_refs} /></div> : null}
    </div>
  )
}

export default function PerformanceIntelligencePanel({ projectId, initialSceneId = 'scene_001' }: PerformanceIntelligencePanelProps) {
  const [sceneId, setSceneId] = useState(initialSceneId)
  const [analysis, setAnalysis] = useState<PerformanceAnalysisResponse | null>(null)
  const [saveMessage, setSaveMessage] = useState('')

  const analyzeMutation = useMutation({
    mutationFn: () => analyzePerformance(projectId, {
      scene_id: sceneId,
      scope: 'scene',
      persist: true,
      include_context_bundles: true,
    }),
    onSuccess: (result) => setAnalysis(result),
  })

  const saveMutation = useMutation({
    mutationFn: (brief: CharacterPerformanceBrief) => savePerformanceDecision(projectId, {
      scene_id: brief.scene_id,
      character_id: brief.character_id,
      source_brief_id: brief.brief_id,
      decision_text: brief.subtext_summary,
      inferred_tradeoff: 'performance restraint versus exposition',
      saved_by: 'creator',
      save_to_project_memory: true,
    }),
    onSuccess: () => {
      setSaveMessage('Saved to project memory.')
      setTimeout(() => setSaveMessage(''), 2500)
    },
  })

  return (
    <div className="space-y-4 py-4">
      <div className="flex flex-col gap-3 rounded-lg border border-zinc-700/70 bg-zinc-800/30 p-4 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Brain size={16} className="text-amber-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Performance Intelligence</h3>
          </div>
          <p className="mt-1 text-xs text-zinc-500">Motivation, subtext, relationship pressure, and acting continuity.</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={sceneId}
            onChange={(event) => setSceneId(event.target.value)}
            className="h-9 w-32 rounded-md border border-zinc-700 bg-zinc-950 px-3 text-sm text-zinc-200 outline-none focus:border-amber-400"
            aria-label="Scene ID"
          />
          <button
            type="button"
            onClick={() => analyzeMutation.mutate()}
            disabled={analyzeMutation.isPending || !sceneId.trim()}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-amber-400 px-3 text-sm font-medium text-zinc-950 transition-colors hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {analyzeMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
            Analyze
          </button>
        </div>
      </div>

      {analyzeMutation.error ? (
        <div className="rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {analyzeMutation.error instanceof Error ? analyzeMutation.error.message : 'Performance analysis failed'}
        </div>
      ) : null}
      {saveMessage ? <div className="rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">{saveMessage}</div> : null}

      {analysis ? (
        <div className="space-y-4">
          <div className="rounded-lg border border-zinc-700/70 bg-zinc-900/50 p-4">
            <p className="text-sm text-zinc-300">{analysis.summary}</p>
          </div>
          {analysis.briefs.map((brief) => (
            <BriefCard key={brief.brief_id} brief={brief} onSave={(value) => saveMutation.mutate(value)} />
          ))}
          {analysis.relationship_reads.length ? (
            <div className="rounded-lg border border-zinc-700/70 bg-zinc-800/30 p-4">
              <div className="mb-3 flex items-center gap-2">
                <Users size={15} className="text-cyan-400" />
                <h4 className="text-sm font-semibold text-zinc-100">Relationship Pressure</h4>
              </div>
              <div className="space-y-2">
                {analysis.relationship_reads.map((read) => (
                  <div key={read.relationship_read_id} className="rounded border border-zinc-700/50 bg-zinc-900/50 px-3 py-2">
                    <p className="text-sm text-zinc-300">{read.pressure}</p>
                    <p className="mt-1 text-xs text-zinc-500">{read.power_shift}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-zinc-700 p-6 text-center text-sm text-zinc-500">
          Run analysis for a scene to inspect playable motivation and evidence.
        </div>
      )}
    </div>
  )
}
