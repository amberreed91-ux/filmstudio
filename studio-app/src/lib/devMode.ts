export function isStudioDevMode(): boolean {
  if (typeof window === 'undefined') return false
  const fromStorage = window.localStorage.getItem('devMode') === 'true'
  const params = new URLSearchParams(window.location.search)
  const fromQuery = params.get('dev') === '1'
  return fromStorage || fromQuery
}

export function enableStudioDevMode(): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem('devMode', 'true')
  console.log('[Studio DevMode] enabled')
}

export function disableStudioDevMode(): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem('devMode')
  console.log('[Studio DevMode] disabled')
}

