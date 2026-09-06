import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import {
  AlertCircle,
  Brain,
  BookOpen,
  Box,
  ChevronRight,
  Link2,
  MapPin,
  Orbit,
  Search,
  UserRound,
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
import UniverseGraph3D, { getNodeTypeStyle, NODE_TYPE_LEGEND } from '../components/UniverseGraph3D'
import { useProjectRouteContext } from '../hooks/useProjectRouteContext'
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

  const { projectId: effectiveProjectId, projectError } = useProjectRouteContext(queryProjectId, projectId)

  // ── Core state ────────────────────────────────────────────────────────────
  const [data, setData] = useState<UniverseGraphData | null>(null)
  const [absences, setAbsences] = useState<AbsenceReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [searchQuery, setSearchQuery] = useState('')
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
  const dialogRef = useRef<HTMLDivElement>(null)
  const inspectorRef = useRef<HTMLElement>(null)

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

  const modalOpen = showAddCharacter || showAddRelationship || showEditModal || showDeleteConfirm
  useEffect(() => {
    if (!modalOpen) return
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const dialog = dialogRef.current
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]') || [])
    const input = dialog?.querySelector<HTMLElement>('input, select, textarea')
    ;(input || focusable()[0])?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowAddCharacter(false)
        setShowAddRelationship(false)
        setShowEditModal(false)
        setShowDeleteConfirm(false)
      }
      if (event.key === 'Tab') {
        const elements = focusable()
        const first = elements[0]
        const last = elements[elements.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => { document.removeEventListener('keydown', onKeyDown); previousFocus?.focus() }
  }, [modalOpen])

  useEffect(() => {
    if (!detailPanelOpen || !selectedNode) return
    inspectorRef.current?.focus({ preventScroll: true })
    if (window.matchMedia('(max-width: 1279px)').matches) {
      inspectorRef.current?.scrollIntoView({ block: 'start', behavior: 'instant' })
    }
  }, [detailPanelOpen, selectedNode])

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

  // Factual counts from the loaded atlas, without inferred story ratings.
  const metrics = useMemo(() => ({
    characters: data?.nodes.filter((node) => node.node_type === 'character').length || 0,
    locations: data?.nodes.filter((node) => node.node_type === 'location').length || 0,
    relationships: data?.relationships.length || 0,
  }), [data])

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
    const query = searchQuery.trim().toLocaleLowerCase()
    if (query) nodes = nodes.filter((node) => `${node.name} ${node.description} ${node.universe_tags.join(' ')}`.toLocaleLowerCase().includes(query))
    return nodes
  }, [data, category, filterMode, searchQuery])


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

  // ── Handlers ──────────────────────────────────────────────────────────────
  const handleNodeClick = useCallback((node: UniverseNode) => {
    setSelectedNode(node)
    setDetailPanelOpen(true)
  }, [])

  const handleNodeHover = useCallback(() => {
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
        universe_tags: selectedNode.node_type !== 'character' || selectedNode.universe_tags.includes(editForm.role)
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
      await triggerDebate({
        project_id: effectiveProjectId,
        query: `Simulate the psychological mind of character "${selectedNode.name}": motivations, internal conflicts, emotional drives, decision-making patterns, and how they would react under pressure. Description: ${selectedNode.description}`,
      })
      setSuccess(`Mind simulation for "${selectedNode.name}" complete`)
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
      <StudioShell title="Universe" subtitle="Galaxy & story atlas">
        <ProjectGuard>
          <div role="status" className="flex items-center justify-center gap-3 py-20 text-sm text-slate-300">
            Loading your story atlas…
            <Loader2 size={32} className="animate-spin" style={{ color: 'var(--color-primary)' }} />
          </div>
        </ProjectGuard>
      </StudioShell>
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <>
      <StudioShell title="Universe" subtitle="Galaxy & story atlas">
      <ProjectGuard>
        <ProjectContextBar roomName="universe" compact />
        <div className="px-3 pb-8 sm:px-5 lg:px-7" data-testid="universe-workspace">
          <header className="flex flex-wrap items-end justify-between gap-5 py-6 sm:py-8">
            <div>
              <p className="mb-2 flex items-center gap-2 text-xs font-medium text-[#c7af82]"><Orbit size={15} /> The world of your film</p>
              <h1 className="text-3xl font-medium tracking-[-0.04em] text-[#f3eee5] sm:text-[38px]">Your story, connected.</h1>
              <p className="mt-2 max-w-xl text-sm leading-6 text-[#aab9c7]">Explore the people, places and ideas that hold your world together.</p>
              <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[#aab9c7]" aria-label="Universe totals">
                <span><strong className="mr-1 font-medium text-[#e7e2d9]">{metrics.characters}</strong> characters</span>
                <span><strong className="mr-1 font-medium text-[#e7e2d9]">{metrics.locations}</strong> locations</span>
                <span><strong className="mr-1 font-medium text-[#e7e2d9]">{metrics.relationships}</strong> connections</span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => setShowAddRelationship(true)} className="flex min-h-10 items-center gap-2 rounded-md border border-white/15 px-3.5 py-2 text-xs font-medium text-[#d2dbe3] hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-amber-200"><Link2 size={14} /> Add relationship</button>
              <button type="button" onClick={() => setShowAddCharacter(true)} className="flex min-h-10 items-center gap-2 rounded-md border border-[#d0b17b]/50 bg-[#dcc18c] px-3.5 py-2 text-xs font-semibold text-[#1c2026] hover:bg-[#ecd4a7] focus-visible:outline-2 focus-visible:outline-amber-200"><Plus size={15} /> Add character</button>
            </div>
          </header>

          {error && <div role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"><span>{error || projectError}</span><button type="button" onClick={() => void loadData()} className="rounded border border-rose-300/30 px-3 py-1.5 hover:bg-white/5">Try again</button></div>}
          {success && <div role="status" className="mb-4 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">{success}</div>}

          <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_320px] 2xl:grid-cols-[minmax(0,1fr)_350px]">
            <section aria-label="Universe constellation" className="min-w-0 overflow-hidden rounded-xl border border-[#7891a5]/20 bg-[#080f18]">
              <div className="relative h-[460px] sm:h-[590px] xl:h-[660px]">
                <UniverseGraph3D nodes={filteredNodes} layoutNodes={data?.nodes} relationships={data?.relationships || []}
                  selectedNodeId={detailPanelOpen ? selectedNode?.node_id || null : null}
                  onNodeClick={handleNodeClick} onNodeHover={handleNodeHover} />
                {loading && <div role="status" className="absolute left-4 top-20 z-30 flex items-center gap-2 rounded bg-[#0b1724]/95 px-3 py-2 text-xs text-[#d8e1e8]"><Loader2 size={14} className="animate-spin" /> Refreshing universe…</div>}
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 px-4 py-3">
                <div className="flex flex-wrap gap-x-4 gap-y-2">
                  {NODE_TYPE_LEGEND.map(({ key, label, style }) => <span key={key} className="flex items-center gap-1.5 text-[11px] text-[#b6c3ce]"><span className="h-1.5 w-1.5 rounded-full" style={{ background: style.fill }} />{label}</span>)}
                </div>
                <span className="text-[11px] text-[#8499ab]">Connections from your project</span>
              </div>
            </section>

            <aside className="min-w-0 space-y-4">
              {detailPanelOpen && selectedNode && <section ref={inspectorRef} tabIndex={-1} data-testid="universe-inspector" aria-labelledby="universe-detail-title" className="scroll-mt-24 overflow-hidden rounded-xl border border-[#c9ad79]/30 bg-[#111b27] focus:outline-none">
                <div className="relative border-b border-white/10 p-5">
                  <button type="button" aria-label="Close details" onClick={() => setDetailPanelOpen(false)} className="absolute right-3 top-3 rounded p-2 text-[#a5b7c8] hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-amber-200"><X size={15} /></button>
                  <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg border border-white/15 bg-[#192a3a] text-[#dfc494]">{selectedNode.node_type === 'character' ? <UserRound size={23} /> : selectedNode.node_type === 'location' ? <MapPin size={23} /> : selectedNode.node_type === 'object' ? <Box size={23} /> : <BookOpen size={23} />}</div>
                  <p className="mb-1.5 text-xs capitalize text-[#c7af82]">{selectedNode.node_type} · Atlas entry</p>
                  <h2 id="universe-detail-title" className="break-words pr-1 text-2xl font-medium leading-tight tracking-tight text-[#f0e8db]">{selectedNode.name}</h2>
                  {selectedNode.universe_tags.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{selectedNode.universe_tags.map((tag) => <span key={tag} className="max-w-full break-words rounded border border-white/10 bg-white/[0.04] px-2 py-1 text-[11px] text-[#b9c8d5]">{ROLE_LABELS[tag as CharacterRole] || tag}</span>)}</div>}
                </div>
                <div className="space-y-5 p-5">
                  <p className="whitespace-pre-wrap break-words text-sm leading-6 text-[#bfccd8]">{selectedNode.description || 'No description yet. Add the details that define this part of your world.'}</p>
                  {(selectedNode.first_scene || selectedNode.last_scene) && <dl className="grid grid-cols-2 gap-3 border-y border-white/10 py-3 text-xs">
                    {selectedNode.first_scene && <div><dt className="text-[#90a4b6]">First appearance</dt><dd className="mt-1 break-words text-[#dce4e9]">{selectedNode.first_scene}</dd></div>}
                    {selectedNode.last_scene && <div><dt className="text-[#90a4b6]">Last appearance</dt><dd className="mt-1 break-words text-[#dce4e9]">{selectedNode.last_scene}</dd></div>}
                  </dl>}
                  <div><h3 className="mb-2 flex items-center gap-2 text-xs font-medium text-[#d8e1e9]"><Link2 size={13} /> Connections <span className="text-[#829bad]">{selectedNodeRelationships.length}</span></h3>
                    {selectedNodeRelationships.length ? <div className="space-y-1">{selectedNodeRelationships.map((relationship) => <button type="button" key={relationship.relationshipId}
                      onClick={() => { const node = data?.nodes.find((entry) => entry.node_id === relationship.characterId); if (node) { setCategory('all'); setFilterMode('all'); setSearchQuery(''); handleNodeClick(node) } }}
                      className="flex w-full items-start justify-between gap-3 rounded px-2 py-2 text-left hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-amber-200">
                      <span className="min-w-0 break-words text-xs leading-5 text-[#d5e0e9]">{relationship.characterName}</span><span className="max-w-[45%] shrink-0 break-words pt-0.5 text-[10px] text-[#c7b189]">{relationship.type.replaceAll('_', ' ')}</span>
                    </button>)}</div> : <p className="text-xs leading-5 text-[#92a7b9]">No connections recorded yet.</p>}
                  </div>
                  <button type="button" onClick={openEditModal} className="flex min-h-10 w-full items-center justify-center gap-2 rounded-md border border-white/15 bg-white/[0.03] px-3 py-2 text-xs font-medium text-[#d6e0e8] hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-amber-200"><Edit3 size={13} /> Edit details</button>
                  <details className="border-t border-white/10 pt-3 text-xs text-[#a4b8c9]"><summary className="cursor-pointer py-1 focus-visible:outline-2 focus-visible:outline-amber-200">More entry actions</summary>
                    <div className="space-y-2 pt-3">
                      {selectedNode.node_type === 'character' && <button type="button" onClick={handleSimulateMind} disabled={simulating} className="flex min-h-10 w-full items-center justify-center gap-2 rounded border border-[#8da9be]/25 px-3 py-2 text-xs text-[#b8cedf] hover:bg-white/5 disabled:opacity-50">{simulating ? <Loader2 size={13} className="animate-spin" /> : <Brain size={13} />} Simulate mind</button>}
                      <button type="button" onClick={() => setShowDeleteConfirm(true)} className="flex min-h-10 w-full items-center justify-center gap-2 rounded px-3 py-2 text-xs text-rose-300 hover:bg-rose-400/10"><Trash2 size={13} /> Delete entry</button>
                    </div>
                  </details>
                </div>
              </section>}

              <section data-testid="universe-atlas" aria-labelledby="universe-atlas-title" className="overflow-hidden rounded-xl border border-[#7891a5]/20 bg-[#0c1520]">
                <div className="space-y-4 border-b border-white/10 p-4 sm:p-5">
                  <div className="flex items-center justify-between"><h2 id="universe-atlas-title" className="flex items-center gap-2 text-base font-medium tracking-tight text-[#e8e5de]"><BookOpen size={16} className="text-[#cdb586]" /> Story atlas</h2><span className="font-mono text-[11px] text-[#92a8ba]">{data?.nodes.length || 0} entries</span></div>
                  <div className="relative"><Search size={15} className="pointer-events-none absolute left-3 top-3 text-[#8ba1b4]" /><input data-testid="universe-search" type="search" aria-label="Search story atlas" placeholder="Find a person, place or idea" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} className="min-h-10 w-full rounded-md border border-[#6d899f]/25 bg-[#060e18] py-2 pl-9 pr-3 text-xs text-[#e1e8ee] placeholder:text-[#8ca1b3] focus:border-[#d5b981] focus:outline-none" /></div>
                  <div role="group" aria-label="Entity types" className="flex flex-wrap gap-1">
                    {([{ value: 'all', label: 'All' }, { value: 'character', label: 'Characters' }, { value: 'location', label: 'Locations' }, { value: 'object', label: 'Objects' }, { value: 'lore', label: 'Lore' }] as const).map(({ value, label }) => <button type="button" key={value} aria-pressed={category === value} onClick={() => setCategory(value)} className={`rounded px-2.5 py-1.5 text-[11px] transition-colors focus-visible:outline-2 focus-visible:outline-amber-200 ${category === value ? 'bg-[#d5bd8d]/15 text-[#e1cba4]' : 'text-[#a9bac9] hover:bg-white/5'}`}>{label}</button>)}
                  </div>
                  <div className="flex items-center gap-3"><label htmlFor="universe-role-filter" className="shrink-0 text-[11px] text-[#90a6b8]">Character role</label><select id="universe-role-filter" aria-label="Character role filter" value={filterMode} onChange={(event) => setFilterMode(event.target.value as FilterMode)} className="min-w-0 flex-1 rounded border border-white/10 bg-[#101c29] px-2 py-1.5 text-[11px] text-[#c5d3de] focus:outline-2 focus:outline-amber-200"><option value="all">All roles</option><option value="protagonists">Protagonists</option><option value="antagonists">Antagonists</option></select></div>
                </div>
                <p className="px-5 pt-3 text-[11px] text-[#90a6b8]" aria-live="polite">{filteredNodes.length} {filteredNodes.length === 1 ? 'entry' : 'entries'} in this view</p>
                <div className={`${detailPanelOpen ? 'max-h-[330px]' : 'max-h-[460px]'} overflow-y-auto p-2`}>
                  {filteredNodes.map((node) => { const selected = detailPanelOpen && selectedNode?.node_id === node.node_id; const style = getNodeTypeStyle(node.node_type); return <button type="button" key={node.node_id} data-testid={`universe-node-${node.node_id}`} aria-pressed={selected} onClick={() => handleNodeClick(node)} className={`group flex w-full items-start gap-3 rounded-lg border px-3 py-3 text-left focus-visible:outline-2 focus-visible:outline-amber-200 ${selected ? 'border-[#cab181]/35 bg-[#cab181]/10' : 'border-transparent hover:bg-[#1a2a3b]/60'}`}>
                    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded border border-white/10 bg-[#172534]" style={{ color: style.fill }}>{node.node_type === 'character' ? <UserRound size={15} /> : node.node_type === 'location' ? <MapPin size={15} /> : node.node_type === 'object' ? <Box size={15} /> : <BookOpen size={15} />}</span>
                    <span className="min-w-0 flex-1"><span className={`block break-words text-xs font-medium leading-5 ${selected ? 'text-[#ead7b4]' : 'text-[#d4dfe8]'}`}>{node.name}</span><span className="mt-0.5 block text-[10px] capitalize text-[#8fa7ba]">{node.node_type}{node.universe_tags.find((tag) => ['protagonist', 'antagonist'].includes(tag)) ? ` · ${node.universe_tags.find((tag) => ['protagonist', 'antagonist'].includes(tag))}` : ''}</span></span><ChevronRight size={13} className="mt-2 shrink-0 text-[#6d8598]" />
                  </button> })}
                  {filteredNodes.length === 0 && <div className="px-3 py-8 text-center text-sm leading-6 text-[#a8bbc9]">{data?.nodes.length ? <>No matching entries.<button type="button" onClick={() => { setCategory('all'); setFilterMode('all'); setSearchQuery('') }} className="mx-auto mt-3 block rounded border border-[#ba9f71]/40 px-3 py-1.5 text-xs text-[#ddc89f] hover:bg-white/5">Clear filters</button></> : <>Your world starts with a character.<br /><span className="text-xs text-[#899fb1]">Add one above, or populate from your scenes in Universe tools.</span></>}</div>}
                </div>
              </section>
            </aside>
          </div>

          <div className="mt-5 grid items-start gap-4 lg:grid-cols-2">
            <details className="rounded-lg border border-[#7891a5]/15 bg-[#0c1520]/70 px-4 py-3 text-xs text-[#b4c5d3]">
              <summary className="cursor-pointer py-1 font-medium text-[#c8d4df] focus-visible:outline-2 focus-visible:outline-amber-200">Universe tools</summary>
              <p className="mt-3 text-xs leading-5 text-[#91a9bb]">Refresh your atlas, bring in details from your scenes, or export your world bible.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" onClick={() => void loadData()} disabled={loading} className="flex min-h-10 items-center gap-2 rounded border border-white/15 px-3 py-2 hover:bg-white/5 disabled:opacity-50"><RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh atlas</button>
                <button type="button" onClick={handleAutoPopulate} disabled={loading} className="flex min-h-10 items-center gap-2 rounded border border-white/15 px-3 py-2 hover:bg-white/5 disabled:opacity-50"><Plus size={13} /> Auto-populate from scenes</button>
                <button type="button" onClick={handleExportGraph} disabled={isExporting} className="flex min-h-10 items-center gap-2 rounded border border-white/15 px-3 py-2 hover:bg-white/5 disabled:opacity-50">{isExporting ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Export world bible</button>
              </div>
            </details>
            {absences && absences.absences.length > 0 && <details className="rounded-lg border border-[#c1a477]/25 bg-[#b39562]/[0.04] px-4 py-3 text-xs text-[#b4c5d3]">
              <summary className="cursor-pointer py-1 font-medium text-[#d6c29d] focus-visible:outline-2 focus-visible:outline-amber-200">Continuity notes · {absences.absences.length} {absences.absences.length === 1 ? 'absence' : 'absences'}</summary>
              <div className="mt-3 space-y-4">{absences.absences.map((absence) => <div key={absence.node_id}><p className="font-medium text-[#d6dfe7]">{absence.name}</p><p className="mt-1 text-xs leading-5 text-[#a0b4c4]">{absence.advisory}</p>{absence.last_seen_scene && <p className="mt-1 text-[11px] text-[#829aab]">Last seen: {absence.last_seen_scene}</p>}</div>)}</div>
            </details>}
          </div>
        </div>

        {/* ── ADD CHARACTER MODAL ──────────────────────────────────────── */}
        {showAddCharacter && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4" onClick={(event) => { if (event.target === event.currentTarget) setShowAddCharacter(false) }}>
            <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Add character" className="glass-panel max-h-[85vh] w-full max-w-[440px] overflow-y-auto rounded-xl p-6">
              {error && <div role="alert" className="mb-4 rounded border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm leading-5 text-rose-200">{error || projectError}</div>}
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-lg font-bold" style={{ color: 'var(--color-on-surface)' }}>
                  Add Character
                </h3>
                <button type="button" aria-label="Close add character" onClick={() => setShowAddCharacter(false)} className="rounded p-1 hover:bg-white/10">
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
                    aria-label="New character name"
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
                    aria-label="New character role"
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
                    aria-label="New character description"
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
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4" onClick={(event) => { if (event.target === event.currentTarget) setShowAddRelationship(false) }}>
            <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Add relationship" className="glass-panel max-h-[85vh] w-full max-w-[440px] overflow-y-auto rounded-xl p-6">
              {error && <div role="alert" className="mb-4 rounded border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm leading-5 text-rose-200">{error || projectError}</div>}
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-lg font-bold" style={{ color: 'var(--color-on-surface)' }}>
                  Add Relationship
                </h3>
                <button type="button" aria-label="Close add relationship" onClick={() => setShowAddRelationship(false)} className="rounded p-1 hover:bg-white/10">
                  <X size={18} style={{ color: 'var(--color-on-surface-variant)' }} />
                </button>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    FROM CHARACTER
                  </label>
                  <select
                    aria-label="Relationship from character"
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
                    aria-label="Relationship type"
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
                    aria-label="Relationship to character"
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
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4" onClick={(event) => { if (event.target === event.currentTarget) setShowEditModal(false) }}>
            <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Edit entry" className="glass-panel max-h-[85vh] w-full max-w-[440px] overflow-y-auto rounded-xl p-6">
              {error && <div role="alert" className="mb-4 rounded border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm leading-5 text-rose-200">{error || projectError}</div>}
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-lg font-bold" style={{ color: 'var(--color-on-surface)' }}>
                  Edit {selectedNode?.node_type || 'entry'}
                </h3>
                <button type="button" aria-label="Close edit entry" onClick={() => setShowEditModal(false)} className="rounded p-1 hover:bg-white/10">
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
                    aria-label="Edit entry name"
                    value={editForm.name}
                    onChange={(e) => setEditForm((p) => ({ ...p, name: e.target.value }))}
                    className="cyber-input w-full rounded px-3 py-2 text-sm outline-none"
                    style={{ color: 'var(--color-on-surface)' }}
                  />
                </div>
                {selectedNode?.node_type === 'character' && (
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    ROLE
                  </label>
                  <select
                    aria-label="Edit entry role"
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
                )}
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    DESCRIPTION
                  </label>
                  <textarea
                    aria-label="Edit entry description"
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
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4" onClick={(event) => { if (event.target === event.currentTarget) setShowDeleteConfirm(false) }}>
            <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Delete entry" className="glass-panel max-h-[85vh] w-full max-w-[400px] overflow-y-auto rounded-xl p-6">
              {error && <div role="alert" className="mb-4 rounded border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm leading-5 text-rose-200">{error || projectError}</div>}
              <div className="mb-2 flex items-center gap-2">
                <AlertCircle size={20} style={{ color: 'var(--color-error)' }} />
                <h3 className="text-lg font-bold" style={{ color: 'var(--color-on-surface)' }}>
                  Delete {selectedNode.node_type}
                </h3>
              </div>
              <p className="mb-4 text-sm" style={{ color: 'var(--color-on-surface-variant)' }}>
                Are you sure you want to delete "{selectedNode.name}"? This will also remove all relationships involving this entry. This cannot be undone.
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
