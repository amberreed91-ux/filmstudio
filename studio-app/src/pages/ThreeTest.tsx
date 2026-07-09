import { Canvas } from '@react-three/fiber'

export function ThreeTest() {
  return (
    <div style={{ width: '100vw', height: '100vh', background: 'red' }}>
      <Canvas gl={{ powerPreference: "high-performance", antialias: false }}>
        <color attach="background" args={['blue']} />
        <ambientLight intensity={2} />
        <mesh>
          <boxGeometry args={[2, 2, 2]} />
          <meshStandardMaterial color="lime" />
        </mesh>
      </Canvas>
    </div>
  )
}