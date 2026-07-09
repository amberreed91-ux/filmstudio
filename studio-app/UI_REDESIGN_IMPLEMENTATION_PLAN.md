# Studio App UI Redesign Implementation Plan

## Status: IN PROGRESS

This document tracks the comprehensive UI/UX redesign to transform the Studio app into a high-end professional film production suite (DaVinci Resolve meets film festival operations center aesthetic).

---

## Phase 1: Foundation ✅ COMPLETE

### 1.1 Typography & Fonts ✅
- [x] Added Google Fonts (Inter + JetBrains Mono) to index.html
- [x] Created new design system CSS with proper font variables

### 1.2 Design System ✅
- [x] Created `studio-pro-design-system.css` with:
  - Complete color palette (void, primary, secondary, elevated backgrounds)
  - Typography scale (display, heading, subheading, body, label, mono)
  - Component styles (cards, panels, buttons, badges)
  - Status indicators and data bars
  - Intelligence panels
  - Empty states and loading states
  - Tab pills and expandable sections
  - Toast notifications
  - Progress indicators (thin lines only, NO percentages)
  - Animations (pulse, shimmer, slide-in, fade-in)
  - Utility classes
  - Scrollbar styling

### 1.3 Base Styles ✅
- [x] Updated index.css to import new design system
- [x] Applied base body styles with new color variables

---

## Phase 2: CRITICAL - Remove Health Scores 🚧 IN PROGRESS

### 2.1 Components to Update
- [ ] **StudioOverview.tsx** - Remove "Story Health: 80", "Continuity Health: 100", "Cinematic Health: 50"
- [ ] **Dashboard.tsx** - Remove any numeric health scores
- [ ] **ProjectWorkspace.tsx** - Remove health scores and progress bars
- [ ] **WritersRoom.tsx** - Remove health indicators
- [ ] **ProductionBoard.tsx** - Remove progress percentages
- [ ] **ScreeningRoom.tsx** - Remove score displays
- [ ] **StudyRoom.tsx** - Remove health metrics
- [ ] **PrevisRoom.tsx** - Remove quality scores
- [ ] **ArchiveRoom.tsx** - Remove historical scores

### 2.2 Replacement Pattern
Replace ALL instances of:
- "Story Health: 80 — STRONG" → "Story structure has been established. Writer's Room active."
- "Continuity Health: 100 — STRONG" → "No continuity conflicts detected in current graph."
- "Cinematic Health: 50 — NEEDS FOCUS" → "Visual intelligence building. Add more scenes to deepen reads."
- ANY numeric score → Plain-language advisory read
- ANY progress bar → Thin progress line (no percentage) OR remove entirely
- ANY percentage display → Remove or convert to plain language

---

## Phase 3: Navigation System 🔜 TODO

### 3.1 Top Bar (40px)
- [ ] Create `TopBar.tsx` component
  - Studio logo mark (SVG film frame icon) + "STUDIO" text
  - Project name (center, truncated)
  - Director intent one-liner below project name
  - Session timer (monospace)
  - Session Debrief icon
  - Connection status dot

### 3.2 Room Navigation Bar (48px)
- [ ] Create `RoomNav.tsx` component
  - Horizontal scrollable room tabs
  - Rooms: Lobby | Studio Dashboard | Writer's Room | Production Board | Screening Room | Archive | Project Slate | Previs Room | Approval Room | Study Room | Crew Ops | Cost Manager
  - Active state: bottom border 2px purple, no background
  - Inactive: dimmed text, no background
  - Hover: secondary background
  - Status indicators (left side): "ACTIVE SCENES: 0", "RENDERS: 0"

