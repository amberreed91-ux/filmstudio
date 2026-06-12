# CRITICAL: Health Score Removal Guide

## ⚠️ IMMEDIATE ACTION REQUIRED

All numeric health scores, progress bars, and percentage displays must be removed from the Studio app. This violates the core Studio Brain philosophy.

---

## Files Requiring Immediate Updates

### 1. StudioOverview.tsx ✅ IDENTIFIED
**Location**: Lines 147-157 (healthCards calculation)
**Current Code**:
```typescript
const healthCards = useMemo(() => {
  const storyScore = clampPercent((asNumber(progressionReport.progression_score) ?? 0.6) * 100)
  const continuityScore = clampPercent((asNumber(continuityReport.continuity_score) ?? 0.6) * 100)
  const flowScore = clampPercent((asNumber(sequenceFlow.flow_score) ?? 0.65) * 100)
  const endingScore = clampPercent((asNumber(endingImpact.impact_score) ?? 0.65) * 100)
  const cinematicScore = clampPercent((flowScore + endingScore) / 2)
  const totalScenes = asNumber(productionSummary.total_scenes) ?? scenes.length
  const lockedScenes = asNumber(productionSummary.locked_scenes) ?? approvedScenesCount
  const productionScore = totalScenes > 0 ? clampPercent((lockedScenes / totalScenes) * 100) : 0
  const statusFor = (score: number) => (score >= 80 ? 'Strong' : score >= 60 ? 'Watch' : 'Needs Focus')
  return [
    { label: 'Story Health', score: Math.round(storyScore), status: statusFor(storyScore), accent: 'text-emerald-300', bar: 'from-emerald-400 to-emerald-200' },
    { label: 'Continuity Health', score: Math.round(continuityScore), status: statusFor(continuityScore), accent: 'text-amber-300', bar: 'from-amber-400 to-amber-200' },
    { label: 'Cinematic Health', score: Math.round(cinematicScore), status: statusFor(cinematicScore), accent: 'text-cyan-300', bar: 'from-cyan-400 to-cyan-200' },
    { label: 'Production Status', score: Math.round(productionScore), status: totalScenes > 0 ? statusFor(productionScore) : 'No Data', accent: 'text-indigo-300', bar: 'from-indigo-400 to-indigo-200' },
  ]
}, [...])
```

**Rendered at**: Line 432
```tsx
<section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
  {healthCards.map((card) => (
    <MetricCard
      key={card.label}
      label={card.label}
      value={card.score}
      status={card.status}
      accentClass={card.accent}
      barClass={card.bar}
    />
  ))}
</section>
```

**REPLACE WITH**:
```typescript
const studioAdvisories = useMemo(() => {
  const totalScenes = asNumber(productionSummary.total_scenes) ?? scenes.length
  const lockedScenes = asNumber(productionSummary.locked_scenes) ?? approvedScenesCount
  
  // Story advisory
  const storyText = totalScenes > 0 
    ? "Story structure has been established. Writer's Room active."
    : "No story structure yet. Start in Writer's Room to begin."
  
  // Continuity advisory
  const continuityText = asNumber(continuityReport.continuity_score) > 0.8
    ? "No continuity conflicts detected in current graph."
    : "Continuity intelligence building. Review scenes for consistency."
  
  // Cinematic advisory
  const cinematicText = totalScenes > 3
    ? "Visual intelligence building. Add more scenes to deepen reads."
    : "Not enough scenes for cinematic analysis. Generate more scenes."
  
  // Production advisory
  const productionText = lockedScenes > 0
    ? `${lockedScenes} of ${totalScenes} scenes approved and locked.`
    : totalScenes > 0
      ? "No scenes approved yet. Review in Previs Room."
      : "No production data. Generate scenes to begin."
  
  return [
    { label: 'Story Structure', text: storyText, accent: 'text-emerald-300', border: 'border-emerald-300/30' },
    { label: 'Continuity Graph', text: continuityText, accent: 'text-amber-300', border: 'border-amber-300/30' },
    { label: 'Visual Intelligence', text: cinematicText, accent: 'text-cyan-300', border: 'border-cyan-300/30' },
    { label: 'Production Status', text: productionText, accent: 'text-indigo-300', border: 'border-indigo-300/30' },
  ]
}, [...])
```

**And render as**:
```tsx
<section className="grid grid-cols-1 gap-4 md:grid-cols-2">
  {studioAdvisories.map((advisory) => (
    <div key={advisory.label} className={`rounded-2xl border ${advisory.border} bg-black/35 p-4 shadow-[0_20px_70px_rgba(0,0,0,0.28)] backdrop-blur-xl`}>
      <div className={`text-xs uppercase tracking-[0.14em] ${advisory.accent}`}>{advisory.label}</div>
      <div className="mt-2 text-sm text-zinc-200 leading-relaxed">{advisory.text}</div>
    </div>
  ))}
</section>
```

---

### 2. Other Percentage Displays in StudioOverview.tsx

