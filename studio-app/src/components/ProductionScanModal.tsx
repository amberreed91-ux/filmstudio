import React, { useState, useEffect } from 'react'
import { X, ShieldCheck } from 'lucide-react'
import { runProductionScan, type ProductionScanReport } from '../lib/studioApi'
import ProductionScanReportView from './ProductionScanReport'

interface ProductionScanModalProps {
  projectId: string
  isOpen: boolean
  onClose: () => void
}

export default function ProductionScanModal({ projectId, isOpen, onClose }: ProductionScanModalProps) {
  const [report, setReport] = useState<ProductionScanReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const performScan = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await runProductionScan(projectId)
      setReport(result)
    } catch (err) {
      console.error('Scan failed:', err)
      setError('The co-director was unable to complete the scan. Ensure all scene data is accessible.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isOpen) {
      performScan()
    } else {
      setReport(null)
    }
  }, [isOpen, projectId])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-[#0a0f1c] border border-white/10 w-full max-w-5xl h-[85vh] rounded-xl shadow-2xl overflow-hidden flex flex-col relative">
        {/* Close button */}
        <button 
          onClick={onClose}
          className="absolute top-4 right-4 z-[110] p-2 rounded-full bg-white/5 hover:bg-white/10 transition-colors text-zinc-400 hover:text-white print:hidden"
        >
          <X size={20} />
        </button>

        {loading && (
          <div className="flex-1 flex flex-col items-center justify-center space-y-6">
            <div className="relative">
              <div className="w-20 h-20 rounded-full border-2 border-cyan-500/20 animate-ping absolute inset-0"></div>
              <div className="w-20 h-20 rounded-full border-2 border-t-cyan-500 border-r-transparent border-b-transparent border-l-transparent animate-spin relative z-10"></div>
              <div className="absolute inset-0 flex items-center justify-center">
                <ShieldCheck size={32} className="text-cyan-500" />
              </div>
            </div>
            <div className="text-center space-y-2">
              <h3 className="text-xl font-bold tracking-tight">Co-Director Scanning...</h3>
              <p className="text-zinc-500 max-w-xs mx-auto">Analyzing location continuity, character arcs, and script integrity for production readiness.</p>
            </div>
          </div>
        )}

        {error && (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-4">
            <div className="p-4 bg-rose-500/10 rounded-full text-rose-500">
              <X size={48} />
            </div>
            <div className="space-y-2">
              <h3 className="text-xl font-bold">Scan Incomplete</h3>
              <p className="text-zinc-400 max-w-md">{error}</p>
            </div>
            <button 
              onClick={performScan}
              className="px-6 py-2 bg-white text-black font-bold rounded-lg hover:bg-zinc-200 transition-colors"
            >
              Try Again
            </button>
          </div>
        )}

        {report && !loading && (
          <ProductionScanReportView report={report} onRescan={performScan} />
        )}
      </div>
    </div>
  )
}
