"""`cirq-studio` Typer commands (cirq-studio-tooling.md Requirements 18, 21-28,
Edge Cases 4, 7, 8) — auth/api boundaries mocked, per this project's existing
test convention (see tests/test_auth.py's httpx-mocking pattern) rather than a
live server round trip.
"""

import json
from unittest.mock import patch

from typer.testing import CliRunner

from app.cli import api_client
from app.cli import auth as cli_auth
from app.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# auth whoami / login / logout
# ---------------------------------------------------------------------------


def test_whoami_with_no_credentials_prints_not_signed_in_and_exits_1_without_device_flow():
    with patch.object(cli_auth, "load_credentials", return_value=None), patch.object(
        cli_auth, "run_device_flow"
    ) as mock_flow:
        result = runner.invoke(app, ["auth", "whoami"])

    assert result.exit_code == 1
    assert "not signed in" in result.stdout
    mock_flow.assert_not_called()


def test_login_then_whoami_prints_email_and_display_name():
    with patch.object(cli_auth, "run_device_flow", return_value="jwt-token"), patch.object(
        api_client, "get_me", return_value={"email": "a@b.com", "display_name": "A B"}
    ):
        login_result = runner.invoke(app, ["auth", "login"])
    assert login_result.exit_code == 0
    assert "a@b.com" in login_result.stdout

    with patch.object(
        cli_auth,
        "load_credentials",
        return_value={"token": "jwt-token", "expires_at": "2999-01-01T00:00:00+00:00"},
    ), patch.object(api_client, "get_me", return_value={"email": "a@b.com", "display_name": "A B"}):
        whoami_result = runner.invoke(app, ["auth", "whoami"])
    assert whoami_result.exit_code == 0
    assert "a@b.com" in whoami_result.stdout


def test_logout_removes_credentials_then_whoami_reports_not_signed_in():
    with patch.object(cli_auth, "clear_credentials", return_value=True):
        result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0

    with patch.object(cli_auth, "load_credentials", return_value=None):
        whoami_result = runner.invoke(app, ["auth", "whoami"])
    assert "not signed in" in whoami_result.stdout


def test_logout_with_no_stored_credentials_exits_0_not_an_error():
    with patch.object(cli_auth, "clear_credentials", return_value=False):
        result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert "not signed in" in result.stdout


# ---------------------------------------------------------------------------
# runs create (Requirement 25, Edge Case 7)
# ---------------------------------------------------------------------------


def test_runs_create_with_neither_circuit_id_nor_file_exits_1_without_network_call():
    with patch.object(cli_auth, "ensure_authenticated") as mock_auth, patch.object(
        api_client, "create_run"
    ) as mock_create:
        result = runner.invoke(app, ["runs", "create", "--processor", "weber", "--repetitions", "100"])

    assert result.exit_code == 1
    mock_auth.assert_not_called()
    mock_create.assert_not_called()


def test_runs_create_with_both_circuit_id_and_file_exits_1_without_network_call(tmp_path):
    circuit_file = tmp_path / "c.json"
    circuit_file.write_text("{}")
    with patch.object(cli_auth, "ensure_authenticated") as mock_auth, patch.object(
        api_client, "create_run"
    ) as mock_create:
        result = runner.invoke(
            app,
            [
                "runs",
                "create",
                "--circuit-id",
                "11111111-1111-1111-1111-111111111111",
                "--file",
                str(circuit_file),
                "--processor",
                "weber",
                "--repetitions",
                "100",
            ],
        )
    assert result.exit_code == 1
    mock_auth.assert_not_called()
    mock_create.assert_not_called()


def test_runs_create_with_both_noisy_and_noiseless_exits_1_without_network_call():
    with patch.object(cli_auth, "ensure_authenticated") as mock_auth:
        result = runner.invoke(
            app,
            [
                "runs",
                "create",
                "--circuit-id",
                "11111111-1111-1111-1111-111111111111",
                "--processor",
                "weber",
                "--repetitions",
                "100",
                "--noisy",
                "--noiseless",
            ],
        )
    assert result.exit_code == 1
    mock_auth.assert_not_called()


def test_runs_create_with_file_submits_and_prints_run_id(tmp_path):
    circuit_file = tmp_path / "c.json"
    circuit_file.write_text(json.dumps({"processor_id": "weber", "moments": []}))

    with patch.object(cli_auth, "ensure_authenticated", return_value="jwt-token") as mock_auth, patch.object(
        api_client, "create_run", return_value={"run_id": "abc-123", "status": "queued"}
    ) as mock_create:
        result = runner.invoke(
            app,
            [
                "runs",
                "create",
                "--file",
                str(circuit_file),
                "--processor",
                "weber",
                "--noiseless",
                "--repetitions",
                "100",
            ],
        )

    assert result.exit_code == 0
    assert "abc-123" in result.stdout
    mock_auth.assert_called_once()
    _, kwargs = mock_create.call_args
    assert kwargs["noisy"] is False
    assert kwargs["processor_id"] == "weber"
    assert kwargs["repetitions"] == 100


