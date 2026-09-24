#!/usr/bin/env bash
# Fetch the owner's git-ignored build inputs into game/ from the private HTTPS location on s2u.scotho.com.
#
# Meant for a Claude cloud environment's setup script (Ubuntu, runs before the session), and works anywhere
# with curl. The files are the owner's own dumps: they are never committed, and this script never prints the
# credential. Nothing here is needed on a machine that already has game/ populated from a disc.
#
#   S2U_INPUTS_URL   the private base URL, ending in '/', e.g. https://s2u.scotho.com/private/<token>/
#   S2U_INPUTS_AUTH  'user:password' for HTTP basic auth (or leave unset when the environment's proxy
#                    attaches the credential itself)
#
# Verifies every file against the SHA256SUMS the location serves; a mismatch removes the file and fails.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${S2U_INPUTS_URL:?set S2U_INPUTS_URL to the private base URL (with a trailing slash)}"
curl_args=(-fsSL --retry 3 --retry-delay 2)
[ -n "${S2U_INPUTS_AUTH:-}" ] && curl_args+=(-u "$S2U_INPUTS_AUTH")

# served name -> destination under game/ (the paths the tools and research notes use)
declare -A DEST=(
  [SCUS_972.05]="demo_scus_972_05/SCUS_972.05"
  [socom2_game.elf]="disc/socom2_game.elf"
  [SCUS_973.68]="demo_scus_973_68/SCUS_973.68"
  [socom2_game_r0004.elf]="overlays_r0004/socom2_game_r0004.elf"
)

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
curl "${curl_args[@]}" -o "$tmp/SHA256SUMS" "${S2U_INPUTS_URL}SHA256SUMS"
for name in "${!DEST[@]}"; do
  dest="$ROOT/game/${DEST[$name]}"
  want="$(awk -v n="$name" '$2==n || $2=="*"n {print $1}' "$tmp/SHA256SUMS")"
  [ -n "$want" ] || { echo "fetch_private_inputs: $name is not in SHA256SUMS" >&2; exit 1; }
  if [ -f "$dest" ] && [ "$(sha256sum "$dest" | cut -d' ' -f1)" = "$want" ]; then
    echo "present  $name"; continue
  fi
  mkdir -p "$(dirname "$dest")"
  curl "${curl_args[@]}" -o "$tmp/$name" "${S2U_INPUTS_URL}${name}"
  got="$(sha256sum "$tmp/$name" | cut -d' ' -f1)"
  [ "$got" = "$want" ] || { echo "fetch_private_inputs: $name sha256 mismatch" >&2; exit 1; }
  mv "$tmp/$name" "$dest"
  echo "fetched  $name -> game/${DEST[$name]}"
done
