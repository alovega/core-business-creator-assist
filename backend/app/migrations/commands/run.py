"""CLI entrypoint for Pony migrations (Solaris-style migrate.up)."""

from app.db import bootstrap_database_for_cli

if __name__ == "__main__":
    bootstrap_database_for_cli()
