export type ProductionMode =
  | 'indie'
  | 'prestige'
  | 'commercial'
  | 'experimental'
  | 'streaming'
  | 'documentary'

export type SlateVariant = {
  id: string
  sourceProjectId: string
  title: string
  kind: 'duplicate' | 'branch'
  mode: ProductionMode
  stage: string
  notes: string
  archived: boolean
  createdAt: string
}

export type LeadershipNote = {
  id: string
  text: string
  createdAt: string
}

export type WorkspaceState = {
  productionMode: ProductionMode
  lockedDecisions: string[]
  approvedStages: string[]
  resolvedThreads: string[]
  leadershipNotes: LeadershipNote[]
}

const SLATE_KEY = 'studio:slate-state'
const WORKSPACE_KEY = 'studio:workspace-state'
const STORAGE_VERSION = 'v1'

type StoredSlateState = {
  version: string
  archivedProjectIds: string[]
  variants: SlateVariant[]
}

function canUseStorage() {
  return typeof window !== 'undefined' && Boolean(window.localStorage)
}

function readJson<T>(key: string, fallback: T): T {
  if (!canUseStorage()) return fallback
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as { version?: string }
    if (parsed.version !== STORAGE_VERSION) {
      window.localStorage.removeItem(key)
      return fallback
    }
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function writeJson<T>(key: string, value: T) {
  if (!canUseStorage()) return
  window.localStorage.setItem(key, JSON.stringify(value))
}

export function loadSlateState(): StoredSlateState {
  return readJson<StoredSlateState>(SLATE_KEY, {
    version: STORAGE_VERSION,
    archivedProjectIds: [],
    variants: [],
  })
}

export function saveSlateState(state: StoredSlateState) {
  writeJson(SLATE_KEY, { ...state, version: STORAGE_VERSION })
}

export function createSlateVariant(input: Omit<SlateVariant, 'id' | 'createdAt' | 'archived'>) {
  const state = loadSlateState()
  const nextVariant: SlateVariant = {
    ...input,
    id: `${input.kind}-${Date.now()}`,
    archived: false,
    createdAt: new Date().toISOString(),
  }
  saveSlateState({
    ...state,
    variants: [nextVariant, ...state.variants],
  })
  return nextVariant
}

export function toggleArchivedProject(projectId: string) {
  const state = loadSlateState()
  const archived = new Set(state.archivedProjectIds)
  if (archived.has(projectId)) {
    archived.delete(projectId)
  } else {
    archived.add(projectId)
  }
  saveSlateState({
    ...state,
    archivedProjectIds: Array.from(archived),
  })
}

export function toggleArchivedVariant(variantId: string) {
  const state = loadSlateState()
  saveSlateState({
    ...state,
    variants: state.variants.map((variant) =>
      variant.id === variantId
        ? { ...variant, archived: !variant.archived }
        : variant,
    ),
  })
}

export function getVariantById(variantId: string | null) {
  if (!variantId) return null
  return loadSlateState().variants.find((variant) => variant.id === variantId) || null
}

export function loadWorkspaceState(projectKey: string, fallbackMode: ProductionMode): WorkspaceState {
  const allStates = readJson<Record<string, WorkspaceState>>(WORKSPACE_KEY, {})
  return allStates[projectKey] || {
    productionMode: fallbackMode,
    lockedDecisions: [],
    approvedStages: [],
    resolvedThreads: [],
    leadershipNotes: [],
  }
}

export function saveWorkspaceState(projectKey: string, nextState: WorkspaceState) {
  const allStates = readJson<Record<string, WorkspaceState>>(WORKSPACE_KEY, {})
  writeJson(WORKSPACE_KEY, {
    ...allStates,
    [projectKey]: nextState,
  })
}
