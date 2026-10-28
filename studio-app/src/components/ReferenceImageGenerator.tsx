import { useMemo, useState } from 'react'
import { ArrowRight, Eye, ImagePlus, Loader2, Sparkles } from 'lucide-react'
import ReferenceBinderModal from './ReferenceBinderModal'
import {
  MAX_GENERATED_STILLS,
  PREVIS_ASPECT_RATIOS,
  resolveAssetUrl,
  type GeneratedPrevisImage,
  type PrevisAspectRatio,
  type PrevisImageMode,
} from '../lib/previsImageApi'
import { usePrevisImageGenerator } from '../hooks/usePrevisImageGenerator'

export type GeneratorTarget = { kind: PrevisImageMode; targetId: string; label: string }
export type GeneratorShot = { shotId: string; sceneId: string; sceneName: string }

type Props = {
  projectId: string
  /** The target the Bind action writes to. Null when nothing is selected. */
  target: GeneratorTarget | null
  /** Real shots recorded for this project, newest first. */
  shots: GeneratorShot[]
  /** Refresh the reference library after a successful bind. */
  onBound: () => void | Promise<void>
  /** True when the active target already holds a locked canonical reference. */
  hasLockedCanonical?: boolean
}

const MODE_LABEL: Record<PrevisImageMode, string> = {
  character: 'Character Generator',
  setting: 'Setting Generator',
}

const MODE_HINT: Record<PrevisImageMode, string> = {
  character: 'One subject, readable face and silhouette, plain ground.',
  setting: 'Environment only — spatial layout, materials, and set dressing.',
}

function stillSrc(image: GeneratedPrevisImage): string | null {
  return resolveAssetUrl(image.image_url)
}

/**
 * Dual-mode reference still generator.
 *
 * Presentation only: generation, preset vocabulary, and binding all live behind
 * the backend contract and `usePrevisImageGenerator`. A generated still is a
 * candidate the moment it binds — this panel never approves or canonicalises.
 */
