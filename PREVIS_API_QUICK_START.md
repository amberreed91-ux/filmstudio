# Previs API Quick Start Guide

## Overview
The Previs API generates preview images for scenes using Runway Gen-3. Images are extracted from short video renders.

## Endpoints

### 1. Generate Preview for Single Scene
```http
POST /api/f51/studio/projects/{project_id}/previs/generate-scene/{scene_id}
```

**Response**:
```json
{
  "job_id": "job-20260529195430-a1b2c3d4-scene_001_previs",
  "status": "pending",
  "scene_id": "scene_001",
  "message": "Preview generation started"
}
```

**What it does**:
- Fetches scene from database
- Builds prompt from scene description, emotional tone, location, time of day
- Submits 3-second render to Runway
- Returns immediately with pending status

### 2. Get Preview Images for Scene
```http
GET /api/f51/studio/projects/{project_id}/previs/images/{scene_id}
```

**Response**:
```json
[
  {
    "id": "previs_proj123_scene_001_hero_a1b2c3d4",
    "project_id": "proj123",
    "scene_id": "scene_001",
    "shot_id": null,
    "image_path": "https://storage.runwayml.com/video.mp4",
    "job_id": "job-20260529195430-a1b2c3d4-scene_001_previs",
    "status": "complete",
    "prompt_used": "A tense conversation in a dimly lit room. Tone: psychological tension. Location: INT. COFFEE SHOP. Time: DAY. Style: cinematic still, single frame, film photography, shallow depth of field",
    "fallback": false,
    "created_at": "2026-05-29T19:54:30Z",
    "updated_at": "2026-05-29T19:55:45Z"
  }
]
```

**Status values**:
- `pending` - Render job is still processing
- `complete` - Image is ready
- `failed` - Render job failed

**What it does**:
- Loads previs images from database
- Checks render job status for pending images
- Updates status when jobs complete
- Returns current state

### 3. Generate Previews for All Scenes
```http
POST /api/f51/studio/projects/{project_id}/previs/generate-all
```

**Response**:
```json
{
  "project_id": "proj123",
  "total_scenes": 3,
  "jobs": [
    {
      "scene_id": "scene_001",
      "job_id": "job-20260529195430-a1b2c3d4-scene_001_previs",
      "status": "pending"
    },
    {
      "scene_id": "scene_002",
      "job_id": "job-20260529195431-b2c3d4e5-scene_002_previs",
      "status": "pending"
    },
    {
      "scene_id": "scene_003",
      "job_id": "job-20260529195432-c3d4e5f6-scene_003_previs",
      "status": "pending"
    }
  ]
}
```

**What it does**:
- Loops through all scenes in project
- Calls generate-scene for each
- Returns list of job IDs for tracking

## Frontend Integration Pattern

### On Component Mount
```typescript
async function loadPrevisImages() {
  const response = await fetch(
    `/api/f51/studio/projects/${projectId}/previs/images/${sceneId}`
  )
  const images = await response.json()
  
  if (images.length > 0) {
    const latest = images[0]
    
    if (latest.status === 'complete') {
      setPreviewImage(latest.image_path)
    } else if (latest.status === 'pending') {
      setPreviewStatus('generating')
      startPolling()
    } else if (latest.status === 'failed') {
      setPreviewStatus('failed')
    }
  } else {
    setPreviewStatus('not_generated')
  }
}
```

### Generate Button Click
```typescript
async function handleGeneratePreview() {
  setGenerating(true)
  
  try {
    const response = await fetch(
      `/api/f51/studio/projects/${projectId}/previs/generate-scene/${sceneId}`,
      { method: 'POST' }
    )
    const result = await response.json()
    
    setJobId(result.job_id)
    setPreviewStatus('generating')
    startPolling()
  } catch (error) {
    console.error('Failed to generate preview:', error)
    setPreviewStatus('failed')
  } finally {
    setGenerating(false)
  }
}
```

### Polling for Completion
```typescript
function startPolling() {
  const interval = setInterval(async () => {
    const response = await fetch(
      `/api/f51/studio/projects/${projectId}/previs/images/${sceneId}`
    )
    const images = await response.json()
    
    if (images.length > 0) {
      const latest = images[0]
      
      if (latest.status === 'complete') {
        setPreviewImage(latest.image_path)
        setPreviewStatus('complete')
        clearInterval(interval)
      } else if (latest.status === 'failed') {
        setPreviewStatus('failed')
        clearInterval(interval)
      }
    }
  }, 10000) // Poll every 10 seconds
  
  return () => clearInterval(interval)
}
```

### Display Image
```typescript
{previewStatus === 'complete' && previewImage && (
  <img
    src={previewImage}
    alt={`Preview for ${sceneId}`}
    className="w-full aspect-video object-cover rounded-lg"
  />
)}

{previewStatus === 'generating' && (
  <div className="w-full aspect-video bg-gray-800 rounded-lg flex items-center justify-center">
    <div className="text-center">
      <div className="animate-pulse text-cyan-400">Generating preview…</div>
      <div className="text-xs text-gray-400 mt-2">This may take 1-2 minutes</div>
    </div>
  </div>
)}

{previewStatus === 'not_generated' && (
  <div className="w-full aspect-video bg-gray-800 rounded-lg flex items-center justify-center">
    <button
      onClick={handleGeneratePreview}
      disabled={generating}
      className="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 rounded-lg"
    >
      {generating ? 'Starting…' : 'Generate Preview'}
    </button>
  </div>
)}
```

## Image Path Handling

The `image_path` field can contain:
1. **Video URL** (current fallback): `https://storage.runwayml.com/video.mp4`
   - Use directly in `<img>` tag or `<video poster>` attribute
   - Browser will show first frame as preview

2. **Local path** (when FFmpeg implemented): `/previs-assets/proj123/scene_001.jpg`
   - Served via static file mount
   - Direct image file

## Prompt Building

The API builds prompts from scene data:
```
{scene.description}. Tone: {scene.emotional_tone}. Location: {scene.location}. Time: {scene.time_of_day}. Style: cinematic still, single frame, film photography, shallow depth of field
```

Example:
```
A tense conversation in a dimly lit room. Tone: psychological tension. Location: INT. COFFEE SHOP. Time: DAY. Style: cinematic still, single frame, film photography, shallow depth of field
```

Prompts are capped at 512 characters for Runway API compatibility.

## Error Handling

### 404 - Scene Not Found
```json
{
  "detail": "Scene scene_001 not found"
}
```

### 500 - Generation Failed
```json
{
  "detail": "Failed to generate preview: Runway API error"
}
```

### Empty Response
If no images exist for a scene, the GET endpoint returns an empty array: `[]`

## Performance Notes

- Preview generation takes 1-2 minutes (Runway render time)
- Poll every 10 seconds to check status
- Don't poll more frequently to avoid rate limits
- Consider batch generation for multiple scenes using `/generate-all`

## FFmpeg Status

Currently using video URLs as fallback. When FFmpeg is implemented:
- First frame will be extracted from video
- Saved to `outputs/previs/{project_id}/{scene_id}.jpg`
- Served via `/previs-assets/` static mount
- Faster loading than video URLs

Check logs for:
- `PREVIS_FFMPEG_UNAVAILABLE` - Using video URL fallback
- `PREVIS_FFMPEG_TODO` - Extraction pending implementation
