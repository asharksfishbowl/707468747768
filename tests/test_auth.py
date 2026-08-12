from datetime import timedelta
from unittest.mock import patch

import jwt
import pytest
from fastapi import Depends, FastAPI, WebSocket
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from app import auth
from app.clock import utcnow
from app.db import get_db
from app.models import User

_FAKE_TOKEN_RESPONSE = {"access_token": "fake-google-access-token"}
_FAKE_PROFILE = {"sub": "google-uid-1", "email": "ada@example.com", "name": "Ada Lovelace"}
_TEST_JWT_SECRET = "test-secret-at-least-32-bytes-long!!"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", _TEST_JWT_SECRET)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URI", "https://api.example.com/auth/google/callback"
    )
    monkeypatch.setenv("CLIENT_BASE_URL", "https://app.example.com")


@pytest.fixture()
def client(db_session):
    test_app = FastAPI()
    test_app.include_router(auth.router)

    @test_app.get("/throwaway-protected")
    def throwaway_protected(user: User = Depends(auth.require_auth)):
        return {"id": str(user.id)}

    @test_app.websocket("/throwaway-ws")
    async def throwaway_ws(websocket: WebSocket, db=Depends(get_db)):
        user = await auth.authenticate_websocket(websocket, db)
        if user is None:
            return
        await websocket.accept()
        await websocket.send_json({"user_id": str(user.id)})
        await websocket.close()

    test_app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(test_app)


def _make_token(user_id, secret=_TEST_JWT_SECRET, expires_delta=timedelta(hours=24)):
    now = utcnow()
    payload = {"sub": str(user_id), "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, secret, algorithm=auth._JWT_ALGORITHM)


def _create_user(db_session):
    user = User(google_id="google-uid-1", email="ada@example.com", display_name="Ada")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# GET /auth/google/login (Requirement 1)
# ---------------------------------------------------------------------------


def test_google_login_redirects_to_google_consent_screen(client):
    response = client.get("/auth/google/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=test-client-id" in location


# ---------------------------------------------------------------------------
# GET /auth/google/callback (Requirement 2, Edge Case 16)
# ---------------------------------------------------------------------------


def test_callback_creates_user_on_first_login_and_reuses_on_second(client, db_session):
    with patch("app.auth._exchange_code_for_token", return_value=_FAKE_TOKEN_RESPONSE), \
         patch("app.auth._fetch_google_profile", return_value=_FAKE_PROFILE):
        first = client.get("/auth/google/callback?code=abc", follow_redirects=False)
        second = client.get("/auth/google/callback?code=abc", follow_redirects=False)

    assert first.status_code in (302, 307)
    assert second.status_code in (302, 307)
    assert db_session.query(User).count() == 1

    for response in (first, second):
        location = response.headers["location"]
        # Fragment, not a query param — see auth.py's google_callback docstring.
        assert location.startswith("https://app.example.com/auth/callback#token=")
        token = location.split("#token=", 1)[1]
        payload = jwt.decode(token, _TEST_JWT_SECRET, algorithms=[auth._JWT_ALGORITHM])
        assert payload["sub"] == str(db_session.query(User).one().id)


def test_callback_denied_consent_creates_no_user_row(client, db_session):
    response = client.get(
        "/auth/google/callback?error=access_denied", follow_redirects=False
    )

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://app.example.com/login?error=access_denied"
    assert db_session.query(User).count() == 0


def test_callback_missing_code_creates_no_user_row(client, db_session):
    response = client.get("/auth/google/callback", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert "error=access_denied" in response.headers["location"]
    assert db_session.query(User).count() == 0


def test_callback_failed_code_exchange_creates_no_user_row(client, db_session):
    with patch("app.auth._exchange_code_for_token", side_effect=RuntimeError("boom")):
        response = client.get("/auth/google/callback?code=abc", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://app.example.com/login?error=oauth_failed"
    assert db_session.query(User).count() == 0


def test_callback_token_issuance_failure_still_redirects_with_no_crash(client, db_session):
    # Regression case for the simplify-pass finding: create_access_token failing
    # (e.g. a JWT signing error) after a successful upsert must still redirect
    # gracefully, not leave the client hanging on an unhandled 500.
    with patch("app.auth._exchange_code_for_token", return_value=_FAKE_TOKEN_RESPONSE), \
         patch("app.auth._fetch_google_profile", return_value=_FAKE_PROFILE), \
         patch("app.auth.create_access_token", side_effect=RuntimeError("signing broke")):
        response = client.get("/auth/google/callback?code=abc", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://app.example.com/login?error=oauth_failed"
    # The upsert already committed before the simulated signing failure — that's
    # expected (a retried login will find and reuse this same row via google_id).
    assert db_session.query(User).count() == 1


# ---------------------------------------------------------------------------
# require_auth / protected routes (Requirement 4, Edge Case 10)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="missing-token"),
        pytest.param({"Authorization": "Bearer not-a-real-jwt"}, id="malformed-token"),
    ],
)
def test_protected_route_without_a_valid_token_returns_401(client, headers):
    response = client.get("/throwaway-protected", headers=headers)
    assert response.status_code == 401


def test_protected_route_with_expired_token_returns_401(client, db_session):
    user = _create_user(db_session)
    token = _make_token(user.id, expires_delta=timedelta(hours=-1))
    response = client.get(
        "/throwaway-protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_protected_route_with_valid_token_succeeds(client, db_session):
    user = _create_user(db_session)
    token = _make_token(user.id)
    response = client.get(
        "/throwaway-protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json() == {"id": str(user.id)}


# ---------------------------------------------------------------------------
# GET /auth/me (Requirement 6)
# ---------------------------------------------------------------------------


def test_auth_me_returns_id_email_display_name(client, db_session):
    user = _create_user(db_session)
    token = _make_token(user.id)
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
    }


# ---------------------------------------------------------------------------
# WS auth helper (Requirement 5, Edge Case 11)
# ---------------------------------------------------------------------------


def test_ws_with_valid_token_connects_and_authenticates(client, db_session):
    user = _create_user(db_session)
    token = _make_token(user.id)

    with client.websocket_connect(f"/throwaway-ws?token={token}") as ws:
        assert ws.receive_json() == {"user_id": str(user.id)}


@pytest.mark.parametrize(
    "make_url",
    [
        pytest.param(lambda db: "/throwaway-ws", id="missing-token"),
        pytest.param(
            lambda db: "/throwaway-ws?token=not-a-real-jwt", id="malformed-token"
        ),
        pytest.param(
            lambda db: f"/throwaway-ws?token={_make_token(_create_user(db).id, expires_delta=timedelta(hours=-1))}",
            id="expired-token",
        ),
    ],
)
def test_ws_without_a_valid_token_closes_with_4401_before_subscribing(
    client, db_session, make_url
):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(make_url(db_session)):
            pass
    assert exc_info.value.code == 4401
