import { Clapperboard, FileText, Image as ImageIcon } from 'lucide-react'

type Props = {
  takeReady?: boolean
  boardReady?: boolean
  imageReady?: boolean
}

function StatusDot({ ready, label }: { ready: boolean; label: string }) {
  return (
    <span
      role="status"
      aria-label={label}
      data-testid={label}
      className={`inline-block h-1.5 w-1.5 rounded-full ${ready ? 'bg-emerald-400' : 'bg-amber-400'}`}
    />
  )
}

export default function RenderPromptScopeNote({ takeReady = true, boardReady = true, imageReady = false }: Props) {
  return (
    <div data-testid="render-prompt-scope-note" className="mb-3 grid grid-cols-3 gap-2">
      <div data-testid="scope-group-take" className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
        <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-100">
          <Clapperboard size={12} aria-hidden />
          <span>Previs take direction</span>
          <StatusDot ready={takeReady} label="take-status" />
        </div>
        <div className="mt-0.5 text-xs text-zinc-400">writes to previs-render-prompt</div>
        <div className="text-xs text-zinc-500">previs take only</div>
      </div>
      <div data-testid="scope-group-board" className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
        <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-100">
          <FileText size={12} aria-hidden />
          <span>Board canonical text</span>
          <StatusDot ready={boardReady} label="board-status" />
        </div>
        <div className="mt-0.5 text-xs text-zinc-400">writes to blueprint version</div>
        <div className="text-xs text-zinc-500">approved board</div>
      </div>
      <div data-testid="scope-group-image" className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
        <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-100">
          <ImageIcon size={12} aria-hidden />
          <span>Runway image prompt</span>
          <StatusDot ready={imageReady} label="image-status" />
        </div>
        <div className="mt-0.5 text-xs text-zinc-400">writes to Runway render</div>
        <div className="text-xs text-zinc-500">approved image prompt</div>
      </div>
    </div>
  )
}
