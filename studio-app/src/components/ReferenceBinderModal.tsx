import { useEffect, useState } from 'react'
import { Loader2, Lock, X } from 'lucide-react'
import { resolveAssetUrl, type GeneratedPrevisImage } from '../lib/previsImageApi'
import type { GeneratorShot } from './ReferenceImageGenerator'

type Props = {
  /** Null closes the modal. Non-null opens it for inspection. */
  image: GeneratedPrevisImage | null
  targetLabel: string
  shots: GeneratorShot[]
  initialShotId: string
  /** True when the active target already holds a locked canonical reference. */
  hasLockedCanonical: boolean
  binding: boolean
  onClose: () => void
  onConfirm: (shotId: string | null) => void
}

/**
 * ReferenceBinderModal — inspect a generated candidate still before binding.
 *
 * Presentation only: shows the still with its full provenance (prompt, seed,
 * model parameters, creation timestamp) and the shot it will bind to.
 * Binding always registers a *candidate* — it never overwrites a locked
 * canonical decision. When the target already holds a locked canonical, the
 * creator must explicitly confirm they understand the canonical stays
 * unchanged before the Bind action enables.
 */
export default function ReferenceBinderModal({
  image,
  targetLabel,
  shots,
  initialShotId,
  hasLockedCanonical,
  binding,
  onClose,
  onConfirm,
}: Props) {
  const [shotId, setShotId] = useState(initialShotId)
  const [acknowledged, setAcknowledged] = useState(false)

  useEffect(() => {
    setShotId(initialShotId)
    setAcknowledged(false)
  }, [image, initialShotId])

  useEffect(() => {
    if (!image) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [image, onClose])

  if (!image) return null

  const src = resolveAssetUrl(image.image_url)
  const options = shots.slice(0, 60)
  const confirmBlocked =
    binding || options.length === 0 || (hasLockedCanonical && !acknowledged)

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Inspect candidate still"
      data-testid="reference-binder-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border-2 border-[#1E293B] bg-[#0B0F17]/92 p-5 text-[#CBD5E1] shadow-[0_0_60px_rgba(109,40,217,0.35)] backdrop-blur-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-zinc-100">Inspect candidate still</h2>
            <p className="mt-1 text-xs text-zinc-400">
              {image.mode === 'character' ? 'Character' : 'Setting'} candidate · {targetLabel}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close candidate inspector"
            className="rounded border border-white/15 p-1.5 text-zinc-300 hover:border-white/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F59E0B] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0F17]"
          >
            <X size={14} />
          </button>
        </div>

        {src ? (
          <img
            src={src}
            alt={`Generated ${image.mode} reference seed ${image.seed}`}
            className={`mt-3 w-full rounded object-cover ${
              image.aspect_ratio === '9:16'
                ? 'aspect-[9/16]'
                : image.aspect_ratio === '1:1'
                  ? 'aspect-square'
                  : 'aspect-video'
            }`}
          />
        ) : (
          <p className="mt-3 rounded border border-white/10 p-4 text-xs text-zinc-500">
            Still image unavailable for preview.
          </p>
        )}

        <dl className="mt-3 space-y-1.5 rounded-md border border-white/10 bg-white/[0.02] p-3 text-[11px]">
          <div className="flex gap-2">
            <dt className="w-24 shrink-0 uppercase tracking-wide text-zinc-500">Prompt</dt>
            <dd className="min-w-0 text-zinc-300">{image.prompt}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-24 shrink-0 uppercase tracking-wide text-zinc-500">Seed</dt>
            <dd className="font-mono tabular-nums text-zinc-300">{image.seed}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-24 shrink-0 uppercase tracking-wide text-zinc-500">Provider</dt>
            <dd className="font-mono text-zinc-300">
              {image.provider} · {image.model}
            </dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-24 shrink-0 uppercase tracking-wide text-zinc-500">Framing</dt>
            <dd className="text-zinc-300">
              {image.aspect_ratio} · {image.style_preset} · {image.lighting_preset}
            </dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-24 shrink-0 uppercase tracking-wide text-zinc-500">Created</dt>
            <dd className="font-mono text-zinc-300">{image.created_at}</dd>
          </div>
        </dl>

        <label className="mt-3 block text-[10px] uppercase tracking-[0.14em] text-zinc-500">
          Bind to shot
          <select
            aria-label="Shot for inspected candidate"
            value={shotId}
            onChange={(event) => setShotId(event.target.value)}
            disabled={binding || options.length === 0}
            className="mt-1 block w-full rounded border border-white/15 bg-black/30 px-2 py-2 font-mono text-[11px] normal-case tracking-normal text-zinc-200 disabled:opacity-40"
          >
            {options.length === 0 ? <option value="">No shots recorded</option> : null}
            {options.map((shot) => (
              <option key={shot.shotId} value={shot.shotId}>
                {shot.sceneName} · {shot.shotId}
              </option>
            ))}
          </select>
        </label>

        {hasLockedCanonical ? (
          <label className="mt-3 flex cursor-pointer items-start gap-2 rounded-md border border-amber-200/30 bg-amber-200/5 p-3 text-[11px] leading-relaxed text-amber-100">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
              aria-label="Confirm canonical stays unchanged"
              className="mt-0.5"
            />
            <span>
              <Lock size={11} className="mr-1 inline" />
              This target holds a locked canonical reference. Binding registers this still as a
              candidate only — the canonical stays unchanged. Confirm you understand before binding.
            </span>
          </label>
        ) : (
          <p className="mt-3 text-[11px] leading-relaxed text-zinc-500">
            Binding registers this still as a candidate with shot provenance. Approval stays
            explicit — nothing becomes canonical here.
          </p>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={binding}
            className="rounded-md border border-white/15 px-3 py-2 text-xs text-zinc-300 disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(shotId || null)}
            disabled={confirmBlocked}
            aria-label="Confirm bind candidate to shot"
            className="inline-flex items-center gap-1.5 rounded-md border-2 border-[#8B5CF6]/60 px-3 py-2 text-xs font-medium text-cyan-200 shadow-[0_0_16px_rgba(139,92,246,0.35)] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F59E0B] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0F17]"
          >
            {binding ? <Loader2 size={12} className="animate-spin" /> : null}
            Bind as candidate
          </button>
        </div>
      </div>
    </div>
  )
}
