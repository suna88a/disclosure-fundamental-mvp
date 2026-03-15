#!/usr/bin/env bash
set -eu

APP_DIR="/srv/disclosure-fundamental-mvp"
LOG_DIR="$APP_DIR/logs"
DATA_DIR="$APP_DIR/data"
PDF_DIR="$DATA_DIR/pdf"
BACKUP_DIR="$DATA_DIR/backups"

mkdir -p "$LOG_DIR" "$PDF_DIR" "$BACKUP_DIR"

cd "$APP_DIR"

exec /srv/disclosure-fundamental-mvp/.venv/bin/uvicorn \
  app.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1 \
  --proxy-headers
