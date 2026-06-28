import React, { useMemo, useRef, useState } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Html } from '@react-three/drei'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import { BlendFunction, KernelSize } from 'postprocessing'
import * as THREE from 'three'
import type { UniverseNode, UniverseRelationship } from '../types/universe'

interface UniverseGraph3DProps {
  nodes: UniverseNode[]
  relationships: UniverseRelationship[]
  selectedNodeId: string | null
  onNodeClick: (node: UniverseNode) => void
  onNodeHover: (node: UniverseNode | null) => void
}

const RELATIONSHIP_COLORS: Record<string, string> = {
  ally: '#4cd7f6',
  rival: '#ffb4ab',
  love: '#ffd165',
  family: '#d3c5ac',
  mentor: '#4cd7f6',
  default: 'rgba(255,255,255,0.15)',
}

const CATEGORY_COLORS: Record<string, string> = {
  character: '#00d4aa',
  location: '#4488ff',
  object: '#ff8844',
  lore: '#888888',
}

// Node-type visual style: fill, border (alpha), and glow color.
// These drive the colored circle + tinted halo + outline border per type.
export interface NodeTypeStyle {
  fill: string
  border: string
  glow: string
}

export const NODE_TYPE_STYLES: Record<string, NodeTypeStyle> = {
  character: {
    fill: '#4cd7f6', // secondary / cyan
    border: 'rgba(76,215,246,0.6)',
    glow: 'rgba(76,215,246,0.5)',
  },
  location: {
    fill: '#ffd165', // primary / amber
    border: 'rgba(255,209,101,0.6)',
    glow: 'rgba(255,209,101,0.5)',
  },
  scene: {
    fill: '#c084fc', // purple
    border: 'rgba(192,132,252,0.6)',
    glow: 'rgba(192,132,252,0.5)',
  },
  object: {
    fill: '#4ade80', // green
    border: 'rgba(74,222,128,0.6)',
    glow: 'rgba(74,222,128,0.5)',
  },
  lore: {
    fill: '#fb923c', // orange
    border: 'rgba(251,146,60,0.6)',
    glow: 'rgba(251,146,60,0.5)',
  },
}

export const DEFAULT_NODE_TYPE_STYLE: NodeTypeStyle = {
  fill: '#9b8f79', // outline / warm gray
  border: 'rgba(155,143,121,0.6)',
  glow: 'rgba(155,143,121,0.45)',
}

export const NODE_TYPE_LEGEND: Array<{ key: string; label: string; style: NodeTypeStyle }> = [
  { key: 'character', label: 'CHARACTER', style: NODE_TYPE_STYLES.character },
  { key: 'location', label: 'LOCATION', style: NODE_TYPE_STYLES.location },
  { key: 'scene', label: 'SCENE', style: NODE_TYPE_STYLES.scene },
  { key: 'object', label: 'OBJECT', style: NODE_TYPE_STYLES.object },
  { key: 'lore', label: 'LORE', style: NODE_TYPE_STYLES.lore },
]

export function getNodeTypeStyle(nodeType: string): NodeTypeStyle {
  return NODE_TYPE_STYLES[nodeType] || DEFAULT_NODE_TYPE_STYLE
}

