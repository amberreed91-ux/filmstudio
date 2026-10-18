import { useRef, useState } from 'react'

export type CameraFrustumParams = {
  fov: number
  tilt: number
}

type Props = {
  initial?: CameraFrustumParams
  onChange?: (params: CameraFrustumParams) => void
}

/**
 * CameraFrustumGizmo — drag the reticle to steer live camera frustum
 * parameters for the Previs Bay. Horizontal drag drives field-of-view,
 * vertical drag drives tilt. Pointer state is local; the parent owns the
 * params via onChange so nothing here touches backend state.
 */
export default function CameraFrustumGizmo({ initial = { fov: 48, tilt: 8 }, onChange }: Props) {
  const [params, setParams] = useState<CameraFrustumParams>(initial)
  const [dragging, setDragging] = useState(false)
  const trackRef = useRef<HTMLDivElement>(null)

  function emit(next: CameraFrustumParams) {
    setParams(next)
    onChange?.(next)
  }

  function handlePointerMove(event: React.PointerEvent) {
    if (!dragging) return
    const rect = trackRef.current?.getBoundingClientRect()
    if (!rect) return
    const nx = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
    const ny = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height))
    emit({ fov: Math.round(20 + nx * 50), tilt: Math.round(30 - ny * 60) })
  }

  const knobLeft = `${((params.fov - 20) / 50) * 100}%`
  const knobTop = `${((30 - params.tilt) / 60) * 100}%`

  return (
    <div className="rounded-lg border-2 border-[#1E293B] bg-[#0B0F17]/80 p-3 backdrop-blur-2xl" data-testid="camera-frustum-gizmo">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[10px] uppercase tracking-[0.16em] text-[#CBD5E1]/70">Camera gizmo · drag to steer frustum</p>
        <p className="font-mono text-[10px] text-[#CBD5E1]/70" data-testid="camera-frustum-readout">
          fov {params.fov}° · tilt {params.tilt}°
        </p>
      </div>
      <div
        ref={trackRef}
        role="slider"
        aria-label="Camera frustum gizmo"
        aria-valuetext={`fov ${params.fov} degrees, tilt ${params.tilt} degrees`}
        aria-valuemin={20}
        aria-valuemax={70}
        aria-valuenow={params.fov}
        tabIndex={0}
        data-testid="camera-gizmo-track"
        onPointerDown={(event) => {
          ;(event.target as HTMLElement).setPointerCapture?.(event.pointerId)
          setDragging(true)
        }}
        onPointerUp={() => setDragging(false)}
        onPointerCancel={() => setDragging(false)}
        onPointerMove={handlePointerMove}
        onKeyDown={(event) => {
          if (event.key === 'ArrowLeft') emit({ ...params, fov: Math.max(20, params.fov - 1) })
          if (event.key === 'ArrowRight') emit({ ...params, fov: Math.min(70, params.fov + 1) })
          if (event.key === 'ArrowUp') emit({ ...params, tilt: Math.min(30, params.tilt + 1) })
          if (event.key === 'ArrowDown') emit({ ...params, tilt: Math.max(-30, params.tilt - 1) })
        }}
        className="relative mt-2 h-36 cursor-crosshair touch-none overflow-hidden rounded-lg border border-[#1E293B] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F59E0B]"
        style={{
          background:
            'radial-gradient(circle at 50% 50%, rgba(109,40,217,0.35) 0%, transparent 55%), linear-gradient(#0B0F17, #121824)',
        }}
      >
        {/* Frustum guide lines */}
        <div aria-hidden="true" className="absolute inset-0" style={{ background: 'linear-gradient(transparent 49.5%, rgba(203,213,225,0.12) 50%, transparent 50.5%), linear-gradient(90deg, transparent 49.5%, rgba(203,213,225,0.12) 50%, transparent 50.5%)' }} />
        <div
          aria-hidden="true"
          data-testid="camera-gizmo-knob"
          className="absolute h-5 w-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[#8B5CF6] bg-[#6D28D9]/60"
          style={{ left: knobLeft, top: knobTop, boxShadow: '0 0 16px rgba(139,92,246,0.7)' }}
        />
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-[#CBD5E1]/60">
        Horizontal position sets field-of-view · vertical position sets tilt. Values flow to the live frustum preview.
      </p>
    </div>
  )
}
