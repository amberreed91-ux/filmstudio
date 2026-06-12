import React from 'react'
import { CheckCircle, AlertTriangle, AlertOctagon, Printer, RefreshCw, ChevronRight } from 'lucide-react'
import { type ProductionScanReport, type ProductionScanFlag, type Severity } from '../lib/studioApi'

interface ProductionScanReportViewProps {
  report: ProductionScanReport
  onRescan: () => void
}

const SeverityBadge = ({ severity }: { severity: Severity }) => {
  const styles = {
    note: 'bg-zinc-500/20 text-zinc-300 border-zinc-500/30',
    warning: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    blocker: 'bg-rose-500/20 text-rose-300 border-rose-500/30'
  }

  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${styles[severity]}`}>
      {severity}
    </span>
  )
}

export default function ProductionScanReportView({ report, onRescan }: ProductionScanReportViewProps) {
  const handleExport = () => {
    window.print()
  }

  const groupedFlags = report.flags.reduce((acc, flag) => {
    if (!acc[flag.flag_type]) {
      acc[flag.flag_type] = []
    }
    acc[flag.flag_type].push(flag)
    return acc
  }, {} as Record<string, ProductionScanFlag[]>)

  return (
    <div className="flex flex-col h-full bg-[#0a0f1c] text-zinc-100 overflow-hidden print:bg-white print:text-black">
      {/* Header */}
      <div className="flex items-center justify-between p-6 border-b border-white/10 flex-shrink-0">
        <div className="flex items-center gap-4">
          <div className={`p-3 rounded-full ${report.clear_to_shoot ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
            {report.clear_to_shoot ? <CheckCircle size={32} /> : <AlertOctagon size={32} />}
          </div>
          <div>
            <h2 className="text-2xl font-bold tracking-tight">Production Readiness Scan</h2>
            <div className="flex items-center gap-2 mt-1">
              <span className={`text-sm font-semibold uppercase ${report.clear_to_shoot ? 'text-emerald-400' : 'text-rose-400'}`}>
                {report.clear_to_shoot ? 'Clear to Shoot' : 'Production Blocked'}
              </span>
              <span className="text-zinc-500">•</span>
              <span className="text-sm text-zinc-400 uppercase tracking-widest">{report.readiness_level.replace('_', ' ')}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 print:hidden">
          <button
            onClick={onRescan}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 transition-colors text-sm font-medium"
          >
            <RefreshCw size={16} />
            Re-scan
          </button>
          <button
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500 text-black hover:bg-cyan-400 transition-colors text-sm font-bold uppercase tracking-wider"
          >
            <Printer size={16} />
            Export PDF
          </button>
        </div>
      </div>

      {/* Summary */}
      <div className="p-6 bg-white/5 border-b border-white/10 flex-shrink-0 print:bg-gray-100 print:border-black/20">
        <h3 className="text-xs font-bold uppercase tracking-[0.2em] text-cyan-400 mb-2">Co-Director Synthesis</h3>
        <p className="text-lg leading-relaxed italic text-zinc-200 print:text-black">
          "{report.summary}"
        </p>
      </div>

      {/* Flags */}
      <div className="flex-1 overflow-y-auto p-6 space-y-8">
        {Object.entries(groupedFlags).map(([type, flags]) => (
          <div key={type} className="space-y-4">
            <h4 className="text-sm font-bold uppercase tracking-widest text-zinc-500 border-b border-white/5 pb-2">
              {type}s
            </h4>
            <div className="grid gap-4">
              {flags.map((flag, idx) => (
                <div key={idx} className="cinematic-panel p-4 border border-white/10 hover:border-white/20 transition-all group">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-2 flex-1">
                      <div className="flex items-center gap-3">
                        <SeverityBadge severity={flag.severity} />
                        <span className="font-semibold text-zinc-100">{flag.description}</span>
                      </div>
                      
                      {flag.affected_scenes.length > 0 && (
                        <div className="flex flex-wrap gap-2 mt-2">
                          <span className="text-[10px] uppercase font-bold text-zinc-500 mt-1">Affected:</span>
                          {flag.affected_scenes.map(sceneId => (
                            <a 
                              key={sceneId}
                              href={`/studio/scenes/${sceneId}`}
                              className="text-[10px] px-2 py-0.5 rounded bg-white/5 border border-white/10 text-cyan-400 hover:bg-cyan-500/10 transition-colors"
                            >
                              Scene {sceneId}
                            </a>
                          ))}
                        </div>
                      )}

                      <div className="mt-4 p-3 bg-black/40 rounded border-l-2 border-cyan-500/50 italic text-sm text-zinc-400 group-hover:text-zinc-300 transition-colors">
                        <span className="text-[10px] not-italic font-bold uppercase tracking-widest text-cyan-500 block mb-1">Co-Director Note</span>
                        {flag.co_director_note}
                      </div>
                    </div>
                    <div className="text-zinc-600 group-hover:text-zinc-400 transition-colors">
                      <ChevronRight size={20} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        {report.flags.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center opacity-50">
            <CheckCircle size={48} className="mb-4 text-emerald-500" />
            <p className="text-xl font-medium">No production risks identified.</p>
            <p className="text-sm mt-2 text-zinc-400">Everything looks green for production.</p>
          </div>
        )}
      </div>
    </div>
  )
}
