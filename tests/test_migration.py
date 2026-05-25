"""Tests for the PostgreSQL migration runner and v001 migration."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from orchid_storage_postgres.migrations import PostgresMigrationRunner
from orchid_storage_postgres.migrations.v001_initial_schema import VERSION, up


class TestPostgresMigrationRunner:
    @pytest.mark.asyncio
    async def test_ensure_migrations_table(self):
        runner = PostgresMigrationRunner()
        conn = AsyncMock()
        await runner.ensure_migrations_table(conn)
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_applied_versions(self):
        runner = PostgresMigrationRunner()
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        versions = await runner.get_applied_versions(conn)
        assert versions == set()

    @pytest.mark.asyncio
    async def test_record_version(self):
        runner = PostgresMigrationRunner()
        conn = AsyncMock()
        await runner.record_version(conn, "001", "test")
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remove_version(self):
        runner = PostgresMigrationRunner()
        conn = AsyncMock()
        await runner.remove_version(conn, "001")
        conn.execute.assert_awaited_once()


class TestV001Migration:
    @pytest.mark.asyncio
    async def test_up_executes_statements(self):
        conn = AsyncMock()
        await up(conn)
        # PG_UP has many statements — verify at least some executed
        assert conn.execute.await_count > 0

    @pytest.mark.asyncio
    async def test_has_version(self):
        assert VERSION == "001"
