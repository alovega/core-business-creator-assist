"""Load and run pending migration modules."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from pony.orm import db_session

from app.db import db
from app.migrations.database_version import DatabaseVersion

MIGRATIONS_DIR = Path(__file__).resolve().parent / "versions"
IGNORE_FILES = {"__init__.py"}


def _migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        return []
    files = [
        path
        for path in MIGRATIONS_DIR.glob("*.py")
        if path.name not in IGNORE_FILES
    ]
    return sorted(files, key=lambda path: int(path.stem.split("_", 1)[0]))


def _version_from_path(path: Path) -> int:
    return int(path.stem.split("_", 1)[0])


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@db_session
def run_pending_migrations() -> None:
    DatabaseVersion.ensure_table(db)
    for path in _migration_files():
        version = _version_from_path(path)
        if not DatabaseVersion.is_pending(db, version):
            continue
        module = _load_module(path)
        print(f"Running migration {path.name}")
        module.up(db)
        DatabaseVersion.mark_executed(db, version)
