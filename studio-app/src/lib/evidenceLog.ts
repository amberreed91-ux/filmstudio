/** Deterministic, dependency-free hash for display-only log identity. */
export function hashLogEntry(id: string, detail: string): string {
  const input = `${id}::${detail}`
  let hash = 5381
  for (let i = 0; i < input.length; i += 1) {
    hash = ((hash << 5) + hash + input.charCodeAt(i)) >>> 0
  }
  return `sha-${hash.toString(16).padStart(8, '0')}`
}
