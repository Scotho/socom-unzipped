#!/usr/bin/env bash
# Sprint 7 Task 4: the hosted-server folder. Assembles <out>/socom-unzipped-server/ from server/ --
# horizon-server/ (sources plus its Release binaries, no obj/, no bin/Debug/), the empty dirs the servers
# expect, config/ WITHOUT simulated.db, start-servers.ps1, seed-simulated-db.ps1, README.md -- and zips it.
# The seeded database never ships: the host seeds their own with seed-simulated-db.ps1. Usage:
#   scripts/make_server_zip.sh [out dir]      (default: dist/server)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVER="${SERVER:-$ROOT/server}"
OUT="${1:-$ROOT/dist/server}"
PKG="$OUT/socom-unzipped-server"
BINREL="bin/Release/net9.0"
for f in start-servers.ps1 seed-simulated-db.ps1 README.md; do
  [ -f "$SERVER/$f" ] || { echo "make_server_zip: $SERVER/$f missing -- point SERVER at a socom_pc server/ folder" >&2; exit 2; }
done
for p in Server.Unified.Launcher Server.NAT Server.UniverseInformation Server.Medius Server.Dme; do
  exe="$SERVER/horizon-server/$p/$BINREL/$p.exe"
  [ -f "$exe" ] || { echo "make_server_zip: $exe missing -- run server/start-servers.ps1 -Build first" >&2; exit 2; }
done
rm -rf "$PKG"
mkdir -p "$PKG/config" "$PKG/dme-plugins" "$PKG/medius-plugins" "$PKG/files" "$PKG/logs"
cp -r "$SERVER/horizon-server" "$PKG/horizon-server"
find "$PKG/horizon-server" -type d \( -name obj -o -name .git \) -prune -exec rm -rf {} +
find "$PKG/horizon-server" -type d -path '*/bin/Debug' -prune -exec rm -rf {} +
cp "$SERVER/start-servers.ps1" "$SERVER/seed-simulated-db.ps1" "$SERVER/README.md" "$PKG/"
# Sprint 8 Goal 12: the Linux glue (systemd units, horizon-ctl.sh, install.sh) rides along.
[ -f "$SERVER/linux/install.sh" ] || { echo "make_server_zip: $SERVER/linux/install.sh missing" >&2; exit 2; }
cp -r "$SERVER/linux" "$PKG/linux"
# config: every *.json, and deliberately NOT simulated.db (accounts + per-app settings are the host's own).
cp "$SERVER"/config/*.json "$PKG/config/"
cat > "$PKG/config/README.txt" <<'CFG'
SOCOM Unzipped -- server configuration

These are the live configs: nat.json, muis.json, medius.json, dme.json, db.config.json.

simulated.db is NOT in this zip on purpose. It is the encrypted account/per-app-settings database, and it is
the host's own: seed a fresh one before the first start, with the servers stopped, from the folder above --

    .\seed-simulated-db.ps1                 # account socom / socom for app id 10472, CreateAccountOnNotFound=True
    .\seed-simulated-db.ps1 -Show           # decrypt and print what is in it

Then set the address clients are told to dial back on, and start:

    .\start-servers.ps1 -PublicIp <this machine's public address>
    .\start-servers.ps1 -ShowIp             # what is advertised right now
    .\start-servers.ps1 -Status             # which ports are listening

Ports to forward from the router are listed in ..\README.md ("Hosting it on another machine").
CFG
cat > "$PKG/README.txt" <<'RD'
SOCOM Unzipped -- the hosted server (Horizon Private Server for SOCOM II, app id 10472)

1. Install the .NET 9 runtime (the binaries under horizon-server\*\bin\Release\net9.0 are prebuilt;
   .\start-servers.ps1 -Build rebuilds them and needs the .NET 9 SDK instead).
2. Seed the database once: .\seed-simulated-db.ps1        (see config\README.txt -- simulated.db does not ship)
3. Advertise this machine's address: .\start-servers.ps1 -PublicIp <public IP or hostname>
4. Forward the ports listed in README.md ("Hosting it on another machine: ports to forward") and open the
   Windows firewall for the server processes.
5. .\start-servers.ps1 -Status to see what is listening, -Stop to stop, -ShowIp to check the advertised address.

On Linux (Ubuntu 24.04; the same prebuilt binaries run under the .NET 9 runtime): seed simulated.db on a Windows
machine (step 2) and copy it into config/, then
    sudo bash linux/install.sh                                   # runtime, 'horizon' user, /opt/socom-unzipped-server, systemd units
    sudo /opt/socom-unzipped-server/linux/horizon-ctl.sh public-ip <public IP or hostname>
    sudo /opt/socom-unzipped-server/linux/horizon-ctl.sh start   # then: status | show-ip | stop | restart
Open the same ports in the host's firewall (README.md, "Hosting it on Linux").

README.md is the full write-up: layout, ports, the advertised-address fields, the database, what is verified.
Logs land in logs\.
RD
( cd "$OUT" && rm -f socom-unzipped-server.zip && powershell -NoProfile -Command "Compress-Archive -Path 'socom-unzipped-server' -DestinationPath 'socom-unzipped-server.zip' -Force" )
echo "server folder: $PKG ($(ls "$PKG" | wc -l) entries), zip: $OUT/socom-unzipped-server.zip ($(du -h "$OUT/socom-unzipped-server.zip" | cut -f1))"
