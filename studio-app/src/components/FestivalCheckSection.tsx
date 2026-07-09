import { useState, useEffect } from "react";
import { studioApi } from "../lib/studioApi";
import type { FestivalValidationResult, FestivalPresets } from "../lib/studioApi";

interface FestivalCheckSectionProps {
  projectId: string;
  packageId: string;
}

export function FestivalCheckSection({ projectId, packageId }: FestivalCheckSectionProps) {
  const [presets, setPresets] = useState<FestivalPresets>({});
  const [selectedPreset, setSelectedPreset] = useState<string>("sundance");
  const [validationResult, setValidationResult] = useState<FestivalValidationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadPresets();
  }, []);

  const loadPresets = async () => {
    try {
      const result = await studioApi.getFestivalPresets();
      setPresets(result.presets || {});
    } catch (err) {
      console.error("Failed to load festival presets:", err);
    }
  };

  const runCheck = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await studioApi.validateForFestival(
        projectId,
        packageId,
        { preset: selectedPreset }
      );
      setValidationResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run festival check");
    } finally {
      setLoading(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "met":
        return <span className="text-green-400">✓</span>;
      case "unknown":
        return <span className="text-amber-400">?</span>;
      case "unmet":
        return <span className="text-red-400">⚠</span>;
      default:
        return <span className="text-slate-500">•</span>;
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case "met":
        return "Met";
      case "unknown":
        return "Unknown";
      case "unmet":
        return "Needs attention";
      default:
        return "Unknown";
    }
  };

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 space-y-4">
      <h3 className="text-sm font-semibold text-slate-300">Festival Check</h3>

      {/* Preset Selector */}
      <div>
        <label className="block text-xs text-slate-400 mb-2">Festival</label>
        <select
          value={selectedPreset}
          onChange={(e) => setSelectedPreset(e.target.value)}
          className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-md text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {Object.keys(presets).map((key) => (
            <option key={key} value={key}>
              {presets[key].festival_name || key}
            </option>
          ))}
        </select>
      </div>

      {/* Run Check Button */}
      <button
        onClick={runCheck}
        disabled={loading}
        className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-md text-sm font-medium transition-colors"
      >
        {loading ? "Checking..." : "Run Check"}
      </button>

      {/* Error */}
      {error && (
        <div className="bg-red-900/20 border border-red-700 rounded-md px-4 py-3 text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Results */}
      {validationResult && (
        <div className="space-y-4 pt-2">
          {/* Advisory */}
          <div className="text-sm text-slate-400 leading-relaxed">
            {validationResult.advisory}
          </div>

          {/* Flags List */}
          <div className="space-y-2">
            {validationResult.flags.map((flag, idx) => (
              <div
                key={idx}
                className="flex items-start gap-3 px-3 py-2 bg-slate-750 rounded-md"
              >
                <div className="flex-none mt-0.5 text-lg">
                  {getStatusIcon(flag.status)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-slate-300">{flag.requirement}</div>
                  {flag.note && (
                    <div className="text-xs text-slate-500 mt-1">{flag.note}</div>
                  )}
                  <div className="text-xs text-slate-600 mt-1">
                    {getStatusLabel(flag.status)}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Honest Note */}
          <div className="text-xs text-slate-500 italic pt-2 border-t border-slate-700">
            {validationResult.honest_note}
          </div>
        </div>
      )}
    </div>
  );
}
