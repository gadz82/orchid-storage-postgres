"""
Migration v001 — PostgreSQL initial schema.

Creates every framework-owned table in a single pass.
"""

from __future__ import annotations

import logging

from orchid_ai.persistence.migrations._schema_ddl import PG_UP

logger = logging.getLogger(__name__)

VERSION = "001"
DESCRIPTION = "PostgreSQL initial schema (chat, MCP outbound, MCP inbound gateway, events)"

_PG_DOWN = [
    "DROP TABLE IF EXISTS signal_sources CASCADE",
    "DROP TABLE IF EXISTS job_runs CASCADE",
    "DROP TABLE IF EXISTS schedules CASCADE",
    "DROP TABLE IF EXISTS triggers CASCADE",
    "DROP TABLE IF EXISTS signal_queue_dead_letter CASCADE",
    "DROP TABLE IF EXISTS signal_queue CASCADE",
    "DROP TABLE IF EXISTS signals CASCADE",
    "DROP TABLE IF EXISTS mcp_gateway_tokens CASCADE",
    "DROP TABLE IF EXISTS mcp_gateway_auth_codes CASCADE",
    "DROP TABLE IF EXISTS mcp_gateway_clients CASCADE",
    "DROP TABLE IF EXISTS mcp_client_registrations CASCADE",
    "DROP TABLE IF EXISTS mcp_oauth_tokens CASCADE",
    "DROP TABLE IF EXISTS agent_configs CASCADE",
    "DROP TABLE IF EXISTS conversation_summaries CASCADE",
    "DROP TABLE IF EXISTS chat_messages CASCADE",
    "DROP TABLE IF EXISTS chat_sessions CASCADE",
]


async def up(conn, *, dialect: str = "postgres") -> None:
    """Apply the PostgreSQL initial schema."""
    for sql in PG_UP:
        await conn.execute(sql)
    logger.info("[orchid-storage-postgres] Migration v001 applied (%d statements)", len(PG_UP))


async def down(conn, *, dialect: str = "postgres") -> None:
    """Roll back the PostgreSQL initial schema."""
    for sql in _PG_DOWN:
        await conn.execute(sql)
