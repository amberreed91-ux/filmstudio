# Architecture Boundary Cleanup v1.0

This document outlines the architectural boundaries and ownership patterns established during the v1.0 boundary cleanup.

## 🏗️ Service Ownership

### Core Services
- **RenderService**: Owns all render job lifecycle management, provider abstraction, and job polling
- **ProjectStoreService**: Owns project persistence and state management
- **GenerateShortFilmWorkflowService**: Owns complex short film generation workflows
- **ShortFilmReviewService**: Owns review lifecycle and decision management
- **ClipRevisionService**: Owns clip revision workflow and job tracking
- **FinalShortFilmPackageService**: Owns final packaging and delivery workflows

### Specialized Services
- **VideoAssetService**: Owns video asset registration and metadata management
- **KeyframeExtractionService**: Owns keyframe extraction and analysis
- **ShotDetectionService**: Owns shot boundary detection and analysis
- **SemanticMemoryService**: Owns scene memory ingestion and retrieval
- **ContinuityIntelligenceService**: Owns continuity analysis and issue detection
- **DirectorCommentaryService**: Owns AI-generated commentary workflow
- **SemanticSearchService**: Owns similarity search and content discovery
- **StyleLearningService**: Owns style signature analysis and learning
- **VideoUnderstandingStatusService**: Owns processing status tracking

## 🚫 Provider Boundaries

### Provider Isolation
- **Routes MUST NOT directly call provider adapters**
- **Services own all provider interactions**
- **Provider configuration managed through RenderService**
- **Provider errors handled at service layer**

### Provider Access Pattern
```python
# ❌ WRONG - Direct provider calls in routes
from app.providers import runway_adapter
result = runway_adapter.submit_job(job)

# ✅ CORRECT - Service-mediated provider calls
from app.services import render_service
job = render_service.create_job(...)
submitted_job = await render_service.submit_job(job.id)
```

## 💾 Persistence Boundaries

### Storage Ownership
- **Services own persistence decisions**
- **Routes MUST NOT access storage directly**
- **Storage abstraction through service interfaces**
- **Database operations encapsulated in services**

### Storage Access Pattern
```python
# ❌ WRONG - Direct storage access in routes
from app.data.storage import get_storage
storage = get_storage()
storage.save_project(project)

# ✅ CORRECT - Service-mediated persistence
from app.services.project_store import project_store
updated = project_store.update_project(project_id, data)
```

## 🎨 Frontend Orchestration Boundaries

### UI Orchestration Rules
- **Frontend owns UI state and user interactions**
- **Backend owns business logic and data validation**
- **API contracts defined through Pydantic DTOs**
- **No business logic in frontend components**

### API Contract Pattern
```python
# Backend DTOs define contracts
class CreateReviewPayload(BaseModel):
    output_url: str
    reviewer: str = ""
    notes: str = ""

# Frontend uses contracts for validation
const payload = {
    output_url: validatedUrl,
    reviewer: validatedReviewer,
    notes: validatedNotes
}
```

## 🔄 Service Communication

### Inter-Service Boundaries
- **Services communicate through well-defined interfaces**
- **No circular dependencies between services**
- **Shared utilities in `app.utils` module**
- **Service initialization managed in main.py**

### Service Dependency Pattern
```python
# Services depend on abstractions, not implementations
class ClipRevisionService:
    def __init__(self, storage: StorageInterface, render_service: RenderServiceInterface):
        self._storage = storage
        self._render_service = render_service
```

## 🛡️ Error Handling Boundaries

### Error Ownership
- **Services own domain-specific error handling**
- **Routes own HTTP response formatting**
- **Validation errors handled at service layer**
- **Infrastructure errors handled at route layer**

### Error Handling Pattern
```python
# Service layer - Domain errors
if not output_url:
    raise ValidationError("Missing output_url for review", stage="review")

# Route layer - HTTP formatting
try:
    review = service.create_review(...)
except ValidationError as e:
    raise HTTPException(status_code=400, detail=e.to_dict())
```

## 📊 Data Flow Boundaries

### Request Flow
1. **Route** - HTTP request parsing and validation
2. **Service** - Business logic execution
3. **Storage** - Data persistence
4. **Route** - Response formatting

### Response Flow
1. **Service** - Domain object creation
2. **Route** - DTO serialization
3. **HTTP** - Response delivery

## 🔧 Utility Boundaries

### Shared Utilities
- **`app.utils.helpers`** - Common helper functions
- **`app.utils.validators`** - Shared validation logic
- **`app.utils.converters`** - Data transformation utilities

### Utility Usage Pattern
```python
# Shared utility functions
from app.utils.helpers import as_non_empty_string, ensure_scene_fallback

# Used across services and routes
clean_value = as_non_empty_string(raw_value)
summary = ensure_scene_fallback(summary, concept)
```

## 🚀 Route Layer Responsibilities

### Thin Routes
- **HTTP request/response handling**
- **Input validation using Pydantic DTOs**
- **Authentication and authorization**
- **HTTP status code management**
- **Error response formatting**

### Route Pattern
```python
@router.post("/projects/{project_id}/endpoint")
async def endpoint_handler(project_id: str, payload: PayloadDTO):
    # 1. Validate input (Pydantic)
    # 2. Call service method
    # 3. Format response
    # 4. Handle HTTP errors
    result = await service.handle_request(project_id, payload)
    return result
```

## 🧪 Testing Boundaries

### Test Organization
- **Unit tests for service logic**
- **Integration tests for service interactions**
- **API tests for route contracts**
- **No testing across architectural boundaries**

## 📋 Migration Checklist

### Completed v1.0 Changes
- ✅ **Removed direct provider calls from routes**
- ✅ **Consolidated business logic in services**
- ✅ **Created shared utility functions**
- ✅ **Normalized DTO/model usage**
- ✅ **Established clear error handling boundaries**
- ✅ **Implemented thin route pattern**

### Future Considerations
- 🔄 **Consider service event bus for inter-service communication**
- 🔄 **Add service health check endpoints**
- 🔄 **Implement service metrics and monitoring**
- 🔄 **Consider circuit breaker patterns for external dependencies**

## 🚨 Boundary Violations

### What to Avoid
- **Direct database access in routes**
- **Business logic in UI components**
- **Provider calls outside services**
- **Circular service dependencies**
- **Mixed concerns in single functions**

### Detection Patterns
- Look for imports crossing boundaries
- Check for business logic in routes
- Verify provider calls are service-mediated
- Ensure proper error handling layers

## 📖 Maintenance Guidelines

### Adding New Features
1. **Define DTOs for API contracts**
2. **Implement business logic in services**
3. **Create thin route handlers**
4. **Add appropriate error handling**
5. **Write tests for each layer**

### Modifying Existing Features
1. **Respect existing boundaries**
2. **Update contracts if needed**
3. **Maintain backward compatibility**
4. **Update tests accordingly**
5. **Document boundary changes**

---

This architecture ensures maintainable, testable, and scalable code with clear separation of concerns and well-defined boundaries between layers.
