"""Unit tests for the three MCP store backends."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchid_ai.core.mcp_gateway_state import (
    OrchidMCPGatewayAuthCode,
    OrchidMCPGatewayClient,
    OrchidMCPGatewayToken,
)
from orchid_ai.core.mcp_registration import OrchidMCPClientRegistration
from orchid_ai.core.mcp_tokens import OrchidMCPTokenRecord


def _mock_pool() -> tuple[MagicMock, AsyncMock]:
    pool = MagicMock()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="DELETE 0")
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


# ── Token store ──────────────────────────────────────────────


class TestMCPTokenStore:
    @pytest.mark.asyncio
    async def test_missing_asyncpg_raises_import_error(self):
        from orchid_storage_postgres.mcp_token_store import OrchidPostgresMCPTokenStore

        store = OrchidPostgresMCPTokenStore(dsn="postgresql://localhost/db")
        with patch.dict("sys.modules", {"asyncpg": None}):
            with pytest.raises(ImportError):
                await store.init_db()

    @pytest.mark.asyncio
    async def test_get_token_returns_none(self):
        from orchid_storage_postgres.mcp_token_store import OrchidPostgresMCPTokenStore

        store = OrchidPostgresMCPTokenStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        result = await store.get_token("t1", "u1", "server-a")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_token(self):
        from orchid_storage_postgres.mcp_token_store import OrchidPostgresMCPTokenStore

        store = OrchidPostgresMCPTokenStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()

        record = OrchidMCPTokenRecord(
            server_name="server-a",
            tenant_id="t1",
            user_id="u1",
            access_token="tok",
            refresh_token="ref",
            expires_at=12345.0,
            scopes=["a", "b"],
            created_at=12345.0,
            updated_at=12345.0,
        )
        await store.save_token(record)
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_token_parses_command_tag(self):
        from orchid_storage_postgres.mcp_token_store import OrchidPostgresMCPTokenStore

        store = OrchidPostgresMCPTokenStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        conn.execute = AsyncMock(return_value="DELETE 1")
        result = await store.delete_token("t1", "u1", "server-a")
        assert result is True

    @pytest.mark.asyncio
    async def test_cleanup_expired_parses_count(self):
        from orchid_storage_postgres.mcp_token_store import OrchidPostgresMCPTokenStore

        store = OrchidPostgresMCPTokenStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        conn.execute = AsyncMock(return_value="DELETE 7")
        result = await store.cleanup_expired(before=99999.0)
        assert result == 7

    @pytest.mark.asyncio
    async def test_cleanup_expired_unparseable(self):
        from orchid_storage_postgres.mcp_token_store import OrchidPostgresMCPTokenStore

        store = OrchidPostgresMCPTokenStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        conn.execute = AsyncMock(return_value="UNKNOWN")
        result = await store.cleanup_expired(before=99999.0)
        assert result == 0


# ── Client registration store ───────────────────────────────


class TestMCPClientRegistrationStore:
    @pytest.mark.asyncio
    async def test_missing_asyncpg_raises_import_error(self):
        from orchid_storage_postgres.mcp_client_registration_store import (
            OrchidPostgresMCPClientRegistrationStore,
        )

        store = OrchidPostgresMCPClientRegistrationStore(dsn="postgresql://localhost/db")
        with patch.dict("sys.modules", {"asyncpg": None}):
            with pytest.raises(ImportError):
                await store.init_db()

    @pytest.mark.asyncio
    async def test_get_returns_none(self):
        from orchid_storage_postgres.mcp_client_registration_store import (
            OrchidPostgresMCPClientRegistrationStore,
        )

        store = OrchidPostgresMCPClientRegistrationStore(dsn="postgresql://localhost/db")
        store._pool, _ = _mock_pool()
        result = await store.get("server-a")
        assert result is None

    @pytest.mark.asyncio
    async def test_save(self):
        from orchid_storage_postgres.mcp_client_registration_store import (
            OrchidPostgresMCPClientRegistrationStore,
        )

        store = OrchidPostgresMCPClientRegistrationStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        record = OrchidMCPClientRegistration(
            server_name="s",
            authorization_endpoint="https://x/auth",
            token_endpoint="https://x/token",
            registration_endpoint="https://x/reg",
            issuer="https://x",
            scopes_supported=["a"],
            token_endpoint_auth_methods_supported=["client_secret_basic"],
            client_id="cid",
            client_secret="cs",
            client_id_issued_at=12345.0,
            client_secret_expires_at=99999.0,
            created_at=12345.0,
            updated_at=12345.0,
        )
        await store.save(record)
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_parses_command_tag(self):
        from orchid_storage_postgres.mcp_client_registration_store import (
            OrchidPostgresMCPClientRegistrationStore,
        )

        store = OrchidPostgresMCPClientRegistrationStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        conn.execute = AsyncMock(return_value="DELETE 1")
        result = await store.delete("s")
        assert result is True


# ── Gateway state store ─────────────────────────────────────


class TestMCPGatewayStateStore:
    @pytest.mark.asyncio
    async def test_missing_asyncpg_raises_import_error(self):
        from orchid_storage_postgres.mcp_gateway_state_store import (
            OrchidPostgresMCPGatewayStateStore,
        )

        store = OrchidPostgresMCPGatewayStateStore(dsn="postgresql://localhost/db")
        with patch.dict("sys.modules", {"asyncpg": None}):
            with pytest.raises(ImportError):
                await store.init_db()

    @pytest.mark.asyncio
    async def test_register_client(self):
        from orchid_storage_postgres.mcp_gateway_state_store import (
            OrchidPostgresMCPGatewayStateStore,
        )

        store = OrchidPostgresMCPGatewayStateStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        record = OrchidMCPGatewayClient(
            client_id="cid",
            client_name="My App",
            redirect_uris=["https://x/cb"],
            grant_types=["authorization_code"],
            response_types=["code"],
            token_endpoint_auth_method="client_secret_basic",
            created_at=12345.0,
        )
        await store.register(record)
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_client_none(self):
        from orchid_storage_postgres.mcp_gateway_state_store import (
            OrchidPostgresMCPGatewayStateStore,
        )

        store = OrchidPostgresMCPGatewayStateStore(dsn="postgresql://localhost/db")
        store._pool, _ = _mock_pool()
        result = await store.get("cid")
        assert result is None

    @pytest.mark.asyncio
    async def test_consume_returns_none_for_unknown_code(self):
        from orchid_storage_postgres.mcp_gateway_state_store import (
            OrchidPostgresMCPGatewayStateStore,
        )

        store = OrchidPostgresMCPGatewayStateStore(dsn="postgresql://localhost/db")
        store._pool, _ = _mock_pool()
        result = await store.consume("missing-code")
        assert result is None

    @pytest.mark.asyncio
    async def test_put_auth_code(self):
        from orchid_storage_postgres.mcp_gateway_state_store import (
            OrchidPostgresMCPGatewayStateStore,
        )

        store = OrchidPostgresMCPGatewayStateStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        record = OrchidMCPGatewayAuthCode(
            code="code-1",
            client_id="cid",
            redirect_uri="https://x/cb",
            code_challenge="cc",
            code_challenge_method="S256",
            upstream_state="state-x",
            upstream_code_verifier="verifier-x",
            scopes=["a"],
            client_state="cs",
            identity=None,
            idp_access_token="",
            idp_refresh_token="",
            idp_expires_at=0.0,
            created_at=12345.0,
        )
        await store.put(record)
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_auth_code_no_op_when_no_fields(self):
        from orchid_storage_postgres.mcp_gateway_state_store import (
            OrchidPostgresMCPGatewayStateStore,
        )

        store = OrchidPostgresMCPGatewayStateStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        await store.update("code-1")  # no fields → returns without executing
        conn.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_auth_code_with_fields(self):
        from orchid_storage_postgres.mcp_gateway_state_store import (
            OrchidPostgresMCPGatewayStateStore,
        )

        store = OrchidPostgresMCPGatewayStateStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        await store.update("code-1", idp_access_token="newtok", idp_expires_at=99999.0)
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_issue_token(self):
        from orchid_storage_postgres.mcp_gateway_state_store import (
            OrchidPostgresMCPGatewayStateStore,
        )

        store = OrchidPostgresMCPGatewayStateStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        record = OrchidMCPGatewayToken(
            access_token="atok",
            refresh_token="rtok",
            client_id="cid",
            subject="user-1",
            identity={"tenant_key": "t"},
            scopes=["a"],
            expires_at=99999.0,
            idp_access_token="iatok",
            idp_refresh_token="irtok",
            idp_expires_at=99999.0,
        )
        await store.issue(record)
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_revoke_token_parses_tag(self):
        from orchid_storage_postgres.mcp_gateway_state_store import (
            OrchidPostgresMCPGatewayStateStore,
        )

        store = OrchidPostgresMCPGatewayStateStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        conn.execute = AsyncMock(return_value="DELETE 1")
        result = await store.revoke("atok")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_by_access_token_filters_expired(self):
        """An expired token must surface as ``None`` (the runtime check
        runs in :func:`_not_expired_token`)."""
        from orchid_storage_postgres.mcp_gateway_state_store import (
            OrchidPostgresMCPGatewayStateStore,
        )

        store = OrchidPostgresMCPGatewayStateStore(dsn="postgresql://localhost/db")
        store._pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(
            return_value={
                "access_token": "atok",
                "refresh_token": "rtok",
                "client_id": "cid",
                "subject": "u",
                "identity": {"tenant_key": "t"},
                "scopes": ["a"],
                "expires_at": 1.0,  # ancient → expired
                "idp_access_token": "",
                "idp_refresh_token": "",
                "idp_expires_at": 0.0,
            }
        )
        result = await store.get_by_access_token("atok")
        assert result is None
