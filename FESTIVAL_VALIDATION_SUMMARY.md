# Festival Validation Feature - Implementation Summary

## Overview
The Festival Validation feature allows users to validate export packages against festival specifications, ensuring films meet submission requirements for festivals like Sundance, Tribeca, SXSW, and others.

## Status: ✅ COMPLETE

All components have been implemented, tested, and verified:
- ✅ Backend service with validation logic
- ✅ Festival presets (Sundance, Tribeca, SXSW, Generic Short)
- ✅ API endpoints for validation and presets
- ✅ Frontend UI component with results display
- ✅ Integration with Export Package Panel
- ✅ All tests passing (9 backend + 10 frontend)
- ✅ No regressions (521 total frontend tests passing)

## Architecture

### Backend Components

#### 1. Export Package Service (`studio-backend/app/services/export_package_service.py`)

**Key Methods:**
- `validate_for_festival(package_id, festival_specs)` - Main validation method
- `get_festival_presets()` - Returns available festival presets
- Individual validation methods for each requirement type:
  - `_validate_runtime()` - Runtime requirements
  - `_validate_format()` - Format requirements (mp4, ProRes, DCP)
  - `_validate_resolution()` - Resolution requirements
  - `_validate_aspect_ratio()` - Aspect ratio requirements
  - `_validate_file_size()` - File size limits
  - `_validate_subtitles()` - Subtitle requirements
  - `_validate_color_grading()` - Color grading note requirements
  - `_validate_custom_requirements()` - Custom text requirements

**Festival Presets:**
```python
FESTIVAL_PRESETS = {
    "sundance": {
        "festival_name": "Sundance Film Festival",
        "max_runtime_minutes": 120.0,
        "required_format": "DCP or ProRes",
        "required_resolution": "1920x1080 or higher",
        "requires_color_grading_note": True,
        "custom_requirements": [
            "Closed captions for dialogue",
            "Stereo or 5.1 audio mix"
        ]
    },
    "tribeca": { ... },
    "sxsw": { ... },
    "generic_short": { ... }
}
```

**Validation Response:**
```json
{
  "festival_name": "Sundance Film Festival",
  "package_id": "export_abc123",
  "valid": true,
  "flags": [
    {
      "requirement": "Maximum runtime: 120 minutes",
      "status": "unknown",
      "note": "Runtime cannot be verified without scene duration data...",
      "blocking": false
    }
  ],
  "advisory": "Package has 7 requirement(s) that could not be automatically verified...",
  "unknown_count": 7,
  "honest_note": "7 of 7 requirements could not be verified from available package data."
}
```

#### 2. API Routes (`studio-backend/app/routes/export_package.py`)

**Endpoints:**

1. **POST** `/api/f51/studio/projects/{project_id}/export-packages/{package_id}/validate-festival`
   - Validates a package against festival specs
   - Body: `{ "preset": "sundance" }` or full festival_specs dict
   - Returns: Validation result with flags

2. **GET** `/api/f51/studio/festival-presets`
   - Returns all available festival presets
   - No authentication required
   - Returns: `{ "presets": { ... } }`

### Frontend Components

#### 1. FestivalCheckSection Component (`studio-app/src/components/FestivalCheckSection.tsx`)

**Features:**
- Dropdown to select festival preset
- "Run Check" button to trigger validation
- Results display with status icons:
  - ✓ Green checkmark for "met"
  - ? Amber question mark for "unknown"
  - ⚠ Red flag for "unmet" (rare)
- Honest note displayed at bottom
- Advisory message at top
- Loading and error states

**Props:**
```typescript
interface FestivalCheckSectionProps {
  projectId: string;
  packageId: string;
}
```

#### 2. Export Package Panel Integration (`studio-app/src/components/ExportPackagePanel.tsx`)

The FestivalCheckSection is integrated into the Export Package Panel, appearing below the package summary when a package is loaded.

### API Client (`studio-app/src/lib/studioApi.ts`)

**New Methods:**
```typescript
async getFestivalPresets(): Promise<{ presets: FestivalPresets }>
async validateForFestival(
  projectId: string,
  packageId: string,
  request: { preset: string } | FestivalSpecs
): Promise<FestivalValidationResult>
```

