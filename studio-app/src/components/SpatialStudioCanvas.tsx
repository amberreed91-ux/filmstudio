import { Component, Suspense, useMemo, useRef, useState, type ReactNode } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, useGLTF } from '@react-three/drei'
import * as THREE from 'three'

/** Dedicated 3D room mesh — drop a Blender export at this path to replace procedural geometry. */
export const STUDIO_LOBBY_MODEL_URL = '/models/studio_lobby.glb'

/** Ambient dust particle count for the atmospheric shader layer. */
export const AMBIENT_DUST_COUNT = 320

/** Deep violet portal glow shared across rings, fog accents, and selection states. */
export const PORTAL_GLOW_VIOLET = '#6D28D9'

/**
 * Tactical soundstage scene — Fee Fee Anne Studios.
 * Ports the standalone `code.html` ANIMATION_8 soundstage into R3F scale:
 * obsidian circular floor grid, concentric neon rings, overhead industrial
 * trusses with volumetric cones, central FF monogram pedestal with orbiting
 * rings, 12 bespoke miniature room bays with LED rims + tag banners,
 * connected by pulsing laser conduits.
 *
 * Self-contained scene-graph component (no <Canvas> wrapper) so hosts like
 * Interactive3DLobby can embed it as the primary background viewport inside
 * their own Canvas, keeping camera controls and overlays in one place.
 */

export interface SpatialPortal {
  key: string
  label: string
  sub: string
  to: string
  color: string
  angle: number
  position: [number, number, number]
}

const PORTAL_RADIUS = 6.4

function portalPosition(angle: number): [number, number, number] {
  return [Math.cos(angle) * PORTAL_RADIUS, 0, Math.sin(angle) * PORTAL_RADIUS]
}

function portalRotation(position: [number, number, number]): number {
  // Face the bay toward the stage center.
  return Math.atan2(-position[0], -position[2])
}

// 12 tactical room bays. Angles mirror the standalone ANIMATION_8 staging;
// `to` values mirror real APP_ROUTES paths in studio-app/src/routes.tsx so
// selection navigates into existing 2D rooms. Backend routes + studio.db
// isolation are untouched — these are navigation targets only.
export const SPATIAL_PORTALS: SpatialPortal[] = [
  { key: 'atrium', label: 'The Atrium', sub: 'glass entry pavilion', to: '/studio', color: '#e0e7ff', angle: -Math.PI * 0.64, position: portalPosition(-Math.PI * 0.64) },
  { key: 'gate', label: 'Gate Intake', sub: 'holographic orb vessel', to: '/studio/gate', color: '#38bdf8', angle: -Math.PI * 0.45, position: portalPosition(-Math.PI * 0.45) },
  { key: 'page', label: 'Page', sub: "screenwriter's office", to: '/studio/page', color: '#f59e0b', angle: -Math.PI * 0.3, position: portalPosition(-Math.PI * 0.3) },
  { key: 'board', label: 'Board', sub: 'narrative shot wall', to: '/studio/board', color: '#ec4899', angle: -Math.PI * 0.15, position: portalPosition(-Math.PI * 0.15) },
  { key: 'previs', label: 'Previs Bay', sub: 'virtual production stage', to: '/studio/previs', color: '#a855f7', angle: 0.0, position: portalPosition(0.0) },
  { key: 'screening', label: 'Screening', sub: 'cinema 4K DCP review', to: '/studio/screening-room', color: '#ffffff', angle: Math.PI * 0.16, position: portalPosition(Math.PI * 0.16) },
  { key: 'universe', label: 'Universe', sub: 'spatial constellation graph', to: '/studio/universe-graph', color: '#818cf8', angle: Math.PI * 0.32, position: portalPosition(Math.PI * 0.32) },
  { key: 'vault', label: 'The Vault', sub: 'spatial helix cold store', to: '/studio/archive', color: '#38bdf8', angle: Math.PI * 0.48, position: portalPosition(Math.PI * 0.48) },
  { key: 'production', label: 'Production Desk', sub: 'command telemetry desk', to: '/studio/production-desk', color: '#2dd4bf', angle: Math.PI * 0.64, position: portalPosition(Math.PI * 0.64) },
  { key: 'integrity', label: 'Integrity Engine', sub: 'laser quarantine chamber', to: '/studio/integrity', color: '#10b981', angle: Math.PI * 0.82, position: portalPosition(Math.PI * 0.82) },
  { key: 'reference', label: 'Reference Atelier', sub: 'visual dev mood boards', to: '/studio/reference-space', color: '#f43f5e', angle: Math.PI * 0.98, position: portalPosition(Math.PI * 0.98) },
  { key: 'project', label: 'Project Room', sub: 'focus enclave workstation', to: '/studio/slate', color: '#8b5cf6', angle: -Math.PI * 0.82, position: portalPosition(-Math.PI * 0.82) },
]

