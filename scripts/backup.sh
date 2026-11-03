#!/usr/bin/env bash
# Daily PostgreSQL + config backup with failure alerting and optional
# off-host replication (BUG-006). Install via cron (see docs/operations.md).
set -euo pipefail

APP_DIR="/opt/oxmit"
BACKUP_DIR="${APP_DIR}/backups"
RETENTION_DAYS=14
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "${BACKUP_DIR}"
cd "${APP_DIR}"

env_get() { grep -E "^$1=" .env | tail -n1 | cut -d= -f2-; }
POSTGRES_USER="$(env_get POSTGRES_USER)"
POSTGRES_DB="$(env_get POSTGRES_DB)"
BOT_TOKEN="$(env_get BOT_TOKEN)"
# Alert target: BACKUP_ALERT_CHAT_ID if set, else the first admin ID.
ALERT_CHAT_ID="${BACKUP_ALERT_CHAT_ID:-$(env_get ADMIN_TELEGRAM_IDS | cut -d, -f1)}"

alert() { # best-effort: log + notify via the LOCAL Bot API server (the cloud
          # API is unreachable after the documented logOut migration)
    local msg="$1"
    echo "$(date -Is) ALERT: ${msg}" >> "${BACKUP_DIR}/backup.log" || true
    if [ -n "${BOT_TOKEN:-}" ] && [ -n "${ALERT_CHAT_ID:-}" ]; then
        curl -s -m 10 "http://127.0.0.1:8081/bot${BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${ALERT_CHAT_ID}" \
            --data-urlencode "text=🚨 Oxmit backup failed: ${msg}" >/dev/null || true
    fi
}
trap 'alert "backup.sh exited with code $? (stamp ${STAMP})"' ERR

docker compose exec -T postgres pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  | gzip > "${BACKUP_DIR}/oxmit-db-${STAMP}.sql.gz"

tar -czf "${BACKUP_DIR}/oxmit-config-${STAMP}.tar.gz" \
  -C "${APP_DIR}" docker-compose.yml .env.example deploy 2>/dev/null || true

# Optional off-host replication: set BACKUP_RCLONE_TARGET (e.g. "remote:bucket/oxmit")
# and configure rclone separately. Best-effort; failure alerts but keeps local copy.
if [ -n "${BACKUP_RCLONE_TARGET:-}" ] && command -v rclone >/dev/null 2>&1; then
    rclone copy "${BACKUP_DIR}" "${BACKUP_RCLONE_TARGET}" --max-age 48h \
        || alert "rclone sync to ${BACKUP_RCLONE_TARGET} failed"
fi

find "${BACKUP_DIR}" -name 'oxmit-*' -type f -mtime +${RETENTION_DAYS} -delete
trap - ERR
echo "backup finished: ${BACKUP_DIR}/oxmit-db-${STAMP}.sql.gz"
