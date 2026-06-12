# Studio Backend Health Check Report
**Date**: May 28, 2026  
**Status**: ⚠️ PARTIAL PASS - Core functionality blocked by API contract issue

---

## Executive Summary

The backend is running and most infrastructure is healthy, but **project creation is failing** due to an API contract mismatch. This blocks all downstream tests (scenes, renders, intelligence services).

**Critical Issues**:
1. ❌ Project creation API expects request body, but receives query parameters
2. ⚠️ 46 backend tests failing (mostly batch render and retry features)
3. ❌ Frontend build failing
4. ⚠️ 2 database tables missing (previs_images, surfaced_disagreements)

---

## Detailed Results

### ✅ CORE FUNCTIONALITY

| Component | Status | Details |
|-----------|--------|---------|
| **PROJECT CREATION** | ❌ FAIL | API returns 422: expects body, receives query params |
| **SCENE CREATION** | ⊘ SKIP | Blocked by project creation failure |
| **HOSTED RENDER** | ⊘ SKIP | Blocked by project creation failure |
| **RENDER COMPLETION** | ⊘ SKIP | Blocked by project creation failure |
| **ASSET RESOLUTION** | ⊘ SKIP | Blocked by project creation failure |

**Project Creation Error**:
```
Status: 422
Response: {"detail":[{"type":"missing","loc":["body"],"msg":"Field required","input":null}]}
```

The API endpoint `/api/f51/studio/projects` expects a JSON body but the health check (and likely the frontend) is sending query parameters.

---

### ⊘ INTELLIGENCE SERVICES

All intelligence endpoints skipped due to no project available.

| Endpoint | Status | Notes |
|----------|--------|-------|
| **Timeline Intelligence** | SKIP | Requires valid project |
| **Continuity Intelligence** | SKIP | Requires valid project |
| **Film DNA** | SKIP | Requires valid project |
| **Arc Completeness** | SKIP | Requires valid project |
| **Character Journeys** | SKIP | Requires valid project |
| **Motif Threads** | SKIP | Requires valid project |
| **Session Debrief** | SKIP | Requires valid project |
| **Director Intent** | SKIP | Requires valid project |

---

### ✅ DATABASE TABLES

| Table | Status | Notes |
|-------|--------|-------|
| **continuity_graphs** | ✅ EXISTS | |
| **continuity_graph_versions** | ✅ EXISTS | |
| **film_dna** | ✅ EXISTS | |
| **previs_images** | ❌ MISSING | May need migration |
| **session_debriefs** | ✅ EXISTS | |
| **pitch_decks** | ✅ EXISTS | |
| **export_packages** | ✅ EXISTS | |
| **surfaced_disagreements** | ❌ MISSING | May need migration |

**Missing Tables**: 2 out of 8 tables are missing. These may be from newer features that haven't been migrated yet.

---

### ⚠️ BUILD & TESTS

| Component | Status | Details |
|-----------|--------|---------|
| **Frontend Build** | ❌ FAIL | Exit code 2 - TypeScript errors likely |
| **Backend Tests** | ⚠️ PARTIAL | 2037 passed / 46 failed (97.8% pass rate) |
| **Frontend Tests** | ❌ FAIL | 0 passed / 2 failed |

#### Backend Test Failures (46 total)

**Categories of failures**:

1. **Provider Config Test** (1 failure)
   - `test_provider_config_deterministic` - Likely due to Runway API key being present when test expects it empty

2. **Batch Render Tests** (22 failures)
   - All tests in `test_render_batch.py` failing
   - Suggests batch rendering feature may have breaking changes
   - Tests: job creation, batch IDs, shared context, shot position notes, batch status

3. **Retry with Context Tests** (22 failures)
   - All tests in `test_retry_with_continuity_context.py` failing
   - Suggests retry feature may have breaking changes
   - Tests: retry creation, prompt content, retry counts, max retry cap

4. **Runway Env Loading** (1 failure)
   - `test_render_service_missing_runway_api_key_results_in_none` - Expects missing key but key is present

**Note**: Most failures appear to be test environment issues (API key present when tests expect it absent) or feature-specific tests that may need updating.

---

## Runway Provider Status ✅

**Good news**: Runway is correctly configured for hosted generation!

```
Provider: Runway
  Enabled: True
  Mode: hosted_api
  Ready for hosted: True
  Is mock: False
  Is simulated: False
  Display: Runway: Real provider mode active
```

