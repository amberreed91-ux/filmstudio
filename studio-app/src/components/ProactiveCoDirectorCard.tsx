/**
 * ProactiveCoDirectorCard
 *
 * Inline card — never a modal or toast.
 * Dark card with teal left border.
 * Only renders when should_surface: true.
 * Dismissed once → never re-appears in same session.
 *
 * Props:
 *   message       — co-director voice text
 *   triggerType   — scene_save | project_open | cut_assembly
 *   saveToNotes   — whether to show "Save to Notes" button
 *   onDismiss     — called when × is clicked
 *   onSaveToNotes — called when "Save to Notes" is clicked
 */

import type { TriggerType } from '../hooks/useProactiveCoDirector'

interface Props {
  message: string
  triggerType: TriggerType
  saveToNotes?: boolean
  onDismiss: () => void
  onSaveToNotes?: () => void
}

const TRIGGER_LABELS: Record<TriggerType, string> = {
  scene_save: 'Scene Note',
  project_open: 'Welcome Back',
  cut_assembly: 'Cut Review',
}

export default function ProactiveCoDirectorCard({
  message,
  triggerType,
  saveToNotes = false,
  onDismiss,
  onSaveToNotes,
}: Props) {
  return (
    <div
      className="relative rounded-lg overflow-hidden"
      style={{
        background: 'rgba(0, 0, 0, 0.55)',
        border: '1px solid rgba(0, 212, 170, 0.25)',
        borderLeft: '3px solid #00d4aa',
      }}
      role="note"
      aria-label="Co-Director note"
    >
      {/* Header row */}
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <div className="flex items-center gap-2">
          {/* Teal dot */}
          <span
            className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0"
            style={{ background: '#00d4aa' }}
          />
          {/* Eyebrow */}
          <span
            className="text-[9px] font-semibold uppercase tracking-[0.22em]"
            style={{ color: '#00d4aa' }}
          >
            Co-Director
          </span>
          {/* Trigger label */}
          <span
            className="text-[9px] uppercase tracking-[0.14em] opacity-60"
            style={{ color: '#00d4aa' }}
          >
            · {TRIGGER_LABELS[triggerType]}
          </span>
        </div>

        {/* Dismiss × */}
        <button
          type="button"
          onClick={onDismiss}
          className="rounded p-1 text-zinc-500 transition-colors hover:text-zinc-200"
          aria-label="Dismiss co-director note"
          title="Dismiss"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          >
            <line x1="1" y1="1" x2="11" y2="11" />
            <line x1="11" y1="1" x2="1" y2="11" />
          </svg>
        </button>
      </div>

      {/* Message */}
      <div className="px-4 pb-3">
        <p
          className="text-sm leading-relaxed"
          style={{ color: 'rgba(255,255,255,0.82)' }}
        >
          {message}
        </p>

        {/* Save to Notes button */}
        {saveToNotes && onSaveToNotes && (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => {
                onSaveToNotes()
              }}
              className="inline-flex items-center gap-1.5 rounded border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] transition-all hover:scale-[1.02]"
              style={{
                borderColor: 'rgba(0, 212, 170, 0.35)',
                background: 'rgba(0, 212, 170, 0.08)',
                color: '#00d4aa',
              }}
            >
              {/* Floppy disk icon */}
              <svg
                width="11"
                height="11"
                viewBox="0 0 16 16"
                fill="currentColor"
              >
                <path d="M2 1a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V4.5L11.5 1H2zm9 0v3H5V1h6zM3 9h10v5H3V9zm2 1v3h6v-3H5z" />
              </svg>
              Save to Notes
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
