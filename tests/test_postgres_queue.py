"""Postgres-backed queue + event-store tests.

These tests require a live Postgres reachable at the DSN supplied via
``ORCHID_TEST_PG_DSN``.  They're skipped when the variable is unset
so CI can stay hermetic; the docker-compose Postgres is what wires
them up locally::

    export ORCHID_TEST_PG_DSN=postgresql://orchid:orchid@localhost:5432/orchid_test
    cd orchid && .venv/bin/python -m pytest tests/events/test_postgres_queue.py

The fixture isolates each test in a fresh schema and rolls back at
teardown so tests don't leak rows across runs.

.. note::

    ``PostgresEventStorage`` and ``PostgresSignalQueue`` are not yet
    available in the orchid-storage-postgres plugin.  These tests are
    skipped unconditionally until the postgres events plugin ships.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="PostgresEventStorage / PostgresSignalQueue not yet available in orchid-storage-postgres plugin")
