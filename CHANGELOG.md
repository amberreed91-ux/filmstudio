# Changelog

All notable changes to AI Film Studio are documented here.

## [Sprint 11] - 2026-07-28 — Commercial Release Readiness

### Added

**Infrastructure & Deployment**
- Multi-stage Dockerfile with non-root user and `.dockerignore`
- Docker Compose with health checks, volume mounts, and resource limits
- Nginx reverse proxy config with rate limiting, security headers, and gzip
- `.env.example` with all configurable environment variables

**Middleware Stack**
- `RequestIDMiddleware` — UUID correlation ID via contextvars for every request
- `StructuredLoggingMiddleware` — JSON request/response logs with duration and correlation
- `RateLimitMiddleware` — Sliding window per-IP rate limiting (default 120/min) with bypass for health endpoints

**Health & Readiness**
- Enhanced `GET /health` — subsystem checks (DB, render, queue, circuit breakers, background tasks, system metrics)
- New `GET /ready` — readiness probe returning 503 until DB and schema are initialized

**Security**
- `ADMIN_TOKEN` externalized to environment variable (no hardcoded tokens)
- `CORS_ORIGINS` configurable via environment variable
- `DEMO_MODE` defaults to `False` (production-safe by default)
- Auth route reads demo mode from server config, not client parameter

**Observability**
- Structured JSON logging with correlation ID, duration, status code
- Rate limit headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`
- Request ID propagated via `X-Request-ID` header and contextvars

**Reliability**
- `BackgroundTaskRegistry` for tracking and gracefully cancelling background tasks
- Graceful shutdown: cancel tasks → stop queue → drain pool → close sessions
- `DatabaseBackup` service with SQLite backup API, rotation, and daily scheduling
- Migration 43: `error_reports` table for frontend error telemetry

**Frontend Error Telemetry**
- `errorTelemetry.ts` — batched error reporting with queue, flush, configurable endpoint
- `localStorage.ts` — centralized localStorage API with shared constants and typed accessors
- Error boundary in `App.tsx` catches and reports component errors

**Frontend Performance**
- Code splitting via `React.lazy()` for all 22 page components
- Vendor chunk splitting: React, Three.js, UI libraries, Recharts, React Query
- Route transition loading skeletons

### Fixed
- `print()` calls in production services replaced with structured logging
- Bare `except:` clauses replaced with `except Exception:` across 6 files
- `demo_mode` default changed from `True` to `False`
- Connection pool in `storage.py` now properly reuses connections

### Tests
- 73 new tests across 8 test files (backend + frontend)
- Middleware: RequestID, StructuredLogging, RateLimit
- Services: BackgroundTaskRegistry, DatabaseBackup
- Routes: health, ready, error telemetry
- Config: defaults, env var overrides
- Frontend: errorTelemetry batching, localStorage utilities
