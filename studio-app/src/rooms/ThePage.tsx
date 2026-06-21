import { Canvas, useFrame } from '@react-three/fiber'
import { useRef, useMemo } from 'react'
import { PerspectiveCamera } from '@react-three/drei'
import { EffectComposer, Bloom, Vignette, ChromaticAberration } from '@react-three/postprocessing'
import { Vector2 } from 'three'
import * as THREE from 'three'

// Floating ash/dust particles — slow, heavy, like disturbed paper dust
function AshParticles() {
  const ref = useRef<THREE.Points>(null)
  const count = 180

  const { positions, phases, speeds } = useMemo(() => {
    const positions = new Float32Array(count * 3)
    const phases = new Float32Array(count)
    const speeds = new Float32Array(count)
    for (let i = 0; i < count; i++) {
      positions[i * 3]     = (Math.random() - 0.5) * 14
      positions[i * 3 + 1] = (Math.random() - 0.5) * 8
      positions[i * 3 + 2] = (Math.random() - 0.5) * 10
      phases[i] = Math.random() * Math.PI * 2
      speeds[i] = 0.0002 + Math.random() * 0.0004
    }
    return { positions, phases, speeds }
  }, [])

  useFrame(({ clock }) => {
    if (!ref.current) return
    const t = clock.getElapsedTime()
    const pos = ref.current.geometry.attributes.position.array as Float32Array
    for (let i = 0; i < count; i++) {
      const phase = phases[i]
      const speed = speeds[i]
      pos[i * 3]     += Math.sin(t * speed * 0.7 + phase) * 0.003
      pos[i * 3 + 1] += speed * 0.8 // very slow upward drift
      pos[i * 3 + 2] += Math.cos(t * speed + phase * 1.4) * 0.002
      // Wrap when drifted too far
      if (pos[i * 3 + 1] > 4) pos[i * 3 + 1] = -4
    }
    ref.current.geometry.attributes.position.needsUpdate = true
  })

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.022}
        color="#c8924a"
        transparent
        opacity={0.25}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  )
}

// The desk — dark volcanic glass surface, partially visible at bottom of frame
function WriterDesk() {
  return (
    <group position={[0, -2.8, 0]}>
      {/* Desk surface */}
      <mesh receiveShadow>
        <boxGeometry args={[6, 0.06, 3.5]} />
        <meshStandardMaterial
          color="#0d0b08"
          roughness={0.3}
          metalness={0.6}
        />
      </mesh>
      {/* Scattered papers — subtle white planes at slight angles */}
      <mesh position={[-0.4, 0.04, 0.2]} rotation={[0, 0.15, 0]}>
        <planeGeometry args={[1.1, 0.85]} />
        <meshStandardMaterial color="#f0ead6" roughness={0.9} />
      </mesh>
      <mesh position={[0.5, 0.04, -0.1]} rotation={[0, -0.08, 0]}>
        <planeGeometry args={[1.1, 0.85]} />
        <meshStandardMaterial color="#ede6d0" roughness={0.9} />
      </mesh>
      <mesh position={[-0.1, 0.035, -0.3]} rotation={[0, 0.22, 0]}>
        <planeGeometry args={[1.1, 0.85]} />
        <meshStandardMaterial color="#f5eedc" roughness={0.9} />
      </mesh>
    </group>
  )
}

// Desk lamp — the signature element, a practical amber light source
function DeskLamp() {
  return (
    <group position={[2.2, -1.4, -0.8]}>
      {/* Lamp base */}
      <mesh castShadow>
        <cylinderGeometry args={[0.12, 0.18, 0.08, 12]} />
        <meshStandardMaterial color="#1a1510" roughness={0.8} metalness={0.4} />
      </mesh>
      {/* Lamp arm */}
      <mesh position={[0, 0.55, 0]} castShadow>
        <cylinderGeometry args={[0.025, 0.025, 1.1, 8]} />
        <meshStandardMaterial color="#1a1510" roughness={0.7} metalness={0.5} />
      </mesh>
      {/* Lamp shade */}
      <mesh position={[0, 1.15, 0]} castShadow>
        <coneGeometry args={[0.28, 0.32, 16, 1, true]} />
        <meshStandardMaterial
          color="#c8824a"
          roughness={0.6}
          side={THREE.DoubleSide}
          emissive="#c8824a"
          emissiveIntensity={0.15}
        />
      </mesh>
    </group>
  )
}

function SceneContents() {
  return (
    <>
      <color attach="background" args={['#06050302']} />
      <fog attach="fog" args={['#080604', 8, 22]} />

      <PerspectiveCamera makeDefault position={[0, 0.5, 7]} fov={58} />

      {/* Near-black ambient — barely any fill, room is dark */}
      <ambientLight intensity={0.04} color="#3a2a1a" />

      {/* THE signature light — warm practical lamp, key source */}
      <pointLight
        position={[2.2, -0.3, -0.8]}
        intensity={18}
        color="#d4884a"
        distance={8}
        decay={2}
        castShadow
      />

      {/* Subtle screen/page bounce — cold fill from slightly forward */}
      <pointLight
        position={[-1.2, -1.8, 2]}
        intensity={1.2}
        color="#c4b8a0"
        distance={5}
        decay={2}
      />

      {/* Ceiling — deep dark, barely visible */}
      <mesh position={[0, 5, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <planeGeometry args={[20, 20]} />
        <meshStandardMaterial color="#05040300" roughness={1} />
      </mesh>

      {/* Back wall — deep shadow */}
      <mesh position={[0, 0, -7]}>
        <planeGeometry args={[20, 16]} />
        <meshStandardMaterial color="#06050300" roughness={1} />
      </mesh>

      {/* Side walls */}
      <mesh position={[-7, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
        <planeGeometry args={[20, 16]} />
        <meshStandardMaterial color="#07060400" roughness={1} />
      </mesh>
      <mesh position={[7, 0, 0]} rotation={[0, -Math.PI / 2, 0]}>
        <planeGeometry args={[20, 16]} />
        <meshStandardMaterial color="#07060400" roughness={1} />
      </mesh>

      <WriterDesk />
      <DeskLamp />
      <AshParticles />

      <EffectComposer>
        <Bloom
          luminanceThreshold={0.15}
          luminanceSmoothing={0.85}
          intensity={2.2}
        />
        <Vignette eskil={false} offset={0.2} darkness={1.1} />
        <ChromaticAberration
          offset={new Vector2(0.0008, 0.0008)}
          radialModulation={false}
          modulationOffset={0}
        />
      </EffectComposer>
    </>
  )
}

export function PageScene() {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        pointerEvents: 'none',
      }}
    >
      <Canvas
        shadows
        gl={{ antialias: true, alpha: false }}
        style={{ width: '100%', height: '100%' }}
      >
        <SceneContents />
      </Canvas>
    </div>
  )
}