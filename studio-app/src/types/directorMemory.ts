/**
 * Director's Memory Engine v1 — Per-project symbolic memory.
 *
 * Mirrors AGENTS.md memory rules:
 * - Explicit-save-only for user-defined entries (symbols, characters, themes, notes).
 * - Co-director voice only — no scores, no percentages.
 * - Every saved entry is editable and forgettable.
 */

export type DirectorMemoryKind =
  | 'symbols'
  | 'motifs'
  | 'characters'
  | 'themes'
  | 'notes'
  | 'debates'

export const DIRECTOR_MEMORY_KINDS: DirectorMemoryKind[] = [
  'symbols',
  'motifs',
  'characters',
  'themes',
  'notes',
  'debates',
]

export interface DirectorMemoryEntryBase {
  entry_id: string
  kind: DirectorMemoryKind
  project_id: string
  saved_at: string
  updated_at: string
  editable: true
  forgettable: true
}

export interface SymbolEntry extends DirectorMemoryEntryBase {
  kind: 'symbols'
  symbol: string
  meaning: string
  first_introduced_scene: string
  last_seen_scene: string
}

export interface MotifEntry extends DirectorMemoryEntryBase {
  kind: 'motifs'
  motif: string
  keyword: string
  first_introduced_scene: string
  last_seen_scene: string
}

export interface CharacterEntry extends DirectorMemoryEntryBase {
  kind: 'characters'
  character: string
  traits: string[]
  avoids: string[]
  motivations: string
  speech_patterns: string
}

export interface ThemeEntry extends DirectorMemoryEntryBase {
  kind: 'themes'
  theme: string
  first_introduced_scene: string
  last_seen_scene: string
}

export interface DirectorNoteEntry extends DirectorMemoryEntryBase {
  kind: 'notes'
  headline: string
  note: string
  keyword: string
}

export interface AgentResponse {
  agent_name: string
  perspective: string
  position: string
  reasoning: string
  recommendation: string
}

export interface CoDirectorDebateEntry extends DirectorMemoryEntryBase {
  kind: 'debates'
  debate_id: string
  scene_id?: string
  act_number?: number
  is_full_project: boolean
  query: string
  agent_responses: AgentResponse[]
  points_of_agreement: string[]
  points_of_conflict: string[]
  synthesis: string
  filmmaker_prerogative: string
  is_dismissed: boolean
  is_saved: boolean
}

export type DirectorMemoryEntry =
  | SymbolEntry
  | MotifEntry
  | CharacterEntry
  | ThemeEntry
  | DirectorNoteEntry
  | CoDirectorDebateEntry

export interface DirectorMemoryBundle {
  symbols: SymbolEntry[]
  motifs: MotifEntry[]
  characters: CharacterEntry[]
  themes: ThemeEntry[]
  notes: DirectorNoteEntry[]
  debates: CoDirectorDebateEntry[]
}

export interface DirectorMemoryResponse {
  project_id: string
  memory: DirectorMemoryBundle
  last_updated: string
}

export interface DirectorMemoryCallback {
  kind: DirectorMemoryKind
  entry_id: string | null
  label: string
  message: string
  scene_id: string
  voice: 'co_director'
}

export interface DirectorMemoryScanResult {
  project_id: string
  scene_id: string
  scene_index: number | null
  callbacks: DirectorMemoryCallback[]
  generated_at: string
}
