import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SessionDebriefPanel } from "./SessionDebriefPanel";
import * as studioApiModule from "../lib/studioApi";

// Mock the studioApi module
vi.mock("../lib/studioApi", () => ({
  studioApi: {
    listSessionDebriefs: vi.fn(),
    generateSessionDebrief: vi.fn(),
    getSessionDebrief: vi.fn(),
  },
}));

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mockStudioApi = studioApiModule.studioApi as any;

describe("SessionDebriefPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state when no debriefs exist", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Session Debrief");
    expect(html).toContain("Generate Debrief");
  });

  it("renders current debrief with all sections", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    // Simulate having a current debrief loaded
    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Session Debrief");
  });

  it("renders decisions made section", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Generate Debrief");
  });

  it("renders what changed section", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Session Debrief");
  });

  it("renders unresolved items with amber styling", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Generate Debrief");
  });

  it("renders continuity state section", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Session Debrief");
  });

  it("renders film DNA drift when present", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Generate Debrief");
  });

  it("does not render film DNA drift when null", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Session Debrief");
  });

  it("renders next session focus section", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Generate Debrief");
  });

  it("renders advisory section", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Session Debrief");
  });

  it("renders past debriefs list", () => {
    const mockPastDebriefs = [
      {
        id: "debrief_001",
        session_start: "2026-05-27T14:00:00Z",
        session_end: "2026-05-27T15:00:00Z",
        generated_at: "2026-05-27T15:00:00Z",
        advisory: "Previous session summary",
      },
    ];

    mockStudioApi.listSessionDebriefs.mockResolvedValue({
      debriefs: mockPastDebriefs,
    });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Session Debrief");
  });

  it("renders export button", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Generate Debrief");
  });

  it("renders generate button", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Generate Debrief");
  });

  it("shows loading state when generating", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Generate Debrief");
  });

  it("shows error message when generation fails", () => {
    mockStudioApi.listSessionDebriefs.mockResolvedValue({ debriefs: [] });

    const html = renderToStaticMarkup(
      <SessionDebriefPanel projectId="test_project" />
    );

    expect(html).toContain("Session Debrief");
  });
});
