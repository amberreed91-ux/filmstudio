import type { ReactNode } from 'react'
import { getProceduralRoomStyle } from '../lib/proceduralBackdrops'

/**
 * Shared Fee Fee Anne Studios identity primitives: violet ambient lighting,
 * obsidian graphite panels, floating glass HUDs, and silver accents.
 * Backdrops come from the procedural engine — no image downloads.
 */

export function roomBackdrop(roomKey: string): { background: string; accent: string; accentDeep: string; glow: string } {
  const style = getProceduralRoomStyle(roomKey)
  return {
    background: style.background,
    accent: style.tokens.accent,
    accentDeep: style.tokens.accentDeep,
    glow: style.glow,
  }
}

export function RoomBackdrop({ roomKey, testid, children }: { roomKey: string; testid: string; children: ReactNode }) {
  const { background } = roomBackdrop(roomKey)
  return (
    <div data-testid={testid} className="w-full overflow-visible" style={{ background }}>
      {children}
    </div>
  )
}

export function PanoramicHeader({
  eyebrow,
  title,
  lede,
  accent,
}: {
  eyebrow: string
  title: string
  lede: string
  accent: string
}) {
  return (
    <section
      className="relative overflow-hidden rounded-2xl border border-white/10 p-8 text-center sm:p-10"
      style={{
        background: 'linear-gradient(180deg, rgba(10,8,24,0.82) 0%, rgba(4,6,13,0.88) 100%)',
        boxShadow: `0 0 44px ${accent}22, 0 24px 70px rgba(0,0,0,0.55)`,
      }}
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{ background: `linear-gradient(90deg, transparent, ${accent}aa, transparent)` }}
      />
      <p
        className="text-[11px] font-semibold uppercase"
        style={{ letterSpacing: '0.32em', color: accent }}
      >
        {eyebrow}
      </p>
      <h1 className="mt-3 text-3xl font-bold tracking-wide text-zinc-50 sm:text-4xl">{title}</h1>
      <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-zinc-300">{lede}</p>
    </section>
  )
}

export function GlassPanel({
  accent,
  children,
  className = '',
  testid,
}: {
  accent: string
  children: ReactNode
  className?: string
  testid?: string
}) {
  return (
    <section
      data-testid={testid}
      className={`rounded-2xl border border-white/10 bg-[#0a0d18]/80 p-6 backdrop-blur-md ${className}`}
      style={{ boxShadow: `0 0 28px ${accent}18, 0 18px 55px rgba(0,0,0,0.5)` }}
    >
      {children}
    </section>
  )
}

export function FieldLabel({ children }: { children: ReactNode }) {
  return (
    <label className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-300">
      {children}
    </label>
  )
}

const inputClass =
  'w-full rounded-lg border border-white/15 bg-black/55 p-3 text-sm text-zinc-100 outline-none transition-all duration-200 focus:ring-2'

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement> & { accent: string }) {
  const { accent, style, ...rest } = props
  return (
    <input
      {...rest}
      className={`${inputClass} ${props.className ?? ''}`}
      style={{ ...style, ['--tw-ring-color' as string]: `${accent}55` }}
      onFocus={(event) => {
        event.currentTarget.style.borderColor = `${accent}99`
        props.onFocus?.(event)
      }}
      onBlur={(event) => {
        event.currentTarget.style.borderColor = ''
        props.onBlur?.(event)
      }}
    />
  )
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { accent: string }) {
  const { accent, style, ...rest } = props
  return (
    <textarea
      {...rest}
      className={`${inputClass} min-h-[120px] resize-y ${props.className ?? ''}`}
      style={{ ...style, ['--tw-ring-color' as string]: `${accent}55` }}
      onFocus={(event) => {
        event.currentTarget.style.borderColor = `${accent}99`
        props.onFocus?.(event)
      }}
      onBlur={(event) => {
        event.currentTarget.style.borderColor = ''
        props.onBlur?.(event)
      }}
    />
  )
}

export function SelectInput(props: React.SelectHTMLAttributes<HTMLSelectElement> & { accent: string }) {
  const { accent, style, children, ...rest } = props
  return (
    <select
      {...rest}
      className={`${inputClass} ${props.className ?? ''}`}
      style={{ ...style, ['--tw-ring-color' as string]: `${accent}55` }}
    >
      {children}
    </select>
  )
}