const TYPE_ICONS: Record<string, string> = {
  character: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
  location: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 21h18"/><path d="M5 21V7l8-4 8 4v14"/><path d="M9 9h1"/><path d="M9 13h1"/><path d="M14 9h1"/><path d="M14 13h1"/></svg>`,
  scene: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="2" width="20" height="20" rx="2"/><path d="M7 2v20"/><path d="M17 2v20"/><path d="M2 12h20"/><path d="M2 7h5"/><path d="M2 17h5"/><path d="M17 17h5"/><path d="M17 7h5"/></svg>`,
  object: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="7.2" cy="14.4" r="3.2"/><path d="M10.2 17.6L12 21l5.6-3.6"/><path d="M15.5 7.5a2.121 2.121 0 0 1 3 3L12 16l-3-1.5"/></svg>`,
  lore: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg>`,
}

// Relationship Line Component with animated pulse
const RelationshipLine = ({
  start,
  end,
  type,
  hoveredNodeId,
  connectedToHovered,
}: {
  start: [number, number, number]
  end: [number, number, number]
  type: string
  hoveredNodeId: string | null
  connectedToHovered: boolean
}) => {
  const pulse1Ref = useRef<THREE.Mesh>(null)
  const pulse2Ref = useRef<THREE.Mesh>(null)
  const lineRef = useRef<THREE.Mesh>(null)
  const config = RELATIONSHIP_COLORS[type] || RELATIONSHIP_COLORS.default

  const points = useMemo(() => [new THREE.Vector3(...start), new THREE.Vector3(...end)], [start, end])
  const curve = useMemo(() => new THREE.LineCurve3(points[0], points[1]), [points])

  useFrame(({ clock }) => {
    if (lineRef.current) {
      const mat = lineRef.current.material as THREE.MeshBasicMaterial
      if (connectedToHovered) {
        mat.opacity = THREE.MathUtils.lerp(mat.opacity, 0.8, 0.1)
      } else if (hoveredNodeId) {
        mat.opacity = THREE.MathUtils.lerp(mat.opacity, 0.1, 0.1)
      } else {
        mat.opacity = THREE.MathUtils.lerp(mat.opacity, 0.2, 0.05)
      }
    }

    const duration = 2
    const t1 = ((clock.elapsedTime) % duration) / duration
    const t2 = ((clock.elapsedTime + 1) % duration) / duration

    if (pulse1Ref.current) {
      pulse1Ref.current.position.lerpVectors(points[0], points[1], t1)
    }
    if (pulse2Ref.current) {
      pulse2Ref.current.position.lerpVectors(points[0], points[1], t2)
    }
  })

  return (
    <group>
      <mesh ref={lineRef}>
        <tubeGeometry args={[curve, 1, 0.025, 8, false]} />
        <meshBasicMaterial color={config} transparent opacity={0.2} />
      </mesh>
      <mesh ref={pulse1Ref}>
        <sphereGeometry args={[0.06, 16, 16]} />
        <meshBasicMaterial color={config} />
      </mesh>
      <mesh ref={pulse2Ref}>
        <sphereGeometry args={[0.06, 16, 16]} />
        <meshBasicMaterial color={config} />
      </mesh>
    </group>
  )
}

// Node Component
const Node = ({
  node,
  position,
  isSelected,
  onClick,
  onHover,
}: {
  node: UniverseNode
  position: [number, number, number]
  isSelected: boolean
  onClick: () => void
  onHover: (hovered: boolean) => void
}) => {
  const meshRef = useRef<THREE.Mesh>(null)
  const glowRef = useRef<THREE.Mesh>(null)
  const groupRef = useRef<THREE.Group>(null)
  const outlineRef = useRef<THREE.LineSegments>(null)

  const isProtagonist = node.universe_tags.includes('protagonist')
  const isSupporting = node.universe_tags.includes('supporting')

  // Type-based style drives fill / border / glow color.
  // Sizes still depend on character role tags — only color is type-derived.
  const typeStyle = getNodeTypeStyle(node.node_type)
  const baseColor = typeStyle.fill

  const scale = isProtagonist ? 1.5 : isSupporting ? 0.95 : 0.7

  // Stable outline geometry so we don't rebuild it on every frame.
  const outlineGeometry = useMemo(() => new THREE.SphereGeometry(0.5, 16, 16), [])

  useFrame(({ clock }) => {
    if (meshRef.current && !isSelected) {
      const t = clock.elapsedTime
      // Per-node phase from id length gives each node its own micro-orbit.
      const phase = node.node_id.length * 0.7
      meshRef.current.position.x = Math.sin(t * 0.32 + phase) * 0.06
      meshRef.current.position.y = Math.sin(t * 0.5 + phase * 1.3) * 0.09
      meshRef.current.position.z = Math.cos(t * 0.4 + phase * 0.6) * 0.06
    }
    if (glowRef.current) {
      const s = scale + 0.2 + Math.sin(clock.elapsedTime * 1.5) * 0.05
      glowRef.current.scale.setScalar(s)
    }
  })

  return (
    <group ref={groupRef} position={position} scale={[scale, scale, scale]}>
      {/* Outer glow halo — applied to every node, color = type fill */}
      <mesh ref={glowRef}>
        <sphereGeometry args={[0.72, 32, 32]} />
        <meshBasicMaterial
          color={baseColor}
          transparent
          opacity={isProtagonist ? 0.35 : 0.18}
        />
      </mesh>

      {/* Border outline — wireframe edges in type border color */}
      <lineSegments ref={outlineRef}>
        <edgesGeometry args={[outlineGeometry]} />
        <lineBasicMaterial color={typeStyle.border} transparent opacity={isSelected ? 0.95 : 0.6} />
      </lineSegments>

      {/* Inner tinted fill — 0.15 opacity (or full when selected) */}
      <mesh
        ref={meshRef}
        onClick={(e) => {
          e.stopPropagation()
          onClick()
        }}
        onPointerOver={(e) => {
          e.stopPropagation()
          onHover(true)
        }}
        onPointerOut={(e) => {
          e.stopPropagation()
          onHover(false)
        }}
      >
        <sphereGeometry args={[0.5, 32, 32]} />
        <meshStandardMaterial
          color={baseColor}
          transparent
          opacity={isSelected ? 1 : 0.15}
          emissive={baseColor}
          emissiveIntensity={isSelected ? 0.6 : 0.35}
          depthWrite={false}
        />
      </mesh>

      {isProtagonist && (
        <mesh>
          <boxGeometry args={[1.6, 1.6, 1.6]} />
          <meshBasicMaterial color={baseColor} wireframe transparent opacity={0.5} />
        </mesh>
      )}

      <Html position={[0, 0, 0]} center pointerEvents="none" style={{ pointerEvents: 'none' }}>
        <div
          className="flex items-center justify-center"
          style={{
            width: 28,
            height: 28,
            color: 'rgba(255,255,255,0.8)',
          }}
          dangerouslySetInnerHTML={{ __html: TYPE_ICONS[node.node_type] || '' }}
        />
      </Html>

      <Html position={[0, -1.05, 0]} center pointerEvents="none">
        <div
          className="font-status-xs uppercase tracking-[0.15em] text-[10px]"
          style={{
            color: 'var(--color-on-surface)',
            whiteSpace: 'nowrap',
            textShadow: '0 1px 3px rgba(0,0,0,0.8)',
          }}
        >
          {node.name}
        </div>
      </Html>
    </group>
  )
}

// ── Star field & nebula ────────────────────────────────────────────────────
// Multi-layer star field rendered as additive points with a custom shader for
// per-vertex twinkle, plus a handful of large additive-blended sphere "clouds"
// that simulate deep-space dust/nebula.

const STAR_VERTEX_SHADER = /* glsl */ `
  attribute float aSize;
  attribute float aPhase;
  attribute float aBrightness;
  varying vec3 vColor;
  varying float vAlpha;
  uniform float uTime;
  uniform float uPixelRatio;

  void main() {
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    // Independent twinkle per star; mix keeps even the dim stars visible.
    float twinkle = mix(0.55, 1.0, sin(uTime * 1.4 + aPhase) * 0.5 + 0.5);
    vAlpha = aBrightness * twinkle;
    vColor = color;
    gl_PointSize = aSize * uPixelRatio * (300.0 / max(-mvPosition.z, 0.1));
    gl_Position = projectionMatrix * mvPosition;
  }
`

const STAR_FRAGMENT_SHADER = /* glsl */ `
  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    vec2 cxy = 2.0 * gl_PointCoord - 1.0;
    float r2 = dot(cxy, cxy);
    if (r2 > 1.0) discard;
    // Soft round sprite: bright core + gentle halo.
    float core = smoothstep(0.55, 0.0, r2);
    float halo = exp(-r2 * 3.2);
    gl_FragColor = vec4(vColor, (core * 0.95 + halo * 0.35) * vAlpha);
  }
