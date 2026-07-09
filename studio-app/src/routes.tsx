import type { ReactNode } from 'react'
import { BookOpen, Clapperboard, DollarSign, Film, FolderKanban, Home, LayoutDashboard, FileText, Eye, Share2 } from 'lucide-react'
import { matchPath } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import StudyRoom from './pages/StudyRoom'
import Scheduler from './pages/Scheduler'
import Cost from './pages/Cost'
import ProjectSlate from './pages/ProjectSlate'
import ProjectWorkspace from './pages/ProjectWorkspace'
import ScriptIngest from './pages/ScriptIngest'
import PrevisRoom from './pages/PrevisRoom'
import StudioLanding from './pages/StudioLanding'
import StudioLobby from './pages/StudioLobby'
import StudioOverview from './pages/StudioOverview'
import WritersRoom from './pages/WritersRoom'
import ProductionBoard from './pages/ProductionBoard'
import ScreeningRoom from './pages/ScreeningRoom'
import ArchiveRoom from './pages/ArchiveRoom'
import StudioDevTools from './pages/StudioDevTools'
import ShareProject from './pages/ShareProject'
import UniverseGraphPage from './pages/UniverseGraphPage'
import { ThreeTest } from './pages/ThreeTest'

export type NavigationPlacement =
  | 'primary'
  | 'secondary'
  | 'contextual'
  | 'hidden-system'

export type AppRoute = {
  path: string
  label: string
  title: string
  purpose: string
  placement: NavigationPlacement
  breadcrumbs?: Array<{
    label: string
    to?: string
  }>
  contextualLinks?: Array<{
    to: string
    label?: string
  }>
  icon?: ReactNode
  element: ReactNode
}

