"""Create a timestamped migration file (SolarisServer-style)."""

from __future__ import annotations

import stat
import sys
import time
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "versions"

TEMPLATE = """from pony.orm import db_session


@db_session
def up(db):
    pass


@db_session
def down(db):
    pass
"""


def create_migration(name: str) -> Path:
    version = int(time.time())
    safe_name = name.replace(" ", "_").replace("-", "_").lower()
    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = MIGRATIONS_DIR / f"{version}_{safe_name}.py"
    path.write_text(TEMPLATE, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IWUSR)
    print(f"Migration file {path} was created.")
    return path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.migrations.commands.create_migration <name>")
        raise SystemExit(1)
    create_migration(sys.argv[1])