def test_runs_create_defaults_to_noisy_when_neither_flag_given(tmp_path):
    circuit_file = tmp_path / "c.json"
    circuit_file.write_text(json.dumps({"processor_id": "weber", "moments": []}))

    with patch.object(cli_auth, "ensure_authenticated", return_value="jwt-token"), patch.object(
        api_client, "create_run", return_value={"run_id": "abc-123", "status": "queued"}
    ) as mock_create:
        runner.invoke(
            app, ["runs", "create", "--file", str(circuit_file), "--processor", "weber", "--repetitions", "100"]
        )

    assert mock_create.call_args.kwargs["noisy"] is True


def test_runs_create_prints_api_error_detail_and_exits_1(tmp_path):
    circuit_file = tmp_path / "c.json"
    circuit_file.write_text(json.dumps({"processor_id": "weber", "moments": []}))

    with patch.object(cli_auth, "ensure_authenticated", return_value="jwt-token"), patch.object(
        api_client, "create_run", side_effect=api_client.ApiError(400, "bad definition")
    ):
        result = runner.invoke(
            app, ["runs", "create", "--file", str(circuit_file), "--processor", "weber", "--repetitions", "100"]
        )

    assert result.exit_code == 1
    # Error details go to stderr (typer.echo(..., err=True)) -- .output is the
    # combined stream, unlike .stdout which only ever holds the stdout half.
    assert "bad definition" in result.output


# ---------------------------------------------------------------------------
# runs get / list / watch (Requirements 26-28, Edge Case 8)
# ---------------------------------------------------------------------------


def test_runs_get_done_prints_histogram_as_bitstring_count_table():
    run = {
        "status": "done",
        "result": {"result": {"0": 52, "3": 48}},
        "processor_id": "weber",
        "repetitions": 100,
    }
    with patch.object(cli_auth, "ensure_authenticated", return_value="jwt-token"), patch.object(
        api_client, "get_run", return_value=run
    ):
        result = runner.invoke(app, ["runs", "get", "run-id-1"])
    assert result.exit_code == 0
    assert "52" in result.stdout and "48" in result.stdout


def test_runs_get_queued_prints_status_without_histogram():
    run = {"status": "queued", "processor_id": "weber", "repetitions": 100}
    with patch.object(cli_auth, "ensure_authenticated", return_value="jwt-token"), patch.object(
        api_client, "get_run", return_value=run
    ):
        result = runner.invoke(app, ["runs", "get", "run-id-1"])
    assert result.exit_code == 0
    assert "queued" in result.stdout


def test_runs_get_error_prints_error_message():
    run = {"status": "error", "error_message": "timed out after 120s", "processor_id": "weber", "repetitions": 100}
    with patch.object(cli_auth, "ensure_authenticated", return_value="jwt-token"), patch.object(
        api_client, "get_run", return_value=run
    ):
        result = runner.invoke(app, ["runs", "get", "run-id-1"])
    assert result.exit_code == 0
    assert "timed out after 120s" in result.stdout


def test_runs_list_prints_one_line_per_run():
    runs = [
        {
            "id": "r1",
            "status": "done",
            "processor_id": "weber",
            "repetitions": 100,
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]
    with patch.object(cli_auth, "ensure_authenticated", return_value="jwt-token"), patch.object(
        api_client, "list_runs", return_value=runs
    ):
        result = runner.invoke(app, ["runs", "list"])
    assert result.exit_code == 0
    assert "r1" in result.stdout


def test_runs_watch_prints_running_update_with_histogram_before_done():
    messages = [
        {"status": "queued"},
        {"status": "running", "partial_histogram": {"result": {"0": 10}}, "chunks_done": 1, "chunks_total": 1},
        {"status": "done", "result": {"result": {"0": 100}}},
    ]

    def fake_watch_run(token, run_id, on_message):
        for m in messages:
            on_message(m)
        return messages[-1]

    with patch.object(cli_auth, "ensure_authenticated", return_value="jwt-token"), patch.object(
        api_client, "watch_run", side_effect=fake_watch_run
    ):
        result = runner.invoke(app, ["runs", "watch", "run-id-1"])

    assert result.exit_code == 0
    assert "running" in result.stdout
    assert "10" in result.stdout
    assert "100" in result.stdout


def test_runs_watch_error_result_exits_1():
    def fake_watch_run(token, run_id, on_message):
        message = {"status": "error", "error_message": "boom"}
        on_message(message)
        return message

    with patch.object(cli_auth, "ensure_authenticated", return_value="jwt-token"), patch.object(
        api_client, "watch_run", side_effect=fake_watch_run
    ):
        result = runner.invoke(app, ["runs", "watch", "run-id-1"])

    assert result.exit_code == 1
    assert "boom" in result.stdout


def test_runs_watch_run_not_found_prints_error_and_exits_1():
    with patch.object(cli_auth, "ensure_authenticated", return_value="jwt-token"), patch.object(
        api_client, "watch_run", side_effect=api_client.ApiError(4404, "run not found")
    ):
        result = runner.invoke(app, ["runs", "watch", "missing-run"])
    assert result.exit_code == 1
    assert "run not found" in result.output
