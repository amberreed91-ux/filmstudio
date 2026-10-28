import React, { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Html, Line } from '@react-three/drei'
import { Compass, Minus, Pause, Play, Plus, RotateCcw } from 'lucide-react'
import * as THREE from 'three'
import type { UniverseNode, UniverseRelationship } from '../types/universe'

interface UniverseGraph3DProps {
  nodes: UniverseNode[]
  layoutNodes?: UniverseNode[]
  relationships: UniverseRelationship[]
  selectedNodeId: string | null
  onNodeClick: (node: UniverseNode) => void
  onNodeHover: (node: UniverseNode | null) => void
}

export interface NodeTypeStyle { fill: string; border: string; glow: string }
// eslint-disable-next-line react-refresh/only-export-components
export const NODE_TYPE_STYLES: Record<string, NodeTypeStyle> = {
  character: { fill: '#b2d3e6', border: '#779eaf', glow: '#6f9caf' },
  location: { fill: '#ddbf87', border: '#af9362', glow: '#b99b69' },
  object: { fill: '#a0c4af', border: '#6b967f', glow: '#86b29a' },
  lore: { fill: '#c2b3d5', border: '#9083a3', glow: '#a399ba' },
}
// eslint-disable-next-line react-refresh/only-export-components
export const DEFAULT_NODE_TYPE_STYLE: NodeTypeStyle = { fill: '#c6c0b6', border: '#938b7e', glow: '#a9a294' }
// eslint-disable-next-line react-refresh/only-export-components
export const NODE_TYPE_LEGEND = [
  { key: 'character', label: 'Characters', style: NODE_TYPE_STYLES.character },
  { key: 'location', label: 'Locations', style: NODE_TYPE_STYLES.location },
  { key: 'object', label: 'Objects', style: NODE_TYPE_STYLES.object },
  { key: 'lore', label: 'Lore', style: NODE_TYPE_STYLES.lore },
]
// eslint-disable-next-line react-refresh/only-export-components
export function getNodeTypeStyle(nodeType: string): NodeTypeStyle {
  return NODE_TYPE_STYLES[nodeType] || DEFAULT_NODE_TYPE_STYLE
}

type Position = [number, number, number]
type MapCommand = { type: 'in' | 'out' | 'reset'; sequence: number }

function seedFromId(id: string) {
  let seed = 2166136261
  for (let index = 0; index < id.length; index += 1) seed = Math.imul(seed ^ id.charCodeAt(index), 16777619)
  return (seed >>> 0) / 4294967295
}

function useMapActivity() {
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [visible, setVisible] = useState(() => !document.hidden)
  const [paused, setPaused] = useState(false)
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const updateMotion = () => setReducedMotion(query.matches)
    const updateVisibility = () => setVisible(!document.hidden)
    query.addEventListener('change', updateMotion)
    document.addEventListener('visibilitychange', updateVisibility)
    return () => {
      query.removeEventListener('change', updateMotion)
      document.removeEventListener('visibilitychange', updateVisibility)
    }
  }, [])
  return { active: visible && !paused && !reducedMotion, paused: paused || reducedMotion, reducedMotion, setPaused }
}

function StarDepth({ active }: { active: boolean }) {
  const group = useRef<THREE.Group>(null)
  const positions = useMemo(() => {
    const points = new Float32Array(180 * 3)
    for (let index = 0; index < 180; index += 1) {
      points[index * 3] = (seedFromId(`x${index}`) - 0.5) * 65
      points[index * 3 + 1] = (seedFromId(`y${index}`) - 0.5) * 42
      points[index * 3 + 2] = -10 - seedFromId(`z${index}`) * 24
    }
    return points
  }, [])
  useFrame((_, delta) => {
    if (active && group.current) group.current.rotation.z += Math.min(delta, 0.05) * 0.002
  })
  return <group ref={group}><points>
    <bufferGeometry><bufferAttribute attach="attributes-position" args={[positions, 3]} /></bufferGeometry>
    <pointsMaterial color="#d2dce6" size={0.032} transparent opacity={0.55} depthWrite={false} sizeAttenuation />
  </points></group>
}

