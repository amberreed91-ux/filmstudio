import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './styles/cinematic.css'
import CreatorWorkspaceFixture from './CreatorWorkspaceFixture'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <CreatorWorkspaceFixture />
  </StrictMode>,
)
