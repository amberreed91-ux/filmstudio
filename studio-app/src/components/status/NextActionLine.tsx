import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { nextActionCopy } from '../../lib/statusCopy'

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
