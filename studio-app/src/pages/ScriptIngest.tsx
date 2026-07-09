import { useState, useEffect, useRef, type DragEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileText, Upload, CheckCircle, AlertCircle, File } from 'lucide-react'
import StudioShell from '../components/StudioShell'
import StudioPanel from '../components/StudioPanel'
import CinematicLoading from '../components/CinematicLoading'
import { ingestScript, getRenderProviders } from '../lib/studioApi'

interface RenderProvider {
  provider_id: string
  name: string
  status: string
  is_simulated: boolean
}

const DEFAULT_PROVIDERS: RenderProvider[] = [
  { provider_id: 'runway', name: 'Runway', status: 'available', is_simulated: false },
  { provider_id: 'simulation', name: 'Simulation (Demo)', status: 'available', is_simulated: true },
  { provider_id: 'openai', name: 'OpenAI', status: 'available', is_simulated: false },
  { provider_id: 'replicate', name: 'Replicate', status: 'available', is_simulated: false },
]

export default function ScriptIngest() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dropZoneRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [providers, setProviders] = useState<RenderProvider[]>(DEFAULT_PROVIDERS)
  
  const [formData, setFormData] = useState({
    title: '',
    creative_intent: '',
    render_provider: 'runway',
    script_text: '',
  })

  // Load providers on mount
  useEffect(() => {
    const loadProviders = async () => {
      try {
        const data = await getRenderProviders()
        if (data && data.length > 0) {
          setProviders(data)
          const runway = data.find((provider) => provider.provider_id === 'runway')
          if (runway) {
            setFormData((prev) => ({ ...prev, render_provider: 'runway' }))
          } else if (data[0]?.provider_id) {
            setFormData((prev) => ({ ...prev, render_provider: data[0].provider_id }))
          }
        }
      } catch {
        // Keep defaults if API fails
      }
    }
    loadProviders()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(false)

    if (!formData.title.trim()) {
      setError('Please enter a project title')
      return
    }
    if (!formData.script_text.trim()) {
      setError('Please enter script content')
      return
    }

    setLoading(true)
    try {
      const project = await ingestScript(formData)
      setSuccess(true)
      // Navigate to the new project workspace after a brief delay
      setTimeout(() => {
        navigate(`/studio/project/${project.project_id}`)
      }, 1500)
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message)
      } else if (typeof err === 'object' && err !== null) {
        // Handle object/array errors from API
        const errObj = err as Record<string, unknown>
        if (Array.isArray(err)) {
          setError(err.map(e => typeof e === 'object' ? JSON.stringify(e) : String(e)).join(', '))
        } else if (errObj.detail) {
          setError(String(errObj.detail))
        } else {
          setError(JSON.stringify(err))
        }
      } else {
        setError(String(err))
      }
    } finally {
      setLoading(false)
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const processFile = (file: File) => {
    const reader = new FileReader()
    reader.onload = (event) => {
      const content = event.target?.result as string
      const fileName = file.name.replace(/\.[^/.]+$/, '') // Remove extension
      const autoTitle = fileName.replace(/[-_]/g, ' ') // Replace dashes/underscores with spaces
      
      // Auto-fill title from filename if not already set
      setFormData(prev => ({
        ...prev,
        script_text: content,
        title: prev.title || autoTitle
      }))
      setUploadedFileName(file.name)
    }
    reader.onerror = () => {
      setError('Failed to read file')
    }
    reader.readAsText(file)
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    processFile(file)
  }

  const triggerFileInput = () => {
    fileInputRef.current?.click()
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    
    const files = e.dataTransfer.files
    if (files && files.length > 0) {
      const file = files[0]
      const validExtensions = ['.fountain', '.fdx', '.txt', '.pdf', '.sbx']
      const hasValidExtension = validExtensions.some(ext => file.name.toLowerCase().endsWith(ext))
      
      if (hasValidExtension) {
        processFile(file)
      } else {
        setError('Please upload a .fountain, .fdx, .txt, .pdf, or .sbx file')
      }
    }
  }

  return (
    <StudioShell 
      title="Script Ingestion" 
      subtitle="Transform your screenplay into a production workspace"
    >
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          
          {/* Header Info */}
          <StudioPanel 
            title="Ingest a Screenplay" 
            subtitle="Paste your script below to create a new production project with scenes, shots, and crew assignments"
          >
            <div className="flex items-start gap-4 p-4 rounded-xl" style={{ background: 'var(--bg-panel)' }}>
              <div className="p-3 rounded-lg" style={{ background: 'rgba(0, 200, 255, 0.1)' }}>
                <FileText size={24} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                  The script analysis engine will parse your screenplay, extract scenes and characters, 
                  and set up a complete production workspace ready for AI-assisted direction.
                </p>
              </div>
            </div>
          </StudioPanel>

          {/* Ingest Form */}
          <StudioPanel title="Script Details" subtitle="Configure your new production">
            <form onSubmit={handleSubmit} className="space-y-4">
              
              {/* Title */}
              <div>
                <label className="block text-xs mb-2" style={{ color: 'var(--text-muted)' }}>
                  Project Title *
                </label>
                <input
                  type="text"
                  name="title"
                  value={formData.title}
                  onChange={handleChange}
                  placeholder="e.g., Neon Aftertaste"
                  className="w-full px-4 py-3 rounded-lg text-sm"
                  style={{ 
                    background: 'var(--bg-panel)', 
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)'
                  }}
                />
              </div>

              {/* Creative Intent */}
              <div>
                <label className="block text-xs mb-2" style={{ color: 'var(--text-muted)' }}>
                  Creative Intent / Vision
                </label>
                <textarea
                  name="creative_intent"
                  value={formData.creative_intent}
                  onChange={handleChange}
                  placeholder="Describe the tone, style, and vision for this project..."
                  rows={3}
                  className="w-full px-4 py-3 rounded-lg text-sm resize-none"
                  style={{ 
                    background: 'var(--bg-panel)', 
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)'
                  }}
                />
              </div>

              {/* Render Provider */}
              <div>
                <label className="block text-xs mb-2" style={{ color: 'var(--text-muted)' }}>
                  Render Provider
                </label>
                <select
                  name="render_provider"
                  value={formData.render_provider}
                  onChange={handleChange}
                  className="w-full px-4 py-3 rounded-lg text-sm"
                  style={{ 
                    background: 'var(--bg-panel)', 
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)'
                  }}
                >
                  {providers.map(provider => (
                    <option key={provider.provider_id} value={provider.provider_id}>
                      {provider.name}
                      {provider.is_simulated ? ' (Demo)' : ''}
                    </option>
                  ))}
                </select>
              </div>

              {/* Script Text */}
              <div
                ref={dropZoneRef}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    Script Content *
                  </label>
                  <button
                    type="button"
                    onClick={triggerFileInput}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs"
                    style={{ 
                      background: 'var(--bg-panel)',
                      border: '1px solid var(--border)',
                      color: 'var(--text-secondary)',
                      cursor: 'pointer'
                    }}
                  >
                    <File size={14} />
                    {uploadedFileName ? 'Replace File' : 'Upload Script'}
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".fountain,.fdx,.txt,.pdf,.sbx"
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                </div>
                {uploadedFileName && (
                  <div className="flex items-center gap-2 mb-2 px-3 py-2 rounded-lg" style={{ background: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.3)' }}>
                    <File size={14} style={{ color: '#22c55e' }} />
                    <span className="text-xs" style={{ color: '#22c55e' }}>{uploadedFileName}</span>
                  </div>
                )}
                {/* Drag and Drop Overlay */}
                {isDragging && (
                  <div 
                    className="absolute inset-0 flex flex-col items-center justify-center rounded-lg z-10"
                    style={{ 
                      background: 'rgba(0, 200, 255, 0.1)', 
                      border: '2px dashed var(--accent-cyan)',
                      backdropFilter: 'blur(4px)'
                    }}
                  >
                    <Upload size={32} style={{ color: 'var(--accent-cyan)' }} />
                    <span className="mt-2 text-sm" style={{ color: 'var(--accent-cyan)' }}>
                      Drop your script here
                    </span>
                  </div>
                )}
                <div className="relative">
                  <textarea
                  name="script_text"
                  value={formData.script_text}
                  onChange={handleChange}
                  placeholder={`INT. COFFEE SHOP - DAY

The camera PANS across a crowded room, settling on MAYA (30s), typing furiously on her laptop.

MAYA
(sotto voce)
Not again...

She looks up, making eye contact with a STRANGER across the room...`}
                  rows={16}
                  className="w-full px-4 py-3 rounded-lg text-sm resize-none font-mono"
                  style={{ 
                    background: 'var(--bg-panel)', 
                    border: isDragging ? '2px solid var(--accent-cyan)' : '1px solid var(--border)',
                    color: 'var(--text-primary)'
                  }}
                />
                </div>
                <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                  Standard screenplay format recommended (INT./EXT., character names, dialogue, action lines)
                </p>
              </div>

              {/* Status Messages */}
              {error && (
                <div className="flex items-center gap-2 p-3 rounded-lg" 
                  style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
                  <AlertCircle size={16} style={{ color: '#ef4444' }} />
                  <span className="text-sm" style={{ color: '#ef4444' }}>{error}</span>
                </div>
              )}

              {success && (
                <div className="flex items-center gap-2 p-3 rounded-lg" 
                  style={{ background: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.3)' }}>
                  <CheckCircle size={16} style={{ color: '#22c55e' }} />
                  <span className="text-sm" style={{ color: '#22c55e' }}>
                    Script ingested successfully! Redirecting to workspace...
                  </span>
                </div>
              )}

              {/* Submit Button */}
              <div className="flex items-center gap-3 pt-4">
                <button
                  type="submit"
                  disabled={loading || success}
                  className="flex items-center gap-2 px-6 py-3 rounded-lg text-sm font-medium"
                  style={{ 
                    background: loading || success ? 'rgba(0, 200, 255, 0.5)' : 'var(--accent-cyan)',
                    color: '#080c14',
                    cursor: loading || success ? 'not-allowed' : 'pointer',
                    border: 'none'
                  }}
                >
                  {loading ? (
                    <>
                      <span className="inline-block w-full min-w-[260px]">
                        <CinematicLoading
                          compact
                          title="Generation Progress Atmosphere"
                          lines={[
                            'Analyzing scene composition...',
                            'Preparing cinematic lighting...',
                            'Rendering motion frames...',
                          ]}
                        />
                      </span>
                    </>
                  ) : success ? (
                    <>
                      <CheckCircle size={16} />
                      Ingested!
                    </>
                  ) : (
                    <>
                      <Upload size={16} />
                      Ingest Script & Create Project
                    </>
                  )}
                </button>
                
                {!loading && !success && (
                  <button
                    type="button"
                    onClick={() => navigate(-1)}
                    className="px-4 py-3 rounded-lg text-sm"
                    style={{ 
                      background: 'transparent',
                      color: 'var(--text-secondary)',
                      border: '1px solid var(--border)',
                      cursor: 'pointer'
                    }}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </form>
          </StudioPanel>
        </div>
      </div>
    </StudioShell>
  )
}
