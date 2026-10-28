import { useMemo, useState } from 'react'
import { Check, Loader2, Sparkles, X, AlertTriangle, Ban, Image as ImageIcon } from 'lucide-react'
import { buildStudioApiUrl } from '../lib/studioApi'
import {
  defaultTriggerWordFor,
  isActiveTrainingStatus,
  trainingStatusClassName,
  trainingStatusLabel,
  validateTriggerWord,
  visualTrainingError,
  type ReferenceAsset,
} from '../lib/visualTrainingApi'
import { findModelForTarget, type VisualTrainingController } from '../hooks/useVisualTraining'

/**
 * Studio-native Visual Training panel for a single canonical target — a
 * character look or a scene/setting. Filmmaking language first: the filmmaker
 * is training a reusable *visual identity* from *approved reference images*,
 * not managing datasets or checkpoints.
 *
 * The panel is presentational. All fetching and lifecycle state live in the
 * `useVisualTraining` controller passed in. Render-time defaults (provider,
 * model, trigger) are computed during render so the UI is correct on the first
 * paint and deterministic under static rendering.
 */

export interface VisualTrainingPanelProps {
  controller: VisualTrainingController
  canonicalTargetId: string
  targetName: string
  /** Short line under the title, e.g. "Approved look · version 3" or a location. */
  targetSubtitle?: string
  /** Existing approved preview (character portrait / environment still). */
  previewImageUrl?: string | null
  /** Label for the canonical approval/lock state, e.g. "Look locked". */
  approvalLabel?: string
  /**
   * Fired once when a training job reaches the complete state, so a host view
   * can refresh any sibling that lists ready identities (e.g. the Previs
   * opt-in picker after training a setting in the same session).
   */
  onIdentityReady?: () => void
  onClose: () => void
}

const primaryButton =
  'inline-flex items-center justify-center gap-2 rounded-md bg-amber-200 px-4 py-3 text-sm font-medium text-zinc-950 hover:bg-amber-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-zinc-500'
const secondaryButton =
  'inline-flex items-center justify-center gap-2 rounded-md border border-white/20 px-3 py-2.5 text-xs font-medium text-zinc-200 hover:border-white/35 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 disabled:cursor-not-allowed disabled:opacity-40'
const fieldClass =
  'mt-2 block w-full rounded border border-white/20 bg-black/30 px-3 py-2.5 text-sm leading-relaxed text-zinc-200 placeholder:text-zinc-600 focus-visible:outline-2 focus-visible:outline-amber-200 disabled:opacity-40'

