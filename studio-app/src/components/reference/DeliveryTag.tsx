import { GATE_TONE_CLASS } from '../status/gateTones'

/** True for files kept on this machine (never http/data URLs). */
export function isLocalBoardFile(imageUrl: string | null | undefined): boolean {
  const url = (imageUrl || '').trim()
  if (!url) return true
  if (/^https?:\/\//i.test(url)) return false
  if (url.startsWith('data:')) return false
  return true
}

/**
 * Plain-language delivery tag. "Local file" means: kept here,
 * not ready to send — it must be uploaded at submit time.
 */
export default function DeliveryTag({ imageUrl }: { imageUrl: string | null | undefined }) {
  if (isLocalBoardFile(imageUrl)) {
    return (
      <span
        data-testid="delivery-tag-local"
        className={`inline-block rounded-full border px-2.5 py-0.5 text-[11px] ${GATE_TONE_CLASS.idle}`}
      >
        Local file — not ready to send
      </span>
    )
  }
  return (
    <span
      data-testid="delivery-tag-ready"
      className={`inline-block rounded-full border px-2.5 py-0.5 text-[11px] ${GATE_TONE_CLASS.ok}`}
    >
      Ready to send
    </span>
  )
}
