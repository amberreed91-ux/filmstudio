import { useCallback } from 'react'
import { useTransition } from '../lib/studioTransition'

export function useCut() {
  const cut = useTransition((s) => s.cut)
  return useCallback((path: string) => cut(path), [cut])
}