import type { StudioProject } from './studioApi'

export type CoDirectorInspectionSnapshot = {
  mode: string
  workflowActive: boolean
  critique: string | null
  proposal: string | null
  comparison: string | null
  intensity: string | null
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function asText(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

function summarizeArtifact(value: unknown): string | null {
  const text = asText(value)
  if (text) {
    return text
  }
  const item = asRecord(value)
  if (!item) {
    return null
  }
  return (
    asText(item.title) ||
    asText(item.category) ||
    asText(item.description) ||
    asText(item.level)
  )
}

function getSnapshotRoot(project: StudioProject | null): Record<string, unknown> | null {
  const root = asRecord(project)
  if (!root) {
    return null
  }

  const candidates: unknown[] = [
    root.co_director_workflow,
    root.co_director,
    asRecord(root.interactive_modules)?.co_director_workflow,
    asRecord(root.interactive_modules)?.co_director,
    asRecord(root.producer_dashboard)?.co_director_workflow,
    asRecord(root.producer_dashboard)?.co_director,
    asRecord(root.project_dashboard)?.co_director_workflow,
    asRecord(root.project_dashboard)?.co_director,
  ]

  for (const candidate of candidates) {
    const parsed = asRecord(candidate)
    if (parsed) {
      return parsed
    }
  }

  return null
}

export function extractCoDirectorInspection(project: StudioProject | null): CoDirectorInspectionSnapshot | null {
  const snapshot = getSnapshotRoot(project)
  if (!snapshot) {
    return null
  }

  const mode = asText(snapshot.mode) || asText(snapshot.current_mode) || 'unknown'
  const critique = summarizeArtifact(snapshot.critique)
  const proposal = summarizeArtifact(snapshot.proposal)
  const comparison = summarizeArtifact(snapshot.comparison)
  const intensity =
    summarizeArtifact(snapshot.intensity) ||
    summarizeArtifact(asRecord(snapshot.intensity_profile)?.level) ||
    summarizeArtifact(asRecord(snapshot.intensity_profile)?.guidance_level)

  const explicitWorkflow = snapshot.workflow_active
  const workflowActive = typeof explicitWorkflow === 'boolean'
    ? explicitWorkflow
    : Boolean(critique || proposal || comparison || intensity)

  return {
    mode,
    workflowActive,
    critique,
    proposal,
    comparison,
    intensity,
  }
}
