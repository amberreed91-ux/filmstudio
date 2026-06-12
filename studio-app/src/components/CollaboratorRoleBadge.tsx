import type { CollaboratorRole } from '../lib/studioApi'

type CollaboratorRoleBadgeProps = {
  role: CollaboratorRole
  className?: string
}

const ROLE_CONFIG: Record<CollaboratorRole, { label: string; color: string; bgColor: string }> = {
  owner: {
    label: 'Owner',
    color: '#f43f5e', // rose-500
    bgColor: 'rgba(244, 63, 94, 0.15)',
  },
  editor: {
    label: 'Editor',
    color: '#f59e0b', // amber-500
    bgColor: 'rgba(245, 158, 11, 0.15)',
  },
  viewer: {
    label: 'Viewer',
    color: '#06b6d4', // cyan-500
    bgColor: 'rgba(6, 182, 212, 0.15)',
  },
}

const ROLE_DARK_CONFIG: Record<CollaboratorRole, { label: string; textClass: string; bgClass: string }> = {
  owner: {
    label: 'Owner',
    textClass: 'text-rose-300',
    bgClass: 'bg-rose-500/15',
  },
  editor: {
    label: 'Editor',
    textClass: 'text-amber-300',
    bgClass: 'bg-amber-500/15',
  },
  viewer: {
    label: 'Viewer',
    textClass: 'text-cyan-300',
    bgClass: 'bg-cyan-500/15',
  },
}

export default function CollaboratorRoleBadge({ role, className = '' }: CollaboratorRoleBadgeProps) {
  const config = ROLE_DARK_CONFIG[role] || ROLE_DARK_CONFIG.viewer

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider border ${config.bgClass} ${config.textClass} border-white/10 ${className}`}
      style={{
        border: '1px solid rgba(255, 255, 255, 0.1)',
      }}
    >
      {config.label}
    </span>
  )
}

// Helper to get role display properties
export function getRoleProperties(role: CollaboratorRole) {
  return ROLE_CONFIG[role] || ROLE_CONFIG.viewer
}

// Helper to check permissions
export function canEdit(role: CollaboratorRole): boolean {
  return role === 'owner' || role === 'editor'
}

export function canDelete(role: CollaboratorRole): boolean {
  return role === 'owner'
}

export function canComment(role: CollaboratorRole): boolean {
  return role === 'owner' || role === 'editor' || role === 'viewer'
}

export function canApprove(role: CollaboratorRole): boolean {
  return role === 'owner' || role === 'editor'
}
