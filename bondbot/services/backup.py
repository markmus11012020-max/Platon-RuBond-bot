from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

PREFIX = "bondbot-"
SUFFIX = ".db"


def backup_database(
    db_path: str | Path,
    backup_dir: str | Path,
    *,
    keep: int = 14,
    now: datetime | None = None,
) -> Path:
    """Создаёт консистентную копию SQLite через online backup API."""
    source_path = Path(db_path)
    if not source_path.exists():
        raise FileNotFoundError(f"database not found: {source_path}")
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    target_path = target_dir / f"{PREFIX}{stamp}{SUFFIX}"

    source = sqlite3.connect(str(source_path))
    target = sqlite3.connect(str(target_path))
    try:
        with target:
            source.backup(target)
    finally:
        target.close()
        source.close()

    backups = sorted(
        target_dir.glob(f"{PREFIX}*{SUFFIX}"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for old in backups[max(1, keep):]:
        try:
            old.unlink()
        except OSError as exc:
            log.warning("backup prune %s failed: %s", old, exc)

    log.info("backup created: %s", target_path)
    return target_path


__all__ = ["backup_database"]
