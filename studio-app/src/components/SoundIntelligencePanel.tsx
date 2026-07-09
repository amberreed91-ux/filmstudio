import { useQuery } from '@tanstack/react-query';
import { AlertCircle, Music, Volume2, VolumeX, Headphones } from 'lucide-react';

interface SoundAdvisory {
  mood: string;
  score_notes: string;
  ambient_notes: string;
  silence_flag: boolean;
}

interface SceneSoundIntelligence {
  scene_sounds: Array<{
    scene_id: string;
    scene_title: string;
    advisory: SoundAdvisory;
  }>;
}

interface SoundIntelligencePanelProps {
  projectId: string;
}

/**
 * Sound Intelligence Panel - displays sound/music advisories per scene.
 * Phase 1 implementation.
 *
 * Following AGENTS.md: No business logic - display only
 */
export default function SoundIntelligencePanel({ projectId }: SoundIntelligencePanelProps) {
  // Fetch sound intelligence
  const { data, isLoading, error } = useQuery<SceneSoundIntelligence>({
    queryKey: ['sound-intelligence', projectId],
    queryFn: async () => {
      const response = await fetch(`/api/projects/${projectId}/script-analysis/sound`);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch sound intelligence' }));
        throw new Error(errorData.detail || 'Failed to fetch sound intelligence');
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
          <span className="text-sm">Analyzing sound design...</span>
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
        No sound intelligence available
      </div>
    );
  }

  // Empty state
  if (!data.scene_sounds || data.scene_sounds.length === 0) {
    return (
      <div className="text-center py-8 text-zinc-500 text-sm">
        No sound advisories
      </div>
    );
  }

  // Color mapping for moods
  const getMoodColor = (mood: string) => {
    switch (mood.toLowerCase()) {
      case 'tense':
        return 'bg-rose-500/20 text-rose-300';
      case 'melancholic':
        return 'bg-blue-500/20 text-blue-300';
      case 'propulsive':
        return 'bg-amber-500/20 text-amber-300';
      case 'hopeful':
        return 'bg-emerald-500/20 text-emerald-300';
      default:
        return 'bg-zinc-500/20 text-zinc-300';
    }
  };

  return (
    <div className="space-y-4 pt-4">
      <div className="flex items-center gap-2 mb-3">
        <Music size={16} className="text-zinc-400" />
        <h3 className="text-sm font-medium text-zinc-200">Sound Design</h3>
      </div>

      <div className="space-y-3">
        {data.scene_sounds.map((scene, index) => (
          <div
            key={index}
            className="bg-zinc-800/30 rounded-lg p-4 space-y-3"
          >
            {/* Scene header */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-medium text-zinc-300">
                {scene.scene_id}
              </span>
              {scene.scene_title && (
                <span className="text-xs text-zinc-400">
                  {scene.scene_title}
                </span>
              )}
              <span className={`text-xs px-2 py-0.5 rounded ${getMoodColor(scene.advisory.mood)}`}>
                <div className="flex items-center gap-1">
                  <Headphones size={10} />
                  {scene.advisory.mood}
                </div>
              </span>
              {scene.advisory.silence_flag && (
                <span className="text-xs px-2 py-0.5 rounded bg-violet-500/20 text-violet-300">
                  <div className="flex items-center gap-1">
                    <VolumeX size={10} />
                    Intentional Silence
                  </div>
                </span>
              )}
            </div>

            {/* Score notes */}
            {scene.advisory.score_notes && (
              <div className="flex items-start gap-2">
                <Music size={14} className="text-zinc-500 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs text-zinc-500 uppercase tracking-wide mb-0.5">
                    Score
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    {scene.advisory.score_notes}
                  </p>
                </div>
              </div>
            )}

            {/* Ambient notes */}
            {scene.advisory.ambient_notes && (
              <div className="flex items-start gap-2">
                <Volume2 size={14} className="text-zinc-500 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs text-zinc-500 uppercase tracking-wide mb-0.5">
                    Ambient
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    {scene.advisory.ambient_notes}
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