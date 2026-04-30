import { AlertTriangle } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

export default function NotFound() {
  const location = useLocation()

  return (
    <div className="flex min-h-screen items-center justify-center px-6" style={{ background: 'var(--bg-deep)' }}>
      <div
        className="max-w-xl w-full rounded-2xl p-8 text-center"
        style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      >
        <div className="mx-auto mb-4 w-12 h-12 rounded-full flex items-center justify-center" style={{ background: 'rgba(249,115,22,0.12)' }}>
          <AlertTriangle size={22} style={{ color: 'var(--accent-orange)' }} />
        </div>
        <h1 className="text-2xl font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          Page not found
        </h1>
        <p className="text-sm mb-6" style={{ color: 'var(--text-secondary)' }}>
          The route <span style={{ color: 'var(--text-primary)' }}>{location.pathname}</span> is not part of the current studio navigation map.
        </p>
        <div className="flex items-center justify-center gap-3">
          <Link to="/studio" className="btn-primary no-underline">
            Go to Studio Home
          </Link>
          <Link to="/studio/dashboard" className="btn-ghost no-underline">
            Open Dashboard
          </Link>
        </div>
      </div>
    </div>
  )
}
