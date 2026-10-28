/**
 * Motif indicators for the scene continuity panel.
 *
 * Motifs arrive from the project-scoped motif-threads read. Active threads lead
 * the list so the indicators describe what the current cut still carries, not a
 * chronological archive. Order among equal statuses is preserved.
 */

export type MotifLike = {
  motif: string
  status: string
}

function asList<T>(motifs: T[]): T[] {
  return Array.isArray(motifs) ? motifs : []
}

/** Active threads first, everything else in arrival order. */
export function orderMotifs<T extends MotifLike>(motifs: T[]): T[] {
  return [...asList(motifs)].sort(
    (a, b) => Number(b.status === 'active') - Number(a.status === 'active'),
  )
}

/** The motifs the active project still carries. */
export function activeMotifs<T extends MotifLike>(motifs: T[]): T[] {
  return orderMotifs(motifs).filter((motif) => motif.status === 'active')
}
