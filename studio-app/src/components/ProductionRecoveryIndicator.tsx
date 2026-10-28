import { Loader2, RefreshCw, CheckCircle, AlertCircle, XCircle } from 'lucide-react'

interface ProductionRecoveryIndicatorProps {
  isRecovering: boolean
  recoveryStatus: string
  recoveryMessage: string
  recoveryError?: string
  recoveredItems: {
    jobs: number
    reviews: number
    revisions: number
    packages: number
    total: number
  }
  onSafeRefresh?: () => void
  onDismiss?: () => void
}

export default function ProductionRecoveryIndicator({
  isRecovering,
  recoveryStatus,
  recoveryMessage,
  recoveryError,
  recoveredItems,
  onSafeRefresh,
  onDismiss
}: ProductionRecoveryIndicatorProps) {
  const getStatusIcon = () => {
    switch (recoveryStatus) {
      case 'hydrating':
      case 'reconnecting':
      case 'recovering':
        return <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-green-400" />
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-400" />
      default:
        return <AlertCircle className="w-4 h-4 text-yellow-400" />
    }
  }

  const getStatusColor = () => {
    switch (recoveryStatus) {
      case 'hydrating':
      case 'reconnecting':
      case 'recovering':
        return 'bg-blue-500/20 border-blue-500/50 text-blue-300'
      case 'completed':
        return 'bg-green-500/20 border-green-500/50 text-green-300'
      case 'failed':
        return 'bg-red-500/20 border-red-500/50 text-red-300'
      default:
        return 'bg-zinc-800/50 border-zinc-700/50 text-zinc-300'
    }
  }

  // Don't show anything when idle
  if (recoveryStatus === 'idle' && !isRecovering) {
    return null
  }

  return (
    <div className={`studio-surface p-4 mb-4 border ${getStatusColor()}`}>
      <div className="flex items-start justify-between">
        <div className="flex items-start space-x-3">
          <div className="mt-1">
            {getStatusIcon()}
          </div>
          <div className="flex-1">
            <div className="flex items-center space-x-2">
              <h4 className="font-medium">
                {recoveryStatus === 'hydrating' && 'Hydrating Production Board...'}
                {recoveryStatus === 'reconnecting' && 'Refreshing Production Board...'}
                {recoveryStatus === 'recovering' && 'Recovering Production Board...'}
                {recoveryStatus === 'completed' && 'Production Board Ready'}
                {recoveryStatus === 'failed' && 'Recovery Failed'}
              </h4>
              {onSafeRefresh && !isRecovering && (
                <button type="button"
                  onClick={onSafeRefresh}
                  className="text-zinc-400 hover:text-zinc-300 transition-colors"
                  title="Safe Refresh"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              )}
            </div>
            
            <p className="text-sm mt-1 opacity-80">
              {recoveryMessage}
            </p>

            {recoveryError && (
              <div className="mt-2 text-sm text-red-400">
                Error: {recoveryError}
              </div>
            )}

            {/* Recovery progress */}
            {(isRecovering || recoveredItems.total > 0) && (
              <div className="mt-3 space-y-2">
                {recoveredItems.total > 0 && (
                  <div className="text-xs space-y-1">
                    <div>Recovered: {recoveredItems.total} items</div>
                    <div className="grid grid-cols-2 gap-2 text-zinc-400">
                      <div>• Jobs: {recoveredItems.jobs}</div>
                      <div>• Reviews: {recoveredItems.reviews}</div>
                      <div>• Revisions: {recoveredItems.revisions}</div>
                      <div>• Packages: {recoveredItems.packages}</div>
                    </div>
                  </div>
                )}

                {isRecovering && (
                  <div className="flex items-center space-x-2">
                    <div className="flex-1 bg-zinc-700/50 rounded-full h-1.5">
                      <div 
                        className="bg-blue-400 h-1.5 rounded-full transition-all duration-300"
                        style={{ width: '60%' }}
                      />
                    </div>
                    <span className="text-xs text-zinc-400">Recovering...</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {onDismiss && (
          <button type="button"
            onClick={onDismiss}
            className="text-zinc-400 hover:text-zinc-300 transition-colors"
          >
            ×
          </button>
        )}
      </div>
    </div>
  )
}
