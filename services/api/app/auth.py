"""Google OAuth code-exchange flow + JWT issuance/verification.

Spec: Requirements 1-7 ("Auth" section), Edge Cases 10, 11, 16.

Google OAuth client id/secret, the JWT signing secret, and the client app's base URL
are all read from env vars at call time (not import time), so this module imports
cleanly in any environment (including this dev container, which has none of them set)
and fails loudly and specifically only when a route that actually needs one is hit
without it configured. NOTE for whoever builds services/api/app/main.py (Phase 3):
add a startup hook that calls `_env()` for every required var once at boot, so a
misconfigured deployment fails fast instead of on the first real request.
"""

import logging
import os
import uuid
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db import get_db
from app.models import User

logger = logging.getLogger(__name__)

_JWT_ALGORITHM = "HS256"
_JWT_TTL = timedelta(hours=24)
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
_HTTP_TIMEOUT_SECONDS = 10.0

# Env var names as constants, not inline literals, so a typo is a NameError at
# import time instead of a silent "not set" divergence between call sites.
_ENV_JWT_SECRET_KEY = "JWT_SECRET_KEY"
_ENV_GOOGLE_CLIENT_ID = "GOOGLE_OAUTH_CLIENT_ID"
_ENV_GOOGLE_CLIENT_SECRET = "GOOGLE_OAUTH_CLIENT_SECRET"
_ENV_GOOGLE_REDIRECT_URI = "GOOGLE_OAUTH_REDIRECT_URI"
_ENV_CLIENT_BASE_URL = "CLIENT_BASE_URL"
# Used only by /auth/google/device-exchange below (Requirement 32) -- deliberately
# NOT added to validate_required_env()'s startup check: the device-code flow (Cirq
# Studio Tooling spec) is an optional CLI-auth path, unlike the web OAuth vars above
# which the whole API depends on to boot usefully. A deployment that never uses the
# CLI shouldn't be forced to configure a second OAuth client just to start.
_ENV_GOOGLE_DEVICE_CLIENT_ID = "GOOGLE_OAUTH_DEVICE_CLIENT_ID"

router = APIRouter()

# Reused across requests for connection keep-alive to Google's endpoints, rather than
# a throwaway client (and fresh TCP/TLS handshake) per login.
_google_http_client = httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS)


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set — required for Google OAuth / JWT auth")
    return value


def validate_required_env() -> None:
    """Called once at app startup (see services/api/app/main.py's lifespan), so a
    misconfigured deployment fails fast at boot instead of on the first request that
    happens to need one of these.
    """
    for name in (
        _ENV_JWT_SECRET_KEY,
        _ENV_GOOGLE_CLIENT_ID,
        _ENV_GOOGLE_CLIENT_SECRET,
        _ENV_GOOGLE_REDIRECT_URI,
        _ENV_CLIENT_BASE_URL,
    ):
        _env(name)


# ---------------------------------------------------------------------------
# JWT issuance / verification (Requirements 2, 4, 5, 6)
# ---------------------------------------------------------------------------


