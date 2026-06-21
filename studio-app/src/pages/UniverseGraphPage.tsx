import React, { useState, useEffect, useMemo, useRef } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import {
  Users, MapPin, Box, ScrollText, Share2, Plus,
  Download, RefreshCw, AlertCircle, X, Info
} from 'lucide-react';
import {
   getUniverseGraph, saveUniverseNode, deleteUniverseNode,
   saveUniverseRelationship, deleteUniverseRelationship,
   getUniverseAbsences, exportUniverseBible, forceAutoPopulateUniverse
 } from '../lib/studioApi';
import type {
  UniverseNode, UniverseRelationship, UniverseGraphData,
  UniverseNodeType, AbsenceReport
} from '../types/universe';

type CategoryFilter = 'all' | 'character' | 'location' | 'object' | 'lore' | 'relationships';

const CATEGORY_COLORS: Record<CategoryFilter, string> = {
  all: '#ffffff',
  character: '#00d4aa',
  location: '#4488ff',
  object: '#ff8844',
  lore: '#888888',
  relationships: '#888888',
};

const UniverseGraphPage: React.FC = () => {
  const projectId = "proj-001";
  const [data, setData] = useState<UniverseGraphData | null>(null);
  const [absences, setAbsences] = useState<AbsenceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [selectedNode, setSelectedNode] = useState<UniverseNode | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const fgRef = useRef<any>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [graphRes, absenceRes] = await Promise.all([
        getUniverseGraph(projectId),
        getUniverseAbsences(projectId)
      ]);
      setData(graphRes);
      setAbsences(absenceRes);

      const uniqueTypes = [...new Set(graphRes.nodes.map(n => n.node_type))];
      console.log('[UniverseGraph] Unique node types in data:', uniqueTypes);
      console.log('[UniverseGraph] Node counts by type:', Object.fromEntries(
        uniqueTypes.map(t => [t, graphRes.nodes.filter(n => n.node_type === t).length])
      ));
      console.log('[UniverseGraph] Relationship count:', graphRes.relationships.length);

      // Auto-select first character if no node selected yet
      if (!selectedNode && graphRes.nodes.length > 0) {
        const firstChar = graphRes.nodes.find(n => n.node_type === 'character') || graphRes.nodes[0];
        setSelectedNode(firstChar);
      }
    } catch (err) {
      console.error("Failed to load universe data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [projectId]);

  const getNodeColor = (nodeType: string) => {
    switch (nodeType) {
      case 'character': return '#00d4aa';
      case 'location': return '#4488ff';
      case 'object': return '#ff8844';
      case 'lore': return '#888888';
      default: return '#555555';
    }
  };

  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };

    const nodes = data.nodes.map(n => ({
      id: n.node_id,
      name: n.name,
      node_type: n.node_type,
      val: n.node_type === 'character' ? 8 : 5,
      color: getNodeColor(n.node_type),
    }));

    let links = data.relationships.map(r => ({
      source: r.from_node,
      target: r.to_node,
      type: r.relationship_type,
    }));

    if (links.length === 0 && nodes.length > 1) {
      console.log('[UniverseGraph] No relationships found — adding mock edges between all nodes');
      for (let i = 0; i < nodes.length - 1; i++) {
        links.push({ source: nodes[i].id, target: nodes[i + 1].id, type: 'connected_to' });
      }
    }

    return { nodes, links };
  }, [data]);

  const handleExport = async () => {
    setIsExporting(true);
    try {
      const bible = await exportUniverseBible(projectId);
      const blob = new Blob([bible], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `UniverseBible_${projectId}.md`;
      a.click();
    } catch (err) {
      console.error("Export failed", err);
    } finally {
      setIsExporting(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCw className="animate-spin text-zinc-500" size={32} />
      </div>
    );
  }

  const categories: { id: CategoryFilter; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'character', label: 'Characters' },
    { id: 'location', label: 'Locations' },
    { id: 'object', label: 'Objects' },
    { id: 'lore', label: 'Lore' },
    { id: 'relationships', label: 'Relationships' },
  ];

  // Build memory engine advisory for selected node
  const getMemoryEngineNote = (node: UniverseNode) => {
    const connected = node.connected_nodes.map(cid => data?.nodes.find(n => n.node_id === cid)).filter(Boolean) as UniverseNode[];
    const connectedNames = connected.map(c => c.name).join(', ');
    if (!node.last_scene) return null;
    if (connectedNames) {
      return `${connectedNames} last seen ${node.last_scene}. This may strengthen the arc.`;
    }
    return null;
  };

  const getTypeLabel = (nodeType: string) => {
    switch (nodeType) {
      case 'character': return 'Character';
      case 'location': return 'Location';
      case 'object': return 'Object';
      case 'lore': return 'Lore';
      default: return nodeType;
    }
  };

  const getTypeIcon = (nodeType: string) => {
    switch (nodeType) {
      case 'character': return <Users size={14} />;
      case 'location': return <MapPin size={14} />;
      case 'object': return <Box size={14} />;
      case 'lore': return <ScrollText size={14} />;
      default: return null;
    }
  };

  return (
    <>
      <div className="flex flex-col h-full overflow-hidden relative" style={{ background: 'var(--color-surface-0)', position: 'relative', zIndex: 1 }}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-6 py-5 shrink-0"
        style={{ background: 'var(--color-surface-1)', borderBottom: '1px solid var(--color-border)' }}
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg" style={{ background: 'var(--color-surface-2)' }}>
            <Share2 size={20} style={{ color: 'var(--color-accent)' }} />
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-[0.2em] font-bold" style={{ color: 'var(--color-accent)' }}>
              Universe Knowledge Graph
            </div>
            <h1
              className="mt-1 text-3xl font-light"
              style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}
            >
              The Story Bible
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
            style={{ background: 'var(--color-surface-2)', color: 'var(--color-text-secondary)' }}
          >
            <Plus size={14} />
            Add node
          </button>
          <button
            onClick={handleExport}
            disabled={isExporting}
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium border transition-colors disabled:opacity-50"
            style={{ borderColor: 'var(--color-accent)', color: 'var(--color-accent)' }}
          >
            <Download size={14} />
            Export Bible
          </button>
        </div>
      </div>

      {/* Category Filter Bar */}
      <div
        className="flex items-center gap-5 px-6 py-3 shrink-0 border-b"
        style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border)' }}
      >
        {categories.map(cat => (
          <button
            key={cat.id}
            onClick={() => setCategory(cat.id)}
            className="flex items-center gap-2 text-sm font-medium transition-colors pb-0.5"
            style={{
              color: category === cat.id ? CATEGORY_COLORS[cat.id] : 'var(--color-text-muted)',
              borderBottom: category === cat.id ? `2px solid ${CATEGORY_COLORS[cat.id]}` : '2px solid transparent',
            }}
          >
            {cat.id !== 'all' && cat.id !== 'relationships' && (
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: CATEGORY_COLORS[cat.id] }}
              />
            )}
            {cat.label}
          </button>
        ))}
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-hidden flex min-h-0">

        {/* Graph Area */}
        <div
          className="flex-1 relative min-w-0"
          style={{
            background: '#080808',
            backgroundImage: 'radial-gradient(circle, #1a1a1a 1px, transparent 1px)',
            backgroundSize: '28px 28px',
          }}
        >
          <ForceGraph2D
            ref={fgRef}
            graphData={graphData}
            nodeLabel="name"
            nodeRelSize={8}
            linkColor={() => '#2a2a2a'}
            linkWidth={1}
            linkDirectionalParticles={1}
            linkDirectionalParticleSpeed={0.01}
            onNodeClick={(node: any) => {
              const found = data?.nodes.find(n => n.node_id === node.id) || null;
              setSelectedNode(found);
            }}
            backgroundColor="transparent"
            nodeCanvasObjectMode={() => 'after'}
            nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const color = node.color || '#555';
              const nodeSize = Math.sqrt(node.val || 5) * 8;
              const isSelected = selectedNode?.node_id === node.id;

              // Glow ring for selected node
              if (isSelected) {
                ctx.beginPath();
                ctx.arc(node.x, node.y, nodeSize + 6, 0, 2 * Math.PI);
                ctx.strokeStyle = color + '60';
                ctx.lineWidth = 3;
                ctx.stroke();
              }

              // Outer ring
              ctx.beginPath();
              ctx.arc(node.x, node.y, nodeSize, 0, 2 * Math.PI);
              ctx.fillStyle = color + '25';
              ctx.fill();
              ctx.strokeStyle = color;
              ctx.lineWidth = isSelected ? 2.5 : 1.5;
              ctx.stroke();

              // Letter initial
              const letter = (node.name || '?')[0].toUpperCase();
              const fontSize = Math.max(10, (nodeSize * 0.8)) / globalScale;
              ctx.font = `bold ${fontSize}px sans-serif`;
              ctx.fillStyle = color;
              ctx.textAlign = 'center';
              ctx.textBaseline = 'middle';
              ctx.fillText(letter, node.x, node.y);

              // Node name label below
              const labelFontSize = Math.max(9, 10 / globalScale);
              ctx.font = `${labelFontSize}px sans-serif`;
              ctx.fillStyle = color;
              ctx.textAlign = 'center';
              ctx.textBaseline = 'top';
              ctx.fillText(node.name, node.x, node.y + nodeSize + 5);
            }}
          />

          {/* Absence Alerts */}
          {absences && absences.absences.length > 0 && (
            <div className="absolute top-4 right-4 max-w-xs space-y-2 pointer-events-none">
              {absences.absences.map((abs, i) => (
                <div
                  key={i}
                  className="p-3 rounded-md backdrop-blur-md pointer-events-auto"
                  style={{ background: 'rgba(120,53,15,0.4)', border: '1px solid rgba(245,158,11,0.3)' }}
                >
                  <div className="flex items-start gap-2 text-amber-200">
                    <AlertCircle size={16} className="mt-0.5 shrink-0" />
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wider">Absence Detected</p>
                      <p className="text-sm mt-0.5">{abs.name} ({abs.type}) hasn't appeared since {abs.last_seen_scene}.</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Sidebar */}
        <div
          className="w-80 shrink-0 flex flex-col overflow-y-auto"
          style={{ background: 'var(--color-surface-1)', borderLeft: '1px solid var(--color-border)' }}
        >
          {/* Legend */}
          <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--color-border)' }}>
            <div className="text-[10px] uppercase tracking-widest font-bold mb-2" style={{ color: 'var(--color-text-muted)' }}>
              Legend
            </div>
            <div className="flex flex-col gap-1.5">
              {[
                { color: '#00d4aa', label: 'Character' },
                { color: '#4488ff', label: 'Location' },
                { color: '#ff8844', label: 'Object' },
                { color: '#888888', label: 'Lore' },
              ].map(item => (
                <div key={item.label} className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: item.color }} />
                  <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>{item.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Selected Node Detail */}
          {selectedNode ? (
            <div className="flex-1 flex flex-col">
              <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--color-border)' }}>
                <div className="text-[10px] uppercase tracking-widest font-bold" style={{ color: 'var(--color-text-muted)' }}>
                  Selected — {selectedNode.name.toUpperCase()}
                </div>
              </div>

              {/* Node Card */}
              <div className="m-4 p-4 rounded-lg border" style={{ borderColor: getNodeColor(selectedNode.node_type) + '40', background: 'var(--color-surface-0)' }}>
                {/* Card Header */}
                <div className="flex items-center gap-3 mb-4">
                  <div
                    className="w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold shrink-0"
                    style={{
                      backgroundColor: getNodeColor(selectedNode.node_type) + '20',
                      color: getNodeColor(selectedNode.node_type),
                    }}
                  >
                    {getTypeIcon(selectedNode.node_type)}
                  </div>
                  <div>
                    <h3 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
                      {selectedNode.name}
                    </h3>
                    <p className="text-xs uppercase tracking-widest mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                      {getTypeLabel(selectedNode.node_type)}
                    </p>
                  </div>
                  <button
                    onClick={() => setSelectedNode(null)}
                    className="ml-auto text-zinc-500 hover:text-zinc-300 transition-colors"
                  >
                    <X size={16} />
                  </button>
                </div>

                {/* Description */}
                {selectedNode.description && (
                  <p className="text-sm mb-4 leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                    {selectedNode.description}
                  </p>
                )}

                {/* Data Table */}
                <div className="space-y-2 mb-4">
                  <div className="flex justify-between text-sm">
                    <span style={{ color: 'var(--color-text-muted)' }}>First appears</span>
                    <span style={{ color: 'var(--color-text-primary)' }}>{selectedNode.first_scene || 'Unknown'}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span style={{ color: 'var(--color-text-muted)' }}>Last seen</span>
                    <span style={{ color: 'var(--color-text-primary)' }}>{selectedNode.last_scene || 'Unknown'}</span>
                  </div>
                  {selectedNode.connected_nodes.length > 0 && (
                    <div className="pt-1">
                      <div className="text-xs mb-1.5" style={{ color: 'var(--color-text-muted)' }}>Connected to</div>
                      <div className="flex flex-wrap gap-1.5">
                        {selectedNode.connected_nodes.map(cid => {
                          const cnode = data?.nodes.find(n => n.node_id === cid);
                          return (
                            <button
                              key={cid}
                              onClick={() => cnode && setSelectedNode(cnode)}
                              className="text-xs px-2 py-1 rounded transition-colors"
                              style={{ background: 'var(--color-surface-2)', color: 'var(--color-text-secondary)' }}
                            >
                              {cnode?.name || cid}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>

                {/* Memory Engine Panel */}
                {(() => {
                  const note = getMemoryEngineNote(selectedNode);
                  if (!note) return null;
                  return (
                    <div
                      className="rounded-md p-3 text-sm leading-relaxed"
                      style={{
                        borderLeft: '3px solid var(--color-accent)',
                        background: 'var(--color-surface-2)',
                        color: 'var(--color-text-secondary)',
                      }}
                    >
                      <div className="text-[10px] uppercase tracking-widest font-bold mb-1" style={{ color: 'var(--color-accent)' }}>
                        Memory Engine
                      </div>
                      {note}
                    </div>
                  );
                })()}
              </div>

              {/* Action Buttons */}
              <div className="px-4 pb-4 flex gap-2 mt-auto">
                <button
                  className="flex-1 px-3 py-2 rounded text-xs font-medium transition-colors"
                  style={{ background: 'var(--color-surface-2)', color: 'var(--color-text-primary)' }}
                >
                  Edit Details
                </button>
                <button
                  onClick={async () => {
                    if (window.confirm(`Delete "${selectedNode.name}"?`)) {
                      await deleteUniverseNode(projectId, selectedNode.node_id);
                      setSelectedNode(null);
                      loadData();
                    }
                  }}
                  className="px-3 py-2 rounded text-xs font-medium transition-colors"
                  style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171' }}
                >
                  Delete
                </button>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center p-6 text-center gap-3">
              <Info size={24} style={{ color: 'var(--color-text-muted)' }} />
              <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                Click a node to view details
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
    </>
  );
};

export default UniverseGraphPage;
