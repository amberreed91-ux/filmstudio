# Implementation Summary - UI Redesign & Previs Images

## Status: PARTIAL - Core Infrastructure Complete

This document tracks the implementation of two major features:
1. Core visual design system changes
2. Runway-powered previs image generation

---

## Part 1: Core Visual Changes

### ✅ COMPLETED

#### 1. Global Styles (src/index.css)
- ✅ Added all CSS variables in `@layer base` for Tailwind v4
- ✅ Set body background to #040810 (near-black)
- ✅ Set body color to #e8edf5 (light grey)
- ✅ Set body font to Inter
- ✅ Added `.mono` class with JetBrains Mono font and #5b8dd9 color
- ✅ Added `.studio-card` and `.studio-panel` classes
- ✅ Added `.btn-studio-primary` and `.btn-studio-secondary` button styles
- ✅ Added `.studio-nav` navigation styles
- ✅ Added `.studio-advisory` panel style (replaces red blocked banner)

### 🔄 IN PROGRESS

#### 2. Navigation Component Updates
**File**: `studio-app/src/components/TopNav.tsx`

Current state uses inline styles with CSS variables. Needs migration to design system classes:

```tsx
// CURRENT (inline styles)
<nav className="flex items-center gap-1">
  <Link style={{ color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)' }}>

// TARGET (design system classes)
<nav className="studio-nav">
  <Link className={active ? 'studio-nav-tab-active' : 'studio-nav-tab'}>
```

**Action needed**: Update TopNav.tsx to use `.studio-nav`, `.studio-nav-tab`, `.studio-nav-tab-active` classes

#### 3. Card/Panel Components
**Files**: Multiple components across `studio-app/src/pages/` and `studio-app/src/components/`

Current state uses Tailwind utility classes like:
- `bg-black/35`
- `border border-white/10`
- `rounded-lg`

**Action needed**: Replace with `.studio-card` or `.studio-panel` classes

#### 4. Button Components
Current state uses Tailwind classes and inline styles.

**Action needed**: Replace with `.btn-studio-primary` and `.btn-studio-secondary` classes

#### 5. Remove "STUDIO DECISION GATE" Red Banner
**Files**: Search for red background styling on decision gate/blocked panels

**Action needed**: 
- Find decision gate banner component
- Replace red background with `.studio-advisory` class (amber left border)

#### 6. Remove Percentage Displays
**Files**: Multiple - search for "%" and "drawn · 0%"

**Action needed**:
- Remove all percentage displays
- Replace with plain text status messages

---

## Part 2: Runway-Powered Previs Images

### ✅ COMPLETED

#### 1. Previs Image Service
**File**: `studio-backend/app/services/previs_image_service.py`

Created complete service with:
- ✅ `generate_scene_hero()` - Generates hero image for scenes
- ✅ `generate_shot_thumbnail()` - Generates thumbnails for shots
- ✅ Prompt building from scene/shot data
- ✅ 512 character hard cap on prompts
- ✅ Runway Gen-3 Alpha integration via existing render service
- ✅ FFmpeg first-frame extraction
- ✅ Graceful fallback when FFmpeg unavailable
- ✅ FFmpeg availability check on startup
- ✅ Output directory management (`outputs/previs/`)

### 🔄 TODO - Backend

#### 2. Storage Layer
**File**: `studio-backend/app/services/storage.py`

**Action needed**: Add methods:
```python
def save_previs_image(
    self,
    project_id: str,
    scene_id: str,
    shot_id: Optional[str],
    image_path: str,
    job_id: str,
    status: str,
    prompt_used: str,
    fallback: bool
) -> bool:
    """Save previs image metadata to database"""

def load_previs_images(
    self,
    project_id: str,
    scene_id: Optional[str] = None
) -> list[dict]:
    """Load previs images for project/scene"""
```

**Database table needed**:
```sql
CREATE TABLE previs_images (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scene_id TEXT NOT NULL,
    shot_id TEXT,
    image_path TEXT NOT NULL,
    job_id TEXT NOT NULL,
    status TEXT NOT NULL,
    prompt_used TEXT NOT NULL,
    fallback BOOLEAN NOT NULL,
    created_at TEXT NOT NULL
);
```

