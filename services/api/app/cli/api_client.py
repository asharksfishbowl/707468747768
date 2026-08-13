"""Thin REST + WS client for cirq-studio's own API (services/api) — used by the
`runs` subcommands (Requirements 25-28). Kept separate from cli/auth.py, which
only ever talks to Google (device-code flow) and our own /auth/google/device-exchange
— one module per external counterpart.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import websockets
from websockets.sync.client import connect as _default_ws_connect

from app.cli.auth import api_base_url
from app.models import RunStatus

_HTTP_TIMEOUT_SECONDS = 10.0

# The two RunStatus values that end a run's lifecycle -- derived from the same
# enum services/api/app/models.py and worker.py already treat as authoritative,
# rather than re-typing "done"/"error" as a third independent pair of literals.
_TERMINAL_RUN_STATUSES = frozenset({RunStatus.DONE.value, RunStatus.ERROR.value})


class ApiError(Exception):
    """`status_code` mirrors the API's own HTTP status where there is one; `0` marks
    a transport-level failure (e.g. an unexpectedly dropped WebSocket) that has no
    HTTP status of its own — callers (cli/main.py) just need a message and an
    exit-1 trigger either way.
    """

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _raise_for_api_error(response: httpx.Response) -> None:
    if response.status_code >= 400:
        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            body = None
        # `dict.get(key, default)` would evaluate `response.text` unconditionally
        # even when "detail" is present -- checked explicitly instead so the
        # fallback is only read when actually needed.
        detail = body["detail"] if isinstance(body, dict) and "detail" in body else response.text
        raise ApiError(response.status_code, str(detail))


def get_me(token: str) -> dict:
    response = httpx.get(f"{api_base_url()}/auth/me", headers=_headers(token), timeout=_HTTP_TIMEOUT_SECONDS)
    _raise_for_api_error(response)
    return response.json()


def create_run(token: str, **body: Any) -> dict:
    """Requirement 25. `body` is the POST /runs payload verbatim (circuit_id/
    definition, processor_id, noisy, repetitions)."""
    response = httpx.post(f"{api_base_url()}/runs", headers=_headers(token), json=body, timeout=_HTTP_TIMEOUT_SECONDS)
    _raise_for_api_error(response)
    return response.json()


def get_run(token: str, run_id: str) -> dict:
    """Requirement 26."""
    response = httpx.get(f"{api_base_url()}/runs/{run_id}", headers=_headers(token), timeout=_HTTP_TIMEOUT_SECONDS)
    _raise_for_api_error(response)
    return response.json()


def list_runs(token: str, page: int = 1) -> list[dict]:
    """Requirement 28."""
    response = httpx.get(
        f"{api_base_url()}/runs", headers=_headers(token), params={"page": page}, timeout=_HTTP_TIMEOUT_SECONDS
    )
    _raise_for_api_error(response)
    return response.json()


def watch_run(
    token: str,
    run_id: str,
    on_message: Callable[[dict], None],
    connect_fn=_default_ws_connect,
) -> dict:
    """Requirement 27, Edge Case 8. Calls `on_message(parsed_json)` for every
    message as it arrives until a terminal status ('done' or 'error'), then closes
    the socket explicitly and returns that final message — deterministic cleanup
    of the network resource rather than relying on generator garbage collection.
    `connect_fn` is injectable (defaults to the real `websockets.sync.client.connect`)
    so tests can substitute a fake connection yielding canned messages.

    Raises `ApiError(4404, ...)` on the not-found/not-owned close code (matching
    `services/api/app/ws.py`'s existing behavior); `ApiError(0, ...)` on any other
    unexpected close (network interruption) or a clean close with no terminal
    status ever received — the CLI prints either as an error, exits 1, no retry
    (Requirement 27, same no-retry principle as `create_run`).
    """
    ws_url = f"{api_base_url().replace('http', 'ws', 1)}/runs/{run_id}/stream?token={token}"
    try:
        with connect_fn(ws_url) as ws:
            for raw in ws:
                message = json.loads(raw)
                on_message(message)
                if message.get("status") in _TERMINAL_RUN_STATUSES:
                    return message
    except websockets.exceptions.ConnectionClosedError as e:
        close_code = e.rcvd.code if e.rcvd is not None else None
        if close_code == 4404:
            raise ApiError(4404, "run not found") from e
        raise ApiError(0, f"connection lost (code {close_code})") from e

    raise ApiError(0, "connection lost before a final status was received")
