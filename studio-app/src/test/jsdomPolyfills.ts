/**
 * Polyfills for vitest's jsdom environment, imported by component tests
 * (before any app code renders).
 *
 * In this setup jsdom's localStorage/sessionStorage surface as plain objects
 * without the Storage methods app code calls (persistActiveProjectId etc.),
 * and the objects reject added properties — so replace them wholesale with
 * an in-memory Storage implementation.
 */

function createMemoryStorage(): Storage {
  const backing = new Map<string, string>()
  return {
    get length() { return backing.size },
    clear: () => backing.clear(),
    getItem: (key: string) => (backing.has(key) ? backing.get(key)! : null),
    key: (index: number) => Array.from(backing.keys())[index] ?? null,
    removeItem: (key: string) => { backing.delete(key) },
    setItem: (key: string, value: string) => { backing.set(String(key), String(value)) },
  }
}

export function installJsdomPolyfills(): void {
  if (typeof window === 'undefined') return
  const win = window as unknown as Record<string, unknown>
  for (const name of ['localStorage', 'sessionStorage']) {
    const existing = win[name] as Storage | undefined
    if (existing && typeof existing.setItem === 'function') continue
    try {
      Object.defineProperty(win, name, { value: createMemoryStorage(), configurable: true, writable: true })
    } catch {
      // Keep the original if the environment refuses the swap; component
      // tests that hit storage will surface a clear error instead.
    }
  }
}
