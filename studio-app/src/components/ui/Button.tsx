import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

/**
 * The studio's single button primitive.
 *
 * Why this exists: the app had 654 hand-rolled button elements, many of which
 * omitted `type` (so they defaulted to `type="submit"`), and only 12 of which
 * had any `:active` press state. Nothing reported in-flight state to assistive
 * technology — `aria-busy` appeared zero times in the codebase.
 *
 * This primitive makes the safe thing the default:
 *   - `type="button"` unless you opt into `type="submit"`.
 *   - `loading` sets `aria-busy`, disables the button, and swaps in a spinner.
 *   - One focus ring, one disabled treatment, one set of variants.
 *
 * Usage with `useAsyncAction`:
 *   const action = useAsyncAction(fn)
 *   <Button onClick={() => void action.run()} loading={action.isRunning} loadingLabel="Saving…">
 */

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'quiet'
export type ButtonSize = 'sm' | 'md' | 'lg'

const BASE_CLASS =
  'inline-flex items-center justify-center font-medium transition-all duration-150 ' +
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 ' +
  'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-45'

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  // Gold — the app's primary action (matches the side rail and the hero CTAs).
  primary:
    'bg-[#ffd165] text-[#3a2c00] hover:bg-[#ffdb85] active:bg-[#f0c257] ' +
    'shadow-[0_8px_24px_rgba(255,209,101,0.18)]',
  // Amber translucent — secondary emphasis.
  secondary:
    'border border-amber-300/40 bg-amber-400/15 text-amber-100 hover:bg-amber-400/25 active:bg-amber-400/30',
  // Neutral surface — tertiary actions.
  ghost:
    'border border-white/12 bg-white/[0.03] text-zinc-300 ' +
    'hover:border-amber-200/40 hover:bg-amber-400/10 hover:text-zinc-100',
  // Destructive.
  danger:
    'border border-rose-400/40 bg-rose-500/15 text-rose-200 hover:bg-rose-500/25 active:bg-rose-500/30',
  // Inline text action, no chrome.
  quiet: 'text-zinc-400 hover:text-zinc-100',
}

const SIZE_CLASS: Record<ButtonSize, string> = {
  sm: 'min-h-8 gap-1.5 rounded-md px-2.5 py-1 text-[11px]',
  md: 'min-h-10 gap-2 rounded-lg px-3.5 py-2 text-xs',
  lg: 'min-h-12 gap-2.5 rounded-xl px-5 py-3 text-sm',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  /** In-flight state: disables the button, sets aria-busy, and shows a spinner. */
  loading?: boolean
  /** Text shown while loading. Falls back to the normal children. */
  loadingLabel?: string
  /** Leading icon. Hidden while loading. */
  icon?: ReactNode
  /** Stretch to the container width. */
  fullWidth?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'ghost',
    size = 'md',
    loading = false,
    loadingLabel,
    icon,
    fullWidth = false,
    type = 'button',
    disabled,
    className = '',
    children,
    ...rest
  },
  ref,
) {
  const isDisabled = disabled || loading
  const classes = [
    BASE_CLASS,
    VARIANT_CLASS[variant],
    SIZE_CLASS[size],
    fullWidth ? 'w-full' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      {...rest}
      ref={ref}
      type={type}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={classes}
    >
      {loading ? (
        <Loader2 size={14} className="animate-spin" aria-hidden="true" />
      ) : (
        icon
      )}
      {loading && loadingLabel ? loadingLabel : children}
    </button>
  )
})

export default Button
