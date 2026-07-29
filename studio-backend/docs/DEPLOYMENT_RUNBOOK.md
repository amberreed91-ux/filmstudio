# Deployment Runbook — AI Film Studio

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- Docker and Docker Compose (for containerized deployment)
- SQLite (bundled with Python, no separate install needed)

## Quick Start (Development)

```bash
# Backend
cd studio-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit as needed
uvicorn main:app --reload --port 8010

# Frontend
cd studio-app
npm install
npm run dev  # starts on port 5000
```

## Environment Variables

Copy `.env.example` to `.env` and configure. Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `DEMO_MODE` | `false` | Enable passwordless login (dev only) |
| `ADMIN_TOKEN` | `""` | Token for admin endpoints |
| `CORS_ORIGINS` | `""` | Comma-separated allowed origins |
| `RATE_LIMIT_PER_MINUTE` | `120` | Sliding window rate limit per IP |
| `BACKUP_ENABLED` | `true` | Enable automated SQLite backups |
| `BACKUP_DIR` | `./backups` | Backup storage directory |
| `BACKUP_MAX_COUNT` | `7` | Max backups to retain |
| `STORAGE_PATH` | `./data` | SQLite database directory |
| `LOG_FORMAT` | `json` | `json` for production, `text` for dev |

## Docker Deployment

```bash
cd studio-backend
docker compose up -d --build
```

This starts:
- **api** service on port 8010 (FastAPI + SQLite)
- **nginx** reverse proxy on port 80/443

### Volumes

| Volume | Container Path | Purpose |
|---|---|---|
| `studio-data` | `/app/data` | SQLite database |
| `studio-outputs` | `/app/outputs` | Rendered outputs |
| `studio-backups` | `/app/backups` | Automated backups |

### Health Checks

The container uses the `/ready` endpoint for health checks:
```bash
curl http://localhost:8010/ready
# 200 = ready, 503 = not ready
```

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Comprehensive health (DB, render, queue, system metrics) |
| `GET /ready` | Readiness probe (DB + schema check) |
| `GET /docs` | OpenAPI documentation |
| `POST /api/f51/studio/errors` | Frontend error telemetry ingestion |

## Graceful Shutdown

On SIGTERM/SIGINT, the server:
1. Cancels all background tasks (with timeout)
2. Stops the production queue worker
3. Drains the SQLite connection pool
4. Closes all database sessions

No manual intervention required.

## Backups

Automated backups run every `BACKUP_INTERVAL_HOURS` (default: 24h). To trigger manually:

```python
from app.services.database_backup import init_database_backup
backup = init_database_backup("./data/studio.db", "./backups")
result = backup.create_backup()
print(result)  # {"backup_path": "...", "size_bytes": ..., "duration_ms": ...}
```

### Backup Rotation

Backups are automatically rotated when count exceeds `BACKUP_MAX_COUNT`. Oldest backups are removed first.

## Monitoring

### Structured Logs (JSON)

Set `LOG_FORMAT=json` for production. Each request emits:
```json
{
  "timestamp": 1700000000.0,
  "level": "info",
  "request_id": "uuid",
  "method": "GET",
  "path": "/studio/dashboard",
  "status_code": 200,
  "duration_ms": 12.5
}
```

### Rate Limiting

Rate-limited responses include:
```json
{
  "error": "rate_limit_exceeded",
  "retry_after_seconds": 42
}
```

With headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`

Bypassed paths: `/health`, `/ready`, `/build-info`, `/docs`, `/openapi.json`

### Error Telemetry

Frontend errors are batched and sent to `POST /api/f51/studio/errors`. Stored in the `error_reports` table (migration 43).

## Troubleshooting

### Server won't start — "ModuleNotFoundError: No module named 'numpy'"
```bash
pip install numpy
```

### Database locked errors
Check `DB_POOL_SIZE` and ensure only one writer process. SQLite WAL mode is enabled by default.

### Rate limiting legitimate traffic
Increase `RATE_LIMIT_PER_MINUTE` or add IPs to the bypass list in `app/middleware/rate_limit.py`.

### Backup failures
Ensure `BACKUP_DIR` exists and is writable. Check logs for `studio-backup` logger.
