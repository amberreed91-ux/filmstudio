import { useCallback, useState, useEffect } from "react";
import { studioApi } from "../lib/studioApi";
import type { PitchDeck, PitchDeckSummary, PitchDeckSlide } from "../lib/studioApi";

interface PitchDeckSectionProps {
  projectId: string;
}

export function PitchDeckSection({ projectId }: PitchDeckSectionProps) {
  const [currentDeck, setCurrentDeck] = useState<PitchDeck | null>(null);
  const [pastDecks, setPastDecks] = useState<PitchDeckSummary[]>([]);
  const [selectedDeckId, setSelectedDeckId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingDeckId, setLoadingDeckId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showOptions, setShowOptions] = useState(false);
  const [targetAudience, setTargetAudience] = useState<'festival' | 'investor' | 'general'>('general');

  const loadPastDecks = useCallback(async () => {
    try {
      const result = await studioApi.listPitchDecks(projectId, 5);
      setPastDecks(result.decks || []);
    } catch (err) {
      console.error("Failed to load past decks:", err);
    }
  }, [projectId]);

  useEffect(() => {
    loadPastDecks();
  }, [loadPastDecks]);

  const generateDeck = async () => {
    setLoading(true);
    setError(null);
    try {
      const deck = await studioApi.generatePitchDeck(projectId, targetAudience);
      setCurrentDeck(deck);
      setSelectedDeckId(null);
      setShowOptions(false);
      await loadPastDecks();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate pitch deck");
    } finally {
      setLoading(false);
    }
  };

  const loadDeck = async (deckId: string) => {
    setLoadingDeckId(deckId);
    setError(null);
    try {
      const deck = await studioApi.getPitchDeck(projectId, deckId);
      setCurrentDeck(deck);
      setSelectedDeckId(deckId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load pitch deck");
    } finally {
      setLoadingDeckId(null);
    }
  };

  const copyAllAsText = () => {
    if (!currentDeck) return;

    let text = `${currentDeck.logline}\n\n`;
    text += `Tone: ${currentDeck.tone_statement}\n\n`;
    text += `---\n\n`;

    currentDeck.slides.forEach((slide) => {
      text += `Slide ${slide.slide_number}: ${slide.title}\n`;
      text += `${slide.headline}\n\n`;
      text += `${slide.body}\n`;
      if (slide.visual_suggestion) {
        text += `Visual: ${slide.visual_suggestion}\n`;
      }
      text += `\n---\n\n`;
    });

    text += `\nNote: ${currentDeck.honest_note}\n`;

    navigator.clipboard.writeText(text);
  };

  const getSlideIcon = (type: PitchDeckSlide['type']) => {
    switch (type) {
      case 'logline': return '📝';
      case 'concept': return '💡';
      case 'visual_language': return '🎨';
      case 'character': return '👤';
      case 'arc': return '📈';
      case 'tone': return '🎭';
      case 'production_note': return '🎬';
      default: return '•';
    }
  };

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-300">Pitch Deck</h3>
        <button type="button"
          onClick={() => setShowOptions(!showOptions)}
          disabled={loading}
          aria-busy={loading}
          className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-md text-sm font-medium transition-colors"
        >
          {loading ? "Generating..." : "Generate Draft"}
        </button>
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-700 rounded-md px-4 py-3 text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Options Panel */}
      {showOptions && (
        <div className="bg-slate-750 rounded-md p-4 space-y-4">
          <div>
            <label className="block text-xs text-slate-400 mb-2">Target Audience</label>
            <select
              value={targetAudience}
              onChange={(e) => setTargetAudience(e.target.value as 'festival' | 'investor' | 'general')}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-md text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="general">General</option>
              <option value="festival">Festival</option>
              <option value="investor">Investor</option>
            </select>
          </div>

          <div className="flex gap-3">
            <button type="button"
              onClick={generateDeck}
              disabled={loading}
              aria-busy={loading}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-md text-sm font-medium transition-colors"
            >
              Generate Draft
            </button>
            <button type="button"
              onClick={() => setShowOptions(false)}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-md text-sm font-medium transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Current Deck */}
      {currentDeck && (
        <div className="space-y-4">
          {/* Honest Note */}
          <div className="bg-amber-900/10 border border-amber-700/30 rounded-md px-4 py-3">
            <div className="text-sm text-amber-300">{currentDeck.honest_note}</div>
          </div>

          {/* Logline and Tone */}
          <div className="bg-slate-750 rounded-md p-4 space-y-3">
            <div>
              <div className="text-xs text-slate-500 mb-1">Logline</div>
              <div className="text-sm text-slate-200">{currentDeck.logline}</div>
            </div>
            <div>
              <div className="text-xs text-slate-500 mb-1">Tone</div>
              <div className="text-sm text-slate-200">{currentDeck.tone_statement}</div>
            </div>
          </div>

          {/* Slides */}
          <div className="space-y-3">
            {currentDeck.slides.map((slide) => (
              <div
                key={slide.slide_number}
                className="bg-slate-750 rounded-md p-4 space-y-2"
              >
                <div className="flex items-start gap-3">
                  <div className="text-2xl flex-none">{getSlideIcon(slide.type)}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="text-xs text-slate-500">
                        Slide {slide.slide_number}
                      </div>
                      <div className="text-xs text-slate-600">•</div>
                      <div className="text-xs text-slate-500">{slide.title}</div>
                    </div>
                    <div className="text-lg font-medium text-slate-200 mb-2">
                      {slide.headline}
                    </div>
                    <div className="text-sm text-slate-300 leading-relaxed mb-2">
                      {slide.body}
                    </div>
                    {slide.visual_suggestion && (
                      <div className="text-xs text-slate-500 italic">
                        Visual: {slide.visual_suggestion}
                      </div>
                    )}
                    <div className="text-xs text-slate-600 mt-2">
                      Source: {slide.data_source.replace(/_/g, ' ')}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <button type="button"
              onClick={copyAllAsText}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-md text-sm font-medium transition-colors"
            >
              📋 Copy All as Text
            </button>
          </div>

          {/* Uncertainty Notes */}
          {currentDeck.uncertainty_notes.length > 0 && (
            <div className="bg-slate-750 rounded-md p-4">
              <div className="text-xs text-slate-500 mb-2">Uncertainty Notes</div>
              <ul className="space-y-1">
                {currentDeck.uncertainty_notes.map((note, idx) => (
                  <li key={idx} className="text-xs text-slate-400">
                    • {note}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Advisory */}
          <div className="text-xs text-slate-500 italic">
            {currentDeck.advisory}
          </div>
        </div>
      )}

      {/* Past Decks */}
      {pastDecks.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-slate-400 mb-2">Past Decks</h4>
          <div className="space-y-2">
            {pastDecks.map((deck) => (
              <button type="button"
                key={deck.deck_id}
                onClick={() => loadDeck(deck.deck_id)}
                disabled={loadingDeckId === deck.deck_id}
                aria-busy={loadingDeckId === deck.deck_id}
                className={`w-full text-left px-3 py-2 rounded-md border transition-colors text-sm disabled:opacity-50 ${
                  selectedDeckId === deck.deck_id
                    ? "bg-slate-700 border-slate-600"
                    : "bg-slate-750 border-slate-700 hover:bg-slate-700"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-slate-300 capitalize">{deck.target_audience}</div>
                  <div className="text-xs text-slate-500">
                    {new Date(deck.created_at).toLocaleDateString()}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!currentDeck && !loading && !showOptions && pastDecks.length === 0 && (
        <div className="text-center py-8">
          <div className="text-slate-500 text-sm">
            No pitch decks yet. Click "Generate Draft" to create your first pitch deck.
          </div>
        </div>
      )}
    </div>
  );
}
