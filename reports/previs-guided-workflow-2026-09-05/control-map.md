# Guided Previs control map

This is a presentation change. Existing generation, approval, retry, and assembly handlers remain intact. Navigation does not invoke production operations.

| Capability | Location |
| --- | --- |
| Select scene; switch/add shots | Shared scene/shot strip, above every step |
| Story intention, framing/action | Step 1: Plan the shot |
| All 13 detailed shot planning fields | Step 1 → Detailed shot planning |
| Recommend shot count; staging panel | Step 1 → Planning assistance |
| Generate or change storyboard frame | Step 2 → Create the frame |
| Storyboard image model, seed and seed lock | Step 2 → Image settings |
| Build storyboard blueprint | Step 2 → Build the scene blueprint |
| Blueprint status, per-shot readiness/rationale | Step 2 status + Blueprint details |
| Continuity review and approval | Step 2 → Review continuity → Approve the blueprint |
| Continuity comparisons, individual issue actions | Step 2 → Inspect continuity issues and comparisons |
| Edit render prompt; enhancement indicator; original prompt/revert | Step 3 → Direct the action |
| Actual duration and duration presets | Step 3 → Duration |
| Duration recommendation, custom recommendation edit/shorten/lengthen/accept | Step 3 → Help choosing a duration |
| Render provider, resolution, video seed/randomize | Step 3 → Advanced render settings; current provider/quality/seed also shown when collapsed |
| Voice, music, SFX switches and prompts | Step 3 → Advanced render settings → Audio generation |
| AI prompt enhancement | Step 3 → Advanced render settings |
| Create new take | Step 3 → Render take |
| Saved media playback | Wide current-shot preview; storyboard step specifically shows storyboard frame |
| Take preview and deletion | Step 4 → Takes for shot |
| Prior render prompts, deletion, adherence retry | Step 4 → Render history and retries |
| Assemble scene; Screening navigation | Step 4 → Assemble your scene; uses latest completed take per shot per existing backend behavior |
| Whole-scene generation, score mode/manual path, assembly status | Step 4 → Generate a whole scene; explicitly creates new footage |
| Canonical workflow and all package/revision/approval actions | Step 4 → Production handoff, kept mounted |
| Cinematography, casting, performance/audio, production design, colorist panels | Creative departments and notes |
| Director notes and shot signals | Creative departments and notes |
| Backend health, last check, render stage indicators | Studio status |
| Active errors, success, running job status | Shared status area above preview; remains visible across steps |
| Production scan, share, switch film | Film actions in project context bar |
| Room navigation | Existing desktop rail with accessible labels; in-flow Rooms disclosure on mobile |
| Header search, status, health/restart, settings, notifications, Co-Director, account | Desktop header; Studio tools disclosure on narrow viewports |
| Expandable crew presence | In-flow footer of Previs, default compact; global room preference unchanged |

Step navigation has an ordered list and aria-current="step". Continue/Next focuses the newly displayed heading; top navigation retains focus on its button. Duration and resolution presets expose aria-pressed. All step sections stay mounted so current UI choices and panel state survive navigation.
