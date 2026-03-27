#!/usr/bin/env bash
# LiminalQA backup script
#
# Creates a timestamped tar.gz of the sled DB and (optionally) Grafana/Prometheus
# volumes, then optionally uploads to S3-compatible storage.
#
# Usage:
#   ./scripts/backup.sh                        # back up to ./backups/
#   ./scripts/backup.sh --dest /mnt/nas        # custom destination directory
#   ./scripts/backup.sh --s3 s3://bucket/path  # upload to S3 (requires awscli)
#   ./scripts/backup.sh --no-stop              # backup without stopping services
#                                              # (live backup — data may be inconsistent)
#
# Environment variables:
#   LIMINAL_DB_PATH   — path to sled DB (default: /var/lib/liminalqa/db)
#   BACKUP_DEST       — local destination directory (default: ./backups)
#   S3_BUCKET         — S3 URI prefix for upload (e.g. s3://my-bucket/liminalqa)
#   AWS_PROFILE       — AWS profile for s3 upload

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DB_PATH="${LIMINAL_DB_PATH:-/var/lib/liminalqa/db}"
DEST="${BACKUP_DEST:-./backups}"
S3_URI="${S3_BUCKET:-}"
STOP_SERVICES=true
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
ARCHIVE_NAME="liminalqa_backup_${TIMESTAMP}.tar.gz"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest)   DEST="$2"; shift 2 ;;
    --s3)     S3_URI="$2"; shift 2 ;;
    --no-stop) STOP_SERVICES=false; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

mkdir -p "$DEST"

# ---------------------------------------------------------------------------
# Stop services for a consistent snapshot (skip with --no-stop)
# ---------------------------------------------------------------------------
if $STOP_SERVICES; then
  echo "→ Stopping liminalqa-ingest and liminalqa-grpc …"
  if command -v systemctl &>/dev/null && systemctl is-active --quiet liminalqa-ingest 2>/dev/null; then
    sudo systemctl stop liminalqa-ingest liminalqa-grpc 2>/dev/null || true
    STARTED_SYSTEMD=true
  elif docker compose ps --services 2>/dev/null | grep -q "ingest"; then
    docker compose stop ingest grpc 2>/dev/null || true
    STARTED_COMPOSE=true
  else
    echo "  (no running services detected — proceeding)"
  fi
fi

# ---------------------------------------------------------------------------
# Create archive
# ---------------------------------------------------------------------------
ARCHIVE_PATH="${DEST}/${ARCHIVE_NAME}"
echo "→ Archiving ${DB_PATH} → ${ARCHIVE_PATH}"

if [[ ! -d "$DB_PATH" ]]; then
  echo "ERROR: DB path does not exist: ${DB_PATH}" >&2
  exit 1
fi

tar -czf "$ARCHIVE_PATH" -C "$(dirname "$DB_PATH")" "$(basename "$DB_PATH")"
ARCHIVE_SIZE=$(du -sh "$ARCHIVE_PATH" | cut -f1)
echo "  Archive size: ${ARCHIVE_SIZE}"

# ---------------------------------------------------------------------------
# Restart services
# ---------------------------------------------------------------------------
if $STOP_SERVICES; then
  if [[ "${STARTED_SYSTEMD:-false}" == "true" ]]; then
    echo "→ Restarting services via systemctl …"
    sudo systemctl start liminalqa-ingest liminalqa-grpc || true
  elif [[ "${STARTED_COMPOSE:-false}" == "true" ]]; then
    echo "→ Restarting services via docker compose …"
    docker compose start ingest grpc || true
  fi
fi

# ---------------------------------------------------------------------------
# Optional S3 upload
# ---------------------------------------------------------------------------
if [[ -n "$S3_URI" ]]; then
  echo "→ Uploading to ${S3_URI}/${ARCHIVE_NAME} …"
  aws s3 cp "$ARCHIVE_PATH" "${S3_URI}/${ARCHIVE_NAME}" \
    ${AWS_PROFILE:+--profile "$AWS_PROFILE"}
  echo "  Upload complete."
fi

# ---------------------------------------------------------------------------
# Prune old local backups (keep last 7)
# ---------------------------------------------------------------------------
echo "→ Pruning old backups (keeping last 7) …"
ls -1t "${DEST}"/liminalqa_backup_*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm --
echo "  Done."

echo ""
echo "✓ Backup complete: ${ARCHIVE_PATH}"
