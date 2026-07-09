import { useQuery } from '@tanstack/react-query';
import { AlertCircle, Scissors, AlertTriangle } from 'lucide-react';

interface TransitionAdvisory {
  transition_type: 'cut' | 'dissolve' | 'match_cut' | 'smash_cut' | 'fade_to_black' | 'cross_dissolve';
  transition_rationale: string;
  continuity_notes: string;
}

interface SceneTransitionIntelligence {
  scene_pairs: Array<{
    from_scene_id: string;
    to_scene_id: string;
    advisory: TransitionAdvisory;
  }>;
}

interface TransitionIntelligencePanelProps {
  projectId: string;
}

/**
 * Transition Intelligence Panel - displays transition advisories between scenes.
 * Phase 1 implementation.
 *
 * Following AGENTS.md: No business logic - display only
 */
export default function TransitionIntelligencePanel({ projectId }: TransitionIntelligencePanelProps) {
  // Fetch transition intelligence
  const { data, isLoading, error } = useQuery<SceneTransitionIntelligence>({
    queryKey: ['transition-intelligence', projectId],
    queryFn: async () => {
      const response = await fetch(`/api/projects/${projectId}/script-analysis/transitions`);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch transition intelligence' }));
        throw new Error(errorData.detail || 'Failed to fetch transition intelligence');
      }
      return response.json();
    },
    enabled: !!projectId,
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
    retry: 2,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="flex items-center gap-2 text-zinc-400">
          <div className="animate-spin">⏳</div>
          <span className="text-sm">Analyzing transitions...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 p-4 bg-rose-500/10 border border-rose-500/30 rounded text-rose-300 text-sm">
        <AlertCircle size={16} />
        <span>{(error as Error).message}</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-8 text-zinc-500 text-sm">
        No transition intelligence available
      </div>
    );
  }

  // Empty state
  if (!data.scene_pairs || data.scene_pairs.length === 0) {
    return (
      <div className="text-center py-8 text-zinc-500 text-sm">
        No transition advisories
      </div>
    );
  }

  // Color mapping for transition types
  const getTransitionColor = (transitionType: string) => {
    switch (transitionType) {
      case 'fade_to_black':
      case 'cross_dissolve':
        return 'bg-violet-500/20 text-violet-300';
      case 'dissolve':
        return 'bg-blue-500/20 text-blue-300';
      case 'match_cut':
        return 'bg-emerald-500/20 text-emerald-300';
      case 'smash_cut':
        return 'bg-rose-500/20 text-rose-300';
      case 'cut':
      default:
        return 'bg-zinc-500/20 text-zinc-300';
    }
  };

  return (
    <div className="space-y-4 pt-4">
      <div className="flex items-center gap-2 mb-3">
        <Scissors size={16} className="text-zinc-400" />
        <h3 className="text-sm font-medium text-zinc-200">Scene Transitions</h3>
      </div>

      <div className="space-y-3">
        {data.scene_pairs.map((pair, index) => (
          <div
            key={index}
            className="bg-zinc-800/30 rounded-lg p-4 space-y-3"
          >
            {/* Scene pair header */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-zinc-300">
                {pair.from_scene_id}
              </span>
              <span className="text-zinc-500">→</span>
              <span className="text-xs font-medium text-zinc-300">
                {pair.to_scene_id}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded ${getTransitionColor(pair.advisory.transition_type)}`}>
                {pair.advisory.transition_type.replace('_', ' ')}
              </span>
            </div>

            {/* Transition rationale */}
            {pair.advisory.transition_rationale && (
              <div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">
                  Rationale
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed">
                  {pair.advisory.transition_rationale}
                </p>
              </div>
            )}

            {/* Continuity notes */}
            {pair.advisory.continuity_notes && (
              <div className="flex items-start gap-2 bg-amber-500/5 border border-amber-500/20 rounded p-2">
                <AlertTriangle size={14} className="text-amber-400 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs text-amber-400 uppercase tracking-wide mb-0.5">
                    Continuity Note
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    {pair.advisory.continuity_notes}
                  </p>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}