function StudioLighting({ centerRef }: { centerRef: React.RefObject<THREE.PointLight | null> }) {
  return (
    <>
      {/* Deep violet ambient base */}
      <ambientLight intensity={0.6} color="#2d1a4e" />
      <hemisphereLight args={['#6D28D9', '#0b0620', 0.5]} />
      {/* Violet key + deep violet rim */}
      <pointLight position={[0, 7, 4]} intensity={120} distance={40} color="#6D28D9" />
      <pointLight position={[-7, 4, -5]} intensity={70} distance={35} color="#4C1D95" />
      <pointLight position={[7, 3, -4]} intensity={50} distance={30} color="#6D28D9" />
      {/* Pulsing stage-center glow (animated via ref) */}
      <pointLight ref={centerRef} position={[0, 3, 0]} intensity={30} distance={22} color="#a855f7" />
      {/* Dynamic shadow-mapped key light for room-mesh depth */}
      <directionalLight
        position={[0, 8, 0]}
        intensity={0.5}
        color="#c4b5fd"
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-camera-near={1}
        shadow-camera-far={30}
        shadow-camera-left={-12}
        shadow-camera-right={12}
        shadow-camera-top={12}
        shadow-camera-bottom={-12}
      />
    </>
  )
}

/** Volumetric-feel dust motes drifting through the violet key light. */
function AmbientDust({ count = AMBIENT_DUST_COUNT }: { count?: number }) {
  const group = useRef<THREE.Points>(null)
  const positions = useMemo(() => {
    const points = new Float32Array(count * 3)
    for (let index = 0; index < count; index += 1) {
      const radius = 2 + Math.random() * 9
      const angle = Math.random() * Math.PI * 2
      points[index * 3] = Math.cos(angle) * radius
      points[index * 3 + 1] = 0.2 + Math.random() * 6
      points[index * 3 + 2] = Math.sin(angle) * radius
    }
    return points
  }, [count])
  useFrame(({ clock }) => {
    if (!group.current) return
    const t = clock.getElapsedTime()
    group.current.rotation.y = t * 0.02
    group.current.position.y = Math.sin(t * 0.25) * 0.15
  })
  return (
    <points ref={group} data-testid="spatial-ambient-dust">
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        color="#a78bfa"
        size={0.045}
        transparent
        opacity={0.55}
        depthWrite={false}
        sizeAttenuation
        blending={THREE.AdditiveBlending}
      />
    </points>
  )
}

/** Obsidian circular floor platform with procedural grid texture. */
function useGridTexture(): THREE.CanvasTexture {
  return useMemo(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 512
    canvas.height = 512
    const ctx = canvas.getContext('2d')
    if (!ctx) return new THREE.CanvasTexture(canvas)
    ctx.fillStyle = '#0a0614'
    ctx.fillRect(0, 0, 512, 512)
    ctx.strokeStyle = '#23123d'
    ctx.lineWidth = 1.5
    for (let i = 0; i <= 512; i += 32) {
      ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, 512); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(512, i); ctx.stroke()
    }
    const tex = new THREE.CanvasTexture(canvas)
    tex.wrapS = THREE.RepeatWrapping
    tex.wrapT = THREE.RepeatWrapping
    tex.repeat.set(10, 10)
    return tex
  }, [])
}

function ObsidianFloor() {
  const grid = useGridTexture()
  return (
    <group>
      {/* Circular obsidian platform */}
      <mesh position={[0, -0.4, 0]} receiveShadow>
        <cylinderGeometry args={[9.2, 9.5, 0.8, 64]} />
        <meshStandardMaterial map={grid} color="#110920" roughness={0.35} metalness={0.7} />
      </mesh>
      {/* Concentric neon floor markings */}
      <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[1.9, 1.96, 64]} />
        <meshBasicMaterial color="#c084fc" transparent opacity={0.85} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[4.9, 4.97, 64]} />
        <meshBasicMaterial color="#6d28d9" transparent opacity={0.5} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[8.5, 8.58, 64]} />
        <meshBasicMaterial color="#6d28d9" transparent opacity={0.5} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      {/* Violet under-glow disc beneath the brand mark */}
      <mesh position={[0, 0.03, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[1.6, 2.4, 64]} />
        <meshBasicMaterial color="#6D28D9" transparent opacity={0.35} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
    </group>
  )
}

