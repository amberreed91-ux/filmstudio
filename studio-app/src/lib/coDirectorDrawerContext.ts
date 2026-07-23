export type CoDirectorSpecialist =
  | 'director'
  | 'writer'
  | 'memory_archivist'
  | 'evaluator'
  | 'provider_router'

export type CoDirectorContext =
  | 'current_scene'
  | 'full_script'
  | 'project_overview'
  | 'custom'

export type CoDirectorSceneSummary = {
  scene_id: string
  scene_name: string
  location?: string
}

export function resolveSceneForContext(
  scenes: CoDirectorSceneSummary[] | undefined,
  activeSceneId?: string,
): CoDirectorSceneSummary | undefined {
  return scenes?.find((scene) => scene.scene_id === activeSceneId) || scenes?.[0]
}

export function buildCoDirectorChatPayload(args: {
  specialist: CoDirectorSpecialist
  message: string
  context: CoDirectorContext
  projectId?: string
  systemPrompt: string
  scenes?: CoDirectorSceneSummary[]
  activeSceneId?: string
}): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    specialist: args.specialist,
    message: args.message,
    context: args.context,
    project_id: args.projectId,
    system_prompt: args.systemPrompt,
  }
  const scene = resolveSceneForContext(args.scenes, args.activeSceneId)
  if (args.context === 'current_scene' && scene?.scene_id) {
    payload.scene_id = scene.scene_id
  }
  return payload
}

export function formatMemoryProvenance(
  available: number,
  supplied: number | null,
): string {
  const noun = available === 1 ? 'entry' : 'entries'
  return supplied === null
    ? `Director's Memory — ${available} ${noun} available`
    : `Director's Memory — ${supplied} of ${available} ${noun} supplied`
}
