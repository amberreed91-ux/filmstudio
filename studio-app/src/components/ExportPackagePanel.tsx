import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { studioApi } from "../lib/studioApi";
import type { ExportPackage, ExportPackageSummary } from "../lib/studioApi";
import { FestivalCheckSection } from "./FestivalCheckSection";
import { PitchDeckSection } from "./PitchDeckSection";

interface ExportPackagePanelProps {
  projectId: string;
}

export function ExportPackagePanel({ projectId }: ExportPackagePanelProps) {
  const [currentPackage, setCurrentPackage] = useState<ExportPackage | null>(null);
  const [pastPackages, setPastPackages] = useState<ExportPackageSummary[]>([]);
  const [selectedPackageId, setSelectedPackageId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingPackageId, setLoadingPackageId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showOptions, setShowOptions] = useState(false);
  
  // Export options
  const [includeContinuityReport, setIncludeContinuityReport] = useState(true);
  const [includeRenderLineage, setIncludeRenderLineage] = useState(true);
  const [includeDirectorNotes, setIncludeDirectorNotes] = useState(true);

  const loadPastPackages = useCallback(async () => {
    try {
      const result = await studioApi.listExportPackages(projectId, 5);
      setPastPackages(result.packages || []);
    } catch (err) {
      console.error("Failed to load past packages:", err);
    }
  }, [projectId]);

  useEffect(() => {
    loadPastPackages();
  }, [loadPastPackages]);

  const buildPackage = async () => {
    setLoading(true);
    setError(null);
    try {
      const pkg = await studioApi.buildExportPackage(projectId, {
        include_continuity_report: includeContinuityReport,
        include_render_lineage: includeRenderLineage,
        include_director_notes: includeDirectorNotes,
      });
      setCurrentPackage(pkg);
      setSelectedPackageId(null);
      setShowOptions(false);
      await loadPastPackages();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to build package");
    } finally {
      setLoading(false);
    }
  };

  const loadPackage = async (packageId: string) => {
    setLoading(true);
    setLoadingPackageId(packageId);
    setError(null);
    try {
      const pkg = await studioApi.getExportPackage(projectId, packageId);
      setCurrentPackage(pkg);
      setSelectedPackageId(packageId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load package");
    } finally {
      setLoading(false);
      setLoadingPackageId(null);
    }
  };

  const copyManifestJson = () => {
    if (!currentPackage) return;
    
    const manifestJson = JSON.stringify(currentPackage.manifest, null, 2);
    navigator.clipboard.writeText(manifestJson);
  };

  const downloadContinuityReport = () => {
    if (!currentPackage?.continuity_report) return;
    
    const reportText = JSON.stringify(currentPackage.continuity_report, null, 2);
    const blob = new Blob([reportText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `continuity-report-${currentPackage.package_id}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const openFilm = () => {
    if (!currentPackage?.stitched_film_url) return;
    window.open(currentPackage.stitched_film_url, "_blank");
  };

  return (
    <div className="h-full flex flex-col bg-slate-900 text-slate-200">
      {/* Header */}
      <div className="flex-none border-b border-slate-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-slate-100">Export Package</h2>
            <p className="text-sm text-slate-400 mt-1">
              Complete film package with manifest, continuity report, and render lineage
            </p>
          </div>
          <button type="button"
            onClick={() => setShowOptions(!showOptions)}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-md text-sm font-medium transition-colors"
          >
            {loading ? "Building..." : "Export"}
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

          {/* Export Options Panel */}
          {showOptions && (
            <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 space-y-4">
              <h3 className="text-sm font-semibold text-slate-300">Export Options</h3>
              
              <div className="space-y-3">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeContinuityReport}
                    onChange={(e) => setIncludeContinuityReport(e.target.checked)}
                    className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm text-slate-300">Include Continuity Report</span>
                </label>

                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeRenderLineage}
                    onChange={(e) => setIncludeRenderLineage(e.target.checked)}
                    className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm text-slate-300">Include Render Lineage</span>
                </label>

                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeDirectorNotes}
                    onChange={(e) => setIncludeDirectorNotes(e.target.checked)}
                    className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm text-slate-300">Include Director Notes</span>
                </label>
              </div>

              <div className="flex gap-3 pt-2">
                <button type="button"
                  onClick={buildPackage}
                  disabled={loading}
                  aria-busy={loading}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-md text-sm font-medium transition-colors"
                >
                  {loading ? <Loader2 size={14} className="mr-1.5 inline animate-spin" /> : null}
                  {loading ? "Building..." : "Build Package"}
                </button>
                <button type="button"
                  onClick={() => setShowOptions(false)}
                  className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-md text-sm font-medium transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Current Package */}
          {currentPackage && (
            <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
              {/* Package Header */}
              <div className="px-6 py-4 border-b border-slate-700">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="text-sm font-medium text-slate-300">
                      {currentPackage.manifest.film_title}
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      Exported {new Date(currentPackage.created_at).toLocaleString()}
                    </div>
                  </div>
                  <div className="text-xs px-2 py-1 rounded bg-green-900/30 text-green-300 border border-green-700/50">
                    {currentPackage.status}
                  </div>
                </div>
              </div>

              {/* Honest Assembly Note */}
              <div className="px-6 py-4 bg-amber-900/10 border-b border-amber-700/30">
                <div className="text-sm font-medium text-amber-300 mb-1">Assembly Status</div>
                <div className="text-sm text-slate-300 leading-relaxed">
                  {currentPackage.honest_assembly_note}
                </div>
              </div>

              {/* Manifest Summary */}
              <div className="px-6 py-4 border-b border-slate-700">
                <h3 className="text-sm font-semibold text-slate-300 mb-3">Manifest Summary</h3>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <div className="text-xs text-slate-500">Scenes</div>
                    <div className="text-lg font-semibold text-slate-200">
                      {currentPackage.manifest.scene_count}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Total Shots</div>
                    <div className="text-lg font-semibold text-slate-200">
                      {currentPackage.manifest.total_shots}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Completed Renders</div>
                    <div className="text-lg font-semibold text-slate-200">
                      {currentPackage.manifest.scenes.reduce(
                        (acc, scene) =>
                          acc +
                          scene.shots.filter(
                            (shot) => shot.status === "complete" && shot.output_url
                          ).length,
                        0
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Download Options */}
              <div className="px-6 py-4 space-y-3">
                <h3 className="text-sm font-semibold text-slate-300 mb-3">Download Options</h3>
                
                <button type="button"
                  onClick={copyManifestJson}
                  className="w-full px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-md text-sm font-medium transition-colors text-left"
                >
                  📋 Copy Manifest JSON
                </button>

                {currentPackage.continuity_report && (
                  <button type="button"
                    onClick={downloadContinuityReport}
                    className="w-full px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-md text-sm font-medium transition-colors text-left"
                  >
                    📄 Download Continuity Report
                  </button>
                )}

                {currentPackage.stitched_film_url && (
                  <button type="button"
                    onClick={openFilm}
                    className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium transition-colors text-left"
                  >
                    🎬 Open Film
                  </button>
                )}
              </div>

              {/* Package Contents */}
              <div className="px-6 py-4 border-t border-slate-700">
                <h3 className="text-sm font-semibold text-slate-300 mb-3">Package Contents</h3>
                <div className="space-y-2 text-sm text-slate-400">
                  <div className="flex items-center gap-2">
                    <span className="text-green-400">✓</span>
                    <span>Scene Manifest</span>
                  </div>
                  {currentPackage.continuity_report && (
                    <div className="flex items-center gap-2">
                      <span className="text-green-400">✓</span>
                      <span>Continuity Report</span>
                    </div>
                  )}
                  {currentPackage.render_lineage && (
                    <div className="flex items-center gap-2">
                      <span className="text-green-400">✓</span>
                      <span>Render Lineage</span>
                    </div>
                  )}
                  {currentPackage.director_notes && (
                    <div className="flex items-center gap-2">
                      <span className="text-green-400">✓</span>
                      <span>Director Notes</span>
                    </div>
                  )}
                  {currentPackage.film_dna_snapshot && (
                    <div className="flex items-center gap-2">
                      <span className="text-green-400">✓</span>
                      <span>Film DNA Snapshot</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Festival Check */}
          {currentPackage && (
            <FestivalCheckSection
              projectId={projectId}
              packageId={currentPackage.package_id}
            />
          )}

          {/* Pitch Deck */}
          <PitchDeckSection projectId={projectId} />

          {/* Past Packages */}
          {pastPackages.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-slate-300 mb-3">Past Exports</h3>
              <div className="space-y-2">
                {pastPackages.map((pkg) => (
                  <button type="button"
                    key={pkg.package_id}
                    onClick={() => loadPackage(pkg.package_id)}
                    disabled={loading || loadingPackageId !== null}
                    aria-busy={loadingPackageId === pkg.package_id}
                    className={`w-full text-left px-4 py-3 rounded-md border transition-colors ${
                      selectedPackageId === pkg.package_id
                        ? "bg-slate-700 border-slate-600"
                        : "bg-slate-800 border-slate-700 hover:bg-slate-750"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-slate-300">
                          {pkg.scene_count} scenes, {pkg.total_shots} shots
                        </div>
                        <div className="text-xs text-slate-500 mt-1">
                          {new Date(pkg.created_at).toLocaleString()}
                        </div>
                        {loadingPackageId === pkg.package_id ? (
                          <div className="mt-1 flex items-center gap-1 text-xs text-slate-400">
                            <Loader2 size={11} className="animate-spin" /> Loading package…
                          </div>
                        ) : null}
                      </div>
                      <div className="text-xs px-2 py-1 rounded bg-slate-700 text-slate-400">
                        {pkg.status}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Empty State */}
          {!currentPackage && !loading && !showOptions && pastPackages.length === 0 && (
            <div className="text-center py-12">
              <div className="text-slate-500 text-sm">
                No export packages yet. Click Export to build your first package.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
