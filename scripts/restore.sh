#!/usr/bin/env bash
# LiminalQA restore script
#
# Restores a sled DB from a backup archive created by backup.sh.
# The target services are stopped before restoring and restarted after.
#
# Usage:
#   ./scripts/restore.sh <backup.tar.gz>
#   ./scripts/restore.sh s3://bucket/liminalqa_backup_20250101_120000.tar.gz
#
# Environment variables:
#   LIMINAL_DB_PATH   — restore destination (default: /var/lib/liminalqa/db)
#   AWS_PROFILE       — AWS profile for S3 download

set -euo pipefail

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <backup.tar.gz | s3://...>" >&2
  exit 1
fi

SOURCE="$1"
DB_PATH="${LIMINAL_DB_PATH:-/var/lib/liminalqa/db}"
DB_PARENT="$(dirname "$DB_PATH")"
DB_NAME="$(basename "$DB_PATH")"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# ---------------------------------------------------------------------------
# Download from S3 if needed
# ---------------------------------------------------------------------------
LOCAL_ARCHIVE="$SOURCE"
if [[ "$SOURCE" == s3://* ]]; then
  LOCAL_ARCHIVE="/tmp/liminalqa_restore_${TIMESTAMP}.tar.gz"
  echo "→ Downloading ${SOURCE} …"
  aws s3 cp "$SOURCE" "$LOCAL_ARCHIVE" \
    ${AWS_PROFILE:+--profile "$AWS_PROFILE"}
fi

if [[ ! -f "$LOCAL_ARCHIVE" ]]; then
  echo "ERROR: Archive not found: ${LOCAL_ARCHIVE}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Stop services
# ---------------------------------------------------------------------------
echo "→ Stopping liminalqa services …"
if command -v systemctl &>/dev/null && systemctl is-active --quiet liminalqa-ingest 2>/dev/null; then
  sudo systemctl stop liminalqa-ingest liminalqa-grpc 2>/dev/null || true
  RESTART_SYSTEMD=true
elif docker compose ps --services 2>/dev/null | grep -q "ingest"; then
  docker compose stop ingest grpc 2>/dev/null || true
  RESTART_COMPOSE=true
fi

# ---------------------------------------------------------------------------
# Rotate existing DB (keep as .bak)
# ---------------------------------------------------------------------------
if [[ -d "$DB_PATH" ]]; then
  BAK="${DB_PATH}.bak_${TIMESTAMP}"
  echo "→ Moving existing DB to ${BAK} …"
  mv "$DB_PATH" "$BAK"
fi

# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------
echo "→ Extracting archive into ${DB_PARENT} …"
mkdir -p "$DB_PARENT"
tar -xzf "$LOCAL_ARCHIVE" -C "$DB_PARENT"

if [[ ! -d "$DB_PATH" ]]; then
  echo "ERROR: Extracted archive did not produce ${DB_PATH}" >&2
  echo "  Contents of ${DB_PARENT}:" >&2
  ls "$DB_PARENT" >&2
  exit 1
fi

echo "  Restored: ${DB_PATH}"

# ---------------------------------------------------------------------------
# Restart services
# ---------------------------------------------------------------------------
echo "→ Restarting services …"
if [[ "${RESTART_SYSTEMD:-false}" == "true" ]]; then
  sudo systemctl start liminalqa-ingest liminalqa-grpc
elif [[ "${RESTART_COMPOSE:-false}" == "true" ]]; then
  docker compose start ingest grpc
fi

# ---------------------------------------------------------------------------
# Clean up temp download
# ---------------------------------------------------------------------------
if [[ "$SOURCE" == s3://* ]]; then
  rm -f "$LOCAL_ARCHIVE"
fi

echo ""
echo "✓ Restore complete. DB is at: ${DB_PATH}"
echo "  Old DB (if any) is at: ${DB_PATH}.bak_${TIMESTAMP}"
