"""PostgreSQL storage plugin for the Orchid AI framework.

Provides ``OrchidPostgresChatStorage``, a PostgreSQL visibility
fragment, and a PostgreSQL checkpointer.  Auto-registers via
``importlib.metadata`` entry points.
"""

from __future__ import annotations

import logging

__version__ = "0.0.0"

from .chat_storage import OrchidPostgresChatStorage
from .visibility import _build_postgres_filter

__all__ = ["OrchidPostgresChatStorage"]

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
