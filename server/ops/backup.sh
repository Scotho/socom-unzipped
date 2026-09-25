#!/usr/bin/env bash
# The hosted box's own backup of the Horizon account store (Sprint 10 Goal 2; tracked by Sprint 13 Task O3).
# Installed as /usr/local/sbin/socom-backup.sh and run daily by /etc/cron.d/socom-backup (backup.cron beside this
# file); run by hand any time: sudo socom-backup.sh
#
# Reads ops.env (OPS_ENV, else ops.env beside this script, else /etc/socom-unzipped/ops.env): OPS_SERVER_DIR,
# OPS_BACKUP_DIR, OPS_BACKUP_KEEP. Nothing about the box is written here.
#
# What it keeps: config/simulated.db (the accounts and personas; encrypted with the key in db.config.json, so the
# json files travel with it) and config/*.json, copied into $OPS_BACKUP_DIR/<UTC stamp>/ with a SHA256SUMS of
# bare file names, the newest OPS_BACKUP_KEEP sets kept. The server writes the database while running, so it is
# copied twice and compared: a torn copy is retried, and one that never settles is kept as simulated.db.unsettled
# so a restore knows.
#
# Restore (run once on 2026-09-21 on the box; server/README.md "Backups, health and the off-box pull"):
#   sudo $OPS_SERVER_DIR/linux/horizon-ctl.sh stop
#   sudo cp -p $OPS_BACKUP_DIR/<stamp>/simulated.db $OPS_SERVER_DIR/config/simulated.db
#   sudo chown horizon:horizon $OPS_SERVER_DIR/config/simulated.db
#   sudo $OPS_SERVER_DIR/linux/horizon-ctl.sh start && sudo $OPS_SERVER_DIR/linux/horizon-ctl.sh status
set -euo pipefail

load_ops_env() {
  local f="${OPS_ENV:-}"
  if [ -z "$f" ]; then
    f="$(cd "$(dirname "$0")" && pwd)/ops.env"
    [ -f "$f" ] || f=/etc/socom-unzipped/ops.env
  fi
  [ -f "$f" ] || { echo "$(basename "$0"): no ops.env (set OPS_ENV, or copy server/ops/ops.env.example to $f)" >&2; exit 2; }
  set -a; . <(tr -d '\r' < "$f"); set +a      # an ops.env saved on Windows has CRLF line ends
}
load_ops_env
: "${OPS_SERVER_DIR:?ops.env must set OPS_SERVER_DIR}"
: "${OPS_BACKUP_DIR:?ops.env must set OPS_BACKUP_DIR}"
: "${OPS_BACKUP_KEEP:?ops.env must set OPS_BACKUP_KEEP}"
case "$OPS_BACKUP_KEEP" in ''|*[!0-9]*|0) echo "backup.sh: OPS_BACKUP_KEEP must be a positive number" >&2; exit 2;; esac

SRC="$OPS_SERVER_DIR/config"
[ -f "$SRC/simulated.db" ] || { echo "backup.sh: $SRC/simulated.db not found" >&2; exit 1; }
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dest="$OPS_BACKUP_DIR/$stamp"
mkdir -p "$dest"
chmod 700 "$OPS_BACKUP_DIR"
settled=0
for attempt in 1 2 3 4 5; do
  cp -p "$SRC/simulated.db" "$dest/simulated.db.a"
  sleep "${OPS_BACKUP_SETTLE_SEC:-2}"
  cp -p "$SRC/simulated.db" "$dest/simulated.db.b"
  if cmp -s "$dest/simulated.db.a" "$dest/simulated.db.b"; then
    mv "$dest/simulated.db.b" "$dest/simulated.db"; rm -f "$dest/simulated.db.a"; settled=1; break
  fi
  rm -f "$dest/simulated.db.a" "$dest/simulated.db.b"
done
if [ "$settled" = 0 ]; then
  cp -p "$SRC/simulated.db" "$dest/simulated.db.unsettled"
fi
cp -p "$SRC"/*.json "$dest/"
( cd "$dest" && sha256sum -- * > SHA256SUMS )
chmod 600 "$dest"/*
# keep the newest OPS_BACKUP_KEEP sets (stamps sort by time)
ls -1d "$OPS_BACKUP_DIR"/*/ 2>/dev/null | sort | head -n -"$OPS_BACKUP_KEEP" | xargs -r rm -rf
echo "socom-backup: $dest ($(wc -c < "$(ls "$dest"/simulated.db* | head -1)") bytes, settled=$settled, $(ls -1d "$OPS_BACKUP_DIR"/*/ | wc -l) sets kept)"
