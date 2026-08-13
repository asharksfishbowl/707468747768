# Shared image for the `api` and `worker` compose services (docker-compose.yml) —
# same image, different `command:`. Spec: cirq-studio-tooling.md Requirement 4.
FROM python:3.12-slim

WORKDIR /repo

# Dependencies installed from requirements.txt (pinned, doesn't need any source
# present) before the source is copied in, so this expensive layer -- cirq-core,
# cirq-google, fastapi, etc. -- only gets invalidated when requirements.txt itself
# changes, not on every application-code edit.
COPY pyproject.toml requirements.txt README.md ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY services/api services/api

# --no-deps: dependencies are already installed above: this just registers the
# editable link, so it stays cheap even though it does re-run on every source
# change (the layer above it doesn't).
RUN pip install --no-cache-dir -e . --no-deps
