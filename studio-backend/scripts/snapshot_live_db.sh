#!/bin/bash
# Consistent main+wal+shm snapshot of a SQLite WAL database.
#
# Usage: snapshot_live_db.sh [source_dir] [dest_dir]
#   source_dir defaults to the live studio-backend/data dir.
#   dest_dir   defaults to ./data-dev/<timestamp>.
#
# Copies bytes only (cp -p, never opens SQLite), hashes all three files,
# and prints the set for the operator's records. Run this BEFORE restarting
# servers against a dev copy (see Part 2 cutover note).
set -u
SRC="${1:-$(cd "$(dirname "$0")/../data" && pwd)}"
DEST="${2:-$(cd "$(dirname "$0")/../.." && pwd)/studio-backend/data-dev/manual-$(date +%Y%m%dT%H%M%S)}"
mkdir -p "$DEST"
for f in studio.db studio.db-wal studio.db-shm; do
  if [ -e "$SRC/$f" ]; then
    cp -p "$SRC/$f" "$DEST/$f" || exit 1
  fi
done
echo "snapshot set -> $DEST"
ls -lT "$DEST"/studio.db* 2>/dev/null || ls -l "$DEST"/studio.db*
shasum -a 256 "$DEST"/studio.db* 2>/dev/null || sha256sum "$DEST"/studio.db*