/** Overhead industrial lighting trusses with volumetric cones. */
function LightingTrusses() {
  const beams = useMemo(() => Array.from({ length: 8 }, (_, r) => (r / 8) * Math.PI * 2), [])
  return (
    <group position={[0, 9, 0]}>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[8, 0.12, 8, 48]} />
        <meshStandardMaterial color="#3b1c60" metalness={0.8} roughness={0.3} />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[3.4, 0.09, 8, 36]} />
        <meshStandardMaterial color="#3b1c60" metalness={0.8} roughness={0.3} />
      </mesh>
      {beams.map((rad) => (
        <group key={rad}>
          <mesh position={[Math.cos(rad) * 5.7, 0, Math.sin(rad) * 5.7]} rotation={[0, -rad + Math.PI / 2, 0]}>
            <boxGeometry args={[0.09, 0.09, 4.6]} />
            <meshStandardMaterial color="#3b1c60" metalness={0.8} roughness={0.3} />
          </mesh>
          {/* Fresnel housing */}
          <mesh position={[Math.cos(rad) * 7.7, -0.2, Math.sin(rad) * 7.7]}>
            <cylinderGeometry args={[0.14, 0.22, 0.34, 12]} />
            <meshStandardMaterial color="#190b2c" />
          </mesh>
          {/* Volumetric beam cone */}
          <mesh position={[Math.cos(rad) * 6, -2.4, Math.sin(rad) * 6]}>
            <coneGeometry args={[1.05, 4.8, 16, 1, true]} />
            <meshBasicMaterial color="#9333ea" transparent opacity={0.08} side={THREE.DoubleSide} blending={THREE.AdditiveBlending} depthWrite={false} />
          </mesh>
        </group>
      ))}
    </group>
  )
}

/** FF monogram logo texture (procedural canvas). */
function useLogoTexture(): THREE.CanvasTexture {
  return useMemo(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 512
    canvas.height = 512
    const ctx = canvas.getContext('2d')
    if (ctx) {
      const grad = ctx.createRadialGradient(256, 256, 25, 256, 256, 255)
      grad.addColorStop(0, '#581c87')
      grad.addColorStop(0.5, '#2e1065')
      grad.addColorStop(0.9, '#080112')
      ctx.fillStyle = grad
      ctx.beginPath(); ctx.arc(256, 256, 245, 0, Math.PI * 2); ctx.fill()
      ctx.lineWidth = 7
      ctx.strokeStyle = '#c084fc'
      ctx.stroke()
      ctx.lineWidth = 2
      ctx.strokeStyle = '#a855f7'
      ctx.beginPath(); ctx.arc(256, 256, 230, 0, Math.PI * 2); ctx.stroke()
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillStyle = '#ffffff'
      ctx.font = 'italic bold 145px "Times New Roman", Georgia, serif'
      ctx.shadowColor = '#d8b4fe'
      ctx.shadowBlur = 22
      ctx.fillText('FF', 256, 235)
      ctx.shadowBlur = 0
      ctx.font = 'bold 21px monospace'
      ctx.fillStyle = '#f3e8ff'
      ctx.fillText('FEE FEE ANNE', 256, 345)
      ctx.font = 'bold 14px monospace'
      ctx.fillStyle = '#a855f7'
      ctx.fillText('✦ STUDIOS ✦', 256, 375)
    }
    return new THREE.CanvasTexture(canvas)
  }, [])
}

/** Central glowing FF monogram pedestal with orbiting rings. */
function FFMonogramPedestal() {
  const logo = useLogoTexture()
  const orbital = useRef<THREE.Group>(null)
  const orb1 = useRef<THREE.Mesh>(null)
  const orb2 = useRef<THREE.Mesh>(null)
  const logoRef = useRef<THREE.Mesh>(null)
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    if (orb1.current) orb1.current.rotation.z = t * 0.5
    if (orb2.current) orb2.current.rotation.y = -t * 0.35
    if (orbital.current) orbital.current.rotation.y = t * 0.2
    if (logoRef.current) logoRef.current.rotation.z = t * 0.04
  })
  return (
    <group>
      <mesh position={[0, 0.35, 0]}>
        <cylinderGeometry args={[1.65, 1.78, 0.7, 48]} />
        <meshStandardMaterial color="#140726" roughness={0.25} metalness={0.85} />
      </mesh>
      <mesh position={[0, 0.72, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.72, 0.045, 12, 64]} />
        <meshBasicMaterial color="#d8b4fe" />
      </mesh>
      <mesh ref={logoRef} position={[0, 0.73, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[1.62, 48]} />
        <meshBasicMaterial map={logo} />
      </mesh>
      <group ref={orbital} position={[0, 1.35, 0]}>
        <mesh ref={orb1} rotation={[0.55, 0.35, 0]}>
          <torusGeometry args={[1.95, 0.025, 12, 64]} />
          <meshBasicMaterial color="#a855f7" />
        </mesh>
        <mesh ref={orb2} rotation={[-0.45, 0, 0.7]}>
          <torusGeometry args={[2.15, 0.02, 12, 64]} />
          <meshBasicMaterial color="#38bdf8" transparent opacity={0.85} />
        </mesh>
      </group>
      <Html center position={[0, 2.2, 0]} zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
        <div className="text-center" aria-hidden="true" style={{ pointerEvents: 'none' }}>
          <div className="text-sm font-bold uppercase text-zinc-100" style={{ letterSpacing: '0.42em', textShadow: '0 0 18px rgba(167,139,250,0.8)' }}>
            FEE FEE ANNE STUDIOS
          </div>
          <div className="mt-1 text-[10px] uppercase text-violet-300/70" style={{ letterSpacing: '0.3em' }}>
            Procedural Soundstage
          </div>
        </div>
      </Html>
    </group>
  )
}

