import { useState, useEffect, useCallback, useRef } from 'react'
import { STUDIO_API_BASE } from '../lib/studioApi'

type RecoveryStatus = 'idle' | 'hydrating' | 'reconnecting' | 'recovering' | 'completed' | 'failed'

interface RecoveryState {
  isRecovering: boolean
  status: RecoveryStatus
  progress: number
  message: string
  error?: string
  recoveredJobs: string[]
  recoveredReviews: string[]
  recoveredRevisions: string[]
  recoveredPackages: string[]
  totalRecovered: number
}

interface RecoveryResponse {
  status: string
  start_time?: string
  end_time?: string
  duration_seconds?: number
  project_id?: string
  jobs: Record<string, number>
  reviews: Record<string, number>
  revisions: Record<string, number>
  packages: Record<string, number>
  projects: Record<string, number>
  error?: string
}

interface UseProductionRecoveryOptions {
  projectId?: string
  autoRecover?: boolean
  onRecoveryComplete?: (result: RecoveryResponse) => void
  onRecoveryError?: (error: string) => void
}

export function useProductionRecovery(options: UseProductionRecoveryOptions = {}) {
  const {
    projectId,
    autoRecover = true,
    onRecoveryComplete,
    onRecoveryError
  } = options

  const [recoveryState, setRecoveryState] = useState<RecoveryState>({
    isRecovering: false,
    status: 'idle',
    progress: 0,
    message: '',
    recoveredJobs: [],
    recoveredReviews: [],
    recoveredRevisions: [],
    recoveredPackages: [],
    totalRecovered: 0
  })

  const recoveryPollRef = useRef<NodeJS.Timeout | null>(null)
  const isMountedRef = useRef(true)

  // Update recovery state safely
  const updateRecoveryState = useCallback((updates: Partial<RecoveryState>) => {
    if (isMountedRef.current) {
      setRecoveryState(prev => ({ ...prev, ...updates }))
    }
  }, [])

  // Poll recovery status
  const pollRecoveryStatus = useCallback(async () => {
    try {
      const response = await fetch(`${STUDIO_API_BASE}/api/production-recovery/status`)
      if (!response.ok) return

      const status = await response.json()
      
      updateRecoveryState({
        isRecovering: status.is_recovering,
        recoveredJobs: status.recovered_jobs || [],
        recoveredReviews: status.recovered_reviews || [],
        recoveredRevisions: status.recovered_revisions || [],
        recoveredPackages: status.recovered_packages || [],
        totalRecovered: status.total_recovered || 0
      })

      // If recovery is complete, stop polling
      if (!status.is_recovering && recoveryState.isRecovering) {
        updateRecoveryState({ 
          status: 'completed',
          message: 'Recovery completed successfully',
          progress: 100
        })
        
        if (recoveryPollRef.current) {
          clearInterval(recoveryPollRef.current)
          recoveryPollRef.current = null
        }
      }
    } catch (error) {
      console.error('Failed to poll recovery status:', error)
    }
  }, [recoveryState.isRecovering, updateRecoveryState])

  // Start recovery process
  const startRecovery = useCallback(async () => {
    if (recoveryState.isRecovering) {
      console.warn('Recovery already in progress')
      return
    }

    updateRecoveryState({
      isRecovering: true,
      status: 'hydrating',
      progress: 0,
      message: 'Starting production board recovery...'
    })

    try {
      const response = await fetch(`${STUDIO_API_BASE}/api/production-recovery/recover${projectId ? `?project_id=${projectId}` : ''}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        }
      })

      if (!response.ok) {
        throw new Error(`Recovery request failed: ${response.status}`)
      }

      const result: RecoveryResponse = await response.json()
      
      if (result.status === 'started') {
        updateRecoveryState({
          status: 'recovering',
          message: 'Recovery in progress...'
        })
        
        // Start polling for status updates
        if (recoveryPollRef.current) {
          clearInterval(recoveryPollRef.current)
        }
        recoveryPollRef.current = setInterval(pollRecoveryStatus, 2000)
        
      } else if (result.status === 'completed') {
        updateRecoveryState({
          isRecovering: false,
          status: 'completed',
          progress: 100,
          message: 'Recovery completed successfully',
          recoveredJobs: [],
          recoveredReviews: [],
          recoveredRevisions: [],
          recoveredPackages: [],
          totalRecovered: 0
        })
        onRecoveryComplete?.(result)
        
      } else if (result.status === 'failed') {
        updateRecoveryState({
          isRecovering: false,
          status: 'failed',
          message: 'Recovery failed',
          error: result.error
        })
        onRecoveryError?.(result.error || 'Unknown recovery error')
      }

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      updateRecoveryState({
        isRecovering: false,
        status: 'failed',
        message: 'Recovery failed',
        error: errorMessage
      })
      onRecoveryError?.(errorMessage)
    }
  }, [projectId, recoveryState.isRecovering, updateRecoveryState, pollRecoveryStatus, onRecoveryComplete, onRecoveryError])

  // Safe refresh function
  const safeRefresh = useCallback(async () => {
    updateRecoveryState({
      status: 'reconnecting',
      progress: 0,
      message: 'Refreshing production board...'
    })

    try {
      // Start recovery to refresh data
      await startRecovery()
    } catch (error) {
      updateRecoveryState({
        status: 'failed',
        message: 'Refresh failed',
        error: error instanceof Error ? error.message : 'Unknown error'
      })
    }
  }, [startRecovery, updateRecoveryState])

  // Reset recovery state
  const resetRecovery = useCallback(() => {
    updateRecoveryState({
      isRecovering: false,
      status: 'idle',
      progress: 0,
      message: '',
      error: undefined,
      recoveredJobs: [],
      recoveredReviews: [],
      recoveredRevisions: [],
      recoveredPackages: [],
      totalRecovered: 0
    })
  }, [updateRecoveryState])

  // Auto-recover on mount if enabled
  useEffect(() => {
    if (autoRecover && !recoveryState.isRecovering && recoveryState.status === 'idle') {
      // Small delay to allow other components to load first
      const timer = setTimeout(() => {
        startRecovery()
      }, 1000)
      
      return () => clearTimeout(timer)
    }
  }, [autoRecover, recoveryState.isRecovering, recoveryState.status, startRecovery])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isMountedRef.current = false
      if (recoveryPollRef.current) {
        clearInterval(recoveryPollRef.current)
        recoveryPollRef.current = null
      }
    }
  }, [])

  return {
    recoveryState,
    startRecovery,
    safeRefresh,
    resetRecovery,
    isRecovering: recoveryState.isRecovering,
    recoveryStatus: recoveryState.status,
    recoveryMessage: recoveryState.message,
    recoveryError: recoveryState.error,
    recoveredItems: {
      jobs: recoveryState.recoveredJobs.length,
      reviews: recoveryState.recoveredReviews.length,
      revisions: recoveryState.recoveredRevisions.length,
      packages: recoveryState.recoveredPackages.length,
      total: recoveryState.totalRecovered
    }
  }
}
