"""WS /runs/{id}/stream (Requirement 34, Edge Case 8).

Uses `redis.asyncio` (not the sync `redis` client `worker.py`/`routes/runs.py` use)
so a blocking pub/sub read doesn't stall the event loop -- the same class of fix as
`auth.py`'s WS DB-lookup in Phase 2 (applied here too, see `run_in_threadpool` below).
"""

import uuid

import redis.asyncio
from fastapi import APIRouter, Depends, WebSocket
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.auth import authenticate_websocket
from app.db import get_db
from app.models import Run
from app.redis_client import get_async_redis_client, run_channel
from app.routes.runs import _get_owned_run

router = APIRouter()

# Not part of the spec's Requirement 34 (which only defines close code 4401, Phase
# 2's auth failure code) -- this mirrors the REST 404-not-403 existence-hiding policy
# (Edge Case 9) into a WS close code for a run that doesn't exist or isn't the
# connecting user's own, since GET /runs/{id} (Requirement 35) is owner-only 404 too.
_NOT_FOUND_CLOSE_CODE = 4404


def _run_state(run: Run) -> dict:
    return {
        "run_id": str(run.id),
        "status": run.status.value,
        "result": run.result,
        "error_message": run.error_message,
    }


@router.websocket("/runs/{run_id}/stream")
async def stream_run(
    websocket: WebSocket,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    redis_conn: redis.asyncio.Redis = Depends(get_async_redis_client),
) -> None:
    user = await authenticate_websocket(websocket, db)
    if user is None:
        return  # already closed with 4401 (Edge Case 11)

    # This handler runs on the asyncio event loop -- WS routes aren't dispatched
    # through FastAPI's sync-route threadpool the way HTTP `def` routes are, so the
    # blocking DB call is offloaded explicitly (same fix as authenticate_websocket's
    # own DB lookup in Phase 2).
    run = await run_in_threadpool(_get_owned_run, db, run_id, user)
    if run is None:
        await websocket.close(code=_NOT_FOUND_CLOSE_CODE)
        return

    await websocket.accept()
    # Edge Case 8: send current persisted state first, so a client that connects (or
    # reconnects) mid-run sees the latest state immediately, not just future chunks.
    await websocket.send_json(_run_state(run))

    pubsub = redis_conn.pubsub()
    await pubsub.subscribe(run_channel(str(run_id)))
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            # worker.py's _publish already produced valid JSON text; forward it
            # as-is instead of parsing it just to re-serialize an identical payload.
            data = message["data"]
            await websocket.send_text(data.decode() if isinstance(data, bytes) else data)
    finally:
        await pubsub.aclose()
