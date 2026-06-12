import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Users, AlertTriangle, Network, MessageSquare, Brain, Save, History, X, Loader2, CheckCircle2 } from 'lucide-react';

interface CharacterArcPanelProps {
  projectId: string;
}

interface CharacterProfile {
  character_id: string;
  name: string;
  first_appearance_scene: string;
  scene_count: number;
  scene_ids: string[];
}

interface CharacterArcGap {
  character_id: string;
  character_name: string;
  gap_start_scene: string;
  gap_end_scene: string;
  gap_scene_count: number;
  advisory: string;
}

interface CharacterRelationship {
  character_a: string;
  character_b: string;
  shared_scene_count: number;
  shared_scene_ids: string[];
}

interface CharacterArcAnalysis {
  character_count: number;
  characters: CharacterProfile[];
  arc_gaps: CharacterArcGap[];
  relationships: CharacterRelationship[];
  overall_advisory: string;
}

interface CharacterMindSimulation {
  character_name: string;
  likely_reaction: string;
  reasoning: string;
  consistency_flag: boolean;
  tension_note?: string;
}

interface SimulationHistoryEntry {
  query: string;
  response: CharacterMindSimulation;
  timestamp: string;
}

interface CharacterSimulationHistory {
  character_id: string;
  history: SimulationHistoryEntry[];
}

/**
 * Phase 2: Character Arc Analysis display component
 * 
 * Shows:
 * - Character inventory with scene counts
 * - Arc gaps (characters who disappear or appear once)
 * - Relationship matrix (characters who share scenes)
 * 
 * Following AGENTS.md:
 * - No business logic in components
 * - Backend is source of truth
 * - React Query for data fetching
 */
