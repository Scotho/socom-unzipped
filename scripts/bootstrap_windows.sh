#!/usr/bin/env bash
# The Windows toolchain a fresh clone needs, fetched and verified (Sprint 10 H3; Sprint 11 Goal 0's third item).
#
#   bash scripts/bootstrap_windows.sh            fetch what is missing or at another version into tools/
#   bash scripts/bootstrap_windows.sh --check    say what is there and exit 0 iff all three match
#
# build.sh puts tools/llvm-mingw/bin, tools/cmake/bin and tools/ninja on its PATH and nothing else, so these three
# are the whole toolchain: the same llvm-mingw the owner's builds use (clang 23.1.0, ucrt), CMake and Ninja. Each
# archive is pinned by version AND sha256 -- a download that does not match is deleted, never used. Only these
# three directories under tools/ are touched; everything else there (Ghidra, PCSX2, the reference trees) is the
# owner's and is left alone. Python 3 is required (it does the extraction; there is no unzip on a bare Git Bash).
#
# The CMake tree fetches the rest itself at configure time (raylib, imgui, the FFmpeg prebuilt, ...): see
# third_party/ps2recomp/ps2xRuntime/CMakeLists.txt. What a fresh clone still cannot build is the game -- the
# recompiled code comes from your own disc (README "For developers").
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/scripts/python_env.sh"   # $PYTHON, resolved once for every script
TOOLS="${SOCOM_TOOLS_DIR:-$ROOT/tools}"     # the override exists for the script's own test
CACHE="$TOOLS/.bootstrap"

# name | version | url | sha256 | top-level directory inside the archive ("" = files at the root)
LLVM_MINGW_VERSION=20260826
CMAKE_VERSION=4.4.3
NINJA_VERSION=1.13.2
ENTRIES=(
  "llvm-mingw|$LLVM_MINGW_VERSION|https://github.com/mstorsjo/llvm-mingw/releases/download/$LLVM_MINGW_VERSION/llvm-mingw-$LLVM_MINGW_VERSION-ucrt-x86_64.zip|ae601f4e0f72bbdf441ad2df8bb16f037e2e9251559ea6b37b4057aef39c06c3|llvm-mingw-$LLVM_MINGW_VERSION-ucrt-x86_64"
  "cmake|$CMAKE_VERSION|https://github.com/Kitware/CMake/releases/download/v$CMAKE_VERSION/cmake-$CMAKE_VERSION-windows-x86_64.zip|4d52ebab7193a698651639ed80d8d04fd903358843572cf44c7fd234cb7c26ab|cmake-$CMAKE_VERSION-windows-x86_64"
  "ninja|$NINJA_VERSION|https://github.com/ninja-build/ninja/releases/download/v$NINJA_VERSION/ninja-win.zip|07fc8261b42b20e71d1720b39068c2e14ffcee6396b76fb7a795fb460b78dc65|"
)

py="$PYTHON"

sha256_of() { "$py" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }

stamp_of() { cat "$TOOLS/$1/.bootstrap-version" 2>/dev/null || echo "-"; }

check_only=0
[ "${1:-}" = "--check" ] && check_only=1

status=0
for entry in "${ENTRIES[@]}"; do
  IFS='|' read -r name version url sha top <<< "$entry"
  have="$(stamp_of "$name")"
  if [ "$have" = "$version" ]; then
    echo "bootstrap: $name $version present"
    continue
  fi
  if [ "$check_only" = 1 ]; then
    echo "bootstrap: $name wanted $version, have $have"
    status=1
    continue
  fi
  mkdir -p "$CACHE"
  archive="$CACHE/$(basename "$url")"
  if [ ! -f "$archive" ] || [ "$(sha256_of "$archive")" != "$sha" ]; then
    echo "bootstrap: fetching $name $version ($(basename "$url"))"
    rm -f "$archive"
    curl -sSL --fail --retry 3 -o "$archive.part" "$url"
    mv -f "$archive.part" "$archive"
  fi
  got="$(sha256_of "$archive")"
  if [ "$got" != "$sha" ]; then
    rm -f "$archive"
    echo "bootstrap: $name: sha256 mismatch -- wanted $sha, got $got. The download is deleted; nothing was installed." >&2
    exit 1
  fi
  echo "bootstrap: $name $version verified; extracting into tools/$name"
  # Extract straight into the final directory and write the version stamp LAST. There used to be an
  # extract-then-`mv` here, and on this machine `mv` refused to rename llvm-mingw's 9,314 files in a second working
  # tree ("Permission denied", destination absent, no reparse point and no read-only bit; PowerShell's Rename-Item
  # on the same path succeeded instantly) -- it stopped a fresh clone at its very first command. No rename, no
  # failure mode: an interrupted extraction leaves no stamp, `--check` reports the version missing, and the next run
  # redoes it from the cached, sha256-verified archive.
  rm -rf "$TOOLS/$name"
  "$py" - "$archive" "$TOOLS/$name" "$top" <<'PY'
import os, sys, zipfile
archive, dest, top = sys.argv[1], sys.argv[2], sys.argv[3]
with zipfile.ZipFile(archive) as z:
    for info in z.infolist():
        rel = info.filename
        if top:
            if not rel.startswith(top + "/"):
                continue
            rel = rel[len(top) + 1:]
        if not rel or rel.endswith("/"):
            continue
        if ".." in rel.split("/") or rel.startswith("/"):
            raise SystemExit(f"refusing archive member {info.filename!r}")
        out = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with z.open(info) as src, open(out, "wb") as dst:
            dst.write(src.read())
PY
  printf '%s\n' "$version" > "$TOOLS/$name/.bootstrap-version"
done

if [ "$check_only" = 1 ]; then
  exit "$status"
fi
export PATH="$TOOLS/llvm-mingw/bin:$TOOLS/cmake/bin:$TOOLS/ninja:$PATH"
echo "bootstrap: $(clang --version | head -1)"
echo "bootstrap: $(cmake --version | head -1)"
echo "bootstrap: ninja $(ninja --version)"
