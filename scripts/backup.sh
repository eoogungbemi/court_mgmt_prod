#!/usr/bin/env bash
# pg_dump backup for any court-mgmt deployment.
#
# Configuration (override via environment variables):
#   COMPOSE_FILE   — path to the compose file  (default: docker-compose.server.yml
#                    if it exists, else docker-compose.deploy.yml)
#   PROJECT        — docker compose project name (default: court-mgmt)
#   BACKUP_DIR     — where to store dumps       (default: /var/backups/court-mgmt)
#   KEEP_DAILY     — days of daily backups to keep (default: 14)
#   KEEP_WEEKLY    — weeks of weekly backups to keep (default: 8)
#
# Cron (runs at 02:00 every night, logs to /var/log/court-backup.log):
#   0 2 * * * /opt/court/scripts/backup.sh >> /var/log/court-backup.log 2>&1
#
# For deploy.sh-managed installations use:
#   0 2 * * * /opt/court-NAME/scripts/backup.sh >> /var/log/court-NAME-backup.log 2>&1

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Pick the right compose file automatically
if [[ -z "${COMPOSE_FILE:-}" ]]; then
  if [[ -f "${APP_DIR}/docker-compose.server.yml" ]]; then
    COMPOSE_FILE="${APP_DIR}/docker-compose.server.yml"
  else
    COMPOSE_FILE="${APP_DIR}/docker-compose.deploy.yml"
  fi
fi

PROJECT="${PROJECT:-court-mgmt}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/court-mgmt}"
KEEP_DAILY="${KEEP_DAILY:-14}"
KEEP_WEEKLY="${KEEP_WEEKLY:-8}"

DATE=$(date +%Y-%m-%d)
WEEKDAY=$(date +%u)   # 1=Mon … 7=Sun

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

DAILY_FILE="$BACKUP_DIR/daily/court_mgmt_${DATE}.sql.gz"

echo "[$(date -Iseconds)] Starting backup — project=${PROJECT} file=$(basename "$COMPOSE_FILE")"
echo "[$(date -Iseconds)] Target: ${DAILY_FILE}"

docker compose -f "$COMPOSE_FILE" -p "$PROJECT" exec -T db \
  pg_dump -U "${POSTGRES_USER:-court}" "${POSTGRES_DB:-court_mgmt}" \
  | gzip > "$DAILY_FILE"

SIZE=$(du -sh "$DAILY_FILE" | cut -f1)
echo "[$(date -Iseconds)] Backup complete (${SIZE})"

# Promote to weekly on Sundays
if [[ "$WEEKDAY" -eq 7 ]]; then
  WEEKLY_FILE="$BACKUP_DIR/weekly/court_mgmt_week_$(date +%Y-W%V).sql.gz"
  cp "$DAILY_FILE" "$WEEKLY_FILE"
  echo "[$(date -Iseconds)] Weekly copy saved → $WEEKLY_FILE"
fi

# Prune old backups
find "$BACKUP_DIR/daily"  -name "*.sql.gz" -mtime +"$KEEP_DAILY"  -delete
find "$BACKUP_DIR/weekly" -name "*.sql.gz" -mtime +"$((KEEP_WEEKLY * 7))" -delete

echo "[$(date -Iseconds)] Done. Remaining backups:"
ls -lh "$BACKUP_DIR/daily/" "$BACKUP_DIR/weekly/" 2>/dev/null || true
