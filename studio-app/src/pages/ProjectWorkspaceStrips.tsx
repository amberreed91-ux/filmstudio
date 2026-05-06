import { getProductionSignalSeverity } from './ProjectWorkspaceSignals'

export function ProductionSignalStrip({ message }: { message: string }) {
  const severity = getProductionSignalSeverity(message)
  const borderColor =
    severity === 'warning'
      ? 'color-mix(in srgb, var(--accent-blue) 22%, var(--border))'
      : severity === 'degraded'
        ? 'color-mix(in srgb, var(--text-primary) 24%, var(--border))'
        : 'var(--border)'
  const messageColor =
    severity === 'warning'
      ? 'color-mix(in srgb, var(--accent-blue) 60%, var(--text-secondary))'
      : severity === 'degraded'
        ? 'color-mix(in srgb, var(--text-primary) 78%, var(--text-secondary))'
        : 'var(--text-secondary)'
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: `1px solid ${borderColor}` }}
      data-testid="production-signal-strip"
      data-severity={severity}
    >
      <span style={{ color: 'var(--text-muted)' }}>Production Signal</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: messageColor }}>{message}</span>
    </div>
  )
}

export function IntentSignalStrip({ label }: { label: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="intent-signal-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>Intent</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
    </div>
  )
}

export function ReviewStateStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="review-state-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>Review State</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function MemoryVisibilityStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="memory-visibility-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>Memory Visibility</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function MemorySnapshotStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="memory-snapshot-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>Memory Snapshot</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function ShotPlanStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="shot-plan-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>Shot Plan</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function VisualBoardStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="visual-board-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>Visual Board</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function PrevisStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="previs-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function ProviderStatusStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="provider-status-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function ExecutionStatusStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="execution-status-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function ValidationStatusStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="validation-status-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function ShotPipelineStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="shot-pipeline-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function TakePipelineStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="take-pipeline-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function RenderStatusStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="render-status-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function SceneStatusStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="scene-status-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

