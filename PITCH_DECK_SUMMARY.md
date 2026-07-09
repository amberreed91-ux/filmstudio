# Pitch Deck Feature - Implementation Summary

## Overview
The Pitch Deck feature auto-drafts visual pitch documents by pulling from Film DNA, character maps, and arc analysis. It generates a structured slide deck that can be customized for different audiences (festival, investor, general).

## Status: ✅ COMPLETE

All components have been implemented, tested, and verified:
- ✅ Backend service with slide generation logic
- ✅ Database migration for pitch_decks table
- ✅ Storage methods for saving/loading decks
- ✅ API endpoints for generation and retrieval
- ✅ Frontend UI component with slide preview
- ✅ Integration with Export Package Panel
- ✅ All tests passing (11 backend + 4 frontend)
- ✅ No regressions (525 total frontend tests passing)

## Architecture

### Backend Components

#### 1. Pitch Deck Service (`studio-backend/app/services/pitch_deck_service.py`)

**Key Methods:**
- `generate_pitch_deck(project_id, target_audience)` - Main generation method
- `_synthesize_logline()` - Creates one-sentence film summary
- `_synthesize_tone_statement()` - Creates 1-2 sentence tone description
- `_generate_concept_slide()` - What the film is about emotionally
- `_generate_visual_language_slide()` - Dominant motifs and lighting
- `_generate_character_slides()` - One slide per major character (3+ scenes)
- `_generate_arc_slide()` - Emotional arc shape and resolution
- `_generate_tone_slide()` - Primary tone with references
- `_generate_production_note_slide()` - Current production status

**Slide Structure (in order):**
1. **Logline** - Synthesized from Film DNA + director intent
2. **Concept** - What the film is about, emotionally
3. **Visual Language** - Dominant motifs, lighting character, tone references
4. **Characters** - One slide per major character (3+ scenes), arc_summary as body
5. **Emotional Arc** - Arc shape + resolution read
6. **Tone** - Primary tone + references from director intent
7. **Production Note** - Honest assembly note from latest export package, or "In production"

**Data Sources:**
- `film_dna` - Film DNA analysis
- `character_journey` - Character presence from continuity graph
- `director_intent` - Director's creative vision
- `arc_analysis` - Arc completeness assessment
- `synthesized` - Generated from available data
- `export_package` - Production status from export packages

**Response Structure:**
```json
{
  "deck_id": "deck_abc123",
  "project_id": "project_123",
  "target_audience": "festival",
  "slides": [
    {
      "slide_number": 1,
      "title": "Logline",
      "type": "logline",
      "headline": "A musician discovers a memory glitch",
      "body": "A one-sentence summary of the film's core story.",
      "visual_suggestion": "Opening frame or key visual",
      "data_source": "synthesized"
    }
  ],
  "logline": "A musician discovers a memory glitch",
  "tone_statement": "The film has a mysterious tone with melancholic undertones.",
  "advisory": "This pitch deck was generated for festival audience from available project data.",
  "uncertainty_notes": ["Arc analysis not available"],
  "honest_note": "This is an AI-drafted starting point from available project data. Review and edit before sharing.",
  "generated_at": "2026-05-28T12:00:00Z"
}
```

#### 2. Database Migration (#16)

**Table: pitch_decks**
```sql
CREATE TABLE IF NOT EXISTS pitch_decks (
    deck_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    deck_json TEXT NOT NULL DEFAULT '{}',
    target_audience TEXT NOT NULL DEFAULT 'general',
    created_at TEXT NOT NULL,
    CHECK (deck_id != ''),
    CHECK (project_id != ''),
    CHECK (target_audience IN ('festival', 'investor', 'general'))
);

CREATE INDEX idx_pitch_decks_project ON pitch_decks(project_id);
CREATE INDEX idx_pitch_decks_created ON pitch_decks(created_at);
CREATE INDEX idx_pitch_decks_audience ON pitch_decks(target_audience);
```

#### 3. Storage Methods (`studio-backend/app/data/storage.py`)

**Methods:**
- `save_pitch_deck(project_id, deck)` - Save a pitch deck
- `load_pitch_deck(deck_id)` - Load a specific deck
- `list_pitch_decks(project_id, limit)` - List decks for a project

#### 4. API Routes (`studio-backend/app/routes/pitch_deck.py`)

**Endpoints:**

1. **POST** `/api/f51/studio/projects/{project_id}/pitch-deck`
   - Generates a new pitch deck
   - Body: `{ "target_audience": "festival" | "investor" | "general" }`
   - Returns: Full pitch deck with slides

2. **GET** `/api/f51/studio/projects/{project_id}/pitch-decks`
   - Lists pitch decks for a project
   - Query: `?limit=10`
   - Returns: `{ "decks": [{ "deck_id", "target_audience", "created_at" }] }`

3. **GET** `/api/f51/studio/projects/{project_id}/pitch-decks/{deck_id}`
   - Gets a specific pitch deck
   - Returns: Full pitch deck

### Frontend Components

#### 1. PitchDeckSection Component (`studio-app/src/components/PitchDeckSection.tsx`)

