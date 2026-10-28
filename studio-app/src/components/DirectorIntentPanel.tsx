import { useEffect, useState, useCallback } from "react";
import { getDirectorIntent, updateDirectorIntent } from "../lib/studioApi";
import type { DirectorIntent, DirectorIntentUpdate } from "../lib/studioApi";

interface DirectorIntentPanelProps {
  projectId: string;
}

export function DirectorIntentPanel({ projectId }: DirectorIntentPanelProps) {
  const [intent, setIntent] = useState<DirectorIntent | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveConfirmation, setSaveConfirmation] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [genre, setGenre] = useState("");
  const [toneReferences, setToneReferences] = useState<string[]>([]);
  const [toneReferenceInput, setToneReferenceInput] = useState("");
  const [emotionalTarget, setEmotionalTarget] = useState("");
  const [visualReferences, setVisualReferences] = useState<string[]>([]);
  const [visualReferenceInput, setVisualReferenceInput] = useState("");
  const [whatSuccessLooksLike, setWhatSuccessLooksLike] = useState("");
  const [whatToAvoid, setWhatToAvoid] = useState<string[]>([]);
  const [whatToAvoidInput, setWhatToAvoidInput] = useState("");

  const loadIntent = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getDirectorIntent(projectId);
      setIntent(data);

      // Populate form fields
      setGenre(data.genre || "");
      setToneReferences(data.tone_references || []);
      setEmotionalTarget(data.emotional_target || "");
      setVisualReferences(data.visual_references || []);
      setWhatSuccessLooksLike(data.what_success_looks_like || "");
      setWhatToAvoid(data.what_to_avoid || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load director intent");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadIntent();
  }, [loadIntent]);

  const saveIntent = useCallback(
    async (update: DirectorIntentUpdate) => {
      try {
        setSaving(true);
        const updated = await updateDirectorIntent(projectId, update);
        setIntent(updated);

        // Show confirmation briefly
        setSaveConfirmation(true);
        setTimeout(() => setSaveConfirmation(false), 2000);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save director intent");
      } finally {
        setSaving(false);
      }
    },
    [projectId]
  );

  // Auto-save handlers (on blur)
  const handleGenreBlur = () => {
    if (genre !== (intent?.genre || "")) {
      saveIntent({ genre: genre || null });
    }
  };

  const handleEmotionalTargetBlur = () => {
    if (emotionalTarget !== (intent?.emotional_target || "")) {
      saveIntent({ emotional_target: emotionalTarget || null });
    }
  };

  const handleWhatSuccessLooksLikeBlur = () => {
    if (whatSuccessLooksLike !== (intent?.what_success_looks_like || "")) {
      saveIntent({ what_success_looks_like: whatSuccessLooksLike || null });
    }
  };

  // Tag input handlers
  const handleAddToneReference = () => {
    if (toneReferenceInput.trim()) {
      const newRefs = [...toneReferences, toneReferenceInput.trim()];
      setToneReferences(newRefs);
      setToneReferenceInput("");
      saveIntent({ tone_references: newRefs });
    }
  };

  const handleRemoveToneReference = (index: number) => {
    const newRefs = toneReferences.filter((_, i) => i !== index);
    setToneReferences(newRefs);
    saveIntent({ tone_references: newRefs });
  };

  const handleAddVisualReference = () => {
    if (visualReferenceInput.trim()) {
      const newRefs = [...visualReferences, visualReferenceInput.trim()];
      setVisualReferences(newRefs);
      setVisualReferenceInput("");
      saveIntent({ visual_references: newRefs });
    }
  };

  const handleRemoveVisualReference = (index: number) => {
    const newRefs = visualReferences.filter((_, i) => i !== index);
    setVisualReferences(newRefs);
    saveIntent({ visual_references: newRefs });
  };

  const handleAddWhatToAvoid = () => {
    if (whatToAvoidInput.trim()) {
      const newItems = [...whatToAvoid, whatToAvoidInput.trim()];
      setWhatToAvoid(newItems);
      setWhatToAvoidInput("");
      saveIntent({ what_to_avoid: newItems });
    }
  };

  const handleRemoveWhatToAvoid = (index: number) => {
    const newItems = whatToAvoid.filter((_, i) => i !== index);
    setWhatToAvoid(newItems);
    saveIntent({ what_to_avoid: newItems });
  };

  if (loading) {
    return (
      <div className="p-6 text-center text-slate-400">
        <div className="animate-pulse">Loading director intent...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-center text-red-400">
        <div>{error}</div>
        <button type="button"
          onClick={loadIntent}
          disabled={loading}
          aria-busy={loading}
          className="mt-4 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded text-sm disabled:opacity-50"
        >
          Retry
        </button>
      </div>
    );
  }

  const isEmpty =
    !genre &&
    toneReferences.length === 0 &&
    !emotionalTarget &&
    visualReferences.length === 0 &&
    !whatSuccessLooksLike &&
    whatToAvoid.length === 0;

  return (
    <div className="p-6 space-y-6">
      {/* Header with save confirmation */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-slate-200">Director Intent</h3>
        {saveConfirmation && (
          <div className="text-sm text-green-400 animate-fade-in">
            Intent saved ✓
          </div>
        )}
        {saving && (
          <div className="text-sm text-slate-400">
            Saving...
          </div>
        )}
      </div>

      {/* Empty state prompt */}
      {isEmpty && (
        <div className="bg-slate-800/50 rounded-lg p-6 text-center">
          <div className="text-slate-400 mb-2">Tell the studio what this film is trying to be.</div>
          <div className="text-sm text-slate-500">
            Your creative vision will guide every AI decision downstream.
          </div>
        </div>
      )}

      {/* Form fields */}
      <div className="space-y-6">
        {/* Genre */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Genre
          </label>
          <input
            type="text"
            value={genre}
            onChange={(e) => setGenre(e.target.value)}
            onBlur={handleGenreBlur}
            placeholder="e.g., Neo-noir thriller, Sci-fi drama"
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* Tone References */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Tone References
          </label>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              value={toneReferenceInput}
              onChange={(e) => setToneReferenceInput(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleAddToneReference();
                }
              }}
              placeholder="e.g., Arrival, Blade Runner 2049"
              className="flex-1 px-3 py-2 bg-slate-800 border border-slate-700 rounded text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
            <button type="button"
              onClick={handleAddToneReference}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium"
            >
              Add
            </button>
          </div>
          {toneReferences.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {toneReferences.map((ref, i) => (
                <span
                  key={i}
                  className="px-3 py-1 bg-slate-700 text-slate-300 rounded text-sm flex items-center gap-2"
                >
                  {ref}
                  <button type="button"
                    onClick={() => handleRemoveToneReference(i)}
                    className="text-slate-500 hover:text-slate-300"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Emotional Target */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Emotional Target
          </label>
          <textarea
            value={emotionalTarget}
            onChange={(e) => setEmotionalTarget(e.target.value)}
            onBlur={handleEmotionalTargetBlur}
            placeholder="What should the film make audiences feel?"
            rows={3}
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* Visual References */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Visual References
          </label>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              value={visualReferenceInput}
              onChange={(e) => setVisualReferenceInput(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleAddVisualReference();
                }
              }}
              placeholder="e.g., Deakins lighting, handheld intimacy"
              className="flex-1 px-3 py-2 bg-slate-800 border border-slate-700 rounded text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
            <button type="button"
              onClick={handleAddVisualReference}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium"
            >
              Add
            </button>
          </div>
          {visualReferences.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {visualReferences.map((ref, i) => (
                <span
                  key={i}
                  className="px-3 py-1 bg-slate-700 text-slate-300 rounded text-sm flex items-center gap-2"
                >
                  {ref}
                  <button type="button"
                    onClick={() => handleRemoveVisualReference(i)}
                    className="text-slate-500 hover:text-slate-300"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        {/* What Success Looks Like */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            What Success Looks Like
          </label>
          <textarea
            value={whatSuccessLooksLike}
            onChange={(e) => setWhatSuccessLooksLike(e.target.value)}
            onBlur={handleWhatSuccessLooksLikeBlur}
            placeholder="Describe what a successful film would achieve"
            rows={3}
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* What To Avoid */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            What To Avoid
          </label>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              value={whatToAvoidInput}
              onChange={(e) => setWhatToAvoidInput(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleAddWhatToAvoid();
                }
              }}
              placeholder="e.g., Heavy exposition, melodrama"
              className="flex-1 px-3 py-2 bg-slate-800 border border-slate-700 rounded text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
            <button type="button"
              onClick={handleAddWhatToAvoid}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium"
            >
              Add
            </button>
          </div>
          {whatToAvoid.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {whatToAvoid.map((item, i) => (
                <span
                  key={i}
                  className="px-3 py-1 bg-slate-700 text-slate-300 rounded text-sm flex items-center gap-2"
                >
                  {item}
                  <button type="button"
                    onClick={() => handleRemoveWhatToAvoid(i)}
                    className="text-slate-500 hover:text-slate-300"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Metadata */}
      {intent && intent.captured_at && (
        <div className="text-xs text-slate-600 pt-4 border-t border-slate-800">
          <div>Created: {new Date(intent.captured_at).toLocaleString()}</div>
          {intent.last_updated && (
            <div>Last updated: {new Date(intent.last_updated).toLocaleString()}</div>
          )}
        </div>
      )}
    </div>
  );
}

// Intent Summary Card Component (for displaying in room headers)
interface DirectorIntentSummaryProps {
  projectId: string;
}

export function DirectorIntentSummary({ projectId }: DirectorIntentSummaryProps) {
  const [intent, setIntent] = useState<DirectorIntent | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadIntent = async () => {
      try {
        const data = await getDirectorIntent(projectId);
        setIntent(data);
      } catch {
        // Silent fail - intent is optional
      } finally {
        setLoading(false);
      }
    };

    loadIntent();
  }, [projectId]);

  if (loading || !intent) {
    return null;
  }

  const isEmpty =
    !intent.genre &&
    intent.tone_references.length === 0 &&
    !intent.emotional_target &&
    intent.visual_references.length === 0 &&
    !intent.what_success_looks_like &&
    intent.what_to_avoid.length === 0;

  if (isEmpty) {
    return null;
  }

  return (
    <div className="bg-slate-800/30 border border-slate-700/50 rounded px-3 py-2 text-xs">
      <div className="flex items-center gap-2 text-slate-400 mb-1">
        <span className="text-blue-400">◆</span>
        <span className="font-medium">Director Intent</span>
      </div>
      <div className="text-slate-500 space-y-1">
        {intent.genre && <div>Genre: {intent.genre}</div>}
        {intent.emotional_target && (
          <div className="truncate">Target: {intent.emotional_target}</div>
        )}
      </div>
    </div>
  );
}