def create_access_token(user: User) -> str:
    now = utcnow()
    payload = {"sub": str(user.id), "iat": now, "exp": now + _JWT_TTL}
    return jwt.encode(payload, _env(_ENV_JWT_SECRET_KEY), algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises `jwt.PyJWTError` (or a subclass) on missing/invalid/expired/malformed."""
    return jwt.decode(token, _env(_ENV_JWT_SECRET_KEY), algorithms=[_JWT_ALGORITHM])


def require_auth(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency for protected REST routes (Requirement 4). Returns 401 on
    a missing, malformed, or expired `Authorization: Bearer <jwt>` header, or when the
    token's subject no longer maps to a real user.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="invalid or expired token")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")
    return user


async def authenticate_websocket(websocket: WebSocket, db: Session) -> User | None:
    """WS-specific auth helper (Requirement 5): the JWT arrives as `?token=` since
    browser `WebSocket` can't set headers. On a missing/invalid/expired/malformed
    token, or an unknown subject, closes the connection with code 4401 *before* the
    caller subscribes to anything (Edge Case 11) and returns `None`; the caller
    (Phase 4's `WS /runs/{id}/stream`) must check for `None` and stop.
    """
    token = websocket.query_params.get("token")
    user: User | None = None
    if token:
        try:
            payload = decode_access_token(token)
            user_id = uuid.UUID(payload["sub"])
        except (jwt.PyJWTError, ValueError, KeyError):
            user = None
        else:
            # This handler runs on the asyncio event loop (WebSocket routes can't be
            # dispatched through FastAPI's sync-route threadpool the way HTTP routes
            # are), so the blocking DB call is offloaded explicitly — otherwise a
            # single WS auth check would stall every other connection on this worker.
            user = await run_in_threadpool(db.get, User, user_id)

    if user is None:
        await websocket.close(code=4401)
        return None
    return user


# ---------------------------------------------------------------------------
# Google OAuth code-exchange flow (Requirements 1, 2, 16)
# ---------------------------------------------------------------------------


def _exchange_code_for_token(code: str) -> dict:
    response = _google_http_client.post(
        _GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": _env(_ENV_GOOGLE_CLIENT_ID),
            "client_secret": _env(_ENV_GOOGLE_CLIENT_SECRET),
            "redirect_uri": _env(_ENV_GOOGLE_REDIRECT_URI),
            "grant_type": "authorization_code",
        },
    )
    response.raise_for_status()
    return response.json()


def _fetch_google_profile(access_token: str) -> dict:
    response = _google_http_client.get(
        _GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return response.json()


def _get_or_create_user(db: Session, profile: dict) -> User:
    google_id = profile["sub"]
    user = db.query(User).filter_by(google_id=google_id).one_or_none()
    if user is not None:
        return user

    user = User(
        google_id=google_id,
        email=profile["email"],
        display_name=profile.get("name") or profile["email"],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/auth/google/login")
def google_login() -> RedirectResponse:
    """Redirects to Google's OAuth consent screen (Requirement 1)."""
    params = {
        "client_id": _env(_ENV_GOOGLE_CLIENT_ID),
        "redirect_uri": _env(_ENV_GOOGLE_REDIRECT_URI),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    return RedirectResponse(f"{_GOOGLE_AUTH_URL}?{urlencode(params)}")


@router.get("/auth/google/callback")
def google_callback(
    code: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Exchanges the OAuth code, upserts the `users` row, issues a JWT (Requirement 2).

    On denied consent or any failure in the exchange/profile-fetch/upsert/token-issuance
    chain, redirects to the client's Login screen with `?error=` set instead of a token
    (Edge Case 16). Token issuance is inside the same error boundary as the rest of the
    flow — a `create_access_token` failure (e.g. misconfigured JWT_SECRET_KEY) after a
    successful upsert must still redirect gracefully, not crash the client's browser
    mid-flow; the exception is always logged first, so an operator can tell a real
    misconfiguration apart from an ordinary failed exchange or denied consent, even
    though both look the same (`?error=oauth_failed`) to the user.
    """
    client_base_url = _env(_ENV_CLIENT_BASE_URL)
    if error or not code:
        return RedirectResponse(f"{client_base_url}/login?error=access_denied")

    try:
        token_response = _exchange_code_for_token(code)
        profile = _fetch_google_profile(token_response["access_token"])
        user = _get_or_create_user(db, profile)
        jwt_token = create_access_token(user)
    except Exception:
        logger.exception("Google OAuth callback failed")
        db.rollback()
        return RedirectResponse(f"{client_base_url}/login?error=oauth_failed")

    # Fragment, not a query param: browsers never send URL fragments to any server,
    # so this keeps the one-time bearer token out of access logs, proxies, and
    # Referer headers. (Requirement 5's WS `?token=` is a different, spec-forced case
    # — browser WebSocket genuinely cannot set headers — not a precedent for this
    # plain HTTP redirect, which can use a fragment instead.)
    return RedirectResponse(f"{client_base_url}/auth/callback#token={jwt_token}")


@router.get("/auth/me")
def auth_me(user: User = Depends(require_auth)) -> dict:
    """Returns the authenticated user's id, email, and display name (Requirement 6)."""
    return {"id": str(user.id), "email": user.email, "display_name": user.display_name}


# ---------------------------------------------------------------------------
# Device-code auth flow (cirq-studio-tooling.md Requirements 29-33)
# ---------------------------------------------------------------------------


class DeviceExchangeRequest(BaseModel):
    id_token: str


@router.post("/auth/google/device-exchange")
def google_device_exchange(
    body: DeviceExchangeRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Requirement 32: the CLI-facing counterpart to `google_callback` above --
    verifies a Google `id_token` (obtained by `cirq-studio`'s own device-code polling,
    Requirement 31) instead of exchanging an authorization code, but funnels into the
    SAME user-upsert/JWT-issuance helpers so first-login-creates/subsequent-logins-reuse
    behavior (Requirement 2) is identical either way. Returns JSON (`{"token": ...}`),
    not a redirect -- the caller is a terminal, not a browser.
    """
    audience = _env(_ENV_GOOGLE_DEVICE_CLIENT_ID)
    try:
        claims = google_id_token.verify_oauth2_token(
            body.id_token, google_requests.Request(), audience=audience
        )
    except Exception:
        # Edge Case 6: no `users` row created on a failed verification -- same
        # "no side effects on a failed auth attempt" principle as Edge Case 16's
        # web-callback failure path above.
        raise HTTPException(status_code=401, detail="invalid id_token")

    profile = {"sub": claims["sub"], "email": claims["email"], "name": claims.get("name")}
    user = _get_or_create_user(db, profile)
    return {"token": create_access_token(user)}
