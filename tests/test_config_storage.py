"""Unit tests for ``OrchidPostgresConfigStorage`` against a mocked asyncpg pool."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchid_storage_postgres.config_storage import OrchidPostgresConfigStorage, _row_to_config


def _mock_pool() -> tuple[MagicMock, AsyncMock]:
    pool = MagicMock()
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    # ``async with conn.transaction()`` — transaction() is sync and returns
    # an async-context-manager object, NOT awaitable.  Override the AsyncMock
    # default behaviour with a MagicMock so calling it stays sync.
    transaction_cm = MagicMock()
    transaction_cm.__aenter__ = AsyncMock(return_value=None)
    transaction_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=transaction_cm)
    return pool, conn


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_missing_asyncpg_raises_import_error(self):
        store = OrchidPostgresConfigStorage(dsn="postgresql://localhost/db")
        with patch.dict("sys.modules", {"asyncpg": None}):
            with pytest.raises(ImportError):
                await store.init_db()

    @pytest.mark.asyncio
    async def test_close_no_op_when_pool_missing(self):
        store = OrchidPostgresConfigStorage(dsn="postgresql://localhost/db")
        await store.close()  # should not raise


class TestCRUD:
    @pytest.mark.asyncio
    async def test_list_configs_empty(self):
        store = OrchidPostgresConfigStorage(dsn="postgresql://localhost/db")
        store._pool, _ = _mock_pool()
        result = await store.list_configs()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_config_returns_none(self):
        store = OrchidPostgresConfigStorage(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value=None)
        result = await store.get_config("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_config_returns_row(self):
        store = OrchidPostgresConfigStorage(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(
            return_value={
                "name": "agent-a",
                "config": {"description": "x"},
                "created_at": datetime(2026, 1, 1),
                "updated_at": datetime(2026, 1, 2),
            }
        )
        result = await store.get_config("agent-a")
        assert result is not None
        assert result["name"] == "agent-a"
        assert result["config"] == {"description": "x"}

    @pytest.mark.asyncio
    async def test_upsert_config(self):
        store = OrchidPostgresConfigStorage(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(
            return_value={
                "name": "agent-a",
                "config": {"description": "x"},
                "created_at": datetime(2026, 1, 1),
                "updated_at": datetime(2026, 1, 2),
            }
        )
        result = await store.upsert_config("agent-a", {"description": "x"})
        assert result["name"] == "agent-a"

    @pytest.mark.asyncio
    async def test_patch_config_missing_returns_none(self):
        store = OrchidPostgresConfigStorage(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value=None)
        result = await store.patch_config("missing", {"description": "x"})
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_config(self):
        store = OrchidPostgresConfigStorage(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        await store.delete_config("agent-a")
        conn.execute.assert_awaited()


class TestRowMapper:
    def test_row_with_dict_config(self):
        row = {
            "name": "n",
            "config": {"a": 1},
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 2),
        }
        result = _row_to_config(row)
        assert result["config"] == {"a": 1}

    def test_row_with_string_config(self):
        row = {
            "name": "n",
            "config": '{"a": 1}',
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 2),
        }
        result = _row_to_config(row)
        assert result["config"] == {"a": 1}