**Features:**
- Target audience selector (Festival / Investor / General)
- "Generate Draft" button
- Honest note displayed in amber at top
- Logline and tone statement summary
- Slide-by-slide preview with:
  - Slide icon (emoji based on type)
  - Slide number and title
  - Headline (large text)
  - Body (smaller text)
  - Visual suggestion (italic)
  - Data source (dimmed text)
- "Copy All as Text" button - exports deck as plain text
- Uncertainty notes section
- Advisory message
- Past decks list with timestamps and audience type

**Slide Icons:**
- 📝 Logline
- 💡 Concept
- 🎨 Visual Language
- 👤 Character
- 📈 Emotional Arc
- 🎭 Tone
- 🎬 Production Note

#### 2. Integration with Export Package Panel

The PitchDeckSection is integrated into the ExportPackagePanel, appearing after the Festival Check section.

### API Client (`studio-app/src/lib/studioApi.ts`)

**New Methods:**
```typescript
generatePitchDeck(projectId, targetAudience): Promise<PitchDeck>
listPitchDecks(projectId, limit): Promise<{ decks: PitchDeckSummary[] }>
getPitchDeck(projectId, deckId): Promise<PitchDeck>
```

**Types:**
```typescript
type PitchDeckSlide = {
  slide_number: number
  title: string
  type: 'logline' | 'concept' | 'visual_language' | 'character' | 'arc' | 'tone' | 'production_note'
  headline: string
  body: string
  visual_suggestion: string | null
  data_source: 'film_dna' | 'character_journey' | 'director_intent' | 'arc_analysis' | 'synthesized' | 'export_package'
}

type PitchDeck = {
  deck_id: string
  project_id: string
  target_audience: 'festival' | 'investor' | 'general'
  slides: PitchDeckSlide[]
  logline: string
  tone_statement: string
  advisory: string
  uncertainty_notes: string[]
  honest_note: string
  generated_at: string
}

type PitchDeckSummary = {
  deck_id: string
  target_audience: string
  created_at: string
}
```

## Slide Generation Logic

### Character Slides
- Only generated for characters appearing in 3+ scenes
- Extracted from continuity graph
- Arc summary from arc completeness analysis
- Sorted by scene count (descending)

### Data Synthesis
- **Logline**: Film DNA → Director Intent → Script Text → Project Title
- **Tone Statement**: Film DNA → Director Intent → Default message
- **Concept**: Director Intent → Film DNA → Script Text → Default message
- **Visual Language**: Film DNA motifs + lighting + Director Intent references
- **Arc**: Arc completeness → Film DNA → Default message
- **Production Note**: Latest export package → "In production"

### Honest Assessment
- Never fabricates data
- Clearly states when data isn't available
- Uncertainty notes track missing data sources
- Honest note always present: "This is an AI-drafted starting point from available project data. Review and edit before sharing."
- Advisory states target audience and data availability

## Testing

### Backend Tests (`studio-backend/app/services/test_pitch_deck.py`)

**11 tests covering:**
1. ✅ Generate pitch deck produces correct slide count
2. ✅ Logline synthesized from Film DNA
3. ✅ Character slides generated for 3+ scene characters only
4. ✅ Honest note always present
5. ✅ Uncertainty notes present when Film DNA missing
6. ✅ Data source correctly attributed per slide
7. ✅ Storage round-trip works correctly
8. ✅ Target audience stored correctly
9. ✅ Production note slide with export package
10. ✅ Production note slide without export package
11. ✅ Visual language slide includes motifs

### Frontend Tests (`studio-app/src/components/PitchDeckSection.test.tsx`)

**4 tests covering:**
1. ✅ Renders pitch deck section
2. ✅ Renders generate draft button
3. ✅ Renders empty state when no decks
4. ✅ Uses purple color for generate button

### Integration Tests

All 525 frontend tests passing with no regressions.

## Usage Example

### 1. Generate a Pitch Deck

```bash
curl -X POST http://127.0.0.1:8010/api/f51/studio/projects/project_123/pitch-deck \
  -H "Content-Type: application/json" \
  -d '{ "target_audience": "festival" }'
```

### 2. List Pitch Decks

```bash
curl http://127.0.0.1:8010/api/f51/studio/projects/project_123/pitch-decks
```

### 3. Get a Specific Deck

```bash
curl http://127.0.0.1:8010/api/f51/studio/projects/project_123/pitch-decks/deck_abc123
```

### 4. Frontend Usage

```typescript
// Generate deck
const deck = await studioApi.generatePitchDeck(projectId, 'festival');

// List past decks
const { decks } = await studioApi.listPitchDecks(projectId);

// Load specific deck
const deck = await studioApi.getPitchDeck(projectId, deckId);

// Copy as text
const text = `${deck.logline}\n\n${deck.tone_statement}\n\n...`;
navigator.clipboard.writeText(text);
```

## User Experience

### Pitch Deck Section UI

1. **Header**
   - "Pitch Deck" title
   - "Generate Draft" button (purple)

2. **Options Panel** (when generating)
   - Target Audience dropdown (General / Festival / Investor)
   - "Generate Draft" button
   - "Cancel" button

