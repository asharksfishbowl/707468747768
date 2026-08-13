"""`app.cli.api_client`'s REST helpers + `watch_run`'s WS message loop
(cirq-studio-tooling.md Requirements 25-28, Edge Case 8)."""

import json

import pytest
import websockets
from websockets.frames import Close

from app.cli import api_client


class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


def test_get_me_raises_api_error_on_401(monkeypatch):
    monkeypatch.setattr(api_client.httpx, "get", lambda *a, **k: _FakeResponse(401, {"detail": "invalid token"}))
    with pytest.raises(api_client.ApiError) as exc_info:
        api_client.get_me("bad-token")
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "invalid token"


def test_create_run_passes_body_and_bearer_header(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json)
        return _FakeResponse(202, {"run_id": "r1", "status": "queued"})

    monkeypatch.setattr(api_client.httpx, "post", fake_post)
    result = api_client.create_run("jwt-token", processor_id="weber", noisy=True, repetitions=100)

    assert result == {"run_id": "r1", "status": "queued"}
    assert captured["headers"] == {"Authorization": "Bearer jwt-token"}
    assert captured["json"]["processor_id"] == "weber"


# ---------------------------------------------------------------------------
# watch_run (Requirement 27, Edge Case 8)
# ---------------------------------------------------------------------------


class _FakeWebSocket:
    def __init__(self, messages):
        self._messages = messages

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._messages)


def _connect_returning(messages):
    return lambda url: _FakeWebSocket(messages)


def test_watch_run_calls_on_message_for_each_frame_and_returns_final_terminal_message():
    frames = [
        json.dumps({"run_id": "r1", "status": "queued"}),
        json.dumps({"run_id": "r1", "status": "running", "partial_histogram": {"result": {"0": 5}}}),
        json.dumps({"run_id": "r1", "status": "done", "result": {"result": {"0": 100}}}),
    ]
    seen = []

    final = api_client.watch_run("jwt-token", "r1", seen.append, connect_fn=_connect_returning(frames))

    assert [m["status"] for m in seen] == ["queued", "running", "done"]
    assert final["status"] == "done"


def test_watch_run_stops_at_first_terminal_status_without_reading_further_frames():
    """A 'done' message mid-stream (server never closes the socket itself, see
    services/api/app/ws.py) must end watch_run's loop -- it shouldn't hang waiting
    for more frames that will never distinguish themselves as "the end"."""
    frames_yielded = []

    def frame_iter():
        for raw in [
            json.dumps({"run_id": "r1", "status": "done", "result": {}}),
            json.dumps({"run_id": "r1", "status": "running"}),  # would never actually happen post-done
        ]:
            frames_yielded.append(raw)
            yield raw

    class LazyFakeWebSocket(_FakeWebSocket):
        def __iter__(self):
            return frame_iter()

    final = api_client.watch_run(
        "jwt-token", "r1", lambda m: None, connect_fn=lambda url: LazyFakeWebSocket([])
    )
    assert final["status"] == "done"
    # Only the first frame was ever pulled from the iterator.
    assert len(frames_yielded) == 1


def _closing_with_code(code: int):
    """A fake WS connection whose iteration raises the same exception a real
    `websockets` connection raises when the server closes with `code`."""

    class ClosingWebSocket(_FakeWebSocket):
        def __iter__(self):
            raise websockets.exceptions.ConnectionClosedError(rcvd=Close(code=code, reason=""), sent=None)

    return lambda url: ClosingWebSocket([])


def test_watch_run_raises_api_error_4404_on_not_found_close():
    """Matches services/api/app/ws.py's _NOT_FOUND_CLOSE_CODE (Edge Case 8)."""
    with pytest.raises(api_client.ApiError) as exc_info:
        api_client.watch_run("jwt-token", "r1", lambda m: None, connect_fn=_closing_with_code(4404))
    assert exc_info.value.status_code == 4404


def test_watch_run_raises_api_error_0_on_unexpected_disconnect():
    with pytest.raises(api_client.ApiError) as exc_info:
        api_client.watch_run("jwt-token", "r1", lambda m: None, connect_fn=_closing_with_code(1006))
    assert exc_info.value.status_code == 0
