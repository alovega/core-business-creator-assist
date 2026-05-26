"""Scaffold a migration from Pony entity definitions."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from app.migrations.migration_helper import discover_entity_classes

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "versions"


def _import_lines(entity_names: list[str]) -> tuple[list[str], list[str]]:
    registry = discover_entity_classes()
    imports: list[str] = []
    models: list[str] = []
    module_paths: dict[str, str] = {
        "User": "app.users.models",
        "Business": "app.businesses.models",
    }

    for name in entity_names:
        if name not in registry:
            known = ", ".join(sorted(registry))
            raise SystemExit(f"Unknown entity '{name}'. Known entities: {known}")
        module = module_paths.get(name, f"app.{name.lower()}s.models")
        imports.append(f"from {module} import {name}")
        models.append(name)

    return imports, models


def create_migration_from_model(name: str, entity_names: list[str]) -> Path:
    version = int(time.time())
    safe_name = name.replace(" ", "_").replace("-", "_").lower()
    path = MIGRATIONS_DIR / f"{version}_{safe_name}.py"
    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)

    import_lines, model_names = _import_lines(entity_names)
    up_body = "\n".join(
        f"    create_table_from_model({model})" for model in model_names
    )
    down_body = "\n".join(
        f'    drop_table(db, {model}._table_)' for model in model_names
    )

    imports_block = "\n".join(import_lines)
    content = f'''"""Migration: {safe_name}

Auto-generated from Pony entities: {", ".join(model_names)}
Review SQL output before applying in production.
"""

from pony.orm import db_session

from app.migrations.migration_helper import create_table_from_model, drop_table

{imports_block}


@db_session
def up(db):
{up_body}


@db_session
def down(db):
{down_body}
'''
    path.write_text(content, encoding="utf-8")
    print(f"Created model-based migration: {path}")
    return path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python -m app.migrations.commands.create_migration_from_model "
            "<migration_name> <EntityName> [EntityName ...]"
        )
        print(
            "Example: python -m app.migrations.commands.create_migration_from_model "
            "add_businesses Business"
        )
        raise SystemExit(1)
    create_migration_from_model(sys.argv[1], sys.argv[2:])
