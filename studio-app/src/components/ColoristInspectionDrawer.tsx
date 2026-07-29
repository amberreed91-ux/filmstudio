import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ColorLookBible, ColorMatchAssessment, ColorRenderContext, ColoristLookPlan } from '../lib/studioApi'

type ColoristInspectionDrawerProps = {
  open: boolean
  onClose: () => void
  lookBible: ColorLookBible | null
  plan: ColoristLookPlan | null
  renderContext: ColorRenderContext | null
  assessment: ColorMatchAssessment | null
}

function label(value: string | null | undefined) {
  return (value || 'pending').replace(/_/g, ' ')
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-md border border-zinc-700/60 bg-zinc-950/45 p-3">
      <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{title}</h4>
      <div className="mt-2 space-y-2">{children}</div>
    </section>
  )
}

export default function ColoristInspectionDrawer({
  open,
  onClose,
  lookBible,
  plan,
  renderContext,
  assessment,
}: ColoristInspectionDrawerProps) {
  if (!open) return null

  const evidence = assessment?.evidence_refs.length ? assessment.evidence_refs : plan?.evidence_refs || lookBible?.evidence_refs || []

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60" data-testid="colorist-inspection-drawer">
      <aside className="h-full w-full max-w-xl overflow-y-auto border-l border-zinc-700 bg-zinc-950 p-5 text-zinc-100 shadow-2xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold">Colorist Inspection</h3>
            <p className="mt-1 text-xs text-zinc-500">Look development, palette evidence, grade matching, and final handoff trace.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-zinc-700 text-zinc-300 hover:border-zinc-500"
            aria-label="Close colorist inspection"
          >
            <X size={15} />
          </button>
        </div>

        <div className="mt-5 space-y-3">
          <Section title="Look Bible">
            {lookBible ? (
              <>
                <p className="text-sm text-zinc-300">{lookBible.creator_note}</p>
                <p className="text-xs text-zinc-500">{lookBible.show_lut_intent}</p>
                <div className="flex flex-wrap gap-2">
                  {lookBible.palette_families.flatMap((family) => family.colors).slice(0, 8).map((color) => (
                    <span key={color} className="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300">{color}</span>
                  ))}
                </div>
              </>
            ) : <p className="text-xs text-zinc-500">No look bible has been developed in this panel yet.</p>}
          </Section>

          <Section title="Plan">
            {plan ? (
              <>
                <p className="text-sm text-zinc-300">{plan.creator_note}</p>
                <div className="grid gap-2 md:grid-cols-2">
                  <p className="text-xs text-zinc-400">Contrast: {plan.contrast_intent}</p>
                  <p className="text-xs text-zinc-400">Temperature: {plan.temperature_intent}</p>
                  <p className="text-xs text-zinc-400">Saturation: {plan.saturation_intent}</p>
                  <p className="text-xs text-zinc-400">Confidence: {label(plan.confidence_label)}</p>
                </div>
              </>
            ) : <p className="text-xs text-zinc-500">No scene color plan has been created.</p>}
          </Section>

          <Section title="Render Context">
            {renderContext ? (
              <>
                <p className="text-sm text-zinc-300">{renderContext.color_direction}</p>
                <p className="text-xs text-zinc-500">{renderContext.lighting_color_notes}</p>
              </>
            ) : <p className="text-xs text-zinc-500">No render color context has been built.</p>}
          </Section>

          <Section title="Assessment">
            {assessment ? (
              <>
                <p className="text-sm text-zinc-300">{assessment.match_summary}</p>
                <div className="flex flex-wrap gap-2">
                  {assessment.held_axes.map((axis) => (
                    <span key={`held-${axis}`} className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-300">Held {label(axis)}</span>
                  ))}
                  {assessment.drift_axes.map((axis) => (
                    <span key={`drift-${axis}`} className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs text-amber-300">Review {label(axis)}</span>
                  ))}
                </div>
              </>
            ) : <p className="text-xs text-zinc-500">No rendered output has been assessed.</p>}
          </Section>

          <Section title="Evidence">
            {evidence.slice(0, 8).map((ref) => (
              <div key={`${ref.ref_type}-${ref.ref_id}`} className="rounded border border-zinc-800 bg-zinc-900/60 p-2">
                <div className="text-xs font-semibold text-zinc-300">{ref.label || label(ref.ref_type)}</div>
                <p className="mt-1 text-xs text-zinc-500">{ref.summary || ref.source_service}</p>
              </div>
            ))}
            {!evidence.length ? <p className="text-xs text-zinc-500">Evidence is still thin for this colorist read.</p> : null}
          </Section>
        </div>
      </aside>
    </div>
  )
}
