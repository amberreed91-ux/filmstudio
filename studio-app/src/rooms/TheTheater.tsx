import { Canvas, useFrame } from '@react-three/fiber'
import { useRef } from 'react'
import { PerspectiveCamera } from '@react-three/drei'
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing'
import * as THREE from 'three'

function TheaterDust() {
  const ref = useRef<THREE.Points>(null)
  const count = 300
  const positions = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    positions[i * 3]     = (Math.random() - 0.5) * 12
    positions[i * 3 + 1] = Math.random() * 6 - 1
    positions[i * 3 + 2] = (Math.random() - 0.5) * 8
  }

  useFrame(({ clock }) => {
    if (!ref.current) return
    ref.current.rotation.y = Math.sin(clock.getElapsedTime() * 0.03) * 0.02
    const pos = ref.current.geometry.attributes.position.array as Float32Array
    for (let i = 0; i < count; i++) {
      pos[i * 3 + 1] += 0.0008
      if (pos[i * 3 + 1] > 5) pos[i * 3 + 1] = -1
    }
    ref.current.geometry.attributes.position.needsUpdate = true
  })

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.018}
        color="#ffe8a0"
        transparent
        opacity={0.6}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  )
}

function TheaterScreen({ videoUrl }: { videoUrl?: string }) {
  return (
    <group position={[0, 1.5, -6]}>
      <mesh>
        <boxGeometry args={[9.4, 5.4, 0.05]} />
        <meshStandardMaterial color="#111111" />
      </mesh>
      <mesh position={[0, 0, 0.06]}>
        <planeGeometry args={[9, 5]} />
        <meshStandardMaterial
          color={videoUrl ? '#ffffff' : '#0a0a0a'}
          emissive={videoUrl ? '#ffffff' : '#1a1a2e'}
          emissiveIntensity={videoUrl ? 0 : 0.8}
        />
      </mesh>
    </group>
  )
}

function TheaterSeats() {
  const rows = 3
  const seatsPerRow = 8
  const seats = []
  for (let row = 0; row < rows; row++) {
    for (let seat = 0; seat < seatsPerRow; seat++) {
      seats.push(
        <group
          key={`${row}-${seat}`}
          position={[
            (seat - seatsPerRow / 2 + 0.5) * 1.1,
            -1.2 + row * 0.3,
            2 + row * 1.4,
          ]}
        >
          <mesh position={[0, 0.3, 0]}>
            <boxGeometry args={[0.8, 0.7, 0.1]} />
            <meshStandardMaterial color="#2a2a4e" roughness={0.9} />
          </mesh>
          <mesh position={[0, 0, 0.2]} rotation={[-Math.PI / 4, 0, 0]}>
            <boxGeometry args={[0.8, 0.1, 0.6]} />
            <meshStandardMaterial color="#1e1e3a" roughness={0.9} />
          </mesh>
        </group>
      )
    }
  }
  return <group>{seats}</group>
}

function SceneContents({ videoUrl }: { videoUrl?: string }) {
  return (
    <>
      {/* Scene background color — critical for visibility */}
      <color attach="background" args={['#05050a']} />

      {/* Camera pulled back and raised for full theater view */}
      <PerspectiveCamera makeDefault position={[0, 2.5, 10]} fov={60} />


      {/* Ambient light boosted so all geometry is visible */}
      <ambientLight intensity={1.2} color="#8888cc" />

      {/* Main projector beam */}
      <spotLight
        position={[0, 10, 10]}
        target-position={[0, 1.8, -4]}
        intensity={12}
        angle={0.22}
        penumbra={0.4}
        color="#fff5e0"
        castShadow
      />

      {/* Screen glow fill */}
      <pointLight position={[0, 1.8, -3.5]} intensity={2.5} color="#7777ff" />

      {/* Accent lights for atmosphere */}
      <pointLight position={[-6, 1, 5]} intensity={2.5} color="#ff6040" />
      <pointLight position={[6, 1, 5]} intensity={2.5} color="#4060ff" />

      {/* Depth fog */}
      <fog attach="fog" args={['#05050a', 15, 40]} />

      {/* Floor — extended to fill view */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -2, 0]} receiveShadow>
        <planeGeometry args={[30, 30]} />
        <meshStandardMaterial color="#0c0c18" roughness={0.95} />
      </mesh>

      {/* Back wall — behind screen */}
      <mesh position={[0, 2.5, -8]}>
        <planeGeometry args={[30, 14]} />
        <meshStandardMaterial color="#0e0e1a" roughness={1} />
      </mesh>

      {/* Left wall */}
      <mesh position={[-10, 2.5, 0]} rotation={[0, Math.PI / 2, 0]}>
        <planeGeometry args={[30, 14]} />
        <meshStandardMaterial color="#0b0b16" roughness={1} />
      </mesh>

      {/* Right wall */}
      <mesh position={[10, 2.5, 0]} rotation={[0, -Math.PI / 2, 0]}>
        <planeGeometry args={[30, 14]} />
        <meshStandardMaterial color="#0b0b16" roughness={1} />
      </mesh>

      {/* Screen — closer to camera so it's prominently visible */}
      <TheaterScreen videoUrl={videoUrl} />

      {/* Seats — positioned within camera frustum */}
      <TheaterSeats />

      <TheaterDust />

      <EffectComposer>
        <Bloom
          luminanceThreshold={0.15}
          luminanceSmoothing={0.85}
          intensity={1.4}
        />
        <Vignette eskil={false} offset={0.2} darkness={0.85} />
      </EffectComposer>
    </>
  )
}

export function TheaterScene({ videoUrl }: { videoUrl?: string }) {
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
        <SceneContents videoUrl={videoUrl} />
      </Canvas>
    </div>
  )
}