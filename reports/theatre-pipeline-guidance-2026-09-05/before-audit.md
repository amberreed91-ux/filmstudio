# Studio pipeline audit — 2026-09-05

Read-only source audit of the current dirty repository. No project data modified and no provider calls made. Line references describe the pre-repair state inspected in this audit; implementation is proceeding in parallel.

## Recommended room ownership

| Stage | Owner / route | Clear user task |
|---|---|---|
| Prepare | Study `/studio/study-room` | Add project Bibles and reference files; inspect what was learned; explicitly save creative memories. |
| Write | The Page `/studio/writers-room` | Import or edit the script; select a scene; create/save character production profiles and voices. |
| Plan and render | Previs `/studio/project/:projectId/previs` | Plan shots, build/review/approve storyboard, direct takes, review and assemble scene. |
| Finish | Theatre `/studio/screening-room` | Watch footage, review/revise, approve the correct output, assemble film and download actual delivery assets. |
| Optional side room | Universe `/studio/universe-graph` | Explore story entities and relationships. Its graph characters are not the editable production profiles. |
| Optional monitor | Production Board `/studio/production-board` | Observe all scenes and render jobs; open the selected scene in Write or Previs. |
| Library | Archive `/studio/archive` | Browse films/assets and retrieve export information; distinguish actual deletion from archiving. |
| Advanced workspace | `/studio/project/:projectId` | Production administration and real workflow gates. Separate local planning checklist from actual approvals. |

Simplest shared guide: **1 Prepare → 2 Write → 3 Storyboard & render → 4 Review & deliver**. A compact disclosure explains the current room, next action, and optional side rooms. Links preserve `project_id`, `scene`, and `shot` through `withProductionContext`. Do not invent completion checkmarks or require a new lock. Character profiles belong inside Write, avoiding another compulsory room. Previs already contains the storyboard; no separate storyboard page is needed.

## Priority repairs

1. **Write handoffs target the wrong scene.** WritersRoom starts `activeSceneId=null` and picks the first scene instead of reading `scene` or legacy `scene_id` (113,229–236). ProductionBoard uses `scene_id` at 478. Root is repairing this and project load/reset behavior. `activeProjectId || route || query` in Write:102, Study:264, Universe:90 and Board:220 can also override an explicit film link with the previous film. Theatre correctly uses `resolveActiveProjectId` at 179–183 and loads the selected route film.

2. **Write can falsely show Saved or drop recent edits.** Its save ignores `{error}` returned by `updateScene` and always clears dirty state (WritersRoom:303–310; studioApi:2572–2591). Navigating away cancels the 3-second timer; switching scenes fires a save without awaiting it (287–299,319–332). Character save also swallows errors at 579–599. Explicit saves should retain drafts on failure and make pending/failed saves visible. Root owns functional repairs.

3. **Script file types are overstated.** Import accepts PDF/FDX/TXT/Fountain but uses `FileReader.readAsText` and POSTs that text to `generate-scenes` (WritersRoom:434–482,708; studioApi:2244–2260). A PDF cannot be treated as plain screenplay text. The older ScriptIngest has the same readAsText limitation (128,161). Safest small fix is truthful supported format handling; real PDF extraction requires a proper parser path. Do not claim PDF ingestion is verified from UI alone.

4. **Theatre stacks multiple workflows and displays invented risk signals.** Canonical panel above player + regular approval + assembly + stitching + export + multiple advice panels creates competing focus. Preserve callbacks but order Watch → Review → Approve → Deliver, with optional advice and canonical workflow disclosed. `weakSceneMarkers` fabricates two weak timeline regions for any nonempty script (ScreeningRoom:354–361); remove those invented creative warnings. `handleDownloadFinalPackage` returns/downloads JSON (1056–1079), so label it “Download export details (JSON)” instead of implying a video bundle. `handleApplyToShot` opens Previs carrying a note; it does not apply a production change (1245–1255), so use “Revise in Previs”.

