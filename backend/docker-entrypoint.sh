#!/bin/sh
set -e

# Solaris-style setup: create DB if missing, then apply pending migrations.
export MIGRATE_MODE=1
export RUN_MIGRATIONS=true
python -c "from app.db import bootstrap_database; bootstrap_database()"
export SKIP_MIGRATIONS=1
unset MIGRATE_MODE

exec "$@"
