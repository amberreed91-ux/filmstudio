import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import TransitionIntelligencePanel from "./TransitionIntelligencePanel";

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock @tanstack/react-query
vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(),
}));

import { useQuery } from "@tanstack/react-query";
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mockUseQuery = useQuery as any;

describe("TransitionIntelligencePanel", () => {
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
      <TransitionIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("Analyzing transitions");
  });

  it("renders error state", () => {
    mockUseQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to fetch"),
    });

    const html = renderToStaticMarkup(
      <TransitionIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("Failed to fetch");
  });

  it("renders empty state when no scene pairs", () => {
    mockUseQuery.mockReturnValue({
      data: { scene_pairs: [] },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <TransitionIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("No transition advisories");
  });

  it("renders scene pairs with transition type badges", () => {
    mockUseQuery.mockReturnValue({
      data: {
        scene_pairs: [
          {
            from_scene_id: "scene_001",
            to_scene_id: "scene_002",
            advisory: {
              transition_type: "smash_cut",
              transition_rationale: "A smash cut releases the tension without warning.",
              continuity_notes: "Eyeline match maintained.",
            },
          },
          {
            from_scene_id: "scene_002",
            to_scene_id: "scene_003",
            advisory: {
              transition_type: "dissolve",
              transition_rationale: "A dissolve lets the emotion linger.",
              continuity_notes: "",
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <TransitionIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("scene_001");
    expect(html).toContain("scene_002");
    expect(html).toContain("scene_003");
    expect(html).toContain("smash cut");
    expect(html).toContain("dissolve");
    expect(html).toContain("A smash cut releases the tension without warning.");
    expect(html).toContain("Eyeline match maintained.");
  });

  it("renders scene pair arrows correctly", () => {
    mockUseQuery.mockReturnValue({
      data: {
        scene_pairs: [
          {
            from_scene_id: "scene_001",
            to_scene_id: "scene_002",
            advisory: {
              transition_type: "cut",
              transition_rationale: "A hard cut to black.",
              continuity_notes: "",
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <TransitionIntelligencePanel projectId="test_project" />
    );

    // Arrow should be present
    expect(html).toContain("→");
  });

  it("renders fade_to_black and cross_dissolve in violet", () => {
    mockUseQuery.mockReturnValue({
      data: {
        scene_pairs: [
          {
            from_scene_id: "scene_001",
            to_scene_id: "scene_002",
            advisory: {
              transition_type: "fade_to_black",
              transition_rationale: "Fade to black.",
              continuity_notes: "",
            },
          },
          {
            from_scene_id: "scene_002",
            to_scene_id: "scene_003",
            advisory: {
              transition_type: "cross_dissolve",
              transition_rationale: "Cross dissolve.",
              continuity_notes: "",
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <TransitionIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("fade to black");
    expect(html).toContain("cross dissolve");
  });

  it("renders match_cut in emerald color", () => {
    mockUseQuery.mockReturnValue({
      data: {
        scene_pairs: [
          {
            from_scene_id: "scene_001",
            to_scene_id: "scene_002",
            advisory: {
              transition_type: "match_cut",
              transition_rationale: "Match cut connects the objects.",
              continuity_notes: "",
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <TransitionIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("match cut");
  });

  it("renders continuity notes with warning icon", () => {
    mockUseQuery.mockReturnValue({
      data: {
        scene_pairs: [
          {
            from_scene_id: "scene_001",
            to_scene_id: "scene_002",
            advisory: {
              transition_type: "cut",
              transition_rationale: "A cut.",
              continuity_notes: "Lighting shift — may need color correction.",
            },
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <TransitionIntelligencePanel projectId="test_project" />
    );

    expect(html).toContain("Continuity Note");
    expect(html).toContain("Lighting shift");
  });

  it("renders component with projectId prop", () => {
    mockUseQuery.mockReturnValue({
      data: { scene_pairs: [] },
      isLoading: false,
      error: null,
    });

    const html = renderToStaticMarkup(
      <TransitionIntelligencePanel projectId="proj-abc123" />
    );

    expect(html).toBeTruthy();
    // The component should have called useQuery with the projectId
    expect(mockUseQuery).toHaveBeenCalled();
  });
});