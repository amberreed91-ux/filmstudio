#!/bin/bash
# backup_studio_db.sh — timestamped SQLite backup + integrity check.
#
# Usage: scripts/backup_studio_db.sh [db_path] [backup_dir]
#   Defaults: data/studio.db and data/backups/
#
# Uses sqlite3 .backup (safe against a running backend; never copies the
# raw file while the -wal is hot), then runs integrity_check on the COPY.
# Exits non-zero unless integrity_check returns exactly "ok".
# Run BEFORE any restart, migration, or live-DB touch. No schedule is
# installed by this script — see docs/RELEASE_CHECKLIST.md.
set -euo pipefail

DB_PATH="${1:-data/studio.db}"
BACKUP_DIR="${2:-data/backups}"

if [ ! -f "${DB_PATH}" ]; then
    echo "ERROR: database not found: ${DB_PATH}" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/studio-$(basename "${DB_PATH}" .db)-${STAMP}.bak"

sqlite3 "${DB_PATH}" ".backup '${BACKUP_FILE}'"
echo "backup written: ${BACKUP_FILE}"

RESULT="$(sqlite3 "${BACKUP_FILE}" "PRAGMA integrity_check;")"
if [ "${RESULT}" != "ok" ]; then
    echo "ERROR: integrity_check failed on ${BACKUP_FILE}: ${RESULT}" >&2
    exit 1
fi
echo "integrity_check: ok"
