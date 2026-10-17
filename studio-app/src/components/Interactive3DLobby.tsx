import { Suspense, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Grid, Html, OrbitControls, Stars } from '@react-three/drei'
import * as THREE from 'three'

export interface LobbyRoom {
  id: string
  label: string
  description: string
  to: string
  color: string
  position: [number, number, number]
}

const RADIUS = 5.2

function polar(index: number, total: number, y: number): [number, number, number] {
  const angle = (index / total) * Math.PI * 2 - Math.PI / 2
  return [Math.cos(angle) * RADIUS, y, Math.sin(angle) * RADIUS]
}

// Additive spatial directory. Routes mirror the existing 2D room paths in
// studio-app/src/routes.tsx exactly — no room load logic is touched.
export const LOBBY_ROOMS: LobbyRoom[] = [
  { id: 'production-desk', label: 'Production Desk', description: 'Status, blockers and delivery evidence', to: '/studio/production-desk', color: '#e8a020', position: polar(0, 9, 1.1) },
  { id: 'reference-space', label: 'Reference Space', description: 'Canonical character and setting references', to: '/studio/reference-space', color: '#7ad6d1', position: polar(1, 9, 1.5) },
  { id: 'previs', label: 'Previs Bay', description: 'Scenes, shots and approvals before rendering', to: '/studio/previs', color: '#d6a95c', position: polar(2, 9, 1.0) },
  { id: 'integrity', label: 'Integrity Engine', description: 'Verification console for blockers and provenance', to: '/studio/integrity', color: '#9f8dc5', position: polar(3, 9, 1.6) },
  { id: 'universe', label: 'Universe', description: 'Characters, locations, lore and objects', to: '/studio/universe-graph', color: '#38b2c8', position: polar(4, 9, 1.1) },
  { id: 'board', label: 'Board', description: 'Scene execution and stage-state monitoring', to: '/studio/production-board', color: '#78b38a', position: polar(5, 9, 1.5) },
  { id: 'writers-room', label: "Writer's Room", description: 'Story structure, beats and continuity intent', to: '/studio/writers-room', color: '#d08383', position: polar(6, 9, 1.0) },
  { id: 'screening-room', label: 'Screening Room', description: 'Playback and review of scene cuts', to: '/studio/screening-room', color: '#5b8dd9', position: polar(7, 9, 1.4) },
  { id: 'overview', label: 'Overview', description: 'Film health, risks and room progress', to: '/studio/overview', color: '#e8edf5', position: polar(8, 9, 1.2) },
]

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('webgl2') ?? canvas.getContext('webgl')
    if (!context) return false
    const lose = (context as WebGLRenderingContext).getExtension('WEBGL_lose_context')
    lose?.loseContext()
    return true
  } catch {
    return false
  }
}

function CameraParallax() {
  const { camera, pointer } = useThree()
  useFrame(() => {
    const targetX = pointer.x * 0.6
    const targetY = 2.6 + pointer.y * 0.4
    camera.position.x += (targetX - camera.position.x) * 0.03
    camera.position.y += (targetY - camera.position.y) * 0.03
    camera.lookAt(0, 1, 0)
  })
  return null
}

function FloatingMarker({ children, position }: { children: React.ReactNode; position: [number, number, number] }) {
  const group = useRef<THREE.Group>(null)
  useFrame(({ clock }) => {
    if (!group.current) return
    const t = clock.getElapsedTime()
    group.current.position.y = position[1] + Math.sin(t * 0.9 + position[0]) * 0.12
  })
  return <group ref={group} position={position}>{children}</group>
}

