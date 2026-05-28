# Database migrations (Pony ORM)

Schema changes use timestamped Python modules (SolarisServer-style).

## Create a migration

```bash
make create_migration name=add_users
```

Creates `app/migrations/versions/<timestamp>_add_users.py` with empty `up(db)` / `down(db)` — edit manually, then apply.

Helpers in `app/migrations/migration_helper.py`:

- `create_table`, `add_column`, `drop_column`
- `create_table_from_model(Model)` — generate DDL from a Pony entity
- `add_missing_columns_from_model(Model)` — add only missing columns

Example `up(db)` for a **new** table (users, businesses, etc.):

```python
from pony.orm import db_session
from app.migrations.migration_helper import create_table_from_model, drop_table
from app.users.models import User

@db_session
def up(db):
    create_table_from_model(User)

@db_session
def down(db):
    drop_table(db, User._table_)
```

Use `add_column_from_model_property` only when the table **already exists** and you are adding a column.

## Startup (Solaris-style)

On `make run`, `make up-api`, or Docker entrypoint:

1. **Create the Postgres database** if it does not exist (`create_db.py`)
2. **Apply pending migrations** (`migrate.up`)

Docker entrypoint always runs both before Gunicorn. `SKIP_MIGRATIONS=1` is set on workers so migrations are not repeated.

`make up` also runs `ensure-db` for local Postgres before you start the API.

Apply manually without starting the server:

```bash
make migrate
```

## Fresh database

```bash
make setup
```

`INSTALL_MODE=1` (via app startup) creates tables from Pony entities on a blank database.
