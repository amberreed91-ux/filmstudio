import { useMemo, useState } from 'react'
import { Camera, Check, Search, X } from 'lucide-react'
import { useCameraPresets } from '../hooks/useCameraPresets'
import type {
  CameraAperture,
  CameraFocalLength,
  CameraLens,
  CameraPlan,
  CameraPreset,
} from '../lib/cameraPresetApi'

type Props = { current: CameraPlan; onApply: (plan: CameraPlan) => void; disabled?: boolean }

const inputClass =
  'w-full min-w-0 rounded-md border border-white/15 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none focus-visible:border-amber-200 disabled:opacity-40'

/* ── Column card — rounded panel with title, optional filter chip, and
   scrollable selection list. Each column is the same shape: title + list. */
function ColumnCard<T extends { id: string; label: string; category?: string }>({
  title,
  items,
  selectedId,
  onSelect,
  filterValue,
  onFilterChange,
  filterOptions,
  selectedIdForFilter,
  renderItem,
  disabled = false,
}: {
  title: string
  items: T[]
  selectedId: string
  onSelect: (item: T) => void
  filterValue: string
  onFilterChange: (next: string) => void
  filterOptions: string[]
  selectedIdForFilter?: string
  renderItem: (item: T, active: boolean) => React.ReactNode
  disabled?: boolean
}) {
  const visible = useMemo(() => {
    if (filterValue === 'All') return items
    return items.filter((item) => item.category === filterValue)
  }, [items, filterValue])
  return (
    <div className="liquid-panel relative flex min-h-[420px] flex-1 flex-col overflow-hidden">
      <span aria-hidden="true" className="liquid-edge" />
      <span aria-hidden="true" className="liquid-spec" />
      <div className="relative z-10 flex items-center justify-between border-b border-white/10 px-4 py-3">
        <h3 className="text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-100/80">{title}</h3>
        <div className="flex items-center gap-1.5">
          <span className="rounded-full border border-white/15 bg-white/[0.04] px-2.5 py-0.5 text-[10px] uppercase tracking-[0.12em] text-zinc-300">{filterValue}</span>
          <select
            aria-label={`${title} filter`}
            value={selectedIdForFilter ?? ''}
            onChange={(event) => onFilterChange(event.target.value || 'All')}
            className="h-6 w-6 cursor-pointer appearance-none rounded-full border border-white/15 bg-transparent text-center text-base leading-none text-zinc-400 outline-none hover:border-white/30 focus-visible:border-amber-200"
          >
            <option value="">⚙</option>
            {filterOptions.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
        </div>
      </div>
      <div role="listbox" aria-label={title} className="relative z-10 flex-1 space-y-2 overflow-y-auto overscroll-contain p-3">
        {visible.map((item) => {
          const active = selectedId === item.id
          return (
            <button
              key={item.id}
              type="button"
              role="option"
              disabled={disabled}
              aria-selected={active}
              title={'description' in item && typeof item.description === 'string' ? item.description : item.label}
              onClick={() => onSelect(item)}
              className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition-all focus-visible:outline-2 focus-visible:outline-amber-200 disabled:opacity-40 ${
                active
                  ? 'border-amber-200/60 bg-gradient-to-br from-amber-200/15 to-amber-200/5 text-amber-100 shadow-[0_0_0_1px_rgba(252,211,77,0.4),inset_0_1px_0_rgba(255,255,255,0.08)]'
                  : 'border-white/10 text-zinc-300 hover:border-white/25 hover:bg-white/[0.04]'
              }`}
            >
              {renderItem(item, active)}
            </button>
          )
        })}
        {!visible.length && <p className="rounded-md border border-dashed border-white/15 p-3 text-xs text-zinc-400">No {title.toLowerCase()} match this filter.</p>}
      </div>
    </div>
  )
}

/* ── Realistic optics glyphs — pure presentational SVG. Props, data flow,
   and selection logic are untouched, so nothing outside this file changes. */
function ApertureGlyph({ aperture }: { aperture: CameraAperture }) {
  // Six-blade iris diaphragm: hexagonal opening sized by f-stop with blade
  // edges radiating to the housing, so f/1.4 reads wide-open and f/11 pinhole.
  const openMap: Record<string, number> = { 'f/1.4': 0.95, 'f/2.8': 0.7, 'f/4': 0.5, 'f/5.6': 0.35, 'f/11': 0.18 }
  const openness = openMap[aperture.f_stop] ?? 0.5
  const cx = 16
  const cy = 16
  const housing = 14
  const ro = 2.2 + openness * 8.6
  const verts = Array.from({ length: 6 }, (_, k) => {
    const a = ((Math.PI / 3) * k) + Math.PI / 6
    return { x: cx + ro * Math.cos(a), y: cy + ro * Math.sin(a), a }
  })
  const blades = verts.map(({ x, y, a }) => {
    const d = a + 0.9
    const dx = Math.cos(d)
    const dy = Math.sin(d)
    const ox = x - cx
    const oy = y - cy
    const b = ox * dx + oy * dy
    const t = -b + Math.sqrt(Math.max(0, b * b - (ox * ox + oy * oy - housing * housing)))
    return { x1: x, y1: y, x2: cx + ox + dx * t, y2: cy + oy + dy * t }
  })
  const hex = verts.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ')
  return (
    <svg viewBox="0 0 32 32" className="h-9 w-9 shrink-0" aria-hidden="true">
      <defs>
        <radialGradient id={`ap-${aperture.id}`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="rgba(255,255,255,0.22)" />
          <stop offset="70%" stopColor="rgba(255,255,255,0.04)" />
          <stop offset="100%" stopColor="rgba(0,0,0,0.5)" />
        </radialGradient>
      </defs>
      <circle cx={cx} cy={cy} r={housing} fill="#0a0a0c" stroke="rgba(255,255,255,0.45)" strokeWidth="1.5" />
      {blades.map((b, i) => (
        <line key={i} x1={b.x1} y1={b.y1} x2={b.x2} y2={b.y2} stroke="rgba(255,255,255,0.4)" strokeWidth="1" />
      ))}
      <polygon points={hex} fill={`url(#ap-${aperture.id})`} stroke="rgba(255,255,255,0.55)" strokeWidth="1" />
    </svg>
  )
}

function FocalFovGlyph({ mm }: { mm: number }) {
  // Top-down field-of-view diagram. Horizontal angle of view on full-frame
  // (36mm wide) is 2·atan(18/mm); the frame-bar width encodes the angle so
  // 14mm reads ultra-wide and 135mm reads telephoto at a glance.
  const half = Math.atan(18 / Math.max(1, mm))
  const aov = ((2 * half * 180) / Math.PI - 15) / (104 - 15)
  const halfW = Math.min(10, Math.max(1.6, 2 + aov * 8))
  const apexY = 27
  const barY = 5
  return (
    <svg viewBox="0 0 32 32" className="h-9 w-9 shrink-0" aria-hidden="true">
      <line x1="16" y1={apexY} x2={16 - halfW} y2={barY} stroke="rgba(255,255,255,0.5)" strokeWidth="1.1" />
      <line x1="16" y1={apexY} x2={16 + halfW} y2={barY} stroke="rgba(255,255,255,0.5)" strokeWidth="1.1" />
      <line x1="16" y1={apexY} x2="16" y2={barY + 1} stroke="rgba(255,255,255,0.25)" strokeWidth="1" strokeDasharray="2 2" />
      <line x1={16 - halfW} y1={barY} x2={16 + halfW} y2={barY} stroke="rgba(252,211,77,0.85)" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="16" cy={apexY} r="1.8" fill="rgba(255,255,255,0.8)" />
    </svg>
  )
}

function LensGlyph({ lens }: { lens: CameraLens }) {
  const palette: Record<string, string> = {
    'compact-anamorphic': 'rgba(122, 214, 209, 0.7)',
    'vintage-prime': 'rgba(255, 180, 120, 0.7)',
    'clinical-sharp': 'rgba(190, 200, 220, 0.7)',
    'creative-tilt': 'rgba(159, 141, 197, 0.7)',
    'macro': 'rgba(120, 179, 138, 0.7)',
    'wide-cinema': 'rgba(255, 209, 101, 0.7)',
  }
  const ring = palette[lens.id] ?? 'rgba(255,255,255,0.7)'
  // Anamorphic: squeezed oval front element with its signature horizontal flare.
  if (lens.id === 'compact-anamorphic') {
    return (
      <svg viewBox="0 0 32 32" className="h-9 w-9 shrink-0" aria-hidden="true">
        <ellipse cx="16" cy="16" rx="13" ry="7.5" fill="none" stroke={ring} strokeWidth="1.6" />
        <ellipse cx="16" cy="16" rx="8" ry="4.4" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="1" />
        <line x1="2.5" y1="16" x2="29.5" y2="16" stroke="rgba(122,214,209,0.85)" strokeWidth="1.2" strokeLinecap="round" />
        <ellipse cx="16" cy="16" rx="2.2" ry="1.6" fill="rgba(255,255,255,0.5)" />
      </svg>
    )
  }
  // Vintage: warm round element with an offset coating ring and swirl arc.
  if (lens.id === 'vintage-prime') {
    return (
      <svg viewBox="0 0 32 32" className="h-9 w-9 shrink-0" aria-hidden="true">
        <circle cx="16" cy="16" r="12" fill="none" stroke={ring} strokeWidth="1.6" />
        <circle cx="17.5" cy="14.5" r="7" fill="none" stroke="rgba(255,180,120,0.5)" strokeWidth="1" />
        <path d="M8 22 A9 9 0 0 0 22 24" fill="none" stroke="rgba(255,255,255,0.45)" strokeWidth="1.2" strokeLinecap="round" />
        <circle cx="16" cy="16" r="2.6" fill="rgba(255,220,170,0.5)" />
      </svg>
    )
  }
  // Tilt-shift: optic tilted off-axis with shift direction arrows.
  if (lens.id === 'creative-tilt') {
    return (
      <svg viewBox="0 0 32 32" className="h-9 w-9 shrink-0" aria-hidden="true">
        <path d="M6 5 L9 5 L7 9 Z" fill="rgba(255,255,255,0.55)" />
        <path d="M26 27 L23 27 L25 23 Z" fill="rgba(255,255,255,0.55)" />
        <g transform="rotate(-18 16 16)">
          <ellipse cx="16" cy="16" rx="11" ry="8" fill="none" stroke={ring} strokeWidth="1.6" />
          <ellipse cx="16" cy="16" rx="5.5" ry="3.6" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="1" />
        </g>
        <ellipse cx="16" cy="16" rx="2" ry="2" fill="rgba(255,255,255,0.4)" />
      </svg>
    )
  }
  // Macro probe: long barrel with focus rings and a small front element.
  if (lens.id === 'macro') {
    return (
      <svg viewBox="0 0 32 32" className="h-9 w-9 shrink-0" aria-hidden="true">
        <rect x="3" y="12.5" width="20" height="7" rx="3.5" fill="none" stroke={ring} strokeWidth="1.6" />
        <line x1="9" y1="12.5" x2="9" y2="19.5" stroke="rgba(255,255,255,0.4)" strokeWidth="1" />
        <line x1="13" y1="12.5" x2="13" y2="19.5" stroke="rgba(255,255,255,0.4)" strokeWidth="1" />
        <ellipse cx="25.5" cy="16" rx="3" ry="5" fill="none" stroke="rgba(255,255,255,0.6)" strokeWidth="1.2" />
        <circle cx="25.5" cy="16" r="1.4" fill="rgba(255,255,255,0.5)" />
      </svg>
    )
  }
  // Spherical default (wide cinema, clinical sharp): round front element
  // with a coating-reflection arc in the lens tint.
  return (
    <svg viewBox="0 0 32 32" className="h-9 w-9 shrink-0" aria-hidden="true">
      <circle cx="16" cy="16" r="12" fill="none" stroke={ring} strokeWidth="1.6" />
      <circle cx="16" cy="16" r="7" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="1" />
      <path d="M9 11 A9.5 9.5 0 0 1 16 6.7" fill="none" stroke={ring} strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="16" cy="16" r="2.6" fill="rgba(255,255,255,0.35)" />
    </svg>
  )
}

function CameraMoveGlyph({ preset }: { preset: CameraPreset }) {
  // Reuse the same move glyphs as the original picker for visual continuity.
  const id = preset.id.toLowerCase()
  if (id.includes('orbit') || id.includes('arc')) {
    return (
      <svg viewBox="0 0 32 32" className="h-9 w-9 shrink-0" aria-hidden="true">
        <circle cx="16" cy="16" r="10" fill="none" stroke="rgba(255,255,255,0.55)" strokeWidth="1.2" strokeDasharray="2 3" />
        <circle cx="26" cy="16" r="1.6" fill="rgba(255,255,255,0.75)" />
      </svg>
    )
  }
  if (id.includes('pan') || id.includes('whip')) {
    return (
      <svg viewBox="0 0 32 32" className="h-9 w-9 shrink-0" aria-hidden="true">
        <path d="M4 16 A12 12 0 0 1 28 16" fill="none" stroke="rgba(255,255,255,0.55)" strokeWidth="1.2" />
        <path d="M25 13 L29 16 L25 19 Z" fill="rgba(255,255,255,0.75)" />
      </svg>
    )
  }
  if (id.includes('tilt')) {
    return (
      <svg viewBox="0 0 32 32" className="h-9 w-9 shrink-0" aria-hidden="true">
        <line x1="16" y1="4" x2="16" y2="28" stroke="rgba(255,255,255,0.5)" strokeWidth="1.2" strokeDasharray="2 3" />
        <path d="M14 6 L16 2 L18 6 Z" fill="rgba(255,255,255,0.75)" />
      </svg>
    )
  }
  if (id.includes('crane') || id.includes('pedestal') || id.includes('drone') || id.includes('top-down')) {
    return (
      <svg viewBox="0 0 32 32" className="h-9 w-9 shrink-0" aria-hidden="true">
        <line x1="16" y1="4" x2="16" y2="28" stroke="rgba(255,255,255,0.5)" strokeWidth="1.2" strokeDasharray="2 3" />
        <rect x="12" y="6" width="8" height="6" rx="1" fill="rgba(255,255,255,0.7)" />
      </svg>
    )
  }
  if (id.includes('push') || id.includes('pull') || id.includes('dolly') || id.includes('zoom') || id.includes('rack') || id.includes('blur') || id.includes('macro') || id.includes('fisheye')) {
    return (
      <svg viewBox="0 0 32 32" className="h-9 w-9 shrink-0" aria-hidden="true">
        <circle cx="16" cy="16" r="9" fill="none" stroke="rgba(255,255,255,0.55)" strokeWidth="1.2" />
        <circle cx="16" cy="16" r="3" fill="rgba(255,255,255,0.85)" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 32 32" className="h-9 w-9 shrink-0" aria-hidden="true">
      <circle cx="16" cy="16" r="9" fill="none" stroke="rgba(255,255,255,0.45)" strokeWidth="1" />
      <circle cx="16" cy="16" r="3" fill="rgba(255,255,255,0.8)" />
    </svg>
  )
}

/** Shot optics picker — 4 columns (Camera move / Lens / Focal length / Aperture)
    matching the Cinema Studio reference. Apply updates the active shot's plan. */
export default function CameraPresetPicker({ current, onApply, disabled = false }: Props) {
  const { catalog, loading, error, retry } = useCameraPresets()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All')
  const [moveId, setMoveId] = useState('')
  const [lensId, setLensId] = useState('')
  const [focalId, setFocalId] = useState('')
  const [apertureId, setApertureId] = useState('')
  const [draft, setDraft] = useState<CameraPlan | null>(null)
  const [applied, setApplied] = useState(false)

  const moveCategories = useMemo(() => ['All', ...new Set((catalog?.presets ?? []).map((p) => p.category))], [catalog])
  const lensCategories = useMemo(() => ['All', ...new Set((catalog?.lenses ?? []).map((l) => l.category))], [catalog])
  const filteredMoves = useMemo(() => {
    const items = catalog?.presets ?? []
    return items.filter((preset) =>
      (category === 'All' || preset.category === category) &&
      `${preset.label} ${preset.description}`.toLowerCase().includes(search.toLowerCase().trim()),
    )
  }, [catalog, category, search])

  const selectedMove = (catalog?.presets ?? []).find((p) => p.id === moveId)
  const selectedLens = (catalog?.lenses ?? []).find((l) => l.id === lensId)
  const selectedFocal = (catalog?.focal_lengths ?? []).find((f) => f.id === focalId)
  const selectedAperture = (catalog?.apertures ?? []).find((a) => a.id === apertureId)

  const handlePickMove = (preset: CameraPreset) => {
    if (disabled) return
    setMoveId(preset.id)
    setDraft((prev) => ({ ...(prev || current), camera: preset.camera }))
    setApplied(false)
  }
  const handlePickLens = (lens: CameraLens) => {
    if (disabled) return
    setLensId(lens.id)
    setDraft((prev) => ({ ...(prev || current), lens: lens.lens_language }))
    setApplied(false)
  }
  const handlePickFocal = (focal: CameraFocalLength) => {
    if (disabled) return
    setFocalId(focal.id)
    setDraft((prev) => ({ ...(prev || current), focal_length: `${focal.mm}mm` }))
    setApplied(false)
  }
  const handlePickAperture = (aperture: CameraAperture) => {
    if (disabled) return
    setApertureId(aperture.id)
    setDraft((prev) => ({ ...(prev || current), aperture: aperture.f_stop }))
    setApplied(false)
  }

  const canApply = !disabled && Boolean(draft)
  const summary = [
    selectedMove?.label,
    selectedLens?.label,
    selectedFocal ? `${selectedFocal.mm}mm` : null,
    selectedAperture?.f_stop,
  ].filter(Boolean).join(' · ')

  return (
    <section aria-label="Shot optics" className="liquid-panel relative overflow-hidden">
      <span aria-hidden="true" className="liquid-shimmer" />
      <span aria-hidden="true" className="liquid-edge" />
      <span aria-hidden="true" className="liquid-spec" />
      <span aria-hidden="true" className="liquid-glow" />
      <div className="relative z-10 space-y-4 p-4 sm:p-5">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-amber-100">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-amber-200/10 ring-1 ring-amber-200/30">
              <Camera size={15} aria-hidden="true" />
            </span>
            <h3 className="text-sm font-medium tracking-tight">Shot optics</h3>
          </div>
          <p className="text-[10px] uppercase tracking-[0.18em] text-zinc-500">Camera · Lens · Focal length · Aperture</p>
        </header>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 bg-black/30 px-3 py-2">
          <p className="break-words text-sm leading-snug text-amber-100" aria-live="polite">
            {summary || 'Pick a camera move, lens, focal length, and aperture.'}
          </p>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-zinc-500">
            <label className="relative">
              <span className="sr-only">Search camera presets</span>
              <Search size={12} aria-hidden="true" className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-500" />
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search moves"
                className={`${inputClass} pl-7`}
                style={{ width: '160px', height: '28px' }}
              />
            </label>
          </div>
        </div>

        {loading && <p role="status" className="text-sm text-zinc-400">Loading camera presets…</p>}
        {error && (
          <div role="alert" className="rounded-md border border-amber-200/30 bg-amber-200/10 p-3 text-sm text-amber-100">
            <p>{error}</p>
            <button type="button" onClick={retry} className="mt-2 underline underline-offset-4">Retry camera presets</button>
          </div>
        )}

        {!loading && !error && catalog && (
          <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-4">
            <ColumnCard
              title="Camera"
              items={filteredMoves}
              selectedId={moveId}
              onSelect={handlePickMove}
              filterValue={category}
              onFilterChange={setCategory}
              filterOptions={moveCategories}
              selectedIdForFilter={category}
              disabled={disabled}
              renderItem={(preset, active) => (
                <>
                  <CameraMoveGlyph preset={preset} />
                  <span className="min-w-0 flex-1">
                    <span className={`block truncate text-xs font-semibold uppercase tracking-[0.06em] ${active ? 'text-amber-100' : 'text-zinc-200'}`}>{preset.label}</span>
                    <span className="mt-0.5 block truncate text-[10px] text-zinc-500">{preset.category}</span>
                  </span>
                  {active && <Check size={12} className="shrink-0 text-amber-200" aria-hidden="true" />}
                </>
              )}
            />

            <ColumnCard
              title="Lens"
              items={catalog.lenses ?? []}
              selectedId={lensId}
              onSelect={handlePickLens}
              filterValue="All"
              onFilterChange={() => {}}
              filterOptions={lensCategories}
              selectedIdForFilter=""
              disabled={disabled}
              renderItem={(lens, active) => (
                <>
                  <LensGlyph lens={lens} />
                  <span className="min-w-0 flex-1">
                    <span className={`block truncate text-xs font-semibold uppercase tracking-[0.06em] ${active ? 'text-amber-100' : 'text-zinc-200'}`}>{lens.label}</span>
                    <span className="mt-0.5 block truncate text-[10px] text-zinc-500">{lens.category}</span>
                  </span>
                  {active && <Check size={12} className="shrink-0 text-amber-200" aria-hidden="true" />}
                </>
              )}
            />

            <ColumnCard
              title="Focal length"
              items={catalog.focal_lengths ?? []}
              selectedId={focalId}
              onSelect={handlePickFocal}
              filterValue="All"
              onFilterChange={() => {}}
              filterOptions={['All']}
              selectedIdForFilter=""
              disabled={disabled}
              renderItem={(focal, active) => (
                <>
                  <FocalFovGlyph mm={focal.mm} />
                  <span className="min-w-0 flex-1">
                    <span className={`block truncate text-xs font-semibold uppercase tracking-[0.06em] ${active ? 'text-amber-100' : 'text-zinc-200'}`}>{focal.mm}mm</span>
                    <span className="mt-0.5 block truncate text-[10px] text-zinc-500">{focal.framing_hint}</span>
                  </span>
                  {active && <Check size={12} className="shrink-0 text-amber-200" aria-hidden="true" />}
                </>
              )}
            />

            <ColumnCard
              title="Aperture"
              items={catalog.apertures ?? []}
              selectedId={apertureId}
              onSelect={handlePickAperture}
              filterValue="All"
              onFilterChange={() => {}}
              filterOptions={['All']}
              selectedIdForFilter=""
              disabled={disabled}
              renderItem={(aperture, active) => (
                <>
                  <ApertureGlyph aperture={aperture} />
                  <span className="min-w-0 flex-1">
                    <span className={`block truncate text-xs font-semibold uppercase tracking-[0.06em] ${active ? 'text-amber-100' : 'text-zinc-200'}`}>{aperture.f_stop}</span>
                    <span className="mt-0.5 block truncate text-[10px] text-zinc-500">{aperture.depth_hint}</span>
                  </span>
                  {active && <Check size={12} className="shrink-0 text-amber-200" aria-hidden="true" />}
                </>
              )}
            />
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-white/10 pt-4">
          <button
            type="button"
            disabled={!canApply}
            onClick={() => { if (draft) { onApply(draft); setDraft(null); setApplied(true) } }}
            className="liquid-btn"
          >
            <Check size={13} aria-hidden="true" />
            Apply to this shot
          </button>
          {applied && <span role="status" className="inline-flex items-center gap-1 text-xs text-amber-100"><Check size={12} aria-hidden="true" /> Optics applied.</span>}
          {(moveId || lensId || focalId || apertureId) && (
            <button
              type="button"
              disabled={disabled}
              onClick={() => {
                setMoveId(''); setLensId(''); setFocalId(''); setApertureId('')
                setDraft({ camera: '', framing: '' })
                setApplied(false)
              }}
              className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-300 hover:bg-white/[0.08] disabled:opacity-40"
            >
              <X size={11} aria-hidden="true" />
              Clear selections
            </button>
          )}
        </div>

        <details className="border-t border-white/10 pt-3">
          <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-500 hover:text-zinc-300">Current shot direction</summary>
          <div className="mt-2 space-y-1 text-xs leading-relaxed text-zinc-300">
            {current.camera && <p><span className="text-amber-100/70">Camera:</span> {current.camera}</p>}
            {current.framing && <p><span className="text-amber-100/70">Framing:</span> {current.framing}</p>}
            {current.lens && <p><span className="text-amber-100/70">Lens:</span> {current.lens}</p>}
            {current.focal_length && <p><span className="text-amber-100/70">Focal length:</span> {current.focal_length}</p>}
            {current.aperture && <p><span className="text-amber-100/70">Aperture:</span> {current.aperture}</p>}
          </div>
        </details>
      </div>
    </section>
  )
}