function RelationshipPath({ start, end, highlighted, subdued }: {
  start: Position; end: Position; highlighted: boolean; subdued: boolean
}) {
  const points = useMemo(() => {
    const first = new THREE.Vector3(...start)
    const last = new THREE.Vector3(...end)
    const mid = first.clone().add(last).multiplyScalar(0.5)
    mid.z -= Math.min(first.distanceTo(last) * 0.13, 1.2)
    return new THREE.QuadraticBezierCurve3(first, mid, last).getPoints(24)
  }, [start, end])
  return <Line points={points} color={highlighted ? '#e5c687' : '#8aabbc'} lineWidth={highlighted ? 1.35 : 0.65}
    transparent opacity={highlighted ? 0.9 : subdued ? 0.08 : 0.27} depthWrite={false} />
}

function StoryNode({ node, position, selected, connected, subdued, showLabel, onSelect, onHover }: {
  node: UniverseNode; position: Position; selected: boolean; connected: boolean; subdued: boolean; showLabel: boolean
  onSelect: () => void; onHover: (hovered: boolean) => void
}) {
  const style = getNodeTypeStyle(node.node_type)
  const radius = node.node_type === 'character' ? 0.23 : 0.15
  return <group position={position}>
    <mesh onClick={(event) => { event.stopPropagation(); onSelect() }}
      onPointerOver={(event) => { event.stopPropagation(); onHover(true) }}
      onPointerOut={() => onHover(false)}>
      <sphereGeometry args={[radius, 24, 20]} />
      <meshStandardMaterial color={selected ? '#f2dfb6' : style.fill} metalness={0.42} roughness={0.38}
        emissive={style.fill} emissiveIntensity={selected ? 0.45 : subdued ? 0.025 : 0.12} />
    </mesh>
    {(selected || connected) && <mesh>
      <ringGeometry args={[radius + 0.095, radius + 0.11, 48]} />
      <meshBasicMaterial color={selected ? '#f1d29c' : style.fill} transparent opacity={selected ? 0.85 : 0.5} side={THREE.DoubleSide} depthWrite={false} />
    </mesh>}
    <Html center position={[0, -radius - 0.27, 0]} zIndexRange={[12, 0]} style={{ pointerEvents: 'none' }}>
      <div className={`${showLabel ? 'block' : 'hidden'} ${selected ? '' : 'max-sm:hidden'} w-[112px] text-center`}
        style={{ opacity: subdued ? 0.4 : 1 }}>
        <span className={`inline-block max-w-full rounded px-1.5 py-1 text-xs leading-[1.35] ${selected ? 'bg-[#111923]/95 text-[#f5ddb2]' : 'bg-[#070e16]/80 text-[#dde5ed]'}`}>
          <span className="line-clamp-2 break-words">{node.name}</span>
        </span>
      </div>
    </Html>
    {/* A large invisible hit target supports touch; the atlas provides keyboard equivalents. */}
    <mesh onClick={(event) => { event.stopPropagation(); onSelect() }}
      onPointerOver={(event) => { event.stopPropagation(); onHover(true) }} onPointerOut={() => onHover(false)}>
      <sphereGeometry args={[radius + 0.2, 8, 8]} /><meshBasicMaterial transparent opacity={0} depthWrite={false} />
    </mesh>
  </group>
}

function MapControls({ command }: { command: MapCommand }) {
  const ref = useRef<React.ComponentRef<typeof OrbitControls>>(null)
  const { camera, size, invalidate } = useThree()
  const defaultDistance = Math.max(16.5, 17 / Math.max(size.width / size.height, 0.5))
  useEffect(() => {
    camera.position.set(0, 0, defaultDistance)
    camera.lookAt(0, 0, 0)
    ref.current?.target.set(0, 0, 0)
    ref.current?.update()
    invalidate()
  }, [camera, defaultDistance, invalidate])
  useEffect(() => {
    if (!ref.current) return
    if (command.type === 'reset') {
      camera.position.set(0, 0, defaultDistance)
      ref.current.target.set(0, 0, 0)
    } else {
      const offset = camera.position.clone().sub(ref.current.target)
      offset.setLength(THREE.MathUtils.clamp(offset.length() * (command.type === 'in' ? 0.8 : 1.25), 6, 48))
      camera.position.copy(ref.current.target).add(offset)
    }
    ref.current.update()
    invalidate()
  }, [command, camera, defaultDistance, invalidate])
  return <OrbitControls ref={ref} makeDefault enableDamping dampingFactor={0.1} minDistance={6} maxDistance={48}
    maxPolarAngle={Math.PI * 0.8} minPolarAngle={Math.PI * 0.2} />
}

