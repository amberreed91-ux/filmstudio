/**
 * User-Facing Text Transformations
 * 
 * Converts technical internal state to filmmaker-friendly language.
 * Core principle: Show what to DO, not what the system IS doing.
 */

// ============================================================================
// STATUS TRANSFORMATIONS
// ============================================================================

export function friendlyStatus(rawStatus: string): string {
  const status = (rawStatus || '').trim().toLowerCase()
  
  // Map technical status to friendly language
  const statusMap: Record<string, string> = {
    'not_started': 'Not started yet',
    'pending': 'Getting ready…',
    'queued': 'Getting ready…',
    'preparing': 'Getting ready…',
    'processing': 'Generating…',
    'rendering': 'Generating…',
    'generating': 'Generating…',
    'polling': 'Generating…',
    'complete': 'Ready',
    'completed': 'Ready',
    'success': 'Ready',
    'failed': 'Needs attention',
    'error': 'Needs attention',
    'cancelled': 'Stopped',
    'blocked': 'Waiting on something',
    'draft': 'In progress',
    'in_review': 'Ready to review',
    'approved': 'Approved',
    'locked': 'Locked',
    // Omit these entirely
    'mock': '',
    'simulated': '',
    'mock_success': '',
  }
  
  return statusMap[status] || status
}

// ============================================================================
// ROOM NAME TRANSFORMATIONS
// ============================================================================

export const ROOM_NAMES: Record<string, { display: string; description: string }> = {
  'lobby': { display: 'Home', description: 'Start a new film or continue where you left off' },
  'dashboard': { display: 'Overview', description: 'See what to do next' },
  'studio-dashboard': { display: 'Overview', description: 'See what to do next' },
  'workspace': { display: 'Workspace', description: 'Your main workspace and quick access hub' },
  'development-room': { display: 'Development Room', description: 'Develop and plan your film concepts' },
  'writers-room': { display: "Writer's Room", description: 'Build your script and scenes' },
  'production-board': { display: 'Production Board', description: 'Manage and render your shots' },
  'screening-room': { display: 'Screening Room', description: 'Review your film' },
  'previs-room': { display: 'Previs', description: 'Visualize each scene' },
  'study-room': { display: 'Study Room', description: 'Add reference materials' },
  'approval-room': { display: 'Approval Room', description: 'Approve scenes for final cut' },
  'crew-ops': { display: 'Studio Settings', description: 'Configure your studio' },
  'project-slate': { display: 'Project Info', description: 'Project details and metadata' },
  'archive': { display: 'Archive', description: 'Past projects and exports' },
  'cost-manager': { display: 'Usage', description: 'Track usage and costs' },
}

export function friendlyRoomName(technicalName: string): string {
  const key = technicalName.toLowerCase().replace(/\s+/g, '-')
  return ROOM_NAMES[key]?.display || technicalName
}

export function roomDescription(technicalName: string): string {
  const key = technicalName.toLowerCase().replace(/\s+/g, '-')
  return ROOM_NAMES[key]?.description || ''
}

// ============================================================================
// ACTION BUTTON LABELS
// ============================================================================

export function primaryActionForStatus(status: string): { label: string; disabled: boolean } {
  const normalized = (status || '').trim().toLowerCase()
  
  const actionMap: Record<string, { label: string; disabled: boolean }> = {
    'not_started': { label: 'Generate', disabled: false },
    'pending': { label: 'View Progress', disabled: true },
    'queued': { label: 'View Progress', disabled: true },
    'preparing': { label: 'View Progress', disabled: true },
    'processing': { label: 'View Progress', disabled: true },
    'rendering': { label: 'View Progress', disabled: true },
    'generating': { label: 'View Progress', disabled: true },
    'polling': { label: 'View Progress', disabled: true },
    'complete': { label: 'Review', disabled: false },
    'completed': { label: 'Review', disabled: false },
    'success': { label: 'Review', disabled: false },
    'ready': { label: 'Review', disabled: false },
    'in_review': { label: 'Review', disabled: false },
    'approved': { label: 'Watch', disabled: false },
    'failed': { label: 'Retry', disabled: false },
    'error': { label: 'Retry', disabled: false },
    'needs_attention': { label: 'Retry', disabled: false },
  }
  
  return actionMap[normalized] || { label: 'View', disabled: false }
}

