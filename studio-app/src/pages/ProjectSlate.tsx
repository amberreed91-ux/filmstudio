import { useState } from 'react'
import { ArrowRight, Archive, Copy, GitBranch } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import StudioShell from '../components/StudioShell'
import StudioPanel from '../components/StudioPanel'
import { useStudio } from '../context/StudioContext'
import { buildSlateCards, inferProductionMode } from '../lib/studioSystem'
import { createSlateVariant, loadSlateState, toggleArchivedProject, toggleArchivedVariant } from '../lib/studioWorkspaceState'

export default function ProjectSlate() {
  const navigate = useNavigate()
  const { overview } = useStudio()
  const [message, setMessage] = useState<string | null>(null)
  const [, setRefreshKey] = useState(0)
  const slateState = loadSlateState()
  const cards = buildSlateCards(overview, slateState.variants, slateState.archivedProjectIds)

  function refreshSlate(messageText: string) {
    setMessage(messageText)
    setRefreshKey((value) => value + 1)
  }

  return (
    <StudioShell title="Project Slate" subtitle="Manage the slate like a studio head: branch projects, spin duplicates, and open active productions.">
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        <StudioPanel
          title="Slate Control"
          subtitle="Every card is a live production package with stage, tone, and mode context."
          action={message ? (
            <span className="text-xs px-3 py-1 rounded-full" style={{ background: 'rgba(0,200,255,0.1)', color: 'var(--accent-cyan)', border: '1px solid rgba(0,200,255,0.18)' }}>
              {message}
            </span>
          ) : null}
        >
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: 'Live Projects', value: `${overview?.projects?.length || 0}` },
              { label: 'Variants', value: `${slateState.variants.filter((variant) => !variant.archived).length}` },
              { label: 'Archived', value: `${cards.filter((card) => card.archived).length}` },
            ].map((item) => (
              <div key={item.label} className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{item.label}</div>
                <div className="text-2xl font-semibold mt-1" style={{ color: 'var(--text-primary)' }}>{item.value}</div>
              </div>
            ))}
          </div>
        </StudioPanel>

        <div className="grid grid-cols-2 gap-4">
          {cards.map((card) => (
            <StudioPanel
              key={card.id}
              title={card.title}
              subtitle={card.tagLine}
              action={
                <span
                  className="text-[11px] uppercase tracking-widest px-2 py-1 rounded-full"
                  style={{
                    background: card.archived ? 'rgba(255,255,255,0.06)' : 'rgba(0,200,255,0.08)',
                    color: card.archived ? 'var(--text-muted)' : 'var(--accent-cyan)',
                    border: '1px solid rgba(255,255,255,0.08)',
                  }}
                >
                  {card.kind}
                </span>
              }
            >
              <div className="flex flex-wrap gap-2 mb-3">
                {[card.stage, card.genre, card.tone, card.mode].map((tag) => (
                  <span key={tag} className="text-xs px-2 py-1 rounded-full" style={{ background: 'rgba(255,255,255,0.04)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
                    {tag}
                  </span>
                ))}
              </div>
              <div className="flex flex-wrap gap-2 mb-4">
                {card.quickFacts.map((fact) => (
                  <div key={fact} className="text-xs px-2 py-1 rounded" style={{ color: 'var(--text-muted)', background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                    {fact}
                  </div>
                ))}
              </div>
              <div className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>{card.status}</div>

              <div className="flex items-center gap-2 flex-wrap">
                <button
                  type="button"
                  className="btn-primary text-xs px-3 py-1.5 inline-flex items-center gap-1"
                  onClick={() => navigate(`/studio/project/${card.sourceProjectId}${card.variantId ? `?variant=${card.variantId}` : ''}`)}
                >
                  Open
                  <ArrowRight size={12} />
                </button>
                <button
                  type="button"
                  className="btn-ghost text-xs px-3 py-1.5 inline-flex items-center gap-1"
                  onClick={() => {
                    const variant = createSlateVariant({
                      sourceProjectId: card.sourceProjectId,
                      title: `${card.title} Copy`,
                      kind: 'duplicate',
                      mode: card.mode || inferProductionMode(null),
                      stage: 'Development',
                      notes: 'Operational duplicate for alternate notes, approvals, and pacing experiments.',
                    })
                    refreshSlate(`Created duplicate package: ${variant.title}`)
                  }}
                >
                  <Copy size={12} />
                  Duplicate
                </button>
                <button
                  type="button"
                  className="btn-ghost text-xs px-3 py-1.5 inline-flex items-center gap-1"
                  onClick={() => {
                    const variant = createSlateVariant({
                      sourceProjectId: card.sourceProjectId,
                      title: `${card.title} Alt Cut`,
                      kind: 'branch',
                      mode: card.mode || inferProductionMode(null),
                      stage: 'Pre-production',
                      notes: 'Branch for alternate tone, pacing, and coverage choices without disturbing the main cut.',
                    })
                    refreshSlate(`Branched a new creative direction: ${variant.title}`)
                  }}
                >
                  <GitBranch size={12} />
                  Branch
                </button>
                <button
                  type="button"
                  className="btn-ghost text-xs px-3 py-1.5 inline-flex items-center gap-1"
                  onClick={() => {
                    if (card.variantId) {
                      toggleArchivedVariant(card.variantId)
                    } else {
                      toggleArchivedProject(card.sourceProjectId)
                    }
                    refreshSlate(card.archived ? `Restored ${card.title} to the active slate.` : `Archived ${card.title} from the working slate.`)
                  }}
                >
                  <Archive size={12} />
                  {card.archived ? 'Restore' : 'Archive'}
                </button>
              </div>
            </StudioPanel>
          ))}
        </div>
      </div>
    </StudioShell>
  )
}
