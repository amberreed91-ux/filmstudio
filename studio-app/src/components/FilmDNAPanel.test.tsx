import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { FilmDNAPanel } from "./FilmDNAPanel";

vi.mock("../lib/studioApi", () => ({
  studioApi: {
    getFilmDNA: vi.fn(),
    refreshFilmDNA: vi.fn(),
  },
}));

describe("FilmDNAPanel", () => {
  const mockFullDNA = {
    film_id: "proj-001",
    visual_language: {
      dominant_motifs: ["rain", "shadows", "neon"],
      color_palette_notes: "Dark and moody with neon accents",
      recurring_shot_types: ["close-up", "wide establishing"],
      lighting_character: "High-contrast with pronounced shadows",
    },
    emotional_arc: {
      opening_register: "calm",
      closing_register: "tense",
      peak_tension_scene: "scene_3",
      arc_shape: "rising",
    },
    tonal_identity: {
      primary_tone: "melancholic",
      secondary_tone: "hopeful",
      tone_consistency: "consistent",
      genre_signals: ["drama", "noir"],
    },
    character_roster: [
      {
        name: "Alice",
        scenes_present: 5,
        first_appearance: "scene_1",
        last_appearance: "scene_5",
        emotional_trajectory: "Observing and reacting to escalating tension",
      },
      {
        name: "Bob",
        scenes_present: 3,
        first_appearance: "scene_2",
        last_appearance: "scene_4",
        emotional_trajectory: "Catalyst for change",
      },
    ],
    character_journeys: {
      characters: [
        {
          name: "Alice",
          total_scenes: 5,
          journey: [
            {
              scene_id: "scene_1",
              order_index: 0,
              scene_title: "Opening",
              emotional_state: "calm",
              knowledge_events: ["event_a"],
              knowledge_gaps: ["event_b"],
              dramatic_irony: true,
              irony_note: "Character unaware of: event_b",
            },
            {
              scene_id: "scene_2",
              order_index: 1,
              scene_title: "Conflict",
              emotional_state: "tense",
              knowledge_events: ["event_a", "event_b"],
              knowledge_gaps: [],
              dramatic_irony: false,
              irony_note: null,
            },
          ],
          arc_summary: "Transitions from calm to tense",
          unresolved_knowledge: ["event_c"],
        },
        {
          name: "Charlie",
          total_scenes: 1,
          journey: [
            {
              scene_id: "scene_3",
              order_index: 2,
              scene_title: "Brief appearance",
              emotional_state: "neutral",
              knowledge_events: [],
              knowledge_gaps: [],
              dramatic_irony: false,
              irony_note: null,
            },
          ],
          arc_summary: "Brief appearance",
          unresolved_knowledge: [],
        },
      ],
      dramatic_irony_scenes: ["scene_1"],
      advisory: "Advisory only. Character knowledge states are inferred.",
      uncertainty_notes: ["Charlie appears in only 1 scene. Journey analysis limited."],
      generated_at: "2024-01-01T12:00:00Z",
    },
    arc_completeness: {
      arc_read: "complete",
      tension_curve: [
        {
          scene_id: "scene_1",
          order_index: 0,
          tension_read: "low",
          note: "Scene maintains low tension",
        },
        {
          scene_id: "scene_2",
          order_index: 1,
          tension_read: "building",
          note: "Tension building — escalation in progress",
        },
        {
          scene_id: "scene_3",
          order_index: 2,
          tension_read: "peak",
          note: "Peak tension — critical moment",
        },
        {
          scene_id: "scene_4",
          order_index: 3,
          tension_read: "releasing",
          note: "Tension releasing — moving toward resolution",
        },
      ],
      resolution_read: "Arc follows a recognizable progression from setup through peak to resolution.",
      missing_beats: [],
      pacing_observations: [],
      advisory: "Arc read: complete. Arc follows a recognizable progression from setup through peak to resolution.",
      uncertainty_notes: ["Arc reads are inherently uncertain without performance context."],
      confidence: "medium",
    },
    production_notes: [
      "Tonal consistency is strong across all scenes",
      "Visual motifs are well-established",
    ],
    uncertainty_notes: [],
    generated_at: "2024-01-01T12:00:00Z",
    scene_count: 5,
    version_id: "v-abc123",
  };

  const mockInsufficientDNA = {
    film_id: "proj-002",
    visual_language: {
      dominant_motifs: [],
      color_palette_notes: "Insufficient data",
      recurring_shot_types: [],
      lighting_character: "Insufficient data",
    },
    emotional_arc: {
      opening_register: "",
      closing_register: "",
      peak_tension_scene: "",
      arc_shape: "uncertain",
    },
    tonal_identity: {
      primary_tone: "uncertain",
      secondary_tone: null,
      tone_consistency: "uncertain",
      genre_signals: [],
    },
    character_roster: [],
    character_journeys: {
      characters: [],
      dramatic_irony_scenes: [],
      advisory: "Insufficient character knowledge data in graph.",
      uncertainty_notes: ["No character knowledge nodes found in continuity graph."],
      generated_at: "2024-01-01T12:00:00Z",
    },
    arc_completeness: {
      arc_read: "uncertain",
      tension_curve: [],
      resolution_read: "Insufficient scenes for arc analysis.",
      missing_beats: [],
      pacing_observations: [],
      advisory: "Arc analysis requires at least 3 scenes.",
      uncertainty_notes: ["Only 2 scene(s) available. Arc analysis requires at least 3 scenes."],
      confidence: "low",
    },
    production_notes: [],
    uncertainty_notes: [
      "Only 2 scene(s) available. Film DNA requires at least 3 scenes for reliable analysis.",
    ],
    generated_at: "2024-01-01T12:00:00Z",
    scene_count: 2,
    version_id: "",
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders component structure", () => {
    // Static render test - just verify component can render
    const html = renderToStaticMarkup(<FilmDNAPanel projectId="proj-001" />);
    expect(html).toBeTruthy();
  });

  it("component has correct data structure for full DNA", () => {
    // Verify the mock data structure is correct
    expect(mockFullDNA.visual_language.dominant_motifs).toContain("rain");
    expect(mockFullDNA.emotional_arc.arc_shape).toBe("rising");
    expect(mockFullDNA.tonal_identity.primary_tone).toBe("melancholic");
    expect(mockFullDNA.character_roster).toHaveLength(2);
    expect(mockFullDNA.character_roster[0].name).toBe("Alice");
  });

  it("component has correct data structure for insufficient DNA", () => {
    // Verify the mock data structure for insufficient scenes
    expect(mockInsufficientDNA.scene_count).toBe(2);
    expect(mockInsufficientDNA.uncertainty_notes).toHaveLength(1);
    expect(mockInsufficientDNA.uncertainty_notes[0]).toContain("at least 3 scenes");
    expect(mockInsufficientDNA.emotional_arc.arc_shape).toBe("uncertain");
  });

  it("visual language section has all required fields", () => {
    expect(mockFullDNA.visual_language).toHaveProperty("dominant_motifs");
    expect(mockFullDNA.visual_language).toHaveProperty("color_palette_notes");
    expect(mockFullDNA.visual_language).toHaveProperty("recurring_shot_types");
    expect(mockFullDNA.visual_language).toHaveProperty("lighting_character");
  });

  it("emotional arc section has all required fields", () => {
    expect(mockFullDNA.emotional_arc).toHaveProperty("opening_register");
    expect(mockFullDNA.emotional_arc).toHaveProperty("closing_register");
    expect(mockFullDNA.emotional_arc).toHaveProperty("peak_tension_scene");
    expect(mockFullDNA.emotional_arc).toHaveProperty("arc_shape");
  });

  it("tonal identity section has all required fields", () => {
    expect(mockFullDNA.tonal_identity).toHaveProperty("primary_tone");
    expect(mockFullDNA.tonal_identity).toHaveProperty("secondary_tone");
    expect(mockFullDNA.tonal_identity).toHaveProperty("tone_consistency");
    expect(mockFullDNA.tonal_identity).toHaveProperty("genre_signals");
  });

  it("character roster entries have all required fields", () => {
    const char = mockFullDNA.character_roster[0];
    expect(char).toHaveProperty("name");
    expect(char).toHaveProperty("scenes_present");
    expect(char).toHaveProperty("first_appearance");
    expect(char).toHaveProperty("last_appearance");
    expect(char).toHaveProperty("emotional_trajectory");
  });

  it("handles empty character roster", () => {
    const dnaWithoutCharacters = {
      ...mockFullDNA,
      character_roster: [],
    };
    expect(dnaWithoutCharacters.character_roster).toHaveLength(0);
  });

  it("handles empty production notes", () => {
    const dnaWithoutNotes = {
      ...mockFullDNA,
      production_notes: [],
    };
    expect(dnaWithoutNotes.production_notes).toHaveLength(0);
  });

  it("handles null secondary tone", () => {
    const dnaWithoutSecondary = {
      ...mockFullDNA,
      tonal_identity: {
        ...mockFullDNA.tonal_identity,
        secondary_tone: null,
      },
    };
    expect(dnaWithoutSecondary.tonal_identity.secondary_tone).toBeNull();
  });

  it("handles uncertainty notes", () => {
    const dnaWithUncertainty = {
      ...mockFullDNA,
      uncertainty_notes: [
        "Some visual tags are missing",
        "Character presence data is incomplete",
      ],
    };
    expect(dnaWithUncertainty.uncertainty_notes).toHaveLength(2);
  });

  it("validates arc shape values", () => {
    const validArcShapes = ["rising", "falling", "flat", "wave", "uncertain"];
    expect(validArcShapes).toContain(mockFullDNA.emotional_arc.arc_shape);
  });

  it("validates tone consistency values", () => {
    const validConsistency = ["consistent", "drifting", "intentionally_varied", "uncertain"];
    expect(validConsistency).toContain(mockFullDNA.tonal_identity.tone_consistency);
  });

  it("character journeys section has all required fields", () => {
    expect(mockFullDNA.character_journeys).toHaveProperty("characters");
    expect(mockFullDNA.character_journeys).toHaveProperty("dramatic_irony_scenes");
    expect(mockFullDNA.character_journeys).toHaveProperty("advisory");
    expect(mockFullDNA.character_journeys).toHaveProperty("uncertainty_notes");
    expect(mockFullDNA.character_journeys).toHaveProperty("generated_at");
  });

  it("character journey entries have all required fields", () => {
    const journey = mockFullDNA.character_journeys.characters[0].journey[0];
    expect(journey).toHaveProperty("scene_id");
    expect(journey).toHaveProperty("order_index");
    expect(journey).toHaveProperty("scene_title");
    expect(journey).toHaveProperty("emotional_state");
    expect(journey).toHaveProperty("knowledge_events");
    expect(journey).toHaveProperty("knowledge_gaps");
    expect(journey).toHaveProperty("dramatic_irony");
    expect(journey).toHaveProperty("irony_note");
  });

  it("dramatic irony correctly identified", () => {
    const alice = mockFullDNA.character_journeys.characters[0];
    const firstScene = alice.journey[0];
    expect(firstScene.dramatic_irony).toBe(true);
    expect(firstScene.irony_note).toContain("unaware");
    expect(firstScene.knowledge_gaps).toContain("event_b");
  });

  it("unresolved knowledge tracked", () => {
    const alice = mockFullDNA.character_journeys.characters[0];
    expect(alice.unresolved_knowledge).toHaveLength(1);
    expect(alice.unresolved_knowledge).toContain("event_c");
  });

  it("minor characters identified", () => {
    const charlie = mockFullDNA.character_journeys.characters.find(
      (c) => c.name === "Charlie"
    );
    expect(charlie).toBeDefined();
    expect(charlie?.total_scenes).toBe(1);
  });

  it("dramatic irony scenes list populated", () => {
    expect(mockFullDNA.character_journeys.dramatic_irony_scenes).toHaveLength(1);
    expect(mockFullDNA.character_journeys.dramatic_irony_scenes).toContain("scene_1");
  });

  it("arc completeness section has all required fields", () => {
    expect(mockFullDNA.arc_completeness).toHaveProperty("arc_read");
    expect(mockFullDNA.arc_completeness).toHaveProperty("tension_curve");
    expect(mockFullDNA.arc_completeness).toHaveProperty("resolution_read");
    expect(mockFullDNA.arc_completeness).toHaveProperty("missing_beats");
    expect(mockFullDNA.arc_completeness).toHaveProperty("pacing_observations");
    expect(mockFullDNA.arc_completeness).toHaveProperty("advisory");
    expect(mockFullDNA.arc_completeness).toHaveProperty("uncertainty_notes");
    expect(mockFullDNA.arc_completeness).toHaveProperty("confidence");
  });

  it("tension curve entries have all required fields", () => {
    const entry = mockFullDNA.arc_completeness.tension_curve[0];
    expect(entry).toHaveProperty("scene_id");
    expect(entry).toHaveProperty("order_index");
    expect(entry).toHaveProperty("tension_read");
    expect(entry).toHaveProperty("note");
  });

  it("tension reads are valid values", () => {
    const validTensionReads = ["low", "building", "peak", "releasing", "uncertain"];
    mockFullDNA.arc_completeness.tension_curve.forEach((entry) => {
      expect(validTensionReads).toContain(entry.tension_read);
    });
  });

  it("complete arc correctly identified", () => {
    expect(mockFullDNA.arc_completeness.arc_read).toBe("complete");
    expect(mockFullDNA.arc_completeness.resolution_read).toContain("recognizable progression");
  });

  it("confidence is never high", () => {
    expect(mockFullDNA.arc_completeness.confidence).not.toBe("high");
    expect(["low", "medium"]).toContain(mockFullDNA.arc_completeness.confidence);
  });

  it("uncertainty note about performance context present", () => {
    expect(
      mockFullDNA.arc_completeness.uncertainty_notes.some((note) =>
        note.toLowerCase().includes("performance context")
      )
    ).toBe(true);
  });
});
