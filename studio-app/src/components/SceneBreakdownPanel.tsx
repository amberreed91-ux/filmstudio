import { useQuery } from '@tanstack/react-query';
import { AlertCircle, BarChart2, Zap, AlertTriangle } from 'lucide-react';

interface ActStructure {
  act1_scenes: string[];
  act2_scenes: string[];
  act3_scenes: string[];
  advisory: string;
}

interface PacingInsight {
  act_number: number;
  pacing_label: string;
  advisory: string;
}

interface TransitionWarning {
  from_scene_id: string;
  to_scene_id: string;
  issue_type: string;
  advisory: string;
}

interface SceneBreakdownAnalysis {
  total_scenes: number;
  estimated_runtime_minutes: number;
  act_structure: ActStructure;
  pacing_insights: PacingInsight[];
  transition_warnings: TransitionWarning[];
}

interface SceneBreakdownPanelProps {
  projectId: string;
}

/**
 * Scene Breakdown Panel - displays act structure, pacing, and transitions.
 * Phase 1 implementation.
 * 
 * Following AGENTS.md: No business logic - display only
 */
export default function SceneBreakdownPanel({ projectId }: SceneBreakdownPanelProps) {
  // Fetch scene breakdown analysis
  const { data, isLoading, error } = useQuery<SceneBreakdownAnalysis>({
    queryKey: ['scene-breakdown', projectId],
    queryFn: async () => {
      const response = await fetch(`/api/projects/${projectId}/script-analysis/breakdown`);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch scene breakdown' }));
        throw new Error(errorData.detail || 'Failed to fetch scene breakdown');
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
          <span className="text-sm">Analyzing screenplay structure...</span>
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
        No analysis data available
      </div>
    );
  }

  return (
    <div className="space-y-6 pt-4">
      {/* Summary Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-zinc-800/50 rounded p-3">
          <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">Total Scenes</div>
          <div className="text-2xl font-semibold text-zinc-200">{data.total_scenes}</div>
        </div>
        <div className="bg-zinc-800/50 rounded p-3">
          <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">Estimated Runtime</div>
          <div className="text-2xl font-semibold text-zinc-200">{data.estimated_runtime_minutes} min</div>
        </div>
        <div className="bg-zinc-800/50 rounded p-3">
          <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">Avg Per Scene</div>
          <div className="text-2xl font-semibold text-zinc-200">
            {Math.round((data.estimated_runtime_minutes * 60) / data.total_scenes)}s
          </div>
        </div>
      </div>

      {/* Act Structure */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <BarChart2 size={16} className="text-zinc-400" />
          <h3 className="text-sm font-medium text-zinc-200">Act Structure</h3>
        </div>
        
        <div className="bg-zinc-800/30 rounded-lg p-4 space-y-4">
          {/* Act Labels */}
          <div className="grid grid-cols-3 gap-4">
            <div>
              <div className="text-xs font-medium text-amber-400 uppercase tracking-wide mb-1">
                Act 1: Setup
              </div>
              <div className="text-xs text-zinc-400">
                {data.act_structure.act1_scenes.length} scenes
              </div>
            </div>
            <div>
              <div className="text-xs font-medium text-rose-400 uppercase tracking-wide mb-1">
                Act 2: Confrontation
              </div>
              <div className="text-xs text-zinc-400">
                {data.act_structure.act2_scenes.length} scenes
              </div>
            </div>
            <div>
              <div className="text-xs font-medium text-blue-400 uppercase tracking-wide mb-1">
                Act 3: Resolution
              </div>
              <div className="text-xs text-zinc-400">
                {data.act_structure.act3_scenes.length} scenes
              </div>
            </div>
          </div>

          {/* Advisory */}
          {data.act_structure.advisory && (
            <div className="border-t border-zinc-700 pt-3">
              <div className="flex items-start gap-2">
                <div className="flex-shrink-0 mt-0.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-amber-400"></div>
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed">
                  {data.act_structure.advisory}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Pacing Analysis */}
      {data.pacing_insights.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Zap size={16} className="text-zinc-400" />
            <h3 className="text-sm font-medium text-zinc-200">Pacing Analysis</h3>
          </div>
          
          <div className="space-y-3">
            {data.pacing_insights.map((insight) => (
              <div
                key={insight.act_number}
                className="bg-zinc-800/30 rounded-lg p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-zinc-300">
                    Act {insight.act_number}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    insight.pacing_label === 'fast' ? 'bg-rose-500/20 text-rose-300' :
                    insight.pacing_label === 'slow' ? 'bg-blue-500/20 text-blue-300' :
                    'bg-amber-500/20 text-amber-300'
                  }`}>
                    {insight.pacing_label}
                  </span>
                </div>
                {insight.advisory && (
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    {insight.advisory}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Transition Warnings */}
      {data.transition_warnings.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={16} className="text-rose-400" />
            <h3 className="text-sm font-medium text-zinc-200">Transition Warnings</h3>
          </div>
          
          <div className="space-y-2">
            {data.transition_warnings.map((warning, index) => (
              <div
                key={index}
                className="bg-rose-500/5 border border-rose-500/20 rounded-lg p-3"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-rose-300 font-medium">
                    {warning.from_scene_id} → {warning.to_scene_id}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-rose-500/20 text-rose-300">
                    {warning.issue_type}
                  </span>
                </div>
                {warning.advisory && (
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    {warning.advisory}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* No warnings message */}
      {data.transition_warnings.length === 0 && (
        <div className="text-center py-4 text-xs text-zinc-500">
          No transition issues detected
        </div>
      )}
    </div>
  );
}