5. **Study duplicates uploads and hides the meaningful order.** It owns three distinct inputs: project Bible registration/upload through KnowledgeLibraryPanel (Study:922; KnowledgeLibrary:80–132), analyzed reference upload/title study (Study:537–665), and attaching selected existing Studio Brain files (Study:434–457,949+). Present them as Bibles, References, Saved guidance—not competing ingest forms. Bible uploads accept Markdown; reference uploads accept media/PDF/text and serve a different purpose. The Reference file picker uploads immediately (610–616), while `filmFile` never gets a setter (306) and “+ INGEST FILE” is effectively inert (880). Remove/reword the duplicate button. Put analysis focus before choosing files. Rebuild Index and Department Context are optional maintenance. Start Bible editor empty rather than prefilled sample rules (KnowledgeLibrary:23–43) to avoid novices accidentally saving those as their film's canon.

6. **Study performs a write on navigation.** `loadReferences` calls `reorganizeReferenceLibrary` automatically before reading (Study:361–365). Make reorganization an explicit maintenance action, or omit this mutation from normal loads. Intercept writes during browser validation. Choosing files is the explicit upload action; saving creative memory remains explicit.

7. **Archive labels are materially misleading.** “Archive Film” calls `deleteProject` (Archive:325–344; studioApi:2230–2242). Use “Delete film” and retain clear confirmation, or implement real archival separately. “Publish” only fetches festival-export JSON and claims publication (388–399); use “Prepare export details” with truthful success. The export button downloads JSON (306–323). “Complete” is inferred only from approved scene count, and runtime is hardcoded `scenes.length * 2.5` (95–104); do not represent those as verified finished-media status/runtime. Theatre final output approval is a different artifact gate.

8. **Workspace has local-only approvals beside real backend gates.** `toggleApprovedStage`/`toggleLockedDecision` only change workspace state (ProjectWorkspace:211–226); state persists in localStorage (studioWorkspaceState:138–145). “Approve Stage”, “Approved”, and “Tap to lock” at 351–367,406–416 falsely resemble production approvals. Rename these local planning/checklist actions and explain their scope; keep the real `ProfessionalStudioWorkflowPanel` (ProjectWorkspace:297) as the approval source. No backend rewrite required for truthful presentation.

9. **Room navigation discards scene/shot context.** StudioShell uses `navigate(room.to)` on desktop/mobile (438,587), even though `withProductionContext` already exists. Preserve available current project/scene/shot. Explicit project links must win over stale context and update active context once before following room links.

## Existing functional overlap to explain, not silently merge

- Previs and Production Board both generate storyboard images / lock their image seed (Board:484–525). Board should primarily monitor and link to Previs; advanced quick actions can remain disclosed. Image seed lock does not freeze script or video takes.
- Universe graph-node save only saves `universe_node` storage (universe_graph_service.py:294–297); it does not update character production profiles edited by WritersRoom.updateCharacter (585). Guide users back to Write for production appearance/voice. Do not claim graph edits automatically synchronize render profiles.
- Regular Screening output approval and Canonical Production Thread approval have different artifact scope. Keep their names and selected output scope visible; do not fake unified approval state merely by moving panels.
- Previs duration acceptance currently also applies FPS/resolution/model (Previs:1473–1493). A button named “Accept Duration” should change duration only; selected provider is not currently sent to its recommendation call (1455–1461). Already identified earlier; still unresolved at audit time.

## Suggested validation

Use intercepted writes with live reads or fixtures: select scene 2 from Board → Write; type then immediately navigate; failed-save response retains text; cross-film deep links update active project; follow Study → Write → Previs → Theatre while preserving project/scene; compare small/mobile widths. Confirm no automatic Study mutation, no invented weak scene markers, and truthful MP4 versus JSON downloads. These checks verify UI handoffs, not a paid full render or final production output.
