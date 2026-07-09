import { Component, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
  errorInfo: { componentStack?: string } | null
}

export default class ProductionBoardErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: { componentStack?: string }) {
    console.error('[ProductionBoardErrorBoundary] Caught error:', error, errorInfo)
    this.setState({ errorInfo })
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null })
    window.location.reload()
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-black px-4 py-8">
          <div className="mx-auto max-w-2xl">
            <div className="rounded-2xl border border-rose-500/50 bg-rose-950/30 p-8 shadow-2xl">
              <div className="flex items-start gap-4">
                <div className="rounded-full bg-rose-500/20 p-3">
                  <AlertTriangle className="h-8 w-8 text-rose-400" />
                </div>
                <div className="flex-1">
                  <h1 className="text-2xl font-bold text-zinc-100">
                    Production Board Error
                  </h1>
                  <p className="mt-2 text-sm text-zinc-300">
                    The Production Board encountered an unexpected error and couldn't render.
                  </p>

                  {this.state.error && (
                    <div className="mt-4 rounded-lg border border-zinc-700/50 bg-zinc-900/50 p-4">
                      <div className="text-xs font-semibold uppercase tracking-wider text-rose-300">
                        Error Details
                      </div>
                      <div className="mt-2 font-mono text-sm text-zinc-400">
                        {this.state.error.message}
                      </div>
                      {this.state.errorInfo?.componentStack && (
                        <details className="mt-3">
                          <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-400">
                            Show component stack
                          </summary>
                          <pre className="mt-2 overflow-x-auto text-xs text-zinc-600">
                            {this.state.errorInfo.componentStack}
                          </pre>
                        </details>
                      )}
                    </div>
                  )}

                  <div className="mt-6 flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={this.handleRetry}
                      className="flex items-center gap-2 rounded-lg border border-cyan-400/45 bg-cyan-500/14 px-4 py-2 text-sm font-semibold uppercase tracking-wider text-cyan-100 transition-colors hover:bg-cyan-500/20"
                    >
                      <RefreshCw className="h-4 w-4" />
                      Try Again
                    </button>
                    <button
                      type="button"
                      onClick={this.handleReset}
                      className="flex items-center gap-2 rounded-lg border border-zinc-600/45 bg-zinc-700/20 px-4 py-2 text-sm font-semibold uppercase tracking-wider text-zinc-100 transition-colors hover:bg-zinc-700/30"
                    >
                      Reload Page
                    </button>
                    <a
                      href="/studio/previs"
                      className="flex items-center gap-2 rounded-lg border border-zinc-600/45 bg-zinc-700/20 px-4 py-2 text-sm font-semibold uppercase tracking-wider text-zinc-100 no-underline transition-colors hover:bg-zinc-700/30"
                    >
                      Go to Previs
                    </a>
                  </div>

                  <div className="mt-6 rounded-lg border border-amber-500/30 bg-amber-950/20 px-4 py-3">
                    <div className="text-xs font-semibold uppercase tracking-wider text-amber-300">
                      Recovery Steps
                    </div>
                    <ul className="mt-2 space-y-1 text-sm text-zinc-400">
                      <li>• Click "Try Again" to re-render without reloading</li>
                      <li>• Click "Reload Page" for a full refresh</li>
                      <li>• Go to Previs to continue working on scenes</li>
                      <li>• If the error persists, check the browser console</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
