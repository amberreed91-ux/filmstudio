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
  enabled?: boolean
  autoRecover?: boolean
  onRecoveryComplete?: (result: RecoveryResponse) => void
  onRecoveryError?: (error: string) => void
}

const CONTRACT_ERROR_MARKERS = [
  'list_render_jobs',
  'list_reviews',
  'list_revisions',
  'list_packages',
  'list_all_projects',
]

export function isProductionRecoveryContractError(message: string): boolean {
  const lower = message.toLowerCase()
  return CONTRACT_ERROR_MARKERS.some((marker) => lower.includes(marker))
}

export function shouldAutoRecoverProductionBoard(input: {
  enabled: boolean
  projectId?: string
  autoRecover: boolean
  isRecovering: boolean
  status: RecoveryStatus
  pollingDisabled: boolean
}): boolean {
  if (!input.enabled) return false
  if (!input.projectId) return false
  if (input.pollingDisabled) return false
  if (!input.autoRecover) return false
  if (input.isRecovering) return false
  return input.status === 'idle'
}

export function useProductionRecovery(options: UseProductionRecoveryOptions = {}) {
  const {
    projectId,
    enabled = true,
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
  const pollingDisabledRef = useRef(false)

  const stopPolling = useCallback(() => {
    if (recoveryPollRef.current) {
      clearInterval(recoveryPollRef.current)
      recoveryPollRef.current = null
    }
  }, [])

  // Update recovery state safely
  const updateRecoveryState = useCallback((updates: Partial<RecoveryState>) => {
    if (isMountedRef.current) {
      setRecoveryState(prev => ({ ...prev, ...updates }))
    }
  }, [])

  // Poll recovery status
  const pollRecoveryStatus = useCallback(async () => {
    if (!enabled || !projectId || pollingDisabledRef.current) return
    try {
      const response = await fetch(`${STUDIO_API_BASE}/api/production-recovery/status`)
      if (!response.ok) {
        pollingDisabledRef.current = true
        stopPolling()
        updateRecoveryState({
          isRecovering: false,
          status: 'failed',
          message: 'Recovery unavailable',
          error: `Status endpoint unavailable (${response.status})`,
        })
        return
      }

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
        
        stopPolling()
      }
    } catch (error) {
      pollingDisabledRef.current = true
      stopPolling()
      const message = error instanceof Error ? error.message : 'Unknown polling error'
      updateRecoveryState({
        isRecovering: false,
        status: 'failed',
        message: 'Recovery unavailable',
        error: message,
      })
    }
  }, [enabled, projectId, recoveryState.isRecovering, stopPolling, updateRecoveryState])

  // Start recovery process
  const startRecovery = useCallback(async () => {
    if (!enabled) return
    if (!projectId) {
      updateRecoveryState({
        isRecovering: false,
        status: 'idle',
        message: '',
      })
      return
    }
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

      if (result.status === 'completed') {
        const combinedErrors = [
          result.error || '',
          JSON.stringify(result.jobs || {}),
          JSON.stringify(result.reviews || {}),
          JSON.stringify(result.revisions || {}),
          JSON.stringify(result.packages || {}),
          JSON.stringify(result.projects || {}),
        ].join(' ')
        if (isProductionRecoveryContractError(combinedErrors)) {
          pollingDisabledRef.current = true
          stopPolling()
          updateRecoveryState({
            isRecovering: false,
            status: 'failed',
            message: 'Recovery unavailable',
            error: 'Recovery backend contracts are unavailable in this runtime.',
          })
          onRecoveryError?.('Recovery backend contracts are unavailable in this runtime.')
          return
        }
      }
      
      if (result.status === 'started') {
        updateRecoveryState({
          status: 'recovering',
          message: 'Recovery in progress...'
        })
        
        // Start polling for status updates
        stopPolling()
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
    if (shouldAutoRecoverProductionBoard({
      enabled,
      projectId,
      autoRecover,
      isRecovering: recoveryState.isRecovering,
      status: recoveryState.status,
      pollingDisabled: pollingDisabledRef.current,
    })) {
      // Small delay to allow other components to load first
      const timer = setTimeout(() => {
        startRecovery()
      }, 1000)
      
      return () => clearTimeout(timer)
    }
  }, [autoRecover, enabled, projectId, recoveryState.isRecovering, recoveryState.status, startRecovery])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isMountedRef.current = false
      stopPolling()
    }
  }, [stopPolling])

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
