import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import {
  AlertCircle,
  Brain,
  CheckCircle2,
  Download,
  Edit3,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from 'lucide-react'
import StudioShell from '../components/StudioShell'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import UniverseGraph3D, { NODE_TYPE_LEGEND } from '../components/UniverseGraph3D'
import { useStudio } from '../context/StudioContext'
import {
  deleteUniverseNode,
  exportUniverseBible,
  forceAutoPopulateUniverse,
  getUniverseAbsences,
  getUniverseGraph,
  saveUniverseNode,
  saveUniverseRelationship,
  triggerDebate,
} from '../lib/studioApi'
import type {
  AbsenceReport,
  UniverseGraphData,
  UniverseNode,
  UniverseRelationship,
} from '../types/universe'
import { persistActiveProjectId } from '../lib/projectContext'

// ── Types ──────────────────────────────────────────────────────────────────

type CategoryFilter = 'all' | 'character' | 'location' | 'object' | 'lore'
type CharacterRole = 'protagonist' | 'antagonist' | 'supporting' | 'minor'
type RelationshipType = 'ally' | 'rival' | 'love' | 'family' | 'mentor'
type FilterMode = 'all' | 'protagonists' | 'antagonists'

interface CreateCharacterForm {
  name: string
  role: CharacterRole
  description: string
}

interface CreateRelationshipForm {
  fromNode: string
  relationshipType: RelationshipType
  toNode: string
}

// ── Constants ──────────────────────────────────────────────────────────────

const ROLE_LABELS: Record<CharacterRole, string> = {
  protagonist: 'Protagonist',
  antagonist: 'Antagonist',
  supporting: 'Supporting',
  minor: 'Minor',
}

const RELATIONSHIP_LABELS: Record<RelationshipType, string> = {
  ally: 'Ally',
  rival: 'Rival',
  love: 'Love Interest',
  family: 'Family',
  mentor: 'Mentor',
}

// ── Component ──────────────────────────────────────────────────────────────

const UniverseGraphPage: React.FC = () => {
  const { projectId } = useParams()
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const { activeProjectId } = useStudio()

  const effectiveProjectId = activeProjectId || projectId || queryProjectId || null

  // ── Core state ────────────────────────────────────────────────────────────
  const [data, setData] = useState<UniverseGraphData | null>(null)
  const [absences, setAbsences] = useState<AbsenceReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [filterMode, setFilterMode] = useState<FilterMode>('all')
  const [selectedNode, setSelectedNode] = useState<UniverseNode | null>(null)
  const [isExporting, setIsExporting] = useState(false)
  const [detailPanelOpen, setDetailPanelOpen] = useState(false)

  // ── Modal state ───────────────────────────────────────────────────────────
  const [showAddCharacter, setShowAddCharacter] = useState(false)
  const [showAddRelationship, setShowAddRelationship] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [creating, setCreating] = useState(false)
  const [simulating, setSimulating] = useState(false)

  const [charForm, setCharForm] = useState<CreateCharacterForm>({
    name: '',
    role: 'supporting',
    description: '',
  })
  const [relForm, setRelForm] = useState<CreateRelationshipForm>({
    fromNode: '',
    relationshipType: 'ally',
    toNode: '',
  })
  const [editForm, setEditForm] = useState<CreateCharacterForm>({
    name: '',
    role: 'supporting',
    description: '',
  })

  // ── Persist project ID ────────────────────────────────────────────────────
  useEffect(() => {
    if (effectiveProjectId) persistActiveProjectId(effectiveProjectId)
  }, [effectiveProjectId])

  // ── Load data ─────────────────────────────────────────────────────────────
  const loadData = useCallback(async () => {
    if (!effectiveProjectId) return
    setLoading(true)
    setError('')
    try {
      const [graphRes, absenceRes] = await Promise.all([
        getUniverseGraph(effectiveProjectId),
        getUniverseAbsences(effectiveProjectId),
      ])
      setData(graphRes)
      setAbsences(absenceRes)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load universe graph')
    } finally {
      setLoading(false)
    }
  }, [effectiveProjectId])

  useEffect(() => {
    void loadData()
  }, [loadData])

  // ── Derived metrics ───────────────────────────────────────────────────────
  const metrics = useMemo(() => {
    if (!data) return { characters: 0, relationships: 0, arcs: 0, consistency: 0 }
    const characters = data.nodes.filter((n) => n.node_type === 'character').length
    const relationships = data.relationships.length
    const arcs = new Set(data.nodes.map((n) => n.universe_tags).flat()).size
    const consistency = data.nodes.length > 0 ? Math.min(95, 60 + characters * 5 + relationships * 2) : 0
    return { characters, relationships, arcs, consistency }
  }, [data])

  // ── Filtered nodes ────────────────────────────────────────────────────────
  const filteredNodes = useMemo(() => {
    if (!data) return []
    let nodes = data.nodes
    if (category !== 'all') {
      nodes = nodes.filter((n) => n.node_type === category)
    }
    if (filterMode === 'protagonists') {
      nodes = nodes.filter((n) => n.node_type === 'character' && n.universe_tags.includes('protagonist'))
    } else if (filterMode === 'antagonists') {
      nodes = nodes.filter((n) => n.node_type === 'character' && n.universe_tags.includes('antagonist'))
    }
    return nodes
  }, [data, category, filterMode])


  // ── Character nodes for relationship modal ────────────────────────────────
  const characterNodes = useMemo(() => {
    if (!data) return []
    return data.nodes.filter((n) => n.node_type === 'character')
  }, [data])

  // ── Selected node relationships ───────────────────────────────────────────
  const selectedNodeRelationships = useMemo(() => {
    if (!data || !selectedNode) return []
    return data.relationships
      .filter((r) => r.from_node === selectedNode.node_id || r.to_node === selectedNode.node_id)
      .map((r) => {
        const otherId = r.from_node === selectedNode.node_id ? r.to_node : r.from_node
        const otherNode = data.nodes.find((n) => n.node_id === otherId)
        return {
          relationshipId: r.relationship_id,
          type: r.relationship_type,
          characterName: otherNode?.name || 'Unknown',
          characterId: otherId,
        }
      })
  }, [data, selectedNode])

  // ── Scenes the selected node appears in ───────────────────────────────────
  const selectedNodeScenes = useMemo(() => {
    if (!selectedNode) return []
    const scenes: string[] = []
    if (selectedNode.first_scene) scenes.push(selectedNode.first_scene)
    if (selectedNode.last_scene && selectedNode.last_scene !== selectedNode.first_scene) {
      scenes.push(selectedNode.last_scene)
    }
    return scenes
  }, [selectedNode])

  // ── Handlers ──────────────────────────────────────────────────────────────
  const handleNodeClick = useCallback((node: UniverseNode) => {
    setSelectedNode(node)
    setDetailPanelOpen(true)
  }, [])

  const handleNodeHover = useCallback((_node: UniverseNode | null) => {
    // Hover state handled internally by 3D component
  }, [])

  const handleCreateCharacter = useCallback(async () => {
    if (!effectiveProjectId || !charForm.name.trim()) return
    setCreating(true)
    setError('')
    try {
      const newNode: UniverseNode = {
        node_id: `char_${Date.now()}`,
        project_id: effectiveProjectId,
        node_type: 'character',
        name: charForm.name.trim(),
        description: charForm.description.trim(),
        universe_tags: [charForm.role],
        connected_nodes: [],
      }
      await saveUniverseNode(effectiveProjectId, newNode)
      setSuccess(`Character "${charForm.name}" created`)
      setShowAddCharacter(false)
      setCharForm({ name: '', role: 'supporting', description: '' })
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create character')
    } finally {
      setCreating(false)
    }
  }, [effectiveProjectId, charForm, loadData])

  const handleCreateRelationship = useCallback(async () => {
    if (!effectiveProjectId || !relForm.fromNode || !relForm.toNode || relForm.fromNode === relForm.toNode) return
    setCreating(true)
    setError('')
    try {
      const newRel: UniverseRelationship = {
        relationship_id: `rel_${Date.now()}`,
        project_id: effectiveProjectId,
        from_node: relForm.fromNode,
        to_node: relForm.toNode,
        relationship_type: relForm.relationshipType,
        description: RELATIONSHIP_LABELS[relForm.relationshipType],
      }
      await saveUniverseRelationship(effectiveProjectId, newRel)
      setSuccess('Relationship created')
      setShowAddRelationship(false)
      setRelForm({ fromNode: '', relationshipType: 'ally', toNode: '' })
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create relationship')
    } finally {
      setCreating(false)
    }
  }, [effectiveProjectId, relForm, loadData])

  const handleDeleteNode = useCallback(async () => {
    if (!effectiveProjectId || !selectedNode) return
    setCreating(true)
    setError('')
    try {
      await deleteUniverseNode(effectiveProjectId, selectedNode.node_id)
      setSuccess(`"${selectedNode.name}" deleted`)
      setShowDeleteConfirm(false)
      setSelectedNode(null)
      setDetailPanelOpen(false)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete node')
    } finally {
      setCreating(false)
    }
  }, [effectiveProjectId, selectedNode, loadData])

  const handleEditNode = useCallback(async () => {
    if (!effectiveProjectId || !selectedNode || !editForm.name.trim()) return
    setCreating(true)
    setError('')
    try {
      const updatedNode: UniverseNode = {
        ...selectedNode,
        name: editForm.name.trim(),
        description: editForm.description.trim(),
        universe_tags: selectedNode.universe_tags.includes(editForm.role)
          ? selectedNode.universe_tags
          : [...selectedNode.universe_tags.filter((t) => !['protagonist', 'antagonist', 'supporting', 'minor'].includes(t)), editForm.role],
      }
      await saveUniverseNode(effectiveProjectId, updatedNode)
      setSuccess(`"${editForm.name}" updated`)
      setShowEditModal(false)
      setSelectedNode(updatedNode)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update node')
    } finally {
      setCreating(false)
    }
  }, [effectiveProjectId, selectedNode, editForm, loadData])

  const handleSimulateMind = useCallback(async () => {
    if (!effectiveProjectId || !selectedNode) return
    setSimulating(true)
    setError('')
    try {
      const { debate } = await triggerDebate({
        project_id: effectiveProjectId,
        query: `Simulate the psychological mind of character "${selectedNode.name}": motivations, internal conflicts, emotional drives, decision-making patterns, and how they would react under pressure. Description: ${selectedNode.description}`,
      })
      setSuccess(`Mind simulation for "${selectedNode.name}" complete`)
      // Could display debate.synthesis in a panel
      console.log('[CharacterMind] Simulation result:', debate.synthesis)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Mind simulation failed')
    } finally {
      setSimulating(false)
    }
  }, [effectiveProjectId, selectedNode])

  const handleExportGraph = useCallback(async () => {
    if (!effectiveProjectId) return
    setIsExporting(true)
    setError('')
    try {
      const result = await exportUniverseBible(effectiveProjectId)
      const blob = new Blob([typeof result === 'string' ? result : JSON.stringify(result, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'universe-graph-export.json'
      a.click()
      URL.revokeObjectURL(url)
      setSuccess('Graph exported')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setIsExporting(false)
    }
  }, [effectiveProjectId])

  const handleAutoPopulate = useCallback(async () => {
    if (!effectiveProjectId) return
    setLoading(true)
    setError('')
    try {
      const result = await forceAutoPopulateUniverse(effectiveProjectId)
      setData(result)
      setSuccess('Universe auto-populated from scenes')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Auto-populate failed')
    } finally {
      setLoading(false)
    }
  }, [effectiveProjectId])

  const openEditModal = useCallback(() => {
    if (!selectedNode) return
    const role = selectedNode.universe_tags.find((t) => ['protagonist', 'antagonist', 'supporting', 'minor'].includes(t)) as CharacterRole || 'supporting'
    setEditForm({
      name: selectedNode.name,
      role,
      description: selectedNode.description,
    })
    setShowEditModal(true)
  }, [selectedNode])


  // ── Loading state ─────────────────────────────────────────────────────────
  if (loading && !data) {
    return (
      <StudioShell title="Universe" subtitle="The Universe — Story Graph">
        <ProjectGuard>
          <div className="flex items-center justify-center py-20">
            <Loader2 size={32} className="animate-spin" style={{ color: 'var(--color-primary)' }} />
          </div>
        </ProjectGuard>
      </StudioShell>
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <>
      <StudioShell title="Universe" subtitle="The Universe — Story Graph">
      <ProjectGuard>
        <ProjectContextBar roomName="universe" />

        {/* Status messages */}
        <div className="px-4 pt-2">
          {error && (
            <div className="mb-2 rounded-lg border border-rose-400/40 bg-rose-500/10 px-4 py-2 text-sm text-rose-200">
              {error}
            </div>
          )}
          {success && (
            <div className="mb-2 rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-200">
              {success}
            </div>
          )}
        </div>

        {/* ── FULL-BLEED GRAPH CANVAS ───────────────────────────────────── */}
        <div className="relative h-[calc(100vh-140px)] w-full overflow-hidden px-4 pb-4">
          <div className="glass-panel relative h-full w-full overflow-hidden rounded-xl">
            {/* 3D Universe Graph */}
            <UniverseGraph3D
              nodes={filteredNodes}
              relationships={data?.relationships || []}
              selectedNodeId={selectedNode?.node_id || null}
              onNodeClick={handleNodeClick}
              onNodeHover={handleNodeHover}
            />

            {/* ── FLOATING CONTROL PANEL (top-left, 288px) ─────────────── */}
            <div className="glass-panel absolute left-4 top-4 z-20 w-[288px] rounded-xl p-4 space-y-3">
              {/* Story Graph Integrity metrics */}
              <div className="text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>
                Story Graph Integrity
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg border p-2" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                  <div className="text-[9px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    Characters
                  </div>
                  <div className="text-lg font-bold" style={{ color: 'var(--color-primary)' }}>
                    {metrics.characters}
                  </div>
                </div>
                <div className="rounded-lg border p-2" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                  <div className="text-[9px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    Relationships
                  </div>
                  <div className="text-lg font-bold" style={{ color: 'var(--color-secondary)' }}>
                    {metrics.relationships}
                  </div>
                </div>
                <div className="rounded-lg border p-2" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                  <div className="text-[9px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    Story Arcs
                  </div>
                  <div className="text-lg font-bold" style={{ color: 'var(--color-on-surface)' }}>
                    {metrics.arcs}
                  </div>
                </div>
                <div className="rounded-lg border p-2" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                  <div className="text-[9px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    Consistency
                  </div>
                  <div className="text-lg font-bold" style={{ color: 'var(--color-primary)' }}>
                    {metrics.consistency}%
                  </div>
                </div>
              </div>

              {/* Add Character button */}
              <button
                type="button"
                onClick={() => setShowAddCharacter(true)}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02]"
                style={{
                  background: 'rgba(255,209,101,0.15)',
                  color: 'var(--color-primary)',
                  border: '1px solid rgba(255,209,101,0.3)',
                }}
              >
                <Plus size={14} />
                ADD CHARACTER
              </button>

              {/* Add Relationship button */}
              <button
                type="button"
                onClick={() => setShowAddRelationship(true)}
                className="glass-panel flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02]"
                style={{ color: 'var(--color-secondary)' }}
              >
                <Plus size={14} />
                ADD RELATIONSHIP
              </button>

              {/* Filter row */}
              <div>
                <div className="mb-1 text-[9px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  FILTER
                </div>
                <div className="flex gap-1">
                  {(['all', 'protagonists', 'antagonists'] as FilterMode[]).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setFilterMode(mode)}
                      className={`status-chip flex-1 rounded border px-1.5 py-1 text-[8px] font-bold uppercase tracking-[0.08em] transition-all ${
                        filterMode === mode
                          ? 'border-primary/50 bg-primary/15 text-primary'
                          : 'hover:bg-white/8'
                      }`}
                      style={{
                        borderColor: filterMode === mode ? undefined : 'rgba(255,255,255,0.08)',
                        color: filterMode === mode ? undefined : 'var(--color-on-surface-variant)',
                      }}
                    >
                      {mode === 'all' ? 'SHOW ALL' : mode.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>

              {/* Category filter */}
              <div>
                <div className="mb-1 text-[9px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  CATEGORY
                </div>
                <div className="flex flex-wrap gap-1">
                  {(['all', 'character', 'location', 'object', 'lore'] as CategoryFilter[]).map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => setCategory(cat)}
                      className={`status-chip rounded border px-1.5 py-0.5 text-[8px] font-bold uppercase transition-all ${
                        category === cat
                          ? 'border-secondary/50 bg-secondary/15 text-secondary'
                          : 'hover:bg-white/8'
                      }`}
                      style={{
                        borderColor: category === cat ? undefined : 'rgba(255,255,255,0.08)',
                        color: category === cat ? undefined : 'var(--color-on-surface-variant)',
                      }}
                    >
                      {cat}
                    </button>
                  ))}
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={handleAutoPopulate}
                  disabled={loading}
                  className="glass-panel flex flex-1 items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[8px] font-bold uppercase tracking-[0.1em] transition-all hover:scale-[1.02] disabled:opacity-50"
                  style={{ color: 'var(--color-on-surface-variant)' }}
                >
                  <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
                  AUTO-POPULATE
                </button>
                <button
                  type="button"
                  onClick={handleExportGraph}
                  disabled={isExporting}
                  className="glass-panel flex flex-1 items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[8px] font-bold uppercase tracking-[0.1em] transition-all hover:scale-[1.02] disabled:opacity-50"
                  style={{ color: 'var(--color-on-surface-variant)' }}
                >
                  {isExporting ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                  EXPORT
                </button>
              </div>

              {/* Absences warning */}
              {absences && absences.absences.length > 0 && (
                <div className="rounded-lg border border-amber-400/30 bg-amber-500/5 p-2">
                  <div className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-[0.1em]" style={{ color: '#fbbf24' }}>
                    <AlertCircle size={12} />
                    {absences.absences.length} ABSENCE{absences.absences.length > 1 ? 'S' : ''}
                  </div>
                  <div className="mt-1 space-y-0.5">
                    {absences.absences.slice(0, 3).map((a) => (
                      <div key={a.node_id} className="text-[8px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                        {a.name} — {a.advisory}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Node-type color legend */}
              <div
                className="rounded-lg border p-2"
                style={{ borderColor: 'rgba(255,255,255,0.06)' }}
              >
                <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  NODE TYPES
                </div>
                <div className="flex flex-wrap gap-x-2.5 gap-y-1">
                  {NODE_TYPE_LEGEND.map(({ key, label, style }) => (
                    <div
                      key={key}
                      className="flex items-center gap-1.5"
                      title={label}
                    >
                      <span
                        className="status-dot inline-block rounded-full"
                        style={{
                          width: 8,
                          height: 8,
                          background: style.fill,
                          boxShadow: `0 0 6px ${style.glow}`,
                        }}
                      />
                      <span
                        className="font-status-xs"
                        style={{ color: 'var(--color-on-surface-variant)' }}
                      >
                        {label}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* ── CHARACTER DETAIL PANEL (right, slides in) ────────────── */}
            {detailPanelOpen && selectedNode && (
              <div
                className="glass-panel absolute right-4 top-4 z-20 w-[320px] rounded-xl p-4"
                style={{
                  animation: 'slideInRight 0.3s ease-out',
                  maxHeight: 'calc(100% - 32px)',
                  overflowY: 'auto',
                }}
              >
                {/* Close button */}
                <button
                  type="button"
                  onClick={() => setDetailPanelOpen(false)}
                  className="absolute right-3 top-3 rounded p-1 transition-all hover:bg-white/10"
                  style={{ color: 'var(--color-on-surface-variant)' }}
                >
                  <X size={16} />
                </button>

                {/* Character name */}
                <h2 className="pr-8 text-xl font-bold" style={{ color: 'var(--color-on-surface)' }}>
                  {selectedNode.name}
                </h2>

                {/* Role badge */}
                <div className="mt-2 flex flex-wrap gap-1">
                  <span
                    className="status-chip rounded px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.1em]"
                    style={{ background: 'rgba(0,212,170,0.1)', color: '#00d4aa' }}
                  >
                    {selectedNode.node_type}
                  </span>
                  {selectedNode.universe_tags
                    .filter((t) => ['protagonist', 'antagonist', 'supporting', 'minor'].includes(t))
                    .map((tag) => (
                      <span
                        key={tag}
                        className="status-chip rounded px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.1em]"
                        style={{
                          background: tag === 'protagonist' ? 'rgba(255,209,101,0.1)' : tag === 'antagonist' ? 'rgba(244,63,94,0.1)' : 'rgba(255,255,255,0.05)',
                          color: tag === 'protagonist' ? 'var(--color-primary)' : tag === 'antagonist' ? 'var(--color-error)' : 'var(--color-on-surface-variant)',
                        }}
                      >
                        {ROLE_LABELS[tag as CharacterRole] || tag}
                      </span>
                    ))}
                </div>

                {/* Description */}
                <p className="mt-3 text-sm leading-relaxed" style={{ color: 'var(--color-on-surface-variant)' }}>
                  {selectedNode.description || 'No description available.'}
                </p>

                {/* Scenes appearing in */}
                {selectedNodeScenes.length > 0 && (
                  <div className="mt-4">
                    <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                      APPEARS IN
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {selectedNodeScenes.map((scene) => (
                        <span
                          key={scene}
                          className="status-chip rounded bg-white/5 px-1.5 py-0.5 text-[9px] font-bold"
                          style={{ color: 'var(--color-on-surface)' }}
                        >
                          {scene}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Relationships */}
                {selectedNodeRelationships.length > 0 && (
                  <div className="mt-4">
                    <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                      RELATIONSHIPS
                    </div>
                    <div className="space-y-1">
                      {selectedNodeRelationships.map((rel) => (
                        <div
                          key={rel.relationshipId}
                          className="flex items-center justify-between rounded border px-2 py-1"
                          style={{ borderColor: 'rgba(255,255,255,0.06)' }}
                        >
                          <span className="text-[11px]" style={{ color: 'var(--color-on-surface)' }}>
                            {rel.characterName}
                          </span>
                          <span
                            className="status-chip rounded px-1.5 py-0.5 text-[8px] font-bold uppercase"
                            style={{ background: 'rgba(76,215,246,0.1)', color: 'var(--color-secondary)' }}
                          >
                            {rel.type}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Action buttons */}
                <div className="mt-4 space-y-2">
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={openEditModal}
                      className="glass-panel flex flex-1 items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[9px] font-bold uppercase tracking-[0.1em] transition-all hover:scale-[1.02]"
                      style={{ color: 'var(--color-on-surface-variant)' }}
                    >
                      <Edit3 size={12} />
                      EDIT
                    </button>
                    <button
                      type="button"
                      onClick={handleSimulateMind}
                      disabled={simulating}
                      className="glass-panel flex flex-1 items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[9px] font-bold uppercase tracking-[0.1em] transition-all hover:scale-[1.02] disabled:opacity-50"
                      style={{ color: 'var(--color-secondary)' }}
                    >
                      {simulating ? <Loader2 size={12} className="animate-spin" /> : <Brain size={12} />}
                      SIMULATE MIND
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowDeleteConfirm(true)}
                    className="flex w-full items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[9px] font-bold uppercase tracking-[0.1em] transition-all hover:scale-[1.02]"
                    style={{
                      background: 'rgba(244,63,94,0.1)',
                      color: 'var(--color-error)',
                      border: '1px solid rgba(244,63,94,0.2)',
                    }}
                  >
                    <Trash2 size={12} />
                    DELETE
                  </button>
                </div>
              </div>
            )}

            {/* ── BOTTOM LABEL OVERLAY ──────────────────────────────────── */}
            <div
              className="absolute bottom-3 left-1/2 -translate-x-1/2 text-[10px] font-semibold uppercase tracking-[0.3em]"
              style={{ color: 'var(--color-on-surface-variant)', opacity: 0.5 }}
            >
              THE UNIVERSE — STORY GRAPH
            </div>
          </div>
        </div>

        {/* ── ADD CHARACTER MODAL ──────────────────────────────────────── */}
        {showAddCharacter && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowAddCharacter(false)}>
            <div className="glass-panel w-[400px] rounded-xl p-6" onClick={(e) => e.stopPropagation()}>
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-lg font-bold" style={{ color: 'var(--color-on-surface)' }}>
                  Add Character
                </h3>
                <button type="button" onClick={() => setShowAddCharacter(false)} className="rounded p-1 hover:bg-white/10">
                  <X size={18} style={{ color: 'var(--color-on-surface-variant)' }} />
                </button>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    NAME
                  </label>
                  <input
                    type="text"
                    value={charForm.name}
                    onChange={(e) => setCharForm((p) => ({ ...p, name: e.target.value }))}
                    placeholder="Character name"
                    className="cyber-input w-full rounded px-3 py-2 text-sm outline-none"
                    style={{ color: 'var(--color-on-surface)' }}
                    autoFocus
                  />
                </div>
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    ROLE
                  </label>
                  <select
                    value={charForm.role}
                    onChange={(e) => setCharForm((p) => ({ ...p, role: e.target.value as CharacterRole }))}
                    className="glass-panel w-full rounded px-3 py-2 text-sm outline-none"
                    style={{ color: 'var(--color-on-surface)' }}
                  >
                    {(Object.keys(ROLE_LABELS) as CharacterRole[]).map((role) => (
                      <option key={role} value={role} className="bg-zinc-900">
                        {ROLE_LABELS[role]}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    DESCRIPTION
                  </label>
                  <textarea
                    value={charForm.description}
                    onChange={(e) => setCharForm((p) => ({ ...p, description: e.target.value }))}
                    placeholder="Character description..."
                    rows={3}
                    className="cyber-input w-full rounded px-3 py-2 text-sm outline-none"
                    style={{ color: 'var(--color-on-surface)' }}
                  />
                </div>
                <button
                  type="button"
                  onClick={handleCreateCharacter}
                  disabled={creating || !charForm.name.trim()}
                  className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[11px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.01] disabled:opacity-50"
                  style={{
                    background: 'rgba(255,209,101,0.15)',
                    color: 'var(--color-primary)',
                    border: '1px solid rgba(255,209,101,0.3)',
                  }}
                >
                  {creating ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                  CREATE
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── ADD RELATIONSHIP MODAL ──────────────────────────────────── */}
        {showAddRelationship && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowAddRelationship(false)}>
            <div className="glass-panel w-[400px] rounded-xl p-6" onClick={(e) => e.stopPropagation()}>
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-lg font-bold" style={{ color: 'var(--color-on-surface)' }}>
                  Add Relationship
                </h3>
                <button type="button" onClick={() => setShowAddRelationship(false)} className="rounded p-1 hover:bg-white/10">
                  <X size={18} style={{ color: 'var(--color-on-surface-variant)' }} />
                </button>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    FROM CHARACTER
                  </label>
                  <select
                    value={relForm.fromNode}
                    onChange={(e) => setRelForm((p) => ({ ...p, fromNode: e.target.value }))}
                    className="glass-panel w-full rounded px-3 py-2 text-sm outline-none"
                    style={{ color: 'var(--color-on-surface)' }}
                  >
                    <option value="" className="bg-zinc-900">Select character...</option>
                    {characterNodes.map((node) => (
                      <option key={node.node_id} value={node.node_id} className="bg-zinc-900">
                        {node.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    RELATIONSHIP TYPE
                  </label>
                  <select
                    value={relForm.relationshipType}
                    onChange={(e) => setRelForm((p) => ({ ...p, relationshipType: e.target.value as RelationshipType }))}
                    className="glass-panel w-full rounded px-3 py-2 text-sm outline-none"
                    style={{ color: 'var(--color-on-surface)' }}
                  >
                    {(Object.keys(RELATIONSHIP_LABELS) as RelationshipType[]).map((type) => (
                      <option key={type} value={type} className="bg-zinc-900">
                        {RELATIONSHIP_LABELS[type]}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    TO CHARACTER
                  </label>
                  <select
                    value={relForm.toNode}
                    onChange={(e) => setRelForm((p) => ({ ...p, toNode: e.target.value }))}
                    className="glass-panel w-full rounded px-3 py-2 text-sm outline-none"
                    style={{ color: 'var(--color-on-surface)' }}
                  >
                    <option value="" className="bg-zinc-900">Select character...</option>
                    {characterNodes.filter((n) => n.node_id !== relForm.fromNode).map((node) => (
                      <option key={node.node_id} value={node.node_id} className="bg-zinc-900">
                        {node.name}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  onClick={handleCreateRelationship}
                  disabled={creating || !relForm.fromNode || !relForm.toNode || relForm.fromNode === relForm.toNode}
                  className="glass-panel flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[11px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.01] disabled:opacity-50"
                  style={{ color: 'var(--color-secondary)' }}
                >
                  {creating ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                  CREATE
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── EDIT MODAL ───────────────────────────────────────────────── */}
        {showEditModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowEditModal(false)}>
            <div className="glass-panel w-[400px] rounded-xl p-6" onClick={(e) => e.stopPropagation()}>
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-lg font-bold" style={{ color: 'var(--color-on-surface)' }}>
                  Edit Character
                </h3>
                <button type="button" onClick={() => setShowEditModal(false)} className="rounded p-1 hover:bg-white/10">
                  <X size={18} style={{ color: 'var(--color-on-surface-variant)' }} />
                </button>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    NAME
                  </label>
                  <input
                    type="text"
                    value={editForm.name}
                    onChange={(e) => setEditForm((p) => ({ ...p, name: e.target.value }))}
                    className="cyber-input w-full rounded px-3 py-2 text-sm outline-none"
                    style={{ color: 'var(--color-on-surface)' }}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    ROLE
                  </label>
                  <select
                    value={editForm.role}
                    onChange={(e) => setEditForm((p) => ({ ...p, role: e.target.value as CharacterRole }))}
                    className="glass-panel w-full rounded px-3 py-2 text-sm outline-none"
                    style={{ color: 'var(--color-on-surface)' }}
                  >
                    {(Object.keys(ROLE_LABELS) as CharacterRole[]).map((role) => (
                      <option key={role} value={role} className="bg-zinc-900">
                        {ROLE_LABELS[role]}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    DESCRIPTION
                  </label>
                  <textarea
                    value={editForm.description}
                    onChange={(e) => setEditForm((p) => ({ ...p, description: e.target.value }))}
                    rows={3}
                    className="cyber-input w-full rounded px-3 py-2 text-sm outline-none"
                    style={{ color: 'var(--color-on-surface)' }}
                  />
                </div>
                <button
                  type="button"
                  onClick={handleEditNode}
                  disabled={creating}
                  className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[11px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.01] disabled:opacity-50"
                  style={{
                    background: 'rgba(255,209,101,0.15)',
                    color: 'var(--color-primary)',
                    border: '1px solid rgba(255,209,101,0.3)',
                  }}
                >
                  {creating ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                  SAVE CHANGES
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── DELETE CONFIRM MODAL ─────────────────────────────────────── */}
        {showDeleteConfirm && selectedNode && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowDeleteConfirm(false)}>
            <div className="glass-panel w-[360px] rounded-xl p-6" onClick={(e) => e.stopPropagation()}>
              <div className="mb-2 flex items-center gap-2">
                <AlertCircle size={20} style={{ color: 'var(--color-error)' }} />
                <h3 className="text-lg font-bold" style={{ color: 'var(--color-on-surface)' }}>
                  Delete Character
                </h3>
              </div>
              <p className="mb-4 text-sm" style={{ color: 'var(--color-on-surface-variant)' }}>
                Are you sure you want to delete "{selectedNode.name}"? This will also remove all relationships involving this character. This cannot be undone.
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowDeleteConfirm(false)}
                  className="glass-panel flex-1 rounded-lg px-4 py-2 text-[11px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01]"
                  style={{ color: 'var(--color-on-surface-variant)' }}
                >
                  CANCEL
                </button>
                <button
                  type="button"
                  onClick={handleDeleteNode}
                  disabled={creating}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-lg px-4 py-2 text-[11px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01] disabled:opacity-50"
                  style={{
                    background: 'rgba(244,63,94,0.15)',
                    color: 'var(--color-error)',
                    border: '1px solid rgba(244,63,94,0.3)',
                  }}
                >
                  {creating ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  DELETE
                </button>
              </div>
            </div>
          </div>
        )}
      </ProjectGuard>
    </StudioShell>
    </>
  )
}

export default UniverseGraphPage