function GalaxyScene({ nodes, layoutNodes, relationships, selectedNodeId, onNodeClick, onNodeHover, active }: UniverseGraph3DProps & { active: boolean }) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  // Force-directed constellation drift: the whole lore graph breathes as one
  // body so character/location clusters read as a living constellation.
  const drift = useRef<THREE.Group>(null)
  useFrame(({ clock }, delta) => {
    if (!active || !drift.current) return
    const t = clock.getElapsedTime()
    drift.current.rotation.z = Math.sin(t * 0.05) * 0.03
    drift.current.rotation.y = Math.sin(t * 0.07) * 0.02
    drift.current.position.y = Math.sin(t * 0.3) * 0.05
    void delta
  })
  const positions = useMemo(() => {
    const result = new Map<string, Position>()
    const ordered = [...(layoutNodes || nodes)].sort((a, b) => a.node_id.localeCompare(b.node_id))
    ordered.forEach((node, index) => {
      const angle = index * 2.399963
      const radius = Math.sqrt((index + 0.65) / Math.max(ordered.length, 1))
      result.set(node.node_id, [Math.cos(angle) * radius * 6.1, Math.sin(angle) * radius * 4.1, (seedFromId(node.node_id) - 0.5) * 1.5])
    })
    return result
  }, [layoutNodes, nodes])
  const focusId = hoveredId || selectedNodeId
  const connectedIds = useMemo(() => {
    const connected = new Set<string>()
    if (focusId) relationships.forEach((relationship) => {
      if (relationship.from_node === focusId) connected.add(relationship.to_node)
      if (relationship.to_node === focusId) connected.add(relationship.from_node)
    })
    return connected
  }, [focusId, relationships])
  const visibleIds = useMemo(() => new Set(nodes.map((node) => node.node_id)), [nodes])
  return <>
    <ambientLight intensity={0.65} />
    <directionalLight position={[-4, 6, 8]} intensity={2.4} color="#dfedff" />
    <directionalLight position={[6, -4, 2]} intensity={0.9} color="#d9ad75" />
    <StarDepth active={active} />
    <group ref={drift} data-testid="universe-constellation-drift">
    {relationships.map((relationship) => {
      const start = positions.get(relationship.from_node)
      const end = positions.get(relationship.to_node)
      if (!start || !end || !visibleIds.has(relationship.from_node) || !visibleIds.has(relationship.to_node)) return null
      const highlighted = relationship.from_node === focusId || relationship.to_node === focusId
      return <RelationshipPath key={relationship.relationship_id} start={start} end={end} highlighted={highlighted} subdued={Boolean(focusId) && !highlighted} />
    })}
    {nodes.map((node) => <StoryNode key={node.node_id} node={node} position={positions.get(node.node_id) || [0, 0, 0] as [number, number, number]}
      selected={node.node_id === selectedNodeId} connected={connectedIds.has(node.node_id)}
      subdued={Boolean(focusId) && focusId !== node.node_id && !connectedIds.has(node.node_id)}
      showLabel={!focusId || focusId === node.node_id || connectedIds.has(node.node_id)}
      onSelect={() => onNodeClick(node)} onHover={(hovered) => { setHoveredId(hovered ? node.node_id : null); onNodeHover(hovered ? node : null) }} />)}
    </group>
  </> 
}

function supportsWebGL() {
  try {
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('webgl2')
    if (!context) return false
    context.getExtension('WEBGL_lose_context')?.loseContext()
    return true
  } catch { return false }
}

