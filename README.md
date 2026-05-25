# orchid-storage-postgres

PostgreSQL storage backend plugin for the [Orchid AI](https://github.com/gadz82/orchid) framework.

## What it provides

- `OrchidPostgresChatStorage` — implements `OrchidChatStorage` backed by PostgreSQL (asyncpg)
- PostgreSQL visibility fragment for `build_run_filter_clause`
- PostgreSQL schema migration (v001)

## Installation

```bash
pip install orchid-storage-postgres
```

## Usage

Reference in your `orchid.yml`:

```yaml
storage:
  class: orchid_storage_postgres.chat_storage.OrchidPostgresChatStorage
  dsn: postgresql://user:pass@localhost:5432/orchid
```

Or build it programmatically:

```python
from orchid_storage_postgres import OrchidPostgresChatStorage

storage = OrchidPostgresChatStorage(dsn="postgresql://user:pass@localhost:5432/orchid")
await storage.init_db()
```

## Development

```bash
cd orchid-storage-postgres
pip install -e ".[dev]"
pytest tests/ -x
ruff check orchid_storage_postgres/
```

## License

MIT
