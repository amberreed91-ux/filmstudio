import { ROUTER_NORMALIZATION_BADGE_LABEL, ROUTER_NORMALIZATION_TOOLTIP } from '../lib/routerNormalization'

type Props = {
  /** Optional extra detail (e.g. warning count) appended after the label. */
  detail?: string
}

/**
 * Amber/gold status chip shown when a generation payload was auto-normalized
 * by `RunwayRouterAdapter`. Pure presentation — visibility logic lives in
 * `lib/routerNormalization.ts`.
 */
export default function RouterNormalizationBadge({ detail }: Props) {
  return (
    <span
      data-testid="router-normalization-badge"
      title={ROUTER_NORMALIZATION_TOOLTIP}
      aria-label={`Normalization: ${ROUTER_NORMALIZATION_TOOLTIP}`}
      className="inline-flex w-fit items-center gap-1 rounded-md border border-amber-300/45 bg-amber-500/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-100"
    >
      <span aria-hidden="true">✦</span>
      {ROUTER_NORMALIZATION_BADGE_LABEL}
      {detail ? <span className="font-normal normal-case tracking-normal text-amber-100/80">{detail}</span> : null}
    </span>
  )
}
