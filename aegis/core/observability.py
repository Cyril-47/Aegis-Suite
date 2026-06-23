"""
Observability Module for Aegis Suite.

Provides structured logging, request IDs, metrics, and health diagnostics.
"""

import json
import logging
import time
import uuid
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from collections import defaultdict
from contextvars import ContextVar

# Context variable for request ID
request_id_var: ContextVar[str] = ContextVar('request_id', default='')


class StructuredFormatter(logging.Formatter):
    """Structured JSON formatter for production logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add request ID if available
        req_id = request_id_var.get('')
        if req_id:
            log_entry["request_id"] = req_id

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class HumanReadableFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname.ljust(8)
        logger_name = record.name
        message = record.getMessage()

        req_id = request_id_var.get('')
        req_part = f" [{req_id[:8]}]" if req_id else ""

        return f"{timestamp} {level} {logger_name}{req_id_part} {message}"


def setup_logging(log_level: str = "INFO", structured: bool = False):
    """Configure logging for the application."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler()

    if structured:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(HumanReadableFormatter())

    root_logger.addHandler(handler)

    # Set log levels for specific loggers
    logging.getLogger("aegis").setLevel(logging.DEBUG)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return str(uuid.uuid4())[:12]


def set_request_id(request_id: str = None) -> str:
    """Set the current request ID."""
    if request_id is None:
        request_id = generate_request_id()
    request_id_var.set(request_id)
    return request_id


def get_request_id() -> str:
    """Get the current request ID."""
    return request_id_var.get('')


@dataclass
class RequestMetrics:
    """Metrics for a single request."""
    method: str
    path: str
    status_code: int
    duration_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    request_id: str = ""
    client_ip: str = ""


class MetricsCollector:
    """Collect and aggregate metrics."""

    def __init__(self):
        self._requests: List[RequestMetrics] = []
        self._counters: Dict[str, int] = defaultdict(int)
        self._timers: Dict[str, List[float]] = defaultdict(list)
        self._max_history = 10000

    def record_request(self, metrics: RequestMetrics):
        """Record a request metric."""
        self._requests.append(metrics)

        # Keep only recent history
        if len(self._requests) > self._max_history:
            self._requests = self._requests[-self._max_history:]

        # Update counters
        self._counters[f"requests.{metrics.method}"] += 1
        self._counters[f"responses.{metrics.status_code}"] += 1

        # Update timers
        self._timers[f"duration.{metrics.path}"].append(metrics.duration_ms)
        if len(self._timers[f"duration.{metrics.path}"]) > 100:
            self._timers[f"duration.{metrics.path}"] = self._timers[f"duration.{metrics.path}"][-100:]

    def increment_counter(self, name: str, value: int = 1):
        """Increment a counter."""
        self._counters[name] += value

    def record_duration(self, name: str, duration_ms: float):
        """Record a duration."""
        self._timers[name].append(duration_ms)
        if len(self._timers[name]) > 100:
            self._timers[name] = self._timers[name][-100:]

    def get_metrics(self) -> Dict[str, Any]:
        """Get all metrics."""
        return {
            "counters": dict(self._counters),
            "timers": {
                name: {
                    "count": len(values),
                    "avg": sum(values) / len(values) if values else 0,
                    "min": min(values) if values else 0,
                    "max": max(values) if values else 0,
                }
                for name, values in self._timers.items()
            },
            "recent_requests": len(self._requests),
        }

    def get_endpoint_stats(self) -> Dict[str, Any]:
        """Get stats grouped by endpoint."""
        endpoint_stats = defaultdict(lambda: {"count": 0, "errors": 0, "total_ms": 0})

        for req in self._requests:
            key = f"{req.method} {req.path}"
            endpoint_stats[key]["count"] += 1
            if req.status_code >= 400:
                endpoint_stats[key]["errors"] += 1
            endpoint_stats[key]["total_ms"] += req.duration_ms

        return dict(endpoint_stats)


# Global metrics collector
metrics_collector = MetricsCollector()


@dataclass
class HealthStatus:
    """Health status for a component."""
    name: str
    status: str  # "healthy", "degraded", "unhealthy"
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


class HealthChecker:
    """Comprehensive health checker."""

    def __init__(self):
        self._checks: List[callable] = []

    def register_check(self, check_func: callable):
        """Register a health check function."""
        self._checks.append(check_func)

    def check_health(self) -> Dict[str, Any]:
        """Run all health checks and return status."""
        results = []
        overall_status = "healthy"

        for check in self._checks:
            try:
                result = check()
                results.append(result)
                if result.status == "unhealthy":
                    overall_status = "unhealthy"
                elif result.status == "degraded" and overall_status == "healthy":
                    overall_status = "degraded"
            except Exception as e:
                results.append(HealthStatus(
                    name=check.__name__ if hasattr(check, '__name__') else "unknown",
                    status="unhealthy",
                    message=str(e)
                ))
                overall_status = "unhealthy"

        return {
            "status": overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": [asdict(r) for r in results],
            "metrics": metrics_collector.get_metrics(),
        }


def check_database_health() -> HealthStatus:
    """Check database health."""
    try:
        from aegis.core.config_manager import get_config_manager
        config = get_config_manager().load()
        return HealthStatus(
            name="database",
            status="healthy",
            message="Database connection OK",
            details={"config_loaded": True}
        )
    except Exception as e:
        return HealthStatus(
            name="database",
            status="unhealthy",
            message=f"Database error: {e}"
        )


def check_bot_health() -> HealthStatus:
    """Check bot health."""
    try:
        from aegis.web.routes.dashboard import get_active_bot
        bot = get_active_bot()
        if bot and bot.is_ready():
            return HealthStatus(
                name="bot",
                status="healthy",
                message=f"Bot connected to {len(bot.guilds)} guilds",
                details={"guilds": len(bot.guilds)}
            )
        else:
            return HealthStatus(
                name="bot",
                status="degraded",
                message="Bot not connected"
            )
    except Exception as e:
        return HealthStatus(
            name="bot",
            status="unhealthy",
            message=f"Bot error: {e}"
        )


def check_analytics_health() -> HealthStatus:
    """Check analytics engine health."""
    try:
        from aegis.analytics.engine import get_analytics_engine
        engine = get_analytics_engine()
        if engine:
            return HealthStatus(
                name="analytics",
                status="healthy",
                message="Analytics engine running"
            )
        else:
            return HealthStatus(
                name="analytics",
                status="degraded",
                message="Analytics engine not initialized"
            )
    except Exception as e:
        return HealthStatus(
            name="analytics",
            status="unhealthy",
            message=f"Analytics error: {e}"
        )


# Create global health checker
health_checker = HealthChecker()
health_checker.register_check(check_database_health)
health_checker.register_check(check_bot_health)
health_checker.register_check(check_analytics_health)
