# Studio App UI/UX Upgrade Plan

## Overview
Transform the studio app into a high-end, cinematic post-production suite with dark, editorial aesthetics.

## Design System Created ✅
- `/studio-app/src/styles/design-system.css` - Complete design system with:
  - Color palette (deep navy blacks, purple accents)
  - Typography system (Inter font, proper sizing)
  - Component styles (cards, buttons, badges, panels)
  - Utility classes
  - Animations and transitions

## Implementation Status

### Phase 1: Foundation ✅
- [x] Create design system CSS
- [x] Import design system into index.css
- [x] Update body background to deep navy black
- [x] Update scrollbar styling

### Phase 2: Global Navigation (TODO)
Components to update:
- Main navigation/router
- Room switcher
- Project header
- Session debrief icon

Changes needed:
- Replace tab bars with left sidebar or slim top nav
- Room names: Study, Writer, Previs, Production, Screening, Crew
- Current room: accent left border (#a78bfa), not background fill
- Project name at top (truncated if long)
- Director Intent summary (1-line: genre + emotional target)
- Session Debrief icon (clock/document) - quiet, not primary

### Phase 3: Cards and Panels (TODO)
Apply to all card/panel components:
- Background: #0f172a
- Border: #1e293b
- Border-radius: 8px
- Hover: border shifts to #334155
- No box shadows - use border + background contrast
- Panel headers: uppercase dimmed label above larger title
- 20px padding inside panels
- Section dividers: 1px #1e293b line

Components to update:
- All `.glass-panel` and `.glass-card` classes
- All `.cinematic-panel` classes
- Scene cards
- Intelligence panels
- Export panels
- Pitch deck panels

### Phase 4: Buttons (TODO)
Update all button styles:
- Primary: bg #a78bfa, color #0f172a, no border
- Secondary: bg transparent, border #334155, color #94a3b8
- Destructive: bg transparent, border #f87171, color #f87171
- Ghost: no border, no bg, color #475569, hover #94a3b8
- All: border-radius 5px, font-weight 600, letter-spacing 0.06em, uppercase
- Disabled: opacity 0.4, cursor not-allowed
- Active: scale(0.97)

Components to update:
- All `.btn-primary`, `.btn-ghost` classes
- Render buttons
- Export buttons
- Generate buttons
- Action buttons throughout

### Phase 5: Intelligence Panels (TODO)
Components: Timeline, Continuity, Editorial, DNA, Arc

Changes:
- Consistent header: dimmed uppercase label + larger title + action button right
- Advisory content: 13px, color #cbd5e1, 1.6 line-height
- Uncertainty notes: italic, color #475569
- Section labels: 10px uppercase #475569, 5px margin-bottom
- Expandable sections: chevron, smooth height transition
- NO scores, NO progress bars, NO percentages

### Phase 6: Screening Room (TODO)
Changes:
- Video player: 60% viewport height minimum
- Intelligence panels: below or collapsible right sidebar
- Tab pills (not full tab bars):
  - Active: bg #1e293b, color #f1f5f9
  - Inactive: no bg, color #475569

### Phase 7: Production Board (TODO)
Changes:
- Scene cards: clean grid or list (user toggle)
- Each card: scene title, status badge, shot count, provider badge, last render status
- Status badges: use color system (never text-only)
- Render progress: thin line at bottom, accent color, no percentage text
- Cascade warning: amber left border, not full alert box

### Phase 8: Empty States (TODO)
Apply everywhere:
- Icon: simple geometric shape (circle outline ◌)
- Headline: what this space will show
- Subtext: single next action needed
- Never show raw API states
- Loading: subtle pulse animation, no spinning icons

### Phase 9: Micro-interactions (TODO)
- All transitions: 150-200ms ease
- Hover states on all interactive elements
- Button press: scale(0.97)
- Panel expand/collapse: height transition
- Toast notifications: slide from bottom right, auto-dismiss 6s

### Phase 10: Responsive (TODO)
- Minimum width: 1024px
- Below 1024px: "best experienced on desktop" message
- No mobile-first breakage

## Color System Reference

```css
--bg-primary: #080f1a       /* Deep navy black */
--bg-secondary: #0f172a     /* Slightly lighter */
--bg-elevated: #1e293b      /* Cards, panels */
--border-subtle: #1e293b
--border-default: #334155
--text-primary: #f1f5f9
--text-secondary: #94a3b8
--text-dimmed: #475569
--accent: #a78bfa           /* Purple - intelligence/advisory */
--positive: #4ade80
--warning: #facc15
--caution: #fb923c
--elevated-risk: #f87171    /* Never "error" */
```

## Typography Reference

```css
--font-ui: 'Inter', system-ui
--text-xs: 10px
--text-sm: 11px
--text-base: 13px
--text-md: 14px
--text-lg: 16px
--text-xl: 18px
--text-2xl: 24px
--text-3xl: 30px
```

Display/headlines: letter-spacing 0.02em
Labels/badges: uppercase, 0.1em letter-spacing, 10-11px
Body: 13-14px, 1.6 line-height
Never below 10px

## Implementation Notes

1. **Preserve Functionality**: All changes are purely visual - no logic changes
2. **Test After Each Phase**: Run `npm test -- --run` to ensure no regressions
3. **Gradual Migration**: Can coexist with existing styles during transition
4. **Component-by-Component**: Update one component at a time, test, commit
5. **Use Design System Classes**: Prefer `.card`, `.btn-primary`, etc. from design-system.css

## Next Steps

1. Update main navigation/routing component
2. Update all card components to use new `.card` class
3. Update all buttons to use new button classes
4. Update intelligence panels
5. Update screening room
6. Update production board
7. Update empty states throughout
8. Add micro-interactions
9. Add responsive message
10. Final testing and polish

## Testing Strategy

After each component update:
```bash
npm test -- --run
```

Ensure all 525+ tests still pass.

## Reference Aesthetic

- **A24 Website**: Clean, editorial, sophisticated
- **Blackmagic DaVinci Resolve**: Professional, dark, focused
- **Film Festival Program**: Curated, intentional, high-end

The goal is to create something a director would actually want to sit in front of - not a SaaS dashboard, not a developer tool, but a professional creative suite.
