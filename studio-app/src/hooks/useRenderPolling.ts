import { useCallback, useEffect, useRef } from 'react'

type UseRenderPollingOptions<TJob> = {
  isTerminal: (job: TJob) => boolean
  getStatus: (jobId: string) => Promise<TJob>
  intervalMs?: number
  timeoutMs?: number
  adaptive?: boolean
}

export function useRenderPolling<TJob>(options: UseRenderPollingOptions<TJob>) {
  const { 
    isTerminal, 
    getStatus, 
    intervalMs = 5000, 
    timeoutMs = 10 * 60 * 1000,
    adaptive = true 
  } = options
  const mountedRef = useRef(true)
  const activeJobsRef = useRef<Set<string>>(new Set())
  const jobIntervalsRef = useRef<Map<string, number>>(new Map())

  const getAdaptiveInterval = useCallback((elapsedMs: number, job: TJob): number => {
    if (!adaptive) return intervalMs
    
    // Extract status from job - handle different job types
    const jobStatus = (job as any).status || 'unknown'
    
    // Adaptive polling based on job status and elapsed time
    if (jobStatus === 'queued' || jobStatus === 'preparing') {
      // Fast polling for queued/preparing jobs (2s)
      return 2000
    } else if (jobStatus === 'generating') {
      // Moderate polling for generating jobs, slower over time
      if (elapsedMs < 30000) return 3000 // First 30s: 3s
      if (elapsedMs < 120000) return 5000 // Next 2min: 5s
      return 8000 // After 2min: 8s
    } else if (jobStatus === 'polling') {
      // Slower polling for polling jobs
      return 6000
    }
    
    return intervalMs
  }, [adaptive, intervalMs])

  const pollUntilTerminal = useCallback(
    async (jobId: string): Promise<TJob | undefined> => {
      if (!mountedRef.current) return undefined
      activeJobsRef.current.add(jobId)

      try {
        let current = await getStatus(jobId)
        const startTime = Date.now()
        let lastPollTime = startTime

        while (!isTerminal(current)) {
          if (!mountedRef.current) break
          if (Date.now() - startTime > timeoutMs) break
          
          const elapsedMs = Date.now() - startTime
          const adaptiveInterval = getAdaptiveInterval(elapsedMs, current)
          
          const timeSinceLastPoll = Date.now() - lastPollTime
          const delay = Math.max(0, adaptiveInterval - timeSinceLastPoll)
          
          await new Promise((resolve) => setTimeout(resolve, delay))
          if (!mountedRef.current) break
          
          current = await getStatus(jobId)
          lastPollTime = Date.now()
        }

        return current
      } finally {
        if (mountedRef.current) {
          activeJobsRef.current.delete(jobId)
          jobIntervalsRef.current.delete(jobId)
        }
      }
    },
    [isTerminal, getStatus, intervalMs, timeoutMs, getAdaptiveInterval]
  )

  const stopPolling = useCallback((jobId: string) => {
    activeJobsRef.current.delete(jobId)
    jobIntervalsRef.current.delete(jobId)
  }, [])

  useEffect(() => {
    return () => {
      mountedRef.current = false
      activeJobsRef.current.clear()
      jobIntervalsRef.current.clear()
    }
  }, [])

  return { pollUntilTerminal, stopPolling, activeJobs: activeJobsRef.current }
}
