import { useCallback, useEffect, useRef, useState } from 'react'

type AsyncActionOptions = {
  preventConcurrent?: boolean
}

export function useAsyncAction<TArgs extends unknown[], TResult>(
  fn: (...args: TArgs) => Promise<TResult>,
  options: AsyncActionOptions = {},
) {
  const { preventConcurrent = true } = options
  const mountedRef = useRef(true)
  const runningRef = useRef(false)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    return () => {
      mountedRef.current = false
    }
  }, [])

  const run = useCallback(async (...args: TArgs) => {
    if (preventConcurrent && runningRef.current) return undefined as TResult | undefined
    runningRef.current = true
    if (mountedRef.current) {
      setIsRunning(true)
      setError(null)
    }
    try {
      const result = await fn(...args)
      return result
    } catch (err) {
      const normalized = err instanceof Error ? err : new Error(String(err))
      if (mountedRef.current) setError(normalized)
      throw normalized
    } finally {
      runningRef.current = false
      if (mountedRef.current) setIsRunning(false)
    }
  }, [fn, preventConcurrent])

  const reset = useCallback(() => {
    if (!mountedRef.current) return
    setError(null)
  }, [])

  return { run, isRunning, error, reset }
}
