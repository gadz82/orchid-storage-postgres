"""Unit tests for OrchidPostgresIngestionManifest."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_pool() -> tuple[MagicMock, AsyncMock]:
    pool = MagicMock()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="DELETE 0")
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


def _make_row(**kwargs) -> dict:
    return kwargs


class TestPostgresIngestionManifest:
    @pytest.mark.asyncio
    async def test_missing_asyncpg_raises_import_error(self):
        from orchid_storage_postgres.ingestion_manifest import OrchidPostgresIngestionManifest

        manifest = OrchidPostgresIngestionManifest(dsn="postgresql://localhost/db")
        with patch.dict("sys.modules", {"asyncpg": None}), pytest.raises(ImportError):
            await manifest.init_db()

    @pytest.mark.asyncio
    async def test_should_skip_returns_false_when_no_row(self):
        from orchid_storage_postgres.ingestion_manifest import OrchidPostgresIngestionManifest

        manifest = OrchidPostgresIngestionManifest(dsn="postgresql://localhost/db")
        manifest._pool, conn = _mock_pool()

        result = await manifest.should_skip("src-1", "hash-1", "ns-1")
        assert result is False
        conn.fetchrow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_should_skip_returns_true_for_unchanged_hash(self):
        from orchid_storage_postgres.ingestion_manifest import OrchidPostgresIngestionManifest

        manifest = OrchidPostgresIngestionManifest(dsn="postgresql://localhost/db")
        manifest._pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value={"content_hash": "hash-1"})

        result = await manifest.should_skip("src-1", "hash-1", "ns-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_should_skip_returns_false_for_changed_hash(self):
        from orchid_storage_postgres.ingestion_manifest import OrchidPostgresIngestionManifest

        manifest = OrchidPostgresIngestionManifest(dsn="postgresql://localhost/db")
        manifest._pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value={"content_hash": "old-hash"})

        result = await manifest.should_skip("src-1", "hash-1", "ns-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_record_upserts(self):
        from orchid_storage_postgres.ingestion_manifest import OrchidPostgresIngestionManifest

        manifest = OrchidPostgresIngestionManifest(dsn="postgresql://localhost/db")
        manifest._pool, conn = _mock_pool()

        await manifest.record("src-1", "hash-1", "ns-1", ["doc-1", "doc-2"])
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remove_deletes(self):
        from orchid_storage_postgres.ingestion_manifest import OrchidPostgresIngestionManifest

        manifest = OrchidPostgresIngestionManifest(dsn="postgresql://localhost/db")
        manifest._pool, conn = _mock_pool()

        await manifest.remove("src-1", "ns-1")
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_known(self):
        from orchid_storage_postgres.ingestion_manifest import OrchidPostgresIngestionManifest

        manifest = OrchidPostgresIngestionManifest(dsn="postgresql://localhost/db")
        manifest._pool, conn = _mock_pool()
        conn.fetch = AsyncMock(return_value=[{"source_id": "a"}, {"source_id": "b"}])

        result = await manifest.list_known("ns-1")
        assert result == {"a", "b"}

    @pytest.mark.asyncio
    async def test_get_document_ids(self):
        from orchid_storage_postgres.ingestion_manifest import OrchidPostgresIngestionManifest

        manifest = OrchidPostgresIngestionManifest(dsn="postgresql://localhost/db")
        manifest._pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value={"document_ids": ["doc-1", "doc-2"]})

        result = await manifest.get_document_ids("src-1", "ns-1")
        assert result == ["doc-1", "doc-2"]

    @pytest.mark.asyncio
    async def test_get_document_ids_returns_empty_when_missing(self):
        from orchid_storage_postgres.ingestion_manifest import OrchidPostgresIngestionManifest

        manifest = OrchidPostgresIngestionManifest(dsn="postgresql://localhost/db")
        manifest._pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value=None)

        result = await manifest.get_document_ids("src-1", "ns-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_close_closes_pool(self):
        from orchid_storage_postgres.ingestion_manifest import OrchidPostgresIngestionManifest

        manifest = OrchidPostgresIngestionManifest(dsn="postgresql://localhost/db")
        manifest._pool, _ = _mock_pool()
        close_mock = AsyncMock()
        manifest._pool.close = close_mock

        await manifest.close()
        close_mock.assert_awaited_once()
        assert manifest._pool is None

    @pytest.mark.asyncio
    async def test_should_skip_passes_scope_to_query(self):
        from orchid_storage_postgres.ingestion_manifest import OrchidPostgresIngestionManifest

        manifest = OrchidPostgresIngestionManifest(dsn="postgresql://localhost/db")
        manifest._pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value=None)

        await manifest.should_skip("src-1", "hash-1", "ns-1", scope="t1")

        sql = conn.fetchrow.call_args[0][0]
        assert "scope" in sql
        assert conn.fetchrow.call_args[0][1:4] == ("src-1", "ns-1", "t1")

    @pytest.mark.asyncio
    async def test_record_passes_scope_to_query(self):
        from orchid_storage_postgres.ingestion_manifest import OrchidPostgresIngestionManifest

        manifest = OrchidPostgresIngestionManifest(dsn="postgresql://localhost/db")
        manifest._pool, conn = _mock_pool()

        await manifest.record("src-1", "hash-1", "ns-1", ["doc-1"], scope="t1")

        sql = conn.execute.call_args[0][0]
        assert "scope" in sql
        assert conn.execute.call_args[0][1:5] == ("src-1", "ns-1", "t1", "hash-1")
