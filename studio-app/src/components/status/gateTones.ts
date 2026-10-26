/** Shared gate-chip tones: green ready / amber waiting / grey idle / red needs-attention. */

export type GateTone = 'ok' | 'waiting' | 'idle' | 'attention'

export const GATE_TONE_CLASS: Record<GateTone, string> = {
  ok: 'border-emerald-400/40 text-emerald-200',
  waiting: 'border-amber-400/40 text-amber-200',
  idle: 'border-white/15 text-zinc-400',
  attention: 'border-rose-400/40 text-rose-200',
}

export const DOT_CLASS: Record<GateTone, string> = {
  ok: 'bg-emerald-400',
  waiting: 'bg-amber-300',
  idle: 'bg-zinc-500',
  attention: 'bg-rose-400',
}
