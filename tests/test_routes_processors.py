import pytest

from app.schema_validation import _VALID_GATES
from cirq_sandbox.engine import list_virtual_processors


def test_list_processors_requires_auth(app_client):
    response = app_client.get("/processors")
    assert response.status_code == 401


def test_list_processors_returns_every_sandbox_processor(app_client, auth_headers):
    response = app_client.get("/processors", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert {p["id"] for p in body} == set(list_virtual_processors())


@pytest.mark.parametrize("processor_id", list_virtual_processors())
def test_processor_entry_has_valid_topology_and_native_gates(
    app_client, auth_headers, processor_id
):
    body = app_client.get("/processors", headers=auth_headers).json()
    entry = next(p for p in body if p["id"] == processor_id)

    topology = entry["topology"]
    assert len(topology["qubits"]) <= 12
    qubit_set = {tuple(q) for q in topology["qubits"]}
    for pair in topology["pairs"]:
        for qubit in pair:
            assert tuple(qubit) in qubit_set

    native_gates = entry["native_gates"]
    assert set(native_gates) <= _VALID_GATES
    # Google sandbox devices compile to CZ as the native two-qubit gate — CNOT/SWAP
    # require decomposition, so they should not show up as natively supported.
    assert "CZ" in native_gates
    assert "CNOT" not in native_gates
    assert "SWAP" not in native_gates


def test_presets_requires_auth(app_client):
    response = app_client.get("/circuits/presets", params={"processor_id": "weber"})
    assert response.status_code == 401


def test_presets_unknown_processor_returns_404(app_client, auth_headers):
    response = app_client.get(
        "/circuits/presets", params={"processor_id": "not-a-real-processor"},
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.parametrize("processor_id", list_virtual_processors())
def test_presets_returns_all_four_in_order(app_client, auth_headers, processor_id):
    response = app_client.get(
        "/circuits/presets", params={"processor_id": processor_id}, headers=auth_headers
    )

    assert response.status_code == 200
    presets = response.json()
    assert len(presets) == 4
    for preset in presets:
        assert preset["processor_id"] == processor_id

    # Requirement 16's order: hello_qubit -> bell_state -> ghz_state -> superposition.
    first_gates = [moment[0]["gate"] for moment in [p["moments"][0] for p in presets]]
    assert first_gates == ["SQRT_X", "H", "H", "H"]
