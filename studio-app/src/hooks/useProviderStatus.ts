import { useMemo } from 'react'

type ProviderOption = 'runway' | 'simulated'

export function useProviderStatus(provider: ProviderOption, useMockSuccess: boolean) {
  return useMemo(() => {
    if (provider === 'simulated') {
      return {
        providerLabel: useMockSuccess ? 'Mock Success' : 'Simulated',
        selectedProviderKey: useMockSuccess ? 'mock_success' : 'simulated',
        isSimulated: true,
      }
    }
    return {
      providerLabel: 'Runway',
      selectedProviderKey: 'runway',
      isSimulated: false,
    }
  }, [provider, useMockSuccess])
}