export const APP_ROUTES: AppRoute[] = [
  {
    path: '/',
    label: 'Studio Landing',
    title: 'Studio Landing',
    purpose: 'Cinematic entry portal for the studio environment.',
    placement: 'hidden-system',
    element: <StudioLanding />,
  },
  {
    path: '/studio',
    label: 'Studio',
    title: 'Studio Lobby',
    purpose: 'Room-based entry point for navigating writing, previs, production, screening, and archive workflows.',
    placement: 'hidden-system',
    breadcrumbs: [{ label: 'Studio' }],
    contextualLinks: [
      { to: '/studio/slate', label: 'Open Project Slate' },
      { to: '/studio/overview', label: 'Open Studio Dashboard' },
      { to: '/studio/writers-room', label: "Open Writer's Room" },
      { to: '/studio/previs', label: 'Open Previs Room' },
    ],
    icon: <Home size={14} />,
    element: <StudioLobby />,
  },
  {
    path: '/studio/lobby',
    label: 'Home',
    title: 'Home',
    purpose: 'Room-based entry point for navigating writing, previs, production, screening, and archive workflows.',
    placement: 'primary',
    breadcrumbs: [{ label: 'Studio', to: '/studio' }, { label: 'Home' }],
    contextualLinks: [
      { to: '/studio/overview', label: 'Open Overview' },
      { to: '/studio/writers-room', label: "Open Write" },
      { to: '/studio/previs', label: 'Open Storyboard' },
    ],
    icon: <Home size={14} />,
    element: <StudioLobby />,
  },
  {
    path: '/studio/overview',
    label: 'Overview',
    title: 'Overview',
    purpose: 'Master command center for film health, active risks, and room-level progress.',
    placement: 'primary',
    breadcrumbs: [{ label: 'Home', to: '/' }, { label: 'Studio', to: '/studio' }, { label: 'Overview' }],
    contextualLinks: [
      { to: '/studio/lobby', label: 'Open Home' },
      { to: '/studio/writers-room', label: "Open Write" },
    ],
    icon: <LayoutDashboard size={14} />,
    element: <StudioOverview />,
  },
  {
    path: '/studio/writers-room',
    label: 'Write',
    title: 'Write',
    purpose: 'Narrative planning and revision room for story structure, beats, and continuity intent.',
    placement: 'primary',
    breadcrumbs: [{ label: 'Studio Lobby', to: '/studio' }, { label: 'Write' }],
    contextualLinks: [
      { to: '/studio/previs', label: 'Open Storyboard' },
      { to: '/studio/production-board', label: 'Open Scenes' },
    ],
    icon: <BookOpen size={14} />,
    element: <WritersRoom />,
  },
  {
    path: '/studio/universe-graph',
    label: 'Universe',
    title: 'Universe Knowledge Graph',
    purpose: 'Interconnected knowledge graph of characters, locations, lore, and objects.',
    placement: 'primary',
    breadcrumbs: [{ label: 'Studio Lobby', to: '/studio' }, { label: 'Universe' }],
    icon: <Share2 size={14} />,
    element: <UniverseGraphPage />,
  },
  {
    path: '/studio/production-board',
    label: 'Scenes',
    title: 'Scenes',
    purpose: 'Execution and stage-state monitoring room for active scene output readiness.',
    placement: 'primary',
    breadcrumbs: [{ label: 'Studio Lobby', to: '/studio' }, { label: 'Scenes' }],
    contextualLinks: [
      { to: '/studio/previs', label: 'Open Storyboard' },
      { to: '/studio/screening-room', label: 'Open Watch' },
    ],
    icon: <Clapperboard size={14} />,
    element: <ProductionBoard />,
  },
  {
    path: '/studio/screening-room',
    label: 'Watch',
    title: 'Watch',
    purpose: 'Playback and review room for scene cuts, comparisons, and intervention outcomes.',
    placement: 'primary',
    breadcrumbs: [{ label: 'Studio Lobby', to: '/studio' }, { label: 'Watch' }],
    contextualLinks: [
      { to: '/studio/previs', label: 'Open Storyboard' },
      { to: '/studio/archive', label: 'Open Archive' },
    ],
    icon: <Film size={14} />,
    element: <ScreeningRoom />,
  },
  {
    path: '/studio/archive',
    label: 'Archive',
    title: 'Archive',
    purpose: 'Browse historical project states, quality snapshots, and prior intervention records.',
    placement: 'primary',
    breadcrumbs: [{ label: 'Studio Lobby', to: '/studio' }, { label: 'Archive' }],
    contextualLinks: [
      { to: '/studio/lobby', label: 'Return to Home' },
      { to: '/studio/previs', label: 'Open Storyboard' },
    ],
    icon: <FolderKanban size={14} />,
    element: <ArchiveRoom />,
  },
  {
    path: '/studio/devtools',
    label: 'Dev Tools',
    title: 'Studio Dev Tools',
    purpose: 'Hidden developer sandbox for diagnostics, mock toggles, and render recovery workflows.',
    placement: 'hidden-system',
    breadcrumbs: [{ label: 'Studio Lobby', to: '/studio' }, { label: 'Dev Tools' }],
    contextualLinks: [
      { to: '/studio/lobby', label: 'Return to Lobby' },
      { to: '/studio/production-board', label: 'Open Production Board' },
    ],
    icon: <Clapperboard size={14} />,
    element: <StudioDevTools />,
  },
  {
    path: '/studio/workspace',
    label: 'Workspace',
    title: 'Project Workspace',
    purpose: 'Workspace entry route for project slate and production workspace access.',
    placement: 'hidden-system',
    breadcrumbs: [{ label: 'Studio Lobby', to: '/studio' }, { label: 'Workspace' }],
    contextualLinks: [
      { to: '/studio/slate', label: 'Open Project Slate' },
      { to: '/studio/production-board', label: 'Open Production Board' },
    ],
    icon: <Film size={14} />,
    element: <ProjectSlate />,
  },
  {
    path: '/studio/development-room',
    label: 'Development Room',
    title: 'Development Room',
    purpose: 'Development room for scene shaping, previs, and iterative planning.',
    placement: 'hidden-system',
    breadcrumbs: [{ label: 'Studio Lobby', to: '/studio' }, { label: 'Development Room' }],
    contextualLinks: [
      { to: '/studio/writers-room', label: "Open Writer's Room" },
      { to: '/studio/previs', label: 'Open Previs Room' },
    ],
    icon: <Film size={14} />,
    element: <PrevisRoom />,
  },
  {
    path: '/studio/ingest',
    label: 'Script Processing',
    title: 'Script Processing',
    purpose: 'Internal script processing stage triggered by Generate Scenes in Writer’s Room.',
    placement: 'hidden-system',
    breadcrumbs: [{ label: 'Studio Dashboard', to: '/studio' }, { label: 'Script Processing' }],
    contextualLinks: [
      { to: '/studio/slate', label: 'Open Project Slate' },
      { to: '/studio/dashboard', label: 'Approval Room' },
    ],
    icon: <FileText size={14} />,
    element: <ScriptIngest />,
  },
  {
    path: '/studio/slate',
    label: 'Project Slate',
    title: 'Project Slate',
    purpose: 'Slate management for projects, variants, branching directions, and archive posture.',
    placement: 'primary',
    breadcrumbs: [{ label: 'Studio Dashboard', to: '/studio' }, { label: 'Project Slate' }],
    contextualLinks: [
      { to: '/studio/dashboard', label: 'Approval Room' },
      { to: '/studio/scheduler', label: 'Crew Ops' },
    ],
    icon: <FolderKanban size={14} />,
    element: <ProjectSlate />,
  },
  {
    path: '/studio/project/:projectId',
    label: 'Project Workspace',
    title: 'Project Workspace',
    purpose: 'End-to-end film production workspace with stage gates, crew collaboration, memory, and orchestration.',
    placement: 'secondary',
    breadcrumbs: [{ label: 'Studio Dashboard', to: '/studio' }, { label: 'Project Workspace' }],
    contextualLinks: [
      { to: '/studio/slate', label: 'Back to Slate' },
      { to: '/studio/dashboard', label: 'Approval Room' },
    ],
    icon: <Film size={14} />,
    element: <ProjectWorkspace />,
  },
  {
    path: '/previs',
    label: 'Rough Previs Room',
    title: 'Rough Previs Room',
    purpose: 'Read-only previs review space for scene strip, shot ledger, continuity, and director evaluations.',
    placement: 'contextual',
    breadcrumbs: [{ label: 'Studio Dashboard', to: '/studio' }, { label: 'Rough Previs Room' }],
    contextualLinks: [
      { to: '/studio/slate', label: 'Back to Slate' },
      { to: '/studio/dashboard', label: 'Approval Room' },
    ],
    icon: <Film size={14} />,
    element: <PrevisRoom />,
  },
  {
    path: '/studio/previs',
    label: 'Previs Room',
    title: 'Previs Room',
    purpose: 'Review generated scenes, shot recommendations, and approvals before rendering.',
    placement: 'primary',
    breadcrumbs: [{ label: 'Studio Dashboard', to: '/studio' }, { label: 'Rough Previs Room' }],
    contextualLinks: [
      { to: '/studio/slate', label: 'Back to Slate' },
      { to: '/studio/dashboard', label: 'Approval Room' },
    ],
    icon: <Film size={14} />,
    element: <PrevisRoom />,
  },
  {
    path: '/studio/project/:projectId/previs',
    label: 'Previs Room',
    title: 'Previs Room',
    purpose: 'Review generated scenes, shot recommendations, and approvals before rendering.',
    placement: 'contextual',
    breadcrumbs: [{ label: 'Studio Dashboard', to: '/studio' }, { label: 'Project Workspace', to: '/studio/slate' }, { label: 'Rough Previs Room' }],
    contextualLinks: [
      { to: '/studio/slate', label: 'Back to Slate' },
      { to: '/studio/dashboard', label: 'Approval Room' },
    ],
    icon: <Film size={14} />,
    element: <PrevisRoom />,
  },
  {
    path: '/three-test',
    label: 'Three Test',
    title: 'Three.js R3F Test',
    purpose: 'Isolated test to verify R3F Canvas rendering.',
    placement: 'hidden-system',
    element: <ThreeTest />,
  },
  {
    path: '/studio/dashboard',
    label: 'Approval Room',
    title: 'Approval Intelligence & QC',
    purpose: 'Quality control, approval gates, reference comparison, and benchmark take review.',
    placement: 'hidden-system',
    breadcrumbs: [{ label: 'Studio Dashboard', to: '/studio' }, { label: 'Approval Room' }],
    contextualLinks: [
      { to: '/studio/slate', label: 'Choose Project Workspace' },
      { to: '/studio/study-room', label: 'Open Study Room' },
    ],
    icon: <LayoutDashboard size={14} />,
    element: <Dashboard />,
  },
  {
    path: '/studio/approval',
    label: 'Approval Room',
    title: 'Approval Intelligence & QC',
    purpose: 'Quality control, approval gates, reference comparison, and benchmark take review.',
    placement: 'hidden-system',
    breadcrumbs: [{ label: 'Studio Dashboard', to: '/studio' }, { label: 'Approval Room' }],
    contextualLinks: [
      { to: '/studio/slate', label: 'Choose Project Workspace' },
      { to: '/studio/study-room', label: 'Open Study Room' },
    ],
    icon: <LayoutDashboard size={14} />,
    element: <Dashboard />,
  },
  {
    path: '/studio/approval-room',
    label: 'Approval Room',
    title: 'Approval Intelligence & QC',
    purpose: 'Quality control, approval gates, reference comparison, and benchmark take review.',
    placement: 'primary',
    breadcrumbs: [{ label: 'Studio Dashboard', to: '/studio' }, { label: 'Approval Room' }],
    contextualLinks: [
      { to: '/studio/slate', label: 'Choose Project Workspace' },
      { to: '/studio/study-room', label: 'Open Study Room' },
    ],
    icon: <LayoutDashboard size={14} />,
    element: <Dashboard />,
  },
  {
    path: '/studio/study-room',
    label: 'Study Room',
    title: 'Study Room',
    purpose: 'Review story structure, scene health, pacing, and creative lessons.',
    placement: 'primary',
    breadcrumbs: [{ label: 'Studio Dashboard', to: '/studio' }, { label: 'Study Room' }],
    contextualLinks: [
      { to: '/studio/slate', label: 'Choose Project Workspace' },
      { to: '/studio/scheduler', label: 'Plan in Crew Ops' },
    ],
    icon: <BookOpen size={14} />,
    element: <StudyRoom />,
  },
  {
    path: '/studio/study',
    label: 'Study Room',
    title: 'Study Room',
    purpose: 'Review story structure, scene health, pacing, and creative lessons.',
    placement: 'hidden-system',
    breadcrumbs: [{ label: 'Studio Dashboard', to: '/studio' }, { label: 'Study Room' }],
    contextualLinks: [
      { to: '/studio/writers-room', label: "Open Writer's Room" },
      { to: '/studio/previs', label: 'Open Previs Room' },
      { to: '/studio/screening-room', label: 'Open Screening Room' },
    ],
    icon: <BookOpen size={14} />,
    element: <StudyRoom />,
  },
  {
    path: '/studio/scheduler',
    label: 'Crew Ops',
    title: 'AI Production Scheduler',
    purpose: 'Crew pipeline status, render routing, and dailies review.',
    placement: 'primary',
    breadcrumbs: [{ label: 'Studio Dashboard', to: '/studio' }, { label: 'Crew Ops' }],
    contextualLinks: [
      { to: '/studio/slate', label: 'Choose Project Workspace' },
      { to: '/studio/cost', label: 'Open Cost Manager' },
    ],
    icon: <Clapperboard size={14} />,
    element: <Scheduler />,
  },
  {
    path: '/studio/cost',
    label: 'Cost Manager',
    title: 'Render Resource & Cost Manager',
    purpose: 'Render queue visibility, provider routing, and cost controls.',
    placement: 'primary',
    breadcrumbs: [{ label: 'Studio Dashboard', to: '/studio' }, { label: 'Cost Manager' }],
    contextualLinks: [
      { to: '/studio/slate', label: 'Choose Project Workspace' },
      { to: '/studio/scheduler', label: 'Go to Crew Ops' },
    ],
    icon: <DollarSign size={14} />,
    element: <Cost />,
  },
  {
    path: '/share/:shareToken',
    label: 'Share Project',
    title: 'Shared Project View',
    purpose: 'Read-only view of a shared project via share token.',
    placement: 'hidden-system',
    element: <ShareProject />,
  },
]

export const PRIMARY_NAV_ROUTES = APP_ROUTES.filter((route) => route.placement === 'primary')

export function getRouteByPath(pathname: string) {
  return APP_ROUTES.find((route) => matchPath({ path: route.path, end: true }, pathname)) || null
}

export function getRouteLabel(pathname: string) {
  return getRouteByPath(pathname)?.label || pathname
}
