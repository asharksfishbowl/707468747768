"""SQLAlchemy models for the `users`, `circuits`, and `runs` tables.

Spec: Requirements 37-39, "Data model (Postgres)".

`definition`/`result` use Postgres JSONB in production; SQLAlchemy's `.with_variant`
falls back to generic JSON on other dialects (e.g. SQLite) so the schema is still
testable without a live Postgres server — JSONB itself has no SQLite equivalent.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Enum, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.clock import utcnow as _utcnow

_JSONB = JSONB().with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    pass


class RunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    google_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    circuits: Mapped[list["Circuit"]] = relationship(back_populates="owner")
    runs: Mapped[list["Run"]] = relationship(back_populates="owner")


class Circuit(Base):
    __tablename__ = "circuits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    definition: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    processor_id: Mapped[str] = mapped_column(String, nullable=False)
    is_public: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    owner: Mapped["User"] = relationship(back_populates="circuits")
    runs: Mapped[list["Run"]] = relationship(back_populates="circuit")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    circuit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("circuits.id"), nullable=True
    )
    definition: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    processor_id: Mapped[str] = mapped_column(String, nullable=False)
    noisy: Mapped[bool] = mapped_column(nullable=False)
    repetitions: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, values_callable=lambda e: [member.value for member in e]),
        nullable=False,
        default=RunStatus.QUEUED,
    )
    result: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    owner: Mapped["User"] = relationship(back_populates="runs")
    circuit: Mapped["Circuit | None"] = relationship(back_populates="runs")
