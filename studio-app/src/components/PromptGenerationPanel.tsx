import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

interface EnhancedPrompt {
  scene_id: string;
  original_description: string;
  enhanced_prompt: string;
  style_tags: string[];
  character_references: string[];
  is_user_edited: boolean;
}

interface PromptGenerationResult {
  prompts: EnhancedPrompt[];
  style_consistency_note: string;
}

interface PromptGenerationPanelProps {
  projectId: string;
}

export function PromptGenerationPanel({ projectId }: PromptGenerationPanelProps) {
  const [editingPrompts, setEditingPrompts] = useState<Record<string, string>>({});

  // Fetch enhanced prompts
  const { data, isLoading, error, refetch } = useQuery<PromptGenerationResult>({
    queryKey: ['script-prompts', projectId],
    queryFn: async () => {
      const response = await fetch(`/api/projects/${projectId}/script-analysis/prompts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_ids: null }) // Generate for all scenes
      });
      if (!response.ok) {
        throw new Error('Failed to generate prompts');
      }
      return response.json();
    },
    enabled: !!projectId,
  });

  const handleEdit = (sceneId: string, newPrompt: string) => {
    setEditingPrompts(prev => ({
      ...prev,
      [sceneId]: newPrompt
    }));
  };

  const handleSave = (sceneId: string) => {
    // In production, you'd persist this back to the project scene data
    // Clear editing state
    setEditingPrompts(prev => {
      const next = { ...prev };
      delete next[sceneId];
      return next;
    });
  };

  const handleCancel = (sceneId: string) => {
    setEditingPrompts(prev => {
      const next = { ...prev };
      delete next[sceneId];
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-zinc-400">Generating enhanced prompts...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg bg-red-900/20 border border-red-700 p-4">
        <p className="text-red-400 text-sm">
          Failed to generate prompts. {error instanceof Error ? error.message : 'Unknown error'}
        </p>
        <button type="button"
          onClick={() => refetch()}
          className="mt-2 text-xs text-red-300 hover:text-red-200 underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data || data.prompts.length === 0) {
    return (
      <div className="rounded-lg bg-zinc-800 border border-zinc-700 p-6 text-center">
        <p className="text-zinc-400 text-sm">
          No prompts available. Add scenes to your project to generate prompts.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Style Consistency Advisory */}
      {data.style_consistency_note && (
        <div className="rounded-lg bg-blue-900/20 border border-blue-700 p-4">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-500/20 flex items-center justify-center mt-0.5">
              <svg className="w-3 h-3 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div className="flex-1">
              <p className="text-blue-200 text-sm leading-relaxed">
                {data.style_consistency_note}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Prompts List */}
      <div className="space-y-4">
        {data.prompts.map((prompt) => {
          const isEditing = prompt.scene_id in editingPrompts;
          const displayPrompt = isEditing ? editingPrompts[prompt.scene_id] : prompt.enhanced_prompt;

          return (
            <div
              key={prompt.scene_id}
              className="rounded-lg bg-zinc-800 border border-zinc-700 p-4 space-y-3"
            >
              {/* Scene Header */}
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-zinc-200">
                  {prompt.scene_id}
                </h3>
                <div className="flex items-center gap-2">
                  {prompt.character_references.length > 0 && (
                    <div className="flex items-center gap-1">
                      {prompt.character_references.map((char, idx) => (
                        <span
                          key={idx}
                          className="text-xs px-2 py-0.5 rounded bg-purple-900/30 text-purple-300"
                        >
                          {char}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Enhanced Prompt */}
              <div className="space-y-2">
                <label className="block text-xs text-zinc-400 uppercase tracking-wide">
                  Enhanced Prompt ({displayPrompt.length}/512)
                </label>
                {isEditing ? (
                  <textarea
                    value={displayPrompt}
                    onChange={(e) => handleEdit(prompt.scene_id, e.target.value)}
                    className="w-full px-3 py-2 rounded bg-zinc-900 border border-zinc-600 text-zinc-200 text-sm font-mono leading-relaxed focus:outline-none focus:border-blue-500 resize-none"
                    rows={4}
                    maxLength={512}
                  />
                ) : (
                  <div className="px-3 py-2 rounded bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm font-mono leading-relaxed">
                    {displayPrompt}
                  </div>
                )}
              </div>

              {/* Style Tags */}
              {prompt.style_tags.length > 0 && (
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-zinc-500">Style:</span>
                  {prompt.style_tags.slice(0, 5).map((tag, idx) => (
                    <span
                      key={idx}
                      className="text-xs px-2 py-0.5 rounded bg-zinc-700 text-zinc-300"
                    >
                      {tag}
                    </span>
                  ))}
                  {prompt.style_tags.length > 5 && (
                    <span className="text-xs text-zinc-500">
                      +{prompt.style_tags.length - 5} more
                    </span>
                  )}
                </div>
              )}

              {/* Original Description (collapsible) */}
              <details className="text-xs">
                <summary className="cursor-pointer text-zinc-500 hover:text-zinc-400">
                  Original Description
                </summary>
                <p className="mt-2 text-zinc-400 leading-relaxed pl-4 border-l-2 border-zinc-700">
                  {prompt.original_description}
                </p>
              </details>

              {/* Actions */}
              <div className="flex items-center justify-end gap-2 pt-2 border-t border-zinc-700">
                {isEditing ? (
                  <>
                    <button type="button"
                      onClick={() => handleCancel(prompt.scene_id)}
                      className="px-3 py-1 text-xs text-zinc-400 hover:text-zinc-200"
                    >
                      Cancel
                    </button>
                    <button type="button"
                      onClick={() => handleSave(prompt.scene_id)}
                      className="px-3 py-1 text-xs rounded bg-blue-600 text-white hover:bg-blue-500"
                    >
                      Save Changes
                    </button>
                  </>
                ) : (
                  <>
                    <button type="button"
                      onClick={() => handleEdit(prompt.scene_id, prompt.enhanced_prompt)}
                      className="px-3 py-1 text-xs text-zinc-400 hover:text-zinc-200"
                    >
                      Edit Prompt
                    </button>
                    <button type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(prompt.enhanced_prompt);
                      }}
                      className="px-3 py-1 text-xs text-blue-400 hover:text-blue-300"
                    >
                      Copy to Clipboard
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Regenerate Button */}
      <div className="flex justify-center pt-4">
        <button type="button"
          onClick={() => refetch()}
          className="px-4 py-2 text-sm rounded bg-zinc-700 text-zinc-200 hover:bg-zinc-600"
        >
          Regenerate All Prompts
        </button>
      </div>
    </div>
  );
}
