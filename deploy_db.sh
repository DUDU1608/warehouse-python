#!/usr/bin/env bash
set -euo pipefail

# === CONFIG ===
LOCAL_DB_PATH="${LOCAL_DB_PATH:-$HOME/Desktop/warehouse-python/instance/warehouse.db}"
REMOTE_USER="${REMOTE_USER:-root}"
REMOTE_HOST="${REMOTE_HOST:-31.97.229.134}"
APP_DIR="${APP_DIR:-/opt/warehouse-app/warehouse-user-module}"
REMOTE_DIR="${REMOTE_DIR:-$APP_DIR/instance}"
VENV_ACTIVATE="${VENV_ACTIVATE:-$APP_DIR/venv/bin/activate}"
LOG_DIR="${LOG_DIR:-/var/log/warehouse}"
BIND_ADDR="${BIND_ADDR:-127.0.0.1:8000}"
WORKERS="${WORKERS:-4}"

echo "📦 Deploying warehouse.db to ${REMOTE_USER}@${REMOTE_HOST} ..."

# 1) Prep server: stop app, ensure dirs, backup old DB
ssh "${REMOTE_USER}@${REMOTE_HOST}" bash -s <<'EOSSH'
set -e
APP_DIR="/opt/warehouse-app/warehouse-user-module"
INSTANCE_DIR="$APP_DIR/instance"
LOG_DIR="/var/log/warehouse"

mkdir -p "$INSTANCE_DIR" "$LOG_DIR"

# Stop gunicorn if running (ignore error if not running)
pkill -f "gunicorn.*127.0.0.1:8000" || true

# Backup current DB if present
if [ -f "$INSTANCE_DIR/warehouse.db" ]; then
  cp -v "$INSTANCE_DIR/warehouse.db" "$INSTANCE_DIR/warehouse.db.bak.$(date +%F-%H%M%S)"
fi
EOSSH

# 2) Copy DB up
scp "$LOCAL_DB_PATH" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/warehouse.db"

# 3) Fix perms and restart gunicorn from correct directory
ssh "${REMOTE_USER}@${REMOTE_HOST}" bash -s <<'EOSSH'
set -e
APP_DIR="/opt/warehouse-app/warehouse-user-module"
INSTANCE_DIR="$APP_DIR/instance"
VENV_ACTIVATE="$APP_DIR/venv/bin/activate"
LOG_DIR="/var/log/warehouse"
BIND_ADDR="127.0.0.1:8000"
WORKERS="4"

chmod 644 "${INSTANCE_DIR}/warehouse.db"

# Restart app (ensure we run from APP_DIR or pass --chdir)
source "${VENV_ACTIVATE}"
nohup gunicorn -w "$WORKERS" -b "$BIND_ADDR" --chdir "$APP_DIR" run:app >> "${LOG_DIR}/gunicorn.log" 2>&1 &
sleep 2
tail -n 80 "${LOG_DIR}/gunicorn.log" || true
EOSSH

echo "✅ Done."


