# Writer's Room Scene Management - Complete Fix

## ✅ Task Complete

The Writer's Room has been completely rebuilt to support proper scene-by-scene workflow instead of script-only parsing.

## Changes Made

### 1. Backend - Scene CRUD Endpoints (`studio-backend/app/routes/projects.py`)

Added 5 new REST API endpoints for scene management:

#### **GET /api/f51/studio/projects/{project_id}/scenes**
- Lists all scenes for a project
- Returns: `{ "scenes": Scene[] }`

#### **POST /api/f51/studio/projects/{project_id}/scenes**
- Creates a new scene
- Request body:
  ```json
  {
    "scene_name": "Opening Scene",
    "description": "The protagonist wakes up",
    "location": "INT. APARTMENT",
    "time_of_day": "MORNING",
    "emotional_tone": "peaceful",
    "characters": ["MAYA"],
    "notes": "Soft lighting"
  }
  ```
- Returns: `{ "scene": Scene, "project": Project }`
- Auto-generates `scene_id` (e.g., `scene_001`, `scene_002`)
- Auto-updates `film_cut` to include new scene

#### **GET /api/f51/studio/projects/{project_id}/scenes/{scene_id}**
- Gets a specific scene
- Returns: `{ "scene": Scene }`

#### **PUT /api/f51/studio/projects/{project_id}/scenes/{scene_id}**
- Updates an existing scene
- Request body: Partial scene data (only fields to update)
- Returns: `{ "scene": Scene, "project": Project }`
- Auto-updates `updated_at` timestamp

#### **DELETE /api/f51/studio/projects/{project_id}/scenes/{scene_id}**
- Deletes a scene
- Auto-removes from `film_cut`
- Returns: `{ "message": "Scene deleted", "scene_id": string }`

### 2. Frontend - API Client (`studio-app/src/lib/studioApi.ts`)

Added TypeScript types and functions:

```typescript
export type Scene = {
  scene_id: string
  scene_name: string
  description: string
  location: string
  time_of_day: string
  emotional_tone: string
  characters: string[]
  notes: string
  created_at: string
  updated_at: string
  status: string
}

export async function listScenes(projectId: string)
export async function createScene(projectId: string, payload: CreateScenePayload)
export async function getScene(projectId: string, sceneId: string)
export async function updateScene(projectId: string, sceneId: string, payload: UpdateScenePayload)
export async function deleteScene(projectId: string, sceneId: string)
```

All functions include proper error handling and return `{ data?, error? }` format.

### 3. Frontend - Writer's Room UI (`studio-app/src/pages/WritersRoom.tsx`)

**Complete rewrite** with modern scene management interface:

#### Features:
1. **Project Header**
   - Shows current project name
   - Shows project ID
   - "Create New Project" button if no project exists

2. **Scene List**
   - Shows all scenes with name, description, location, time, tone, characters
   - Scene count display
   - Empty state message when no scenes exist
   - Edit button (pencil icon) for each scene
   - Delete button (trash icon) for each scene with confirmation

3. **Add Scene Button**
   - Prominent "+ Add Scene" button
   - Opens scene creation form

4. **Scene Form** (Add/Edit)
   - Scene Name (required)
   - Description (textarea)
   - Location (text input)
   - Time of Day (dropdown: Day, Night, Dawn, Dusk, Morning, Afternoon, Evening)
   - Emotional Tone (dropdown: Neutral, Tense, Joyful, Melancholic, Suspenseful, Romantic, Dramatic, Comedic, Mysterious)
   - Characters (add/remove with tags)
   - Notes (textarea)
   - Save/Cancel buttons
   - Form validation (scene name required)
   - Loading states during save

5. **Next Step CTA**
   - Shows when at least one scene exists
   - "Next: Go to Storyboard / Scenes Room" button
   - Navigates to `/studio/previs?project_id={id}`

6. **Error/Success Messages**
   - Clear error messages in red
   - Success messages in green
   - Auto-dismiss after actions

## User Flow

### Complete Writer's Room Flow:

1. **User opens Writer's Room**
   - URL: `/studio/writers-room` or `/studio/writers-room?project_id={id}`
   - If no project: Shows "Create New Project" button
   - If project exists: Shows project name and scene list

2. **User creates/opens a project**
   - Click "Create New Project"
   - Project created via `POST /api/f51/studio/projects`
   - Project ID stored in localStorage
   - URL updates to include `?project_id={id}`

3. **User adds a scene**
   - Click "+ Add Scene" button
   - Form opens with empty fields
   - Fill in: Scene Name (required), Description, Location, Time of Day, Emotional Tone, Characters, Notes
   - Click "Create Scene"
   - API call: `POST /api/f51/studio/projects/{id}/scenes`
   - Scene appears in list immediately
   - Success message: "Scene created successfully"

4. **User sees the scene in the scene list**
   - Scene card shows all details
   - Edit and Delete buttons visible
   - Scene count updates

5. **User edits a scene**
   - Click edit button (pencil icon)
   - Form opens pre-filled with scene data
   - Modify any fields
   - Click "Update Scene"
   - API call: `PUT /api/f51/studio/projects/{id}/scenes/{scene_id}`
   - Scene updates in list
   - Success message: "Scene updated successfully"