// ============================================================================
// ERROR MESSAGES
// ============================================================================

export function friendlyErrorMessage(technicalError: string): string {
  // Never show technical errors to users
  // Always return friendly guidance
  
  if (!technicalError) return ''
  
  const error = technicalError.toLowerCase()
  
  if (error.includes('404') || error.includes('not found')) {
    return "We couldn't find that. Try going back."
  }
  
  if (error.includes('timeout') || error.includes('timed out')) {
    return 'This is taking longer than expected. Try again in a moment.'
  }
  
  if (error.includes('network') || error.includes('connection')) {
    return 'Connection issue. Check your internet and try again.'
  }
  
  if (error.includes('unauthorized') || error.includes('forbidden')) {
    return "You don't have access to that."
  }
  
  // Generic friendly fallback
  return 'Something went wrong. Try again in a moment.'
}

// ============================================================================
// EMPTY STATES
// ============================================================================

export const EMPTY_STATES = {
  noScenes: 'No scenes yet. Start in Write to add your first scene.',
  noRenders: 'Nothing generated yet. Go to Scenes to start.',
  noProjects: 'No projects yet. Create your first film to get started.',
  noReference: 'No reference materials yet. Upload images or videos to guide your film.',
  noApprovals: 'No scenes ready for approval yet.',
  noArchive: 'No archived projects yet.',
}

// ============================================================================
// PROGRESS DISPLAY
// ============================================================================

export function friendlyProgress(completed: number, total: number): string {
  if (total === 0) return ''
  if (completed === total) return 'All ready'
  return `${completed} of ${total} ready`
}

// ============================================================================
// NEXT STEP GUIDANCE
// ============================================================================

export type PipelineStage = 
  | 'no_script'
  | 'script_exists'
  | 'renders_pending'
  | 'renders_complete'
  | 'needs_attention'

export interface NextStepGuidance {
  headline: string
  body: string
  buttonLabel: string
  buttonRoute: string
}

export function getNextStepGuidance(stage: PipelineStage, context?: {
  readyCount?: number
  totalCount?: number
  failedCount?: number
}): NextStepGuidance {
  switch (stage) {
    case 'no_script':
      return {
        headline: 'Start by writing your script',
        body: 'Head to Write to add your scenes and build out your story.',
        buttonLabel: 'Go to Write →',
        buttonRoute: '/studio/writers-room',
      }
    
    case 'script_exists':
      return {
        headline: 'Your scenes are ready to visualize',
        body: 'Go to Storyboard to preview how each scene will look, then to Scenes to generate your video clips.',
        buttonLabel: 'Go to Storyboard →',
        buttonRoute: '/studio/previs',
      }
    
    case 'renders_pending': {
      const ready = context?.readyCount || 0
      const total = context?.totalCount || 0
      return {
        headline: 'Your film is generating',
        body: `${ready} of ${total} scenes are ready. Check back soon or watch progress in Scenes.`,
        buttonLabel: 'Go to Scenes →',
        buttonRoute: '/studio/production-board',
      }
    }
    
    case 'renders_complete':
      return {
        headline: 'Your film is ready to watch',
        body: 'All scenes have been generated. Head to Watch to review your film.',
        buttonLabel: 'Watch your film →',
        buttonRoute: '/studio/screening-room',
      }
    
    case 'needs_attention': {
      const failed = context?.failedCount || 0
      const plural = failed === 1 ? 'scene needs' : 'scenes need'
      return {
        headline: `${failed} ${plural} attention`,
        body: 'Some scenes didn\'t generate successfully. Go to Scenes to retry them.',
        buttonLabel: 'Fix scenes →',
        buttonRoute: '/studio/production-board',
      }
    }
    
    default:
      return {
        headline: 'Welcome to your studio',
        body: 'Start by writing your script in the Write room.',
        buttonLabel: 'Get started →',
        buttonRoute: '/studio/writers-room',
      }
  }
}

