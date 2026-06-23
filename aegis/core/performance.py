"""
Performance Utilities for Aegis Suite.

Provides caching, async helpers, and connection pooling.
"""

import asyncio
import functools
import hashlib
import json
import logging
import time
from typing import Any, Callable, Optional, Dict
from collections import OrderedDict

logger = logging.getLogger("aegis.performance")


class LRUCache:
    """Simple LRU cache with TTL support."""

    def __init__(self, max_size: int = 128, ttl_seconds: int = 60):
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, float] = {}

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key in self._cache:
            # Check TTL
            if time.time() - self._timestamps[key] < self._ttl_seconds:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                return self._cache[key]
            else:
                # Expired, remove
                del self._cache[key]
                del self._timestamps[key]
        return None

    def set(self, key: str, value: Any):
        """Set value in cache."""
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._max_size:
                # Remove oldest
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                del self._timestamps[oldest_key]
        
        self._cache[key] = value
        self._timestamps[key] = time.time()

    def invalidate(self, key: str):
        """Remove a key from cache."""
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)

    def clear(self):
        """Clear all cache entries."""
        self._cache.clear()
        self._timestamps.clear()


# Global config cache
_config_cache = LRUCache(max_size=1, ttl_seconds=30)


def cached_config(func: Callable) -> Callable:
    """Decorator for caching config loading."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        cache_key = "config"
        cached = _config_cache.get(cache_key)
        if cached is not None:
            return cached
        result = func(*args, **kwargs)
        _config_cache.set(cache_key, result)
        return result
    return wrapper


def invalidate_config_cache():
    """Invalidate the config cache."""
    _config_cache.clear()


class ResponseCache:
    """Cache for API responses."""

    def __init__(self, ttl_seconds: int = 60):
        self._ttl_seconds = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        """Get cached response."""
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["timestamp"] < self._ttl_seconds:
                return entry["data"]
            else:
                del self._cache[key]
        return None

    def set(self, key: str, data: Any):
        """Cache a response."""
        self._cache[key] = {
            "data": data,
            "timestamp": time.time()
        }

    def invalidate(self, prefix: str = ""):
        """Invalidate cache entries by prefix."""
        keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
        for key in keys_to_remove:
            del self._cache[key]

    def clear(self):
        """Clear all cached responses."""
        self._cache.clear()


# Global response cache
_response_cache = ResponseCache(ttl_seconds=30)


def cached_response(ttl_seconds: int = 60, prefix: str = ""):
    """Decorator for caching API responses."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and args
            cache_key = f"{prefix}:{func.__name__}:{hashlib.md5(json.dumps(kwargs, sort_keys=True, default=str).encode()).hexdigest()}"
            
            # Check cache
            cached = _response_cache.get(cache_key)
            if cached is not None:
                return cached
            
            # Call function
            result = await func(*args, **kwargs)
            
            # Cache result
            _response_cache.set(cache_key, result)
            
            return result
        return wrapper
    return decorator


def invalidate_response_cache(prefix: str = ""):
    """Invalidate response cache entries."""
    _response_cache.invalidate(prefix)


async def run_in_executor(func: Callable, *args, **kwargs) -> Any:
    """Run a synchronous function in an executor to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


class ConnectionPool:
    """Simple connection pool for database connections."""

    def __init__(self, create_func: Callable, max_size: int = 10):
        self._create_func = create_func
        self._max_size = max_size
        self._pool: list = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> Any:
        """Acquire a connection from the pool."""
        async with self._lock:
            if self._pool:
                return self._pool.pop()
            return self._create_func()

    async def release(self, connection: Any):
        """Release a connection back to the pool."""
        async with self._lock:
            if len(self._pool) < self._max_size:
                self._pool.append(connection)
            else:
                # Pool is full, close the connection
                try:
                    connection.close()
                except Exception:
                    pass

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with a connection from the pool."""
        connection = await self.acquire()
        try:
            return await run_in_executor(func, connection, *args, **kwargs)
        finally:
            await self.release(connection)


# Performance monitoring
class PerformanceMonitor:
    """Monitor and log performance metrics."""

    def __init__(self):
        self._metrics: Dict[str, list] = {}

    def record(self, metric_name: str, value: float):
        """Record a performance metric."""
        if metric_name not in self._metrics:
            self._metrics[metric_name] = []
        self._metrics[metric_name].append(value)
        
        # Keep only last 1000 values
        if len(self._metrics[metric_name]) > 1000:
            self._metrics[metric_name] = self._metrics[metric_name][-1000:]

    def get_average(self, metric_name: str) -> Optional[float]:
        """Get average value for a metric."""
        if metric_name in self._metrics and self._metrics[metric_name]:
            return sum(self._metrics[metric_name]) / len(self._metrics[metric_name])
        return None

    def get_stats(self, metric_name: str) -> Dict[str, Any]:
        """Get statistics for a metric."""
        if metric_name not in self._metrics or not self._metrics[metric_name]:
            return {"count": 0, "average": 0, "min": 0, "max": 0}
        
        values = self._metrics[metric_name]
        return {
            "count": len(values),
            "average": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all metrics."""
        return {name: self.get_stats(name) for name in self._metrics}


# Global performance monitor
performance_monitor = PerformanceMonitor()


def timed(func: Callable) -> Callable:
    """Decorator to measure function execution time."""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        elapsed = time.time() - start
        performance_monitor.record(func.__name__, elapsed)
        return result
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        performance_monitor.record(func.__name__, elapsed)
        return result
    
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper
