import React from 'react'
import { AudienceSimulatorCard } from './AudienceSimulatorCard'
import type { SceneAudienceSimulation, ProjectAudienceSimulation } from '../types/audienceSimulator'
import { X } from 'lucide-react'

interface AudienceSimulatorModalProps {
  projectId: string
  simulation: SceneAudienceSimulation | ProjectAudienceSimulation | null
  onClose: () => void
}

export const AudienceSimulatorModal: React.FC<AudienceSimulatorModalProps> = ({
  projectId,
  simulation,
  onClose
}) => {
  if (!simulation) return null

  // Treat Project simulation as a "Scene" simulation for the card if it has audience_reactions
  const cardData = 'scene_id' in simulation 
    ? simulation 
    : {
        scene_id: 'Full Project Sequence',
        audience_reactions: (simulation as ProjectAudienceSimulation).audience_reactions,
        interpretation_variance: 'The full sequence creates a complex emotional tapestry where readings converge on the thematic resolution while diverging on individual character motivations.',
        co_director_note: simulation.co_director_note
      }

  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center p-4 sm:p-6 bg-black/80 backdrop-blur-sm" onClick={onClose}>
      <div 
        className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto" 
        onClick={e => e.stopPropagation()}
      >
        <button 
          onClick={onClose}
          className="absolute right-4 top-4 z-10 rounded-full bg-white/10 p-2 text-white hover:bg-white/20 transition-colors"
        >
          <X size={20} />
        </button>
        
        <AudienceSimulatorCard 
          projectId={projectId} 
          simulation={cardData as SceneAudienceSimulation} 
          onSaveSuccess={() => {}} 
        />
      </div>
    </div>
  )
}
