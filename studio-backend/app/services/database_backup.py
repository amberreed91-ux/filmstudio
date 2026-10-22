import asyncio
import logging
import os
import time
from pathlib import Path
from app.data.db_guard import (
    LIVE_DB_FILE,
    assert_live_open_allowed,
    backup_database,
)

logger = logging.getLogger("studio-backup")

# Active production database target. All automated backups snapshot this
# file: studio-backend/data/studio.db (resolved from this module's location
# so the target is stable regardless of process cwd or env overrides).
ACTIVE_STUDIO_DB_PATH = str(LIVE_DB_FILE)


def get_active_db_path() -> str:
    """Return the active backup source (the live studio.db file)."""
    return ACTIVE_STUDIO_DB_PATH


class DatabaseBackup:
    """Automated SQLite database backup with rotation."""

    def __init__(
        self,
        db_path: str,
        backup_dir: str = "./backups",
        max_backups: int = 7,
    ):
        # Fail closed on the live path (construction-time, before any open).
        assert_live_open_allowed(db_path)
        self.db_path = db_path
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.max_backups = max_backups

    def create_backup(self) -> dict:
        """Create a timestamped backup using SQLite's online backup API."""
        start = time.perf_counter()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"studio_{timestamp}.db"

        backup_database(self.db_path, backup_path)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        size_bytes = backup_path.stat().st_size

        logger.info("Backup created: %s (%d bytes, %.1fms)", backup_path, size_bytes, duration_ms)

        self._rotate_backups()

        return {
            "backup_path": str(backup_path),
            "size_bytes": size_bytes,
            "duration_ms": duration_ms,
        }

    def _rotate_backups(self):
        """Remove backups beyond the max retention count."""
        backups = sorted(self.backup_dir.glob("studio_*.db"), key=lambda p: p.stat().st_mtime)
        while len(backups) > self.max_backups:
            oldest = backups.pop(0)
            oldest.unlink()
            logger.info("Rotated old backup: %s", oldest)

    def get_status(self) -> dict:
        """Get backup status."""
        backups = sorted(self.backup_dir.glob("studio_*.db"), key=lambda p: p.stat().st_mtime)
        last_backup = backups[-1] if backups else None
        return {
            "backup_dir": str(self.backup_dir),
            "total_backups": len(backups),
            "last_backup": {
                "path": str(last_backup),
                "size_bytes": last_backup.stat().st_size,
                "created_at": last_backup.stat().st_mtime,
            } if last_backup else None,
            "max_retention": self.max_backups,
        }

    async def schedule_daily(self, interval_hours: int = 24):
        """Background loop for scheduled backups."""
        while True:
            await asyncio.sleep(interval_hours * 3600)
            try:
                self.create_backup()
            except Exception as e:
                logger.error("Scheduled backup failed: %s", e)


# Singleton
_database_backup: DatabaseBackup | None = None


def get_database_backup() -> DatabaseBackup | None:
    return _database_backup


def init_database_backup(db_path: str | None = None, backup_dir: str = "./backups", max_backups: int = 7) -> DatabaseBackup:
    global _database_backup
    resolved = db_path or ACTIVE_STUDIO_DB_PATH
    if str(resolved) != ACTIVE_STUDIO_DB_PATH:
        logger.warning(
            "Database backup source %s differs from active target %s",
            resolved, ACTIVE_STUDIO_DB_PATH,
        )
    _database_backup = DatabaseBackup(resolved, backup_dir, max_backups)
    return _database_backup
