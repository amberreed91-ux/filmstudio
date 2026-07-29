# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

# Security: non-root user
RUN groupadd -r studio && useradd -r -g studio -d /app -s /sbin/nologin studio

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy installed dependencies
COPY --from=builder /install /usr/local

# Copy application code
WORKDIR /app
COPY . .

# Create data directory with correct permissions
RUN mkdir -p /app/data /app/outputs /app/static /app/backups && \
    chown -R studio:studio /app

# Switch to non-root user
USER studio

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8010/ready || exit 1

EXPOSE 8010

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