// ============================================================================
// DECISION GATE MESSAGES
// ============================================================================

export function friendlyDecisionGate(isBlocked: boolean, blockerCount: number): {
  heading: string
  message: string
  buttonLabel: string
} {
  if (isBlocked) {
    const plural = blockerCount === 1 ? 'scene needs' : 'scenes need'
    return {
      heading: 'Ready to watch?',
      message: `Before you can watch your film, ${blockerCount} ${plural} attention. Tap below to fix them.`,
      buttonLabel: 'Fix scenes',
    }
  }
  
  return {
    heading: 'Ready to watch?',
    message: 'Everything looks good. Your film is ready to watch.',
    buttonLabel: 'Watch film',
  }
}

// ============================================================================
// HIDE TECHNICAL FIELDS
// ============================================================================

/**
 * Returns true if a field name should be hidden from users
 */
export function shouldHideField(fieldName: string): boolean {
  const hidden = [
    'provider_mode',
    'ready_for_hosted_generation',
    'schema_invalid',
    'payload_unsafe',
    'comparable',
    'auto_select',
    'execution_locked',
    'eligible',
    'request_blocked',
    'provider_job_id',
    'job_id',
    'task_id',
    'graph_id',
    'node_id',
    'metadata',
    'internal_id',
    'created_at',
    'updated_at',
  ]
  
  const lowerField = fieldName.toLowerCase().replace(/[_\s-]/g, '')
  return hidden.some(h => lowerField.includes(h.replace(/[_\s-]/g, '')))
}

/**
 * Returns true if a status value should be hidden (mock, simulated, etc)
 */
export function shouldHideStatus(status: string): boolean {
  const hidden = ['mock', 'simulated', 'mock_success']
  return hidden.includes((status || '').trim().toLowerCase())
}

// ============================================================================
// FILM STATS
// ============================================================================

export interface FilmStats {
  scenesWritten: number
  scenesGenerated: number
  scenesApproved: number
}

export function formatFilmStats(stats: FilmStats): string[] {
  const lines: string[] = []
  
  if (stats.scenesWritten > 0) {
    lines.push(`${stats.scenesWritten} scene${stats.scenesWritten === 1 ? '' : 's'} written`)
  }
  
  if (stats.scenesGenerated > 0) {
    lines.push(`${stats.scenesGenerated} scene${stats.scenesGenerated === 1 ? '' : 's'} generated`)
  }
  
  if (stats.scenesApproved > 0) {
    lines.push(`${stats.scenesApproved} scene${stats.scenesApproved === 1 ? '' : 's'} approved`)
  }
  
  return lines
}

// ============================================================================
// ONBOARDING
// ============================================================================

export const ONBOARDING_STEPS = [
  {
    number: 1,
    title: 'Write',
    description: 'Add your script in the Write room. Describe each scene in plain language.',
  },
  {
    number: 2,
    title: 'Generate',
    description: 'Go to Scenes and tap Generate on each scene to create your video clips with AI.',
  },
  {
    number: 3,
    title: 'Watch',
    description: 'Head to Watch to review your film and export when you\'re happy.',
  },
]

export function hasSeenOnboarding(): boolean {
  try {
    return localStorage.getItem('studio:onboarding:dismissed') === 'true'
  } catch {
    return false
  }
}

export function markOnboardingComplete(): void {
  try {
    localStorage.setItem('studio:onboarding:dismissed', 'true')
  } catch {
    // Ignore storage errors
  }
}