**Types:**
```typescript
interface FestivalSpecs {
  festival_name: string;
  max_runtime_minutes?: number | null;
  min_runtime_minutes?: number | null;
  required_format?: string | null;
  required_resolution?: string | null;
  required_aspect_ratio?: string | null;
  max_file_size_mb?: number | null;
  requires_subtitles?: boolean;
  requires_color_grading_note?: boolean;
  custom_requirements?: string[];
}

interface FestivalValidationResult {
  festival_name: string;
  package_id: string;
  valid: boolean;
  flags: FestivalValidationFlag[];
  advisory: string;
  unknown_count: number;
  honest_note: string;
}

interface FestivalValidationFlag {
  requirement: string;
  status: "met" | "unmet" | "unknown";
  note: string;
  blocking: boolean;
}
```

## Validation Logic

### Honest Assessment Principles

The validation system follows strict honesty principles:

1. **Never claim "unmet" unless clearly verifiable** - Most checks return "unknown" because we cannot automatically verify them
2. **Accurate counting** - The honest_note always states exactly how many requirements could not be verified
3. **Advisory-only approach** - All assessments are advisory, never claiming certainty
4. **No false positives** - Better to say "unknown" than to incorrectly claim something is met or unmet

### Status Definitions

- **"met"** - Requirement is clearly satisfied (rare, only for directly verifiable items)
- **"unknown"** - Cannot be automatically verified from package data (most common)
- **"unmet"** - Requirement is clearly not satisfied (rare, only for directly verifiable failures)

### Blocking vs Non-Blocking

- **blocking: true** - Only set when status is "unmet" and it's a critical requirement
- **blocking: false** - All "unknown" flags are non-blocking
- **valid: false** - Only when at least one blocking=true flag exists

### What Can't Be Verified

Most requirements cannot be automatically verified:
- Runtime (no scene duration data available)
- Format (would need to download and inspect files)
- Resolution (would need to download and inspect files)
- Aspect ratio (would need to download and inspect files)
- File size (would need to download files)
- Subtitles (would need to inspect video files)
- Color grading notes (would need to check documentation)
- Custom requirements (free text, context-dependent)

## Testing

### Backend Tests (`studio-backend/app/services/test_festival_validation.py`)

**9 tests covering:**
1. ✅ Get festival presets
2. ✅ Runtime validation returns "unknown"
3. ✅ Format validation returns "unknown" when no renders
4. ✅ Custom requirements always return "unknown"
5. ✅ Honest note correctly counts unverifiable requirements
6. ✅ valid=False only when blocking=True flag exists
7. ✅ Advisory mentions unknown count
8. ✅ Preset specs load correctly
9. ✅ No flags with None requirement (skipped checks)

### Frontend Tests (`studio-app/src/components/FestivalCheckSection.test.tsx`)

**10 tests covering:**
1. ✅ Renders festival check section
2. ✅ Renders preset dropdown
3. ✅ Renders run check button
4. ✅ Renders results with correct icons per status
5. ✅ Uses "needs attention" copy not "fail"
6. ✅ Renders honest note at bottom
7. ✅ Renders advisory message
8. ✅ Renders flags list
9. ✅ Shows loading state when checking
10. ✅ Shows error message when check fails

### Integration Tests

All 521 frontend tests passing with no regressions.

## Usage Example

### 1. Build an Export Package

```bash
curl -X POST http://127.0.0.1:8010/api/f51/studio/projects/project_123/export-package \
  -H "Content-Type: application/json" \
  -d '{
    "include_continuity_report": true,
    "include_render_lineage": true,
    "include_director_notes": true
  }'
```

### 2. Get Festival Presets

```bash
curl http://127.0.0.1:8010/api/f51/studio/festival-presets
```

### 3. Validate Against Festival

```bash
curl -X POST http://127.0.0.1:8010/api/f51/studio/projects/project_123/export-packages/export_abc123/validate-festival \
  -H "Content-Type: application/json" \
  -d '{ "preset": "sundance" }'
```

