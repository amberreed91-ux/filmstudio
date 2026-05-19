import type { VideoUnderstandingStatus } from './studioApi'

export function resolveVideoUnderstandingBanner(statuses: VideoUnderstandingStatus[]): string {
  const enabled = (statuses || []).some((row) => row.understanding_enabled)
  if (enabled) {
    return 'Visual intelligence is active: keyframes, frame analysis, embeddings, and semantic memory are aligned for at least one reference.'
  }
  return 'Visual intelligence is still staging for this project. Upload a reference video, extract keyframes, run frame analysis, then build semantic memory to unlock search and continuity signals.'
}
