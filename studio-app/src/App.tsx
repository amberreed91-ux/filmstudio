import { Component, type ReactNode } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { StudioProvider } from './context/StudioContext'
import { APP_ROUTES } from './routes'
import NotFound from './pages/NotFound'
import './index.css'

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

class AppErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch() {
    // Error handled in render - no action needed
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center h-screen" style={{ background: 'var(--bg-deep)' }}>
          <div className="max-w-md text-center p-8 rounded-2xl" style={{ background: 'var(--bg-card)', border: '1px solid rgba(239,68,68,0.3)' }}>
            <div className="text-lg font-semibold mb-2" style={{ color: '#ef4444' }}>
              Something went wrong
            </div>
            <div className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
              {this.state.error?.message || 'An unexpected error occurred in the application.'}
            </div>
            <button
              className="text-sm px-4 py-2 rounded-lg cursor-pointer"
              style={{ background: 'rgba(0,200,255,0.15)', color: 'var(--accent-cyan)', border: '1px solid rgba(0,200,255,0.3)' }}
              onClick={() => window.location.reload()}
            >
              Reload Studio
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export default function App() {
  return (
    <AppErrorBoundary>
      <StudioProvider>
        <BrowserRouter>
          <Routes>
            {APP_ROUTES.map((route) => (
              <Route key={route.path} path={route.path} element={route.element} />
            ))}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </StudioProvider>
    </AppErrorBoundary>
  )
}
