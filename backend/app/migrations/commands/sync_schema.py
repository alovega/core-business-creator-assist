"""Apply entity definitions to the database (add missing tables/columns)."""

from __future__ import annotations

import sys

from pony.orm import db_session

from app.db import db
from app.migrations.migration_helper import discover_entity_classes, sync_entity_schema


@db_session
def sync_all(entity_names: list[str] | None = None) -> None:
    registry = discover_entity_classes()
    targets = entity_names or sorted(registry)
    for name in targets:
        if name not in registry:
            raise SystemExit(f"Unknown entity: {name}")
        model = registry[name]
        print(f"Syncing schema for {name} ({model._table_})...")
        sync_entity_schema(model)


if __name__ == "__main__":
    from run import app  # noqa: F401 — initializes Pony mapping

    with app.app_context():
        names = sys.argv[1:] if len(sys.argv) > 1 else None
        sync_all(names)
