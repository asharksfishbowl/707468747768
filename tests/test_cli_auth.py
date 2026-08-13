"""Token storage + device-code flow client (cirq-studio-tooling.md Requirements
19-24, 29-33, Edge Cases 4-6)."""

import stat
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.cli import auth as cli_auth


def _make_fake_jwt(expires_delta=timedelta(hours=24)):
    exp = datetime.now(timezone.utc) + expires_delta
    return jwt.encode({"sub": "u1", "exp": exp}, "irrelevant-signing-secret-32-bytes!!", algorithm="HS256")


@pytest.fixture(autouse=True)
def isolated_credentials(tmp_path, monkeypatch):
    """Redirects token storage to a throwaway directory instead of the real
    ~/.config/cirq-studio -- these constants are computed once at import time, so
    tests patch them directly rather than the HOME env var.
    """
    creds_dir = tmp_path / "cirq-studio"
    monkeypatch.setattr(cli_auth, "_CREDENTIALS_DIR", creds_dir)
    monkeypatch.setattr(cli_auth, "_CREDENTIALS_PATH", creds_dir / "credentials.json")


@pytest.fixture(autouse=True)
def device_client_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_DEVICE_CLIENT_ID", "device-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_DEVICE_CLIENT_SECRET", "device-client-secret")


# ---------------------------------------------------------------------------
# Token storage (Requirement 20)
# ---------------------------------------------------------------------------


def test_load_credentials_returns_none_when_no_file_exists():
    assert cli_auth.load_credentials() is None


def test_save_credentials_writes_token_and_expires_at_with_0600_permissions():
    token = _make_fake_jwt()
    cli_auth.save_credentials(token)

    stored = cli_auth.load_credentials()
    assert stored["token"] == token
    assert "expires_at" in stored
    assert stat.S_IMODE(cli_auth._CREDENTIALS_PATH.stat().st_mode) == 0o600


def test_save_credentials_creates_missing_parent_directories():
    assert not cli_auth._CREDENTIALS_DIR.exists()
    cli_auth.save_credentials(_make_fake_jwt())
    assert cli_auth._CREDENTIALS_DIR.exists()


def test_clear_credentials_removes_file_and_reports_whether_one_existed():
    assert cli_auth.clear_credentials() is False

    cli_auth.save_credentials(_make_fake_jwt())
    assert cli_auth.clear_credentials() is True
    assert cli_auth.load_credentials() is None