export default function ReferenceImageGenerator({ projectId, target, shots, onBound, hasLockedCanonical = false }: Props) {
  // The active tab is derived: an explicit choice applies to the target it was
  // made against, so selecting another target follows that target's kind
  // instead of stranding the Bind action on the wrong tab.
  const [tabChoice, setTabChoice] = useState<{ kind: PrevisImageMode; targetKey: string } | null>(null)
  const targetKey = target ? `${target.kind}:${target.targetId}` : 'none'
  const mode: PrevisImageMode = tabChoice && tabChoice.targetKey === targetKey ? tabChoice.kind : (target?.kind ?? 'character')
  const [prompt, setPrompt] = useState('')
  const [aspectRatio, setAspectRatio] = useState<PrevisAspectRatio>('16:9')
  const [stylePreset, setStylePreset] = useState('none')
  const [lightingPreset, setLightingPreset] = useState('none')
  const [seedText, setSeedText] = useState('')
  const [shotBySignature, setShotBySignature] = useState<Record<string, string>>({})
  const [inspected, setInspected] = useState<GeneratedPrevisImage | null>(null)
  const generator = usePrevisImageGenerator(projectId)

  const seed = useMemo(() => {
    const trimmed = seedText.trim()
    if (!trimmed) return null
    const parsed = Number(trimmed)
    return Number.isInteger(parsed) && parsed >= 0 ? parsed : null
  }, [seedText])

  const seedInvalid = seedText.trim().length > 0 && seed === null
  const styleOptions = generator.presets?.style_presets || []
  const lightingOptions = generator.presets?.lighting_presets || []
  const maxPrompt = generator.presets?.max_prompt_chars || 1200
  const promptReady = prompt.trim().length >= 3
  const canGenerate = Boolean(projectId) && promptReady && !seedInvalid && !generator.generating
  // Binding writes to the selected target, and only when the tab matches it —
  // a setting still can never be bound to a character (or the reverse).
  const bindTarget = target && target.kind === mode ? { kind: target.kind, targetId: target.targetId } : null
  const shotOptions = shots.slice(0, 60)

  function shotValue(image: GeneratedPrevisImage): string {
    const signature = `${image.image_url}|${image.seed}`
    return shotBySignature[signature] ?? (shotOptions[0]?.shotId || '')
  }

  function chooseShot(image: GeneratedPrevisImage, shotId: string) {
    setShotBySignature((previous) => ({ ...previous, [`${image.image_url}|${image.seed}`]: shotId }))
  }

  async function handleBind(image: GeneratedPrevisImage) {
    const bound = await generator.bind(image, bindTarget, shotValue(image) || null)
    if (bound) await onBound()
  }

  async function handleModalConfirm(shotId: string | null) {
    if (!inspected) return
    const bound = await generator.bind(inspected, bindTarget, shotId)
    if (bound) {
      setInspected(null)
      await onBound()
    }
  }

  return (
    <section aria-label="Reference image generator" className="border-t border-white/10 pt-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <Sparkles size={15} className="text-amber-200" />
          Generate a reference
        </h2>
        <span className="text-[10px] uppercase tracking-[0.16em] text-zinc-500">One still per action · provider billed</span>
      </div>

      <div role="tablist" aria-label="Generator mode" className="mt-3 flex flex-wrap gap-2">
        {(['character', 'setting'] as const).map((option) => {
          const active = mode === option
          return (
            <button
              key={option}
              type="button"
              role="tab"
              aria-selected={active}
              id={`reference-generator-tab-${option}`}
              aria-controls="reference-generator-panel"
              onClick={() => setTabChoice({ kind: option, targetKey })}
              className={`min-h-10 rounded-md border px-3 text-xs font-medium transition-colors ${active ? 'border-amber-200/50 bg-amber-200/10 text-amber-100' : 'border-white/15 text-zinc-300 hover:border-white/30'}`}
            >
              {MODE_LABEL[option]}
            </button>
          )
        })}
      </div>

      <div id="reference-generator-panel" role="tabpanel" aria-labelledby={`reference-generator-tab-${mode}`} className="mt-3 space-y-3">
        <div>
          <label htmlFor="reference-generator-prompt" className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">
            {mode === 'character' ? 'Who is this person?' : 'Where does this scene live?'}
          </label>
          <textarea
            id="reference-generator-prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            rows={3}
            maxLength={maxPrompt}
            disabled={generator.generating}
            placeholder={mode === 'character'
              ? 'Maya, late 30s, weathered hands, hospital scrubs under a wool coat, close-cropped hair'
              : 'A rain-slick loading dock at night, corrugated shutters, sodium lamp, standing water'}
            className="mt-1 block w-full resize-y rounded-md border border-white/15 bg-black/30 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 disabled:opacity-40"
          />
          <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-500">
            <span>{MODE_HINT[mode]}</span>
            <span className="tabular-nums">{prompt.length}/{maxPrompt}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-4">
          <div>
            <p id="reference-generator-ratio-label" className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Aspect ratio</p>
            <div role="group" aria-labelledby="reference-generator-ratio-label" className="mt-1 flex gap-1">
              {PREVIS_ASPECT_RATIOS.map((ratio) => {
                const active = aspectRatio === ratio
                return (
                  <button
                    key={ratio}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setAspectRatio(ratio)}
                    disabled={generator.generating}
                    className={`min-h-9 min-w-14 rounded border px-2 text-xs tabular-nums transition-colors disabled:opacity-40 ${active ? 'border-amber-200/50 bg-amber-200/10 text-amber-100' : 'border-white/15 text-zinc-300 hover:border-white/30'}`}
                  >
                    {ratio}
                  </button>
                )
              })}
            </div>
          </div>

          <label className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">
            Style
            <select
              aria-label="Style preset"
              value={stylePreset}
              onChange={(event) => setStylePreset(event.target.value)}
              disabled={generator.generating || styleOptions.length === 0}
              className="mt-1 block min-h-9 min-w-40 rounded border border-white/15 bg-black/30 px-2 text-xs text-zinc-200 disabled:opacity-40"
            >
              {styleOptions.length === 0 ? <option value="none">Presets unavailable</option> : null}
              {styleOptions.map((preset) => <option key={preset.id} value={preset.id}>{preset.label}</option>)}
            </select>
          </label>

          <label className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">
            Lighting
            <select
              aria-label="Lighting preset"
              value={lightingPreset}
              onChange={(event) => setLightingPreset(event.target.value)}
              disabled={generator.generating || lightingOptions.length === 0}
              className="mt-1 block min-h-9 min-w-40 rounded border border-white/15 bg-black/30 px-2 text-xs text-zinc-200 disabled:opacity-40"
            >
              {lightingOptions.length === 0 ? <option value="none">Presets unavailable</option> : null}
              {lightingOptions.map((preset) => <option key={preset.id} value={preset.id}>{preset.label}</option>)}
            </select>
          </label>

          <label className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">
            Seed
            <input
              aria-label="Seed"
              type="number"
              min={0}
              max={2147483647}
              step={1}
              value={seedText}
              onChange={(event) => setSeedText(event.target.value)}
              placeholder="auto"
              disabled={generator.generating}
              aria-invalid={seedInvalid}
              className={`mt-1 block min-h-9 w-28 rounded border bg-black/30 px-2 text-xs tabular-nums text-zinc-200 placeholder:text-zinc-600 disabled:opacity-40 ${seedInvalid ? 'border-rose-400/60' : 'border-white/15'}`}
            />
          </label>

          <button
            type="button"
            onClick={() => void generator.generate({ mode, prompt, aspectRatio, stylePreset, lightingPreset, seed })}
            disabled={!canGenerate}
            aria-busy={generator.generating}
            className="inline-flex min-h-9 items-center gap-2 rounded-md border border-amber-200/40 bg-amber-200/10 px-3 text-xs font-medium text-amber-100 transition-colors hover:border-amber-200/60 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {generator.generating ? <Loader2 size={13} className="animate-spin" /> : <ImagePlus size={13} />}
            {generator.generating ? 'Generating still…' : 'Generate still'}
          </button>
        </div>

        {seedInvalid ? <p role="alert" className="text-xs text-rose-200">Seed must be a whole number between 0 and 2147483647, or empty to let the studio draw one.</p> : null}
        {generator.presetsError ? <p role="status" className="text-[11px] text-amber-200/90">{generator.presetsError} You can still generate from your prompt alone.</p> : null}
        {generator.error ? <p role="alert" className="rounded-md border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-200">{generator.error}</p> : null}
        {generator.notice && !generator.error ? <p role="status" className="rounded-md border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{generator.notice}</p> : null}
        {!bindTarget && target ? (
          <p role="status" className="text-[11px] text-zinc-500">
            This tab generates {mode} stills, but the selected target is a {target.kind}. Select a {mode} target in the left rail to bind results.
          </p>
        ) : null}
        {bindTarget && shotOptions.length === 0 ? (
          <p role="status" className="text-[11px] text-zinc-500">No shots are recorded for this project yet. Still results can be generated, but nothing can be bound to a shot until one exists.</p>
        ) : null}

        {generator.results.length === 0 ? (
          <p className="text-xs text-zinc-500">No stills generated in this session yet.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {generator.results.map((image) => {
              const src = stillSrc(image)
              const signature = `${image.image_url}|${image.seed}`
              return (
                <figure
                  key={signature}
                  data-testid="generated-reference-still"
                  className="overflow-hidden rounded-md border border-white/10 bg-white/[0.02]"
                >
                  {src ? (
                    <img
                      src={src}
                      alt={`Generated ${image.mode} reference`}
                      className={`w-full object-cover ${image.aspect_ratio === '9:16' ? 'aspect-[9/16]' : image.aspect_ratio === '1:1' ? 'aspect-square' : 'aspect-video'}`}
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex aspect-video items-center justify-center text-zinc-600"><ImagePlus size={18} /></div>
                  )}
                  <figcaption className="space-y-2 px-2 py-2">
                    <p className="flex flex-wrap gap-x-2 text-[10px] uppercase tracking-[0.1em] text-zinc-500">
                      <span>{image.aspect_ratio}</span>
                      <span>seed {image.seed}</span>
                      <span className="normal-case tracking-normal">{image.provider}</span>
                    </p>
                    <p className="line-clamp-2 text-xs leading-snug text-zinc-400">{image.prompt.split('\n')[0]}</p>
                    <label className="block text-[10px] uppercase tracking-[0.1em] text-zinc-500">
                      Shot
                      <select
                        aria-label={`Shot for generated still seed ${image.seed}`}
                        value={shotValue(image)}
                        onChange={(event) => chooseShot(image, event.target.value)}
                        disabled={generator.binding || shotOptions.length === 0}
                        className="mt-1 block w-full rounded border border-white/15 bg-black/30 px-2 py-1.5 font-mono text-[11px] text-zinc-200 disabled:opacity-40"
                      >
                        {shotOptions.length === 0 ? <option value="">No shots recorded</option> : null}
                        {shotOptions.map((shot) => (
                          <option key={shot.shotId} value={shot.shotId}>
                            {shot.sceneName} · {shot.shotId}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="flex gap-1.5">
                      <button
                        type="button"
                        onClick={() => setInspected(image)}
                        aria-label={`Inspect candidate seed ${image.seed}`}
                        className="inline-flex min-h-9 items-center justify-center gap-1 rounded border border-white/15 px-2.5 text-[11px] text-zinc-300 transition-colors hover:border-white/30"
                      >
                        <Eye size={12} />
                        Inspect
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleBind(image)}
                        disabled={!bindTarget || generator.binding || shotOptions.length === 0}
                        aria-busy={generator.binding}
                        className="inline-flex w-full min-h-9 flex-1 items-center justify-center gap-1.5 rounded border border-cyan-300/30 px-2 text-[11px] font-medium text-cyan-200 transition-colors hover:border-cyan-200/60 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {generator.binding ? <Loader2 size={12} className="animate-spin" /> : <ArrowRight size={12} />}
                        Bind to Shot Reference
                      </button>
                    </div>
                    <ReferenceBinderModal
                      image={inspected && inspected.image_url === image.image_url && inspected.seed === image.seed ? inspected : null}
                      targetLabel={target?.label || mode}
                      shots={shotOptions}
                      initialShotId={inspected ? shotValue(inspected) : ''}
                      hasLockedCanonical={hasLockedCanonical}
                      binding={generator.binding}
                      onClose={() => setInspected(null)}
                      onConfirm={(shotId) => void handleModalConfirm(shotId)}
                    />
                    <p className="text-xs leading-snug text-zinc-600">Binding registers a candidate with shot provenance. Approval stays explicit.</p>
                  </figcaption>
                </figure>
              )
            })}
          </div>
        )}
        {generator.results.length >= MAX_GENERATED_STILLS ? <p className="text-xs text-zinc-500">Showing the {MAX_GENERATED_STILLS} most recent stills from this session.</p> : null}
      </div>
    </section>
  )
}
