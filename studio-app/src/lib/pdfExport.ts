/**
 * PDF Export Utilities for Scene Breakdown
 * Uses the existing exportProjectArtifact API endpoint
 */

import { exportProjectArtifact, type StudioProject } from './studioApi'

/**
 * Trigger scene breakdown PDF export via API
 * The backend will generate the PDF with project title, scene list,
 * character arcs, tone analysis, transition advisories, and sound advisories
 */
export async function exportSceneBreakdownAsPDF(projectId: string): Promise<void> {
  try {
    const response = await exportProjectArtifact(projectId, 'scene-breakdown')
    
    // If the API returns a URL, trigger download
    if (response && typeof response === 'object') {
      const url = (response as Record<string, unknown>).url as string | undefined
      if (url) {
        // Trigger file download
        const link = document.createElement('a')
        link.href = url
        link.download = `scene_breakdown_${projectId}.pdf`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
      }
    }
  } catch (error) {
    console.error('Failed to export scene breakdown:', error)
    // Could show toast notification here
  }
}
