import { useEffect, useRef } from 'react'
import { useTransition } from '../lib/studioTransition'
import { useNavigate } from 'react-router-dom'

export function CinematicCut() {
  const { state, toRoom, complete } = useTransition()
  const navigate = useNavigate()
  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (state !== 'cutting' || !toRoom) return

    const overlay = overlayRef.current
    if (!overlay) return

    // Frame 1: cut to black (2 frames = ~33ms at 60fps)
    overlay.style.opacity = '1'

    const t1 = setTimeout(() => {
      navigate(toRoom)
      // Frame 2: hold black briefly
      const t2 = setTimeout(() => {
        overlay.style.opacity = '0'
        const t3 = setTimeout(complete, 400)
        return () => clearTimeout(t3)
      }, 80)
      return () => clearTimeout(t2)
    }, 33)

    return () => clearTimeout(t1)
  }, [state, toRoom, navigate, complete])

  return (
    <div
      ref={overlayRef}
      style={{
        position: 'fixed',
        inset: 0,
        background: '#000',
        opacity: 0,
        zIndex: 9999,
        pointerEvents: state === 'cutting' ? 'all' : 'none',
        transition: 'opacity 0.08s linear',
      }}
    />
  )
}