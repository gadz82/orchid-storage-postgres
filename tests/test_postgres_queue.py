"""Unit tests for ``PostgresSignalQueue`` against a mocked ``asyncpg`` pool.

These exercise construction validation, the no-asyncpg ImportError path,
the post-commit NOTIFY plumbing, and the basic ack / nack code paths
without requiring a live Postgres server.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchid_storage_postgres.event_queue import (
    PostgresSignalQueue,
    _PostgresDBTransaction,
    _ensure_aware,
)


# ── Helpers ─────────────────────────────────────────────────


def _mock_pool() -> tuple[MagicMock, AsyncMock]:
    pool = MagicMock()
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)

    # ``async with pool.acquire() as conn``
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    # ``async with conn.transaction()`` — transaction() is sync and returns
    # an async-context-manager object, NOT awaitable.  Override the AsyncMock
    # default with a MagicMock so calling it stays sync.
    transaction_cm = MagicMock()
    transaction_cm.__aenter__ = AsyncMock(return_value=None)
    transaction_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=transaction_cm)
    return pool, conn


# ── Construction ──────────────────────────────────────────────


class TestConstruction:
    def test_requires_pool_or_dsn(self):
        with pytest.raises(ValueError):
            PostgresSignalQueue()

    def test_pool_xor_dsn(self):
        with pytest.raises(ValueError):
            PostgresSignalQueue(pool=MagicMock(), dsn="postgresql://x")

    def test_accepts_pool(self):
        q = PostgresSignalQueue(pool=MagicMock())
        assert q._owned_pool is False

    def test_accepts_dsn(self):
        q = PostgresSignalQueue(dsn="postgresql://localhost/db")
        assert q._owned_pool is True
        assert q._pool is None  # not yet opened

    @pytest.mark.asyncio
    async def test_pool_property_raises_before_init(self):
        q = PostgresSignalQueue(dsn="postgresql://localhost/db")
        with pytest.raises(RuntimeError, match="init_db"):
            _ = q.pool


# ── Lifecycle ─────────────────────────────────────────────────


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_init_db_missing_asyncpg_raises_import_error(self):
        q = PostgresSignalQueue(dsn="postgresql://localhost/db")
        with patch.dict("sys.modules", {"asyncpg": None}):
            with pytest.raises(ImportError):
                await q.init_db()

    @pytest.mark.asyncio
    async def test_close_only_closes_owned_pool(self):
        external_pool = MagicMock()
        external_pool.close = AsyncMock()
        q = PostgresSignalQueue(pool=external_pool)
        await q.close()
        external_pool.close.assert_not_awaited()


# ── Enqueue ────────────────────────────────────────────────────


class TestEnqueue:
    @pytest.mark.asyncio
    async def test_standalone_enqueue_inserts_and_notifies(self):
        pool, conn = _mock_pool()
        q = PostgresSignalQueue(pool=pool, notify_enabled=True)

        signal_id = uuid.uuid4()
        msg_id = await q.enqueue(signal_id)

        # one INSERT + one pg_notify SELECT
        assert conn.execute.await_count == 2
        assert isinstance(msg_id, str)

    @pytest.mark.asyncio
    async def test_standalone_enqueue_skips_notify_when_disabled(self):
        pool, conn = _mock_pool()
        q = PostgresSignalQueue(pool=pool, notify_enabled=False)

        await q.enqueue(uuid.uuid4())
        # only the INSERT
        assert conn.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_enqueue_inside_tx_stages_notify(self):
        pool, _conn = _mock_pool()
        q = PostgresSignalQueue(pool=pool, notify_enabled=True)

        tx_conn = AsyncMock()
        tx = _PostgresDBTransaction(tx_conn)

        msg_id = await q.enqueue(uuid.uuid4(), tx=tx)
        # INSERT was issued through tx.conn, not the pool
        tx_conn.execute.assert_awaited_once()
        assert msg_id in tx.pending_notifies

    @pytest.mark.asyncio
    async def test_enqueue_with_foreign_tx_rejected(self):
        pool, _conn = _mock_pool()
        q = PostgresSignalQueue(pool=pool)

        class _OtherTx:
            pass

        with pytest.raises(RuntimeError, match="non-Postgres"):
            await q.enqueue(uuid.uuid4(), tx=_OtherTx())  # type: ignore[arg-type]


# ── Ack / Nack / DLQ ─────────────────────────────────────────


class TestAckNack:
    @pytest.mark.asyncio
    async def test_ack(self):
        pool, conn = _mock_pool()
        q = PostgresSignalQueue(pool=pool)

        await q.ack(str(uuid.uuid4()))
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_nack_unknown_msg_no_op(self):
        pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value=None)
        q = PostgresSignalQueue(pool=pool)

        await q.nack(str(uuid.uuid4()), retry_after_seconds=5)

    @pytest.mark.asyncio
    async def test_nack_under_max_attempts_reschedules(self):
        pool, conn = _mock_pool()
        sig = uuid.uuid4()
        conn.fetchrow = AsyncMock(return_value={"signal_id": sig, "attempt": 1})
        q = PostgresSignalQueue(pool=pool, max_attempts=5)

        await q.nack(str(uuid.uuid4()), retry_after_seconds=10)
        # one fetchrow + one UPDATE
        assert conn.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_nack_at_max_attempts_moves_to_dlq(self):
        pool, conn = _mock_pool()
        sig = uuid.uuid4()
        conn.fetchrow = AsyncMock(return_value={"signal_id": sig, "attempt": 5})
        q = PostgresSignalQueue(pool=pool, max_attempts=5)

        await q.nack(str(uuid.uuid4()), retry_after_seconds=10)
        # DLQ INSERT + DELETE = 2 executes
        assert conn.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_dead_letter_unknown_no_op(self):
        pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value=None)
        q = PostgresSignalQueue(pool=pool)

        await q.dead_letter(str(uuid.uuid4()), reason="boom")


# ── Observability helpers ───────────────────────────────────


class TestCounts:
    @pytest.mark.asyncio
    async def test_visible_count(self):
        pool, conn = _mock_pool()
        conn.fetchval = AsyncMock(return_value=3)
        q = PostgresSignalQueue(pool=pool)
        assert await q.visible_count() == 3

    @pytest.mark.asyncio
    async def test_in_flight_count(self):
        pool, conn = _mock_pool()
        conn.fetchval = AsyncMock(return_value=2)
        q = PostgresSignalQueue(pool=pool)
        assert await q.in_flight_count() == 2

    @pytest.mark.asyncio
    async def test_dead_letter_count(self):
        pool, conn = _mock_pool()
        conn.fetchval = AsyncMock(return_value=1)
        q = PostgresSignalQueue(pool=pool)
        assert await q.dead_letter_count() == 1


# ── Helpers ──────────────────────────────────────────────────


class TestEnsureAware:
    def test_none_returns_now(self):
        result = _ensure_aware(None)
        assert result.tzinfo is _dt.UTC

    def test_naive_gets_utc(self):
        naive = _dt.datetime(2026, 1, 1)
        aware = _ensure_aware(naive)
        assert aware.tzinfo is _dt.UTC

    def test_aware_passes_through(self):
        aware = _dt.datetime(2026, 1, 1, tzinfo=_dt.UTC)
        assert _ensure_aware(aware) is aware
