# SOCOM Unzipped

**SOCOM II: U.S. Navy SEALs, statically recompiled from your own disc into a native PC program, with online play on a
hosted server.**

[![linux](https://github.com/Scotho/socom-unzipped/actions/workflows/linux.yml/badge.svg)](https://github.com/Scotho/socom-unzipped/actions/workflows/linux.yml)

> **Early stage.** This is a working prototype, not a finished port. It boots, renders the menus and missions, and two
> players have finished online rounds against each other on the hosted server -- but audio, some maps, and the rough
> edges of a first release are still being worked through, and things break between builds. Read [Status](#status)
> before you expect anything.

## What it is, and what it is not

- **A static recompilation.** The game's PS2 executable is translated to C++ once and compiled natively; the result runs
  the game's own code as a normal Windows (and, in progress, Linux) program. There is no PS2 emulator underneath -- the
  runtime provides the hardware the code expects (EE kernel, DMA, a software/OpenGL GS, VU1, the IOP services), and
  SOCOM-specific hooks on top of that.
- **Your own disc.** The game reads its assets from the ISO of the US retail release (`SCUS-97275`, disc revision
  r0001); the launcher verifies the disc before it will launch. **No game code or game data is in this repository**:
  not the executable, not the recompiled C++, not textures, audio, movies or saves -- the recompiled program is built
  by each developer from their own disc. A contribution that adds any of it is closed unread (`CONTRIBUTING.md`). How
  a player build is distributed without shipping any of that is being settled before the first public release.
- **Online play on a server we host.** The game's original network (DNAS / Medius) is gone; this project runs a
  [Horizon Private Server](https://github.com/Horizon-Private-Server/horizon-server) configured for SOCOM II and points
  the game at it. The launcher's default server is `socom.scotho.com`.
- **Not affiliated** with Sony Interactive Entertainment, Zipper Interactive, or the SOCOM community servers. SOCOM is
  their trademark; this is a fan project for people who own the disc.

## Status

As of September 2026 (Sprint 10, tag `v0.9.0`):

| Works | Not yet |
|---|---|
| Boots from the ISO to the title, through the menus, into a mission; keyboard, mouse look, and Xbox/DirectInput pads | A public release download. Builds are handed to testers by hand; the download and its page are Sprint 11 |
| Rendering through an OpenGL backend with an integer up-scale (1x-3x); a CPU rasteriser for tests | Terrain holes on some maps (root cause still open) and a water defect on one map |
| Online: login, lobby, and full rounds on the hosted Horizon server -- two of our instances, and one of ours against a console client through PCSX2 | Music and mission ambience are mid-fix (the stream ring and a conductor-sound path); voice chat is untested end to end |
| A launcher that owns the settings, checks the disc, picks the server, and files bug reports | Linux: the runtime, tests and launcher build in CI; the playable build is being brought up in a VM |
| An automated parity gate (title / transition / mission) and an online "ladder" that plays rounds unattended | Anything but the NTSC r0001 disc |

The live, audited version of this table is `docs/KNOWN.md` (proven, believed, and retracted, each with its evidence),
and `docs/STATUS.md` is the day-by-day.

## For players

There is no public download yet. When there is, it will be announced at <https://s2u.scotho.com>, which also carries the
setup guide and the server's live status. The shape of it: unzip a folder, run `socom_unzipped_launcher.exe`, point it
at your SOCOM II ISO, pick video and controller settings, Launch. Nothing is installed; delete the folder to uninstall.
The launcher refuses any disc that is not r0001 and says so.

## For developers

You need your own r0001 disc to build the game; without it you can still build and test the runtime, the tools, the
launcher and the Python harness (that is what CI does). The short version, on Windows in Git Bash with the portable
toolchain on the `PATH` and the ISO under `game/`:

```
./build.sh recomp      # build the merged ELF from the disc and run the recompiler
./build.sh runtime     # cmake + ninja + clang -> dist/socom2.exe and the launcher
./build.sh test        # the C++ suite and the VU1 replay goldens
python -m unittest discover -s tools_py/tests -t .   # the Python suite
python -m tools_py.parity.gate --stamp first_run     # the in-game gate, about 15 minutes
```

`docs/DEVELOPING.md` is the full developer reference: repository layout, the first hour on a clean checkout with the
lines that say each step worked, every runtime knob (`PS2X_*`) and its exact effect, the online harness, and the
launcher internals. `CONTRIBUTING.md` says what a pull request needs; `docs/GIT_STRATEGY.md` how branches are cut.

### How it works, in one paragraph

The retail ELF is only a loader; the game itself is two encrypted overlays the loader decrypts from the disc. The
tooling under `tools_py/` recovers the plaintext overlays from the player's disc, merges them with the loader into one
ELF, and hands that to a vendored fork of [PS2Recomp](https://github.com/ran-j/PS2Recomp) (`third_party/ps2recomp`)
which emits C++. The fork's runtime supplies the PS2 the code expects; SOCOM's own quirks live in
`third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` (EE side) and
`third_party/ps2recomp/ps2xIOP/src/modules/` (IOP services: sound, network, memory cards). The server under `server/`
is Horizon configured for SOCOM II's app id, with a seed script for a local instance.

### Where things are

| Path | What |
|---|---|
| `build.sh`, `run.sh` | Build and run on Windows (Git Bash); `scripts/build_linux.sh` on Linux |
| `recomp/` | Recompiler configuration and the function map |
| `third_party/ps2recomp/` | The vendored PS2Recomp fork with this project's runtime changes (`git log -- third_party`) |
| `tools_py/` | Python tooling: the overlay decryptor, ELF builder, the parity gate and the online harness, tests |
| `ghidra_scripts/` | Headless Ghidra scripts used for the reverse engineering |
| `server/` | Horizon Private Server sources and the SOCOM II configuration |
| `docs/` | `HANDOFF.md` (start here), `KNOWN.md`, `STATUS.md`, `CURRENT_SPRINT.md`, `HUMAN_TASKS.md`, the research notes under `docs/research/`, and each sprint's spec and plan under `docs/superpowers/` |
| `tests/` | Fixtures for the C++ suite |

### How it was built

Most of this repository was produced by AI agents (Claude, through Claude Code) working in sprints under a human
owner: specs and plans in `docs/superpowers/`, numbered rulings, a "known / believed / retracted" ledger, and a gate
that has to go green before a sprint closes. `docs/STORY.md` tells that story with its evidence; the sprint plans are
kept as written, which is why they read like working notes rather than documentation.

## Contributing and security

Issues and pull requests are welcome -- see `CONTRIBUTING.md` for what can be built without a disc and what a PR must
not contain. Security problems go through GitHub's private vulnerability reporting, not a public issue: `SECURITY.md`.

## License and credits

The port -- the runtime fork and everything that generates or drives it -- is **GPL-3.0**, because PS2Recomp is
(`third_party/ps2recomp/LICENSE`). The Horizon server is MIT (`server/horizon-server/LICENSE`). No game data is
distributed and none is licensed here; SOCOM II remains the property of its rights holders.

Built on [PS2Recomp](https://github.com/ran-j/PS2Recomp) and
[Horizon Private Server](https://github.com/Horizon-Private-Server/horizon-server), with
[Ziemas's 989snd decompilation](https://github.com/Ziemas/989snd) as the reference for the sound driver, and the
knowledge the SOCOM community has kept alive for twenty years.