const UniverseGraph3D: React.FC<UniverseGraph3DProps> = (props) => {
  const [webglAvailable, setWebglAvailable] = useState(supportsWebGL)
  const { active, paused, reducedMotion, setPaused } = useMapActivity()
  const [command, setCommand] = useState<MapCommand>({ type: 'reset', sequence: 0 })
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const contextLost = (event: Event) => { event.preventDefault(); setWebglAvailable(false) }
    canvas.addEventListener('webglcontextlost', contextLost)
    return () => canvas.removeEventListener('webglcontextlost', contextLost)
  }, [webglAvailable])
  const changeView = (type: MapCommand['type']) => setCommand((current) => ({ type, sequence: current.sequence + 1 }))
  return <div data-testid="universe-map" className="relative isolate h-full min-h-[420px] overflow-hidden bg-[#050a11]">
    <img src="/backgrounds/assets/universe-galaxy-atlas.jpg" alt="" aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full object-cover opacity-80" />
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_10%,rgba(3,8,15,0.52)_100%)]" />
    {webglAvailable ? <Canvas ref={canvasRef} camera={{ position: [0, 0, 17], fov: 45 }} dpr={[1, 1.5]}
      frameloop={active ? 'always' : 'demand'} gl={{ antialias: true, alpha: true }} style={{ width: '100%', height: '100%' }}
      fallback={<MapFallback />}>
      <Suspense fallback={null}><MapControls command={command} /><GalaxyScene {...props} active={active} /></Suspense>
    </Canvas> : <MapFallback />}
    <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-start justify-between gap-4 bg-gradient-to-b from-[#060c14]/80 to-transparent p-4 sm:p-5">
      <div><div className="flex items-center gap-2 text-xs font-medium text-[#e5d3af]"><Compass size={14} /> Constellation view</div>
        <p className="mt-1 max-w-[230px] text-xs leading-5 text-[#b4c3d1]">Every point belongs to your story.</p></div>
      <span className="mt-1 font-mono text-[10px] text-[#adc0ce]">{props.nodes.length} entries</span>
    </div>
    {props.nodes.length === 0 && webglAvailable && <div className="pointer-events-none absolute inset-0 z-10 grid place-items-center p-8 text-center">
      <p className="max-w-xs rounded-lg bg-[#070e17]/90 px-5 py-4 text-sm leading-6 text-[#d7e0e8]">No entries in this view. Change the atlas filters or add your first character.</p>
    </div>}
    <div className="absolute inset-x-0 bottom-0 z-20 flex flex-wrap items-end justify-between gap-3 bg-gradient-to-t from-[#060c14] to-transparent p-4 sm:p-5">
      <p className="basis-full text-xs leading-5 text-[#b4c3d1] sm:max-w-[180px] sm:basis-auto">Drag to orbit · Scroll to zoom<br /><span className="text-[#879dac]">Select a point or an atlas entry</span></p>
      <div className="flex gap-1 rounded-lg border border-white/15 bg-[#101a25]/95 p-1">
        {([{ type: 'in', label: 'Zoom in', icon: Plus }, { type: 'out', label: 'Zoom out', icon: Minus }, { type: 'reset', label: 'Reset map view', icon: RotateCcw }] as const).map(({ type, label, icon: Icon }) => <button key={type} type="button" aria-label={label} title={label} onClick={() => changeView(type)} disabled={!webglAvailable} className="rounded p-2 text-[#d8e3eb] hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-amber-200 disabled:opacity-35"><Icon size={16} /></button>)}
        <span className="my-1 w-px bg-white/10" />
        <button type="button" aria-label={paused ? 'Resume map motion' : 'Pause map motion'} aria-pressed={paused} disabled={!webglAvailable || reducedMotion}
          title={reducedMotion ? 'Motion paused by your reduced-motion preference' : paused ? 'Resume map motion' : 'Pause map motion'}
          onClick={() => setPaused(!paused)} className="rounded p-2 text-[#d8e3eb] hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-amber-200 disabled:opacity-35">{paused ? <Play size={16} /> : <Pause size={16} />}</button>
      </div>
    </div>
  </div>
}

function MapFallback() {
  return <div data-testid="universe-map-fallback" role="status" className="absolute inset-0 grid place-items-center p-8 text-center">
    <div className="max-w-xs rounded-lg border border-white/15 bg-[#09121d]/95 p-6 text-sm leading-6 text-[#d2deea]">
      <Compass className="mx-auto mb-3 text-[#d7bd8b]" size={28} />
      The 3D view isn’t available on this device. Explore every entry and connection in the story atlas.
    </div>
  </div>
}

export default UniverseGraph3D
