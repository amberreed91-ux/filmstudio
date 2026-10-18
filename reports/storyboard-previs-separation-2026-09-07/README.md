# Storyboard and Previs separation

Storyboard at /studio/storyboard owns shot planning, camera preset selection, frame generation, continuity review and approval. Previs at /studio/previs defaults to rendering and has only render/review navigation, an approval gate, and a context-preserving link back to Storyboard. Both surfaces share the existing workflow component and canonical backend records.

The studio navigation and journey guide include Storyboard. Writer's Room continues to Storyboard. Scene wall storyboard actions open the shot editor instead of generating a first scene frame directly. Existing Previs links with step=plan or step=storyboard redirect to Storyboard while preserving URL context.

Navigation keeps project, scene and shot context. Scene-reset and route-hydration effects are guarded so step changes do not reset shots or repeatedly overwrite direction.

Validation: production build passed; 17 focused route, workflow, scene-board and camera API tests passed; lint has no errors and one pre-existing dependency warning in PrevisRoom. git diff --check passed. Live browser verification was not run for this change.
