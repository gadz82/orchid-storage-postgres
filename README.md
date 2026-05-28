# orchid-storage-postgres

PostgreSQL storage backend plugin for the [Orchid AI](https://github.com/gadz82/orchid) framework.

## What it provides

PostgreSQL implementations of every framework persistence ABC:

- `OrchidPostgresChatStorage` — chat sessions + messages + conversation summaries
- `OrchidPostgresConfigStorage` — agent configuration CRUD
- `OrchidPostgresMCPTokenStore` — per-server OAuth tokens
- `OrchidPostgresMCPClientRegistrationStore` — RFC 7591 dynamic-client registrations
- `OrchidPostgresMCPGatewayStateStore` — gateway clients / auth codes / tokens
- `PostgresEventStorage` — signal / job / schedule / trigger persistence (events block)
- `PostgresSignalQueue` — durable lease-based queue with `FOR UPDATE SKIP LOCKED` + `pg_notify`
- PostgreSQL visibility fragment for `build_run_filter_clause`
- Async PostgreSQL LangGraph checkpointer (registered as `postgres` type)
- A unified v001 migration that provisions every framework-owned table in one pass

## Installation

```bash
pip install orchid-storage-postgres
```

## Usage

Reference the classes you need in your `orchid.yml`:

```yaml
storage:
  class: orchid_storage_postgres.chat_storage.OrchidPostgresChatStorage
  dsn: postgresql://user:pass@localhost:5432/orchid

config_storage:
  enabled: true
  class: orchid_storage_postgres.config_storage.OrchidPostgresConfigStorage
  dsn: postgresql://user:pass@localhost:5432/orchid

checkpointer:
  type: postgres
  dsn: postgresql://user:pass@localhost:5432/orchid

events:
  enabled: true
  store:
    class_path: orchid_storage_postgres.event_storage.PostgresEventStorage
    extra_args:
      dsn: postgresql://user:pass@localhost:5432/orchid
  queue:
    class_path: orchid_storage_postgres.event_queue.PostgresSignalQueue
```

For MCP gateway / OAuth deployments, add:

```yaml
mcp_token_store:
  class: orchid_storage_postgres.mcp_token_store.OrchidPostgresMCPTokenStore
  dsn: postgresql://user:pass@localhost:5432/orchid

mcp_client_registration_store:
  class: orchid_storage_postgres.mcp_client_registration_store.OrchidPostgresMCPClientRegistrationStore
  dsn: postgresql://user:pass@localhost:5432/orchid

mcp_gateway_state_store:
  class: orchid_storage_postgres.mcp_gateway_state_store.OrchidPostgresMCPGatewayStateStore
  dsn: postgresql://user:pass@localhost:5432/orchid
```

Or build any of them programmatically:

```python
from orchid_storage_postgres import OrchidPostgresChatStorage

storage = OrchidPostgresChatStorage(dsn="postgresql://user:pass@localhost:5432/orchid")
await storage.init_db()
```

## Schema ownership

The single `v001_initial_schema` migration creates **all** framework
tables (chat, MCP, events, agent_configs, conversation_summaries) in one
pass.  All store classes share the same migration runner, so it does
not matter which class triggers `init_db()` first; subsequent calls
become no-ops thanks to `CREATE TABLE IF NOT EXISTS`.

## Development

```bash
cd orchid-storage-postgres
pip install -e ".[dev]"
pytest tests/ -x
ruff check orchid_storage_postgres/
```

Tests are hermetic — they mock `asyncpg.create_pool` and the pool's
async context manager, so no live PostgreSQL is required.

## License

MIT
