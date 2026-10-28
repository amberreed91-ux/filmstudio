import { Sparkles } from 'lucide-react'

type ShotIntentBadgeProps = {
  /** One-line purpose carried by the board card. Empty renders nothing. */
  intent: string
  testId?: string
}

/**
 * A quiet narrative marker for a card that carries a shot intent. It is a
 * reminder of why the shot exists, not a status: cards without an intent stay
 * unmarked rather than advertising an absence.
 */
export default function ShotIntentBadge({ intent, testId }: ShotIntentBadgeProps) {
  const text = (intent || '').trim()
  if (!text) return null

  return (
    <p
      data-testid={testId}
      title={text}
      className="flex min-w-0 items-start gap-1.5 text-xs leading-relaxed text-violet-200/90"
    >
      <Sparkles size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
      <span className="line-clamp-2">Intent · {text}</span>
    </p>
  )
}
