"""
PostgreSQL chat storage — production-grade :class:`OrchidChatStorage` backend.

Backed by ``asyncpg`` with connection pooling.  Implements every
:class:`OrchidChatStorage` method using ``$1..$N`` placeholders.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from orchid_ai.persistence.base import OrchidChatStorage
from orchid_ai.persistence.models import OrchidChatMessage, OrchidChatSession, utcnow

from .migrations import MIGRATIONS_PACKAGE, PostgresMigrationRunner

logger = logging.getLogger(__name__)


class OrchidPostgresChatStorage(OrchidChatStorage):
    """Async PostgreSQL storage for chat sessions and messages.

    Constructor accepts the DSN via ``dsn`` and an optional
    ``extra_migrations_package`` (dotted import path) so integrators
    can append their own migrations after the framework's.
    """

    def __init__(self, *, dsn: str, extra_migrations_package: str | None = None):
        self._dsn = dsn
        self._pool: Any = None
        self._migrator = PostgresMigrationRunner(
            extra_migrations_package=extra_migrations_package,
        )

    # ── Lifecycle ────────────────────────────────────────────

    async def init_db(self) -> None:
        import asyncpg

        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=10)
        async with self._pool.acquire() as conn:
            await self._migrator.run_up(conn)
        logger.info("[OrchidChatStorage:postgres] Initialised")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _conn(self):
        if self._pool is None:
            raise RuntimeError("OrchidPostgresChatStorage: init_db() not called")
        return await self._pool.acquire()

    # ── Sessions ─────────────────────────────────────────────

    async def create_chat(
        self,
        tenant_id: str,
        user_id: str,
        title: str = "",
    ) -> OrchidChatSession:
        now = utcnow()
        chat = OrchidChatSession(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            title=title or "New chat",
            created_at=now,
            updated_at=now,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO chat_sessions (id, tenant_id, user_id, title, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                chat.id, chat.tenant_id, chat.user_id, chat.title, now, now,
            )
        return chat

    async def list_chats(
        self,
        tenant_id: str,
        user_id: str,
    ) -> list[OrchidChatSession]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM chat_sessions WHERE tenant_id = $1 AND user_id = $2 "
                "ORDER BY updated_at DESC",
                tenant_id, user_id,
            )
        return [_row_to_session(r) for r in rows]

    async def get_chat(self, chat_id: str) -> OrchidChatSession | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM chat_sessions WHERE id = $1", chat_id,
            )
        return _row_to_session(row) if row else None

    async def delete_chat(self, chat_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM chat_sessions WHERE id = $1", chat_id)

    async def update_title(self, chat_id: str, title: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE chat_sessions SET title = $1, updated_at = $2 WHERE id = $3",
                title, utcnow(), chat_id,
            )

    async def mark_shared(self, chat_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE chat_sessions SET is_shared = TRUE, updated_at = $1 WHERE id = $2",
                utcnow(), chat_id,
            )

    # ── Messages ─────────────────────────────────────────────

    async def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        agents_used: list[str] | None = None,
        metadata: dict | None = None,
    ) -> OrchidChatMessage:
        now = utcnow()
        msg = OrchidChatMessage(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role=role,
            content=content,
            agents_used=agents_used or [],
            created_at=now,
            metadata=metadata or {},
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO chat_messages (id, chat_id, role, content, agents_used, created_at, metadata) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                msg.id, msg.chat_id, msg.role, msg.content,
                json.dumps(msg.agents_used), now, json.dumps(msg.metadata),
            )
            await conn.execute(
                "UPDATE chat_sessions SET updated_at = $1 WHERE id = $2",
                now, chat_id,
            )
        return msg

    async def get_messages(
        self,
        chat_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OrchidChatMessage]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM chat_messages WHERE chat_id = $1 ORDER BY created_at ASC "
                "LIMIT $2 OFFSET $3",
                chat_id, limit, offset,
            )
        return [_row_to_message(r) for r in rows]

    # ── Conversation summaries ───────────────────────────────

    async def get_conversation_summary(self, chat_id: str) -> str | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT summary_text FROM conversation_summaries WHERE chat_id = $1",
                chat_id,
            )
        return row["summary_text"] if row else None

    async def save_conversation_summary(self, chat_id: str, summary: str, turn_number: int) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO conversation_summaries (chat_id, summary_text, turn_number, updated_at) "
                "VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (chat_id) DO UPDATE SET summary_text = $2, turn_number = $3, updated_at = $4",
                chat_id, summary, turn_number, utcnow(),
            )


# ── Row mappers ──────────────────────────────────────────────


def _parse_dt(val: Any) -> datetime:
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except (ValueError, TypeError):
            return utcnow()
    return utcnow()


def _row_to_session(row: Any) -> OrchidChatSession:
    return OrchidChatSession(
        id=row["id"],
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        title=row["title"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        is_shared=bool(row["is_shared"]),
    )


def _row_to_message(row: Any) -> OrchidChatMessage:
    agents_used = row["agents_used"]
    if isinstance(agents_used, str):
        agents_used = json.loads(agents_used)
    meta = row["metadata"]
    if isinstance(meta, str):
        meta = json.loads(meta)
    return OrchidChatMessage(
        id=row["id"],
        chat_id=row["chat_id"],
        role=row["role"],
        content=row["content"],
        agents_used=agents_used or [],
        created_at=_parse_dt(row["created_at"]),
        metadata=meta or {},
    )
