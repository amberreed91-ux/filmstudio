import { useCallback, useEffect, useRef, useState } from 'react'
import {
  bindGeneratedStillToShot,
  generatePrevisImage,
  getPrevisImagePresets,
  MAX_GENERATED_STILLS,
  type GeneratedPrevisImage,
  type PrevisAspectRatio,
  type PrevisImageMode,
  type PrevisImagePresets,
} from '../lib/previsImageApi'
import type { ReferenceAsset } from '../lib/visualTrainingApi'

/**
 * Reference Space generation state.
 *
 * Keep the rules that matter: one project's results never appear under another
 * project, a second generation cannot start while one is in flight, and a
 * failed generation leaves no result behind — the creator retries deliberately.
 * Binding is the only registry write and it only ever creates a candidate.
 */

type GeneratorScope = { projectId: string; generation: number; mounted: boolean }

export type GenerateInput = {
  mode: PrevisImageMode
  prompt: string
  aspectRatio: PrevisAspectRatio
  stylePreset: string
  lightingPreset: string
  seed: number | null
}

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim() ? error.message.trim() : fallback
}

export function usePrevisImageGenerator(projectId: string) {
  const [presets, setPresets] = useState<PrevisImagePresets | null>(null)
  const [presetsError, setPresetsError] = useState('')
  const [results, setResults] = useState<GeneratedPrevisImage[]>([])
  const [generating, setGenerating] = useState(false)
  const [binding, setBinding] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const scope = useRef<GeneratorScope>({ projectId, generation: 0, mounted: true })
  const inFlight = useRef(false)

  useEffect(() => {
    scope.current = { projectId, generation: scope.current.generation + 1, mounted: true }
    inFlight.current = false
    setResults([])
    setError('')
    setNotice('')
    setGenerating(false)
    setBinding(false)
    return () => {
      scope.current.mounted = false
      scope.current.generation += 1
    }
  }, [projectId])

  useEffect(() => {
    if (!projectId) return
    const operation = scope.current
    let cancelled = false
    setPresetsError('')
    getPrevisImagePresets()
      .then((catalogue) => {
        if (cancelled || scope.current !== operation) return
        setPresets(catalogue)
      })
      .catch((cause: unknown) => {
        if (cancelled || scope.current !== operation) return
        // Fail closed: without the backend's vocabulary there is nothing to
        // validate a request against, so the panel explains rather than guesses.
        setPresetsError(messageOf(cause, 'Style and lighting presets are unavailable right now.'))
      })
    return () => { cancelled = true }
  }, [projectId])

  const generate = useCallback(async (input: GenerateInput): Promise<GeneratedPrevisImage | null> => {
    if (!projectId || inFlight.current) return null
    const operation = scope.current
    inFlight.current = true
    setGenerating(true)
    setError('')
    setNotice('')
    try {
      const image = await generatePrevisImage({
        project_id: projectId,
        mode: input.mode,
        prompt: input.prompt,
        aspect_ratio: input.aspectRatio,
        style_preset: input.stylePreset,
        lighting_preset: input.lightingPreset,
        seed: input.seed,
      })
      if (scope.current !== operation || !scope.current.mounted) return null
      setResults((previous) => [image, ...previous].slice(0, MAX_GENERATED_STILLS))
      setNotice(`Still generated · seed ${image.seed}. Bind it to a shot when it earns its place.`)
      return image
    } catch (cause) {
      if (scope.current === operation && scope.current.mounted) {
        setError(messageOf(cause, 'The still could not be generated. Nothing was saved.'))
      }
      return null
    } finally {
      if (scope.current === operation && scope.current.mounted) {
        inFlight.current = false
        setGenerating(false)
      }
    }
  }, [projectId])

  const bind = useCallback(async (
    image: GeneratedPrevisImage,
    target: { kind: PrevisImageMode; targetId: string } | null,
    shotId: string | null,
  ): Promise<ReferenceAsset | null> => {
    if (!projectId || !target || binding) return null
    const operation = scope.current
    setBinding(true)
    setError('')
    setNotice('')
    try {
      const asset = await bindGeneratedStillToShot(projectId, target, image, shotId)
      if (scope.current !== operation || !scope.current.mounted) return null
      setNotice(
        shotId
          ? `Bound to shot ${shotId} as a candidate. Approve it in the library before generation can use it.`
          : 'Added to this target as a candidate. Approve it in the library before generation can use it.',
      )
      return asset
    } catch (cause) {
      if (scope.current === operation && scope.current.mounted) {
        setError(messageOf(cause, 'The still could not be bound. The library was not modified.'))
      }
      return null
    } finally {
      if (scope.current === operation && scope.current.mounted) setBinding(false)
    }
  }, [projectId, binding])

  return {
    presets,
    presetsError,
    results,
    generating,
    binding,
    error,
    notice,
    generate,
    bind,
  }
}

export type PrevisImageGeneratorController = ReturnType<typeof usePrevisImageGenerator>
