import { Canvas, useFrame } from '@react-three/fiber'
import React from 'react'
import { PerspectiveCamera } from '@react-three/drei'
import * as THREE from 'three'

/**
 * Theater environment — large dark screening room with amber key light
 * from the projection booth, cool rim fill from the screen, and
 * foreground equipment silhouettes.
 */

function EquipmentSilhouettes() {
  // 4 low-poly silhouette meshes representing camera tripods / equipment
  const silhouettes = [
    { pos: [-8, -1.5, 3.5], scale: [0.4, 1.8, 0.4] },   // tripod left
    { pos: [-9.5, -1.5, 4.5], scale: [0.6, 1.2, 0.6] },  // box left
    { pos: [7, -1.5, 3], scale: [0.5, 2.0, 0.5] },        // tripod right
    { pos: [9, -1.5, 5], scale: [0.7, 1.0, 0.7] },        // box right
    { pos: [6.5, -1.5, 4.5], scale: [1.2, 0.3, 0.8] },    // floor case
  ]

  return (
    <group>
      {silhouettes.map((s, i) => (
        <mesh key={i} position={s.pos as [number, number, number]}>
          <boxGeometry args={s.scale as [number, number, number]} />
          <meshStandardMaterial
            color="#000000"
            transparent
            opacity={0.6}
            roughness={1}
            metalness={0}
          />
        </mesh>
      ))}
    </group>
  )
}

function TheaterSeats() {
  const rows = 5
  const seatsPerRow = 10
  const seats: React.ReactNode[] = []
  for (let row = 0; row < rows; row++) {
    for (let seat = 0; seat < seatsPerRow; seat++) {
      seats.push(
        <group
          key={`${row}-${seat}`}
          position={[
            (seat - seatsPerRow / 2 + 0.5) * 1.2,
            -1.4 + row * 0.3,
            1.5 + row * 1.6,
          ]}
        >
          <mesh position={[0, 0.25, 0]}>
            <boxGeometry args={[0.7, 0.5, 0.08]} />
            <meshStandardMaterial color="#0f0e0d" roughness={0.95} />
          </mesh>
          <mesh position={[0, 0.05, 0.15]} rotation={[-Math.PI / 4, 0, 0]}>
            <boxGeometry args={[0.7, 0.08, 0.5]} />
            <meshStandardMaterial color="#0a0908" roughness={0.95} />
          </mesh>
        </group>
      )
    }
  }
  return <group>{seats}</group>
}

function BreathingCameraDrift() {
  useFrame(({ camera, clock }) => {
    camera.rotation.z = Math.sin(clock.getElapsedTime() * 0.15) * 0.008
  })
  return null
}

function SceneContents() {
  return (
    <>
      <color attach="background" args={['#0a0908']} />

      {/* Fog — seats fade into darkness */}
      <fogExp2 attach="fog" args={['#0a0908', 0.035]} />

      <PerspectiveCamera makeDefault position={[0, 2, 9]} fov={65} />

      <BreathingCameraDrift />

      {/* Ambient — very dim warm fill */}
      <ambientLight intensity={0.04} color="#1a1410" />

      {/* Projection booth — warm amber key */}
      <pointLight
        position={[0, 8, -5]}
        intensity={0.8}
        color="#ffd165"
        distance={30}
        decay={2}
      />

      {/* Screen rim — cool cyan fill */}
      <pointLight
        position={[-10, 4, 8]}
        intensity={0.3}
        color="#4cd7f6"
        distance={20}
      />

      {/* Floor — dark reflective surface */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -2, 0]} receiveShadow>
        <planeGeometry args={[40, 30]} />
        <meshStandardMaterial
          color="#0a0908"
          roughness={0.3}
          metalness={0.6}
        />
      </mesh>

      {/* Amber light pool on floor center */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.98, 0]}>
        <circleGeometry args={[3, 32]} />
        <meshBasicMaterial
          color="#ffd165"
          transparent
          opacity={0.04}
        />
      </mesh>

      {/* Back wall */}
      <mesh position={[0, 2.5, -10]}>
        <planeGeometry args={[40, 14]} />
        <meshStandardMaterial color="#080706" roughness={1} />
      </mesh>

      {/* Side walls */}
      <mesh position={[-12, 2.5, 0]} rotation={[0, Math.PI / 2, 0]}>
        <planeGeometry args={[30, 14]} />
        <meshStandardMaterial color="#090807" roughness={1} />
      </mesh>
      <mesh position={[12, 2.5, 0]} rotation={[0, -Math.PI / 2, 0]}>
        <planeGeometry args={[30, 14]} />
        <meshStandardMaterial color="#090807" roughness={1} />
      </mesh>

      {/* Screen */}
      <mesh position={[0, 1.5, -8]}>
        <planeGeometry args={[9, 5]} />
        <meshStandardMaterial color="#0a0a0a" emissive="#1a1a2e" emissiveIntensity={0.6} />
      </mesh>

      {/* Seats */}
      <TheaterSeats />

      {/* Foreground equipment silhouettes */}
      <EquipmentSilhouettes />
    </>
  )
}

export function TheaterScene() {
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