**Line 503**: Completion percentage display
```tsx
<div>Completion: <span className="text-zinc-100">{`${Math.round(clampPercent((asNumber(filmProgress.completion_percent) ?? 0) * 100))}%`}</span></div>
```
**REPLACE WITH**:
```tsx
<div>Status: <span className="text-zinc-100">{filmProgress.ready_to_screen ? 'Ready to screen' : 'In production'}</span></div>
```

**Line 509-511**: Circular progress indicator
```tsx
<div className="relative grid h-24 w-24 place-items-center rounded-full border border-cyan-300/40">
  <div className="absolute inset-1 rounded-full border-4 border-cyan-300/20 border-t-cyan-300" />
  <span className="text-sm font-semibold text-cyan-200">{`${Math.round(clampPercent((asNumber(filmProgress.completion_percent) ?? 0) * 100))}%`}</span>
</div>
```
**REMOVE ENTIRELY** or replace with simple status indicator:
```tsx
<div className="flex items-center gap-2">
  <div className={`w-3 h-3 rounded-full ${filmProgress.ready_to_screen ? 'bg-emerald-400' : 'bg-amber-400'}`} />
  <span className="text-sm text-zinc-200">{filmProgress.ready_to_screen ? 'Complete' : 'In Progress'}</span>
</div>
```

**Line 485**: Studio intelligence score
```tsx
<div className="text-xs text-cyan-100">
  score: <span className="font-semibold">{studioIntelligence.studio_intelligence_score.toFixed(3)}</span>
</div>
```
**REPLACE WITH**:
```tsx
<div className="text-xs text-cyan-100">
  {studioIntelligence.committed_references > 0 ? 'Intelligence active' : 'Building intelligence'}
</div>
```

**Line 565**: Intelligence score in memory tab
```tsx
<div className="rounded-xl border border-white/10 bg-black/35 px-3 py-2">Intelligence score: {studioIntelligence.studio_intelligence_score.toFixed(3)}</div>
```
**REPLACE WITH**:
```tsx
<div className="rounded-xl border border-white/10 bg-black/35 px-3 py-2">
  Intelligence: {studioIntelligence.committed_references > 0 ? `${studioIntelligence.committed_references} patterns committed` : 'No patterns yet'}
</div>
```

---

### 3. Dashboard.tsx

**Search for**: Any instances of progress bars, percentages, or numeric scores
**Pattern to find**: `progress`, `%`, `score`, `health`

**Line 265** (example from earlier read):
```tsx
<div className="text-xs" style={{ color: 'var(--text-muted)' }}>
  {job.progress}%
</div>
```
**REPLACE WITH**:
```tsx
<div className="text-xs" style={{ color: 'var(--text-muted)' }}>
  {job.status}
</div>
```

---

### 4. Components to Search and Update

Run these searches across the codebase:

```bash
# Find all progress percentage displays
grep -r "progress.*%" studio-app/src/

# Find all score displays
grep -r "score.*:" studio-app/src/

# Find all health displays
grep -r "Health" studio-app/src/

# Find all percentage displays
grep -r "%" studio-app/src/components/
grep -r "%" studio-app/src/pages/
```

---

## Replacement Patterns

### Pattern 1: Numeric Score → Plain Language
**Before**: `Story Health: 80 — STRONG`
**After**: `Story structure has been established. Writer's Room active.`

### Pattern 2: Progress Bar → Thin Line (no percentage)
**Before**: `<div className="progress-bar"><div style={{width: '80%'}}>80%</div></div>`
**After**: `<div className="progress-line"><div className="progress-line-fill" style={{width: '80%'}} /></div>`

### Pattern 3: Percentage Display → Status Text
**Before**: `Completion: 75%`
**After**: `Status: In production` or `Status: Ready to screen`

### Pattern 4: Numeric Confidence → Qualitative
**Before**: `Confidence: 0.85`
**After**: `Confidence: High` or just remove

---

## Testing Checklist

After making changes:

- [ ] Run `npm test` - all tests must pass
- [ ] Visual inspection of all rooms
- [ ] Verify NO numeric scores visible anywhere
- [ ] Verify NO progress bars with percentages
- [ ] Verify NO percentage displays
- [ ] Check Dashboard
- [ ] Check Studio Overview
- [ ] Check Production Board
- [ ] Check Screening Room
- [ ] Check Writer's Room
- [ ] Check Previs Room
- [ ] Check Study Room
- [ ] Check Archive Room

---

## Priority Order

1. **IMMEDIATE**: StudioOverview.tsx health cards (most visible)
2. **HIGH**: Dashboard.tsx render progress
3. **HIGH**: ProductionBoard.tsx scene progress
4. **MEDIUM**: All other components
5. **LOW**: Hidden/dev components

---

## Notes

- This is NON-NEGOTIABLE per user requirements
- All numeric health scores violate Studio Brain philosophy
- Use plain-language advisory reads instead
- Focus on what IS happening, not what percentage is complete
- Be honest about uncertainty and limitations
