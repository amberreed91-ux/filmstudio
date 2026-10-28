import { useCallback, useEffect, useState, Fragment } from "react";
import { studioApi } from "../lib/studioApi";
import type { CharacterJourney, ArcCompleteness } from "../lib/studioApi";

interface VisualLanguage {
  dominant_motifs: string[];
  color_palette_notes: string;
  recurring_shot_types: string[];
  lighting_character: string;
}

interface EmotionalArc {
  opening_register: string;
  closing_register: string;
  peak_tension_scene: string;
  arc_shape: string;
}

interface TonalIdentity {
  primary_tone: string;
  secondary_tone: string | null;
  tone_consistency: string;
  genre_signals: string[];
}

interface CharacterRosterEntry {
  name: string;
  scenes_present: number;
  first_appearance: string;
  last_appearance: string;
  emotional_trajectory: string;
}

interface CharacterJourneyMap {
  characters: CharacterJourney[];
  dramatic_irony_scenes: string[];
  advisory: string;
  uncertainty_notes: string[];
  generated_at: string;
}

interface FilmDNA {
  film_id: string;
  visual_language: VisualLanguage;
  emotional_arc: EmotionalArc;
  tonal_identity: TonalIdentity;
  character_roster: CharacterRosterEntry[];
  character_journeys: CharacterJourneyMap;
  arc_completeness: ArcCompleteness;
  production_notes: string[];
  uncertainty_notes: string[];
  generated_at: string;
  scene_count: number;
  version_id: string;
}

interface FilmDNAPanelProps {
  projectId: string;
}

function getTensionColor(tensionRead: string): string {
  switch (tensionRead) {
    case "low":
      return "bg-slate-500";
    case "building":
      return "bg-amber-500";
    case "peak":
      return "bg-red-400";
    case "releasing":
      return "bg-green-400";
    default:
      return "bg-slate-600";
  }
}

