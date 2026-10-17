export type ShotWorkflowStep = 'plan' | 'storyboard' | 'render' | 'review'
export const shotWorkflowSteps = [
  { id: 'plan', title: 'Plan the shots', guidance: 'Choose a scene, plan its shots, and shape the camera view.' },
  { id: 'storyboard', title: 'Generate and approve', guidance: 'Generate a frame for each shot, review continuity, and approve the storyboard.' },
  { id: 'render', title: 'Render a take', guidance: 'Bring an approved shot to life. Direct the action and create a take.' },
  { id: 'review', title: 'Review and assemble', guidance: 'Choose your takes, assemble the scene, and watch it in Screening.' },
] as const
export function shotWorkflowPath(step: ShotWorkflowStep): string {
  return step === 'plan' || step === 'storyboard' ? '/studio/storyboard' : '/studio/previs'
}
export function shotWorkflowStep(pathname: string, requested: string | null): ShotWorkflowStep {
  if (pathname.includes('/storyboard')) return requested === 'storyboard' ? requested : 'plan'
  return requested === 'review' ? requested : 'render'
}
