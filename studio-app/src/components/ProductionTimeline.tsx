export type ProductionStage = 'script' | 'previs' | 'generation' | 'review' | 'edit' | 'archive'

export type SceneTimelineRow = {
  sceneId: string
  currentStage: ProductionStage
  isRendering?: boolean
}

const STAGES: ProductionStage[] = ['script', 'previs', 'generation', 'review', 'edit', 'archive']

function stageLabel(stage: ProductionStage): string {
  return stage
}

function stageIndex(stage: ProductionStage): number {
  const index = STAGES.indexOf(stage)
  return index >= 0 ? index : 0
}

export default function ProductionTimeline({
  scenes,
  title = 'Cinematic Production Timeline',
}: {
  scenes: SceneTimelineRow[]
  title?: string
}) {
  return (
    <section className="production-timeline-panel overflow-hidden">
      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-200">{title}</div>
      <div className="mt-3 space-y-2 overflow-x-auto pb-2">
        {scenes.map((scene) => {
          const currentIdx = stageIndex(scene.currentStage)
          return (
            <div key={scene.sceneId} className="production-timeline-row">
              <div className="production-timeline-scene">{scene.sceneId}</div>
              <div className="production-timeline-track">
                {STAGES.map((stage, index) => {
                  const completed = index < currentIdx
                  const active = index === currentIdx
                  return (
                    <div
                      key={`${scene.sceneId}-${stage}`}
                      className={`production-timeline-node ${
                        completed ? 'node-complete' : active ? 'node-active' : 'node-pending'
                      } ${active && scene.isRendering ? 'node-rendering' : ''}`}
                    >
                      <span className="production-timeline-dot">{completed ? '✓' : active && scene.isRendering ? '●' : ''}</span>
                      <span className="production-timeline-label">{stageLabel(stage)}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
