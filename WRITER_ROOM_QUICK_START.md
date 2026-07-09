# Writer's Room Quick Start Guide

## How to Use the New Script Upload Feature

### Option A: Upload a Script

1. **Navigate to Writer's Room**
   - Click "Writer's Room" in the navigation
   - Make sure you have a project created

2. **Upload Your Script**
   - **Method 1**: Click "Choose File (.txt, .pdf)" button and select your script file
   - **Method 2**: Paste your script directly into the large textarea

3. **Script Format**
   Your script should use one of these formats:
   
   ```
   SCENE 1: INT. COFFEE SHOP - DAY
   A woman sits alone at a corner table, reading a worn paperback.
   
   SCENE 2: EXT. STREET - NIGHT
   She walks through the rain, umbrella forgotten.
   ```
   
   Or:
   
   ```
   INT. COFFEE SHOP - DAY
   A woman sits alone at a corner table, reading a worn paperback.
   
   EXT. STREET - NIGHT
   She walks through the rain, umbrella forgotten.
   ```

4. **Import**
   - Click "Import Script" button
   - Wait for processing (may take up to 60 seconds)
   - Success message will show: "Found 3 scenes in your script!"
   - Scenes appear automatically in the list below

### Option B: Add Scenes Manually

1. **Click "Add Scene" button** in Option B section

2. **Fill in the form**:
   - **Scene Name** (required): e.g., "Opening Scene", "The Confrontation"
   - **Description**: What happens in this scene
   - **Location**: e.g., "INT. APARTMENT", "EXT. STREET"
   - **Time of Day**: Day, Night, Dawn, Dusk, etc.
   - **Emotional Tone**: Tense, Joyful, Melancholic, etc.
   - **Characters**: Add character names one by one
   - **Notes**: Additional ideas or reminders

3. **Click "Create Scene"**
   - Scene appears in the list immediately

### Managing Your Scenes

**Edit a Scene**:
- Click the pencil icon on any scene card
- Update fields as needed
- Click "Update Scene"

**Delete a Scene**:
- Click the trash icon on any scene card
- Confirm deletion

**Reorder Scenes**:
- Scenes are shown in the order they were created
- Use the scene list to review order

### Next Steps

Once you have scenes:
1. Click "Next: Go to Storyboard / Scenes Room"
2. Review and approve scenes in the Previs Room
3. Generate renders in the Production Board
4. Watch your film in the Screening Room

---

## Troubleshooting

### "Studio is starting up — please wait a moment"

**What it means**: The backend is initializing (usually takes 5-10 seconds)

**What to do**:
1. Wait a few seconds
2. Click "Retry" button
3. The message will disappear when backend is ready

### "Request timed out after 30 seconds"

**What it means**: The backend is not responding or is overloaded

**What to do**:
1. Check that the backend is running: `./start_backend.sh`
2. Wait a moment and try again
3. For script import, try a shorter script first

### "Found 0 scenes in your script"

**What it means**: The script parser couldn't find scene headings

**What to do**:
1. Check your script format (see examples above)
2. Make sure scene headings start with "SCENE X:" or "INT./EXT."
3. Try adding scenes manually instead

### Script upload shows no success message

**What it means**: The import may have failed silently

**What to do**:
1. Check the error message (red box) for details
2. Try a simpler script format
3. Use manual scene entry as a fallback

---

## Tips for Best Results

### Script Format
- ✅ Use clear scene headings: "SCENE 1: INT. COFFEE SHOP - DAY"
- ✅ Keep scene descriptions concise (2-3 sentences)
- ✅ Separate scenes with blank lines
- ❌ Don't use complex formatting or special characters
- ❌ Don't include dialogue or camera directions (not supported yet)

### Scene Descriptions
- ✅ Focus on visual action: "She walks through the rain"
- ✅ Include emotional tone: "tense", "melancholic", "hopeful"
- ✅ Specify location clearly: "INT. APARTMENT", "EXT. STREET"
- ❌ Don't write long paragraphs (keep it under 512 characters)

### Workflow
1. **Start small**: Import 2-3 scenes first to test
2. **Review immediately**: Check that scenes parsed correctly
3. **Edit as needed**: Fix any parsing issues manually
4. **Add more**: Import or add remaining scenes
5. **Move forward**: Go to Storyboard when ready

---

## Example Script

Here's a complete example script that will parse correctly:

```
SCENE 1: INT. COFFEE SHOP - DAY
A woman sits alone at a corner table, reading a worn paperback. The café is nearly empty. Rain streaks the window behind her.

SCENE 2: EXT. STREET - NIGHT
She walks through the rain, umbrella forgotten. The city lights blur in the downpour. Her phone rings but she doesn't answer.

SCENE 3: INT. APARTMENT - NIGHT
She enters her dark apartment, dripping wet. She stands in the doorway, not turning on the lights. The phone rings again.
```

This will create 3 scenes with:
- Scene IDs: scene_001, scene_002, scene_003
- Locations: COFFEE SHOP, STREET, APARTMENT
- Times: DAY, NIGHT, NIGHT
- Descriptions: The text after each heading

---

## Need Help?

- Check the error messages (red boxes) for specific issues
- Try manual scene entry if script upload fails
- Start with a simple 2-scene script to test
- Make sure the backend is running before importing
