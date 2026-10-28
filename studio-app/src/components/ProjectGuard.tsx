import { useNavigate } from 'react-router-dom'
import { useStudio } from '../context/StudioContext'
import type { ReactNode } from 'react'

type ProjectGuardProps = {
  children: ReactNode
}

export default function ProjectGuard({ children }: ProjectGuardProps) {
  const navigate = useNavigate()
  const { activeProject, loading } = useStudio()

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '60vh',
          gap: '16px',
        }}
      >
        <p style={{ color: '#8896b0', fontSize: '15px' }}>Loading...</p>
      </div>
    )
  }

  if (!activeProject) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '60vh',
          gap: '16px',
        }}
      >
        <p style={{ color: '#8896b0', fontSize: '15px' }}>No film selected</p>
        <p style={{ color: '#4a5568', fontSize: '13px' }}>
          Go to Home to start or continue a film
        </p>
        <button type="button"
          onClick={() => navigate('/studio/lobby')}
          style={{
            padding: '10px 20px',
            fontSize: '13px',
            fontWeight: 600,
            color: '#e8edf5',
            background: 'rgba(16, 185, 129, 0.15)',
            border: '1px solid rgba(16, 185, 129, 0.4)',
            borderRadius: '8px',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(16, 185, 129, 0.25)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'rgba(16, 185, 129, 0.15)'
          }}
        >
          Go to Home
        </button>
      </div>
    )
  }

  return <>{children}</>
}
