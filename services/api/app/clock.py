"""Single shared "current time" helper — every timestamp default (`created_at` /
`updated_at` in models.py, JWT `iat`/`exp` in auth.py) should go through this, not a
locally re-derived `datetime.now(timezone.utc)`.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