`

// Stellar color palette (true-ish star classes: O/B blue-white, G sun-like,
// K orange, M red dwarfs). Most stars lean toward the G/A range.
const STAR_COLORS = {
  blueWhite: new THREE.Color('#cfe6ff'),
  white: new THREE.Color('#f2eee9'),
  warmWhite: new THREE.Color('#ffe7c4'),
  amber: new THREE.Color('#ffb878'),
  red: new THREE.Color('#ff8a6a'),
}

function pickStarColor(): THREE.Color {
  const r = Math.random()
  if (r < 0.62) return STAR_COLORS.white
  if (r < 0.82) return STAR_COLORS.warmWhite
  if (r < 0.92) return STAR_COLORS.blueWhite
  if (r < 0.98) return STAR_COLORS.amber
  return STAR_COLORS.red
}

function buildStarLayer(
  count: number,
  radiusMin: number,
  radiusMax: number,
  sizeMin: number,
  sizeMax: number,
  brightnessMin: number,
  brightnessMax: number,
): THREE.BufferGeometry {
  const positions = new Float32Array(count * 3)
  const colors = new Float32Array(count * 3)
  const sizes = new Float32Array(count)
  const phases = new Float32Array(count)
  const brightness = new Float32Array(count)

  for (let i = 0; i < count; i++) {
    // Uniform sphere distribution.
    const u = Math.random()
    const v = Math.random()
    const theta = 2 * Math.PI * u
    const phi = Math.acos(2 * v - 1)
    const r = radiusMin + Math.random() * (radiusMax - radiusMin)
    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta)
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
    positions[i * 3 + 2] = r * Math.cos(phi)

    const c = pickStarColor()
    colors[i * 3] = c.r
    colors[i * 3 + 1] = c.g
    colors[i * 3 + 2] = c.b

    sizes[i] = sizeMin + Math.random() * (sizeMax - sizeMin)
    phases[i] = Math.random() * Math.PI * 2
    // Power curve biases toward dimmer stars; the rare bright ones pop.
    const t = Math.random()
    brightness[i] = brightnessMin + Math.pow(t, 2.4) * (brightnessMax - brightnessMin)
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  geometry.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1))
  geometry.setAttribute('aPhase', new THREE.BufferAttribute(phases, 1))
  geometry.setAttribute('aBrightness', new THREE.BufferAttribute(brightness, 1))
  return geometry
}

// Nebula clouds — large, additive-blended sphere meshes placed far behind
// the action to create soft, colored depth.
const NEBULA_CLOUDS = [
  { position: [18, 6, -28] as const, color: '#3b1d6e', size: 22, opacity: 0.18 },
  { position: [-22, -8, -24] as const, color: '#1e3a8a', size: 18, opacity: 0.16 },
  { position: [10, -14, -32] as const, color: '#7c2d12', size: 20, opacity: 0.14 },
  { position: [-14, 14, -34] as const, color: '#581c87', size: 24, opacity: 0.15 },
  { position: [4, 4, 28] as const, color: '#0c4a6e', size: 22, opacity: 0.12 },
]

const Nebula = () => (
  <>
    {NEBULA_CLOUDS.map((c, i) => (
      <mesh key={i} position={[...c.position]}>
        <sphereGeometry args={[c.size, 24, 24]} />
        <meshBasicMaterial
          color={c.color}
          transparent
          opacity={c.opacity}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          side={THREE.BackSide}
        />
      </mesh>
    ))}
  </>
)

// Slowly drift the far-star group around Y for parallax — the sky itself
// keeps gently turning when the camera is idle.
const StarField = () => {
  const farGroupRef = useRef<THREE.Group>(null)
  const midGroupRef = useRef<THREE.Group>(null)

  // Three depth layers give the sense of parallax when the camera drifts.
  const farGeometry = useMemo(
    () => buildStarLayer(600, 38, 65, 0.05, 0.14, 0.35, 0.7),
    [],
  )
  const midGeometry = useMemo(
    () => buildStarLayer(220, 20, 34, 0.1, 0.22, 0.55, 0.9),
    [],
  )
  const brightGeometry = useMemo(
    () => buildStarLayer(45, 12, 22, 0.18, 0.42, 0.85, 1.0),
    [],
  )

  const material = useMemo(() => {
    return new THREE.ShaderMaterial({
      vertexShader: STAR_VERTEX_SHADER,
      fragmentShader: STAR_FRAGMENT_SHADER,
      uniforms: {
        uTime: { value: 0 },
        uPixelRatio: { value: Math.min(window.devicePixelRatio || 1, 2) },
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexColors: true,
    })
  }, [])

  useFrame(({ clock }, delta) => {
    material.uniforms.uTime.value = clock.elapsedTime
    // Far layer drifts slower than the mid layer — gives a gentle parallax.
    if (farGroupRef.current) farGroupRef.current.rotation.y += delta * 0.006
    if (midGroupRef.current) midGroupRef.current.rotation.y += delta * 0.018
  })

  return (
    <>
      <group ref={farGroupRef}>
        <points geometry={farGeometry} material={material} />
      </group>
      <group ref={midGroupRef}>
        <points geometry={midGeometry} material={material} />
      </group>
      <points geometry={brightGeometry} material={material} />
    </>
  )
}

// Controls Manager
const ControlsManager = () => {
  const controlsRef = useRef<any>(null)
  const lastInteractionTime = useRef(Date.now())
  const baseTarget = useMemo(() => new THREE.Vector3(0, 0, 0), [])

  useFrame(({ clock }) => {
    if (!controlsRef.current) return
    const now = Date.now()
    const idleTime = now - lastInteractionTime.current
    controlsRef.current.autoRotate = idleTime > 4000

    // Subtle camera-target drift while idle — the eye keeps gently wandering.
    if (idleTime > 4000) {
      const t = clock.elapsedTime
      controlsRef.current.target.set(
        Math.sin(t * 0.07) * 0.18,
        Math.sin(t * 0.05 + 1.4) * 0.12,
        Math.cos(t * 0.06) * 0.18,
      )
      controlsRef.current.update()
    } else if (
      controlsRef.current.target.x !== 0 ||
      controlsRef.current.target.y !== 0 ||
      controlsRef.current.target.z !== 0
    ) {
      // Snap target back to origin on interaction so dragging feels stable.
      controlsRef.current.target.copy(baseTarget)
    }
  })

  const handleInteraction = () => {
    lastInteractionTime.current = Date.now()
    if (controlsRef.current) {
      controlsRef.current.autoRotate = false
    }
  }

  return (
    <OrbitControls
      ref={controlsRef}
      autoRotate
      autoRotateSpeed={0.28}
      enableDamping
      dampingFactor={0.08}
      minDistance={5}
      maxDistance={20}
      onStart={handleInteraction}
      onChange={handleInteraction}
    />
  )
}

// Main Scene
const Scene = ({
  nodes,
  relationships,
  selectedNodeId,
  onNodeClick,
  onHover,
}: {
  nodes: UniverseNode[]
  relationships: UniverseRelationship[]
  selectedNodeId: string | null
  onNodeClick: (node: UniverseNode) => void
  onHover: (node: UniverseNode | null) => void
}) => {
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)

  const nodePositions = useMemo(() => {
    const positions: Record<string, [number, number, number]> = {}
    const count = nodes.length
    nodes.forEach((node, i) => {
      const phi = Math.acos(-1 + (2 * i) / count)
      const theta = Math.sqrt(count * Math.PI) * phi
      const radius = 5
      const x = radius * Math.cos(theta) * Math.sin(phi)
      const y = radius * Math.sin(theta) * Math.sin(phi)
      const z = Math.sin(i * 1.3) * 2.5
      positions[node.node_id] = [x, y, z]
    })
    return positions
  }, [nodes])

  const connectedNodeIds = useMemo(() => {
    if (!hoveredNodeId) return new Set<string>()
    const connected = new Set<string>()
    relationships.forEach((r) => {
      if (r.from_node === hoveredNodeId) connected.add(r.to_node)
      if (r.to_node === hoveredNodeId) connected.add(r.from_node)
    })
    return connected
  }, [hoveredNodeId, relationships])

  return (
    <>
      {/* Hemisphere ambient — bluish above (cool cosmic), warm below (sun-side dust). */}
      <hemisphereLight args={['#4a6fa5', '#1a0f0a', 0.28]} />
      {/* Distributed warm + cool point lights — adds subtle color variation across nodes. */}
      <pointLight position={[0, 6, 4]} intensity={0.55} color="#ffd165" distance={25} decay={2} />
      <pointLight position={[-10, -3, 5]} intensity={0.32} color="#4cd7f6" distance={22} decay={2} />
      <pointLight position={[9, -6, -8]} intensity={0.28} color="#c084fc" distance={20} decay={2} />
      <pointLight position={[4, 9, -6]} intensity={0.22} color="#fb923c" distance={18} decay={2} />

      {relationships.map((rel) => {
        const startPos = nodePositions[rel.from_node]
        const endPos = nodePositions[rel.to_node]
        if (!startPos || !endPos) return null
        const isConnectedToHovered = connectedNodeIds.has(rel.from_node) || connectedNodeIds.has(rel.to_node)

        return (
          <RelationshipLine
            key={rel.relationship_id}
            start={startPos}
            end={endPos}
            type={rel.relationship_type}
            hoveredNodeId={hoveredNodeId}
            connectedToHovered={isConnectedToHovered}
          />
        )
      })}

      {nodes.map((node) => {
        const position = nodePositions[node.node_id]
        if (!position) return null
        return (
          <Node
            key={node.node_id}
            node={node}
            position={position}
            isSelected={selectedNodeId === node.node_id}
            onClick={() => onNodeClick(node)}
            onHover={(hovered) => {
              setHoveredNodeId(hovered ? node.node_id : null)
              onHover(hovered ? node : null)
            }}
          />
        )
      })}

      {/* Cosmic backdrop drawn last so it sits behind everything. */}
      <Nebula />
      <StarField />
    </>
  )
}

// Main Component
const UniverseGraph3D: React.FC<UniverseGraph3DProps> = ({
  nodes,
  relationships,
  selectedNodeId,
  onNodeClick,
  onNodeHover,
}) => {
  return (
    <div
      className="w-full h-full"
      style={{
        // Deep-space backdrop — radial vignette pulls the eye toward the center.
        background:
          'radial-gradient(ellipse at 50% 55%, #08111c 0%, #050810 45%, #02040a 100%)',
      }}
    >
      <Canvas
        camera={{ position: [0, 0, 14], fov: 50 }}
        style={{ width: '100%', height: '100%' }}
        gl={{ powerPreference: "high-performance", antialias: false, alpha: true }}
        scene={{ background: null }}
      >
        {/* Atmospheric distance fade — soft enough that far stars still read. */}
        <fog attach="fog" args={['#050810', 18, 75]} />
        <ControlsManager />
        <Scene
          nodes={nodes}
          relationships={relationships}
          selectedNodeId={selectedNodeId}
          onNodeClick={onNodeClick}
          onHover={onNodeHover}
        />
        {/* Subtle bloom — only the emissive nodes/halos really light up. */}
        <EffectComposer multisampling={0}>
          <Bloom
            intensity={0.85}
            luminanceThreshold={0.35}
            luminanceSmoothing={0.2}
            mipmapBlur
            kernelSize={KernelSize.LARGE}
            blendFunction={BlendFunction.SCREEN}
          />
        </EffectComposer>
      </Canvas>
    </div>
  )
}

export default UniverseGraph3D