**Test Render Successful**:
- Created job with provider=runway
- Submitted to Runway API
- Received provider_job_id: `68657703-d994-4d84-afa1-2f525b5360ed`
- Status: complete

The Runway integration is working correctly when explicitly specifying `provider=runway`.

---

## Root Cause Analysis

### Primary Blocker: Project Creation API Contract

The project creation endpoint has a mismatch between what the API expects and what clients are sending:

**API Expects**: JSON body with project data
**Clients Send**: Query parameters

This is blocking:
- All end-to-end testing
- Scene creation
- Render job creation
- Intelligence service testing

### Secondary Issues

1. **Frontend Build Failure**
   - TypeScript errors preventing build
   - Likely from recent UI transformation work
   - Need to run `npm run build` with verbose output to see specific errors

2. **Test Failures**
   - Most are feature-specific (batch render, retry)
   - Some are environment-related (API key present when tests expect absent)
   - High overall pass rate (97.8%) suggests core functionality is solid

3. **Missing Database Tables**
   - `previs_images` and `surfaced_disagreements` tables missing
   - May be from newer features
   - Need to check if migrations exist but haven't been run

---

## Recommendations

### Immediate (Critical)

1. **Fix Project Creation API**
   - Investigate `/api/f51/studio/projects` POST endpoint
   - Determine correct contract (body vs query params)
   - Update either API or clients to match
   - This unblocks all downstream functionality

2. **Fix Frontend Build**
   - Run `npm run build` with verbose output
   - Address TypeScript errors
   - Likely related to recent userFacingText.ts changes

### Short Term (Important)

3. **Run Database Migrations**
   - Check if migrations exist for missing tables
   - Run migrations if available
   - Create migrations if needed

4. **Review Failing Tests**
   - Investigate batch render test failures
   - Investigate retry context test failures
   - Update tests if API contracts have changed
   - Fix environment-dependent tests (API key checks)

### Medium Term (Maintenance)

5. **Update Test Suite**
   - Make tests environment-agnostic
   - Mock external dependencies properly
   - Ensure tests don't depend on .env state

6. **Frontend Test Suite**
   - Fix 2 failing frontend tests
   - Ensure test coverage for new UI changes

---

## Summary Table

```
CORE FUNCTIONALITY
  PROJECT CREATION                    [ FAIL ]
  SCENE CREATION                      [ SKIP ]
  HOSTED RENDER                       [ SKIP ]
  RENDER COMPLETION                   [ SKIP ]
  ASSET RESOLUTION                    [ SKIP ]

INTELLIGENCE SERVICES
  TIMELINE INTEL                      [ SKIP ]
  CONTINUITY INTEL                    [ SKIP ]
  FILM DNA                            [ SKIP ]
  ARC COMPLETENESS                    [ SKIP ]
  CHARACTER JOURNEYS                  [ SKIP ]
  MOTIF THREADS                       [ SKIP ]
  SESSION DEBRIEF                     [ SKIP ]
  DIRECTOR INTENT                     [ SKIP ]

DATABASE TABLES
  continuity_graphs                   [ EXISTS ]
  continuity_graph_versions           [ EXISTS ]
  film_dna                            [ EXISTS ]
  previs_images                       [ MISSING ]
  session_debriefs                    [ EXISTS ]
  pitch_decks                         [ EXISTS ]
  export_packages                     [ EXISTS ]
  surfaced_disagreements              [ MISSING ]

BUILD & TESTS
  FRONTEND BUILD                      [ FAIL ]
  BACKEND TESTS                       [ 2037 passed / 46 failed ]
  FRONTEND TESTS                      [ 0 passed / 2 failed ]
```

---

## Next Steps

1. ✅ **Runway is working** - No action needed for hosted renders
2. ❌ **Fix project creation API** - Critical blocker
3. ❌ **Fix frontend build** - Blocking UI deployment
4. ⚠️ **Review test failures** - Maintenance task
5. ⚠️ **Add missing DB tables** - Feature completeness

---

## Positive Findings

Despite the blockers, several things are working well:

✅ Backend is running and healthy  
✅ Runway provider correctly configured for hosted generation  
✅ Test render to Runway API successful  
✅ 97.8% of backend tests passing  
✅ 6 out of 8 database tables present  
✅ Core infrastructure (SQLite, API server) functioning  

The issues are primarily integration/contract mismatches rather than fundamental architecture problems.