/** Celestial constellation node graph (universe bay) — hooks live at this
 *  component's top level so RoomProp's switch never calls hooks conditionally. */
function UniverseConstellation() {
  const nodes: Array<[number, number, number]> = [
    [-0.55, 0.55, -0.35], [-0.25, 0.95, 0.25], [0.05, 0.6, -0.5],
    [0.5, 1.05, 0.12], [0.38, 0.55, 0.42], [-0.42, 1.0, -0.18],
  ]
  const linePositions = useMemo(() => {
    const pairs = [[0, 1], [1, 3], [3, 4], [4, 2], [2, 0], [1, 5], [5, 3]]
    const flat: number[] = []
    pairs.forEach(([a, b]) => {
      flat.push(...nodes[a], ...nodes[b])
    })
    return new Float32Array(flat)
  }, [])
  return (
    <group>
      {nodes.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.085, 12, 12]} />
          <meshBasicMaterial color={i % 2 === 0 ? '#818cf8' : '#38bdf8'} />
        </mesh>
      ))}
      <lineSegments>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[linePositions, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color="#6366f1" />
      </lineSegments>
    </group>
  )
}

/** Bespoke miniature prop per room bay — low-poly, emissive-led, no per-bay lights. */
function RoomProp({ roomKey, color }: { roomKey: string; color: string }) {
  switch (roomKey) {
    case 'atrium':
      return (
        <group>
          <mesh position={[0, 0.75, 0]}>
            <boxGeometry args={[1.7, 0.8, 1.7]} />
            <meshStandardMaterial color="#c7d2fe" transparent opacity={0.4} roughness={0.15} metalness={0.4} />
          </mesh>
          <mesh position={[0, 1.35, 0]} rotation={[0, Math.PI / 4, 0]}>
            <coneGeometry args={[1.25, 0.65, 4]} />
            <meshStandardMaterial color="#c7d2fe" transparent opacity={0.45} roughness={0.15} metalness={0.4} />
          </mesh>
          {[[-0.45, -0.45], [0.45, -0.45], [-0.45, 0.45], [0.45, 0.45]].map(([px, pz]) => (
            <mesh key={`${px}${pz}`} position={[px, 0.45, pz]}>
              <dodecahedronGeometry args={[0.13]} />
              <meshStandardMaterial color="#10b981" roughness={0.6} />
            </mesh>
          ))}
        </group>
      )
    case 'gate':
      return (
        <group>
          <mesh position={[0, 0.2, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[0.72, 0.055, 12, 32]} />
            <meshStandardMaterial color="#0369a1" metalness={0.9} roughness={0.3} />
          </mesh>
          <mesh position={[0, 0.85, 0]}>
            <sphereGeometry args={[0.42, 24, 24]} />
            <meshStandardMaterial color="#38bdf8" emissive="#0284c7" emissiveIntensity={0.9} roughness={0.15} />
          </mesh>
          <mesh position={[0, 0.85, 0]} rotation={[0.8, 0, 0]}>
            <torusGeometry args={[0.6, 0.025, 12, 32]} />
            <meshBasicMaterial color="#7dd3fc" />
          </mesh>
          {([-0.5, 0, 0.5]).map((ox) => (
            <mesh key={ox} position={[ox, 0.8, -0.7]}>
              <boxGeometry args={[0.45, 0.65, 0.04]} />
              <meshStandardMaterial color="#0ea5e9" transparent opacity={0.6} roughness={0.2} />
            </mesh>
          ))}
        </group>
      )
    case 'page':
      return (
        <group>
          <mesh position={[0, 0.85, -0.85]}>
            <boxGeometry args={[1.9, 1.05, 0.09]} />
            <meshStandardMaterial color="#1f172e" />
          </mesh>
          {[0.55, 0.85, 1.15].map((sy) => (
            <mesh key={sy} position={[0, sy, -0.78]}>
              <boxGeometry args={[1.65, 0.035, 0.18]} />
              <meshStandardMaterial color="#78350f" roughness={0.6} />
            </mesh>
          ))}
          <mesh position={[0, 0.35, -0.1]}>
            <boxGeometry args={[1.1, 0.25, 0.55]} />
            <meshStandardMaterial color="#451a03" roughness={0.4} />
          </mesh>
          <mesh position={[0, 0.68, -0.18]}>
            <boxGeometry args={[0.55, 0.3, 0.03]} />
            <meshBasicMaterial color="#fef08a" />
          </mesh>
        </group>
      )
    case 'board':
      return (
        <group>
          <mesh position={[0, 0.8, -0.85]}>
            <boxGeometry args={[1.75, 1.0, 0.06]} />
            <meshStandardMaterial color="#1e152d" />
          </mesh>
          {([0.62, 1.0]).map((ry, ri) => (
            ([-0.6, -0.2, 0.2, 0.6]).map((cx) => (
              <mesh key={`${ri}-${cx}`} position={[cx, ry, -0.81]}>
                <boxGeometry args={[0.32, 0.24, 0.02]} />
                <meshBasicMaterial color={(ri + Math.round(cx * 10)) % 2 === 0 ? '#f472b6' : '#fbcfe8'} />
              </mesh>
            ))
          ))}
          <mesh position={[0, 0.35, 0.1]} rotation={[0.25, 0, 0]}>
            <boxGeometry args={[1.05, 0.03, 0.62]} />
            <meshStandardMaterial color="#334155" />
          </mesh>
        </group>
      )
    case 'previs':
      return (
        <group>
          <mesh position={[0, 0.75, -0.35]}>
            <cylinderGeometry args={[1.0, 1.0, 1.1, 24, 1, true, 0, Math.PI]} />
            <meshBasicMaterial color="#581c87" side={THREE.BackSide} />
          </mesh>
          <mesh position={[0, 0.18, 0.15]}>
            <boxGeometry args={[0.12, 0.03, 1.35]} />
            <meshStandardMaterial color="#64748b" metalness={0.9} roughness={0.3} />
          </mesh>
          <mesh position={[0, 0.42, 0.45]}>
            <coneGeometry args={[0.22, 0.5, 4]} />
            <meshStandardMaterial color="#020617" metalness={0.8} />
          </mesh>
          <mesh position={[0, 0.72, 0.45]}>
            <boxGeometry args={[0.22, 0.16, 0.28]} />
            <meshStandardMaterial color="#1e1b4b" />
          </mesh>
          <mesh position={[0, 0.72, -0.25]} rotation={[-Math.PI / 2, 0, 0]}>
            <coneGeometry args={[0.55, 1.0, 4, 1, true]} />
            <meshBasicMaterial color="#c084fc" transparent opacity={0.25} wireframe />
          </mesh>
        </group>
      )
    case 'screening':
      return (
        <group>
          <mesh position={[0, 0.85, -1.15]}>
            <cylinderGeometry args={[1.85, 1.85, 1.0, 24, 1, true, Math.PI * 0.38, Math.PI * 0.24]} />
            <meshBasicMaterial color="#ffffff" side={THREE.DoubleSide} />
          </mesh>
          {([0, 1]).map((tier) => (
            <group key={tier}>
              <mesh position={[0, 0.2 + tier * 0.12, -0.2 + tier * 0.35]}>
                <boxGeometry args={[1.6, 0.11 * (tier + 1) + 0.1, 0.32]} />
                <meshStandardMaterial color="#0f0b18" />
              </mesh>
              {([-0.6, 0, 0.6]).map((sx) => (
                <mesh key={sx} position={[sx, 0.42 + tier * 0.12, -0.2 + tier * 0.35]}>
                  <boxGeometry args={[0.28, 0.22, 0.24]} />
                  <meshStandardMaterial color="#831843" roughness={0.7} />
                </mesh>
              ))}
            </group>
          ))}
        </group>
      )
    case 'universe':
      return (
        <group>
          <mesh position={[0, 0.18, 0]}>
            <cylinderGeometry args={[0.85, 0.88, 0.12, 24]} />
            <meshStandardMaterial color="#0f172a" />
          </mesh>
          <UniverseConstellation />
        </group>
      )
    case 'vault':
      return (
        <group>
          <mesh position={[0, 0.7, 0]}>
            <cylinderGeometry args={[0.5, 0.5, 1.1, 20, 1, true]} />
            <meshStandardMaterial color="#0284c7" transparent opacity={0.35} roughness={0.1} metalness={0.9} side={THREE.DoubleSide} />
          </mesh>
          {([0.35, 0.57, 0.79, 1.01]).map((ry) => (
            <mesh key={ry} position={[0, ry, 0]} rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[0.5, 0.025, 8, 32]} />
              <meshBasicMaterial color="#38bdf8" />
            </mesh>
          ))}
          {Array.from({ length: 6 }, (_, a) => (a / 6) * Math.PI * 2).map((ba) => (
            <mesh key={ba} position={[Math.cos(ba) * 0.72, 0.62, Math.sin(ba) * 0.72]} rotation={[0, -ba, 0]}>
              <boxGeometry args={[0.09, 1.0, 0.25]} />
              <meshStandardMaterial color="#0c4a6e" metalness={0.8} roughness={0.4} />
            </mesh>
          ))}
        </group>
      )
    case 'production':
      return (
        <group>
          <mesh position={[0, 0.32, 0]} rotation={[0, -Math.PI * 0.6, 0]}>
            <cylinderGeometry args={[0.88, 0.88, 0.28, 20, 1, false, 0, Math.PI * 1.2]} />
            <meshStandardMaterial color="#134e4a" metalness={0.8} roughness={0.3} />
          </mesh>
          {([-0.45, 0, 0.45]).map((ox) => (
            <mesh key={ox} position={[ox, 0.62, -0.28 + Math.abs(ox) * 0.12]}>
              <boxGeometry args={[0.38, 0.25, 0.03]} />
              <meshBasicMaterial color="#2dd4bf" />
            </mesh>
          ))}
          {([-0.22, 0.22]).map((cx) => (
            <mesh key={cx} position={[cx, 0.32, 0.25]}>
              <boxGeometry args={[0.25, 0.38, 0.25]} />
              <meshStandardMaterial color="#042f2e" />
            </mesh>
          ))}
        </group>
      )
    case 'integrity':
      return (
        <group>
          {([-0.55, 0, 0.55]).map((gx) => (
            <group key={gx}>
              <mesh position={[gx, 0.62, -0.55]}>
                <boxGeometry args={[0.32, 1.0, 0.55]} />
                <meshStandardMaterial color="#064e3b" metalness={0.8} roughness={0.4} />
              </mesh>
              {([0.35, 0.5, 0.65, 0.8]).map((ly) => (
                <mesh key={ly} position={[gx, ly, -0.27]}>
                  <boxGeometry args={[0.22, 0.025, 0.02]} />
                  <meshBasicMaterial color="#34d399" />
                </mesh>
              ))}
            </group>
          ))}
          {([0.35, 0.55, 0.75]).map((lz) => (
            <mesh key={lz} position={[0, lz, 0.1]} rotation={[0, 0, Math.PI / 2]}>
              <cylinderGeometry args={[0.012, 0.012, 1.35]} />
              <meshBasicMaterial color="#10b981" />
            </mesh>
          ))}
        </group>
      )
    case 'reference': {
      const moods = ['#f43f5e', '#fb7185', '#f472b6', '#c084fc', '#38bdf8']
      return (
        <group>
          <mesh position={[0, 0.8, -0.85]}>
            <boxGeometry args={[1.85, 1.05, 0.09]} />
            <meshStandardMaterial color="#201524" />
          </mesh>
          {moods.map((mcol, mi) => (
            <mesh key={mcol} position={[-0.62 + mi * 0.31, 0.82, -0.79]}>
              <boxGeometry args={[0.28, 0.44, 0.025]} />
              <meshStandardMaterial color={mcol} />
            </mesh>
          ))}
          <mesh position={[0.62, 0.55, 0.2]}>
            <cylinderGeometry args={[0.02, 0.03, 0.62]} />
            <meshStandardMaterial color="#1e293b" />
          </mesh>
          <mesh position={[0.62, 0.9, 0.2]} rotation={[0, -0.5, 0]}>
            <boxGeometry args={[0.38, 0.5, 0.19]} />
            <meshStandardMaterial color="#0f172a" />
          </mesh>
          <mesh position={[0.54, 0.9, 0.3]} rotation={[0, -0.5, 0]}>
            <boxGeometry args={[0.36, 0.48, 0.02]} />
            <meshBasicMaterial color="#ffffff" />
          </mesh>
        </group>
      )
    }
    default:
      // project: focus enclave workstation with dual monitors
      return (
        <group>
          <mesh position={[0, 0.72, -0.85]}>
            <boxGeometry args={[1.8, 0.95, 0.09]} />
            <meshStandardMaterial color="#1e1533" />
          </mesh>
          <mesh position={[0, 0.32, -0.18]}>
            <boxGeometry args={[1.35, 0.25, 0.55]} />
            <meshStandardMaterial color="#2e1065" />
          </mesh>
          {([-0.37, 0.37]).map((dx) => (
            <mesh key={dx} position={[dx, 0.62, -0.22]}>
              <boxGeometry args={[0.44, 0.28, 0.03]} />
              <meshBasicMaterial color={color} />
            </mesh>
          ))}
        </group>
      )
  }
}

class RoomMeshBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { failed: false }
  }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    if (this.state.failed) return null
    return this.props.children
  }
}

/** Dedicated Blender room mesh (studio_lobby.glb) rendered additively over the procedural stage. */
function StudioRoomMesh({ url }: { url: string }) {
  const { scene } = useGLTF(url)
  const primed = useMemo(() => {
    const clone = scene.clone()
    clone.traverse((child) => {
      const mesh = child as THREE.Mesh
      if (mesh.isMesh) {
        mesh.castShadow = true
        mesh.receiveShadow = true
      }
    })
    return clone
  }, [scene])
  return <primitive object={primed} position={[0, 0, 0]} />
}

/** Single room bay: steel platform, LED rim, corner stanchions, bespoke prop, tag banner. */
function RoomBay({
  portal,
  dimmed,
  onSelect,
  onHover,
}: {
  portal: SpatialPortal
  dimmed: boolean
  onSelect: (portal: SpatialPortal) => void
  onHover: (key: string | null) => void
}) {
  const [hovered, setHovered] = useState(false)
  const frame = useRef<THREE.Group>(null)
  const veil = useRef<THREE.Mesh>(null)
  const rotationY = portalRotation(portal.position)

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    if (veil.current) {
      const material = veil.current.material as THREE.MeshBasicMaterial
      material.opacity = dimmed ? 0.04 : hovered ? 0.3 + Math.sin(t * 4) * 0.06 : 0.12
    }
    if (frame.current) {
      const s = hovered ? 1.08 : 1
      frame.current.scale.lerp(new THREE.Vector3(s, s, s), 0.12)
    }
  })

  const activate = () => onSelect(portal)

  return (
    <group position={portal.position} rotation={[0, rotationY, 0]}>
      {/* Glowing violet ring anchored beneath the bay */}
      <mesh position={[0, 0.03, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[1.35, 1.55, 48]} />
        <meshBasicMaterial
          color={PORTAL_GLOW_VIOLET}
          transparent
          opacity={dimmed ? 0.06 : 0.3}
          side={THREE.DoubleSide}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
      <group ref={frame}>
        {/* Steel base plate */}
        <mesh position={[0, 0.1, 0]} castShadow receiveShadow>
          <boxGeometry args={[2.2, 0.14, 2.2]} />
          <meshStandardMaterial color="#120c22" roughness={0.3} metalness={0.8} />
        </mesh>
        {/* LED skirting rim */}
        <mesh position={[0, 0.18, 0]}>
          <boxGeometry args={[2.24, 0.03, 2.24]} />
          <meshBasicMaterial color={portal.color} transparent opacity={dimmed ? 0.15 : 0.9} />
        </mesh>
        {/* Corner stanchions */}
        {[[-1.02, -1.02], [1.02, -1.02], [-1.02, 1.02], [1.02, 1.02]].map(([cx, cz]) => (
          <group key={`${cx}${cz}`}>
            <mesh position={[cx, 0.32, cz]}>
              <cylinderGeometry args={[0.025, 0.025, 0.38, 8]} />
              <meshStandardMaterial color="#475569" metalness={0.9} roughness={0.35} />
            </mesh>
            <mesh position={[cx, 0.52, cz]}>
              <sphereGeometry args={[0.038, 10, 10]} />
              <meshBasicMaterial color={portal.color} />
            </mesh>
          </group>
        ))}
        <RoomProp roomKey={portal.key} color={portal.color} />
        {/* Illuminated interaction veil */}
        <mesh
          ref={veil}
          position={[0, 0.75, 0.35]}
          onClick={(event) => {
            event.stopPropagation()
            activate()
          }}
          onPointerOver={(event) => {
            event.stopPropagation()
            document.body.style.cursor = 'pointer'
            setHovered(true)
            onHover(portal.key)
          }}
          onPointerOut={() => {
            document.body.style.cursor = 'auto'
            setHovered(false)
            onHover(null)
          }}
        >
          <planeGeometry args={[2.2, 1.7]} />
          <meshBasicMaterial color={portal.color} transparent opacity={0.12} side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
        {/* Generous invisible hit target */}
        <mesh
          position={[0, 0.75, 0.4]}
          onClick={(event) => {
            event.stopPropagation()
            activate()
          }}
          onPointerOver={(event) => {
            event.stopPropagation()
            setHovered(true)
            onHover(portal.key)
          }}
          onPointerOut={() => {
            setHovered(false)
            onHover(null)
          }}
        >
          <planeGeometry args={[2.7, 2.2]} />
          <meshBasicMaterial transparent opacity={0} depthWrite={false} side={THREE.DoubleSide} />
        </mesh>
        {/* Floating tag banner: name + sub (tactical studio signage) */}
        <Html center position={[0, 1.95, 0]} zIndexRange={[20, 0]} style={{ pointerEvents: 'auto' }}>
          <button
            type="button"
            data-testid={`spatial-portal-${portal.key}`}
            onClick={activate}
            aria-label={`Open ${portal.label}`}
            className="w-[132px] cursor-pointer rounded-lg border px-2 py-1 text-center backdrop-blur-md transition-all duration-200"
            style={{
              background: hovered ? 'rgba(8,4,18,0.94)' : 'rgba(8,4,18,0.8)',
              borderColor: hovered ? portal.color : 'rgba(255,255,255,0.14)',
              borderWidth: 1,
              boxShadow: hovered ? `0 0 22px ${portal.color}66` : '0 8px 24px rgba(0,0,0,0.5)',
              opacity: dimmed ? 0.45 : 1,
            }}
          >
            <span className="block text-[11px] font-bold uppercase tracking-[0.14em] text-zinc-100" style={{ fontFamily: 'monospace' }}>
              {portal.label}
            </span>
            <span className="mt-0.5 block text-[10px] leading-tight" style={{ color: portal.color, fontFamily: 'monospace' }}>
              {portal.sub}
            </span>
          </button>
        </Html>
      </group>
    </group>
  )
}

