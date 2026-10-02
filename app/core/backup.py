"""SQLite backup, integrity and maintenance helpers."""
import datetime
import sqlite3
from pathlib import Path

from app.core.config import DB_PATH, BACKUP_DIR


def check_integrity(db_path=DB_PATH):
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    return {"ok": result == "ok", "result": result, "path": str(db_path)}


def vacuum_database(db_path=DB_PATH):
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.execute("VACUUM")
    return check_integrity(db_path)


def create_backup(destination=None, source=DB_PATH):
    source = Path(source)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if destination is None:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = BACKUP_DIR / f"coffeeshop-{stamp}.db"
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.resolve() == source.resolve():
        raise ValueError("Backup destination must differ from the live database")
    with sqlite3.connect(str(source), timeout=30) as source_conn, sqlite3.connect(str(destination)) as backup_conn:
        source_conn.backup(backup_conn)
    return {"path": str(destination), "size": destination.stat().st_size, **check_integrity(destination)}


def restore_backup(backup_path, target=DB_PATH):
    backup_path, target = Path(backup_path), Path(target)
    if not backup_path.is_file():
        raise FileNotFoundError(str(backup_path))
    integrity = check_integrity(backup_path)
    if not integrity["ok"]:
        raise ValueError("Backup failed integrity check")
    safety_copy = create_backup(
        BACKUP_DIR / f"pre-restore-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.db",
        source=target,
    ) if target.exists() else None
    with sqlite3.connect(str(backup_path), timeout=30) as source_conn, sqlite3.connect(str(target)) as target_conn:
        source_conn.backup(target_conn)
    result = check_integrity(target)
    result["safety_backup"] = safety_copy
    return result


def list_backups():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return [
        {"path": str(path), "size": path.stat().st_size,
         "modified_at": datetime.datetime.fromtimestamp(path.stat().st_mtime,
                                                         datetime.timezone.utc).isoformat()}
        for path in sorted(BACKUP_DIR.glob("*.db"), key=lambda item: item.stat().st_mtime, reverse=True)
    ]


def create_daily_backup(retention_days=30):
    """Create at most one scheduled backup per UTC day and prune old backups."""
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    existing = list(BACKUP_DIR.glob(f"coffeeshop-{today}*.db"))
    result = create_backup() if not existing else {
        "path": str(sorted(existing)[-1]),
        "skipped": True,
    }
    cutoff = datetime.datetime.now(datetime.timezone.utc).timestamp() - retention_days * 86400
    for path in BACKUP_DIR.glob("*.db"):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
    return result


# Descriptive aliases for callers that use the maintenance terminology.
database_integrity_check = check_integrity
vacuum_and_check = vacuum_database
