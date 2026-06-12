import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import SoundIntelligencePanel from "./SoundIntelligencePanel";

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock @tanstack/react-query
vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(),
}));

import { useQuery } from "@tanstack/react-query";
const mockUseQuery = useQuery as any;

describe("SoundIntelligencePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
  });

  it("renders loading state", () => {
    mockUseQuery.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    });

    const html = renderToStaticMarkup(
      <SoundIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("Analyzing sound design");
  });

  it("renders error state", () => {
    mockUseQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to fetch"),
    });

    const html = renderToStaticMarkup(
      <SoundIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("Failed to fetch");
  });

  it("renders empty state when no scene sounds", () => {
    mockUseQuery.mockReturnValue({
      data: { scene_sounds: [] },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <SoundIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("No sound advisories");
  });

  it("renders scene sounds with mood badges", () => {
    mockUseQuery.mockReturnValue({
      data: {
        scene_sounds: [
          {
            scene_id: "scene_001",
            scene_title: "The Confrontation",
            advisory: {
              mood: "tense",
              score_notes: "Let the score drop out entirely — this scene earns the silence.",
              ambient_notes: "Rain on glass, distant traffic hum.",
              silence_flag: false,
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <SoundIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("scene_001");
    expect(html).toContain("The Confrontation");
    expect(html).toContain("tense");
  });

  it("renders silence_flag badge when true", () => {
    mockUseQuery.mockReturnValue({
      data: {
        scene_sounds: [
          {
            scene_id: "scene_001",
            scene_title: "The Void",
            advisory: {
              mood: "melancholic",
              score_notes: "Silence.",
              ambient_notes: "Nothing.",
              silence_flag: true,
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <SoundIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("Intentional Silence");
  });

  it("does not render silence badge when silence_flag is false", () => {
    mockUseQuery.mockReturnValue({
      data: {
        scene_sounds: [
          {
            scene_id: "scene_001",
            scene_title: "The Chase",
            advisory: {
              mood: "tense",
              score_notes: "Propulsive.",
              ambient_notes: "Footsteps.",
              silence_flag: false,
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <SoundIntelligencePanel projectId="test_project" />
    );

    expect(html).not.toContain("Intentional Silence");
    expect(html).toContain("tense");
  });

  it("renders score_notes and ambient_notes", () => {
    mockUseQuery.mockReturnValue({
      data: {
        scene_sounds: [
          {
            scene_id: "scene_001",
            scene_title: "The Meeting",
            advisory: {
              mood: "melancholic",
              score_notes: "Let the score drop out entirely — this scene earns the silence.",
              ambient_notes: "Rain on glass, distant traffic hum, the hum of a refrigerator.",
              silence_flag: true,
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <SoundIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("Score");
    expect(html).toContain("Ambient");
    expect(html).toContain("let the score drop out entirely");
    expect(html).toContain("rain on glass");
  });

  it("renders different mood colors", () => {
    mockUseQuery.mockReturnValue({
      data: {
        scene_sounds: [
          {
            scene_id: "scene_001",
            scene_title: "The Chase",
            advisory: {
              mood: "tense",
              score_notes: "Tense score.",
              ambient_notes: "Footsteps.",
              silence_flag: false,
            },
          },
          {
            scene_id: "scene_002",
            scene_title: "The Goodbye",
            advisory: {
              mood: "melancholic",
              score_notes: "Melancholic score.",
              ambient_notes: "Wind.",
              silence_flag: true,
            },
          },
          {
            scene_id: "scene_003",
            scene_title: "The Victory",
            advisory: {
              mood: "hopeful",
              score_notes: "Hopeful score.",
              ambient_notes: "Applause.",
              silence_flag: false,
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <SoundIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("tense");
    expect(html).toContain("melancholic");
    expect(html).toContain("hopeful");
  });

  it("renders propulsive mood badge", () => {
    mockUseQuery.mockReturnValue({
      data: {
        scene_sounds: [
          {
            scene_id: "scene_001",
            scene_title: "The Rush",
            advisory: {
              mood: "propulsive",
              score_notes: "Drive forward.",
              ambient_notes: "Engine roar.",
              silence_flag: false,
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <SoundIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("propulsive");
  });

  it("renders scene_id and scene_title per entry", () => {
    mockUseQuery.mockReturnValue({
      data: {
        scene_sounds: [
          {
            scene_id: "scene_001",
            scene_title: "Opening Shot",
            advisory: {
              mood: "tense",
              score_notes: "Opening tension.",
              ambient_notes: "City sounds.",
              silence_flag: false,
            },
          },
          {
            scene_id: "scene_002",
            scene_title: "The Quiet Moment",
            advisory: {
              mood: "melancholic",
              score_notes: "Quiet.",
              ambient_notes: "Silence.",
              silence_flag: true,
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <SoundIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("scene_001");
    expect(html).toContain("scene_002");
    expect(html).toContain("Opening Shot");
    expect(html).toContain("The Quiet Moment");
  });
});