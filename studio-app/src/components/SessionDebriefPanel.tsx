import { useEffect, useState } from "react";
import { studioApi } from "../lib/studioApi";
import type { SessionDebrief, SessionDebriefSummary } from "../lib/studioApi";

interface SessionDebriefPanelProps {
  projectId: string;
}

export function SessionDebriefPanel({ projectId }: SessionDebriefPanelProps) {
  const [currentDebrief, setCurrentDebrief] = useState<SessionDebrief | null>(null);
  const [pastDebriefs, setPastDebriefs] = useState<SessionDebriefSummary[]>([]);
  const [selectedDebriefId, setSelectedDebriefId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copySuccess, setCopySuccess] = useState(false);

  useEffect(() => {
    loadPastDebriefs();
  }, [projectId]);

  const loadPastDebriefs = async () => {
    try {
      const result = await studioApi.listSessionDebriefs(projectId, 5);
      setPastDebriefs(result.debriefs || []);
    } catch (err) {
      console.error("Failed to load past debriefs:", err);
    }
  };

  const generateNewDebrief = async () => {
    setLoading(true);
    setError(null);
    try {
      // Use current time as session end, and 30 minutes ago as session start
      const sessionEnd = new Date().toISOString();
      const sessionStart = new Date(Date.now() - 30 * 60 * 1000).toISOString();

      const debrief = await studioApi.generateSessionDebrief(
        projectId,
        sessionStart,
        sessionEnd
      );
      setCurrentDebrief(debrief);
      setSelectedDebriefId(null);
      await loadPastDebriefs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate debrief");
    } finally {
      setLoading(false);
    }
  };

  const loadDebrief = async (debriefId: string) => {
    setLoading(true);
    setError(null);
    try {
      const debrief = await studioApi.getSessionDebrief(projectId, debriefId);
      setCurrentDebrief(debrief);
      setSelectedDebriefId(debriefId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load debrief");
    } finally {
      setLoading(false);
    }
  };

  const exportAsText = () => {
    if (!currentDebrief) return;

    const text = `
SESSION DEBRIEF
Generated: ${new Date(currentDebrief.generated_at).toLocaleString()}
Session: ${new Date(currentDebrief.session_start).toLocaleString()} - ${new Date(currentDebrief.session_end).toLocaleString()}

DECISIONS MADE
${currentDebrief.decisions_made.map((d) => `• ${d.description}${d.scene ? ` (${d.scene})` : ""}`).join("\n")}

WHAT CHANGED
${currentDebrief.what_changed.map((c) => `• ${c}`).join("\n")}

UNRESOLVED ITEMS
${currentDebrief.unresolved_items.map((u) => `• ${u.item}\n  Why: ${u.why}\n  Next: ${u.suggested_next}`).join("\n\n")}

CONTINUITY STATE
${currentDebrief.continuity_state}

${currentDebrief.film_dna_drift ? `FILM DNA DRIFT\n${currentDebrief.film_dna_drift}\n\n` : ""}NEXT SESSION FOCUS
${currentDebrief.next_session_focus.map((f) => `• ${f}`).join("\n")}

ADVISORY
${currentDebrief.advisory}
    `.trim();

    navigator.clipboard.writeText(text).then(() => {
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    });
  };

  return (
    <div className="h-full flex flex-col bg-slate-900 text-slate-200">
      {/* Header */}
      <div className="flex-none border-b border-slate-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-slate-100">Session Debrief</h2>
            <p className="text-sm text-slate-400 mt-1">
              One-page summary of what was decided, what changed, and what's next
            </p>
          </div>
          <button
            onClick={generateNewDebrief}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-md text-sm font-medium transition-colors"
          >
            {loading ? "Generating..." : "Generate Debrief"}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-6 space-y-6">
          {error && (
            <div className="bg-red-900/20 border border-red-700 rounded-md px-4 py-3 text-red-300 text-sm">
              {error}
            </div>
          )}

          {/* Current Debrief */}
          {currentDebrief && (
            <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
              {/* Debrief Header */}
              <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium text-slate-300">
                    {new Date(currentDebrief.session_start).toLocaleString()} -{" "}
                    {new Date(currentDebrief.session_end).toLocaleString()}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    Generated {new Date(currentDebrief.generated_at).toLocaleString()}
                  </div>
                </div>
                <button
                  onClick={exportAsText}
                  className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded text-xs font-medium transition-colors"
                >
                  {copySuccess ? "Copied ✓" : "Export as Text"}
                </button>
              </div>

              {/* Debrief Content */}
              <div className="px-6 py-5 space-y-6">
                {/* Decisions Made */}
                <section>
                  <h3 className="text-sm font-semibold text-slate-300 mb-3">
                    Decisions Made
                  </h3>
                  <ul className="space-y-2">
                    {currentDebrief.decisions_made.map((decision, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-slate-400">
                        <span className="text-slate-600 mt-0.5">•</span>
                        <span>
                          {decision.description}
                          {decision.scene && (
                            <span className="text-slate-500 ml-1">({decision.scene})</span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>

                {/* What Changed */}
                <section>
                  <h3 className="text-sm font-semibold text-slate-300 mb-3">
                    What Changed
                  </h3>
                  <ul className="space-y-2">
                    {currentDebrief.what_changed.map((change, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-slate-400">
                        <span className="text-slate-600 mt-0.5">•</span>
                        <span>{change}</span>
                      </li>
                    ))}
                  </ul>
                </section>

                {/* Unresolved Items */}
                {currentDebrief.unresolved_items.length > 0 && (
                  <section>
                    <h3 className="text-sm font-semibold text-slate-300 mb-3">
                      Unresolved Items
                    </h3>
                    <div className="space-y-3">
                      {currentDebrief.unresolved_items.map((item, idx) => (
                        <div
                          key={idx}
                          className="bg-amber-900/10 border border-amber-700/30 rounded-md px-4 py-3"
                        >
                          <div className="text-sm font-medium text-amber-300">
                            {item.item}
                          </div>
                          <div className="text-xs text-slate-400 mt-1">
                            <span className="text-slate-500">Why:</span> {item.why}
                          </div>
                          <div className="text-xs text-slate-400 mt-1">
                            <span className="text-slate-500">Next:</span> {item.suggested_next}
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {/* Continuity State */}
                <section>
                  <h3 className="text-sm font-semibold text-slate-300 mb-3">
                    Continuity State
                  </h3>
                  <p className="text-sm text-slate-400 leading-relaxed">
                    {currentDebrief.continuity_state}
                  </p>
                </section>

                {/* Film DNA Drift */}
                {currentDebrief.film_dna_drift && (
                  <section>
                    <h3 className="text-sm font-semibold text-slate-300 mb-3">
                      Film DNA Drift
                    </h3>
                    <p className="text-sm text-slate-400 leading-relaxed">
                      {currentDebrief.film_dna_drift}
                    </p>
                  </section>
                )}

                {/* Next Session Focus */}
                <section>
                  <h3 className="text-sm font-semibold text-slate-300 mb-3">
                    Next Session Focus
                  </h3>
                  <ul className="space-y-2">
                    {currentDebrief.next_session_focus.map((focus, idx) => (
                      <li
                        key={idx}
                        className="flex items-start gap-2 text-sm text-blue-300 font-medium"
                      >
                        <span className="text-blue-600 mt-0.5">→</span>
                        <span>{focus}</span>
                      </li>
                    ))}
                  </ul>
                </section>

                {/* Advisory */}
                <section className="border-t border-slate-700 pt-5">
                  <h3 className="text-sm font-semibold text-slate-300 mb-3">Advisory</h3>
                  <p className="text-sm text-slate-400 leading-relaxed italic">
                    {currentDebrief.advisory}
                  </p>
                </section>
              </div>
            </div>
          )}

          {/* Past Debriefs */}
          {pastDebriefs.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-slate-300 mb-3">
                Past Debriefs
              </h3>
              <div className="space-y-2">
                {pastDebriefs.map((debrief) => (
                  <button
                    key={debrief.id}
                    onClick={() => loadDebrief(debrief.id)}
                    className={`w-full text-left px-4 py-3 rounded-md border transition-colors ${
                      selectedDebriefId === debrief.id
                        ? "bg-slate-700 border-slate-600"
                        : "bg-slate-800 border-slate-700 hover:bg-slate-750"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="text-xs text-slate-400">
                          {new Date(debrief.session_start).toLocaleString()} -{" "}
                          {new Date(debrief.session_end).toLocaleString()}
                        </div>
                        <div className="text-sm text-slate-300 mt-1 line-clamp-2">
                          {debrief.advisory}
                        </div>
                      </div>
                      <div className="text-xs text-slate-500 flex-none">
                        {new Date(debrief.generated_at).toLocaleDateString()}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Empty State */}
          {!currentDebrief && !loading && pastDebriefs.length === 0 && (
            <div className="text-center py-12">
              <div className="text-slate-500 text-sm">
                No session debriefs yet. Generate one to see a summary of your work.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
