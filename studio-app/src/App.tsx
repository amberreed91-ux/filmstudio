import { Component, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { CinematicCut } from './components/CinematicCut'
import { StudioProvider } from './context/StudioContext'
import { RenderActivityProvider } from './context/RenderActivityContext'
import { AudioUXProvider } from './context/AudioUXContext'
import { APP_ROUTES } from './routes'
import NotFound from './pages/NotFound'
import StudioLayout from './components/StudioLayout'
import { disableStudioDevMode, enableStudioDevMode } from './lib/devMode'
import './index.css'

declare global {
  interface Window {
    enableStudioDevMode?: () => void
    disableStudioDevMode?: () => void
  }
}

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

const queryClient = new QueryClient()

export default function App() {
  if (typeof window !== 'undefined') {
    window.enableStudioDevMode = enableStudioDevMode
    window.disableStudioDevMode = disableStudioDevMode
  }
  
  return (
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <StudioProvider>
          <AudioUXProvider>
            <RenderActivityProvider>
              <BrowserRouter>
                <CinematicCut />
                <StudioLayout>
                  <StudioRoutes />
                </StudioLayout>
              </BrowserRouter>
            </RenderActivityProvider>
          </AudioUXProvider>
        </StudioProvider>
      </QueryClientProvider>
    </AppErrorBoundary>
  )
}

function StudioRoutes() {
  const location = useLocation()

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        {APP_ROUTES.map((route) => (
          <Route key={route.path} path={route.path} element={
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.2 }}
            >
              {route.element}
            </motion.div>
          } />
        ))}
        <Route path="*" element={
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.2 }}
          >
            <NotFound />
          </motion.div>
        } />
      </Routes>
    </AnimatePresence>
  )
}