export default function CharacterArcPanel({ projectId }: CharacterArcPanelProps) {
  const queryClient = useQueryClient();
  const [selectedChar, setSelectedChar] = useState<CharacterProfile | null>(null);
  const [query, setQuery] = useState('');
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery<CharacterArcAnalysis>({
    queryKey: ['character-arcs', projectId],
    queryFn: async () => {
      const response = await fetch(`/api/projects/${projectId}/script-analysis/characters`);
      if (!response.ok) {
        throw new Error(`Character arc analysis failed: ${response.statusText}`);
      }
      return response.json();
    },
    staleTime: 5 * 60 * 1000,
    retry: 2,
  });

  const historyQuery = useQuery<CharacterSimulationHistory>({
    queryKey: ['character-sim-history', projectId, selectedChar?.character_id],
    queryFn: async () => {
      if (!selectedChar) return { character_id: '', history: [] };
      const response = await fetch(`/api/projects/${projectId}/characters/${selectedChar.character_id}/history`);
      if (!response.ok) throw new Error('Failed to load history');
      return response.json();
    },
    enabled: !!selectedChar,
  });

  const simulateMutation = useMutation({
    mutationFn: async (vars: { charId: string; query: string }) => {
      const response = await fetch(`/api/projects/${projectId}/characters/${vars.charId}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: vars.query }),
      });
      if (!response.ok) throw new Error('Simulation failed');
      return response.json() as Promise<CharacterMindSimulation>;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['character-sim-history', projectId, selectedChar?.character_id] });
      setQuery('');
    },
  });

  const saveToNotesMutation = useMutation({
    mutationFn: async (simulation: CharacterMindSimulation) => {
      const response = await fetch(`/api/projects/${projectId}/characters/${selectedChar?.character_id}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(simulation),
      });
      if (!response.ok) throw new Error('Failed to save to notes');
      return response.json();
    },
    onSuccess: () => {
      setSaveStatus('Saved!');
      setTimeout(() => setSaveStatus(null), 3000);
    },
  });

  // Loading state
  if (isLoading) {
    return (
      <div className="py-6 text-center">
        <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-solid border-amber-400 border-r-transparent"></div>
        <p className="mt-2 text-sm text-zinc-400">Analyzing character arcs...</p>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="py-6 text-center">
        <AlertTriangle size={24} className="mx-auto text-red-400 mb-2" />
        <p className="text-sm text-red-400">
          {error instanceof Error ? error.message : 'Failed to load character analysis'}
        </p>
      </div>
    );
  }

  // Empty state
  if (!data) {
    return (
      <div className="py-6 text-center">
        <p className="text-sm text-zinc-500">No character data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 py-4">
      {/* Overall Advisory */}
      {data.overall_advisory && (
        <div className="p-3 bg-zinc-800/50 rounded-lg border border-zinc-700">
          <p className="text-sm text-zinc-300 italic">{data.overall_advisory}</p>
        </div>
      )}

      {/* Character Inventory */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Users size={16} className="text-amber-400" />
          <h4 className="text-sm font-medium text-zinc-200">
            Character Inventory ({data.character_count})
          </h4>
        </div>

        <div className="space-y-2">
          {data.characters.map((char) => (
            <div
              key={char.character_id}
              className="flex items-center justify-between p-3 bg-zinc-800/30 rounded-lg border border-zinc-700/50"
            >
              <div className="flex-1">
                <p className="text-sm font-medium text-zinc-200">{char.name}</p>
                <p className="text-xs text-zinc-500 mt-1">
                  First appears: {char.first_appearance_scene}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <p className="text-sm text-zinc-400">
                    {char.scene_count} {char.scene_count === 1 ? 'scene' : 'scenes'}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedChar(char)}
                  className="p-2 text-zinc-400 hover:text-amber-400 hover:bg-amber-400/10 rounded-lg transition-colors"
                  title="Simulate Character Mind"
                >
                  <Brain size={18} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Arc Gaps (if any) */}
      {data.arc_gaps.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={16} className="text-orange-400" />
            <h4 className="text-sm font-medium text-zinc-200">
              Arc Gaps ({data.arc_gaps.length})
            </h4>
          </div>

          <div className="space-y-2">
            {data.arc_gaps.map((gap, index) => (
              <div
                key={`${gap.character_id}-${index}`}
                className="p-3 bg-orange-950/20 rounded-lg border border-orange-900/30"
              >
                <div className="flex items-start gap-2 mb-2">
                  <span className="text-sm font-medium text-orange-300">
                    {gap.character_name}
                  </span>
                  {gap.gap_scene_count > 0 && (
                    <span className="text-xs px-2 py-0.5 bg-orange-900/40 text-orange-300 rounded">
                      {gap.gap_scene_count}-scene gap
                    </span>
                  )}
                </div>
                <p className="text-xs text-zinc-400 italic">{gap.advisory}</p>
                {gap.gap_scene_count > 0 && (
                  <p className="text-xs text-zinc-500 mt-1">
                    From {gap.gap_start_scene} to {gap.gap_end_scene}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Relationship Matrix */}
      {data.relationships.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Network size={16} className="text-blue-400" />
            <h4 className="text-sm font-medium text-zinc-200">
              Character Relationships ({data.relationships.length})
            </h4>
          </div>

          <div className="space-y-2">
            {data.relationships.map((rel, index) => (
              <div
                key={index}
                className="flex items-center justify-between p-3 bg-blue-950/20 rounded-lg border border-blue-900/30"
              >
                <div className="flex-1">
                  <p className="text-sm text-zinc-300">
                    {rel.character_a} <span className="text-zinc-500">↔</span> {rel.character_b}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-blue-400">
                    {rel.shared_scene_count} shared {rel.shared_scene_count === 1 ? 'scene' : 'scenes'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* No Relationships Message */}
      {data.relationships.length === 0 && (
        <div className="p-4 bg-zinc-800/30 rounded-lg border border-zinc-700/50 text-center">
          <p className="text-sm text-zinc-500">
            No character relationships detected (characters don't share scenes)
          </p>
        </div>
      )}

      {/* Simulation Modal/Panel */}
      {selectedChar && (
        <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-lg h-full bg-zinc-900 border-l border-zinc-800 shadow-2xl flex flex-col">
            {/* Header */}
            <div className="p-4 border-b border-zinc-800 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-amber-400/10 rounded-lg text-amber-400">
                  <Brain size={20} />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-zinc-100">{selectedChar.name}</h3>
                  <p className="text-xs text-zinc-500">Character Mind Simulator</p>
                </div>
              </div>
              <button
                onClick={() => setSelectedChar(null)}
                className="p-2 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Query Input */}
              <div className="space-y-3">
                <label className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                  <MessageSquare size={14} />
                  How would {selectedChar.name} react to...
                </label>
                <div className="relative">
                  <textarea
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="e.g. 'How would they react to a sudden betrayal by Elena?'"
                    className="w-full min-h-[100px] p-4 bg-zinc-800/50 border border-zinc-700 rounded-xl text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-amber-400/50 focus:border-amber-400/50 resize-none"
                  />
                  <button
                    disabled={!query.trim() || simulateMutation.isPending}
                    onClick={() => simulateMutation.mutate({ charId: selectedChar.character_id, query })}
                    className="absolute bottom-3 right-3 px-4 py-2 bg-amber-400 text-black text-xs font-bold rounded-lg hover:bg-amber-300 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 shadow-lg"
                  >
                    {simulateMutation.isPending ? (
                      <>
                        <Loader2 size={14} className="animate-spin" />
                        Simulating...
                      </>
                    ) : (
                      <>
                        <Brain size={14} />
                        Simulate
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Current Result */}
              {simulateMutation.data && (
                <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-300">
                  <div className="p-5 bg-zinc-800 rounded-xl border border-zinc-700 shadow-xl space-y-4">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-amber-400">
                        <CheckCircle2 size={14} />
                        Likely Reaction
                      </div>
                      <button
                        onClick={() => saveToNotesMutation.mutate(simulateMutation.data!)}
                        disabled={saveToNotesMutation.isPending}
                        className="flex items-center gap-2 text-xs text-zinc-400 hover:text-zinc-100 transition-colors"
                      >
                        {saveStatus ? (
                          <span className="text-green-400 flex items-center gap-1">
                            <CheckCircle2 size={12} /> {saveStatus}
                          </span>
                        ) : (
                          <>
                            <Save size={14} /> Save to Notes
                          </>
                        )}
                      </button>
                    </div>
                    <p className="text-sm text-zinc-200 leading-relaxed italic">
                      "{simulateMutation.data.likely_reaction}"
                    </p>
                    <div className="pt-4 border-t border-zinc-700 space-y-3">
                      <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                        Reasoning (Grounded)
                      </div>
                      <p className="text-xs text-zinc-400 leading-relaxed">
                        {simulateMutation.data.reasoning}
                      </p>
                    </div>
                    {simulateMutation.data.tension_note && (
                      <div className="p-3 bg-amber-400/5 rounded-lg border border-amber-400/10">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-amber-400/80 mb-1">
                          Tension Note
                        </div>
                        <p className="text-xs text-amber-200/80 leading-relaxed">
                          {simulateMutation.data.tension_note}
                        </p>
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <div className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ${simulateMutation.data.consistency_flag ? 'bg-green-400/10 text-green-400' : 'bg-red-400/10 text-red-400'}`}>
                        {simulateMutation.data.consistency_flag ? 'Consistent with Arc' : 'Arc Inconsistency Flagged'}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* History */}
              {historyQuery.data?.history && historyQuery.data.history.length > 0 && (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 text-sm font-medium text-zinc-400">
                    <History size={14} />
                    Query History
                  </div>
                  <div className="space-y-3">
                    {historyQuery.data.history.map((entry, idx) => (
                      <div key={idx} className="p-4 bg-zinc-800/30 rounded-xl border border-zinc-800 hover:border-zinc-700 transition-colors">
                        <p className="text-xs font-medium text-zinc-300 mb-2">"{entry.query}"</p>
                        <p className="text-[11px] text-zinc-500 line-clamp-2">
                          {entry.response.likely_reaction}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
