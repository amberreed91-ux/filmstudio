import { ChevronRight, Home } from 'lucide-react'
import { Link } from 'react-router-dom'

type BreadcrumbItem = {
  label: string
  to?: string
}

interface BreadcrumbsProps {
  items: BreadcrumbItem[]
}

export default function Breadcrumbs({ items }: BreadcrumbsProps) {
  return (
    <div
      className="flex items-center gap-2 px-6 py-2 text-xs"
      style={{ borderBottom: '1px solid var(--border)', background: 'rgba(255,255,255,0.02)' }}
    >
      <Link
        to="/studio"
        className="inline-flex items-center gap-1 no-underline"
        style={{ color: 'var(--text-muted)' }}
      >
        <Home size={12} />
        Home
      </Link>
      {items.map((item, index) => (
        <div key={`${item.label}-${index}`} className="flex items-center gap-2">
          <ChevronRight size={12} style={{ color: 'var(--text-muted)' }} />
          {item.to ? (
            <Link to={item.to} className="no-underline" style={{ color: 'var(--text-secondary)' }}>
              {item.label}
            </Link>
          ) : (
            <span style={{ color: 'var(--text-primary)' }}>{item.label}</span>
          )}
        </div>
      ))}
    </div>
  )
}
