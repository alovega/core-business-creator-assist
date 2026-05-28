"""Track executed timestamped migrations."""

from pony.orm import db_session


class DatabaseVersion:
    TABLE_NAME = "database_version"

    @staticmethod
    @db_session
    def ensure_table(db) -> None:
        from app.migrations.migration_helper import add_column, create_table

        create_table(db, DatabaseVersion.TABLE_NAME)
        add_column(db, DatabaseVersion.TABLE_NAME, "updated_at", "datetime")
        add_column(db, DatabaseVersion.TABLE_NAME, "version", "int")
        add_column(db, DatabaseVersion.TABLE_NAME, "versions_executed", "text")

    @staticmethod
    @db_session
    def executed_migrations(db) -> list[int]:
        try:
            rows = list(
                db.select(
                    f"SELECT versions_executed FROM {DatabaseVersion.TABLE_NAME} LIMIT 1"
                )
            )
            if not rows:
                return []
            raw = rows[0]
            if isinstance(raw, tuple):
                raw = raw[0]
            if not raw:
                return []
            return sorted(int(v) for v in str(raw).split(",") if v.strip())
        except Exception:
            return []

    @classmethod
    @db_session
    def is_pending(cls, db, version: int) -> bool:
        return version > 100 and version not in cls.executed_migrations(db)

    @classmethod
    @db_session
    def mark_executed(cls, db, version: int) -> None:
        executed = cls.executed_migrations(db)
        if version not in executed:
            executed.append(version)
        versions = ",".join(str(v) for v in sorted(executed))
        rows = list(db.select(f"SELECT id FROM {DatabaseVersion.TABLE_NAME} LIMIT 1"))
        if rows:
            row_id = rows[0] if not isinstance(rows[0], tuple) else rows[0][0]
            db.execute(
                f"UPDATE {DatabaseVersion.TABLE_NAME} SET version = {version}, "
                f"versions_executed = '{versions}', updated_at = CURRENT_TIMESTAMP "
                f"WHERE id = {row_id}"
            )
        else:
            db.execute(
                f"INSERT INTO {DatabaseVersion.TABLE_NAME} "
                f"(id, version, versions_executed, updated_at) "
                f"VALUES (1, {version}, '{versions}', CURRENT_TIMESTAMP)"
            )
