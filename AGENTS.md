# orchid-storage-postgres — AI Context

## What This Package Is

`orchid-storage-postgres` is the PostgreSQL storage plugin for the Orchid AI
framework. It provides:

- `OrchidPostgresChatStorage` — implements `OrchidChatStorage` backed by asyncpg
- PostgreSQL schema migration (v001) with all framework-owned tables
- PostgreSQL visibility fragment for `build_run_filter_clause` ($1..$N params)

## Auto-Registration

The package registers itself via Python `importlib.metadata` entry points:

```toml
[project.entry-points."orchid.visibility_fragments"]
postgres = "orchid_storage_postgres:_register"
```

No manual `register_visibility_fragment()` calls are needed by integrators.

The chat storage is NOT auto-registered — consumers reference it via
dotted class path in their YAML config:

```yaml
storage:
  class: orchid_storage_postgres.chat_storage.OrchidPostgresChatStorage
  dsn: postgresql://...
```

## Key Files

| File | Purpose |
|------|---------|
| `chat_storage.py` | `OrchidPostgresChatStorage` + row mappers |
| `migrations.py` | `PostgresMigrationRunner` + v001 DDL |
| `visibility.py` | `_build_postgres_filter` (asyncpg $1..$N params) |
| `__init__.py` | Entry-point `_register()` callable |

## Testing

Tests require `asyncpg` but do **not** require a live PostgreSQL server —
all unit tests mock `asyncpg.create_pool`.

```bash
cd orchid-storage-postgres
pip install -e ".[dev]"
pytest tests/ -x
```

## Common Pitfalls

- `asyncpg` uses `$1..$N` positional parameters, NOT `%s` or `:name` style.
- `agents_used` and `metadata` columns in `chat_messages` are stored as
  `JSONB` objects in PostgreSQL.  The row mapper handles both string and
  already-parsed representations.
- The plugin schema migration creates ALL framework-owned tables
  (chat, MCP, events), not just chat tables.
