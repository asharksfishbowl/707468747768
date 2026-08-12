"""FastAPI app instance and route registration.

Spec: Requirements 8, 16-23 ("Processors and topology" + "Saved circuits and
gallery" sections), 24-36 ("Runs" section). Auth routes (Requirements 1-7) come from
Phase 2's `app.auth`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth import router as auth_router
from app.auth import validate_required_env
from app.routes.circuits import router as circuits_router
from app.routes.processors import router as processors_router
from app.routes.runs import router as runs_router
from app.ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail fast on missing required config at boot, instead of on whichever request
    # happens to be the first to need a given env var (see auth.py's docstring).
    validate_required_env()
    yield


app = FastAPI(title="Cirq Sandbox Studio API", lifespan=lifespan)

app.include_router(auth_router)
app.include_router(processors_router)
app.include_router(circuits_router)
app.include_router(runs_router)
app.include_router(ws_router)