function RoomNode({
  room,
  dimmed,
  onNavigate,
  onHover,
}: {
  room: LobbyRoom
  dimmed: boolean
  onNavigate: (to: string) => void
  onHover: (id: string | null) => void
}) {
  const [hovered, setHovered] = useState(false)
  const mesh = useRef<THREE.Mesh>(null)
  const glow = useRef<THREE.Mesh>(null)
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const s = hovered ? 1.35 : 1
    if (mesh.current) {
      mesh.current.scale.lerp(new THREE.Vector3(s, s, s), 0.15)
      mesh.current.rotation.y = t * (hovered ? 0.8 : 0.25)
    }
    if (glow.current) {
      const pulse = hovered ? 0.55 + Math.sin(t * 4) * 0.12 : 0.22
      const material = glow.current.material as THREE.MeshBasicMaterial
      material.opacity = dimmed ? 0.06 : pulse
    }
  })

  return (
    <FloatingMarker position={room.position}>
      {/* Emissive halo */}
      <mesh ref={glow}>
        <sphereGeometry args={[0.62, 24, 24]} />
        <meshBasicMaterial color={room.color} transparent opacity={0.22} depthWrite={false} />
      </mesh>
      {/* Core hotspot */}
      <mesh
        ref={mesh}
        onClick={(event) => {
          event.stopPropagation()
          onNavigate(room.to)
        }}
        onPointerOver={(event) => {
          event.stopPropagation()
          document.body.style.cursor = 'pointer'
          setHovered(true)
          onHover(room.id)
        }}
        onPointerOut={() => {
          document.body.style.cursor = 'auto'
          setHovered(false)
          onHover(null)
        }}
      >
        <octahedronGeometry args={[0.38, 0]} />
        <meshStandardMaterial
          color={room.color}
          metalness={0.55}
          roughness={0.3}
          emissive={room.color}
          emissiveIntensity={hovered ? 0.9 : dimmed ? 0.08 : 0.35}
        />
      </mesh>
      {/* Generous invisible hit target for touch */}
      <mesh
        onClick={(event) => {
          event.stopPropagation()
          onNavigate(room.to)
        }}
        onPointerOver={(event) => {
          event.stopPropagation()
          setHovered(true)
          onHover(room.id)
        }}
        onPointerOut={() => {
          setHovered(false)
          onHover(null)
        }}
      >
        <sphereGeometry args={[0.72, 8, 8]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      <Html center position={[0, -0.95, 0]} zIndexRange={[20, 0]} style={{ pointerEvents: 'auto' }}>
        <button
          type="button"
          data-testid={`lobby-3d-node-${room.id}`}
          onClick={() => onNavigate(room.to)}
          aria-label={`Open ${room.label}`}
          className="w-[132px] cursor-pointer rounded-lg border px-2 py-1.5 text-center backdrop-blur-md transition-all duration-200"
          style={{
            background: hovered ? 'rgba(8,12,20,0.92)' : 'rgba(7,10,16,0.78)',
            borderColor: hovered ? room.color : 'rgba(255,255,255,0.14)',
            boxShadow: hovered ? `0 0 22px ${room.color}55` : '0 8px 24px rgba(0,0,0,0.45)',
            opacity: dimmed ? 0.45 : 1,
          }}
        >
          <span className="block text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-100">{room.label}</span>
          <span className="mt-0.5 block text-[10px] leading-tight text-zinc-400">{room.description}</span>
        </button>
      </Html>
    </FloatingMarker>
  )
}

function Stage() {
  const ring = useRef<THREE.Mesh>(null)
  useFrame(({ clock }) => {
    if (ring.current) ring.current.rotation.z = clock.getElapsedTime() * 0.05
  })
  return (
    <group position={[0, 0, 0]}>
      {/* Central stage disc */}
      <mesh position={[0, -0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[2.1, 64]} />
        <meshStandardMaterial color="#0d1526" metalness={0.4} roughness={0.6} emissive="#e8a020" emissiveIntensity={0.05} />
      </mesh>
      {/* Rotating amber accent ring */}
      <mesh ref={ring} position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[2.14, 2.2, 96]} />
        <meshBasicMaterial color="#e8a020" transparent opacity={0.5} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      {/* Studio wordmark plinth */}
      <Html center position={[0, 0.55, 0]} zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
        <div className="text-center" aria-hidden="true">
          <div className="text-sm font-bold uppercase tracking-[0.4em] text-amber-200/90">Studio</div>
          <div className="mt-1 text-[10px] uppercase tracking-[0.25em] text-zinc-500">Select a room to enter</div>
        </div>
      </Html>
    </group>
  )
}

function LobbyScene({ onNavigate }: { onNavigate: (to: string) => void }) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  return (
    <>
      <color attach="background" args={['#040810']} />
      <fog attach="fog" args={['#040810', 12, 30]} />
      <ambientLight intensity={0.55} />
      {/* Warm amber key light + cool cyan rim, matching the studio palette */}
      <pointLight position={[0, 6, 4]} intensity={60} color="#e8a020" distance={30} />
      <directionalLight position={[-6, 4, -4]} intensity={1.4} color="#7ad6d1" />
      <directionalLight position={[6, 3, -2]} intensity={0.7} color="#d6a95c" />
      <Stars radius={60} depth={30} count={2200} factor={3} saturation={0} fade speed={0.4} />
      <Grid
        position={[0, -0.05, 0]}
        args={[30, 30]}
        cellSize={1}
        cellThickness={0.6}
        cellColor="#1a2744"
        sectionSize={5}
        sectionThickness={1}
        sectionColor="#2d4470"
        fadeDistance={26}
        fadeStrength={2}
        infiniteGrid
      />
      <Stage />
      {LOBBY_ROOMS.map((room) => (
        <RoomNode
          key={room.id}
          room={room}
          dimmed={hoveredId !== null && hoveredId !== room.id}
          onNavigate={onNavigate}
          onHover={setHoveredId}
        />
      ))}
      <CameraParallax />
      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.12}
        enablePan={false}
        enableZoom
        minDistance={5}
        maxDistance={16}
        minPolarAngle={Math.PI * 0.18}
        maxPolarAngle={Math.PI * 0.52}
        target={[0, 1, 0]}
      />
    </>
  )
}

export interface Interactive3DLobbyProps {
  onNavigate: (to: string) => void
}

export default function Interactive3DLobby({ onNavigate }: Interactive3DLobbyProps) {
  const [webglAvailable] = useState<boolean>(() =>
    typeof document === 'undefined' ? false : supportsWebGL(),
  )

  if (!webglAvailable) {
    return (
      <div
        data-testid="lobby-3d-fallback"
        role="status"
        className="grid min-h-[420px] place-items-center rounded-2xl border border-white/10 bg-[#080f1a] p-8 text-center"
      >
        <div className="max-w-sm">
          <div className="text-xs font-semibold uppercase tracking-[0.25em] text-amber-200/90">Studio Lobby</div>
          <p className="mt-3 text-sm leading-6 text-zinc-300">
            The 3D stage isn&apos;t available on this device. Every room stays open in the list view.
          </p>
          <div className="mt-5 grid grid-cols-2 gap-2">
            {LOBBY_ROOMS.map((room) => (
              <button
                key={room.id}
                type="button"
                data-testid={`lobby-3d-node-${room.id}`}
                onClick={() => onNavigate(room.to)}
                className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-left text-xs text-zinc-200 transition-colors hover:border-amber-200/40"
              >
                <span className="block font-semibold uppercase tracking-[0.1em]">{room.label}</span>
                <span className="mt-0.5 block text-[11px] text-zinc-500">{room.description}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div data-testid="lobby-3d-canvas" className="relative h-[560px] min-h-[420px] w-full overflow-hidden rounded-2xl border border-white/10 bg-[#040810]">
      <Canvas
        camera={{ position: [0, 2.6, 10.5], fov: 48 }}
        dpr={[1, 1.75]}
        gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }}
      >
        <Suspense fallback={null}>
          <LobbyScene onNavigate={onNavigate} />
        </Suspense>
      </Canvas>
      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between bg-gradient-to-b from-[#040810]/85 to-transparent p-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.25em] text-amber-200/90">3D Studio Lobby</div>
          <p className="mt-1 max-w-[240px] text-[11px] leading-5 text-zinc-400">
            Drift to orbit · Scroll to zoom · Select a glowing room to enter
          </p>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-500">{LOBBY_ROOMS.length} rooms</span>
      </div>
      {/* Cinematic vignette + grain, matching StudioShell atmosphere */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(circle at center, transparent 52%, rgba(0,0,0,0.5) 100%)' }}
      />
    </div>
  )
}
