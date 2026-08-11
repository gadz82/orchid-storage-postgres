"""Migration v002 — Ingestion manifest for idempotent indexing.

Adds a single table that tracks which source files have been indexed into
which vector namespace, together with their content hash and the vector
document IDs produced during ingestion.  This lets CLI and API indexers
skip unchanged files and delete stale vectors for removed sources.
"""

from __future__ import annotations

VERSION = "002"
DESCRIPTION = "Ingestion manifest for idempotent indexing"

_PG_UP = [
    """
    CREATE TABLE IF NOT EXISTS ingestion_manifest (
        source_id    TEXT NOT NULL,
        namespace    TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        document_ids JSONB NOT NULL DEFAULT '[]',
        indexed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (source_id, namespace)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ingestion_manifest_namespace
        ON ingestion_manifest (namespace)
    """,
]

_PG_DOWN = [
    "DROP INDEX IF EXISTS idx_ingestion_manifest_namespace",
    "DROP TABLE IF EXISTS ingestion_manifest",
]


async def up(conn, *, dialect: str = "postgres") -> None:
    for sql in _PG_UP:
        await conn.execute(sql)


async def down(conn, *, dialect: str = "postgres") -> None:
    for sql in _PG_DOWN:
        await conn.execute(sql)