def test_is_valid_true_for_unexpired_false_for_missing_or_expired():
    assert cli_auth.is_valid(None) is False

    future = {"expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
    assert cli_auth.is_valid(future) is True

    past = {"expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}
    assert cli_auth.is_valid(past) is False


# ---------------------------------------------------------------------------
# Device-code flow (Requirements 30-32, Edge Case 5)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._body


def test_request_device_code_posts_client_id_and_scope(monkeypatch):
    captured = {}

    def fake_post(url, data):
        captured["url"] = url
        captured["data"] = data
        return _FakeResponse(
            200,
            {
                "device_code": "d",
                "user_code": "ABCD-EFGH",
                "verification_url": "https://google.example/device",
                "interval": 5,
                "expires_in": 1800,
            },
        )

    monkeypatch.setattr(cli_auth._http_client, "post", fake_post)
    result = cli_auth.request_device_code()

    assert captured["url"] == cli_auth._GOOGLE_DEVICE_AUTHORIZE_URL
    assert captured["data"]["client_id"] == "device-client-id"
    assert result["user_code"] == "ABCD-EFGH"


def test_poll_for_token_returns_id_token_on_immediate_success(monkeypatch):
    monkeypatch.setattr(cli_auth._http_client, "post", lambda *a, **k: _FakeResponse(200, {"id_token": "google-id-token"}))
    assert cli_auth.poll_for_token("device-code", interval=0, expires_in=10) == "google-id-token"


def test_poll_for_token_keeps_polling_on_authorization_pending_then_succeeds(monkeypatch):
    responses = iter(
        [_FakeResponse(400, {"error": "authorization_pending"}), _FakeResponse(200, {"id_token": "google-id-token"})]
    )
    monkeypatch.setattr(cli_auth._http_client, "post", lambda *a, **k: next(responses))
    monkeypatch.setattr(cli_auth.time, "sleep", lambda s: None)

    assert cli_auth.poll_for_token("device-code", interval=1, expires_in=10) == "google-id-token"


def test_poll_for_token_increases_interval_by_5s_on_slow_down(monkeypatch):
    sleeps = []
    responses = iter([_FakeResponse(400, {"error": "slow_down"}), _FakeResponse(200, {"id_token": "tok"})])
    monkeypatch.setattr(cli_auth._http_client, "post", lambda *a, **k: next(responses))
    monkeypatch.setattr(cli_auth.time, "sleep", lambda s: sleeps.append(s))

    cli_auth.poll_for_token("device-code", interval=5, expires_in=30)
    assert sleeps == [10]  # 5 + RFC 8628's 5s backoff, not a fresh unrelated value


@pytest.mark.parametrize("error", ["expired_token", "access_denied"])
def test_poll_for_token_raises_device_flow_error_on_terminal_errors(monkeypatch, error):
    monkeypatch.setattr(cli_auth._http_client, "post", lambda *a, **k: _FakeResponse(400, {"error": error}))
    with pytest.raises(cli_auth.DeviceFlowError):
        cli_auth.poll_for_token("device-code", interval=1, expires_in=10)


def test_exchange_id_token_calls_device_exchange_endpoint_with_id_token(monkeypatch):
    captured = {}

    def fake_post(url, json):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(200, {"token": "our-jwt"})

    monkeypatch.setattr(cli_auth._http_client, "post", fake_post)
    result = cli_auth.exchange_id_token("google-id-token")

    assert result == "our-jwt"
    assert captured["url"] == f"{cli_auth.api_base_url()}/auth/google/device-exchange"
    assert captured["json"] == {"id_token": "google-id-token"}


def test_run_device_flow_prints_verification_url_and_code_and_saves_credentials(monkeypatch):
    monkeypatch.setattr(
        cli_auth,
        "request_device_code",
        lambda: {
            "device_code": "d",
            "user_code": "ABCD-EFGH",
            "verification_url": "https://google.example/device",
            "interval": 0,
            "expires_in": 10,
        },
    )
    monkeypatch.setattr(cli_auth, "poll_for_token", lambda *a, **k: "google-id-token")
    monkeypatch.setattr(cli_auth, "exchange_id_token", lambda tok: _make_fake_jwt())

    printed = []
    token = cli_auth.run_device_flow(print_fn=printed.append)

    assert any("ABCD-EFGH" in line and "https://google.example/device" in line for line in printed)
    assert cli_auth.load_credentials()["token"] == token


def test_run_device_flow_leaves_no_credentials_file_on_failure(monkeypatch):
    monkeypatch.setattr(
        cli_auth,
        "request_device_code",
        lambda: {"device_code": "d", "user_code": "X", "verification_url": "https://x", "interval": 0, "expires_in": 10},
    )

    def boom(*a, **k):
        raise cli_auth.DeviceFlowError("Google device authorization expired_token")

    monkeypatch.setattr(cli_auth, "poll_for_token", boom)

    with pytest.raises(cli_auth.DeviceFlowError):
        cli_auth.run_device_flow(print_fn=lambda *_: None)
    assert cli_auth.load_credentials() is None


# ---------------------------------------------------------------------------
# ensure_authenticated (Requirement 21, Edge Case 4)
# ---------------------------------------------------------------------------


def test_ensure_authenticated_returns_stored_token_without_device_flow_when_valid(monkeypatch):
    token = _make_fake_jwt()
    cli_auth.save_credentials(token)

    def boom(**_):
        raise AssertionError("should not run the device flow when a valid token is already stored")

    monkeypatch.setattr(cli_auth, "run_device_flow", boom)
    assert cli_auth.ensure_authenticated() == token


def test_ensure_authenticated_runs_device_flow_when_token_missing(monkeypatch):
    monkeypatch.setattr(cli_auth, "run_device_flow", lambda print_fn=print: "new-token")
    assert cli_auth.ensure_authenticated() == "new-token"


def test_ensure_authenticated_runs_device_flow_when_token_expired(monkeypatch):
    cli_auth.save_credentials(_make_fake_jwt(expires_delta=timedelta(hours=-1)))
    monkeypatch.setattr(cli_auth, "run_device_flow", lambda print_fn=print: "refreshed-token")
    assert cli_auth.ensure_authenticated() == "refreshed-token"
