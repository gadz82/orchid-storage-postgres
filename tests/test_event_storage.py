"""Unit tests for ``PostgresEventStorage`` and the four narrow stores."""

from __future__ import annotations

import datetime as _dt
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchid_ai.core.events.job import JobRun, JobSpec, JobStatus
from orchid_ai.core.events.signal import Signal
from orchid_ai.core.events.store import OrchidScheduleRecord, OrchidTriggerRecord

from orchid_storage_postgres.event_storage import (
    PostgresEventStorage,
    PostgresJobStore,
    PostgresScheduleStore,
    PostgresSignalStore,
    PostgresTriggerStore,
    _maybe_load_jsonb,
    _row_to_run,
    _row_to_schedule,
    _row_to_signal,
    _row_to_trigger,
)


def _mock_pool() -> tuple[MagicMock, AsyncMock]:
    pool = MagicMock()
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


# ── Facade construction ─────────────────────────────────────


class TestFacade:
    def test_requires_pool_or_dsn(self):
        with pytest.raises(ValueError):
            PostgresEventStorage()

    def test_pool_xor_dsn(self):
        with pytest.raises(ValueError):
            PostgresEventStorage(pool=MagicMock(), dsn="postgresql://x")

    def test_property_access_before_init_raises(self):
        store = PostgresEventStorage(dsn="postgresql://x")
        with pytest.raises(RuntimeError, match="init_db"):
            _ = store.signals

    @pytest.mark.asyncio
    async def test_init_db_missing_asyncpg_raises_import_error(self):
        store = PostgresEventStorage(dsn="postgresql://x")
        with patch.dict("sys.modules", {"asyncpg": None}):
            with pytest.raises(ImportError):
                await store.init_db()


# ── Signal store ────────────────────────────────────────────


