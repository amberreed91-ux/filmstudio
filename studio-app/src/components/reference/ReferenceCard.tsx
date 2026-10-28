import { GATE_TONE_CLASS } from '../status/gateTones'
import TechDetailsDrawer from '../status/TechDetailsDrawer'
import DeliveryTag from './DeliveryTag'
import type { BoardAsset } from '../../lib/referenceBoardApi'
import { boardCardState } from '../../lib/referenceBoardState'
import { buildStudioApiUrl } from '../../lib/studioApi'

function thumbSrc(imageUrl: string | null | undefined): string | null {
  if (!imageUrl || !imageUrl.trim()) return null
  const trimmed = imageUrl.trim()
  if (/^https?:\/\//i.test(trimmed) || trimmed.startsWith('data:')) return trimmed
  return buildStudioApiUrl(trimmed)
}

function plainName(asset: BoardAsset): string {
  const target = (asset.target_id || '').trim()
  const category = (asset.category || asset.kind || '').replace(/_/g, ' ')
  if (asset.target_type === 'setting') return target ? `${target} — ${category}` : category
  return target ? `${target} — ${category}` : category
}

export default function ReferenceCard({ asset }: { asset: BoardAsset }) {
  const state = boardCardState(asset)
  const src = thumbSrc(asset.image_url)
  return (
    <article
      data-testid={`reference-card-${asset.ref_id}`}
      className="rounded-lg border border-white/10 bg-black/30 p-2.5"
    >
      <div className="flex aspect-[4/3] items-center justify-center overflow-hidden rounded bg-black/50 text-xs text-zinc-500">
        {src ? (
          <img src={src} alt={plainName(asset)} className="h-full w-full object-cover" loading="lazy" />
        ) : (
          <span>{plainName(asset)}</span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span
          data-testid={`reference-chip-${asset.ref_id}`}
          className={`inline-block rounded-full border px-2.5 py-0.5 text-[11px] ${GATE_TONE_CLASS[state.tone]}`}
        >
          {state.chip}
        </span>
        <DeliveryTag imageUrl={asset.image_url} />
      </div>
      <p className="mt-1.5 text-[13px] leading-snug text-zinc-200">{state.reason}</p>
      <TechDetailsDrawer summary="Details">
        <p className="break-all font-mono text-[11px]">
          {asset.ref_id} · {asset.kind} · {asset.target_type}/{asset.target_id} · {asset.approval_state}
          {asset.canonical ? ' · canonical' : ''} · {asset.source_kind || 'confirmed'}
          {asset.source_shot_id ? ` · from ${asset.source_shot_id}` : ''}
        </p>
      </TechDetailsDrawer>
    </article>
  )
}
