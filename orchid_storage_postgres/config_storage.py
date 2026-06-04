"""PostgreSQL config storage — :class:`OrchidConfigStorage` backed by asyncpg.

Uses the same migration runner as :class:`OrchidPostgresChatStorage` —
the shared ``_schema_ddl.py`` / v001 migration is applied once per
database regardless of which storage class initiates it.
``CREATE TABLE IF NOT EXISTS`` makes this safe to call multiple times.

Configuration::

    config_storage:
      class: orchid_storage_postgres.config_storage.OrchidPostgresConfigStorage
      dsn: postgresql://user:pass@host:5432/db
"""

from __future__ import annotations

import json
import logging
from typing import Any

from orchid_ai.config.schema_agent import OrchidAgentConfig, _deep_merge
from orchid_ai.config.storage import OrchidConfigStorage

from .migrations import PostgresMigrationRunner

logger = logging.getLogger(__name__)


class OrchidPostgresConfigStorage(OrchidConfigStorage):
    """Async PostgreSQL storage for agent configurations."""

    def __init__(self, *, dsn: str, extra_migrations_package: str | None = None) -> None:
        """Keyword-only constructor.

        Parameters
        ----------
        dsn : str
            PostgreSQL connection string
            (e.g. ``"postgresql://user:pass@host:5432/db"``).
        extra_migrations_package : str | None
            Optional dotted import path of integrator-supplied migrations.
        """
        self._dsn = dsn
        self._pool: Any = None
        self._migrator = PostgresMigrationRunner(
            extra_migrations_package=extra_migrations_package,
        )

    async def init_db(self) -> None:
        try:
            import asyncpg
        except ImportError as exc:  # pragma: no cover
            raise ImportError("OrchidPostgresConfigStorage requires asyncpg. Install via: pip install asyncpg") from exc

        self._pool = await asyncpg.create_pool(self._dsn, min_size=2, max_size=10)
        async with self._pool.acquire() as conn:
            await self._migrator.run_up(conn)
        safe_dsn = self._dsn.split("@")[-1] if "@" in self._dsn else "***"
        logger.info("[OrchidConfigStorage:postgres] Initialised — %s", safe_dsn)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def list_configs(self) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT name, config, created_at, updated_at FROM agent_configs ORDER BY updated_at DESC"
            )
        return [_row_to_config(r) for r in rows]

    async def get_config(self, name: str) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT name, config, created_at, updated_at FROM agent_configs WHERE name = $1",
                name,
            )
        return _row_to_config(row) if row else None

    async def upsert_config(self, name: str, config: dict) -> dict:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO agent_configs (name, config, created_at, updated_at)
                VALUES ($1, $2, NOW(), NOW())
                ON CONFLICT (name) DO UPDATE SET
                    config = EXCLUDED.config,
                    updated_at = NOW()
                RETURNING name, config, created_at, updated_at
                """,
                name,
                json.dumps(config),
            )
        return _row_to_config(row)

    async def patch_config(self, name: str, patch: dict) -> dict | None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT name, config, created_at, updated_at FROM agent_configs WHERE name = $1 FOR UPDATE",
                    name,
                )
                if row is None:
                    return None
                existing = _row_to_config(row)
                merged = _deep_merge(existing["config"], patch)
                OrchidAgentConfig.model_validate(merged)
                updated = await conn.fetchrow(
                    """
                    UPDATE agent_configs
                    SET config = $2, updated_at = NOW()
                    WHERE name = $1
                    RETURNING name, config, created_at, updated_at
                    """,
                    name,
                    json.dumps(merged),
                )
                return _row_to_config(updated)

    async def delete_config(self, name: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM agent_configs WHERE name = $1", name)


def _row_to_config(row: Any) -> dict:
    config = row["config"]
    if isinstance(config, str):
        config = json.loads(config)
    return {
        "name": row["name"],
        "config": config,
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }
