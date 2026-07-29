import { useState } from 'react';
import { ChevronDown, ChevronUp, BarChart3, Users, Sparkles, Scissors, Music, Brain, Download } from 'lucide-react';
import SceneBreakdownPanel from './SceneBreakdownPanel';
import CharacterArcPanel from './CharacterArcPanel';
import { PromptGenerationPanel } from './PromptGenerationPanel';
import TransitionIntelligencePanel from './TransitionIntelligencePanel';
import SoundIntelligencePanel from './SoundIntelligencePanel';
import PerformanceIntelligencePanel from './PerformanceIntelligencePanel';
import CastingIntelligencePanel from './CastingIntelligencePanel';
import { exportSceneBreakdownAsPDF } from '../lib/pdfExport';
import { useStudio } from '../context/StudioContext';

interface ScriptIntelligencePanelProps {
  projectId: string;
  sceneCount: number;
}

type TabType = 'breakdown' | 'characters' | 'casting' | 'performance' | 'prompts' | 'transitions' | 'sound';

/**
 * Container for all Script Intelligence features.
 * Phase 1: Scene Breakdown
 * Phase 2: Character Arc Analysis
 * Phase 3: Tone Consistency (TODO)
 * Phase 4: Prompt Generation
 * Phase 5: Transition Intelligence (Batch I)
 * Phase 6: Sound Intelligence (Batch I)
 * 
 * Following AGENTS.md: No business logic in components
 */
export default function ScriptIntelligencePanel({ projectId, sceneCount }: ScriptIntelligencePanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>('breakdown');
  const [isExporting, setIsExporting] = useState(false);
  const { project } = useStudio();
  const scenes = Array.isArray(project?.execution_summary?.scenes) ? project.execution_summary.scenes : [];
  const initialPerformanceSceneId = typeof scenes[0]?.scene_id === 'string' ? scenes[0].scene_id : 'scene_001';
  // Don't show panel if insufficient scenes
  if (sceneCount < 2) {
    return null;
  }

  async function handleExportPDF() {
    if (!projectId) return;
    try {
      setIsExporting(true);
      await exportSceneBreakdownAsPDF(projectId);
    } catch (error) {
      console.error('Export failed:', error);
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div className="border border-zinc-700 rounded-lg bg-zinc-900/50 backdrop-blur-sm">
      {/* Header - Collapsible */}
      <div className="px-4 py-3 flex items-center justify-between">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 hover:bg-zinc-800/50 transition-colors rounded p-1 -ml-1"
          aria-label={isExpanded ? "Collapse script analysis" : "Expand script analysis"}
        >
          <BarChart3 size={18} className="text-amber-400" />
          <span className="text-sm font-medium text-zinc-200">Script Intelligence</span>
          <span className="text-xs text-zinc-500">({sceneCount} scenes)</span>
        </button>
        
        {/* Export Button */}
        <button
          type="button"
          onClick={handleExportPDF}
          disabled={isExporting}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md border border-zinc-600 bg-zinc-800/50 text-zinc-200 hover:bg-zinc-700/50 hover:border-zinc-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          title="Export scene breakdown as PDF"
        >
          <Download size={14} />
          {isExporting ? 'Exporting...' : 'Export PDF'}
        </button>
        {isExpanded ? (
          <ChevronUp size={16} className="text-zinc-400" />
        ) : (
          <ChevronDown size={16} className="text-zinc-400" />
        )}
      </div>
      
      {/* Content */}
      {isExpanded && (
        <div className="border-t border-zinc-700">
          {/* Tab Navigation */}
          <div className="flex border-b border-zinc-700 px-4">
            <button
              onClick={() => setActiveTab('breakdown')}
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'breakdown'
                  ? 'border-amber-400 text-amber-400'
                  : 'border-transparent text-zinc-400 hover:text-zinc-300'
              }`}
            >
              <div className="flex items-center gap-2">
                <BarChart3 size={14} />
                Scene Breakdown
              </div>
            </button>
            <button
              onClick={() => setActiveTab('characters')}
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'characters'
                  ? 'border-amber-400 text-amber-400'
                  : 'border-transparent text-zinc-400 hover:text-zinc-300'
              }`}
            >
              <div className="flex items-center gap-2">
                <Users size={14} />
                Character Arcs
              </div>
            </button>
            <button
              onClick={() => setActiveTab('prompts')}
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'prompts'
                  ? 'border-amber-400 text-amber-400'
                  : 'border-transparent text-zinc-400 hover:text-zinc-300'
              }`}
            >
              <div className="flex items-center gap-2">
                <Sparkles size={14} />
                Prompts
              </div>
            </button>
            <button
              onClick={() => setActiveTab('casting')}
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'casting'
                  ? 'border-amber-400 text-amber-400'
                  : 'border-transparent text-zinc-400 hover:text-zinc-300'
              }`}
            >
              <div className="flex items-center gap-2">
                <Users size={14} />
                Casting
              </div>
            </button>
            <button
              onClick={() => setActiveTab('performance')}
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'performance'
                  ? 'border-amber-400 text-amber-400'
                  : 'border-transparent text-zinc-400 hover:text-zinc-300'
              }`}
            >
              <div className="flex items-center gap-2">
                <Brain size={14} />
                Performance
              </div>
            </button>
            <button
              onClick={() => setActiveTab('transitions')}
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'transitions'
                  ? 'border-amber-400 text-amber-400'
                  : 'border-transparent text-zinc-400 hover:text-zinc-300'
              }`}
            >
              <div className="flex items-center gap-2">
                <Scissors size={14} />
                Transitions
              </div>
            </button>
            <button
              onClick={() => setActiveTab('sound')}
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'sound'
                  ? 'border-amber-400 text-amber-400'
                  : 'border-transparent text-zinc-400 hover:text-zinc-300'
              }`}
            >
              <div className="flex items-center gap-2">
                <Music size={14} />
                Sound
              </div>
            </button>
          </div>

          {/* Tab Content */}
          <div className="px-4 pb-4">
            {activeTab === 'breakdown' && <SceneBreakdownPanel projectId={projectId} />}
            {activeTab === 'characters' && <CharacterArcPanel projectId={projectId} />}
            {activeTab === 'casting' && <CastingIntelligencePanel projectId={projectId} />}
            {activeTab === 'performance' && (
              <PerformanceIntelligencePanel projectId={projectId} initialSceneId={initialPerformanceSceneId} />
            )}
            {activeTab === 'prompts' && <PromptGenerationPanel projectId={projectId} />}
            {activeTab === 'transitions' && <TransitionIntelligencePanel projectId={projectId} />}
            {activeTab === 'sound' && <SoundIntelligencePanel projectId={projectId} />}
          </div>
        </div>
      )}
    </div>
  );
}