function Thumb({ url, alt, className = '' }: { url: string; alt: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  if (failed || !url) {
    return (
      <div className={`flex items-center justify-center bg-black/40 text-zinc-600 ${className}`}>
        <ImageIcon size={20} strokeWidth={1.5} />
      </div>
    )
  }
  return (
    <img
      src={/^https?:\/\//.test(url) ? url : buildStudioApiUrl(url)}
      alt={alt}
      onError={() => setFailed(true)}
      className={className}
    />
  )
}

function StatusChip({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] uppercase tracking-[0.1em] ${trainingStatusClassName(status)}`}
    >
      {isActiveTrainingStatus(status) ? <Loader2 size={11} className="animate-spin" /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {trainingStatusLabel(status)}
    </span>
  )
}

function ReferenceCard({
  asset,
  selected,
  disabled,
  onToggle,
  index,
}: {
  asset: ReferenceAsset
  selected: boolean
  disabled: boolean
  onToggle: () => void
  index: number
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      aria-pressed={selected}
      aria-label={`Reference ${index + 1} (${asset.kind.replace(/_/g, ' ')})${selected ? ' — selected' : ''}`}
      className={`group relative min-w-0 overflow-hidden rounded border text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 disabled:opacity-40 ${
        selected ? 'border-amber-200 bg-amber-200/10' : 'border-white/15 bg-black/30 hover:border-white/40'
      }`}
    >
      <span className="relative block aspect-square overflow-hidden bg-black/40">
        <Thumb url={asset.image_url} alt={`Reference ${index + 1}`} className="h-full w-full object-cover" />
        {selected && (
          <span className="absolute bottom-2 right-2 rounded bg-amber-200 p-1 text-zinc-950">
            <Check size={14} />
          </span>
        )}
      </span>
      <span className="block px-2 py-2 text-xs capitalize text-zinc-400">{asset.kind.replace(/_/g, ' ')}</span>
    </button>
  )
}

type Phase = 'configure' | 'confirm'

export function VisualTrainingPanel({
  controller,
  canonicalTargetId,
  targetName,
  targetSubtitle,
  previewImageUrl,
  approvalLabel,
  onIdentityReady,
  onClose,
}: VisualTrainingPanelProps) {
  const isCharacter = controller.targetType === 'character'
  const existingModel = useMemo(
    () => findModelForTarget(controller.models, canonicalTargetId),
    [controller.models, canonicalTargetId],
  )

  const [selectedRefs, setSelectedRefs] = useState<string[]>([])
  const [triggerWord, setTriggerWord] = useState(() =>
    existingModel ? existingModel.trigger_word : defaultTriggerWordFor(targetName),
  )
  const [providerId, setProviderId] = useState(existingModel?.provider ?? '')
  const [providerModel, setProviderModel] = useState(existingModel?.provider_model ?? '')
  const [phase, setPhase] = useState<Phase>('configure')
  // When an identity already exists, require an explicit choice to train again
  // so we never auto-create a duplicate.
  const [retrain, setRetrain] = useState(!existingModel)

  const job = controller.activeJob
  const providers = controller.providers
  const references = controller.references

  // Render-time effective selections (correct on first paint, no effect needed).
  const effectiveProviderId = providerId || providers[0]?.provider_id || ''
  const effectiveProvider = providers.find((p) => p.provider_id === effectiveProviderId) || null
  const effectiveModel =
    providerModel && effectiveProvider?.models.includes(providerModel)
      ? providerModel
      : effectiveProvider?.models[0] || ''

  const triggerError = validateTriggerWord(triggerWord)
  const noProviders = !controller.providersLoading && providers.length === 0
  const noReferences = !controller.referencesLoading && references.length === 0
  const canConfigure =
    !noProviders && !noReferences && selectedRefs.length > 0 && !triggerError && Boolean(effectiveModel)

  const toggleRef = (refId: string) =>
    setSelectedRefs((prev) => (prev.includes(refId) ? prev.filter((id) => id !== refId) : [...prev, refId]))

  const beginTraining = () => {
    void controller
      .startTraining({
        canonicalTargetId,
        canonicalTargetName: targetName,
        triggerWord: triggerWord.trim(),
        sourceAssetIds: selectedRefs,
        provider: effectiveProviderId,
        providerModel: effectiveModel,
        // Reuse the existing model id when retraining a known identity.
        visualModelId: retrain && existingModel ? existingModel.visual_model_id : null,
      })
      .then((finalJob) => {
        // Notify the host only on a genuinely completed identity so sibling
        // identity lists (e.g. the Previs picker) refresh with real data.
        if (finalJob && finalJob.status === 'complete') onIdentityReady?.()
      })
  }

  const startConfigure = () => {
    if (existingModel) {
      setTriggerWord(existingModel.trigger_word)
      setProviderId(existingModel.provider)
      setProviderModel(existingModel.provider_model)
    }
    setRetrain(true)
    setPhase('configure')
  }

  const title = isCharacter ? 'Train This Look' : 'Train This Setting'
  const identityNoun = isCharacter ? 'Character Identity' : 'Setting Identity'

  // ── Lifecycle views (active job takes precedence) ──────────────────────────

  const renderProgress = () => (
    <div className="space-y-4" data-testid="vt-progress">
      <div className="flex items-center gap-3">
        <Loader2 size={18} className="animate-spin text-amber-200" />
        <p className="text-sm text-zinc-200">
          Training {targetName}’s visual identity…
        </p>
      </div>
      <StatusChip status={job!.status} />
      <p className="text-xs leading-relaxed text-zinc-500">
        We’ll show the identity here when it’s ready. You can leave and return — nothing is fabricated while it trains.
      </p>
      <button
        type="button"
        onClick={() => void controller.cancelTraining()}
        disabled={controller.cancelling}
        aria-busy={controller.cancelling}
        className={secondaryButton}
      >
        {controller.cancelling ? <Loader2 size={14} className="animate-spin" /> : <Ban size={14} />}
        Cancel training
      </button>
    </div>
  )

  const renderCompleted = (source: { trigger: string; provider: string; model: string; refCount: number; createdAt: string }) => (
    <div className="space-y-5" data-testid="vt-complete">
      <div>
        <p className="text-[11px] font-medium uppercase tracking-[0.15em] text-emerald-300/80">Visual Identity Ready</p>
        <h3 className="mt-1 text-xl font-medium text-zinc-100">{source.trigger}</h3>
      </div>
      <dl className="space-y-3 text-sm">
        <div className="flex justify-between gap-4"><dt className="text-zinc-500">Status</dt><dd><StatusChip status="complete" /></dd></div>
        <div className="flex justify-between gap-4"><dt className="text-zinc-500">Provider</dt><dd className="text-zinc-200">{source.provider}</dd></div>
        <div className="flex justify-between gap-4"><dt className="text-zinc-500">Model</dt><dd className="text-zinc-200">{source.model}</dd></div>
        <div className="flex justify-between gap-4"><dt className="text-zinc-500">References</dt><dd className="text-zinc-200">{source.refCount} source {source.refCount === 1 ? 'image' : 'images'}</dd></div>
        <div className="flex justify-between gap-4"><dt className="text-zinc-500">Created</dt><dd className="text-zinc-300">{source.createdAt ? new Date(source.createdAt).toLocaleString() : '—'}</dd></div>
      </dl>
      <div className="rounded-md border border-white/10 bg-white/[0.03] p-4">
        <p className="text-xs leading-relaxed text-zinc-300">This identity is now a reusable production asset.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <span className="inline-flex items-center gap-1.5 rounded border border-emerald-400/30 bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-200"><Check size={12} /> Available for Previs</span>
          <span className="inline-flex items-center gap-1.5 rounded border border-emerald-400/30 bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-200"><Check size={12} /> Available for Rendering</span>
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-zinc-500">
          It augments — never replaces — the canonical {isCharacter ? 'character' : 'scene'}. Use it intentionally per shot in Previs.
        </p>
      </div>
      {existingModel && !job && (
        <button type="button" onClick={startConfigure} className={secondaryButton}><Sparkles size={14} />Train a new identity</button>
      )}
    </div>
  )

  const renderFailed = () => (
    <div className="space-y-4" data-testid="vt-failed">
      <div className="flex items-center gap-2 text-rose-200"><AlertTriangle size={16} /><p className="text-sm font-medium">Training failed</p></div>
      <p className="text-xs leading-relaxed text-zinc-400">{job?.error || 'The provider could not complete training.'}</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={startConfigure} className={primaryButton}><Sparkles size={15} />Try again</button>
        <button type="button" onClick={onClose} className={secondaryButton}>Close</button>
      </div>
    </div>
  )

  const renderCancelled = () => (
    <div className="space-y-4" data-testid="vt-cancelled">
      <div className="flex items-center gap-2 text-zinc-300"><Ban size={16} /><p className="text-sm font-medium">Training cancelled</p></div>
      <p className="text-xs leading-relaxed text-zinc-400">No identity was created. You can start a new training run whenever you’re ready.</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={startConfigure} className={primaryButton}><Sparkles size={15} />Train again</button>
        <button type="button" onClick={onClose} className={secondaryButton}>Close</button>
      </div>
    </div>
  )

  // ── Configure / confirm ────────────────────────────────────────────────────

  const renderConfigure = () => (
    <div className="space-y-6" data-testid="vt-configure">
      {noProviders ? (
        <div className="rounded-md border border-amber-200/25 bg-amber-200/5 p-4" data-testid="vt-no-provider">
          <p className="text-sm text-amber-100">Visual training unavailable</p>
          <p className="mt-2 text-xs leading-relaxed text-zinc-400">
            There’s no training provider configured for this Studio right now. We won’t pretend training is available. Connect a provider, then return.
          </p>
          {controller.providersError && <p className="mt-2 text-xs text-zinc-500">{controller.providersError}</p>}
        </div>
      ) : noReferences ? (
        <div className="rounded-md border border-white/10 bg-white/[0.03] p-4" data-testid="vt-no-references">
          <p className="text-sm text-zinc-200">No approved references yet</p>
          <p className="mt-2 text-xs leading-relaxed text-zinc-400">
            {isCharacter
              ? 'Approve suitable character reference images before training. Confirmed face and full-body references become eligible here.'
              : 'Approve suitable environment references before training. Confirmed environment references become eligible here.'}
          </p>
        </div>
      ) : (
        <>
          <section aria-label="Reference images">
            <div className="flex items-baseline justify-between gap-3">
              <h4 className="text-sm font-medium text-zinc-100">Reference images</h4>
              <span className="text-xs text-zinc-500">{selectedRefs.length} selected</span>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-zinc-500">
              Choose the confirmed references that define this {isCharacter ? 'character' : 'setting'}. Only approved references are eligible.
            </p>
            {controller.referencesLoading ? (
              <p className="mt-3 flex items-center gap-2 text-xs text-zinc-400"><Loader2 size={13} className="animate-spin" />Loading references…</p>
            ) : (
              <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4 sm:gap-3">
                {references.map((asset, index) => (
                  <ReferenceCard
                    key={asset.ref_id}
                    asset={asset}
                    index={index}
                    selected={selectedRefs.includes(asset.ref_id)}
                    disabled={controller.submitting}
                    onToggle={() => toggleRef(asset.ref_id)}
                  />
                ))}
              </div>
            )}
            {controller.referencesError && <p className="mt-2 text-xs text-rose-200">{controller.referencesError}</p>}
          </section>

          <section aria-label="Identity configuration" className="space-y-4 border-t border-white/10 pt-5">
            <label className="block text-xs text-zinc-400" htmlFor="vt-trigger">
              Identity trigger
              <input
                id="vt-trigger"
                value={triggerWord}
                onChange={(e) => setTriggerWord(e.target.value)}
                disabled={controller.submitting}
                placeholder={defaultTriggerWordFor(targetName)}
                aria-invalid={Boolean(triggerError)}
                className={fieldClass}
              />
            </label>
            {triggerError && <p role="alert" className="text-xs text-amber-100">{triggerError}</p>}

            <label className="block text-xs text-zinc-400" htmlFor="vt-provider">
              Training provider
              <select
                id="vt-provider"
                value={effectiveProviderId}
                onChange={(e) => { setProviderId(e.target.value); setProviderModel('') }}
                disabled={controller.submitting}
                className={fieldClass}
              >
                {providers.map((p) => (
                  <option key={p.provider_id} value={p.provider_id}>
                    {p.name}{p.is_simulated ? ' (simulated)' : ''}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-xs text-zinc-400" htmlFor="vt-model">
              Training model
              <select
                id="vt-model"
                value={effectiveModel}
                onChange={(e) => setProviderModel(e.target.value)}
                disabled={controller.submitting || !effectiveProvider || effectiveProvider.models.length === 0}
                className={fieldClass}
              >
                {(effectiveProvider?.models ?? []).map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </label>
            {effectiveProvider && effectiveProvider.models.length === 0 && (
              <p className="text-xs text-amber-100">This provider reports no training models.</p>
            )}
          </section>

          <div className="flex flex-wrap gap-2 border-t border-white/10 pt-5">
            <button
              type="button"
              onClick={() => setPhase('confirm')}
              disabled={!canConfigure || controller.submitting}
              className={primaryButton}
            >
              <Sparkles size={15} />Review &amp; train
            </button>
            <button type="button" onClick={onClose} className={secondaryButton}>Cancel</button>
          </div>
          {!canConfigure && !triggerError && selectedRefs.length === 0 && !noReferences && (
            <p className="text-xs text-zinc-500">Select at least one reference to continue.</p>
          )}
          {controller.submitError && <p role="alert" className="text-xs text-rose-200">{controller.submitError}</p>}
        </>
      )}
    </div>
  )

  const renderConfirm = () => (
    <div className="space-y-5" data-testid="vt-confirm">
      <div>
        <p className="text-[11px] font-medium uppercase tracking-[0.15em] text-amber-100/80">Training {identityNoun}</p>
      </div>
      <dl className="space-y-3 text-sm">
        <div className="flex justify-between gap-4"><dt className="text-zinc-500">{isCharacter ? 'Character' : 'Setting'}</dt><dd className="text-zinc-200">{targetName}</dd></div>
        <div className="flex justify-between gap-4"><dt className="text-zinc-500">References</dt><dd className="text-zinc-200">{selectedRefs.length} selected</dd></div>
        <div className="flex justify-between gap-4"><dt className="text-zinc-500">Identity</dt><dd className="font-mono text-zinc-200">{triggerWord.trim()}</dd></div>
        <div className="flex justify-between gap-4"><dt className="text-zinc-500">Provider</dt><dd className="text-zinc-200">{effectiveProvider?.name || effectiveProviderId}</dd></div>
        <div className="flex justify-between gap-4"><dt className="text-zinc-500">Model</dt><dd className="text-zinc-200">{effectiveModel}</dd></div>
      </dl>
      {controller.submitError && <p role="alert" className="text-xs text-rose-200">{visualTrainingError(controller.submitError)}</p>}
      <div className="flex flex-wrap gap-2 border-t border-white/10 pt-4">
        <button type="button" onClick={beginTraining} disabled={controller.submitting} className={primaryButton}>
          {controller.submitting ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
          {controller.submitting ? 'Starting…' : 'Begin Training'}
        </button>
        <button type="button" onClick={() => setPhase('configure')} disabled={controller.submitting} className={secondaryButton}>Back</button>
      </div>
    </div>
  )

  // ── Root render: pick the right view ───────────────────────────────────────

  let body: React.ReactNode
  if (job && isActiveTrainingStatus(job.status)) {
    body = renderProgress()
  } else if (job && job.status === 'complete') {
    body = renderCompleted({
      trigger: job.trigger_word,
      provider: job.provider,
      model: job.provider_model,
      refCount: job.source_asset_ids.length,
      createdAt: job.completed_at || job.created_at,
    })
  } else if (job && job.status === 'failed') {
    body = renderFailed()
  } else if (job && job.status === 'cancelled') {
    body = renderCancelled()
  } else if (existingModel && !retrain) {
    body = renderCompleted({
      trigger: existingModel.trigger_word,
      provider: existingModel.provider,
      model: existingModel.provider_model,
      refCount: existingModel.source_asset_ids.length,
      createdAt: existingModel.created_at,
    })
  } else if (phase === 'confirm') {
    body = renderConfirm()
  } else {
    body = renderConfigure()
  }

  return (
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm sm:p-6"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-white/10 bg-zinc-950/95 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-4 top-4 z-10 rounded-full bg-white/10 p-2 text-white transition-colors hover:bg-white/20"
        >
          <X size={18} />
        </button>

        <header className="flex items-start gap-4 border-b border-white/10 px-6 py-5">
          <div className="h-16 w-16 shrink-0 overflow-hidden rounded border border-white/10 bg-black/40">
            <Thumb url={previewImageUrl || ''} alt={`${targetName} preview`} className="h-full w-full object-cover" />
          </div>
          <div className="min-w-0 pr-8">
            <p className="text-[10px] uppercase tracking-[0.18em] text-zinc-500">{identityNoun}</p>
            <h2 className="mt-0.5 truncate text-lg font-medium text-zinc-100">{title}</h2>
            <p className="mt-1 truncate text-xs text-zinc-400">{targetName}{targetSubtitle ? ` · ${targetSubtitle}` : ''}</p>
            {approvalLabel && (
              <span className="mt-2 inline-flex items-center gap-1.5 rounded border border-amber-200/30 bg-amber-200/5 px-2 py-0.5 text-[11px] text-amber-100">
                <Check size={11} />{approvalLabel}
              </span>
            )}
          </div>
        </header>

        <div className="px-6 py-5">{body}</div>
      </div>
    </div>
  )
}

export default VisualTrainingPanel