3. **Honest Note** (amber background)
   - Always displayed at top when deck is loaded
   - States this is an AI-drafted starting point

4. **Logline and Tone Summary**
   - Logline displayed prominently
   - Tone statement below

5. **Slides Preview**
   - Each slide shown as a card
   - Slide icon (emoji)
   - Slide number and title
   - Headline (large, bold)
   - Body text (smaller)
   - Visual suggestion (italic, if present)
   - Data source (dimmed, at bottom)

6. **Actions**
   - "Copy All as Text" button - exports full deck

7. **Uncertainty Notes** (if present)
   - Listed at bottom
   - Shows what data was unavailable

8. **Advisory**
   - Natural language summary
   - States target audience and data availability

9. **Past Decks**
   - List of previous decks
   - Shows audience type and date
   - Click to load

10. **Empty State**
    - "No pitch decks yet" message
    - Prompts to click "Generate Draft"

## Design Decisions

### Why Slide-by-Slide Preview?
The slide-by-slide preview allows directors to:
- See exactly what will be in the pitch deck
- Understand where each piece of content came from (data_source)
- Identify what needs manual editing
- Copy the entire deck as formatted text for Keynote/Google Slides

### Why "Copy All as Text"?
Rather than generating a PDF or PowerPoint file, we provide formatted text that can be pasted into any presentation tool. This gives directors full control over the final design while providing the content structure.

### Why Show Data Source?
Showing the data source for each slide helps directors understand:
- What data was used to generate each slide
- What is synthesized vs. pulled from Film DNA
- What needs manual review and editing

### Why Uncertainty Notes?
Uncertainty notes provide transparency about what data was unavailable, helping directors know what to focus on when editing the deck.

### Why Three Audience Types?
Different audiences require different emphasis:
- **Festival**: Focus on artistic vision, emotional arc, visual language
- **Investor**: Focus on production status, market potential, team
- **General**: Balanced approach for general audiences

Currently, all three use the same slide structure, but the target_audience field allows for future customization.

## Future Enhancements

Potential improvements for future iterations:

1. **Audience-Specific Slides**
   - Festival: Add "Festival Strategy" slide
   - Investor: Add "Budget & Timeline" slide
   - General: Add "Target Audience" slide

2. **Visual Attachments**
   - Suggest specific frames from renders
   - Include thumbnails in slide preview
   - Export with embedded images

3. **Custom Slide Order**
   - Allow directors to reorder slides
   - Add/remove slides
   - Customize slide content

4. **Export Formats**
   - PDF export
   - PowerPoint export
   - Keynote export
   - Google Slides integration

5. **Collaboration**
   - Share decks with team members
   - Comment on slides
   - Track revisions

6. **Templates**
   - Pre-designed slide templates
   - Custom branding
   - Festival-specific templates

## Files Modified

### Backend
- `studio-backend/app/services/pitch_deck_service.py` - Created service
- `studio-backend/app/data/storage.py` - Added migration #16 and storage methods
- `studio-backend/app/routes/pitch_deck.py` - Created routes
- `studio-backend/main.py` - Registered pitch_deck_router
- `studio-backend/app/services/test_pitch_deck.py` - Created tests

### Frontend
- `studio-app/src/lib/studioApi.ts` - Added API methods and types
- `studio-app/src/components/PitchDeckSection.tsx` - Created component
- `studio-app/src/components/PitchDeckSection.test.tsx` - Created tests
- `studio-app/src/components/ExportPackagePanel.tsx` - Integrated PitchDeckSection

## Verification

### Backend Server
- ✅ Running at http://127.0.0.1:8010
- ✅ Pitch deck endpoints accessible
- ✅ Generation working correctly
- ✅ All routes properly registered

### Frontend Server
- ✅ Running at http://localhost:5002
- ✅ Export Package Panel accessible
- ✅ Pitch Deck Section renders
- ✅ API integration working

### Tests
- ✅ 11 backend tests passing
- ✅ 4 frontend tests passing
- ✅ 525 total frontend tests passing (no regressions)

### API Verification
```bash
# Generate deck
curl -X POST http://127.0.0.1:8010/api/f51/studio/projects/project_6ed04d23df2c/pitch-deck \
  -H "Content-Type: application/json" \
  -d '{"target_audience":"festival"}'

# Response includes:
# - deck_id
# - 6 slides (logline, concept, visual language, arc, tone, production note)
# - logline and tone_statement
# - uncertainty_notes
# - honest_note
# - advisory
```

## Conclusion

The Pitch Deck feature is fully implemented and tested. It auto-drafts visual pitch documents by pulling from Film DNA, character maps, and arc analysis, providing directors with a structured starting point that can be customized for different audiences. The implementation follows honest assessment principles, clearly stating what data is available and what needs manual completion.

Key achievements:
- ✅ Pulls from multiple data sources (Film DNA, character maps, arc analysis)
- ✅ Generates structured slides in logical order
- ✅ Provides transparency through data_source attribution
- ✅ Includes honest note and uncertainty notes
- ✅ Supports three audience types (festival, investor, general)
- ✅ Allows easy export as formatted text
- ✅ Stores past decks for reference
- ✅ All tests passing with no regressions
