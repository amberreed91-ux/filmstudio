import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'

export type NextActionCopy = { label: string; detail: string; to: string | null; toLabel: string | null }

/** One plain-language next action per scene. No counts-as-judgment, no jargon. */
export function nextActionCopy(projectId: string, nextAction: string, sceneId: string): NextActionCopy {
  const q = encodeURIComponent(projectId || '')
  const page = `/studio/writers-room?project_id=${q}`
  const previs = `/studio/previs?project_id=${q}`
  const board = `/studio/production-board?project_id=${q}`
  const theater = `/studio/screening-room?project_id=${q}`
  const vault = `/studio/vault?project_id=${q}`
  switch (nextAction) {
    case 'add_scenes':
      return { label: 'Add scenes to begin', detail: 'This project has no saved scenes yet. Start in The Page.', to: page, toLabel: 'Open The Page' }
    case 'create_board':
      return { label: 'Sketch the shot plan', detail: `${sceneId} has no shot plan yet. Sketch shots in Previs to begin.`, to: previs, toLabel: 'Open Previs' }
    case 'approve_image_prompts':
      return { label: 'Approve the image prompts', detail: 'Some shots still carry proposed prompts. Approve them in Previs.', to: previs, toLabel: 'Open Previs' }
    case 'reapprove_stale_prompts':
      return { label: 'Look again at the changed prompts', detail: 'A prompt changed after approval. Look again and approve in Previs.', to: previs, toLabel: 'Open Previs' }
    case 'confirm_setting_anchor':
      return { label: 'Settle the setting look', detail: 'The setting look is not settled. Check the look in the Vault.', to: vault, toLabel: 'Open the Vault' }
    case 'check_project_data':
      return { label: 'Check the project data', detail: 'The setting look could not be checked from the saved data.', to: null, toLabel: null }
    case 'retry_failed_jobs':
      return { label: 'Try the failed shot again', detail: 'A render failed. Try it again from the scene board.', to: board, toLabel: 'Open scene board' }
    case 'await_media':
      return { label: 'Wait for the media to land', detail: 'Shots are moving. Wait for finished media before the next step.', to: board, toLabel: 'Open scene board' }
    case 'ready':
      return { label: 'Ready to screen', detail: 'Every check passed. Watch it in the Screening Room.', to: theater, toLabel: 'Open Screening Room' }
    default:
      return { label: 'Check this scene', detail: 'Something needs a look before this scene can move on.', to: board, toLabel: 'Open scene board' }
  }
}

export default function NextActionLine({
  projectId,
  nextAction,
  sceneId,
}: {
  projectId: string
  nextAction: string
  sceneId: string
}) {
  const copy = nextActionCopy(projectId, nextAction, sceneId)
  return (
    <>
      <p data-testid={`scene-next-${sceneId}`} className="mt-3 text-sm text-zinc-200">
        <span className="text-zinc-500">Next: </span>{copy.label}
      </p>
      {copy.to && (
        <Link
          data-testid={`scene-next-link-${sceneId}`}
          className="mt-1 inline-flex min-h-10 items-center gap-1.5 text-sm text-cyan-200"
          to={copy.to}
        >
          {copy.toLabel} <ArrowRight size={14} />
        </Link>
      )}
    </>
  )
}
