"""
PostgreSQL migration runner.

The runner discovers migrations in ``orchid_storage_postgres.migrations``
and tracks applied versions in a ``_migrations`` table.
"""

from __future__ import annotations

from typing import Any

from orchid_ai.persistence.migrations.runner import OrchidMigrationRunner

MIGRATIONS_PACKAGE = "orchid_storage_postgres.migrations"


class PostgresMigrationRunner(OrchidMigrationRunner):
    """PostgreSQL-specific migration tracking."""

    dialect = "postgres"
    migrations_package = MIGRATIONS_PACKAGE

    async def ensure_migrations_table(self, conn: Any) -> None:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                version TEXT PRIMARY KEY,
                description TEXT NOT NULL DEFAULT '',
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

    async def get_applied_versions(self, conn: Any) -> set[str]:
        rows = await conn.fetch("SELECT version FROM _migrations")
        return {r["version"] for r in rows}

    async def record_version(self, conn: Any, version: str, description: str) -> None:
        await conn.execute(
            "INSERT INTO _migrations (version, description) VALUES ($1, $2)",
            version,
            description,
        )

    async def remove_version(self, conn: Any, version: str) -> None:
        await conn.execute("DELETE FROM _migrations WHERE version = $1", version)