### 3.3 Stage Breadcrumb Bar (28px)
- [ ] Create `StageBreadcrumb.tsx` component
  - Pill indicators for pipeline stage
  - [OVERVIEW] [CURRENT STEP: SCRIPT] [NEXT: START IN WRITER'S ROOM] [APPROVED: 0]
  - Pill style: border, transparent bg, mono text
  - Active step: purple border and text

### 3.4 Update StudioLayout
- [ ] Integrate TopBar, RoomNav, and StageBreadcrumb
- [ ] Remove old navigation

---

## Phase 4: Studio Dashboard Redesign 🔜 TODO

### 4.1 Project Vitals Section
- [ ] Create "SIGNAL BOARD" panel (monospace readout grid)
- [ ] Create "STUDIO BRAIN STATUS" panel (circular/hexagonal readout)
- [ ] Create "PIPELINE STATUS" panel (vertical pipeline visualization)

### 4.2 Studio Brain Orchestration
- [ ] Scrolling log of intelligence events (monospace)
- [ ] Graph stats panel (right side)

### 4.3 Room Quick Access
- [ ] Grid of room cards (3 per row)
- [ ] Each card: room name, primary question, status, last activity

---

## Phase 5: Lobby Redesign 🔜 TODO

### 5.1 Cinematic Intake Experience
- [ ] Full viewport dark gradient background
- [ ] Large "STUDIO" title (48px, letter-spacing 0.3em)
- [ ] Director Intent capture form (if not set)
- [ ] Project selector (clean list)
- [ ] Technical footer bar

---

## Phase 6: Production Board Redesign 🔜 TODO

### 6.1 Scene Cards
- [ ] Left border color = scene status
- [ ] Card header: Scene ID (mono) + title + provider badge
- [ ] Card body: shot count, render status (text only), last render time
- [ ] Continuity drift indicator (amber pipe)
- [ ] Cascade warning banner
- [ ] Ghost-style action buttons

---

## Phase 7: Screening Room Redesign 🔜 TODO

### 7.1 Layout
- [ ] Left side (65%): video player with dark surround
- [ ] Right side (35%): intelligence sidebar

### 7.2 Intelligence Sidebar
- [ ] Tabs: CONTINUITY | TIMELINE | EDITORIAL | DNA | ARC | MOTIFS
- [ ] Tab style: 9px mono uppercase, active = bottom border purple
- [ ] Consistent panel structure for each intelligence type
- [ ] Advisory items with left border
- [ ] Uncertainty in italic dimmed text

---

## Phase 8: Global Micro-Interactions 🔜 TODO

- [ ] All transitions: 120ms ease
- [ ] Button press: scale(0.97)
- [ ] Card hover: border-color transition
- [ ] Panel expand: smooth height
- [ ] New log entries: fade in
- [ ] Status dots: pulse animation for BUILDING/ACTIVE

---

## Phase 9: Component-by-Component Updates 🔜 TODO

### Components to Update:
- [ ] StudioPanel.tsx
- [ ] CinematicLoading.tsx
- [ ] RenderActivityPanel.tsx
- [ ] DirectorIntentPanel.tsx
- [ ] ContinuityPanel.tsx
- [ ] TimelinePanel.tsx
- [ ] FilmDNAPanel.tsx
- [ ] ArcAnalysisPanel.tsx
- [ ] MotifPanel.tsx
- [ ] SceneCard.tsx
- [ ] ShotCard.tsx
- [ ] ApprovalGate.tsx
- [ ] RenderJobCard.tsx

---

## Phase 10: Testing & Verification 🔜 TODO

- [ ] Run frontend tests: `npm test`
- [ ] Verify all tests pass
- [ ] Visual regression testing
- [ ] Responsive testing (min 1024px)
- [ ] Below 1024px: show "best experienced on desktop" message

---

## Design System Reference

### Colors
```css
--bg-void: #040810
--bg-primary: #080f1a
--bg-secondary: #0d1526
--bg-elevated: #111d2e
--bg-hover: #162236
--border-subtle: #1a2744
--border-default: #243452
--border-active: #2d4470
--text-primary: #e8edf5
--text-secondary: #8896b0
--text-dimmed: #4a5568
--text-mono: #5b8dd9
--accent-purple: #7c6af7
--accent-amber: #e8a020
--accent-green: #2ecc7a
--accent-red: #e05050
--accent-cyan: #38b2c8
```

### Typography
```css
--font-ui: 'Inter', system-ui
--font-mono: 'JetBrains Mono', monospace
--text-display: 24px (room titles)
--text-heading: 15px (panel titles)
--text-subheading: 12px (section headers)
--text-base: 13px (body)
--text-label: 10px (labels)
--text-mono: 12px (readouts)
--text-mono-sm: 9px (small mono)
--text-badge: 9px (badges)
```

### Key Principles
1. **NO numeric health scores** - Use plain-language advisory reads
2. **NO progress bars with percentages** - Use thin progress lines or remove
3. **NO percentage displays** - Convert to plain language
4. **Monospace for technical readouts** - IDs, timecodes, counts
5. **Dark, cinematic, editorial** - NOT a SaaS dashboard
6. **Intricate, technical, purposeful** - Every pixel belongs in post-production

---

## Files Modified

### ✅ Completed
- `studio-app/index.html` - Added Google Fonts
- `studio-app/src/styles/studio-pro-design-system.css` - Created new design system
- `studio-app/src/index.css` - Updated to import new design system

### 🚧 In Progress
- `studio-app/src/pages/Dashboard.tsx` - Removing health scores
- `studio-app/src/pages/StudioOverview.tsx` - Removing health scores

### 🔜 To Do
- All other component files listed above

---

## Next Steps

1. **IMMEDIATE**: Remove all health scores from StudioOverview.tsx
2. **IMMEDIATE**: Remove all health scores from Dashboard.tsx
3. Create new navigation components (TopBar, RoomNav, StageBreadcrumb)
4. Update StudioLayout to use new navigation
5. Redesign Studio Dashboard with new panels
6. Continue through remaining phases

---

## Notes

- This is a UI-only redesign - NO business logic changes
- All existing functionality must continue to work
- All tests must pass after changes
- Focus on visual transformation to high-end professional aesthetic
