import { useState } from 'react'
import { ChevronDown, Check } from 'lucide-react'

// Provider configuration
type ProviderConfig = {
  id: string
  name: string
  runtime?: string
  gpu?: string
  models: string[]
  badge?: string
}

const PROVIDERS: ProviderConfig[] = [
  {
    id: 'runway',
    name: 'Runway',
    models: [],
  },
  {
    id: 'runpod',
    name: 'RunPod',
    models: [],
  },
  {
    id: 'amd',
    name: 'AMD MI300X',
    runtime: 'ROCm',
    gpu: 'MI300X',
    models: ['ltx-2', 'hunyuan-video'],
    badge: 'ROCm',
  },
]

type ProviderPickerProps = {
  value?: { provider: string; model?: string }
  onChange: (selection: { provider: string; model?: string }) => void
  className?: string
}

export default function ProviderPicker({ value, onChange, className = '' }: ProviderPickerProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState<string>(value?.provider || 'runway')
  const [selectedModel, setSelectedModel] = useState<string | undefined>(value?.model)

  function handleProviderSelect(providerId: string) {
    const provider = PROVIDERS.find((p) => p.id === providerId)!
    setSelectedProvider(providerId)
    // Clear model if provider doesn't have models or if switching to a different provider
    if (provider.models.length === 0) {
      setSelectedModel(undefined)
      onChange({ provider: providerId })
    } else {
      // Keep existing model if it belongs to this provider, otherwise clear it
      const modelBelongsToProvider = selectedModel && provider.models.includes(selectedModel)
      const newModel = modelBelongsToProvider ? selectedModel : provider.models[0]
      setSelectedModel(newModel)
      onChange({ provider: providerId, model: newModel })
    }
    setIsOpen(false)
  }

  function handleModelSelect(model: string) {
    setSelectedModel(model)
    onChange({ provider: selectedProvider, model })
    setIsOpen(false)
  }

  function getDisplayLabel(): string {
    const provider = PROVIDERS.find((p) => p.id === selectedProvider)
    if (!provider) return 'Select provider'

    if (provider.models.length > 0 && selectedModel) {
      return `${provider.name} - ${selectedModel}`
    }
    return provider.name
  }

  return (
    <div className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between gap-2 rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-left text-sm font-medium text-zinc-100 hover:bg-white/5 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className="truncate">{getDisplayLabel()}</span>
        <ChevronDown
          size={16}
          className={`text-zinc-400 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && (
        <div className="absolute left-0 mt-1 w-full rounded-lg border border-white/15 bg-black/50 shadow-2xl shadow-black/50 backdrop-blur-xl z-50 overflow-hidden">
          <div className="p-1" role="listbox" aria-label="Select provider">
            {PROVIDERS.map((provider) => {
              const hasModels = provider.models.length > 0
              const isSelected = selectedProvider === provider.id

              return (
                <div key={provider.id} className="space-y-0.5">
                  <button
                    type="button"
                    onClick={() => handleProviderSelect(provider.id)}
                    className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-sm rounded-md hover:bg-white/5 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 ${isSelected ? 'bg-cyan-500/10 text-cyan-100' : 'text-zinc-200'}`}
                    role="option"
                    aria-selected={isSelected}
                  >
                    <div className="flex items-center gap-2">
                      <Check
                        size={16}
                        className={`transition-opacity duration-200 ${isSelected ? 'opacity-100' : 'opacity-0'}`}
                      />
                      <span>{provider.name}</span>
                      {provider.badge && (
                        <span className="text-[10px] uppercase tracking-wider text-zinc-400 bg-zinc-700/50 px-1.5 py-0.5 rounded text-nowrap">
                          {provider.badge}
                        </span>
                      )}
                    </div>
                    {hasModels && <ChevronDown size={14} className="text-zinc-400" />}
                  </button>

                  {isSelected && hasModels && (
                    <div className="pl-6 py-1 border-l border-white/10">
                      {provider.models.map((model) => (
                        <button
                          key={model}
                          type="button"
                          onClick={() => handleModelSelect(model)}
                          className={`w-full text-left text-sm px-3 py-1.5 rounded-md hover:bg-white/5 transition-colors duration-150 focus:outline-none ${selectedModel === model ? 'bg-cyan-500/15 text-cyan-100' : 'text-zinc-300'}`}
                          role="option"
                          aria-selected={selectedModel === model}
                        >
                          <span className="flex items-center gap-2">
                            <Check
                              size={14}
                              className={`transition-opacity duration-200 ${selectedModel === model ? 'opacity-100' : 'opacity-0'}`}
                            />
                            {model}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// Helper to display provider/model label
export function ProviderModelLabel({
  provider,
  model,
  showBadge = false,
}: {
  provider?: string | null
  model?: string | null
  showBadge?: boolean
}) {
  const providerConfig = PROVIDERS.find((p) => p.id === provider?.toLowerCase() || p.name.toLowerCase() === provider?.toLowerCase())

  if (!provider) return <span className="text-zinc-400 text-sm">No provider</span>

  return (
    <span className="flex items-center gap-2 text-sm">
      <span className="text-zinc-200">{providerConfig?.name || provider}</span>
      {model && (
        <>
          <span className="text-zinc-500">-</span>
          <span className="text-zinc-300">{model}</span>
        </>
      )}
      {showBadge && providerConfig?.badge && (
        <span className="text-[10px] uppercase tracking-wider text-zinc-400 bg-zinc-700/50 px-1.5 py-0.5 rounded">
          {providerConfig.badge}
        </span>
      )}
    </span>
  )
}

// Export provider metadata for use in other components
export { PROVIDERS }
export type { ProviderConfig }
