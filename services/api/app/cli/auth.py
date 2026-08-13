"""Token storage + Google device-code flow client for the `cirq-studio` CLI.

Spec: specs/cirq-studio-tooling/cirq-studio-tooling.md Requirements 19-24, 29-33,
Edge Cases 4-6.
"""

from __future__ import annotations

import json
import os
import stat
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import jwt

_CREDENTIALS_DIR = Path.home() / ".config" / "cirq-studio"
_CREDENTIALS_PATH = _CREDENTIALS_DIR / "credentials.json"

_GOOGLE_DEVICE_AUTHORIZE_URL = "https://oauth2.googleapis.com/device/code"
_GOOGLE_DEVICE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
_SLOW_DOWN_INCREMENT_SECONDS = 5  # RFC 8628 4.2's recommended backoff.
_HTTP_TIMEOUT_SECONDS = 10.0

_ENV_API_URL = "CIRQ_STUDIO_API_URL"
_DEFAULT_API_URL = "http://localhost:8000"
_ENV_DEVICE_CLIENT_ID = "GOOGLE_OAUTH_DEVICE_CLIENT_ID"
_ENV_DEVICE_CLIENT_SECRET = "GOOGLE_OAUTH_DEVICE_CLIENT_SECRET"

# Reused across requests for connection keep-alive, same rationale as
# services/api/app/auth.py's module-level `_google_http_client` -- matters most
# here since `poll_for_token` can hit the same host repeatedly every `interval`
# seconds for up to `expires_in` (a fresh TCP/TLS handshake per poll would be
# wasted work against the same server).
_http_client = httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS)


class DeviceFlowError(Exception):
    """Raised when the device flow can't complete (Requirement 31(d)/(e),
    Edge Case 5) — the caller (cli/main.py) prints this and exits 1. Nothing is
    written to the credentials file when this is raised (Edge Case 5's "no
    partial/corrupt file" guarantee — `run_device_flow` only calls
    `save_credentials` after every prior step succeeds).
    """


def api_base_url() -> str:
    """Requirement 19."""
    return os.environ.get(_ENV_API_URL, _DEFAULT_API_URL)


# ---------------------------------------------------------------------------
# Token storage (Requirement 20)
# ---------------------------------------------------------------------------


def load_credentials() -> dict | None:
    if not _CREDENTIALS_PATH.exists():
        return None
    return json.loads(_CREDENTIALS_PATH.read_text())


def save_credentials(token: str) -> None:
    """Decodes `expires_at` from the JWT's own `exp` claim (Requirement 20) —
    signature verification isn't needed here: the CLI has no JWT_SECRET_KEY (that's
    server-side only) and doesn't need one to read a claim out of a token it just
    received directly from that same trusted server.
    """
    claims = jwt.decode(token, options={"verify_signature": False})
    expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc).isoformat()

    _CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    _CREDENTIALS_PATH.write_text(json.dumps({"token": token, "expires_at": expires_at}))
    _CREDENTIALS_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600, owner read/write only.


def clear_credentials() -> bool:
    """Requirement 23. Returns True if a credentials file existed and was removed."""
    if _CREDENTIALS_PATH.exists():
        _CREDENTIALS_PATH.unlink()
        return True
    return False


def is_valid(credentials: dict | None) -> bool:
    """Present and not yet past its own `expires_at` (Requirement 21, Edge Case 4)."""
    if credentials is None:
        return False
    return datetime.fromisoformat(credentials["expires_at"]) > datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Device-code flow (Requirements 29-32, Edge Case 5)
# ---------------------------------------------------------------------------


def _device_client_id() -> str:
    value = os.environ.get(_ENV_DEVICE_CLIENT_ID)
    if not value:
        raise DeviceFlowError(
            f"{_ENV_DEVICE_CLIENT_ID} is not set — required to sign in with `cirq-studio`"
        )
    return value


def _device_client_secret() -> str:
    value = os.environ.get(_ENV_DEVICE_CLIENT_SECRET)
    if not value:
        raise DeviceFlowError(
            f"{_ENV_DEVICE_CLIENT_SECRET} is not set — required to sign in with `cirq-studio`"
        )
    return value


def _expired_error() -> DeviceFlowError:
    """The one source of truth for the "ran out of time" message — built the same
    way whether Google reported `expired_token` explicitly (inside the poll loop)
    or `expires_in` simply elapsed (after it)."""
    return DeviceFlowError("Google device authorization expired_token".replace("_", " "))


def request_device_code() -> dict:
    """Requirement 30. Returns Google's raw JSON: device_code/user_code/
    verification_url/interval/expires_in."""
    response = _http_client.post(
        _GOOGLE_DEVICE_AUTHORIZE_URL,
        data={"client_id": _device_client_id(), "scope": "openid email profile"},
    )
    response.raise_for_status()
    return response.json()


def poll_for_token(device_code: str, interval: int, expires_in: int) -> str:
    """Requirement 31: polls Google's token endpoint until it returns an `id_token`,
    or raises `DeviceFlowError` on `expired_token`/`access_denied`. `interval`-second
    waits between polls are the device-flow protocol itself (RFC 8628), not an
    incidental delay — Google's own response tells the client how often it's allowed
    to ask again; polling faster would just get rate-limited.
    """
    deadline = time.monotonic() + expires_in
    while time.monotonic() < deadline:
        response = _http_client.post(
            _GOOGLE_DEVICE_TOKEN_URL,
            data={
                "client_id": _device_client_id(),
                "client_secret": _device_client_secret(),
                "device_code": device_code,
                "grant_type": _DEVICE_GRANT_TYPE,
            },
        )
        body = response.json()
        if response.status_code == 200:
            return body["id_token"]

        error = body.get("error")
        if error == "expired_token":
            raise _expired_error()
        if error == "access_denied":
            raise DeviceFlowError("Google device authorization access denied")
        if error not in ("authorization_pending", "slow_down"):
            raise DeviceFlowError(f"Unexpected response from Google's device-token endpoint: {body}")

        if error == "slow_down":
            interval += _SLOW_DOWN_INCREMENT_SECONDS
        time.sleep(interval)

    raise _expired_error()


def exchange_id_token(google_id_token: str) -> str:
    """Requirement 32: calls services/api/app/auth.py's device-exchange endpoint,
    returns our own JWT."""
    response = _http_client.post(
        f"{api_base_url()}/auth/google/device-exchange",
        json={"id_token": google_id_token},
    )
    response.raise_for_status()
    return response.json()["token"]


def run_device_flow(print_fn=print) -> str:
    """Requirements 30-33 end to end: prints the verification URL/code, polls,
    exchanges, saves credentials, and returns the new JWT. On any failure this
    raises `DeviceFlowError` before `save_credentials` is ever called — a
    partially-completed login never leaves a corrupt/empty credentials file
    (Edge Case 5).
    """
    authorize = request_device_code()
    print_fn(
        f"To sign in, visit {authorize['verification_url']} and enter code: "
        f"{authorize['user_code']}"
    )
    google_token = poll_for_token(authorize["device_code"], authorize["interval"], authorize["expires_in"])
    token = exchange_id_token(google_token)
    save_credentials(token)
    return token


def ensure_authenticated(print_fn=print) -> str:
    """Requirement 21: the auth-trigger every `runs` subcommand goes through —
    returns a valid stored token, running the device flow first if one isn't
    already present and unexpired.
    """
    credentials = load_credentials()
    if is_valid(credentials):
        return credentials["token"]
    return run_device_flow(print_fn=print_fn)
