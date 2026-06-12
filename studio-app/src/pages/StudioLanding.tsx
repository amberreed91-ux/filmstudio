import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function StudioLanding() {
  const navigate = useNavigate()
  const [isEntering, setIsEntering] = useState(false)

  const handleEnter = () => {
    if (isEntering) return
    setIsEntering(true)
    window.setTimeout(() => {
      navigate('/studio/overview')
    }, 420)
  }

  return (
    <div
      className={`studio-landing-screen cinematic-hero ${isEntering ? 'studio-landing-exit' : ''}`}
      role="presentation"
    >
      <div className="studio-landing-bg" />
      <div className="studio-landing-grain" />
      <div className="studio-landing-vignette" />

      <main className="studio-landing-content">
        <p className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-200">LANDING PAGE ACTIVE</p>
        <h1 className="studio-landing-title">STUDIO</h1>
        <p className="studio-landing-subtitle">Direct. Shape. Remember.</p>
        <button
          type="button"
          onClick={handleEnter}
          className="studio-landing-enter"
        >
          Enter Studio
        </button>
      </main>
    </div>
  )
}