function CharacterJourneyTimeline({ character }: { character: CharacterJourney }) {
  const [expanded, setExpanded] = useState(false);

  const majorCharacters = character.journey.filter((j) => j.order_index >= 0);

  return (
    <div className="border-b border-slate-700 last:border-0">
      <button type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-slate-800/30 transition-colors text-left"
      >
        <div className="flex-1">
          <div className="text-sm font-medium text-slate-300">{character.name}</div>
          <div className="text-xs text-slate-500 mt-1">{character.arc_summary}</div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-xs text-slate-400">{character.total_scenes} scenes</div>
          <div className="text-slate-600">{expanded ? "▼" : "▶"}</div>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          {/* Journey timeline */}
          <div className="space-y-2 mt-2">
            {majorCharacters.map((entry, idx) => (
              <div
                key={entry.scene_id}
                className="flex items-start gap-3 pl-4 border-l-2 border-slate-700"
              >
                <div className="flex-shrink-0 w-6 h-6 rounded-full bg-slate-700 flex items-center justify-center text-xs text-slate-400">
                  {idx + 1}
                </div>
                <div className="flex-1 pb-3">
                  <div className="text-sm text-slate-300 font-medium">
                    {entry.scene_title}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    Emotional state: {entry.emotional_state}
                  </div>
                  {entry.knowledge_events.length > 0 && (
                    <div className="text-xs text-slate-500 mt-1">
                      Learned: {entry.knowledge_events.join(", ")}
                    </div>
                  )}
                  {entry.dramatic_irony && entry.irony_note && (
                    <div className="text-xs text-amber-400 mt-1 flex items-center gap-1">
                      <span className="text-amber-500">⚠</span>
                      <span>{entry.irony_note}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Unresolved knowledge */}
          {character.unresolved_knowledge.length > 0 && (
            <div className="mt-3 p-3 bg-amber-900/20 rounded border border-amber-900/30">
              <div className="text-xs text-amber-400 font-medium mb-1">
                Unresolved Knowledge
              </div>
              <div className="text-xs text-amber-300/70">
                {character.unresolved_knowledge.join(", ")}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function FilmDNAPanel({ projectId }: FilmDNAPanelProps) {
  const [dna, setDna] = useState<FilmDNA | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDNA = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await studioApi.getFilmDNA(projectId);
      setDna(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Film DNA");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const handleRefresh = async () => {
    try {
      setRefreshing(true);
      await studioApi.refreshFilmDNA(projectId);
      // Poll for updated DNA after a short delay
      setTimeout(() => {
        loadDNA();
        setRefreshing(false);
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh Film DNA");
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadDNA();
  }, [loadDNA]);

  if (loading) {
    return (
      <div className="p-6 text-center text-slate-400">
        <div className="animate-pulse">Loading Film DNA...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-center text-red-400">
        <div>{error}</div>
        <button type="button"
          onClick={loadDNA}
          disabled={loading}
          aria-busy={loading}
          className="mt-4 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded text-sm disabled:opacity-50"
        >
          {loading ? "Retrying..." : "Retry"}
        </button>
      </div>
    );
  }

  if (!dna) {
    return (
      <div className="p-6 text-center text-slate-400">
        No Film DNA available
      </div>
    );
  }

  // Empty state for insufficient scenes
  if (dna.scene_count < 3) {
    return (
      <div className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-medium text-slate-200">Film DNA</h3>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-6 text-center">
          <div className="text-slate-400 mb-2">Insufficient Data</div>
          <div className="text-sm text-slate-500">
            Film DNA requires at least 3 scenes for reliable analysis.
          </div>
          <div className="text-sm text-slate-500 mt-1">
            Current scene count: {dna.scene_count}
          </div>
        </div>
        {dna.uncertainty_notes.length > 0 && (
          <div className="text-xs italic text-slate-500 space-y-1">
            {dna.uncertainty_notes.map((note, i) => (
              <div key={i}>{note}</div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-slate-200">Film DNA</h3>
        <button type="button"
          onClick={handleRefresh}
          disabled={refreshing}
          aria-busy={refreshing}
          className="px-3 py-1 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 rounded text-sm transition-colors"
        >
          {refreshing ? "Refreshing..." : "Refresh DNA"}
        </button>
      </div>

      {/* Visual Language */}
      <section className="space-y-3">
        <h4 className="text-sm font-medium text-slate-300 uppercase tracking-wide">
          Visual Language
        </h4>
        <div className="bg-slate-800/50 rounded-lg p-4 space-y-3">
          {dna.visual_language.dominant_motifs.length > 0 && (
            <div>
              <div className="text-xs text-slate-400 mb-2">Dominant Motifs</div>
              <div className="flex flex-wrap gap-2">
                {dna.visual_language.dominant_motifs.map((motif, i) => (
                  <span
                    key={i}
                    className="px-2 py-1 bg-slate-700 text-slate-300 rounded text-xs"
                  >
                    {motif}
                  </span>
                ))}
              </div>
            </div>
          )}
          <div>
            <div className="text-xs text-slate-400 mb-1">Lighting Character</div>
            <div className="text-sm text-slate-300">
              {dna.visual_language.lighting_character}
            </div>
          </div>
          {dna.visual_language.color_palette_notes && (
            <div>
              <div className="text-xs text-slate-400 mb-1">Color Palette</div>
              <div className="text-sm text-slate-300">
                {dna.visual_language.color_palette_notes}
              </div>
            </div>
          )}
          {dna.visual_language.recurring_shot_types.length > 0 && (
            <div>
              <div className="text-xs text-slate-400 mb-2">Recurring Shot Types</div>
              <div className="flex flex-wrap gap-2">
                {dna.visual_language.recurring_shot_types.map((shot, i) => (
                  <span
                    key={i}
                    className="px-2 py-1 bg-slate-700 text-slate-300 rounded text-xs"
                  >
                    {shot}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Emotional Arc */}
      <section className="space-y-3">
        <h4 className="text-sm font-medium text-slate-300 uppercase tracking-wide">
          Emotional Arc
        </h4>
        <div className="bg-slate-800/50 rounded-lg p-4">
          <div className="flex items-center justify-between text-sm">
            <div className="flex-1 text-center">
              <div className="text-xs text-slate-400 mb-1">Opening</div>
              <div className="text-slate-300 font-medium">
                {dna.emotional_arc.opening_register}
              </div>
            </div>
            <div className="flex-1 text-center px-4">
              <div className="text-2xl text-slate-600">→</div>
              <div className="text-xs text-slate-400 mt-1">
                {dna.emotional_arc.arc_shape}
              </div>
            </div>
            <div className="flex-1 text-center">
              <div className="text-xs text-slate-400 mb-1">Peak</div>
              <div className="text-slate-300 font-medium text-xs">
                {dna.emotional_arc.peak_tension_scene || "—"}
              </div>
            </div>
            <div className="flex-1 text-center px-4">
              <div className="text-2xl text-slate-600">→</div>
            </div>
            <div className="flex-1 text-center">
              <div className="text-xs text-slate-400 mb-1">Closing</div>
              <div className="text-slate-300 font-medium">
                {dna.emotional_arc.closing_register}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Tonal Identity */}
      <section className="space-y-3">
        <h4 className="text-sm font-medium text-slate-300 uppercase tracking-wide">
          Tonal Identity
        </h4>
        <div className="bg-slate-800/50 rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-3">
            <span className="px-3 py-1 bg-blue-900/30 text-blue-300 rounded text-sm font-medium">
              {dna.tonal_identity.primary_tone}
            </span>
            {dna.tonal_identity.secondary_tone && (
              <>
                <span className="text-slate-600">+</span>
                <span className="px-3 py-1 bg-blue-900/20 text-blue-400 rounded text-sm">
                  {dna.tonal_identity.secondary_tone}
                </span>
              </>
            )}
          </div>
          <div>
            <div className="text-xs text-slate-400 mb-1">Consistency</div>
            <div className="text-sm text-slate-300">
              {dna.tonal_identity.tone_consistency}
            </div>
          </div>
          {dna.tonal_identity.genre_signals.length > 0 && (
            <div>
              <div className="text-xs text-slate-400 mb-2">Genre Signals</div>
              <div className="flex flex-wrap gap-2">
                {dna.tonal_identity.genre_signals.map((signal, i) => (
                  <span
                    key={i}
                    className="px-2 py-1 bg-slate-700 text-slate-300 rounded text-xs"
                  >
                    {signal}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Character Roster */}
      {dna.character_roster.length > 0 && (
        <section className="space-y-3">
          <h4 className="text-sm font-medium text-slate-300 uppercase tracking-wide">
            Character Roster
          </h4>
          <div className="bg-slate-800/50 rounded-lg p-4 space-y-2">
            {dna.character_roster.map((char, i) => (
              <div
                key={i}
                className="flex items-start justify-between py-2 border-b border-slate-700 last:border-0"
              >
                <div className="flex-1">
                  <div className="text-sm font-medium text-slate-300">
                    {char.name}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {char.emotional_trajectory}
                  </div>
                </div>
                <div className="text-right text-xs text-slate-400">
                  <div>{char.scenes_present} scenes</div>
                  <div className="text-slate-600 mt-1">
                    {char.first_appearance} → {char.last_appearance}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Character Journeys */}
      {dna.character_journeys && dna.character_journeys.characters.length > 0 && (
        <section className="space-y-3">
          <h4 className="text-sm font-medium text-slate-300 uppercase tracking-wide">
            Character Journeys
          </h4>

          {/* Dramatic irony note */}
          {dna.character_journeys.dramatic_irony_scenes.length > 0 && (
            <div className="text-xs text-amber-400 bg-amber-900/20 rounded px-3 py-2 border border-amber-900/30">
              Dramatic irony present in {dna.character_journeys.dramatic_irony_scenes.length} scene(s)
            </div>
          )}

          {/* Major characters (3+ scenes) */}
          <div className="bg-slate-800/50 rounded-lg overflow-hidden">
            {dna.character_journeys.characters
              .filter((char) => char.total_scenes >= 3)
              .map((char) => (
                <CharacterJourneyTimeline key={char.name} character={char} />
              ))}
          </div>

          {/* Minor characters (1-2 scenes) */}
          {dna.character_journeys.characters.filter((char) => char.total_scenes < 3)
            .length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-slate-400 uppercase tracking-wide">
                Minor Characters
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3 space-y-1">
                {dna.character_journeys.characters
                  .filter((char) => char.total_scenes < 3)
                  .map((char) => (
                    <div
                      key={char.name}
                      className="flex items-center justify-between text-xs py-1"
                    >
                      <span className="text-slate-400">{char.name}</span>
                      <span className="text-slate-600">
                        {char.total_scenes} scene{char.total_scenes > 1 ? "s" : ""}
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Arc Completeness */}
      {dna.arc_completeness && dna.arc_completeness.tension_curve.length > 0 && (
        <section className="space-y-3">
          <h4 className="text-sm font-medium text-slate-300 uppercase tracking-wide">
            Arc
          </h4>

          {/* Use amber framing for incomplete arcs */}
          <div
            className={`rounded-lg p-4 space-y-3 ${
              dna.arc_completeness.arc_read === "incomplete"
                ? "bg-amber-900/20 border border-amber-900/30"
                : "bg-slate-800/50"
            }`}
          >
            {/* Tension curve visualization */}
            <div className="flex items-center gap-2 flex-wrap">
              {dna.arc_completeness.tension_curve.map((entry, idx) => (
                <Fragment key={entry.scene_id}>
                  <div className="flex items-center gap-2">
                    <div
                      className={`w-3 h-3 rounded-full ${getTensionColor(
                        entry.tension_read
                      )}`}
                      title={entry.note}
                    />
                    <span className="text-xs text-slate-400">
                      Scene {entry.order_index + 1}
                    </span>
                  </div>
                  {idx < dna.arc_completeness.tension_curve.length - 1 && (
                    <span className="text-slate-600">→</span>
                  )}
                </Fragment>
              ))}
            </div>

            {/* Legend */}
            <div className="flex items-center gap-4 text-xs text-slate-500">
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-slate-500" />
                <span>low</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-amber-500" />
                <span>building</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-red-400" />
                <span>peak</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-green-400" />
                <span>releasing</span>
              </div>
            </div>

            {/* Resolution read */}
            <div className="text-sm text-slate-300 pt-2 border-t border-slate-700">
              {dna.arc_completeness.resolution_read}
            </div>

            {/* Missing beats */}
            {dna.arc_completeness.missing_beats.length > 0 && (
              <div className="space-y-1">
                <div className="text-xs text-slate-400">Consider:</div>
                <ul className="text-xs text-slate-500 space-y-1 pl-4">
                  {dna.arc_completeness.missing_beats.map((beat, i) => (
                    <li key={i} className="list-disc">
                      {beat}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Confidence note */}
            <div className="text-xs italic text-slate-600 pt-2">
              Arc reads are inherently uncertain without performance context.
            </div>
          </div>
        </section>
      )}

      {/* Production Notes */}
      {dna.production_notes.length > 0 && (
        <section className="space-y-3">
          <h4 className="text-sm font-medium text-slate-300 uppercase tracking-wide">
            Production Notes
          </h4>
          <div className="bg-slate-800/50 rounded-lg p-4 space-y-2">
            {dna.production_notes.map((note, i) => (
              <div key={i} className="text-sm text-slate-400 flex items-start gap-2">
                <span className="text-slate-600">•</span>
                <span>{note}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Uncertainty Notes */}
      {dna.uncertainty_notes.length > 0 && (
        <div className="text-xs italic text-slate-500 space-y-1 pt-4 border-t border-slate-800">
          {dna.uncertainty_notes.map((note, i) => (
            <div key={i}>{note}</div>
          ))}
        </div>
      )}

      {/* Metadata */}
      <div className="text-xs text-slate-600 pt-4 border-t border-slate-800">
        <div>Generated: {new Date(dna.generated_at).toLocaleString()}</div>
        <div>Scene count: {dna.scene_count}</div>
        {dna.version_id && <div>Version: {dna.version_id}</div>}
      </div>
    </div>
  );
}