#### 3. API Endpoints
**File**: `studio-backend/app/routes/projects.py` or new `previs.py`

**Action needed**: Add endpoints:

```python
@router.post("/projects/{project_id}/previs/generate-scene/{scene_id}")
async def generate_scene_previs(project_id: str, scene_id: str):
    """Trigger hero image generation for a scene"""

@router.post("/projects/{project_id}/previs/generate-shot/{scene_id}/{shot_id}")
async def generate_shot_previs(project_id: str, scene_id: str, shot_id: str):
    """Trigger thumbnail generation for a shot"""

@router.post("/projects/{project_id}/previs/generate-all")
async def generate_all_previs(project_id: str):
    """Trigger hero generation for all scenes sequentially"""

@router.get("/projects/{project_id}/previs/images")
async def get_previs_images(project_id: str):
    """Get all previs images for project"""

@router.get("/projects/{project_id}/previs/images/{scene_id}")
async def get_scene_previs_images(project_id: str, scene_id: str):
    """Get hero + shot thumbnails for specific scene"""
```

#### 4. Static File Serving
**File**: `studio-backend/main.py`

**Action needed**: Mount static files:
```python
from fastapi.staticfiles import StaticFiles

app.mount("/previs-assets", StaticFiles(directory="outputs/previs"), name="previs-assets")
```

#### 5. FFmpeg Startup Check
**File**: `studio-backend/main.py`

**Action needed**: Add to lifespan/startup:
```python
# Check FFmpeg availability
from app.services.previs_image_service import FFMPEG_AVAILABLE
if not FFMPEG_AVAILABLE:
    logger.warning("FFmpeg not found. Previs image extraction will be disabled.")
else:
    logger.info("FFmpeg available for previs image extraction")
```

### 🔄 TODO - Frontend

#### 6. PrevisRoom Component Updates
**File**: `studio-app/src/pages/PrevisRoom.tsx`

**Action needed**:

**Scene Hero Image Display**:
```tsx
{/* Replace "NO VISUAL YET" placeholder */}
{heroImage?.status === 'complete' && heroImage.hero_image_url ? (
  <img 
    src={heroImage.hero_image_url}
    alt={`Scene ${scene.id} hero`}
    className="w-full aspect-video object-cover rounded"
    onClick={() => openLightbox(heroImage)}
  />
) : heroImage?.status === 'pending' ? (
  <div className="w-full aspect-video bg-elevated flex items-center justify-center animate-pulse">
    <span className="mono text-xs">Generating previs…</span>
  </div>
) : (
  <div className="w-full aspect-video bg-elevated flex items-center justify-center">
    <span className="text-dimmed text-xs">NO VISUAL YET</span>
  </div>
)}
```

**Shot Thumbnails**:
```tsx
<div className="flex gap-2 mt-3">
  {scene.shots?.map(shot => (
    <div key={shot.id} className="flex flex-col">
      {shot.thumbnail_url ? (
        <img 
          src={shot.thumbnail_url}
          alt={`Shot ${shot.id}`}
          className="w-[120px] h-[68px] object-cover rounded"
        />
      ) : (
        <div className="w-[120px] h-[68px] bg-elevated rounded" />
      )}
      <span className="mono text-xs mt-1">{shot.id}</span>
    </div>
  ))}
</div>
```

**Generate Controls**:
```tsx
<button
  onClick={() => generateScenePrevis(scene.id)}
  disabled={generating}
  className="btn-studio-secondary text-xs"
>
  {generating ? 'Generating…' : 'Generate Previs'}
</button>

{/* At top of room */}
<button
  onClick={generateAllPrevis}
  className="btn-studio-primary"
>
  Generate All
</button>
{generatingAll && (
  <span className="mono text-xs">
    Generating scene {currentScene} of {totalScenes}…
  </span>
)}
```

