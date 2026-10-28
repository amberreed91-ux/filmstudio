# Studio App UI/UX Upgrade Plan

**Status:** active · **Last aligned:** 2026-10-28 · **Scope:** `studio-app`

This is the source of truth for visual work in the studio. It replaces the
earlier design-system attempt: that stylesheet was never imported and has been
deleted, and its accent is no longer the product accent. Do not recreate or
import it.

---

## 1. Source of truth

| Concern | Location |
|---|---|
| Live stylesheet | `src/styles/studio-pro-design-system.css` (imported by `src/index.css`) |
| Base tokens + semantic fills | `src/index.css` → `@theme` and `@layer base` |
| Secondary tokens | `src/styles/design-tokens.css`, `src/styles/cinematic.css` |
| Button primitive | `src/components/ui/Button.tsx` |
| Type-scale guard | `check_type_scale.cjs` |
| Button/async guard | `check_button_conventions.cjs` + `check_button_conventions.self-test.cjs` |
| Room registry | `src/routes.tsx` (`placement: primary` is the creator's critical path) |

If a token is missing, add it to `src/index.css`. Never create a second
design-system stylesheet; two sources of truth for tokens is what caused the
silent transparent-background bug this plan exists to prevent.

---

## 2. Color system

The product accent is **pale gold** (`--accent`). No other accent may drive a
primary action; atmospheric hues from procedural backdrops
(`lib/proceduralBackdrops.ts`, `SpatialStudioCanvas`) are scenery, not UI color.

| Token | Value | Use |
|---|---|---|
| `--accent` | `#ffd165` | Primary action, active selection, focus ring |
| `--success` | `#10b981` | Passed, verified, saved |
| `--warning` | `#f59e0b` | Attention, caution, not-yet |
| `--accent-blue` | `#5b8dd9` | Informational severity, mono readouts |
| `--color-tertiary` | `#34d399` | Secondary confirmation |
| `--bg-primary` | `#080f1a` | App background |
| `--bg-secondary` | `#0d1526` | Panels |
| `--bg-elevated` | `#111d2e` | Cards, raised surfaces |
| `--border-subtle` | `#1a2744` | Hairlines |
| `--text-primary` | `#e8edf5` | Primary copy |
| `--text-secondary` | `#8896b0` | Secondary copy |
| `--text-dimmed` | `#4a5568` | Metadata only |

Rules:
- Gold is for one primary action per surface. Never use gold for warnings.
- Status color is never the only signal: pair it with a word ("approved",
  "needs attention", "not yet").
- No numeric health scores, percentages, or 0–100 ratings in UI copy. See
  `AGENTS.md` co-director rules.

---

## 3. Typography scale

| Step | Size | Use |
|---|---|---|
| micro-label | `10px` | Uppercase + tracked labels, chips, monospace telemetry |
| meta | `11px` | Captions, timestamps, secondary metadata |
| body | `12px` | Descriptions, advisories, button labels (`text-xs`) |
| emphasis | `14px+` | Headings and room titles |

Hard rules (enforced by `npm run check:type-scale`):
1. **10px is a hard floor.** Anything below fails the build. The only
   allowlisted exception is the 9px single letter inside the 12×12 keycap in
   `components/Interactive3DLobby.tsx`.
2. **Never render a sentence below 12px.** 10–11px is reserved for uppercase
   labels, monospace codes, chips, and truncation — not prose.
3. **Allowed hidden-surface exception:** `pages/StudioDevTools.tsx` (internal,
   non-product tooling) is reported but not blocking while it carries dense
   diagnostics. This exception must never be copied into a creator-facing room.
4. Use the named steps (`text-xs`, `text-sm`, `text-[11px]`) instead of new
   arbitrary sizes. Add a token before adding a number.

The guard prints non-blocking "reading text under 12px" warnings so the backlog
is visible; drive it to zero in creator-facing surfaces.

---

## 4. Button and async conventions

Enforced by `check_button_conventions.cjs`.

### 4.1 Every button declares a type

```tsx
<button type="button" onClick={open}>Options</button>
```

Omitting `type` makes the button default to `submit` and silently submit a
surrounding form. There are no exceptions; the guard fails the build on an
untyped button anywhere under `src/`.

### 4.2 Every async action reports in-flight state

An async button must, while the action is pending:

| Requirement | Implementation |
|---|---|
| Assistive-tech signal | `aria-busy={pending || undefined}` |
| Re-entry protection | `disabled={pending}` (widen existing disabled conditions, never remove them) |
| Visible feedback | Spinner (`Loader2` with `animate-spin`) or a label change ("Saving…", "Generating…") |
| Stable layout | Keep the button label/width from collapsing mid-flight |

```tsx
<button
  type="button"
  onClick={() => void save()}
  disabled={saving}
  aria-busy={saving || undefined}
>
  {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
  {saving ? 'Saving…' : 'Save'}
</button>
```

Prefer the primitive: `<Button loading={saving} loadingLabel="Saving…">Save</Button>`
already does all of the above.

Async detection covers inline `async`/`await`, the `void promise()` intent
marker, direct handler references, and handlers declared async in the same
file. The guard's default is **fatal repo-wide**; the legacy backlog report was
removed once the migration finished. Do not add an allowlist to dodge it — add
the pending state.

### 4.3 What "async" means here

Anything that awaits a fetch, provider call, file read/write, or state mutation
that can fail or take longer than one frame. Purely local setters (open a
drawer, switch a tab) do not need busy state.

---

## 5. Quality gates

| Command | Gate |
|---|---|
| `npm run check:type-scale` | 10px floor; reports sub-12px prose |
| `npm run check:buttons` | explicit `type`; async `aria-busy` + `disabled` |
| `npm run check:buttons:self-test` | proves the guard still catches regressions |
| `npm run typecheck` | `tsc -b --force` |
| `npm run lint` | ESLint, zero errors **and** zero warnings |
| `npm test -- --run` | Vitest suite |
| `npm run build` | production build |

CI (`.github/workflows/ci.yml`) runs typecheck, lint, both guards, the guard
self-test, and the unit suite on every push and PR; run the production build
before shipping. A red guard is a red build; fix the surface, not the guard.

---

## 6. Current state (2026-10-28)

Done:
- Type-scale sweep across creator-facing text and the 10px floor guard.
- Explicit `type` added to every button repo-wide; button guard wired into CI
  with a self-test.
- In-flight `aria-busy` + disabled state on **every** async action under
  `src/` (231 actions); the guard is fatal repo-wide with no backlog allowance.
  This includes the shared panels: Export, Canonical Workflow, Production
  Queue, Voice Picker, Knowledge Library, Reference Image Generator,
  Generation Readiness, Storyboard Image Prompt, and the collaboration family.
- Dead code removed: the unused top-nav component and the old unimported design-system stylesheet.
- Token definitions consolidated in `src/index.css` so `var(--x)` always
  resolves.
- ESLint at zero errors and zero warnings; `npm run lint`
  (`eslint . --max-warnings 0`) is a blocking CI gate.
- `react-refresh`, React Compiler purity/memoization, effect dependency, and
  `set-state-in-effect` issues resolved repo-wide; helper functions moved into
  `src/lib/*` so component modules export components only.

Open:
1. **Visual regression baseline.** Playwright is installed; add screenshot
   checks for the primary rooms and use
   `reports/ui-audit-2026-10-28/` as the reference set.
2. **Handoff polish.** One status vocabulary and one empty-state pattern across
   Previs → Scenes → Watch → Production Desk.
3. **Type-scale backlog.** Clear the remaining sub-12px reading-text warnings in
   `RenderPromptScopeNote`, `TacticalSideRail`, `PrevisRoom`, and
   `SceneContinuityPanel`; keep `StudioDevTools` allowlisted with its reason.
4. **Co-director presentation.** Keep rendering advisory voice (no scores, no
   generic praise) consistent across the rooms; see `AGENTS.md`.

---

## 7. Working rules for agents and contributors

1. Preserve behavior. Visual/accessibility changes must not alter workflow
   logic, gating, or persistence.
2. Edit the live stylesheet or `index.css`; never add a parallel design system.
3. Do not suppress guards (`eslint-disable`, allowlists, skipped tests). Fix
   the cause.
4. Test after each room-level pass, not only at the end.
5. Prefer one clear primary action per surface; quiet everything else.
6. Legacy documents (`UI_UPGRADE_SUMMARY.md`, `IMPLEMENTATION_SUMMARY.md`) are
   historical records. They describe removed code and must not be used as
   implementation guidance.

---

## 8. Verification sequence

```bash
cd studio-app
node check_button_conventions.cjs
npm run typecheck
npm run lint
npm run test -- --run
npm run build
```

All five must exit `0` before a UI pass is considered complete.
