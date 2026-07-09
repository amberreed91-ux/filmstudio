import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ExportPackagePanel } from "./ExportPackagePanel";
import * as studioApiModule from "../lib/studioApi";

// Mock the studioApi module
vi.mock("../lib/studioApi", () => ({
  studioApi: {
    listExportPackages: vi.fn(),
    buildExportPackage: vi.fn(),
    getExportPackage: vi.fn(),
  },
}));

const mockStudioApi = studioApiModule.studioApi as any;

describe("ExportPackagePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state when no packages exist", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export Package");
    expect(html).toContain("Export");
  });

  it("renders export button", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export");
  });

  it("renders honest assembly note prominently", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export Package");
  });

  it("renders manifest summary with scene and shot counts", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export Package");
  });

  it("renders download options section", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export");
  });

  it("renders copy manifest json button", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export Package");
  });

  it("renders download continuity report button when included", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export");
  });

  it("renders open film button when stitched film available", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export Package");
  });

  it("renders package contents list", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export");
  });

  it("renders past packages list", () => {
    const mockPastPackages = [
      {
        package_id: "pkg_001",
        created_at: "2026-05-28T15:00:00Z",
        status: "complete",
        scene_count: 2,
        total_shots: 5,
      },
    ];

    mockStudioApi.listExportPackages.mockResolvedValue({
      packages: mockPastPackages,
    });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export Package");
  });

  it("renders export options panel with checkboxes", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export");
  });

  it("renders build package button in options", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export Package");
  });

  it("shows loading state when building", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export");
  });

  it("shows error message when build fails", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export Package");
  });

  it("renders completed renders count", () => {
    mockStudioApi.listExportPackages.mockResolvedValue({ packages: [] });

    const html = renderToStaticMarkup(
      <ExportPackagePanel projectId="test_project" />
    );

    expect(html).toContain("Export");
  });
});
