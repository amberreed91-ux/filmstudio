export type TakeComparisonTake = {
  id: string
  label: string
  imageUrl?: string
  note?: string
}

type Props = {
  open: boolean
  takes: TakeComparisonTake[]
  selectedId: string | null
  onSelect: (id: string) => void
  onClose: () => void
}

/**
 * TakeComparisonDrawer — side-by-side take review surface for Screening.
 *
 * Obsidian glassmorphism treatment shared with the studio inspector family:
 * backdrop-blur-2xl, #0B0F17/#121824 grounds, 2px #1E293B graphite border,
 * #CBD5E1 silver typography, gold #F59E0B focus rings, violet #8B5CF6
 * glowing selection borders. Read-only presentation: selection only lifts
 * local UI state in the parent, never mutates backend records.
 */
export default function TakeComparisonDrawer({ open, takes, selectedId, onSelect, onClose }: Props) {
  if (!open) return null
  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-label="Take comparison drawer"
      data-testid="take-comparison-drawer"
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-lg flex-col border-l-2 border-[#1E293B] bg-[#0B0F17]/90 text-[#CBD5E1] shadow-[0_0_60px_rgba(109,40,217,0.35)] backdrop-blur-2xl"
    >
      <div className="flex items-start justify-between gap-3 border-b border-[#1E293B] bg-[#121824]/60 p-4">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-[0.18em] text-violet-300/80">Take comparison</p>
          <h2 className="mt-1 truncate text-sm font-semibold text-[#CBD5E1]">Compare takes before approval</h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close take comparison"
          data-testid="take-comparison-close"
          className="min-h-10 rounded-md border border-white/15 px-3 text-sm text-[#CBD5E1] hover:border-white/30 hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F59E0B] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0F17]"
        >
          Close
        </button>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto bg-[#121824]/30 p-4">
        {takes.length === 0 ? (
          <p className="rounded-lg border-2 border-dashed border-[#1E293B] p-4 text-xs text-[#CBD5E1]/70">
            No takes staged for comparison yet. Render at least two takes to compare them here.
          </p>
        ) : (
          <ul className="space-y-3">
            {takes.map((take) => {
              const selected = take.id === selectedId
              return (
                <li key={take.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(take.id)}
                    aria-pressed={selected}
                    data-testid={`take-comparison-take-${take.id}`}
                    data-selected={selected ? 'true' : 'false'}
                    className={`w-full rounded-xl border-2 p-3 text-left backdrop-blur-2xl transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F59E0B] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0F17] ${
                      selected
                        ? 'border-[#8B5CF6] bg-[#121824] shadow-[0_0_22px_rgba(139,92,246,0.5)]'
                        : 'border-[#1E293B] bg-[#0B0F17]/70 hover:border-white/25'
                    }`}
                  >
                    <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[#CBD5E1]">
                      {take.label}
                    </span>
                    {take.imageUrl ? (
                      <img src={take.imageUrl} alt={`${take.label} still`} className="mt-2 aspect-video w-full rounded-lg border border-[#1E293B] object-cover" />
                    ) : null}
                    {take.note ? <span className="mt-2 block text-[11px] leading-relaxed text-[#CBD5E1]/75">{take.note}</span> : null}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
