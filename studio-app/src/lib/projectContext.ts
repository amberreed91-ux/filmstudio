type ResolveActiveProjectIdInput = {
  queryProjectId?: string | null
  routeProjectId?: string | null
  locationState?: unknown
  persistedProjectId?: string | null
  contextProjectId?: string | null
  overviewProjectId?: string | null
}

function clean(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

export function projectIdFromLocationState(locationState: unknown): string {
  const state = asRecord(locationState)
  if (!state) return ''
  const direct =
    clean(state.project_id) ||
    clean(state.projectId)
  if (direct) return direct
  const project = asRecord(state.project)
  if (!project) return ''
  return clean(project.project_id) || clean(project.projectId)
}

export function resolveActiveProjectId(input: ResolveActiveProjectIdInput): string {
  const query = clean(input.queryProjectId)
  if (query) return query
  const route = clean(input.routeProjectId)
  if (route) return route
  const routeState = projectIdFromLocationState(input.locationState)
  if (routeState) return routeState
  const persisted = clean(input.persistedProjectId)
  if (persisted) return persisted
  const context = clean(input.contextProjectId)
  if (context) return context
  return clean(input.overviewProjectId)
}

export function withProjectQuery(path: string, projectId?: string | null): string {
  const cleanId = clean(projectId)
  if (!cleanId) return path
  const [base, hashPart = ''] = path.split('#')
  const [pathname, query = ''] = base.split('?')
  const params = new URLSearchParams(query)
  params.set('project_id', cleanId)
  const next = `${pathname}?${params.toString()}`
  return hashPart ? `${next}#${hashPart}` : next
}

export function readPersistedActiveProjectId(): string {
  return clean(localStorage.getItem('studio:activeProjectId') || localStorage.getItem('studio:selected-project-id'))
}

export function persistActiveProjectId(projectId: string): void {
  const cleanId = clean(projectId)
  if (!cleanId) return
  localStorage.setItem('studio:activeProjectId', cleanId)
  localStorage.setItem('studio:selected-project-id', cleanId)
}
