export const PROJECT = {
  name: 'Neon Dreams v2.4',
  id: 'neon-dreams-v2-4',
  scenes: 34,
  shots: 220,
  status: 'In Production',
}

export const APPROVAL_GATES = [
  {
    id: 'rights',
    label: 'Rights & Clearances',
    status: 'passed',
    sub: 'All Assets Cleared',
    detail: 'Talent, Music, Locations',
  },
  {
    id: 'safety',
    label: 'Safety & Compliance',
    status: 'passed',
    sub: 'No Critical Issues',
    detail: 'PG-13 Rating Adhered, No Hazardous Elements',
  },
  {
    id: 'creative',
    label: 'Creative Rules',
    status: 'warning',
    sub: 'Action Required',
    detail: "Director's Note: Adjust Lighting Contrast in Scene 4B. Rule Ref: CR-204",
  },
]

export const CREW = [
  {
    id: 'director',
    name: 'Director AI',
    task: 'Analyzing Scene 4',
    color: '#22c55e',
    bg: '#052e16',
    icon: 'director',
    waveform: [20, 35, 15, 40, 28, 50, 33, 45, 20, 38],
  },
  {
    id: 'storyboard',
    name: 'Storyboard AI',
    task: 'Generating 12/20 frames',
    color: '#a855f7',
    bg: '#2e1065',
    icon: 'storyboard',
    waveform: [10, 25, 40, 30, 45, 20, 35, 50, 25, 15],
  },
  {
    id: 'editor',
    name: 'Editor AI',
    task: 'Processing Scene 3',
    color: '#3b82f6',
    bg: '#1e3a5f',
    icon: 'editor',
    waveform: [30, 20, 45, 35, 25, 40, 30, 20, 35, 45],
  },
  {
    id: 'cinematographer',
    name: 'Cinematographer AI',
    task: 'Composing Shot 7',
    color: '#f97316',
    bg: '#431407',
    icon: 'camera',
    waveform: [40, 30, 20, 45, 35, 25, 40, 35, 20, 30],
  },
  {
    id: 'sound',
    name: 'Sound Designer AI',
    task: 'Mixing Audio Track 2',
    color: '#06b6d4',
    bg: '#083344',
    icon: 'sound',
    waveform: [15, 40, 25, 50, 30, 45, 20, 35, 45, 30],
  },
]

export const PIPELINE_STAGES = [
  { id: 'ingest', label: 'Story Ingest', status: 'complete', progress: 100 },
  { id: 'breakdown', label: 'Scene Breakdown', status: 'active', progress: 60, detail: '12 Shots Identified • 4 Crew Assigned • Rights Check: Passed' },
  { id: 'crew', label: 'Crew Assignment', status: 'pending', progress: 0 },
  { id: 'render', label: 'Rendering', status: 'queue', progress: 0 },
]

export const LIVE_DAILIES = [
  { id: 32, label: 'Shot 32: EXT. Alley', thumb: null, reviewed: false },
  { id: 33, label: 'Shot 33: INT. Lab', thumb: null, reviewed: false },
  { id: 34, label: 'Shot 34: EXT. Rooftop', thumb: null, reviewed: true },
]

export const PROVIDERS = [
  {
    id: 'runway',
    name: 'Runway',
    type: 'Cloud',
    instance: 'Gen-4 Cluster',
    load: 70,
    jobs: 21,
    costHr: 11.4,
    realtimeCost: 11.4,
    color: '#f97316',
  },
  {
    id: 'runpod',
    name: 'RunPod (Decentralized)',
    type: 'Decentralized',
    instance: 'A100 Clusters (12x)',
    load: 60,
    jobs: 18,
    costHr: 4.8,
    realtimeCost: 4.8,
    color: '#a855f7',
  },
  {
    id: 'local',
    name: 'Internal Local Servers',
    type: 'Local',
    instance: 'RTX 4090 Farm (8x)',
    load: 25,
    jobs: 3,
    costHr: 0,
    realtimeCost: 0,
    color: '#22c55e',
  },
]

export const RENDER_QUEUE = [
  { id: 'SCN_A_001_FIN', status: 'Rendering', progress: 45, eta: '00:15:30', cost: '$0.08/min', priority: false },
  { id: 'SCN_B_012_VFX', status: 'Queued', progress: 0, eta: '01:20:00', cost: 'Est. $0.12/min', priority: false },
  { id: 'SCN_C_005_COMP', status: 'Rendering', progress: 80, eta: '00:02:15', cost: '$0.15/min', priority: true },
  { id: 'SCN_A_001_FIN', status: 'Queued', progress: 0, eta: '00:15:30', cost: '$0.08/min', priority: false },
  { id: 'SCN_B_012_VFX', status: 'Queued', progress: 0, eta: '01:20:00', cost: '$0.12/min', priority: false },
  { id: 'SCN_C_005_COMP', status: 'Queued', progress: 0, eta: '00:15:30', cost: '$0.08/min', priority: false },
  { id: 'SCN_B_012_VFX', status: 'Queued', progress: 0, eta: '01:20:00', cost: '$0.08/min', priority: false },
  { id: 'SCN_C_005_COMP', status: 'Rendering', progress: 60, eta: '00:02:15', cost: '$0.15/min', priority: false },
]

export const STYLE_TRAITS = [
  { id: 'kubrick', label: 'Kubrickian Symmetry', icon: 'symmetry', color: '#06b6d4' },
  { id: 'fincher', label: 'Fincher Green-Tones', icon: 'palette', color: '#22c55e' },
  { id: 'tarkovsky', label: 'Tarkovsky Long Take', icon: 'camera', color: '#a855f7' },
  { id: 'hitchcock', label: 'Hitchcockian Suspense', icon: 'suspense', color: '#f97316' },
]

export const ROUTING_LOG = [
  { time: '10:45 AM', msg: 'Switched SCN_C_005 to Runway for speed.' },
  { time: '10:30 AM', msg: 'Rerouted SCN_A_001 to RunPod for cost efficiency.' },
  { time: '10:15 AM', msg: 'Local servers idling, shifting low-priority jobs.' },
]
