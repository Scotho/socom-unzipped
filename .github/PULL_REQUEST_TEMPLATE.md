## What and why

<!-- One paragraph. Link the issue. Target `main` (not a sprint branch) unless a maintainer asked otherwise. -->

## How it was tested

- [ ] A test failed before this change and passes after it (name it, and what it failed with)
- [ ] `bash scripts/build_linux.sh test --no-runner` (or `./build.sh test`) is green -- C++ total: ___ Python total: ___
- [ ] The three-stage gate, if this touches the runtime, `recomp/`, `tools_py/parity/`, `scripts/parity/` or
      `build.sh` -- stamp: ___ (no disc? say so and a maintainer runs it)

## What was measured

<!-- Numbers before and after, and the command. "None: documentation only" is a fine answer. Any default moved or
     measurement skipped is said here. -->

## Checklist

- [ ] No game code or data: no ISO, ELF, generated C++, extracted assets or saves
- [ ] No keys, tokens, private addresses or personal paths
- [ ] New third-party code has its licence text and a notices row
- [ ] A new `PS2X_*` knob has a reason and a table row; a path-valued knob stays inside the portable folder