### 4. Frontend Usage

```typescript
// Load presets
const { presets } = await studioApi.getFestivalPresets();

// Run validation
const result = await studioApi.validateForFestival(
  projectId,
  packageId,
  { preset: "sundance" }
);

// Display results
console.log(result.advisory);
console.log(result.honest_note);
result.flags.forEach(flag => {
  console.log(`${flag.status}: ${flag.requirement}`);
});
```

## User Experience

### Festival Check Section UI

1. **Preset Selection**
   - Dropdown with festival names (Sundance, Tribeca, SXSW, Generic Short)
   - Clear festival name display

2. **Run Check Button**
   - Prominent button to trigger validation
   - Loading state: "Checking..."
   - Disabled during validation

3. **Results Display**
   - Advisory message at top (natural language summary)
   - Flags list with icons and status labels
   - Each flag shows:
     - Status icon (✓ ? ⚠)
     - Requirement text
     - Advisory note
     - Status label ("Met", "Unknown", "Needs attention")
   - Honest note at bottom in dimmed italic

4. **Error Handling**
   - Clear error messages if validation fails
   - Network error handling
   - Package not found handling

## Design Decisions

### Why Most Checks Return "Unknown"

The validation system is designed to be honest about its limitations. Most festival requirements cannot be automatically verified without:
- Downloading and inspecting video files
- Parsing video metadata
- Checking external documentation
- Manual human review

Rather than giving false confidence, the system clearly states what it cannot verify.

### Why "Needs Attention" Instead of "Fail"

The word "fail" implies certainty and finality. Since most checks are advisory and cannot be definitively verified, we use "needs attention" to indicate items that require manual review without implying failure.

### Why Blocking Flags Are Rare

A flag is only marked as blocking when:
1. The requirement can be automatically verified
2. The requirement is clearly not met
3. The requirement is critical for submission

Since most requirements cannot be automatically verified, most flags are non-blocking.

## Future Enhancements

Potential improvements for future iterations:

1. **Video File Analysis**
   - Download and inspect video files
   - Extract actual runtime, format, resolution, aspect ratio
   - Detect subtitle tracks
   - Measure file size

2. **Custom Festival Specs**
   - Allow users to define custom festival requirements
   - Save custom presets
   - Share presets across projects

3. **Validation History**
   - Track validation results over time
   - Show changes between validations
   - Export validation reports

4. **Integration with Render Pipeline**
   - Validate during render
   - Suggest render settings based on festival requirements
   - Auto-configure render jobs for festival specs

5. **Submission Checklist**
   - Generate submission checklist from validation results
   - Track manual verification steps
   - Mark items as reviewed

## Files Modified

### Backend
- `studio-backend/app/services/export_package_service.py` - Added validation methods and presets
- `studio-backend/app/routes/export_package.py` - Added validation endpoints
- `studio-backend/main.py` - Registered festival presets router
- `studio-backend/app/services/test_festival_validation.py` - Created tests

### Frontend
- `studio-app/src/lib/studioApi.ts` - Added API methods and types
- `studio-app/src/components/FestivalCheckSection.tsx` - Created component
- `studio-app/src/components/FestivalCheckSection.test.tsx` - Created tests
- `studio-app/src/components/ExportPackagePanel.tsx` - Integrated FestivalCheckSection

## Verification

### Backend Server
- ✅ Running at http://127.0.0.1:8010
- ✅ Festival presets endpoint accessible
- ✅ Validation endpoint functional
- ✅ All routes properly registered

### Frontend Server
- ✅ Running at http://localhost:5002
- ✅ Export Package Panel accessible
- ✅ Festival Check Section renders
- ✅ API integration working

### Tests
- ✅ 9 backend tests passing
- ✅ 10 frontend tests passing
- ✅ 521 total frontend tests passing (no regressions)
- ✅ All export package tests passing (14 tests)

## Conclusion

The Festival Validation feature is fully implemented and tested. It provides honest, advisory-only validation of export packages against festival requirements, clearly stating what can and cannot be automatically verified. The implementation follows all specified requirements and maintains the honest assessment principles throughout.
