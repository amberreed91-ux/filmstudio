import { Canvas, useFrame } from '@react-three/fiber'
import { useRef, useMemo } from 'react'
import { PerspectiveCamera } from '@react-three/drei'
import * as THREE from 'three'

/**
 * The Page — intimate writer's room / study environment.
 * Warm key light simulating a desk lamp, cool ambient bounce,
 * silhouette bookshelves in the background, and drifting dust motes.
 */

function DustMotes() {
  const ref = useRef<THREE.Points>(null)
  const count = 25

  const positions = useMemo(() => {
    const pos = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      pos[i * 3]     = (Math.random() - 0.5) * 8
      pos[i * 3 + 1] = Math.random() * 5
      pos[i * 3 + 2] = (Math.random() - 0.5) * 4 - 2
    }
    return pos
  }, [])

  useFrame(({ clock }) => {
    if (!ref.current) return
    const pos = ref.current.geometry.attributes.position.array as Float32Array
    for (let i = 0; i < count; i++) {
      pos[i * 3 + 1] += 0.001
      if (pos[i * 3 + 1] > 5) {
        pos[i * 3 + 1] = 0
      }
    }
    ref.current.geometry.attributes.position.needsUpdate = true
  })

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.02}
        color="#ffd165"
        transparent
        opacity={0.3}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  )
}

function BackgroundSilhouettes() {
  return (
    <group>
      {/* Bookshelf left — far back */}
      <mesh position={[-6, -0.5, -10]} rotation={[0, 0.3, 0]}>
        <boxGeometry args={[2.5, 3.5, 0.4]} />
        <meshStandardMaterial color="#050403" roughness={1} metalness={0} transparent opacity={0.7} />
      </mesh>
      {/* Shelf dividers */}
      <mesh position={[-6, 0.7, -9.9]}>
        <boxGeometry args={[2.5, 0.06, 0.2]} />
        <meshStandardMaterial color="#060504" roughness={1} />
      </mesh>
      <mesh position={[-6, -0.3, -9.9]}>
        <boxGeometry args={[2.5, 0.06, 0.2]} />
        <meshStandardMaterial color="#060504" roughness={1} />
      </mesh>

      {/* Bookshelf right — far back */}
      <mesh position={[6, -0.5, -11]} rotation={[0, -0.3, 0]}>
        <boxGeometry args={[2.5, 3.5, 0.4]} />
        <meshStandardMaterial color="#050403" roughness={1} metalness={0} transparent opacity={0.7} />
      </mesh>
      <mesh position={[6, 0.7, -10.9]}>
        <boxGeometry args={[2.5, 0.06, 0.2]} />
        <meshStandardMaterial color="#060504" roughness={1} />
      </mesh>
      <mesh position={[6, -0.3, -10.9]}>
        <boxGeometry args={[2.5, 0.06, 0.2]} />
        <meshStandardMaterial color="#060504" roughness={1} />
      </mesh>

      {/* Desk edge — barely visible, bottom-left */}
      <mesh position={[-3, -2.2, -8]} rotation={[0.05, 0.1, 0]}>
        <boxGeometry args={[4, 0.1, 1.5]} />
        <meshStandardMaterial color="#080706" roughness={1} metalness={0} transparent opacity={0.8} />
      </mesh>
    </group>
  )
}

function SceneContents() {
  return (
    <>
      <color attach="background" args={['#0c0b09']} />

      {/* Fog — fades background silhouettes into darkness */}
      <fogExp2 attach="fog" args={['#0e0d0b', 0.025]} />

      <PerspectiveCamera makeDefault position={[0, 0.5, 5]} fov={55} />

      {/* Ambient — very dim warm fill */}
      <ambientLight intensity={0.06} color="#1a1a14" />

      {/* Desk lamp — warm key, directional, close */}
      <pointLight
        position={[3, 5, 2]}
        intensity={1.2}
        color="#ffd165"
        distance={20}
      />

      {/* Screen/window cool bounce */}
      <pointLight
        position={[-5, 3, -3]}
        intensity={0.15}
        color="#4cd7f6"
        distance={15}
      />

      {/* Floor — dark, barely reflective */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -2.5, 0]}>
        <planeGeometry args={[20, 20]} />
        <meshStandardMaterial color="#0a0907" roughness={0.8} metalness={0.2} />
      </mesh>

      {/* Back wall */}
      <mesh position={[0, 1.5, -12]}>
        <planeGeometry args={[20, 14]} />
        <meshStandardMaterial color="#080705" roughness={1} />
      </mesh>

      {/* Side walls */}
      <mesh position={[-8, 1.5, 0]} rotation={[0, Math.PI / 2, 0]}>
        <planeGeometry args={[24, 14]} />
        <meshStandardMaterial color="#090806" roughness={1} />
      </mesh>
      <mesh position={[8, 1.5, 0]} rotation={[0, -Math.PI / 2, 0]}>
        <planeGeometry args={[24, 14]} />
        <meshStandardMaterial color="#090806" roughness={1} />
      </mesh>

      {/* Ceiling */}
      <mesh position={[0, 5.5, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <planeGeometry args={[20, 24]} />
        <meshStandardMaterial color="#080705" roughness={1} />
      </mesh>

      {/* Background silhouettes — bookshelves and desk edge */}
      <BackgroundSilhouettes />

      {/* Dust motes drifting in lamp light */}
      <DustMotes />
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
        gl={{ powerPreference: "high-performance", antialias: false }}
        style={{ width: '100%', height: '100%' }}
      >
        <SceneContents />
      </Canvas>
    </div>
  )
}