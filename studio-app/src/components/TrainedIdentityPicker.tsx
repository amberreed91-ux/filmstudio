import { Check, Sparkles } from 'lucide-react'
import type { Scene } from '../lib/studioApi'
import type { VisualTrainingJob } from '../lib/visualTrainingApi'
import { useAvailableIdentities } from '../hooks/useAvailableIdentities'

/**
 * Opt-in selector for trained visual identities at render time.
 *
 * Rendering is backward compatible: nothing is injected unless the filmmaker
 * explicitly chooses an identity here. Selecting one sets a single
 * `visual_model_id` for the next take (the render pipeline applies at most one
 * trained reference per job); choosing "No trained identity" clears it and
 * leaves the existing render path untouched.
 */
export interface TrainedIdentityPickerProps {
  projectId: string
  scene: Scene | null
  selectedModelId: string | null
  onSelect: (modelId: string | null) => void
  disabled?: boolean
  /** Bump to force a refetch after a sibling trains a new identity in-session. */
  refreshKey?: number
}

function IdentityRow({
  model,
  label,
  selected,
  disabled,
  onChoose,
}: {
  model: VisualTrainingJob
  label: string
  selected: boolean
  disabled: boolean
  onChoose: () => void
}) {
  return (
    <button
      type="button"
      onClick={onChoose}
      disabled={disabled}
      aria-pressed={selected}
      className={`flex w-full items-center justify-between gap-3 rounded border px-3 py-2 text-left transition-colors disabled:opacity-40 ${
        selected ? 'border-amber-200/60 bg-amber-200/10' : 'border-white/10 bg-black/20 hover:border-white/30'
      }`}
    >
      <span className="min-w-0">
        <span className="block truncate font-mono text-xs text-zinc-100">{model.trigger_word}</span>
        <span className="mt-0.5 block truncate text-[11px] text-zinc-400">{label} · {model.provider}</span>
      </span>
      <span className={`inline-flex shrink-0 items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] ${selected ? 'border-amber-200/50 bg-amber-200/15 text-amber-100' : 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200'}`}>
        {selected ? <><Check size={11} />In use</> : <>Ready · Use</>}
      </span>
    </button>
  )
}

export default function TrainedIdentityPicker({
  projectId,
  scene,
  selectedModelId,
  onSelect,
  disabled,
  refreshKey,
}: TrainedIdentityPickerProps) {
  const { characterIdentities, settingIdentities, loading, error } = useAvailableIdentities(projectId, refreshKey)

  // Setting identities relevant to this scene first (exact canonical match),
  // then any project character identities the filmmaker may opt into.
  const sceneId = scene?.scene_id
  const relevantSettings = settingIdentities.filter(
    (m) => !sceneId || m.configuration?.canonical_target_id === sceneId,
  )
  const hasAny = relevantSettings.length > 0 || characterIdentities.length > 0

  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-3" data-testid="trained-identity-picker">
      <div className="flex items-center gap-2">
        <Sparkles size={14} className="text-amber-200" />
        <p className="text-xs font-medium text-zinc-200">Trained visual identities</p>
      </div>
      <p className="mt-1 text-[11px] leading-relaxed text-zinc-500">
        Opt in per take. Choosing an identity attaches that reusable look to the next render; nothing changes unless you pick one.
      </p>

      {loading ? (
        <p className="mt-2 text-[11px] text-zinc-400">Loading identities…</p>
      ) : error ? (
        <p className="mt-2 text-[11px] text-zinc-400">{error}</p>
      ) : !hasAny ? (
        <p className="mt-2 text-[11px] leading-relaxed text-zinc-500" data-testid="trained-identity-none">
          No trained identities yet. Train a character look or this setting to reuse a consistent visual identity here.
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          <button
            type="button"
            onClick={() => onSelect(null)}
            disabled={disabled}
            aria-pressed={selectedModelId === null}
            className={`flex w-full items-center justify-between gap-3 rounded border px-3 py-2 text-left transition-colors disabled:opacity-40 ${
              selectedModelId === null ? 'border-white/30 bg-white/5' : 'border-white/10 bg-black/20 hover:border-white/25'
            }`}
          >
            <span className="text-xs text-zinc-300">No trained identity</span>
            <span className="text-[11px] text-zinc-500">{selectedModelId === null ? 'Default render' : 'Use default'}</span>
          </button>

          {relevantSettings.map((model) => (
            <IdentityRow
              key={model.visual_model_id}
              model={model}
              label="Setting"
              selected={selectedModelId === model.visual_model_id}
              disabled={Boolean(disabled)}
              onChoose={() => onSelect(selectedModelId === model.visual_model_id ? null : model.visual_model_id)}
            />
          ))}
          {characterIdentities.map((model) => (
            <IdentityRow
              key={model.visual_model_id}
              model={model}
              label={String(model.configuration?.canonical_target_name || 'Character')}
              selected={selectedModelId === model.visual_model_id}
              disabled={Boolean(disabled)}
              onChoose={() => onSelect(selectedModelId === model.visual_model_id ? null : model.visual_model_id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