6. **User deletes a scene**
   - Click delete button (trash icon)
   - Confirmation dialog: "Are you sure?"
   - Click OK
   - API call: `DELETE /api/f51/studio/projects/{id}/scenes/{scene_id}`
   - Scene removed from list
   - Success message: "Scene deleted successfully"

7. **User proceeds to Storyboard/Scenes room**
   - When at least one scene exists, "Next" CTA appears
   - Click "Next: Go to Storyboard / Scenes Room"
   - Navigates to `/studio/previs?project_id={id}`
   - Scenes available for storyboarding/rendering

## Testing Steps

### 1. Start Backend
```bash
cd studio-backend
./start_backend.sh
```
Backend runs on http://localhost:8010

### 2. Start Frontend
```bash
cd studio-app
npm run dev
```
Frontend runs on http://localhost:5001

### 3. Test Scene Creation Flow

**Step 1: Create Project**
- Navigate to http://localhost:5001/studio/writers-room
- Click "Create New Project"
- Verify: Project created, URL updates with `?project_id=...`
- Verify: Project name shows at top

**Step 2: Add First Scene**
- Click "+ Add Scene"
- Fill in form:
  - Scene Name: "Opening Scene"
  - Description: "The protagonist wakes up in a strange room"
  - Location: "INT. BEDROOM"
  - Time of Day: "MORNING"
  - Emotional Tone: "mysterious"
  - Characters: Add "ALEX"
  - Notes: "Soft morning light through curtains"
- Click "Create Scene"
- Verify: Success message appears
- Verify: Scene appears in list
- Verify: Scene count shows "(1)"

**Step 3: Add Second Scene**
- Click "+ Add Scene"
- Fill in form:
  - Scene Name: "The Discovery"
  - Description: "Alex finds a mysterious letter"
  - Location: "INT. KITCHEN"
  - Time of Day: "MORNING"
  - Emotional Tone: "suspenseful"
  - Characters: Add "ALEX"
- Click "Create Scene"
- Verify: Scene appears in list
- Verify: Scene count shows "(2)"

**Step 4: Edit Scene**
- Click edit button (pencil) on first scene
- Change Description to: "The protagonist wakes up confused"
- Change Emotional Tone to: "tense"
- Click "Update Scene"
- Verify: Success message appears
- Verify: Scene updates in list

**Step 5: Delete Scene**
- Click delete button (trash) on second scene
- Click OK in confirmation dialog
- Verify: Success message appears
- Verify: Scene removed from list
- Verify: Scene count shows "(1)"

**Step 6: Proceed to Storyboard**
- Verify: "Next: Go to Storyboard / Scenes Room" button appears
- Click the button
- Verify: Navigates to `/studio/previs?project_id=...`
- Verify: Scenes available in Previs Room

### 4. Test API Endpoints Directly

```bash
# List scenes
curl http://localhost:8010/api/f51/studio/projects/{project_id}/scenes

# Create scene
curl -X POST http://localhost:8010/api/f51/studio/projects/{project_id}/scenes \
  -H "Content-Type: application/json" \
  -d '{
    "scene_name": "Test Scene",
    "description": "A test scene",
    "location": "INT. TEST",
    "time_of_day": "DAY",
    "emotional_tone": "neutral",
    "characters": ["TEST"],
    "notes": "Test notes"
  }'

# Get scene
curl http://localhost:8010/api/f51/studio/projects/{project_id}/scenes/scene_001

# Update scene
curl -X PUT http://localhost:8010/api/f51/studio/projects/{project_id}/scenes/scene_001 \
  -H "Content-Type: application/json" \
  -d '{"scene_name": "Updated Scene"}'

# Delete scene
curl -X DELETE http://localhost:8010/api/f51/studio/projects/{project_id}/scenes/scene_001
```

## Build Status

✅ **Backend**: Python compiles successfully
✅ **Frontend**: TypeScript compiles successfully
✅ **Build**: Production build succeeds (973.07 kB)

## Files Modified/Created

### Backend
- ✅ `studio-backend/app/routes/projects.py` - Added scene CRUD endpoints

### Frontend
- ✅ `studio-app/src/lib/studioApi.ts` - Added scene API functions
- ✅ `studio-app/src/pages/WritersRoom.tsx` - Complete rewrite with scene management UI

## Breaking Changes

⚠️ **The old script-based Writer's Room is replaced**

The previous Writer's Room that parsed full scripts is now replaced with a scene-by-scene workflow. Users who were using the script parsing feature should:

1. Use the new scene-by-scene creation
2. Or use the existing `/generate-scenes` endpoint which still works for bulk script parsing

## Next Steps (Optional Enhancements)

1. **Drag-and-drop scene reordering** - Allow users to reorder scenes visually
2. **Scene templates** - Pre-fill common scene types
3. **Bulk import** - Import scenes from CSV or screenplay format
4. **Scene preview** - Show thumbnail or visual preview for each scene
5. **Scene duplication** - Copy existing scenes as templates
6. **Scene search/filter** - Filter by location, character, tone, etc.
7. **Auto-save** - Save changes automatically on blur
8. **Undo/Redo** - Scene editing history

## Summary

The Writer's Room is now a fully functional scene management interface where users can:
- ✅ Create projects
- ✅ Add individual scenes with rich metadata
- ✅ Edit scenes
- ✅ Delete scenes
- ✅ See all scenes in a list
- ✅ Proceed to Storyboard/Scenes room when ready

All API endpoints are working, error handling is in place, and the UI provides clear feedback for all actions.