class TestSignalStore:
    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing(self):
        pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value=None)
        s = PostgresSignalStore(pool=pool)
        result = await s.get(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_find_by_dedupe_none_when_no_key(self):
        pool, _ = _mock_pool()
        s = PostgresSignalStore(pool=pool)
        result = await s.find_by_dedupe(source="test", dedupe_key=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_list_empty(self):
        pool, conn = _mock_pool()
        conn.fetch = AsyncMock(return_value=[])
        s = PostgresSignalStore(pool=pool)
        result = await s.list(limit=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_update_relay_status(self):
        pool, conn = _mock_pool()
        s = PostgresSignalStore(pool=pool)
        await s.update_relay_status(uuid.uuid4(), status="published")
        conn.execute.assert_awaited()


# ── Job store ───────────────────────────────────────────────


class TestJobStore:
    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing(self):
        pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value=None)
        s = PostgresJobStore(pool=pool)
        result = await s.get(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_latest_attempt_zero_for_unknown(self):
        pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value={"n": None})
        s = PostgresJobStore(pool=pool)
        result = await s.latest_attempt(trigger_id="t", signal_id=uuid.uuid4())
        assert result == 0

    @pytest.mark.asyncio
    async def test_list_empty(self):
        pool, conn = _mock_pool()
        conn.fetch = AsyncMock(return_value=[])
        s = PostgresJobStore(pool=pool)
        result = await s.list(limit=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_with_filters_builds_clauses(self):
        pool, conn = _mock_pool()
        conn.fetch = AsyncMock(return_value=[])
        s = PostgresJobStore(pool=pool)
        await s.list(trigger_id="t1", status="pending", limit=10, chat_binding_chat_id="chat-1")
        # one fetch call with the WHERE clause
        conn.fetch.assert_awaited_once()
        sql = conn.fetch.await_args.args[0]
        assert "trigger_id" in sql
        assert "status" in sql
        assert "chat_binding" in sql


# ── Schedule store ──────────────────────────────────────────


class TestScheduleStore:
    @pytest.mark.asyncio
    async def test_upsert(self):
        pool, conn = _mock_pool()
        s = PostgresScheduleStore(pool=pool)
        record = OrchidScheduleRecord(
            schedule_id="sch-1",
            trigger_id="t1",
            cron="* * * * *",
            interval_seconds=None,
            identity_claim={"tenant_key": "t"},
            last_fire_at=None,
            next_fire_at=None,
            enabled=True,
        )
        await s.upsert(record)
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_set_enabled(self):
        pool, conn = _mock_pool()
        s = PostgresScheduleStore(pool=pool)
        await s.set_enabled("sch-1", enabled=False)
        conn.execute.assert_awaited()


# ── Trigger store ───────────────────────────────────────────


class TestTriggerStore:
    @pytest.mark.asyncio
    async def test_insert_version(self):
        pool, conn = _mock_pool()
        s = PostgresTriggerStore(pool=pool)
        record = OrchidTriggerRecord(
            trigger_id="t1",
            version=1,
            config={"id": "t1"},
            created_at=_dt.datetime.now(tz=_dt.UTC),
            deleted_at=None,
        )
        await s.insert_version(record)
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_soft_delete(self):
        pool, conn = _mock_pool()
        s = PostgresTriggerStore(pool=pool)
        await s.soft_delete("t1", deleted_at=_dt.datetime.now(tz=_dt.UTC))
        conn.execute.assert_awaited()


# ── Helpers ──────────────────────────────────────────────────


class TestMaybeLoadJsonb:
    def test_none(self):
        assert _maybe_load_jsonb(None) is None

    def test_dict_passthrough(self):
        assert _maybe_load_jsonb({"a": 1}) == {"a": 1}

    def test_string_decoded(self):
        assert _maybe_load_jsonb('{"a": 1}') == {"a": 1}


class TestRowMappers:
    def test_row_to_signal(self):
        sid = uuid.uuid4()
        now = _dt.datetime.now(tz=_dt.UTC)
        row = MagicMock()
        row.__getitem__ = lambda self, k: {
            "signal_id": sid,
            "type": "test.event",
            "source": "test",
            "payload": {"k": "v"},
            "tenant_key": "t1",
            "user_id": "u1",
            "correlation_id": None,
            "dedupe_key": None,
            "identity_claim": None,
            "chat_binding": None,
            "occurred_at": now,
            "persisted_at": now,
            "relay_status": "published",
        }[k]
        row.keys = lambda: [
            "signal_id", "type", "source", "payload", "tenant_key", "user_id",
            "correlation_id", "dedupe_key", "identity_claim", "chat_binding",
            "occurred_at", "persisted_at", "relay_status",
        ]
        signal = _row_to_signal(row)
        assert isinstance(signal, Signal)
        assert signal.signal_id == sid
        assert signal.payload == {"k": "v"}

    def test_row_to_schedule(self):
        row = {
            "schedule_id": "s1",
            "trigger_id": "t1",
            "cron": "* * * * *",
            "interval_seconds": None,
            "identity_claim": {"tenant_key": "t"},
            "last_fire_at": None,
            "next_fire_at": None,
            "enabled": True,
        }
        result = _row_to_schedule(row)
        assert result.schedule_id == "s1"
        assert result.enabled is True

    def test_row_to_trigger(self):
        now = _dt.datetime.now(tz=_dt.UTC)
        row = {
            "trigger_id": "t1",
            "version": 2,
            "config": {"id": "t1"},
            "created_at": now,
            "deleted_at": None,
        }
        result = _row_to_trigger(row)
        assert result.trigger_id == "t1"
        assert result.version == 2

    def test_row_to_run(self):
        now = _dt.datetime.now(tz=_dt.UTC)
        sid = uuid.uuid4()
        spec_dict = {
            "trigger_id": "t1",
            "signal_id": str(sid),
            "agent_name": "agent-a",
            "prompt": "hello",
            "identity_claim": {"tenant_key": "t"},
            "correlation_id": None,
            "parallelism_key": "tenant:t",
            "visibility": "tenant",
            "visibility_user_id": None,
            "chat_binding": None,
        }
        row = {
            "run_id": uuid.uuid4(),
            "spec": spec_dict,
            "attempt_number": 1,
            "status": JobStatus.PENDING.value,
            "queued_at": now,
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "next_retry_at": None,
            "metadata": {},
            "visibility": "tenant",
            "visibility_user_id": None,
        }
        run = _row_to_run(row)
        assert isinstance(run, JobRun)
        assert isinstance(run.spec, JobSpec)
        assert run.spec.signal_id == sid
        assert run.status == JobStatus.PENDING
