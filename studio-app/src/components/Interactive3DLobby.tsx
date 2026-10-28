import { Component, Suspense, useEffect, useRef, useState, type ReactNode } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Environment, OrbitControls, useGLTF } from '@react-three/drei'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import SpatialStudioCanvas from './SpatialStudioCanvas'
import { SPATIAL_PORTALS } from '../lib/spatialPortals'
import { LOBBY_MODEL_URL, LOBBY_ROOMS, isLobbyModelAvailable } from '../lib/lobbyRooms'
import { getProceduralRoomStyle } from '../lib/proceduralBackdrops'

/** Renders a user-supplied GLB/GLTF lobby model. Must sit inside Suspense + error boundary. */
function LobbyCustomModel({ url }: { url: string }) {
  const { scene } = useGLTF(url)
  return <primitive object={scene} position={[0, 0, 0]} />
}

class LobbyModelErrorBoundary extends Component<{ children: ReactNode; onError?: () => void }, { failed: boolean }> {
  constructor(props: { children: ReactNode; onError?: () => void }) {
    super(props)
    this.state = { failed: false }
  }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch() {
    this.props.onError?.()
  }
  render() {
    if (this.state.failed) return null
    return this.props.children
  }
}

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

const HOME_POSITION: [number, number, number] = [0, 2.6, 10.5]
const HOME_TARGET: [number, number, number] = [0, 1, 0]

/** Listens for tactical-dock `recenter-stage` / `focus-room` window events. */
function CameraRig({ controlsRef, onNavigate }: { controlsRef: React.RefObject<OrbitControlsImpl | null>; onNavigate: (to: string) => void }) {
  const { camera } = useThree()
  // Gentle idle drift toward pointer (tilt mechanic) without fighting OrbitControls.
  const pointer = useRef({ x: 0, y: 0 })
  useEffect(() => {
    const move = (e: MouseEvent) => {
      pointer.current = {
        x: (e.clientX / window.innerWidth) * 2 - 1,
        y: -((e.clientY / window.innerHeight) * 2 - 1),
      }
    }
    window.addEventListener('mousemove', move)
    return () => window.removeEventListener('mousemove', move)
  }, [])
  useFrame((state) => {
    // Read the camera from the frame state rather than mutating the value
    // returned by useThree() — React Compiler forbids modifying hook results.
    state.camera.rotation.z += (pointer.current.x * 0.01 - state.camera.rotation.z) * 0.02
  })
  useEffect(() => {
    const recenter = () => {
      camera.position.set(...HOME_POSITION)
      controlsRef.current?.target.set(...HOME_TARGET)
      controlsRef.current?.update()
    }
    const focus = (e: Event) => {
      const roomId = (e as CustomEvent<{ roomId: string }>).detail?.roomId
      if (!roomId) return
      const portal = SPATIAL_PORTALS.find((p) => p.key === roomId)
      const room = LOBBY_ROOMS.find((r) => r.id === roomId)
      if (portal) {
        const [px, , pz] = portal.position
        const len = Math.hypot(px, pz) || 1
        camera.position.set((px / len) * 4.2, 2.2, (pz / len) * 4.2)
        controlsRef.current?.target.set(px * 0.55, 0.8, pz * 0.55)
        controlsRef.current?.update()
      }
      if (room) onNavigate(room.to)
    }
    window.addEventListener('recenter-stage', recenter)
    window.addEventListener('focus-room', focus)
    return () => {
      window.removeEventListener('recenter-stage', recenter)
      window.removeEventListener('focus-room', focus)
    }
  }, [camera, controlsRef, onNavigate])
  return null
}

