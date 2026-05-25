"""Tests for the PostgreSQL visibility fragment."""

from __future__ import annotations

from types import SimpleNamespace

from orchid_storage_postgres.visibility import _build_postgres_filter


class TestPostgresVisibilityFilter:
    def test_admin_short_circuits_to_tenant_only(self):
        auth = SimpleNamespace(tenant_key="t1", user_id="u1", roles=frozenset(["admin"]))
        f = _build_postgres_filter(auth)
        assert "tenant_key = $1" in f.where
        assert f.params["tenant_key"] == "t1"

    def test_non_admin_gets_visibility_clauses(self):
        auth = SimpleNamespace(tenant_key="t1", user_id="u1", roles=frozenset())
        f = _build_postgres_filter(auth)
        assert "tenant_key = $1" in f.where
        assert "visibility = 'tenant'" in f.where
        assert "visibility_user_id = $2" in f.where
        assert f.params["tenant_key"] == "t1"
        assert f.params["user_id"] == "u1"

    def test_uses_positional_params(self):
        auth = SimpleNamespace(tenant_key="t1", user_id="u1", roles=frozenset())
        f = _build_postgres_filter(auth)
        assert "$1" in f.where
        assert "$2" in f.where
