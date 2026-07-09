import type { StudioProject } from '../lib/studioApi'
import { extractCoDirectorInspection } from '../lib/coDirectorInspection'

function displayValue(value: string | null): string {
  return value || 'Unavailable'
}

export default function CoDirectorInspectionPanel({ project }: { project: StudioProject | null }) {
  const inspection = extractCoDirectorInspection(project)
  const hasSnapshot = inspection !== null

  return (
    <details
      className="rounded-xl p-3"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="co-director-inspection"
    >
      <summary className="cursor-pointer text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
        Co-Director Inspection
      </summary>
      {hasSnapshot ? (
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Mode</div>
            <div style={{ color: 'var(--text-secondary)' }}>{displayValue(inspection.mode)}</div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Workflow Active</div>
            <div style={{ color: 'var(--text-secondary)' }}>{inspection.workflowActive ? 'Yes' : 'No'}</div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Critique</div>
            <div style={{ color: 'var(--text-secondary)' }}>{displayValue(inspection.critique)}</div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Proposal</div>
            <div style={{ color: 'var(--text-secondary)' }}>{displayValue(inspection.proposal)}</div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Comparison</div>
            <div style={{ color: 'var(--text-secondary)' }}>{displayValue(inspection.comparison)}</div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Intensity</div>
            <div style={{ color: 'var(--text-secondary)' }}>{displayValue(inspection.intensity)}</div>
          </div>
        </div>
      ) : (
        <div className="mt-3 text-xs" style={{ color: 'var(--text-muted)' }}>
          No active Co Director session
        </div>
      )}
    </details>
  )
}
