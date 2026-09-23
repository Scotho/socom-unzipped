#!/usr/bin/env bash
# The worktree an agent gets, exactly as docs/HANDOFF.md "Giving an agent a worktree" prescribes (learned the hard
# way on 2026-09-21: the toolchain was deleted THROUGH a junction twice, and an agent pushed to main three times
# against its brief). One command creates it right; one command removes it right.
#
#   scripts/agent_worktree.sh create <name> [base-ref]   # C:\projects\wt-<name>, branch agent/<name> off base (default: HEAD)
#   scripts/agent_worktree.sh remove <name>              # junctions deleted first and verified, then the worktree
#   scripts/agent_worktree.sh list
#
# What "right" means: `tools/` is junctioned in (the pinned toolchain) and NOTHING else -- never `game/` (the ISO
# and the decrypted overlays stay in the main tree; agents do not run the game); the push URL is dead so a brief's
# "do not push" is enforced by git, not by a sentence; the branch name says whose it is.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WT_ROOT="/c/projects"
NOPUSH="no-push://agent-worktree"

usage() { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

wt_path() { echo "$WT_ROOT/wt-$1"; }
win_path() { cygpath -w "$1"; }

create() {
  local name="$1" base="${2:-HEAD}" path
  [[ "$name" =~ ^[a-z0-9][a-z0-9-]{1,30}$ ]] || { echo "agent_worktree: name must be [a-z0-9-], got '$name'" >&2; exit 2; }
  path="$(wt_path "$name")"
  [ -e "$path" ] && { echo "agent_worktree: $path exists" >&2; exit 2; }
  git -C "$ROOT" rev-parse --verify -q "$base" >/dev/null || { echo "agent_worktree: no such base $base" >&2; exit 2; }
  git -C "$ROOT" worktree add -b "agent/$name" "$path" "$base" || exit 1
  # The dead push first: nothing else happens in this worktree until it cannot reach the remote.
  git -C "$path" config remote.origin.pushurl "$NOPUSH"
  [ "$(git -C "$path" config remote.origin.pushurl)" = "$NOPUSH" ] || { echo "agent_worktree: pushurl not set" >&2; exit 1; }
  # tools/ only. A real junction (git sees a directory, never a symlink), made by PowerShell: `cmd /c mklink /J`
  # from Git Bash loses its switches to MSYS path conversion (the first run of this script proved it).
  if [ -d "$ROOT/tools" ]; then
    powershell -NoProfile -Command "New-Item -ItemType Junction -Path '$(win_path "$path/tools")' -Target '$(win_path "$ROOT/tools")' | Out-Null" || { echo "agent_worktree: junction failed" >&2; exit 1; }
    [ -d "$path/tools/llvm-mingw" ] || { echo "agent_worktree: junction made but tools/llvm-mingw not visible through it" >&2; exit 1; }
  fi
  echo "created $path on agent/$name (base $(git -C "$path" rev-parse --short HEAD)); push disabled; tools/ junctioned"
  echo "build there with: bash scripts/loop_lock.sh run agent-$name --purpose \"...\" -- ./build.sh test --no-runner"
}

remove() {
  local name="$1" path
  path="$(wt_path "$name")"
  [ -d "$path" ] || { echo "agent_worktree: no worktree at $path" >&2; exit 2; }
  # Every junction goes first, through PowerShell's Delete() on the reparse point, and BOTH sides are verified
  # before git touches anything: `git worktree remove` recurses through a surviving junction into the main tree.
  for j in "$path"/tools; do
    [ -e "$j" ] || continue
    powershell -NoProfile -Command "(Get-Item -LiteralPath '$(win_path "$j")').Delete()" || { echo "agent_worktree: could not delete junction $j" >&2; exit 1; }
    [ -e "$j" ] && { echo "agent_worktree: junction $j still present; refusing to remove the worktree" >&2; exit 1; }
    [ -d "$ROOT/tools/llvm-mingw" ] || { echo "agent_worktree: the main tree's tools/ is damaged; STOP" >&2; exit 1; }
  done
  git -C "$ROOT" worktree remove --force "$path" || exit 1
  echo "removed $path (branch agent/$name kept; delete it with git branch -D when merged)"
}

case "${1:-}" in
  create) [ -n "${2:-}" ] || usage; create "$2" "${3:-HEAD}" ;;
  remove) [ -n "${2:-}" ] || usage; remove "$2" ;;
  list) git -C "$ROOT" worktree list ;;
  *) usage ;;
esac
