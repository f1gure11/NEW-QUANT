#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/okx-quant}"
APP_USER="${APP_USER:-okxbot}"
SSH_PORT="${SSH_PORT:-22}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root." >&2
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip rsync ufw curl ca-certificates unzip

if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
fi

mkdir -p "$APP_DIR" "$APP_DIR/data/okx"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 750 "$APP_DIR"

ufw allow "$SSH_PORT"/tcp
ufw --force enable

echo "Server base setup complete: $APP_DIR owned by $APP_USER"
echo "Dashboard stays on 127.0.0.1:8765. Use an SSH tunnel from your PC."
