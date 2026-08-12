import pytest

from app.auth import create_access_token
from app.models import User

_VALID_DEFINITION = {
    "processor_id": "weber",
    "moments": [
        [{"gate": "H", "qubits": [[0, 0]]}],
        [{"gate": "MEASURE", "qubits": [[0, 0]], "key": "result"}],
    ],
}


@pytest.fixture()
def other_user(db_session):
    u = User(google_id="other-google-id", email="bo@example.com", display_name="Bo")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture()
def other_auth_headers(other_user):
    return {"Authorization": f"Bearer {create_access_token(other_user)}"}


def _create(app_client, auth_headers, *, name="My Circuit", is_public=False, definition=None):
    response = app_client.post(
        "/circuits",
        headers=auth_headers,
        json={"name": name, "definition": definition or _VALID_DEFINITION, "is_public": is_public},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# POST /circuits (Requirement 17)
# ---------------------------------------------------------------------------


def test_create_circuit_requires_auth(app_client):
    response = app_client.post(
        "/circuits", json={"name": "x", "definition": _VALID_DEFINITION, "is_public": False}
    )
    assert response.status_code == 401


def test_create_circuit_persists_and_returns_full_definition(app_client, auth_headers, user):
    circuit = _create(app_client, auth_headers, name="Bell Test")

    assert circuit["name"] == "Bell Test"
    assert circuit["processor_id"] == "weber"
    assert circuit["is_public"] is False
    assert circuit["definition"] == _VALID_DEFINITION


def test_create_circuit_with_unsupported_gate_returns_400(app_client, auth_headers):
    bad_definition = {
        "processor_id": "weber",
        "moments": [[{"gate": "TOFFOLI", "qubits": [[0, 0]]}]],
    }
    response = app_client.post(
        "/circuits",
        headers=auth_headers,
        json={"name": "bad", "definition": bad_definition, "is_public": False},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /circuits (Requirement 18)
# ---------------------------------------------------------------------------


def test_list_circuits_returns_only_own_circuits_without_definition(
    app_client, auth_headers, other_auth_headers
):
    mine = _create(app_client, auth_headers, name="Mine")
    _create(app_client, other_auth_headers, name="Not Mine")

    response = app_client.get("/circuits", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert [c["id"] for c in body] == [mine["id"]]
    assert "definition" not in body[0]


def test_list_circuits_newest_first_and_paginated(app_client, auth_headers):
    for i in range(3):
        _create(app_client, auth_headers, name=f"Circuit {i}")

    page1 = app_client.get(
        "/circuits", headers=auth_headers, params={"page": 1, "page_size": 2}
    ).json()
    page2 = app_client.get(
        "/circuits", headers=auth_headers, params={"page": 2, "page_size": 2}
    ).json()

    assert [c["name"] for c in page1] == ["Circuit 2", "Circuit 1"]
    assert [c["name"] for c in page2] == ["Circuit 0"]


# ---------------------------------------------------------------------------
# GET /circuits/{id} (Requirement 19, Edge Case 9)
# ---------------------------------------------------------------------------


def test_get_own_circuit_returns_full_definition(app_client, auth_headers):
    circuit = _create(app_client, auth_headers)
    response = app_client.get(f"/circuits/{circuit['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["definition"] == _VALID_DEFINITION


def test_get_public_circuit_by_non_owner_succeeds(app_client, auth_headers, other_auth_headers):
    circuit = _create(app_client, auth_headers, is_public=True)
    response = app_client.get(f"/circuits/{circuit['id']}", headers=other_auth_headers)
    assert response.status_code == 200


def test_get_private_circuit_by_non_owner_returns_404_not_403(
    app_client, auth_headers, other_auth_headers
):
    circuit = _create(app_client, auth_headers, is_public=False)
    response = app_client.get(f"/circuits/{circuit['id']}", headers=other_auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PUT /circuits/{id} (Requirement 20, Edge Case 9)
# ---------------------------------------------------------------------------


def test_update_own_circuit_partial_fields(app_client, auth_headers):
    circuit = _create(app_client, auth_headers, name="Original", is_public=False)

    response = app_client.put(
        f"/circuits/{circuit['id']}", headers=auth_headers, json={"is_public": True}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Original"  # untouched
    assert body["is_public"] is True
    assert body["definition"] == _VALID_DEFINITION  # untouched


def test_update_circuit_by_non_owner_returns_404_even_if_public(
    app_client, auth_headers, other_auth_headers
):
    circuit = _create(app_client, auth_headers, is_public=True)
    response = app_client.put(
        f"/circuits/{circuit['id']}", headers=other_auth_headers, json={"name": "hijacked"}
    )
    assert response.status_code == 404


def test_update_circuit_with_invalid_definition_returns_400(app_client, auth_headers):
    circuit = _create(app_client, auth_headers)
    response = app_client.put(
        f"/circuits/{circuit['id']}",
        headers=auth_headers,
        json={"definition": {"processor_id": "weber", "moments": [[{"gate": "NOPE", "qubits": [[0, 0]]}]]}},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /circuits/{id} (Requirement 21, Edge Case 9)
# ---------------------------------------------------------------------------


def test_delete_own_circuit(app_client, auth_headers):
    circuit = _create(app_client, auth_headers)
    response = app_client.delete(f"/circuits/{circuit['id']}", headers=auth_headers)
    assert response.status_code == 204
    assert app_client.get(f"/circuits/{circuit['id']}", headers=auth_headers).status_code == 404


def test_delete_circuit_by_non_owner_returns_404_even_if_public(
    app_client, auth_headers, other_auth_headers
):
    circuit = _create(app_client, auth_headers, is_public=True)
    response = app_client.delete(f"/circuits/{circuit['id']}", headers=other_auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /circuits/gallery (Requirement 22)
# ---------------------------------------------------------------------------


def test_gallery_shows_public_circuits_from_other_users_with_owner_name(
    app_client, auth_headers, other_auth_headers, other_user
):
    _create(app_client, auth_headers, name="Private", is_public=False)
    public = _create(app_client, other_auth_headers, name="Public", is_public=True)

    response = app_client.get("/circuits/gallery", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert [c["id"] for c in body] == [public["id"]]
    assert body[0]["owner_display_name"] == other_user.display_name


# ---------------------------------------------------------------------------
# POST /circuits/{id}/clone (Requirement 23, Edge Case 14)
# ---------------------------------------------------------------------------


def test_clone_public_circuit_creates_independent_copy(
    app_client, auth_headers, other_auth_headers
):
    original = _create(app_client, other_auth_headers, name="Original", is_public=True)

    response = app_client.post(f"/circuits/{original['id']}/clone", headers=auth_headers)

    assert response.status_code == 200
    clone = response.json()
    assert clone["id"] != original["id"]
    assert clone["name"] == "Original (copy)"
    assert clone["is_public"] is False
    assert clone["definition"] == _VALID_DEFINITION

    # Editing the clone doesn't touch the original (no lasting link).
    app_client.put(
        f"/circuits/{clone['id']}", headers=auth_headers, json={"name": "Edited Clone"}
    )
    original_after = app_client.get(
        f"/circuits/{original['id']}", headers=other_auth_headers
    ).json()
    assert original_after["name"] == "Original"


def test_clone_own_public_circuit_is_allowed_not_a_no_op(app_client, auth_headers):
    original = _create(app_client, auth_headers, name="Mine", is_public=True)
    response = app_client.post(f"/circuits/{original['id']}/clone", headers=auth_headers)

    assert response.status_code == 200
    clone = response.json()
    assert clone["id"] != original["id"]
    assert clone["name"] == "Mine (copy)"


def test_clone_private_circuit_by_non_owner_returns_404(
    app_client, auth_headers, other_auth_headers
):
    original = _create(app_client, auth_headers, is_public=False)
    response = app_client.post(
        f"/circuits/{original['id']}/clone", headers=other_auth_headers
    )
    assert response.status_code == 404
