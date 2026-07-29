import json
import time
import logging
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.middleware.request_id import request_id_var

logger = logging.getLogger("studio-http")

LOG_FORMAT = os.getenv("LOG_FORMAT", "json")


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Emit structured JSON logs for every HTTP request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        rid = request_id_var.get()

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)

            log_entry = {
                "timestamp": time.time(),
                "level": "info",
                "logger": "studio-http",
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "query": str(request.query_params) if request.query_params else None,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            }

            if response.status_code >= 500:
                log_entry["level"] = "error"
                logger.error(json.dumps(log_entry))
            elif response.status_code >= 400:
                log_entry["level"] = "warning"
                logger.warning(json.dumps(log_entry))
            else:
                logger.info(json.dumps(log_entry))

            return response

        except Exception as e:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(json.dumps({
                "timestamp": time.time(),
                "level": "error",
                "logger": "studio-http",
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": duration_ms,
                "error": str(e),
            }))
            raise
