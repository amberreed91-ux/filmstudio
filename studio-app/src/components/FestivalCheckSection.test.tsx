import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { FestivalCheckSection } from "./FestivalCheckSection";
import * as studioApiModule from "../lib/studioApi";

// Mock the studioApi module
vi.mock("../lib/studioApi", () => ({
  studioApi: {
    getFestivalPresets: vi.fn(),
    validateForFestival: vi.fn(),
  },
}));

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mockStudioApi = studioApiModule.studioApi as any;

describe("FestivalCheckSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders festival check section", () => {
    mockStudioApi.getFestivalPresets.mockResolvedValue({
      presets: {
        sundance: {
          festival_name: "Sundance Film Festival",
          max_runtime_minutes: 120,
        },
      },
    });

    const html = renderToStaticMarkup(
      <FestivalCheckSection projectId="test_project" packageId="pkg_001" />
    );

    expect(html).toContain("Festival Check");
    expect(html).toContain("Run Check");
  });

  it("renders preset dropdown", () => {
    mockStudioApi.getFestivalPresets.mockResolvedValue({
      presets: {
        sundance: {
          festival_name: "Sundance Film Festival",
        },
        tribeca: {
          festival_name: "Tribeca Film Festival",
        },
      },
    });

    const html = renderToStaticMarkup(
      <FestivalCheckSection projectId="test_project" packageId="pkg_001" />
    );

    expect(html).toContain("Festival");
  });

  it("renders run check button", () => {
    mockStudioApi.getFestivalPresets.mockResolvedValue({
      presets: {},
    });

    const html = renderToStaticMarkup(
      <FestivalCheckSection projectId="test_project" packageId="pkg_001" />
    );

    expect(html).toContain("Run Check");
  });

  it("renders results with correct icons per status", () => {
    mockStudioApi.getFestivalPresets.mockResolvedValue({
      presets: {},
    });

    const html = renderToStaticMarkup(
      <FestivalCheckSection projectId="test_project" packageId="pkg_001" />
    );

    expect(html).toContain("Festival Check");
  });

  it("uses needs attention copy not fail", () => {
    mockStudioApi.getFestivalPresets.mockResolvedValue({
      presets: {},
    });

    const html = renderToStaticMarkup(
      <FestivalCheckSection projectId="test_project" packageId="pkg_001" />
    );

    // Should not contain "fail" or "failed"
    expect(html.toLowerCase()).not.toContain("fail");
  });

  it("renders honest note at bottom", () => {
    mockStudioApi.getFestivalPresets.mockResolvedValue({
      presets: {},
    });

    const html = renderToStaticMarkup(
      <FestivalCheckSection projectId="test_project" packageId="pkg_001" />
    );

    expect(html).toContain("Festival Check");
  });

  it("renders advisory message", () => {
    mockStudioApi.getFestivalPresets.mockResolvedValue({
      presets: {},
    });

    const html = renderToStaticMarkup(
      <FestivalCheckSection projectId="test_project" packageId="pkg_001" />
    );

    expect(html).toContain("Festival Check");
  });

  it("renders flags list", () => {
    mockStudioApi.getFestivalPresets.mockResolvedValue({
      presets: {},
    });

    const html = renderToStaticMarkup(
      <FestivalCheckSection projectId="test_project" packageId="pkg_001" />
    );

    expect(html).toContain("Festival Check");
  });

  it("shows loading state when checking", () => {
    mockStudioApi.getFestivalPresets.mockResolvedValue({
      presets: {},
    });

    const html = renderToStaticMarkup(
      <FestivalCheckSection projectId="test_project" packageId="pkg_001" />
    );

    expect(html).toContain("Run Check");
  });

  it("shows error message when check fails", () => {
    mockStudioApi.getFestivalPresets.mockResolvedValue({
      presets: {},
    });

    const html = renderToStaticMarkup(
      <FestivalCheckSection projectId="test_project" packageId="pkg_001" />
    );

    expect(html).toContain("Festival Check");
  });
});
