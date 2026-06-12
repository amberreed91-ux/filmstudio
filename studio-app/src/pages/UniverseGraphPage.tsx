import React, { useState, useEffect, useMemo, useRef } from 'react';
import { ForceGraph2D } from 'react-force-graph-2d';
import { 
  Users, MapPin, Box, ScrollText, Share2, Plus, Search, 
  Download, RefreshCw, AlertCircle, X, Info
} from 'lucide-react';
import { 
  getUniverseGraph, saveUniverseNode, deleteUniverseNode, 
  saveUniverseRelationship, deleteUniverseRelationship, 
  getUniverseAbsences, exportUniverseBible, forceAutoPopulateUniverse 
} from '../lib/studioApi';
import { 
  UniverseNode, UniverseRelationship, UniverseGraphData, 
  UniverseNodeType, AbsenceReport 
} from '../types/universe';

const UniverseGraphPage: React.FC = () => {
  const projectId = "proj-001"; // In a real app, this would come from context or URL
  const [data, setData] = useState<UniverseGraphData | null>(null);
  const [absences, setAbsences] = useState<AbsenceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'graph' | 'characters' | 'locations' | 'objects' | 'lore' | 'relationships'>('graph');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNode, setSelectedNode] = useState<UniverseNode | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const fgRef = useRef<any>();

  const loadData = async () => {
    setLoading(true);
    try {
      const [graphRes, absenceRes] = await Promise.all([
        getUniverseGraph(projectId),
        getUniverseAbsences(projectId)
      ]);
      setData(graphRes);
      setAbsences(absenceRes);
    } catch (err) {
      console.error("Failed to load universe data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [projectId]);

  const filteredNodes = useMemo(() => {
    if (!data) return [];
    return data.nodes.filter(n => 
      n.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      n.description.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [data, searchQuery]);

  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    return {
      nodes: data.nodes.map(n => ({
        id: n.node_id,
        name: n.name,
        type: n.node_type,
        val: n.node_type === 'character' ? 10 : 7
      })),
      links: data.relationships.map(r => ({
        source: r.from_node,
        target: r.to_node,
        type: r.relationship_type
      }))
    };
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

  const handleAutoPopulate = async () => {
    if (!window.confirm("This will auto-populate missing nodes from existing script intelligence. Continue?")) return;
    setLoading(true);
    try {
      await forceAutoPopulateUniverse(projectId);
      await loadData();
    } catch (err) {
      console.error("Auto-populate failed", err);
    } finally {
      setLoading(false);
    }
  };

  const nodeColor = (node: any) => {
    switch (node.type) {
      case 'character': return '#f59e0b'; // Amber
      case 'location': return '#10b981'; // Emerald
      case 'object': return '#3b82f6'; // Blue
      case 'lore': return '#8b5cf6'; // Violet
      default: return '#94a3b8';
    }
  };

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCw className="animate-spin text-zinc-500" size={32} />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-zinc-950 text-zinc-100 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-500/10 rounded-lg text-indigo-400">
            <Share2 size={20} />
          </div>
          <div>
            <h1 className="text-lg font-semibold leading-none">Universe Knowledge Graph</h1>
            <p className="text-xs text-zinc-500 mt-1">Interconnected continuity intelligence engine</p>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 text-zinc-500" size={14} />
            <input 
              type="text"
              placeholder="Search universe..."
              className="bg-zinc-800 border-none rounded-md pl-9 pr-4 py-2 text-sm w-64 focus:ring-1 focus:ring-indigo-500"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <button 
            onClick={handleAutoPopulate}
            className="flex items-center gap-2 px-3 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm font-medium transition-colors"
          >
            <RefreshCw size={14} />
            Auto-Sync
          </button>
          <button 
            onClick={handleExport}
            disabled={isExporting}
            className="flex items-center gap-2 px-3 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-md text-sm font-medium transition-colors"
          >
            <Download size={14} />
            Export Bible
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-zinc-800 px-4 bg-zinc-900/30">
        {[
          { id: 'graph', label: 'Network View', icon: Share2 },
          { id: 'characters', label: 'Characters', icon: Users },
          { id: 'locations', label: 'Locations', icon: MapPin },
          { id: 'objects', label: 'Objects', icon: Box },
          { id: 'lore', label: 'Lore', icon: ScrollText },
          { id: 'relationships', label: 'Relationships', icon: Share2 },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all ${
              activeTab === tab.id 
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5' 
                : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <tab.icon size={14} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden relative">
        {activeTab === 'graph' ? (
          <div className="w-full h-full bg-zinc-950">
            <ForceGraph2D
              ref={fgRef}
              graphData={graphData}
              nodeLabel="name"
              nodeColor={nodeColor}
              linkColor={() => '#333'}
              linkDirectionalParticles={1}
              linkDirectionalParticleSpeed={0.01}
              onNodeClick={(node: any) => setSelectedNode(data?.nodes.find(n => n.node_id === node.id) || null)}
              backgroundColor="#09090b"
            />
            
            {/* Absence Alerts Overlay */}
            {absences && absences.absences.length > 0 && (
              <div className="absolute top-4 right-4 max-w-xs space-y-2 pointer-events-none">
                {absences.absences.map((abs, i) => (
                  <div key={i} className="p-3 bg-amber-900/40 border border-amber-500/30 rounded-md backdrop-blur-md pointer-events-auto">
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

            {/* Selected Node Details */}
            {selectedNode && (
              <div className="absolute bottom-4 left-4 right-4 md:right-auto md:w-96 bg-zinc-900 border border-zinc-800 rounded-lg shadow-2xl p-4 overflow-y-auto max-h-[80%]">
                <div className="flex justify-between items-start mb-4">
                  <div className="flex items-center gap-2">
                    <div className={`w-3 h-3 rounded-full`} style={{ backgroundColor: nodeColor({ type: selectedNode.node_type }) }}></div>
                    <h3 className="text-xl font-bold">{selectedNode.name}</h3>
                  </div>
                  <button onClick={() => setSelectedNode(null)} className="text-zinc-500 hover:text-zinc-300">
                    <X size={18} />
                  </button>
                </div>
                
                <div className="space-y-4">
                  <div>
                    <label className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">Description</label>
                    <p className="text-sm text-zinc-300 leading-relaxed mt-1">{selectedNode.description || 'No description established.'}</p>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">First Seen</label>
                      <p className="text-sm font-medium mt-0.5">{selectedNode.first_scene || 'Unknown'}</p>
                    </div>
                    <div>
                      <label className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">Last Seen</label>
                      <p className="text-sm font-medium mt-0.5">{selectedNode.last_scene || 'Unknown'}</p>
                    </div>
                  </div>

                  {selectedNode.connected_nodes.length > 0 && (
                    <div>
                      <label className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">Connections</label>
                      <div className="flex flex-wrap gap-2 mt-1">
                        {selectedNode.connected_nodes.map(cid => {
                          const cnode = data?.nodes.find(n => n.node_id === cid);
                          return (
                            <button 
                              key={cid}
                              onClick={() => setSelectedNode(cnode || null)}
                              className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 rounded transition-colors"
                            >
                              {cnode?.name || cid}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  <div className="pt-2 flex gap-2">
                    <button className="flex-1 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded text-xs font-medium">Edit Details</button>
                    <button 
                      onClick={async () => {
                        if (window.confirm("Delete this node?")) {
                          await deleteUniverseNode(projectId, selectedNode.node_id);
                          setSelectedNode(null);
                          loadData();
                        }
                      }}
                      className="px-3 py-1.5 bg-red-900/20 hover:bg-red-900/40 text-red-400 rounded text-xs font-medium"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="p-6 overflow-y-auto h-full max-w-6xl mx-auto">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-2xl font-bold capitalize">{activeTab} Inventory</h2>
              <button className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-md text-sm font-medium transition-colors">
                <Plus size={16} />
                Add {activeTab.slice(0, -1)}
              </button>
            </div>

            {activeTab === 'relationships' ? (
              <div className="grid gap-4">
                {data?.relationships.map(rel => (
                  <div key={rel.relationship_id} className="p-4 bg-zinc-900 border border-zinc-800 rounded-lg flex items-center justify-between">
                    <div className="flex items-center gap-6">
                      <div className="text-right">
                        <p className="text-sm font-bold">{data.nodes.find(n => n.node_id === rel.from_node)?.name}</p>
                        <p className="text-[10px] text-zinc-500">{data.nodes.find(n => n.node_id === rel.from_node)?.node_type}</p>
                      </div>
                      <div className="flex flex-col items-center">
                        <div className="h-px w-24 bg-zinc-700 relative">
                          <Share2 size={10} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-zinc-500" />
                        </div>
                        <p className="text-[10px] text-indigo-400 font-bold uppercase mt-1 tracking-tighter">{rel.relationship_type}</p>
                      </div>
                      <div>
                        <p className="text-sm font-bold">{data.nodes.find(n => n.node_id === rel.to_node)?.name}</p>
                        <p className="text-[10px] text-zinc-500">{data.nodes.find(n => n.node_id === rel.to_node)?.node_type}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-zinc-400 max-w-md italic">{rel.description}</p>
                      <button 
                        onClick={async () => {
                          if (window.confirm("Delete relationship?")) {
                            await deleteUniverseRelationship(projectId, rel.relationship_id);
                            loadData();
                          }
                        }}
                        className="text-xs text-red-500 hover:text-red-400 mt-2"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredNodes.filter(n => activeTab === 'graph' || n.node_type === activeTab.slice(0, -1)).map(node => (
                  <div key={node.node_id} className="p-5 bg-zinc-900 border border-zinc-800 rounded-lg hover:border-zinc-700 transition-colors group">
                    <div className="flex justify-between items-start mb-3">
                      <h3 className="font-bold text-lg">{node.name}</h3>
                      <div className={`p-1.5 rounded-md`} style={{ backgroundColor: `${nodeColor({ type: node.node_type })}20`, color: nodeColor({ type: node.node_type }) }}>
                        {node.node_type === 'character' && <Users size={16} />}
                        {node.node_type === 'location' && <MapPin size={16} />}
                        {node.node_type === 'object' && <Box size={16} />}
                        {node.node_type === 'lore' && <ScrollText size={16} />}
                      </div>
                    </div>
                    <p className="text-sm text-zinc-400 line-clamp-3 h-15 mb-4">{node.description || 'No description established.'}</p>
                    <div className="flex items-center justify-between pt-4 border-t border-zinc-800">
                      <span className="text-[10px] text-zinc-500 uppercase tracking-widest">{node.connected_nodes.length} connections</span>
                      <button 
                        onClick={() => {
                          setSelectedNode(node);
                          setActiveTab('graph');
                        }}
                        className="text-xs text-indigo-400 font-bold hover:underline"
                      >
                        View in Graph
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default UniverseGraphPage;