/** Pulsing laser conduits: static violet lines + animated packets from dais to bays. */
function LaserConduits() {
  const pulses = useRef<THREE.Group>(null)
  const packetData = useMemo(
    () =>
      SPATIAL_PORTALS.map((portal, i) => ({
        angle: portal.angle,
        start: 1.9,
        end: PORTAL_RADIUS - 1.2,
        speed: 0.22 + ((i * 37) % 10) * 0.01,
        offset: (i * 0.37) % 1,
      })),
    [],
  )
  const lineGeoms = useMemo(
    () =>
      SPATIAL_PORTALS.map((portal) => {
        const pts = [
          new THREE.Vector3(Math.cos(portal.angle) * 1.9, 0.25, Math.sin(portal.angle) * 1.9),
          new THREE.Vector3(Math.cos(portal.angle) * (PORTAL_RADIUS - 1.2), 0.12, Math.sin(portal.angle) * (PORTAL_RADIUS - 1.2)),
        ]
        return new THREE.BufferGeometry().setFromPoints(pts)
      }),
    [],
  )
  useFrame(({ clock }) => {
    if (!pulses.current) return
    const t = clock.getElapsedTime()
    pulses.current.children.forEach((child, i) => {
      const d = packetData[i]
      const u = (t * d.speed + d.offset) % 1.0
      const dist = d.start + u * (d.end - d.start)
      child.position.set(Math.cos(d.angle) * dist, 0.25 + Math.sin(u * Math.PI) * 0.12, Math.sin(d.angle) * dist)
    })
  })
  return (
    <group>
      {lineGeoms.map((geom, i) => (
        // DEFERRED: SVG <line> typing; resolve in 3D studio redesign (post-roadmap)
        // NOTE: @ts-expect-error masks ALL errors on the next line; recheck line 827 when the 3D redesign lands.
        // @ts-expect-error
        <line key={SPATIAL_PORTALS[i].key} geometry={geom}>
          <lineBasicMaterial color="#a855f7" transparent opacity={0.7} />
        </line>
      ))}
      <group ref={pulses}>
        {packetData.map((_, i) => (
          <mesh key={SPATIAL_PORTALS[i].key}>
            <sphereGeometry args={[0.07, 10, 10]} />
            <meshBasicMaterial color="#d8b4fe" />
          </mesh>
        ))}
      </group>
    </group>
  )
}

