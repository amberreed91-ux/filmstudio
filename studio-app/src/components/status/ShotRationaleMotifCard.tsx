import type { DeskQueueItem } from '../../lib/deskShotInspector'

type ShotRationaleMotifCardProps = {
  item: DeskQueueItem
}

/**
 * The Desk's inspector card: why this shot exists and which motif it carries.
 *
 * Read-only by design — the Desk reports evidence; it never edits the shot.
 * An untagged shot gets a plain sentence, not an invented rationale: the
 * co-director only speaks from evidence it actually has.
 */
export default function ShotRationaleMotifCard({ item }: ShotRationaleMotifCardProps) {
  const where = [item.sceneName || item.sceneId, item.shotNumber ? `shot ${item.shotNumber}` : '']
    .filter(Boolean)
    .join(' · ')

  return (
    <div data-testid="shot-rationale-motif" className="rounded-lg border border-white/10 bg-white/[0.02] p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-200/80">
          Shot Rationale &amp; Motif
        </h2>
        <span className="font-mono text-[11px] text-zinc-500">{item.shotId}</span>
      </div>
      {where && <p className="mt-1 text-xs text-zinc-500">{where}</p>}

      <div className="mt-4">
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-400">Primary purpose</p>
        {item.intent ? (
          <p className="mt-1 text-sm leading-relaxed text-zinc-200" data-testid="shot-rationale">
            {item.intent}
          </p>
        ) : (
          <p className="mt-1 text-xs leading-relaxed text-zinc-500" data-testid="shot-rationale-empty">
            No shot rationale has been carried from the board yet. Set this shot&apos;s intent in Previs and it will follow the cut here.
          </p>
        )}
      </div>

      <div className="mt-4">
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-400">Visual motifs</p>
        {item.motifs.length > 0 ? (
          <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Visual motifs">
            {item.motifs.map((motif) => (
              <li
                key={motif}
                data-testid="shot-motif-chip"
                className="rounded-full border border-violet-300/30 bg-violet-400/10 px-2 py-0.5 text-[11px] text-violet-100"
              >
                {motif}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-xs leading-relaxed text-zinc-500" data-testid="shot-motif-empty">
            No motif is tagged to this shot.
          </p>
        )}
      </div>
    </div>
  )
}
