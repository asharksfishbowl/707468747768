# Dev task runner for Cirq Sandbox Studio / Cirq Studio Tooling.
# Spec: specs/cirq-studio-tooling/cirq-studio-tooling.md, Requirements 9-15.

.PHONY: up down migrate seed test logs

# Requirement 10, Edge Case 1: refuses to start if .env is missing rather than
# silently creating one — an auto-created .env with empty GOOGLE_OAUTH_*/
# JWT_SECRET_KEY would look running but be unable to authenticate anyone.
up:
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Copy .env.example to .env and fill in the required values, then re-run 'make up'." >&2; \
		exit 1; \
	fi
	docker compose up -d postgres redis api worker client-web

# No -v: preserves the postgres named volume (Requirement 15). A full reset
# (docker compose down -v) is deliberately not a Makefile target — wiping
# local data shouldn't be one short command away.
down:
	docker compose down

# Requires `api` already running (make up) — no auto-start (Requirement 11,
# Edge Case 2): a container-not-running failure here is Docker's own error,
# left unmodified.
migrate:
	docker compose exec api alembic -c services/api/alembic.ini upgrade head

# Same no-auto-start rule as migrate (Requirement 12, Edge Case 2).
seed:
	docker compose exec api python -m app.seed

logs:
	docker compose logs -f

# Requirement 13: runs both pytest and the client's type-check, even if the
# first fails, and fails overall if either failed -- tracked independently so
# a single `&&` chain can't hide the second step's result.
test:
	@pytest; pytest_status=$$?; \
	(cd apps/studio && npx tsc --noEmit); tsc_status=$$?; \
	if [ $$pytest_status -ne 0 ] || [ $$tsc_status -ne 0 ]; then \
		echo "make test: FAILED (pytest exit=$$pytest_status, tsc exit=$$tsc_status)" >&2; \
		exit 1; \
	fi; \
	echo "make test: pytest and tsc --noEmit both passed"
