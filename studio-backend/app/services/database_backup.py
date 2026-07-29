import asyncio
import logging
import os
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger("studio-backup")


class DatabaseBackup:
    """Automated SQLite database backup with rotation."""

    def __init__(
        self,
        db_path: str,
        backup_dir: str = "./backups",
        max_backups: int = 7,
    ):
        self.db_path = db_path
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.max_backups = max_backups

    def create_backup(self) -> dict:
        """Create a timestamped backup using SQLite's online backup API."""
        start = time.perf_counter()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"studio_{timestamp}.db"

        source = sqlite3.connect(self.db_path)
        dest = sqlite3.connect(str(backup_path))
        try:
            source.backup(dest)
        finally:
            source.close()
            dest.close()

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


def init_database_backup(db_path: str, backup_dir: str = "./backups", max_backups: int = 7) -> DatabaseBackup:
    global _database_backup
    _database_backup = DatabaseBackup(db_path, backup_dir, max_backups)
    return _database_backup
