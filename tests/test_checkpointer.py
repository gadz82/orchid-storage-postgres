"""Tests for the PostgreSQL checkpointer (bundled in orchid-storage-postgres)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestBuildPostgresCheckpointer:
    @pytest.mark.asyncio
    async def test_factory_in_module(self):
        from orchid_storage_postgres import _build_postgres_checkpointer

        assert callable(_build_postgres_checkpointer)

    @pytest.mark.asyncio
    async def test_missing_package_raises_import_error(self):
        with patch.dict("sys.modules", {"langgraph.checkpoint.postgres": None}):
            with pytest.raises(ImportError):
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: F401


class TestRegistration:
    def test_register_adds_to_registry(self):
        from orchid_ai.checkpointing.factory import _CHECKPOINTER_REGISTRY
        from orchid_storage_postgres import _register

        _register()
        assert "postgres" in _CHECKPOINTER_REGISTRY
