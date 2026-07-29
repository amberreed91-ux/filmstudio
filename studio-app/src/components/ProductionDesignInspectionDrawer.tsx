import { X } from 'lucide-react'
import type { ProductionDesignAssessment, ProductionDesignPlan } from '../lib/studioApi'

type ProductionDesignInspectionDrawerProps = {
  open: boolean
  onClose: () => void
  plan: ProductionDesignPlan | null
  assessment?: ProductionDesignAssessment | null
}

function EmptyRow({ label }: { label: string }) {
  return <div className="rounded-md border border-zinc-800 bg-zinc-950/40 p-3 text-xs text-zinc-500">{label}</div>
}

export default function ProductionDesignInspectionDrawer({
  open,
  onClose,
  plan,
  assessment = null,
}: ProductionDesignInspectionDrawerProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60" data-testid="production-design-inspection-drawer">
      <aside className="h-full w-full max-w-xl overflow-y-auto border-l border-zinc-700 bg-zinc-950 p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-zinc-100">Production Design Inspection</h2>
            <p className="mt-1 text-xs text-zinc-500">Environment, props, costumes, symbolism, evidence, memory, and spine context.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-zinc-700 text-zinc-300 hover:border-zinc-400 hover:text-white"
            aria-label="Close production design inspection"
          >
            <X size={16} />
          </button>
        </div>

        {!plan ? (
          <div className="mt-6">
            <EmptyRow label="No production design plan has been created yet." />
          </div>
        ) : (
          <div className="mt-6 space-y-5">
            <section>
              <div className="text-[11px] font-semibold uppercase text-zinc-500">Source</div>
              <div className="mt-2 rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
                <p className="text-sm text-zinc-300">{plan.source_summary || plan.creator_note}</p>
                <div className="mt-2 text-xs text-zinc-500">Signature {plan.source_signature || 'not available'}</div>
              </div>
            </section>

            <section>
              <div className="text-[11px] font-semibold uppercase text-zinc-500">Evidence</div>
              <div className="mt-2 space-y-2">
                {plan.evidence_refs.slice(0, 8).map((ref) => (
                  <div key={`${ref.evidence_id}-${ref.source_id}`} className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
                    <div className="text-xs font-medium text-zinc-200">{ref.source_type.replace(/_/g, ' ')}</div>
                    <p className="mt-1 text-xs text-zinc-500">{ref.relevance || ref.excerpt || ref.source_id}</p>
                  </div>
                ))}
                {!plan.evidence_refs.length ? <EmptyRow label="Evidence is thin for this design read." /> : null}
              </div>
            </section>

            <section>
              <div className="text-[11px] font-semibold uppercase text-zinc-500">Memory and Spine</div>
              <div className="mt-2 grid gap-2">
                {plan.memory_refs.slice(0, 4).map((ref) => (
                  <div key={ref.memory_id} className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3 text-xs text-zinc-400">
                    {ref.summary || ref.memory_type}
                  </div>
                ))}
                {plan.spine_refs.slice(0, 4).map((ref) => (
                  <div key={`${ref.constraint_id}-${ref.field_name}`} className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3 text-xs text-zinc-400">
                    {ref.summary || ref.field_name}
                  </div>
                ))}
                {!plan.memory_refs.length && !plan.spine_refs.length ? <EmptyRow label="No memory or Creative Spine refs were available." /> : null}
              </div>
            </section>

            <section>
              <div className="text-[11px] font-semibold uppercase text-zinc-500">Symbolism</div>
              <div className="mt-2 space-y-2">
                {plan.symbolic_refs.map((ref) => (
                  <div key={ref.symbol_id} className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
                    <div className="text-sm text-zinc-200">{ref.object_name || ref.motif}</div>
                    <p className="mt-1 text-xs text-zinc-500">{ref.emotional_meaning || 'Advisory symbolic read.'}</p>
                  </div>
                ))}
                {!plan.symbolic_refs.length ? <EmptyRow label="No symbolic object refs were strong enough to surface." /> : null}
              </div>
            </section>

            {assessment ? (
              <section>
                <div className="text-[11px] font-semibold uppercase text-zinc-500">Assessment</div>
                <div className="mt-2 rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
                  <p className="text-sm text-zinc-300">{assessment.alignment_summary}</p>
                  {assessment.revision_suggestions.length ? (
                    <div className="mt-3 space-y-2">
                      {assessment.revision_suggestions.slice(0, 4).map((suggestion) => (
                        <p key={suggestion.suggestion_id} className="text-xs text-zinc-500">{suggestion.summary}</p>
                      ))}
                    </div>
                  ) : null}
                </div>
              </section>
            ) : null}
          </div>
        )}
      </aside>
    </div>
  )
}
