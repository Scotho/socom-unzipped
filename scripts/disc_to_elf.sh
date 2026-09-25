#!/usr/bin/env bash
# Your own SOCOM II disc -> the files ./build.sh recomp needs (Sprint 10, 2026-09-21).
#
#   bash scripts/disc_to_elf.sh "/path/to/SOCOM II - U.S. Navy SEALs (USA).iso"
#   bash scripts/disc_to_elf.sh --check                 what is already done under game/
#   bash scripts/disc_to_elf.sh <iso> --out /some/dir   put the tree and the overlays elsewhere
#
# It extracts the ISO9660 filesystem to game/disc/, decrypts the DNAS overlay and the APACHE00.ZDB
# code package by running the game's own code under Unicorn, merges the result into
# game/overlays/socom2_game.elf, and verifies every step against tools_py/disc_to_elf_expected.json.
# About ten minutes and 4.2 GB the first time; a second run is a no-op that still verifies. The two
# decryption stages need Unicorn: pip install unicorn.
#
# All of the work is tools_py/disc_to_elf.py -- this wrapper exists so the documented command has the
# same shape as the other two a newcomer types (scripts/bootstrap_windows.sh, ./build.sh) and so it
# finds the interpreter under either name (scripts/python_env.sh). `python3 -m tools_py.disc_to_elf` is
# the same thing with the same arguments; docs/DEVELOPING.md "From your own disc to a buildable ELF" is
# the recipe.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/scripts/python_env.sh"   # $PYTHON, resolved once for every script
socom_require_python disc_to_elf

cd "$ROOT"
exec "$PYTHON" -m tools_py.disc_to_elf "$@"
