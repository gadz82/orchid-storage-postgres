# orchid-storage-postgres — AI Context

## What This Package Is

`orchid-storage-postgres` is the PostgreSQL storage plugin for the
Orchid AI framework. It provides PostgreSQL-backed implementations of
**every** framework persistence ABC:

| Class | Implements | Module |
|-------|-----------|--------|
| `OrchidPostgresChatStorage` | `OrchidChatStorage` | `chat_storage.py` |
| `OrchidPostgresConfigStorage` | `OrchidConfigStorage` | `config_storage.py` |
| `OrchidPostgresMCPTokenStore` | `OrchidMCPTokenStore` | `mcp_token_store.py` |
| `OrchidPostgresMCPClientRegistrationStore` | `OrchidMCPClientRegistrationStore` | `mcp_client_registration_store.py` |
| `OrchidPostgresMCPGatewayStateStore` | `OrchidMCPGatewayClientStore` + `OrchidMCPGatewayAuthCodeStore` + `OrchidMCPGatewayTokenStore` | `mcp_gateway_state_store.py` |
| `PostgresEventStorage` (+ 4 narrow stores) | `OrchidSignalStore` / `OrchidJobStore` / `OrchidScheduleStore` / `OrchidTriggerStore` | `event_storage.py` |
| `PostgresSignalQueue` | `OrchidSignalQueue` | `event_queue.py` |
| `_build_postgres_checkpointer` | LangGraph `BaseCheckpointSaver` | `__init__.py` |
| `_build_postgres_filter` | `_Filter` (visibility fragment) | `visibility.py` |

Plus the unified migration runner (`PostgresMigrationRunner`,
`migrations/v001_initial_schema.py`) which provisions every
framework-owned table in a single pass via the shared
`orchid_ai.persistence.migrations._schema_ddl.PG_UP` block.

## Auto-Registration

The package registers two extension points via Python
`importlib.metadata` entry points:

```toml
[project.entry-points."orchid.visibility_fragments"]
postgres = "orchid_storage_postgres:_register"

[project.entry-points."orchid.checkpointers"]
postgres = "orchid_storage_postgres:_register"
```

No manual `register_visibility_fragment()` /
`register_checkpointer()` calls are needed by integrators.

The storage classes themselves are NOT auto-registered — consumers
reference them via dotted class path in their YAML config:

```yaml
storage:
  class: orchid_storage_postgres.chat_storage.OrchidPostgresChatStorage
  dsn: postgresql://...

config_storage:
  class: orchid_storage_postgres.config_storage.OrchidPostgresConfigStorage
  dsn: postgresql://...

events:
  enabled: true
  store:
    class_path: orchid_storage_postgres.event_storage.PostgresEventStorage
    extra_args:
      dsn: postgresql://...
  queue:
    class_path: orchid_storage_postgres.event_queue.PostgresSignalQueue
```

## Key Files

| File | Purpose |
|------|---------|
| `chat_storage.py` | `OrchidPostgresChatStorage` + row mappers |
| `config_storage.py` | `OrchidPostgresConfigStorage` |
| `event_queue.py` | `PostgresSignalQueue` + `_PostgresDBTransaction` |
| `event_storage.py` | `PostgresEventStorage` facade + 4 narrow stores |
| `mcp_token_store.py` | `OrchidPostgresMCPTokenStore` |
| `mcp_client_registration_store.py` | `OrchidPostgresMCPClientRegistrationStore` |
| `mcp_gateway_state_store.py` | `OrchidPostgresMCPGatewayStateStore` |
| `migrations/__init__.py` | `PostgresMigrationRunner` |
| `migrations/v001_initial_schema.py` | Initial schema migration (all framework tables) |
| `visibility.py` | `_build_postgres_filter` (asyncpg `$1..$N` params) |
| `__init__.py` | Entry-point `_register()` callable + checkpointer factory |

## Schema Ownership

Migration `v001` creates **every framework-owned table in a single
pass**, so a single DSN can back chat + config + MCP + events.  The
DDL is sourced from
`orchid_ai.persistence.migrations._schema_ddl.PG_UP` — the same block
the SQLite migration uses (in its `SQLITE_UP` sibling).

Tables created:

- `chat_sessions`, `chat_messages`, `conversation_summaries`
- `agent_configs`
- `mcp_oauth_tokens`, `mcp_client_registrations`
- `mcp_gateway_clients`, `mcp_gateway_auth_codes`, `mcp_gateway_tokens`
- `signals`, `signal_queue`, `signal_queue_dead_letter`,
  `triggers`, `schedules`, `job_runs`, `signal_sources`

`CREATE TABLE IF NOT EXISTS` makes init_db() safe to call multiple
times across the various store classes.

## Testing

Tests do **not** require a live PostgreSQL server — every async pool
call is mocked.  The `_mock_pool()` helper in each test file builds an
`AsyncMock` `Pool` whose `acquire()` context manager yields an
`AsyncMock` `Connection`.

```bash
cd orchid-storage-postgres
pip install -e ".[dev]"
pytest tests/ -x
```

## Common Pitfalls

- `asyncpg` uses `$1..$N` positional parameters, NOT `%s` or `:name` style.
- JSON columns travel as serialised strings — asyncpg's default codec
  implicitly casts `text → jsonb` on the Postgres side.
- `_PostgresDBTransaction` is private (underscore prefix) but shared
  between `event_queue.py` and `event_storage.py` so the dispatcher's
  outbox commits both signal + queue rows atomically. Do not import it
  from outside this package.
- Pool sizing: chat / config / MCP stores use `min=2, max=10`; the
  signal queue uses `min=1, max=5` because the long-lived
  `LISTEN`/`NOTIFY` listener already pins one connection.
- The `events.queue` block accepts either `pool=` (shared with the
  storage) or `dsn=` (private pool).  In production wiring use
  `pool=` so the dispatcher's outbox commits queue rows in the same
  transaction as the signal row.
