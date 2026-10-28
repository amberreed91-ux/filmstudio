/** Session key for a project's Gate dossier handoff into The Page. */
export function dossierStorageKey(projectId: string): string {
  return `gate:dossier:${projectId}`
}