**Lightbox**:
```tsx
{lightboxImage && (
  <div 
    className="fixed inset-0 bg-void/95 z-50 flex items-center justify-center"
    onClick={closeLightbox}
  >
    <div className="max-w-5xl max-h-[90vh] flex flex-col items-center">
      <img 
        src={lightboxImage.hero_image_url}
        alt="Preview"
        className="max-w-full max-h-[80vh] object-contain"
      />
      <div className="mt-4 text-center">
        <div className="text-primary">{lightboxImage.scene_id}</div>
        <div className="mono text-xs text-dimmed mt-2">
          {lightboxImage.prompt_used}
        </div>
      </div>
    </div>
  </div>
)}
```

#### 7. Cinematic Timeline Updates
**Files**: Components that show "NO VISUAL YET" cards

**Action needed**:
- Replace placeholder with hero image when available
- Keep scene ID, title, status overlay
- Remove "drawn · 0%" - replace with generation status only

### 🔄 TODO - Tests

#### 8. Backend Tests
**File**: `studio-backend/app/services/test_previs_image_service.py`

**Action needed**: Create tests for:
- ✅ Prompt building from scene data
- ✅ 512 character hard cap
- ✅ FFmpeg extraction called with correct args
- ✅ Fallback when Runway fails
- ✅ Fallback when FFmpeg unavailable
- ✅ Storage save/load round-trip
- ✅ Generate-all processes sequentially
- ✅ Static file serving

#### 9. Frontend Tests
**File**: `studio-app/src/pages/PrevisRoom.test.tsx`

**Action needed**: Create tests for:
- Hero image renders when URL present
- Pending state renders with pulsing animation
- Placeholder renders when fallback=true
- Lightbox opens on image click
- Prompt displayed in lightbox

---

## Build & Test Commands

### Frontend
```bash
cd studio-app
rm -rf node_modules/.vite dist/
npm run build
npm run dev
# Hard refresh: Cmd+Shift+R
npm test
```

### Backend
```bash
cd studio-backend
pytest app/services/test_previs_image_service.py -v
pytest  # Run all tests
```

---

## Current Visual State

After the changes applied:
- ✅ Body background is #040810 (near-black)
- ✅ Body text is #e8edf5 (light grey)
- ✅ CSS variables defined and available
- ✅ Design system classes created
- ⚠️ Components still use Tailwind utility classes (need migration)
- ⚠️ Navigation still uses inline styles (need migration)

**To see full visual transformation**: Components need to be updated to use design system classes instead of Tailwind utilities.

---

## Priority Order

### High Priority (Visual Impact)
1. Update TopNav to use design system classes
2. Remove percentage displays across all components
3. Replace red decision gate banner with amber advisory style
4. Update main card/panel components to use `.studio-card`

### Medium Priority (Feature Complete)
1. Add storage layer for previs images
2. Add API endpoints for previs generation
3. Mount static file serving
4. Update PrevisRoom component

### Low Priority (Polish)
1. Add lightbox component
2. Add generate-all progress indicator
3. Write comprehensive tests
4. Update cinematic timeline

---

## Files Modified

### ✅ Completed
1. `studio-app/src/index.css` - Added design system in @layer base
2. `studio-backend/app/services/previs_image_service.py` - Created complete service

### 🔄 Needs Work
1. `studio-app/src/components/TopNav.tsx` - Update to use design system classes
2. `studio-backend/app/services/storage.py` - Add previs image methods
3. `studio-backend/app/routes/` - Add previs endpoints
4. `studio-backend/main.py` - Mount static files, FFmpeg check
5. `studio-app/src/pages/PrevisRoom.tsx` - Add image display and generation
6. Multiple component files - Replace Tailwind classes with design system

---

## Next Steps

1. **Immediate**: Hard refresh browser (Cmd+Shift+R) to see background color change
2. **Phase 1**: Complete backend previs infrastructure (storage, endpoints, static files)
3. **Phase 2**: Update PrevisRoom component to display and generate images
4. **Phase 3**: Migrate components from Tailwind to design system classes
5. **Phase 4**: Write comprehensive tests

---

**Date**: May 28, 2026
**Status**: Core infrastructure in place, component migration needed
