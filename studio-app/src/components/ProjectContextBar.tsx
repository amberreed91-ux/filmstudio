import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStudio } from '../context/StudioContext'
import { Share2, Check, Copy, ChevronDown, User, Shield, Pencil, Eye, ShieldCheck } from 'lucide-react'
import { generateShareToken, shareWithCollaborator, type StudioProject, type CollaboratorRole } from '../lib/studioApi'
import CollaboratorRoleBadge from './CollaboratorRoleBadge'
import ProductionScanModal from './ProductionScanModal'

type ProjectContextBarProps = {
  roomName: string
  compact?: boolean
}

type ShareModalProps = {
  project: StudioProject
  onClose: () => void
  onShareComplete: (shareToken: string) => void
}

function ShareModal({ project, onClose, onShareComplete }: ShareModalProps) {
  const [email, setEmail] = useState('')
  const [isSharing, setIsSharing] = useState(false)
  const [shareToken, setShareToken] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedRole, setSelectedRole] = useState<CollaboratorRole>('viewer')
  const [showRoleDropdown, setShowRoleDropdown] = useState(false)

  const roleOptions: Array<{ value: CollaboratorRole; label: string; icon: React.ReactNode }> = [
    { value: 'owner', label: 'Owner', icon: <Shield size={14} /> },
    { value: 'editor', label: 'Editor', icon: <Pencil size={14} /> },
    { value: 'viewer', label: 'Viewer', icon: <Eye size={14} /> },
  ]

  async function handleGenerateShareLink() {
    if (!project.project_id) return
    
    try {
      setIsSharing(true)
      setError(null)
      const response = await generateShareToken(project.project_id)
      setShareToken(response.share_token)
      onShareComplete(response.share_token)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate share link')
    } finally {
      setIsSharing(false)
    }
  }

  async function handleShareWithCollaborator() {
    if (!email.trim() || !project.project_id) return
    
    try {
      setIsSharing(true)
      setError(null)
      await shareWithCollaborator(project.project_id, email.trim(), selectedRole)
      // After sharing, generate a new share token for display
      const response = await generateShareToken(project.project_id)
      setShareToken(response.share_token)
      onShareComplete(response.share_token)
      setEmail('')
      setSelectedRole('viewer')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to share with collaborator')
    } finally {
      setIsSharing(false)
    }
  }

  function getRoleIcon(role: CollaboratorRole) {
    const option = roleOptions.find((r) => r.value === role)
    return option?.icon || <User size={14} />
  }

  function copyToClipboard() {
    if (!shareToken) return
    const shareUrl = `${window.location.origin}/share/${shareToken}`
    navigator.clipboard.writeText(shareUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div
      style={{
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        background: '#0a0f1c',
        border: '1px solid rgba(148, 163, 184, 0.3)',
        borderRadius: '12px',
        padding: '24px',
        width: '420px',
        maxWidth: '90vw',
        zIndex: 1000,
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
      }}
      onClick={(e) => e.stopPropagation()}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '16px',
        }}
      >
        <h3
          style={{
            fontSize: '16px',
            fontWeight: 600,
            color: '#f1f5f9',
          }}
        >
          Share "{project.title || 'Untitled Film'}"
        </h3>
        <button
          type="button"
          onClick={onClose}
          style={{
            fontSize: '20px',
            color: '#94a3b8',
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
          }}
        >
          &times;
        </button>
      </div>

      {/* Selected Role Badge Preview */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: '16px',
          padding: '8px 12px',
          background: '#0f172a',
          border: '1px solid rgba(148, 163, 184, 0.3)',
          borderRadius: '6px',
        }}
      >
        <span
          style={{
            fontSize: '12px',
            fontWeight: 600,
            color: '#94a3b8',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}
        >
          Role:
        </span>
        <CollaboratorRoleBadge role={selectedRole} />
      </div>

      <p
        style={{
          fontSize: '13px',
          color: '#94a3b8',
          marginBottom: '20px',
        }}
      >
        Anyone with this link can view the project in read-only mode.
      </p>

      {!shareToken ? (
        <>
          <label
            style={{
              display: 'block',
              fontSize: '12px',
              fontWeight: 600,
              color: '#cbd5e1',
              marginBottom: '8px',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}
          >
            Share via email (optional)
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="collaborator@example.com"
            style={{
              width: '100%',
              padding: '10px 12px',
              fontSize: '14px',
              background: '#0f172a',
              border: '1px solid rgba(148, 163, 184, 0.4)',
              borderRadius: '6px',
              color: '#f1f5f9',
              marginBottom: '12px',
            }}
            className="focus:outline-none focus:border-cyan-400/60 placeholder:text-slate-500"
          />
          
          {/* Role Selector */}
          <div style={{ marginBottom: '12px' }}>
            <label
              style={{
                display: 'block',
                fontSize: '12px',
                fontWeight: 600,
                color: '#cbd5e1',
                marginBottom: '8px',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              Role
            </label>
            <div style={{ position: 'relative' }}>
              <button
                type="button"
                onClick={() => setShowRoleDropdown(!showRoleDropdown)}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  fontSize: '14px',
                  background: '#0f172a',
                  border: '1px solid rgba(148, 163, 184, 0.4)',
                  borderRadius: '6px',
                  color: '#f1f5f9',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  textAlign: 'left' as const,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {getRoleIcon(selectedRole)}
                  <span>{selectedRole}</span>
                </div>
                <ChevronDown
                  size={16}
                  style={{
                    color: '#94a3b8',
                    transition: 'transform 0.2s',
                    transform: showRoleDropdown ? 'rotate(180deg)' : 'rotate(0deg)',
                  }}
                />
              </button>
              
              {showRoleDropdown && (
                <div
                  style={{
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    right: 0,
                    marginTop: '4px',
                    background: '#0a0f1c',
                    border: '1px solid rgba(148, 163, 184, 0.3)',
                    borderRadius: '6px',
                    padding: '4px',
                    zIndex: 100,
                    boxShadow: '0 10px 25px rgba(0, 0, 0, 0.5)',
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {roleOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => {
                        setSelectedRole(option.value)
                        setShowRoleDropdown(false)
                      }}
                      style={{
                        width: '100%',
                        padding: '8px 12px',
                        fontSize: '13px',
                        background: selectedRole === option.value ? 'rgba(148, 163, 184, 0.2)' : 'transparent',
                        border: 'none',
                        borderRadius: '4px',
                        color: selectedRole === option.value ? '#f1f5f9' : '#94a3b8',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        textAlign: 'left' as const,
                      }}
                    >
                      {option.icon}
                      <span>{option.label}</span>
                      {selectedRole === option.value && (
                        <Check size={14} style={{ color: '#06b6d4', marginLeft: 'auto' }} />
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
          
          <button
            type="button"
            onClick={handleShareWithCollaborator}
            disabled={isSharing || !email.trim()}
            aria-busy={isSharing}
            style={{
              width: '100%',
              padding: '10px 16px',
              fontSize: '14px',
              fontWeight: 600,
              color: '#065f46',
              background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.2) 0%, rgba(6, 95, 70, 0.1) 100%)',
              border: '1px solid rgba(16, 185, 129, 0.4)',
              borderRadius: '6px',
              cursor: isSharing ? 'wait' : 'pointer',
              opacity: isSharing || !email.trim() ? 0.6 : 1,
            }}
          >
            {isSharing ? 'Sharing...' : 'Share with Collaborator'}
          </button>
          <button
            type="button"
            onClick={handleGenerateShareLink}
            disabled={isSharing}
            aria-busy={isSharing}
            style={{
              width: '100%',
              padding: '10px 16px',
              fontSize: '14px',
              fontWeight: 600,
              color: '#f1f5f9',
              background: 'transparent',
              border: '1px solid rgba(148, 163, 184, 0.4)',
              borderRadius: '6px',
              cursor: isSharing ? 'wait' : 'pointer',
              marginTop: '8px',
            }}
          >
            {isSharing ? 'Generating link…' : 'Or just generate a shareable link'}
          </button>
        </>
      ) : (
        <>
          <div
            style={{
              display: 'flex',
              gap: '8px',
              padding: '12px',
              background: '#0f172a',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              borderRadius: '6px',
              marginBottom: '12px',
            }}
          >
            <span
              style={{
                flex: 1,
                fontSize: '13px',
                fontFamily: 'monospace',
                color: '#a7f3d0',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {`${window.location.origin}/share/${shareToken}`}
            </span>
            <button
              type="button"
              onClick={copyToClipboard}
              style={{
                padding: '6px 10px',
                background: copied ? '#059669' : '#064e3b',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              {copied ? (
                <Check size={14} style={{ color: '#ffffff' }} />
              ) : (
                <Copy size={14} style={{ color: '#a7f3d0' }} />
              )}
              <span
                style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#ffffff',
                }}
              >
                {copied ? 'Copied!' : 'Copy'}
              </span>
            </button>
          </div>
          <div
            style={{
              fontSize: '13px',
              color: '#a7f3d0',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <Check size={16} />
            Share link generated
          </div>
        </>
      )}

      {error && (
        <p
          style={{
            fontSize: '13px',
            color: '#fca5a5',
            marginTop: '12px',
          }}
        >
          {error}
        </p>
      )}
    </div>
  )
}

function ShareButton({ project }: { project: StudioProject }) {
  const [isOpen, setIsOpen] = useState(false)

  function handleShareComplete() {
    // Could update project with share token here if needed
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          fontSize: '12px',
          fontWeight: 700,
          color: '#f0f4f8',
          background: 'linear-gradient(135deg, rgba(148, 163, 184, 0.25) 0%, rgba(100, 116, 139, 0.15) 100%)',
          border: '1px solid rgba(148, 163, 184, 0.6)',
          borderRadius: '6px',
          cursor: 'pointer',
          padding: '6px 14px',
          transition: 'all 0.2s ease',
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
          boxShadow: '0 2px 8px rgba(148, 163, 184, 0.2)',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = 'linear-gradient(135deg, rgba(148, 163, 184, 0.35) 0%, rgba(100, 116, 139, 0.25) 100%)'
          e.currentTarget.style.borderColor = 'rgba(148, 163, 184, 0.8)'
          e.currentTarget.style.boxShadow = '0 4px 12px rgba(148, 163, 184, 0.3)'
          e.currentTarget.style.transform = 'translateY(-1px)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = 'linear-gradient(135deg, rgba(148, 163, 184, 0.25) 0%, rgba(100, 116, 139, 0.15) 100%)'
          e.currentTarget.style.borderColor = 'rgba(148, 163, 184, 0.6)'
          e.currentTarget.style.boxShadow = '0 2px 8px rgba(148, 163, 184, 0.2)'
          e.currentTarget.style.transform = 'translateY(0)'
        }}
      >
        <Share2 size={14} />
        Share
      </button>

      {isOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.7)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 999,
          }}
          onClick={() => setIsOpen(false)}
        >
          <ShareModal
            project={project}
            onClose={() => setIsOpen(false)}
            onShareComplete={handleShareComplete}
          />
        </div>
      )}
    </>
  )
}

export default function ProjectContextBar({ roomName, compact = false }: ProjectContextBarProps) {
  const navigate = useNavigate()
  const { activeProject } = useStudio()
  const [isScanModalOpen, setIsScanModalOpen] = useState(false)

  if (!activeProject) return null

  const projectActions = (
    <>
        {/* Right side - Switch film link and Share button */}
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => setIsScanModalOpen(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '11px',
              fontWeight: 800,
              color: '#06b6d4',
              background: 'rgba(6, 182, 212, 0.1)',
              border: '1px solid rgba(6, 182, 212, 0.4)',
              borderRadius: '4px',
              cursor: 'pointer',
              padding: '4px 12px',
              transition: 'all 0.2s ease',
              textTransform: 'uppercase',
              letterSpacing: '0.1em',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(6, 182, 212, 0.2)'
              e.currentTarget.style.borderColor = 'rgba(6, 182, 212, 0.6)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(6, 182, 212, 0.1)'
              e.currentTarget.style.borderColor = 'rgba(6, 182, 212, 0.4)'
            }}
          >
            <ShieldCheck size={14} />
            Run Production Scan
          </button>

          <ShareButton project={activeProject} />
          <button
            type="button"
            onClick={() => navigate('/studio/lobby')}
            style={{
              fontSize: '12px',
              fontWeight: 700,
              color: '#f0f4f8',
              background: 'linear-gradient(135deg, rgba(122, 214, 209, 0.25) 0%, rgba(109, 212, 206, 0.15) 100%)',
              border: '1px solid rgba(122, 214, 209, 0.6)',
              borderRadius: '6px',
              cursor: 'pointer',
              padding: '6px 14px',
              transition: 'all 0.2s ease',
              textTransform: 'uppercase',
              letterSpacing: '0.1em',
              boxShadow: '0 2px 8px rgba(122, 214, 209, 0.2)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'linear-gradient(135deg, rgba(122, 214, 209, 0.35) 0%, rgba(109, 212, 206, 0.25) 100%)'
              e.currentTarget.style.borderColor = 'rgba(122, 214, 209, 0.8)'
              e.currentTarget.style.boxShadow = '0 4px 12px rgba(122, 214, 209, 0.3)'
              e.currentTarget.style.transform = 'translateY(-1px)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'linear-gradient(135deg, rgba(122, 214, 209, 0.25) 0%, rgba(109, 212, 206, 0.15) 100%)'
              e.currentTarget.style.borderColor = 'rgba(122, 214, 209, 0.6)'
              e.currentTarget.style.boxShadow = '0 2px 8px rgba(122, 214, 209, 0.2)'
              e.currentTarget.style.transform = 'translateY(0)'
            }}
          >
            Switch film
          </button>
        </div>
    </>
  )

  return (
    <>
      <div
        style={{
          minHeight: '32px',
          flexWrap: 'wrap',
          gap: '8px',
          paddingTop: '6px',
          paddingBottom: '6px',
          background: '#040810',
          borderBottom: '1px solid #1a2744',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingLeft: '16px',
          paddingRight: '16px',
        }}
      >
        {/* Left side - Film title and room name */}
        <div className="min-w-0 flex-1" style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>

          <div
            style={{
              fontSize: '13px',
              fontWeight: 600,
              color: '#e8edf5',
              lineHeight: '1.3',
              overflowWrap: 'anywhere',
            }}
          >
            {activeProject.title || 'Untitled Film'}
          </div>
          <div
            style={{
              fontSize: '9px',
              fontFamily: 'monospace',
              color: '#94a3b8',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              lineHeight: '1',
            }}
          >
            {roomName}
          </div>
        </div>

        {compact ? <details className="min-w-0 max-w-full text-xs text-zinc-300 open:basis-full"><summary className="cursor-pointer rounded px-2 py-1.5">Film actions</summary><div className="pt-3">{projectActions}</div></details> : projectActions}
      </div>

      <ProductionScanModal 
        projectId={activeProject.project_id} 
        isOpen={isScanModalOpen} 
        onClose={() => setIsScanModalOpen(false)} 
      />
    </>
  )
}
