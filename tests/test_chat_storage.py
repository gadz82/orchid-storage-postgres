"""Tests for ``OrchidPostgresChatStorage`` against a mocked ``asyncpg`` pool."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


from orchid_storage_postgres.chat_storage import OrchidPostgresChatStorage, _row_to_message, _row_to_session


# ── Helpers ─────────────────────────────────────────────────


def _mock_pool() -> MagicMock:
    pool = MagicMock()
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)

    # Support ``async with pool.acquire() as conn``
    async def _acquire():
        return conn

    pool.acquire.return_value.__aenter__ = AsyncMock(side_effect=_acquire)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    pool.execute = AsyncMock()
    return pool


async def _init_store(store: OrchidPostgresChatStorage, pool: MagicMock) -> OrchidPostgresChatStorage:
    with patch.object(store, "init_db", AsyncMock()) as mock_init:
        mock_init.side_effect = None  # real init_db would set _pool
        store._pool = pool
    return store


# ── Construction ──────────────────────────────────────────────


class TestConstruction:
    @pytest.mark.asyncio
    async def test_missing_driver_raises_import_error(self):
        with patch.dict("sys.modules", {"asyncpg": None}):
            store = OrchidPostgresChatStorage(dsn="postgresql://localhost/db")
            with pytest.raises(ImportError):
                await store.init_db()

    @pytest.mark.asyncio
    async def test_init_db_creates_pool(self):
        mock_asyncpg = MagicMock()
        mock_pool = MagicMock()
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch.dict("sys.modules", {"asyncpg": mock_asyncpg}):
            store = OrchidPostgresChatStorage(dsn="postgresql://localhost/db")
            await store.init_db()
            mock_asyncpg.create_pool.assert_awaited_once()


# ── CRUD ─────────────────────────────────────────────────────


class TestChatCRUD:
    @pytest.mark.asyncio
    async def test_create_chat(self):
        store = OrchidPostgresChatStorage(dsn="postgresql://localhost/db")
        store._pool = _mock_pool()
        conn = await store._pool.acquire().__aenter__()

        chat = await store.create_chat("t1", "u1", "Hello")
        assert chat.tenant_id == "t1"
        assert chat.user_id == "u1"
        assert chat.title == "Hello"
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_list_chats(self):
        store = OrchidPostgresChatStorage(dsn="postgresql://localhost/db")
        store._pool = _mock_pool()
        conn = await store._pool.acquire().__aenter__()
        conn.fetch = AsyncMock(return_value=[])

        chats = await store.list_chats("t1", "u1")
        assert chats == []

    @pytest.mark.asyncio
    async def test_get_chat_returns_none_for_missing(self):
        store = OrchidPostgresChatStorage(dsn="postgresql://localhost/db")
        store._pool = _mock_pool()
        conn = await store._pool.acquire().__aenter__()
        conn.fetchrow = AsyncMock(return_value=None)

        chat = await store.get_chat("missing")
        assert chat is None

    @pytest.mark.asyncio
    async def test_delete_chat(self):
        store = OrchidPostgresChatStorage(dsn="postgresql://localhost/db")
        store._pool = _mock_pool()
        conn = await store._pool.acquire().__aenter__()

        await store.delete_chat("c1")
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_title(self):
        store = OrchidPostgresChatStorage(dsn="postgresql://localhost/db")
        store._pool = _mock_pool()
        conn = await store._pool.acquire().__aenter__()

        await store.update_title("c1", "New Title")
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_mark_shared(self):
        store = OrchidPostgresChatStorage(dsn="postgresql://localhost/db")
        store._pool = _mock_pool()
        conn = await store._pool.acquire().__aenter__()

        await store.mark_shared("c1")
        conn.execute.assert_awaited()


# ── Messages ─────────────────────────────────────────────────


class TestMessages:
    @pytest.mark.asyncio
    async def test_add_message(self):
        store = OrchidPostgresChatStorage(dsn="postgresql://localhost/db")
        store._pool = _mock_pool()
        conn = await store._pool.acquire().__aenter__()

        msg = await store.add_message("c1", "user", "hello")
        assert msg.chat_id == "c1"
        assert msg.role == "user"
        assert msg.content == "hello"
        assert conn.execute.await_count >= 2  # INSERT + UPDATE

    @pytest.mark.asyncio
    async def test_get_messages(self):
        store = OrchidPostgresChatStorage(dsn="postgresql://localhost/db")
        store._pool = _mock_pool()
        conn = await store._pool.acquire().__aenter__()
        conn.fetch = AsyncMock(return_value=[])

        msgs = await store.get_messages("c1", limit=10)
        assert msgs == []


# ── Conversation summaries ───────────────────────────────────


class TestConversationSummaries:
    @pytest.mark.asyncio
    async def test_get_summary_returns_none(self):
        store = OrchidPostgresChatStorage(dsn="postgresql://localhost/db")
        store._pool = _mock_pool()
        conn = await store._pool.acquire().__aenter__()
        conn.fetchrow = AsyncMock(return_value=None)

        result = await store.get_conversation_summary("c1")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_summary(self):
        store = OrchidPostgresChatStorage(dsn="postgresql://localhost/db")
        store._pool = _mock_pool()
        conn = await store._pool.acquire().__aenter__()

        await store.save_conversation_summary("c1", "Summary text", 3)
        conn.execute.assert_awaited()


# ── Row mappers ──────────────────────────────────────────────


class TestRowMappers:
    def test_row_to_session(self):
        row = {
            "id": "s1",
            "tenant_id": "t1",
            "user_id": "u1",
            "title": "Test",
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 2),
            "is_shared": True,
        }
        session = _row_to_session(row)
        assert session.id == "s1"
        assert session.is_shared is True

    def test_row_to_message_jsonb_parsed(self):
        row = {
            "id": "m1",
            "chat_id": "c1",
            "role": "assistant",
            "content": "Hi there",
            "agents_used": json.dumps(["agent-a"]),
            "created_at": datetime(2026, 1, 1),
            "metadata": json.dumps({"k": "v"}),
        }
        msg = _row_to_message(row)
        assert msg.agents_used == ["agent-a"]
        assert msg.metadata == {"k": "v"}

    def test_row_to_message_already_parsed(self):
        row = {
            "id": "m1",
            "chat_id": "c1",
            "role": "assistant",
            "content": "Hi",
            "agents_used": ["agent-a"],
            "created_at": datetime(2026, 1, 1),
            "metadata": {"k": "v"},
        }
        msg = _row_to_message(row)
        assert msg.agents_used == ["agent-a"]
        assert msg.metadata == {"k": "v"}
