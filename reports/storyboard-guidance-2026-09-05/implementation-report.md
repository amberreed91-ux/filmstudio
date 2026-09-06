# Storyboard guidance implementation

The Board now begins with the film's scene sequence. Scene wall, Production, and Creative advice expose one workspace at a time. Every scene has a visible review/continue action, keyboard-accessible frame button, and a disclosure for secondary operations. The default page does not mount the queue detail or specialist panels. Character filtering, first-frame generation, script handoff, seed preference, takes review, queue recovery, and basic scene checks remain available. Runtime/completion estimates and invented provider progress have been removed. Video output URLs no longer become image thumbnails; frame loading, unavailable, and uncreated states are explicit.

Previs storyboard preparation now presents four compact selectors—Create frame, Build blueprint, Check continuity, Approve scene—with one active work area. Its sections stay mounted to preserve controls while changing stages. Current backend state suggests a starting stage; the creator can revisit each stage. Continuity comparisons/actions, image settings, seed lock, blueprint information, and approval guards remain accessible. A Board link opens the storyboard stage with project, scene, and requested shot context. Approval matches the current blueprint version before showing the approved state.

Co-director launcher is visible in the shell at all viewport sizes, once per shell. The drawer fits narrow viewports and dynamic viewport height. Crew status uses the project-scoped useCrewPresence hook supplied by root; no mock work, animated fabricated updates, or no-op More menu remains.

Cancel render now invokes cancelRenderJob and refreshes real jobs; it never retries. Responses from a prior project are ignored after a film switch.

## Verification

- Full frontend suite: 702 passed, 80 files.
- Production build passed.
- Touched-file lint: zero errors, two existing/functionality-owner warnings (Previs blueprint selection effect, Drawer input clearing effect).
- Desktop1600, medium900, mobile390: no horizontal overflow. Co-director visible on all tested widths; mobile drawer382px.
- Fixture browser checks passed nine cases: populated frame/MP4 fallback, image failure, character filter, contextual handoff, explicit continuity review and preserved actions, explicit approval, preserved image provider during substage switches, real cancel endpoint once, empty and error states.
- All browser POST/PUT/PATCH/DELETE requests intercepted; no film data edits, provider generation, actual approval, real cancellation, or memory writes.

Screenshots and structured checks are in this directory. Populated screenshots use an existing real project frame served by the fixture, with clearly synthetic scene/job state for verification. Initial live screenshots are also included, but image requests had not finished when captured; use board-populated-desktop/mobile and storyboard-continuity/approved views for layout evaluation.