export interface SpatialStudioCanvasProps {
  onSelectRoom?: (portal: SpatialPortal) => void
  onNavigate?: (to: string) => void
  activeRoom?: string | null
  /** Custom room mesh URL. Defaults to the Blender lobby export when present; pass null to force procedural-only. */
  roomModelUrl?: string | null
}

/**
 * Primary 3D background viewport contents: obsidian circular floor grid,
 * concentric neon rings, industrial truss rig, FF monogram pedestal with
 * orbiting rings, 12 bespoke room bays with LED rims + tag banners,
 * pulsing laser conduits, and violet ambient dust.
 * Must be rendered inside a React Three Fiber <Canvas>.
 */
export default function SpatialStudioCanvas({ onSelectRoom, onNavigate, activeRoom, roomModelUrl = STUDIO_LOBBY_MODEL_URL }: SpatialStudioCanvasProps) {
  const [hoveredKey, setHoveredKey] = useState<string | null>(activeRoom ?? null)
  const centerGlow = useRef<THREE.PointLight | null>(null)

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    if (centerGlow.current) {
      centerGlow.current.intensity = 26 + Math.sin(t * 3.0) * 8
    }
  })

  const handleSelect = (portal: SpatialPortal) => {
    onSelectRoom?.(portal)
    onNavigate?.(portal.to)
  }

  return (
    <group>
      <color attach="background" args={['#05020a']} />
      {/* Deepened volumetric fog: near haze holds the violet key, far falloff swallows the room edge */}
      <fog attach="fog" args={['#05020a', 10, 38]} />
      <StudioLighting centerRef={centerGlow} />
      <ObsidianFloor />
      <LightingTrusses />
      <AmbientDust />
      {roomModelUrl ? (
        <RoomMeshBoundary>
          <Suspense fallback={null}>
            <StudioRoomMesh url={roomModelUrl} />
          </Suspense>
        </RoomMeshBoundary>
      ) : null}
      <FFMonogramPedestal />
      <LaserConduits />
      {SPATIAL_PORTALS.map((portal) => (
        <RoomBay
          key={portal.key}
          portal={portal}
          dimmed={hoveredKey !== null && hoveredKey !== portal.key}
          onSelect={(p) => {
            setHoveredKey(p.key)
            handleSelect(p)
          }}
          onHover={setHoveredKey}
        />
      ))}
    </group>
  )
}
