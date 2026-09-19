#!/usr/bin/env bash
# Install the hosted Horizon stack on an Ubuntu 24.04 box (Sprint 8 Goal 12). Run as root from the unpacked
# server folder:   sudo bash linux/install.sh
# Idempotent: the .NET 9 runtime, a 'horizon' user, the folder under /opt/socom-unzipped-server, the four units
# and their target, a logrotate rule. It does not start anything and does not set the advertised address:
#   sudo /opt/socom-unzipped-server/linux/horizon-ctl.sh public-ip <public IP or hostname>
#   sudo /opt/socom-unzipped-server/linux/horizon-ctl.sh start
# config/simulated.db does not ship: seed one with seed-simulated-db.ps1 on a Windows machine and copy it to
# /opt/socom-unzipped-server/config/ before the first start (see config/README.txt).
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "install.sh: run as root (sudo bash linux/install.sh)" >&2; exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/opt/socom-unzipped-server

if ! dotnet --list-runtimes 2>/dev/null | grep -q '^Microsoft.NETCore.App 9\.'; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q
  if ! apt-get install -y -q dotnet-runtime-9.0; then
    apt-get install -y -q software-properties-common
    add-apt-repository -y ppa:dotnet/backports
    apt-get update -q
    apt-get install -y -q dotnet-runtime-9.0
  fi
fi
dotnet --list-runtimes | grep '^Microsoft.NETCore.App 9\.'

id horizon >/dev/null 2>&1 || useradd --system --home-dir "$DEST" --shell /usr/sbin/nologin horizon

mkdir -p "$DEST"
if [ "$SRC" != "$DEST" ]; then
  # config/ is the host's own once installed: never overwrite an existing config file or the database.
  tar -C "$SRC" --exclude=./config -cf - . | tar -C "$DEST" -xf -
  mkdir -p "$DEST/config"
  for f in "$SRC"/config/*; do [ -e "$DEST/config/$(basename "$f")" ] || cp -p "$f" "$DEST/config/"; done
fi
mkdir -p "$DEST/logs" "$DEST/files" "$DEST/medius-plugins" "$DEST/dme-plugins"
chmod +x "$DEST"/linux/*.sh
chown -R horizon:horizon "$DEST"

install -m 0644 "$DEST"/linux/horizon-*.service "$DEST"/linux/horizon.target /etc/systemd/system/
cat > /etc/logrotate.d/horizon <<'ROT'
/opt/socom-unzipped-server/logs/*.log {
    weekly
    rotate 4
    size 50M
    compress
    missingok
    notifempty
    copytruncate
    su horizon horizon
}
ROT
systemctl daemon-reload
systemctl enable horizon.target horizon-nat.service horizon-muis.service horizon-medius.service horizon-dme.service
[ -f "$DEST/config/simulated.db" ] || echo "NOTE: $DEST/config/simulated.db is missing -- seed one and copy it up before the first start."
echo "installed. Next: $DEST/linux/horizon-ctl.sh public-ip <address> ; $DEST/linux/horizon-ctl.sh start ; ... status"
