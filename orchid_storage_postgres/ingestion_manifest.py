"""PostgreSQL :class:`OrchidIngestionManifest` — idempotent indexing manifest.

Backed by ``asyncpg``.  Shares the same database and migration system
as :class:`OrchidPostgresChatStorage`; the ``ingestion_manifest`` table
is created by migration ``v002_ingestion_manifest``.

Configuration::

    INDEX_MANIFEST_CLASS=orchid_storage_postgres.ingestion_manifest.OrchidPostgresIngestionManifest
    INDEX_MANIFEST_DSN=postgresql://user:pass@host:5432/db
"""

from __future__ import annotations

import json
import logging
from typing import Any

from orchid_ai.core.ingestion_manifest import OrchidIngestionManifest

from .migrations import PostgresMigrationRunner

logger = logging.getLogger(__name__)


class OrchidPostgresIngestionManifest(OrchidIngestionManifest):
    """Async PostgreSQL storage for ingestion manifests.

    Tracks content hashes and vector document IDs per ``(source_id,
    namespace)`` so callers can skip unchanged files and prune removed
    sources.

    Pool: ``min_size=2, max_size=10``.
    """

    def __init__(self, *, dsn: str, extra_migrations_package: str | None = None):
        self._dsn = dsn
        self._pool: Any = None
        self._migrator = PostgresMigrationRunner(
            extra_migrations_package=extra_migrations_package,
        )

    async def init_db(self) -> None:
        try:
            import asyncpg
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "OrchidPostgresIngestionManifest requires asyncpg. Install via: pip install asyncpg"
            ) from exc

        self._pool = await asyncpg.create_pool(self._dsn, min_size=2, max_size=10)
        async with self._pool.acquire() as conn:
            await self._migrator.run_up(conn)
        logger.info(
            "[OrchidIngestionManifest:postgres] Initialised — %s",
            self._dsn.split("@")[-1] if "@" in self._dsn else "***",
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def should_skip(self, source_id: str, content_hash: str, namespace: str, scope: str = "") -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT content_hash FROM ingestion_manifest "
                "WHERE source_id = $1 AND namespace = $2 AND scope = $3",
                source_id,
                namespace,
                scope,
            )
        if row is None:
            return False
        return row["content_hash"] == content_hash

    async def record(
        self,
        source_id: str,
        content_hash: str,
        namespace: str,
        document_ids: list[str],
        scope: str = "",
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ingestion_manifest
                    (source_id, namespace, scope, content_hash, document_ids, indexed_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (source_id, namespace, scope) DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    document_ids = EXCLUDED.document_ids,
                    indexed_at = EXCLUDED.indexed_at
                """,
                source_id,
                namespace,
                scope,
                content_hash,
                document_ids,
            )

    async def remove(self, source_id: str, namespace: str, scope: str = "") -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM ingestion_manifest WHERE source_id = $1 AND namespace = $2 AND scope = $3",
                source_id,
                namespace,
                scope,
            )

    async def list_known(self, namespace: str, scope: str = "") -> set[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT source_id FROM ingestion_manifest WHERE namespace = $1 AND scope = $2",
                namespace,
                scope,
            )
        return {row["source_id"] for row in rows}

    async def get_document_ids(self, source_id: str, namespace: str, scope: str = "") -> list[str]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT document_ids FROM ingestion_manifest "
                "WHERE source_id = $1 AND namespace = $2 AND scope = $3",
                source_id,
                namespace,
                scope,
            )
        if row is None:
            return []
        document_ids = row["document_ids"]
        if isinstance(document_ids, str):
            try:
                return json.loads(document_ids)
            except json.JSONDecodeError:
                return []
        if isinstance(document_ids, list):
            return document_ids
        return []