function LobbyScene({ onNavigate, modelAvailable }: { onNavigate: (to: string) => void; modelAvailable: boolean }) {
  const [modelFailed, setModelFailed] = useState(false)
  const controlsRef = useRef<OrbitControlsImpl | null>(null)
  const showCustomModel = modelAvailable && !modelFailed
  return (
    <>
      {/* Primary background viewport: tactical Fee Fee Anne soundstage.
          Owns the obsidian floor grid, neon rings, truss rig, FF pedestal,
          and 12 bespoke room bays with laser conduits. */}
      <SpatialStudioCanvas onNavigate={onNavigate} roomModelUrl={null} />
      {/* Custom Blender export (GLB/GLTF) with HDRI environment lighting when available. */}
      {showCustomModel && (
        <LobbyModelErrorBoundary onError={() => setModelFailed(true)}>
          <Suspense fallback={null}>
            <LobbyCustomModel url={LOBBY_MODEL_URL} />
            <Environment preset="city" />
          </Suspense>
        </LobbyModelErrorBoundary>
      )}
      <CameraRig controlsRef={controlsRef} onNavigate={onNavigate} />
      <OrbitControls
        ref={controlsRef}
        makeDefault
        enableDamping
        dampingFactor={0.12}
        enablePan={false}
        enableZoom
        minDistance={4}
        maxDistance={18}
        minPolarAngle={Math.PI * 0.15}
        maxPolarAngle={Math.PI * 0.55}
        target={HOME_TARGET}
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
  const [modelAvailable, setModelAvailable] = useState(false)

  useEffect(() => {
    let cancelled = false
    void isLobbyModelAvailable().then((ok) => {
      if (!cancelled && ok) {
        // Warm the drei GLTF cache only after HEAD confirms the file exists,
        // so missing-file deployments never trigger a loader error.
        useGLTF.preload(LOBBY_MODEL_URL)
        setModelAvailable(true)
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  const fallbackBackdrop = getProceduralRoomStyle('atrium')

  if (!webglAvailable) {
    return (
      <div
        data-testid="lobby-3d-fallback"
        role="status"
        className="grid min-h-[420px] h-full place-items-center p-8 text-center"
        style={{ background: fallbackBackdrop.background }}
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

  const focusRoom = (id: string) => {
    window.dispatchEvent(new CustomEvent('focus-room', { detail: { roomId: id } }))
  }
  const recenter = () => {
    window.dispatchEvent(new CustomEvent('recenter-stage'))
  }

  // Foreground quick-nav mirrors the spatial bays so every room stays
  // reachable even if WebGL picking is imprecise.
  const quickRoutes = [
    { label: 'Atrium', id: 'atrium' },
    { label: 'Previs', id: 'previs' },
    { label: 'Screening', id: 'screening' },
    { label: 'Vault', id: 'vault' },
    { label: 'Integrity', id: 'integrity' },
  ]

  return (
    <div data-testid="lobby-3d-canvas" className="relative h-full min-h-[420px] w-full overflow-hidden bg-[#05020a]">
      {/* Primary 3D viewport — explicit ids bind the ANIMATION_8 stage to its
          flex parent so the renderer never measures zero dimensions. */}
      <div id="threejs-container-ANIMATION_8" className="absolute inset-0 h-full w-full" style={{ pointerEvents: 'auto' }}>
        <Canvas
          camera={{ position: HOME_POSITION, fov: 48 }}
          dpr={[1, 1.75]}
          shadows
          gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }}
          style={{ width: '100%', height: '100%', display: 'block' }}
        >
          <Suspense fallback={null}>
            <LobbyScene onNavigate={onNavigate} modelAvailable={modelAvailable} />
          </Suspense>
        </Canvas>
      </div>
      {/* Probe for tests/e2e: procedural fallback always mounted; custom model is additive. */}
      <span data-testid="lobby-3d-model-status" data-available={modelAvailable ? 'true' : 'false'} className="hidden" />
      {/* HUD tactical viewport overlay */}
      <div className="pointer-events-none absolute left-4 top-3 z-10 flex items-center space-x-3 rounded border border-purple-900/40 bg-black/40 px-2.5 py-1.5 font-mono text-[10px] tracking-widest text-purple-400/80 backdrop-blur-sm">
        <span className="h-1.5 w-1.5 animate-ping rounded-full bg-cyan-400" />
        <span>DRAG TO ROTATE 3D LOBBY • SCROLL TO ZOOM • HOVER ROOM BAYS</span>
      </div>
      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between bg-gradient-to-b from-[#05020a]/85 to-transparent p-4 pt-12">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.25em] text-violet-200/90">Fee Fee Anne Studios · 3D Lobby</div>
          <p className="mt-1 max-w-[240px] text-[11px] leading-5 text-zinc-400">
            Drift to orbit · Scroll to zoom · Walk through a glowing bay to enter
          </p>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-500">{LOBBY_ROOMS.length} rooms</span>
      </div>
      {/* Cinematic vignette — never intercepts pointer events. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(circle at center, transparent 52%, rgba(0,0,0,0.5) 100%)' }}
      />
      {/* Corner framing brackets */}
      <div aria-hidden="true" className="pointer-events-none absolute right-2 top-2 z-10 h-3 w-3 border-r-2 border-t-2 border-purple-500/40" />
      <div aria-hidden="true" className="pointer-events-none absolute bottom-8 left-2 z-10 h-3 w-3 border-b-2 border-l-2 border-purple-500/40" />
      {/* Quick room presets */}
      <div className="absolute bottom-10 left-4 z-10 flex items-center space-x-1.5 rounded border border-purple-950 bg-[#070312]/80 p-1.5 font-mono text-[10px] text-purple-300/70 backdrop-blur">
        <span className="px-1 font-semibold text-purple-400">PRESETS:</span>
        {quickRoutes.map((route) => (
          <button
            key={route.id}
            type="button"
            data-testid={`lobby-quick-nav-${route.label.toLowerCase()}`}
            onClick={() => focusRoom(route.id)}
            className="cursor-pointer rounded px-2 py-0.5 transition hover:bg-purple-900/60 hover:text-white"
          >
            {route.label.toUpperCase()}
          </button>
        ))}
        <button
          type="button"
          onClick={recenter}
          className="rounded border border-purple-700/60 bg-purple-950/80 px-2 py-0.5 font-bold text-purple-200 transition hover:border-purple-400"
        >
          RE-CENTER
        </button>
      </div>
      {/* Bottom status bar */}
      <div className="absolute inset-x-0 bottom-0 z-10 flex h-7 items-center justify-between border-t border-purple-950/70 bg-[#05020b]/90 px-4 font-mono text-[10px] tracking-wider text-purple-400/60">
        <div className="flex items-center space-x-3">
          <span className="flex h-3 w-3 items-center justify-center border border-purple-800 text-[8px] text-purple-300">L</span>
          <span>897.by 42.680</span>
          <span className="text-purple-900">|</span>
          <span className="text-purple-300/80">QUANTUM SECURITY STRINGS</span>
          <span className="text-purple-900">|</span>
          <span>HASH: 09F41-EE06-CC02</span>
        </div>
        <div className="flex items-center space-x-2">
          <span>SYNC:</span>
          <span className="text-purple-300">studio.db</span>
          <span className="font-bold text-purple-400">[ISOLATED]</span>
        </div>
      </div>
    </div>
  )
}
