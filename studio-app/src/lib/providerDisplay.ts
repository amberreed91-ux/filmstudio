export function formatProviderLabel(rawProvider?: string | null, availableProviderIds: string[] = [], providerMode?: string): string {
  const normalized = (rawProvider || '').trim().toLowerCase()
  const mode = (providerMode || '').trim().toLowerCase()
  
  if (!normalized || normalized === 'idle' || normalized === 'unknown_provider') return 'Idle'
  
  // Show "Runway (Hosted)" for hosted API mode
  if (normalized === 'runway') {
    if (mode === 'hosted_api' || mode === 'hosted') return 'Runway (Hosted)'
    return 'Runway'
  }
  
  if (normalized === 'simulated') return 'Simulated'
  if (normalized === 'mock_success') return 'Mock Success'
  if (normalized === 'generic') return 'Generic'
  if (normalized === 'higgsfield') return 'Higgsfield'
  if (normalized === 'aws') {
    return availableProviderIds.includes('aws') ? 'AWS' : 'No active provider'
  }
  return rawProvider || 'No active provider'
}
