export type UniverseNodeType = 'character' | 'location' | 'object' | 'lore';

export interface UniverseNode {
  node_id: string;
  project_id: string;
  node_type: UniverseNodeType;
  name: string;
  description: string;
  first_scene?: string;
  last_scene?: string;
  universe_tags: string[];
  created_at?: string;
  updated_at?: string;
  connected_nodes: string[];
}

export interface UniverseRelationship {
  relationship_id: string;
  project_id: string;
  from_node: string;
  to_node: string;
  relationship_type: string;
  description: string;
  created_at?: string;
}

export interface UniverseGraphData {
  project_id: string;
  nodes: UniverseNode[];
  relationships: UniverseRelationship[];
}

export interface Absence {
  node_id: string;
  name: string;
  type: string;
  last_seen_scene: string;
  advisory: string;
}

export interface AbsenceReport {
  project_id: string;
  absences: Absence[];
}
