type FilmMemoryData = {
  themes: string[]
  motifs: string[]
  emotionalArcs: string[]
  callbacks: string[]
  continuityReferences: string[]
}

function toNodes(data: FilmMemoryData) {
  const nodes: Array<{ label: string; type: 'theme' | 'motif' | 'arc' | 'callback' | 'continuity' }> = []
  data.themes.forEach((value) => nodes.push({ label: value, type: 'theme' }))
  data.motifs.forEach((value) => nodes.push({ label: value, type: 'motif' }))
  data.emotionalArcs.forEach((value) => nodes.push({ label: value, type: 'arc' }))
  data.callbacks.forEach((value) => nodes.push({ label: value, type: 'callback' }))
  data.continuityReferences.forEach((value) => nodes.push({ label: value, type: 'continuity' }))
  return nodes.slice(0, 14)
}

function nodeTone(type: 'theme' | 'motif' | 'arc' | 'callback' | 'continuity'): string {
  if (type === 'theme') return 'memory-node-theme'
  if (type === 'motif') return 'memory-node-motif'
  if (type === 'arc') return 'memory-node-arc'
  if (type === 'callback') return 'memory-node-callback'
  return 'memory-node-continuity'
}

export default function FilmMemoryPanel({
  data,
  archivistStatus,
}: {
  data: FilmMemoryData
  archivistStatus?: string
}) {
  const nodes = toNodes(data)
  return (
    <section className="film-memory-panel">
      <div className="film-memory-network-bg" />
      <div className="relative z-10">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-200">Film Memory Graph</h3>
          <span className="rounded border border-emerald-400/40 bg-emerald-500/12 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-emerald-100">
            Memory Archivist Linked
          </span>
        </div>
        {archivistStatus ? (
          <div className="mt-2 text-xs text-emerald-200">{archivistStatus}</div>
        ) : null}
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {nodes.length === 0 ? (
            <div className="col-span-full rounded border border-white/10 bg-black/25 px-3 py-3 text-[11px] text-zinc-400">
              No structured memory graph nodes for this cut yet. Tone, motifs, and continuity references populate when the execution bundle and Study Room memory include matching signals.
            </div>
          ) : (
            nodes.map((node, index) => (
              <div key={`${node.type}-${node.label}-${index}`} className={`film-memory-node ${nodeTone(node.type)}`}>
                <div className="truncate text-[10px] uppercase tracking-[0.1em]">{node.type}</div>
                <div className="mt-1 truncate text-xs text-zinc-100">{node.label}</div>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  )
}
