"""
Middleware for Aegis Suite.

Provides request ID tracking, metrics collection, and performance monitoring.
"""

import time
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from aegis.core.observability import (
    set_request_id,
    get_request_id,
    metrics_collector,
    RequestMetrics,
)

logger = logging.getLogger("aegis.middleware")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add unique request IDs to all requests."""

    async def dispatch(self, request: Request, call_next):
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or None
        request_id = set_request_id(request_id)

        # Add request ID to response headers
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect request metrics."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Record metrics
        metrics = RequestMetrics(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=get_request_id(),
            client_ip=request.client.host if request.client else "unknown",
        )
        metrics_collector.record_request(metrics)

        # Log slow requests
        if duration_ms > 1000:
            logger.warning(
                f"Slow request: {request.method} {request.url.path} took {duration_ms:.2f}ms"
            )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Add CSP header (allowing inline styles, scripts, Google Fonts, and WS connections)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' ws: wss:; "
            "img-src 'self' data: https:;"
        )

        return response
