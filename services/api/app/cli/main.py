"""`cirq-studio` — terminal client for Cirq Sandbox Studio's API.

Spec: specs/cirq-studio-tooling/cirq-studio-tooling.md Requirements 18, 21-28,
Edge Cases 4, 7, 8. Registered as an installed command via pyproject.toml's
`[project.scripts] cirq-studio = "app.cli.main:app"`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

import typer

from app.cli import api_client
from app.cli import auth as cli_auth

app = typer.Typer(help="cirq-studio — terminal client for Cirq Sandbox Studio.")
auth_app = typer.Typer(help="Manage the cirq-studio CLI session.")
runs_app = typer.Typer(help="Submit and inspect circuit runs.")
app.add_typer(auth_app, name="auth")
app.add_typer(runs_app, name="runs")


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


@contextmanager
def _translate_errors() -> Iterator[None]:
    """Every command below either calls the API (`api_client.ApiError`) or may
    trigger the device flow (`cli_auth.DeviceFlowError`) — both are "the
    operation failed, report it and exit 1" the same way, so that shape lives
    here once instead of once per command.
    """
    try:
        yield
    except (api_client.ApiError, cli_auth.DeviceFlowError) as e:
        _fail(str(e))


def _print_whoami(token: str) -> None:
    with _translate_errors():
        me = api_client.get_me(token)
    typer.echo(f"{me['email']} ({me['display_name']})")


def _print_histogram(result: dict) -> None:
    """Requirement 26: bitstring -> count text table, one line per outcome, one
    section per MEASURE key."""
    for key, counts in result.items():
        typer.echo(f"[{key}]")
        for bitstring, count in counts.items():
            typer.echo(f"  {bitstring}\t{count}")


# ---------------------------------------------------------------------------
# auth (Requirements 22-24)
# ---------------------------------------------------------------------------


@auth_app.command("login")
def auth_login() -> None:
    """Requirement 22: unconditionally re-authenticates, even with a valid stored
    token already present."""
    with _translate_errors():
        token = cli_auth.run_device_flow(print_fn=typer.echo)
    _print_whoami(token)


@auth_app.command("logout")
def auth_logout() -> None:
    """Requirement 23: removing an already-absent credentials file is success
    (exit 0), not an error — that's already the desired end state."""
    if cli_auth.clear_credentials():
        typer.echo("Logged out.")
    else:
        typer.echo("not signed in")


@auth_app.command("whoami")
def auth_whoami() -> None:
    """Requirement 24: read-only status check — deliberately does NOT call
    `ensure_authenticated` (which would trigger the device flow); a missing/expired
    token here is just reported, not fixed."""
    credentials = cli_auth.load_credentials()
    if not cli_auth.is_valid(credentials):
        typer.echo("not signed in")
        raise typer.Exit(1)
    _print_whoami(credentials["token"])


# ---------------------------------------------------------------------------
# runs (Requirements 21, 25-28, Edge Cases 4, 7, 8)
# ---------------------------------------------------------------------------


@runs_app.command("create")
def runs_create(
    circuit_id: str | None = typer.Option(None, "--circuit-id", help="UUID of a saved circuit."),
    file: Path | None = typer.Option(None, "--file", help="Path to a circuit-definition JSON file."),
    processor: str = typer.Option(..., "--processor"),
    noisy: bool = typer.Option(False, "--noisy"),
    noiseless: bool = typer.Option(False, "--noiseless"),
    repetitions: int = typer.Option(..., "--repetitions"),
) -> None:
    """Requirement 25, Edge Case 7: all validation below happens before any
    network call (auth-trigger included) — a usage error never starts the device
    flow or hits the API."""
    if (circuit_id is None) == (file is None):
        _fail("exactly one of --circuit-id or --file is required")
    if noisy and noiseless:
        _fail("--noisy and --noiseless are mutually exclusive")

    definition = None
    if file is not None:
        try:
            definition = json.loads(file.read_text())
        except (OSError, json.JSONDecodeError) as e:
            _fail(f"could not read circuit file {file}: {e}")

    with _translate_errors():
        token = cli_auth.ensure_authenticated(print_fn=typer.echo)
        result = api_client.create_run(
            token,
            circuit_id=circuit_id,
            definition=definition,
            processor_id=processor,
            noisy=not noiseless,  # neither given -> noisy (matches the API's own default)
            repetitions=repetitions,
        )
    typer.echo(result["run_id"])


@runs_app.command("get")
def runs_get(run_id: str) -> None:
    """Requirement 26."""
    with _translate_errors():
        token = cli_auth.ensure_authenticated(print_fn=typer.echo)
        run = api_client.get_run(token, run_id)

    status = run["status"]
    if status in ("queued", "running"):
        typer.echo(f"status: {status}  processor: {run['processor_id']}  repetitions: {run['repetitions']}")
    elif status == "done":
        _print_histogram(run.get("result") or {})
    elif status == "error":
        typer.echo(f"error: {run.get('error_message')}")


@runs_app.command("watch")
def runs_watch(run_id: str) -> None:
    """Requirement 27, Edge Case 8: plain text output, prints each state
    transition as it arrives; no auto-reconnect on an unexpected drop."""

    def on_message(message: dict) -> None:
        typer.echo(f"status: {message.get('status')}")
        if message.get("status") == "running" and message.get("partial_histogram"):
            _print_histogram(message["partial_histogram"])

    with _translate_errors():
        token = cli_auth.ensure_authenticated(print_fn=typer.echo)
        final = api_client.watch_run(token, run_id, on_message)

    if final["status"] == "done":
        _print_histogram(final.get("result") or {})
        return
    typer.echo(f"error: {final.get('error_message')}")
    raise typer.Exit(1)


@runs_app.command("list")
def runs_list(page: int = typer.Option(1, "--page")) -> None:
    """Requirement 28."""
    with _translate_errors():
        token = cli_auth.ensure_authenticated(print_fn=typer.echo)
        runs = api_client.list_runs(token, page=page)
    for run in runs:
        typer.echo(
            f"{run['id']}  {run['status']}  {run['processor_id']}  {run['repetitions']}  {run['created_at']}"
        )


if __name__ == "__main__":
    app()
