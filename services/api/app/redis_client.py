"""Shared Redis connection + queue/pub-sub naming, used by routes/runs.py (enqueue),
worker.py (consume + publish, a synchronous process), and ws.py (subscribe, an async
FastAPI route -- needs `redis.asyncio` so a blocking pub/sub read doesn't stall the
event loop, mirroring auth.py's WS DB-lookup fix in Phase 2).

`REDIS_URL` (see .env.example) selects the target Redis instance; falls back to a
local dev default when unset, mirroring db.py's DATABASE_URL pattern.
"""

import os

import redis
import redis.asyncio

_DEFAULT_REDIS_URL = "redis://localhost:6379/0"

JOB_QUEUE_KEY = "cirq_sandbox_studio:runs:queue"


def run_channel(run_id: str) -> str:
    return f"run:{run_id}"


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL)


# Constructed once at import time, like db.py's `engine` -- redis.Redis.from_url is a
# lazy connection-pool wrapper (no actual connection is opened until the first
# command), so this doesn't eagerly connect, and reusing one pool across requests
# avoids opening a fresh connection per `POST /runs`/per WS connection. Caching here
# doesn't conflict with tests injecting a `fakeredis` instance -- FastAPI dependency
# overrides replace the dependency function's call entirely, they never fall through
# to this module-level value.
_sync_client = redis.Redis.from_url(_redis_url())
_async_client = redis.asyncio.Redis.from_url(_redis_url())


def get_redis_client() -> redis.Redis:
    """Synchronous client, used by routes/runs.py (enqueue) and worker.py (consume +
    publish -- a plain script process, not async).
    """
    return _sync_client


def get_async_redis_client() -> redis.asyncio.Redis:
    """Async client, used by ws.py's `WS /runs/{id}/stream` (an async route -- pub/sub
    reads must not block the event loop). A FastAPI dependency like `get_db`, so
    tests can override it via `app.dependency_overrides` the same way.
    """
    return _async_client
