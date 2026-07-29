# Architecture Decision Records

## ADR-001: Structured HTTP Middleware Stack

**Date**: Sprint 11  
**Status**: Accepted  
**Decision**: Add RequestID, StructuredLogging, and RateLimit as Starlette BaseHTTPMiddleware layers in `main.py`.

### Context
The application lacked request correlation, structured logging, and rate limiting. Debugging production issues required correlating frontend errors with backend logs manually.

### Decision
- **RequestIDMiddleware**: Injects UUID via `contextvars` for request propagation across async boundaries
- **StructuredLoggingMiddleware**: Emits JSON logs with request ID, duration, status code
- **RateLimitMiddleware**: Sliding window per-IP rate limiting with bypass paths for health checks

### Consequences
- Request IDs propagate through all async service calls via `request_id_var`
- JSON logs enable log aggregation (ELK, Datadog, etc.)
- Rate limiting prevents abuse without affecting health check endpoints
- Middleware order matters: RequestID → StructuredLogging → RateLimit

---

## ADR-002: Graceful Shutdown via Lifespan Events

**Date**: Sprint 11  
**Status**: Accepted  
**Decision**: Replace bare `on_event("startup")`/`on_event("shutdown")` with FastAPI lifespan context manager.

### Context
Background tasks (render polling, queue workers) could be interrupted mid-operation during deployment, causing orphaned database states.

### Decision
Use `@asynccontextmanager` lifespan in `main.py` that:
1. Initializes services on startup
2. On shutdown: cancels tasks → stops queue → drains pool → closes sessions

### Consequences
- No orphaned render jobs or partial database writes during deployment
- `BackgroundTaskRegistry` tracks all spawned tasks for clean cancellation
- Docker Compose health checks ensure traffic only reaches ready instances

---

## ADR-003: Externalized Configuration via Pydantic Settings

**Date**: Sprint 11  
**Status**: Accepted  
**Decision**: Move hardcoded values (admin token, CORS origins, rate limits, backup config) to `app/config.py` Pydantic Settings with env var fallback.

### Context
Hardcoded `ADMIN_TOKEN = "studio-admin-2026"` and `allow_origins=["http://localhost:5000"]` were security risks for production deployment.

### Decision
- All secrets and tuning knobs read from environment variables
- `.env.example` documents all available variables with defaults
- `admin_token` defaults to empty string (no admin access without explicit configuration)
- `demo_mode` defaults to `False` (production-safe by default)

### Consequences
- No secrets in source code
- Different environments (dev/staging/prod) use different `.env` files
- Docker Compose passes env vars through to containers

---

## ADR-004: Frontend Code Splitting via React.lazy

**Date**: Sprint 11  
**Status**: Accepted  
**Decision**: Convert all 22 page imports in `routes.tsx` to `React.lazy()` with Suspense boundaries.

### Context
Initial bundle included all page components (Three.js, Recharts, Framer Motion), resulting in a 1MB+ vendor chunk and slow initial load.

### Decision
- Each page component lazy-loaded as a separate chunk
- Vendor chunks split: `vendor-react`, `vendor-three`, `vendor-ui`, `vendor-charts`, `vendor-query`
- Loading skeleton shown during route transitions

### Consequences
- Initial load drops from ~2MB to ~230KB (vendor-react only)
- Three.js (1MB) only loads when universe graph or 3D components are accessed
- Route transitions have brief loading states (acceptable UX tradeoff)

---

## ADR-005: Error Telemetry with Client-Side Batching

**Date**: Sprint 11  
**Status**: Accepted  
**Decision**: Frontend errors are batched locally and flushed to `POST /api/f51/studio/errors` rather than sent individually.

### Context
Individual error reports create excessive HTTP overhead and can flood the backend during cascading failures.

### Decision
- Errors queued in memory (max 100)
- Batch flush on: queue reaches 10 errors, or 5-second timer
- `keepalive: true` ensures delivery even during page unload
- Backend stores to `error_reports` table but never blocks the response

### Consequences
- Reduced HTTP overhead (1 batch request vs. N individual requests)
- Telemetry failures never break the user experience
- Backend gracefully handles storage failures (logs warning, continues)
