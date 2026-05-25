"""
PostgreSQL run-visibility filter fragment.

Registers a ``build_run_filter_clause`` implementation for the ``postgres``
dialect that uses ``$1..$N`` positional parameters (asyncpg convention).
"""

from __future__ import annotations

from typing import Any

from orchid_ai.events.visibility import _Filter  # noqa: PLC2701


def _build_postgres_filter(auth: Any) -> _Filter:
    """Return a ``WHERE`` fragment + positional bind params for PostgreSQL."""
    tenant_key = getattr(auth, "tenant_key", "default")
    user_id = getattr(auth, "user_id", "")
    roles = getattr(auth, "roles", frozenset())

    if "admin" in roles:
        return _Filter(
            where="tenant_key = $1",
            params={"tenant_key": tenant_key},
        )
    return _Filter(
        where=(
            "tenant_key = $1 AND ("
            "visibility = 'tenant' "
            "OR (visibility IN ('actor', 'addressed') "
            "    AND visibility_user_id = $2)"
            ")"
        ),
        params={"tenant_key": tenant_key, "user_id": user_id},
    )
