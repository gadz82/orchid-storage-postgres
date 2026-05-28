"""PostgreSQL storage plugin for the Orchid AI framework.

Provides PostgreSQL-backed implementations of every framework
storage / persistence ABC:

- :class:`OrchidPostgresChatStorage` — chat sessions + messages
  (:class:`orchid_ai.persistence.base.OrchidChatStorage`).
- :class:`OrchidPostgresConfigStorage` — agent configuration CRUD
  (:class:`orchid_ai.config.storage.OrchidConfigStorage`).
- :class:`OrchidPostgresMCPTokenStore` — per-server OAuth tokens
  (:class:`orchid_ai.core.mcp.OrchidMCPTokenStore`).
- :class:`OrchidPostgresMCPClientRegistrationStore` — RFC 7591 DCR
  (:class:`orchid_ai.core.mcp.OrchidMCPClientRegistrationStore`).
- :class:`OrchidPostgresMCPGatewayStateStore` — gateway clients,
  auth codes and tokens (all three
  :mod:`orchid_ai.core.mcp_gateway_state` ABCs).
- :class:`PostgresEventStorage` (+ four narrow stores) — events
  signal/job/schedule/trigger persistence.
- :class:`PostgresSignalQueue` — durable lease-based signal queue.
- An async PostgreSQL checkpointer factory wired into
  :func:`orchid_ai.checkpointing.factory.build_checkpointer` via the
  ``postgres`` type string.
- A PostgreSQL visibility fragment for
  :func:`orchid_ai.events.visibility.build_run_filter_clause`.

Auto-registers the visibility fragment + checkpointer via
``importlib.metadata`` entry points; storage classes are referenced
by dotted import path in the consumer's YAML.
"""

from __future__ import annotations

import logging

__version__ = "1.0.1"

from .chat_storage import OrchidPostgresChatStorage
from .config_storage import OrchidPostgresConfigStorage
from .event_queue import PostgresSignalQueue
from .event_storage import (
    PostgresEventStorage,
    PostgresJobStore,
    PostgresScheduleStore,
    PostgresSignalStore,
    PostgresTriggerStore,
)
from .mcp_client_registration_store import OrchidPostgresMCPClientRegistrationStore
from .mcp_gateway_state_store import OrchidPostgresMCPGatewayStateStore
from .mcp_token_store import OrchidPostgresMCPTokenStore
from .visibility import _build_postgres_filter

__all__ = [
    "OrchidPostgresChatStorage",
    "OrchidPostgresConfigStorage",
    "OrchidPostgresMCPClientRegistrationStore",
    "OrchidPostgresMCPGatewayStateStore",
    "OrchidPostgresMCPTokenStore",
    "PostgresEventStorage",
    "PostgresJobStore",
    "PostgresScheduleStore",
    "PostgresSignalQueue",
    "PostgresSignalStore",
    "PostgresTriggerStore",
]

logger = logging.getLogger(__name__)


async def _build_postgres_checkpointer(dsn: str):
    """Build an async PostgreSQL checkpointer from a DSN."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    checkpointer = AsyncPostgresSaver.from_conn_string(dsn)
    await checkpointer.setup()
    logger.info("[orchid-storage-postgres] Checkpointer ready")
    return checkpointer


def _register() -> None:
    """Entry-point callable — registers the postgres visibility fragment and checkpointer."""
    try:
        from orchid_ai.events.visibility import register_visibility_fragment

        register_visibility_fragment("postgres", _build_postgres_filter)
        logger.debug("[orchid-storage-postgres] Registered visibility fragment")
    except ImportError:
        logger.debug("[orchid-storage-postgres] Skipping visibility fragment (not in this orchid-ai version)")

    try:
        from orchid_ai.checkpointing.factory import register_checkpointer

        register_checkpointer("postgres", _build_postgres_checkpointer)
        logger.debug("[orchid-storage-postgres] Registered checkpointer")
    except ImportError:
        logger.debug("[orchid-storage-postgres] Skipping checkpointer (not in this orchid-ai version)")
