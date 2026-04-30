import type { ReactNode } from 'react'

interface StudioPanelProps {
  title: string
  subtitle?: string
  action?: ReactNode
  children: ReactNode
  className?: string
  'data-testid'?: string
}

export default function StudioPanel({ title, subtitle, action, children, className, 'data-testid': testid }: StudioPanelProps) {
  return (
    <section
      className={`rounded-2xl p-4 ${className || ''}`}
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
      data-testid={testid}
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</h2>
          {subtitle && (
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{subtitle}</p>
          )}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}
