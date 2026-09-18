#!/usr/bin/env bash
# Sprint 8 Goal 1: sync the tree (and, on request, the generated code and the ISO) into the socom-linux VM over SSH.
# The host has no rsync, so the tree travels as a tar stream; the generated code likewise; the ISO by scp once.
#   scripts/vm_sync.sh tree        # the repository minus build dirs, logs, vm/, dist*/ (a few seconds)
#   scripts/vm_sync.sh generated   # recomp/output (576 MB, 14,882 files; once, or after a re-recomp)
#   scripts/vm_sync.sh iso <path>  # the ISO to ~/socom2.iso (4 GB, once)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
KEY="$ROOT/vm/keys/socom_linux"
SSH="ssh -i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -p 2222 socom@127.0.0.1"
case "${1:-tree}" in
  tree)
    $SSH 'mkdir -p ~/socom_pc' &&
    tar --exclude=./third_party/ps2recomp/build-clang --exclude=./third_party/ps2recomp/build-tools \
        --exclude=./vm --exclude=./logs --exclude=./dist --exclude=./dist-linux --exclude=./recomp/output \
        --exclude=./tools/llvm-mingw --exclude=./tools/cmake --exclude=./tools/ninja --exclude=./tools/pcsx2 \
        --exclude=./server --exclude=./research --exclude=./node_modules --exclude='*.wav' --exclude='*.iso' \
        -czf - . | $SSH 'tar -xzf - -C ~/socom_pc' && echo "tree synced" ;;
  generated)
    $SSH 'mkdir -p ~/socom_pc/recomp/output' &&
    tar -C recomp -czf - output | $SSH 'tar -xzf - -C ~/socom_pc/recomp' && $SSH 'ls ~/socom_pc/recomp/output | wc -l' ;;
  iso)
    scp -i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -P 2222 "$2" socom@127.0.0.1:~/socom2.iso && echo "iso copied" ;;
  ssh) shift; $SSH "$@" ;;
  *) echo "usage: vm_sync.sh tree|generated|iso <path>|ssh <cmd>" >&2; exit 2 ;;
esac
