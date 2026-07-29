import { X } from 'lucide-react'
import type { CameraGrammarAssessment, CameraGrammarPlan } from '../lib/studioApi'

type CinematographerInspectionDrawerProps = {
  open: boolean
  plan: CameraGrammarPlan | null
  assessment?: CameraGrammarAssessment | null
  onClose: () => void
}

function label(value: string | null | undefined) {
  return (value || 'unspecified').replace(/_/g, ' ')
}

export default function CinematographerInspectionDrawer({
  open,
  plan,
  assessment,
  onClose,
}: CinematographerInspectionDrawerProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" role="dialog" aria-label="Cinematographer inspection">
      <div className="h-full w-full max-w-xl overflow-y-auto border-l border-zinc-700 bg-zinc-950 p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-zinc-100">Cinematographer Inspection</h3>
            <p className="mt-1 text-xs text-zinc-500">Evidence, memory, spine, and render slot trace.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-zinc-700 p-2 text-zinc-300 hover:border-zinc-500 hover:text-zinc-100"
            aria-label="Close cinematographer inspection"
          >
            <X size={15} />
          </button>
        </div>

        {plan ? (
          <div className="mt-5 space-y-4">
            <section className="rounded-lg border border-zinc-700/70 bg-zinc-900/60 p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-cyan-300">Visual Job</div>
              <p className="mt-2 text-sm text-zinc-300">{plan.visual_storytelling_rationale || plan.creator_note}</p>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-zinc-400">
                <span>Composition: {label(plan.composition_intent)}</span>
                <span>Lens: {label(plan.lens_intent)}</span>
                <span>Movement: {label(plan.movement_intent)}</span>
                <span>Lighting: {label(plan.lighting_intent)}</span>
                <span>Framing: {label(plan.framing_intent)}</span>
                <span>Evidence: {label(plan.confidence_label)}</span>
              </div>
            </section>

            <section className="rounded-lg border border-zinc-700/70 bg-zinc-900/60 p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-300">Render Slots</div>
              <div className="mt-2 space-y-2">
                {plan.render_slot_suggestions.map((slot) => (
                  <div key={slot.slot} className="rounded border border-zinc-700/60 bg-zinc-950/60 p-2">
                    <div className="text-xs font-semibold text-zinc-200">{label(slot.slot)}</div>
                    <p className="mt-1 text-xs text-zinc-400">{slot.suggestion}</p>
                    <p className="mt-1 text-[11px] text-zinc-600">{slot.budget_used}/{slot.budget_limit} characters</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-zinc-700/70 bg-zinc-900/60 p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Evidence</div>
              <div className="mt-2 space-y-2">
                {plan.evidence_refs.map((ref) => (
                  <p key={`${ref.ref_type}-${ref.ref_id}`} className="text-xs text-zinc-400">
                    <span className="text-zinc-200">{ref.label || ref.ref_type}</span>
                    {ref.summary ? `: ${ref.summary}` : null}
                  </p>
                ))}
                {!plan.evidence_refs.length ? <p className="text-xs text-zinc-500">No evidence refs attached yet.</p> : null}
              </div>
            </section>

            <section className="grid gap-3 md:grid-cols-2">
              <div className="rounded-lg border border-zinc-700/70 bg-zinc-900/60 p-4">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Memory</div>
                <div className="mt-2 space-y-2">
                  {plan.memory_refs.map((ref) => (
                    <p key={ref.memory_id} className="text-xs text-zinc-400">{ref.summary || ref.memory_type}</p>
                  ))}
                  {!plan.memory_refs.length ? <p className="text-xs text-zinc-500">No memory refs available.</p> : null}
                </div>
              </div>
              <div className="rounded-lg border border-zinc-700/70 bg-zinc-900/60 p-4">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Creative Spine</div>
                <div className="mt-2 space-y-2">
                  {plan.spine_refs.map((ref) => (
                    <p key={`${ref.constraint_id}-${ref.field_name}`} className="text-xs text-zinc-400">{ref.summary || ref.field_name}</p>
                  ))}
                  {!plan.spine_refs.length ? <p className="text-xs text-zinc-500">No spine refs available.</p> : null}
                </div>
              </div>
            </section>

            {assessment ? (
              <section className="rounded-lg border border-zinc-700/70 bg-zinc-900/60 p-4">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-cyan-300">Assessment</div>
                <p className="mt-2 text-sm text-zinc-300">{assessment.alignment_summary}</p>
                {assessment.revision_suggestions.map((suggestion) => (
                  <p key={suggestion.suggestion_id} className="mt-2 rounded border border-zinc-700/50 bg-zinc-950/50 p-2 text-xs text-zinc-400">
                    {suggestion.summary}
                  </p>
                ))}
              </section>
            ) : null}
          </div>
        ) : (
          <div className="mt-6 rounded border border-dashed border-zinc-700 p-5 text-sm text-zinc-500">
            Generate a camera plan before inspecting cinematographer reasoning.
          </div>
        )}
      </div>
    </div>
  )
}
