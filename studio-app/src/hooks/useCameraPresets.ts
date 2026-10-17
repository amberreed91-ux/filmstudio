import { useEffect, useState } from 'react'
import { getCameraPresets, type CameraPresetCatalog } from '../lib/cameraPresetApi'

export function useCameraPresets() {
  const [catalog, setCatalog] = useState<CameraPresetCatalog | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    void getCameraPresets(controller.signal).then((data) => {
      if (!controller.signal.aborted) setCatalog(data)
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Camera presets could not be loaded.')
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [attempt])
  return { catalog, error, loading, retry: () => { setLoading(true); setError(''); setAttempt((value) => value + 1) } }
}
