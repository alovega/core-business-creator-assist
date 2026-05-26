"""Raw SQL and model-driven schema helpers (SolarisServer-style)."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from time import time

from pony.orm import Json

SQL_TYPES = {
    "int": "INTEGER",
    "datetime": "TIMESTAMP without time zone",
    "text": "TEXT",
    "boolean": "boolean",
    "json": "JSONB",
    "decimal": "DECIMAL",
    "float": "REAL",
}

PY_TYPES_TO_SQL = {
    str: "text",
    int: "int",
    datetime: "datetime",
    float: "float",
    bool: "boolean",
    Json: "json",
    Decimal: "decimal",
}

KNOWN_DEFAULTS = {
    datetime.utcnow: "CURRENT_TIMESTAMP",
}


def get_default_from_property(default):
    if default is None:
        return None
    if type(default) in (int, float, bool, str):
        return default
    if isinstance(default, dict):
        return json.dumps(default)
    if default in KNOWN_DEFAULTS:
        return KNOWN_DEFAULTS[default]
    return None


def add_column(
    db,
    table_name: str,
    column_name: str,
    column_type: str,
    *,
    required: bool = False,
    default=None,
    unique: bool = False,
    if_not_exists: bool = True,
) -> None:
    extra = "IF NOT EXISTS " if if_not_exists else ""
    sql_type = SQL_TYPES[column_type]
    query = (
        f'ALTER TABLE "{table_name}" ADD COLUMN {extra}"{column_name}" {sql_type}'
    )
    if required:
        query += " NOT NULL"
    if default is not None:
        if column_type == "boolean":
            query += f" DEFAULT {default}"
        elif column_type in ("int", "datetime"):
            query += f" DEFAULT {default}"
        else:
            query += f" DEFAULT '{default}'"
    print(query)
    db.execute(query)
    if unique:
        index_name = f"ix_{table_name}_{column_name}"
        db.execute(
            f'CREATE UNIQUE INDEX IF NOT EXISTS "{index_name}" '
            f'ON "{table_name}" ("{column_name}")'
        )


def create_table(db, table_name: str, *, with_id: bool = True) -> None:
    params = "(id serial NOT NULL PRIMARY KEY)" if with_id else ""
    query = f"CREATE TABLE IF NOT EXISTS {table_name} {params}"
    print(query)
    db.execute(query)


def drop_table(db, table_name: str) -> None:
    query = f'DROP TABLE IF EXISTS "{table_name}" CASCADE'
    print(query)
    db.execute(query)


def drop_column(db, table_name: str, column_name: str) -> None:
    query = f'ALTER TABLE "{table_name}" DROP COLUMN IF EXISTS "{column_name}"'
    print(query)
    db.execute(query)


def add_foreign_key_constraint(
    db,
    table_name: str,
    column_name: str,
    reference_table: str,
    *,
    on_delete: str = "null",
    foreign_column: str = "id",
) -> None:
    db.execute(
        f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS '
        f'"fk_{table_name}__{column_name}"'
    )
    query = (
        f'ALTER TABLE "{table_name}" ADD CONSTRAINT "fk_{table_name}__{column_name}" '
        f'FOREIGN KEY ("{column_name}") REFERENCES "{reference_table}" '
        f'("{foreign_column}")'
    )
    if on_delete == "cascade":
        query += " ON DELETE CASCADE"
    elif on_delete == "null":
        query += " ON DELETE SET NULL"
    else:
        query += " ON DELETE RESTRICT"
    print(query)
    db.execute(query)


def add_fk_column(
    db,
    table_name: str,
    column_name: str,
    reference_table: str,
    *,
    on_delete: str = "null",
    required: bool = False,
) -> None:
    add_column(db, table_name, column_name, "int", required=required)
    add_foreign_key_constraint(
        db, table_name, column_name, reference_table, on_delete=on_delete
    )


def add_index(db, table_name: str, column_name: str) -> None:
    index_name = f"idx_{table_name}__{column_name}"
    query = (
        f'CREATE INDEX IF NOT EXISTS "{index_name}" '
        f'ON "{table_name}" ("{column_name}")'
    )
    print(query)
    db.execute(query)


def add_composite_index(db, table_name: str, *columns: str) -> None:
    cols = '", "'.join(columns)
    suffix = "_".join(columns)
    index_name = f"idx_{table_name}__{suffix}"
    query = (
        f'CREATE INDEX IF NOT EXISTS "{index_name}" '
        f'ON "{table_name}" ("{cols}")'
    )
    print(query)
    db.execute(query)


def constraint_exists(db, table_name: str, constraint_name: str) -> bool:
    rows = list(
        db.select(
            "SELECT 1 FROM information_schema.table_constraints "
            f"WHERE table_name = '{table_name}' "
            f"AND constraint_name = '{constraint_name}' "
            "LIMIT 1"
        )
    )
    return bool(rows)


def add_composite_unique_constraint(
    db,
    table_name: str,
    *columns: str,
    if_not_exists: bool = True,
) -> None:
    """Solaris-style UNIQUE (col1, col2, ...) — keeps serial id as PK."""
    suffix = "_".join(columns)
    constraint_name = f"unq_{table_name}__{suffix}"
    if if_not_exists and constraint_exists(db, table_name, constraint_name):
        return
    quoted = '", "'.join(columns)
    query = (
        f'ALTER TABLE "{table_name}" '
        f'ADD CONSTRAINT "{constraint_name}" UNIQUE ("{quoted}")'
    )
    print(query)
    db.execute(query)


def remove_composite_unique_constraint(db, table_name: str, *columns: str) -> None:
    suffix = "_".join(columns)
    constraint_name = f"unq_{table_name}__{suffix}"
    query = (
        f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'
    )
    print(query)
    db.execute(query)
    index_name = f"unq_{table_name}__{suffix}"
    db.execute(f'DROP INDEX IF EXISTS "{index_name}"')


def set_primary_key(db, table_name: str, *columns: str) -> None:
    cols = ", ".join(f'"{col}"' for col in columns)
    query = f'ALTER TABLE "{table_name}" ADD PRIMARY KEY ({cols})'
    print(query)
    db.execute(query)


def remove_primary_key(db, table_name: str) -> None:
    query = (
        f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{table_name}_pkey" CASCADE'
    )
    print(query)
    db.execute(query)


def rename_table(db, table_name: str, new_table_name: str) -> None:
    query = f'ALTER TABLE "{table_name}" RENAME TO "{new_table_name}"'
    print(query)
    db.execute(query)


def sync_id_sequence(db, table_name: str) -> None:
    query = (
        f"SELECT setval(pg_get_serial_sequence('\"{table_name}\"', 'id'), "
        f'COALESCE((SELECT MAX(id)+1 FROM "{table_name}"), 1), false)'
    )
    print(query)
    db.execute(query)


def column_data_type(db, table_name: str, column_name: str) -> str | None:
    """Return the PostgreSQL data_type for a column, or None if missing."""
    rows = list(
        db.select(
            "SELECT data_type FROM information_schema.columns "
            f"WHERE table_name = '{table_name}' AND column_name = '{column_name}' "
            "LIMIT 1"
        )
    )
    if not rows:
        return None
    return rows[0][0]


def _column_metadata(db, table_name: str, column_name: str) -> dict | None:
    rows = list(
        db.select(
            "SELECT data_type, character_maximum_length, udt_name, is_nullable "
            "FROM information_schema.columns "
            f"WHERE table_schema = 'public' AND table_name = '{table_name}' "
            f"AND column_name = '{column_name}' LIMIT 1"
        )
    )
    if not rows:
        return None
    data_type, char_max, udt_name, is_nullable = rows[0]
    return {
        "data_type": data_type,
        "character_maximum_length": char_max,
        "udt_name": udt_name,
        "is_nullable": is_nullable == "YES",
    }


def postgres_column_type_sql(db, table_name: str, column_name: str) -> str:
    """Build a PostgreSQL type fragment matching an existing column."""
    meta = _column_metadata(db, table_name, column_name)
    if meta is None:
        raise ValueError(f"Column {table_name}.{column_name} not found")

    data_type = meta["data_type"]
    if data_type == "character varying" and meta["character_maximum_length"]:
        return f"character varying({meta['character_maximum_length']})"
    if data_type == "ARRAY":
        return f"{meta['udt_name']}[]"
    if data_type == "USER-DEFINED":
        return meta["udt_name"]
    return data_type


def add_column_postgres_type(
    db,
    table_name: str,
    column_name: str,
    pg_type: str,
    *,
    required: bool = False,
    if_not_exists: bool = True,
) -> None:
    extra = "IF NOT EXISTS " if if_not_exists else ""
    query = (
        f'ALTER TABLE "{table_name}" ADD COLUMN {extra}"{column_name}" {pg_type}'
    )
    if required:
        query += " NOT NULL"
    print(query)
    db.execute(query)


def rename_column(db, table_name: str, old_name: str, new_name: str) -> None:
    query = (
        f'ALTER TABLE "{table_name}" RENAME COLUMN "{old_name}" TO "{new_name}"'
    )
    print(query)
    db.execute(query)


def set_column_not_null(db, table_name: str, column_name: str) -> None:
    query = (
        f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" SET NOT NULL'
    )
    print(query)
    db.execute(query)


def column_exists(db, table_name: str, column_name: str) -> bool:
    rows = list(
        db.select(
            "SELECT 1 FROM information_schema.columns "
            f"WHERE table_name = '{table_name}' AND column_name = '{column_name}' "
            "LIMIT 1"
        )
    )
    return bool(rows)


def table_exists(db, table_name: str) -> bool:
    rows = list(
        db.select(
            "SELECT 1 FROM information_schema.tables "
            f"WHERE table_name = '{table_name}' LIMIT 1"
        )
    )
    return bool(rows)


def _sql_type_for_property(prop) -> str:
    if prop.is_relation:
        return "int"
    py_type = prop.py_type
    if py_type not in PY_TYPES_TO_SQL:
        raise ValueError(
            f"Unsupported attribute type {py_type!r} on {prop.entity.__name__}.{prop.name}"
        )
    return PY_TYPES_TO_SQL[py_type]


def add_column_from_model_property(prop, not_required_columns: list | None = None) -> None:
    """Add a single column (and FK if needed) from a Pony entity attribute."""
    not_required_columns = not_required_columns or []
    entity_db = prop.entity._database_
    table_name = prop.entity._table_

    if not table_exists(entity_db, table_name):
        raise RuntimeError(
            f'Table "{table_name}" does not exist. '
            f"Use create_table_from_model({prop.entity.__name__}) in up(db) first."
        )

    add_column(
        entity_db,
        table_name,
        prop.column,
        _sql_type_for_property(prop),
        required=prop.is_required and prop.column not in not_required_columns,
        default=get_default_from_property(prop.default),
        unique=prop.is_unique,
    )
    if prop.is_relation:
        add_foreign_key_constraint(
            entity_db,
            table_name,
            prop.column,
            prop.py_type._table_,
        )


def create_table_from_model(
    model,
    not_required_columns: list | None = None,
    *,
    table_name: str | None = None,
    with_id: bool = True,
    unique_composite: list[tuple[str, ...]] | None = None,
    skip_columns: list[str] | None = None,
) -> None:
    """Create a table and columns from a Pony entity (review generated SQL)."""
    not_required_columns = not_required_columns or []
    skip_columns = skip_columns or []
    entity_db = model._database_
    table_name = table_name or model._table_

    create_table(entity_db, table_name, with_id=with_id)
    for prop in model._attrs_:
        if prop.is_pk or not prop.column or prop.column in skip_columns:
            continue
        add_column(
            entity_db,
            table_name,
            prop.column,
            _sql_type_for_property(prop),
            required=prop.is_required and prop.column not in not_required_columns,
            default=get_default_from_property(prop.default),
            unique=prop.is_unique,
        )
        if prop.is_relation:
            add_foreign_key_constraint(
                entity_db,
                table_name,
                prop.column,
                prop.py_type._table_,
            )

    for index in model._indexes_:
        columns = [attr.column for attr in index.attrs if attr.column]
        if len(columns) < 2:
            continue
        if index.is_unique:
            add_composite_unique_constraint(entity_db, table_name, *columns)
        else:
            add_composite_index(entity_db, table_name, *columns)

    for columns in unique_composite or []:
        add_composite_unique_constraint(entity_db, table_name, *columns)


def rebuild_table_with_serial_id(
    db,
    table_name: str,
    column_names: list[str],
    *,
    temp_suffix: str = "_new",
) -> None:
    """
    Rebuild a table that used a composite PK so it has id serial + copied rows.
    Column types are copied from the existing table (safe across migration order).
    """
    temp_table = f"{table_name}{temp_suffix}"
    if table_exists(db, temp_table):
        drop_table(db, temp_table)

    create_table(db, temp_table)
    for col in column_names:
        meta = _column_metadata(db, table_name, col)
        if meta is None:
            raise ValueError(f"Column {table_name}.{col} not found")
        pg_type = postgres_column_type_sql(db, table_name, col)
        add_column_postgres_type(
            db,
            temp_table,
            col,
            pg_type,
            required=not meta["is_nullable"],
        )

    cols_sql = ", ".join(f'"{col}"' for col in column_names)
    db.execute(
        f'INSERT INTO "{temp_table}" ({cols_sql}) '
        f'SELECT {cols_sql} FROM "{table_name}"'
    )
    drop_table(db, table_name)
    rename_table(db, temp_table, table_name)
    sync_id_sequence(db, table_name)


def ensure_membership_user_business_unique(db, table_name: str = "business_memberships") -> None:
    """Solaris option 1: serial id PK + UNIQUE(user, business)."""
    add_composite_unique_constraint(db, table_name, "user", "business", if_not_exists=True)


def add_missing_columns_from_model(
    model,
    not_required_columns: list | None = None,
    *,
    skip_columns: list[str] | None = None,
) -> None:
    """Add columns present on the entity but missing in the database."""
    not_required_columns = not_required_columns or []
    skip_columns = skip_columns or []
    entity_db = model._database_
    table_name = model._table_

    if not table_exists(entity_db, table_name):
        create_table_from_model(
            model,
            not_required_columns,
            skip_columns=skip_columns,
        )
        return

    for prop in model._attrs_:
        if prop.is_pk or not prop.column or prop.column in skip_columns:
            continue
        if column_exists(entity_db, table_name, prop.column):
            continue
        add_column_from_model_property(prop, not_required_columns)


def sync_entity_schema(model, not_required_columns: list | None = None) -> None:
    """Create the table or add any missing columns for an entity."""
    add_missing_columns_from_model(model, not_required_columns)


def discover_entity_classes() -> dict[str, type]:
    """Return registered Pony entity classes keyed by class name."""
    from app.businesses.models import Business, BusinessMembership
    from app.common.rbac.models import Permission, Role, RolePermission
    from app.users.models import User

    return {
        cls.__name__: cls
        for cls in (
            Business,
            BusinessMembership,
            User,
            Role,
            Permission,
            RolePermission,
        )
    }
