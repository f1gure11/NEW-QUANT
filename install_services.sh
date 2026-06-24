#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/okx-quant}"
APP_USER="${APP_USER:-okxbot}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root." >&2
  exit 1
fi

cd "$APP_DIR"
python3 -m venv .venv
".venv/bin/python" -m pip install --upgrade pip

mkdir -p data/okx
touch data/okx/grid_bot_stdout.log data/okx/re_grid_bot_stdout.log data/okx/dashboard_stdout.log
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 750 "$APP_DIR"
if [[ -f "$APP_DIR/.env" ]]; then
  chmod 600 "$APP_DIR/.env"
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
fi

cp deploy/systemd/okx-dashboard.service /etc/systemd/system/okx-dashboard.service
cp deploy/systemd/okx-beat-bot.service /etc/systemd/system/okx-beat-bot.service
cp deploy/systemd/okx-re-bot.service /etc/systemd/system/okx-re-bot.service

systemctl daemon-reload
systemctl enable okx-dashboard.service

echo "Services installed."
echo "Start dashboard: systemctl start okx-dashboard"
echo "Default bot control path: open the dashboard and use the BEAT/RE buttons."
echo "Standalone units are installed for emergency/manual use only:"
echo "  systemctl start okx-beat-bot"
echo "  systemctl start okx-re-bot"
