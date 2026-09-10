# SOCOM Unzipped — SOCOM II: U.S. Navy SEALs, statically recompiled for PC

Goal: a `socom2.exe` that runs the US retail game (SCUS_972.75, r0001) natively on modern
Windows without a PS2 emulator, with controller support and online play against a server we
host, structured so it can be extended later. The user supplies their own disc image.

**Start here if you are a new agent:** read `docs/STATUS.md` (what works, what is next, how
to resume), then `docs/superpowers/specs/2026-09-04-socom2-pc-recompilation-design.md` (the
design and milestones) and `docs/superpowers/plans/2026-09-04-implementation-plan.md` (the
task list). `docs/research/` holds the reverse-engineering and research write-ups.

## How it works (one paragraph)
The retail ELF is only a loader; the game is two Metrowerks overlays that the loader decrypts
from `RUN/RAW/APACHE00.ZDB` with libdnas2. We recovered the plaintext overlays once
(`tools_py/decrypt_apache.py`, Unicorn-driven), merged them with the loader into one ELF
(`game/overlays/socom2_game.elf`), and statically recompile that ELF to C++ with a vendored fork
of PS2Recomp (`third_party/ps2recomp`, GPL-3.0). The fork's runtime provides the EE kernel,
DMAC/VIF/GIF, a software GS, a VU1 interpreter and IOP services emulated at the SIF-RPC level.
SOCOM-specific behaviour lives in `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp`
(EE-side hooks) and `third_party/ps2recomp/ps2xIOP/src/modules/*.cpp` (IOP services). The
online server is Horizon Private Server configured for SOCOM II under `server/`.

## Layout
| Path | What |
|---|---|
| `build.sh`, `run.sh` | Build (`recomp`, `runtime`, `all`) and run (`./run.sh <seconds>`) — Git Bash |
| `recomp/` | Recompiler config (`socom2.toml`), Ghidra function map (`socom2_ghidra.csv`), forced entry points (`extra_functions.txt`), generated C++ in `output/` (ignored) |
| `third_party/ps2recomp/` | Vendored PS2Recomp fork (our changes are committed in place; see `git log -- third_party`) |
| `tools_py/` | Python tooling: Unicorn EE harness, APACHE00 decryptor, DNAS self-decryptor, ELF builder, Ghidra CSV fixers, screenshot helper |
| `ghidra_scripts/` | Headless Ghidra scripts (export, pointer/vtable scan, function forcing) |
| `server/` | Horizon Private Server sources+config for app id 10472, `start-servers.ps1`, README |
| `docs/` | Status, spec, plan, research |
| `game/` (ignored) | ISO, extracted disc tree, decrypted overlays, Ghidra decompilation exports |
| `tools/` (ignored) | Portable toolchain: llvm-mingw clang, CMake, Ninja, Ghidra 12.1 + EE extension, PCSX2 2.8.1 (+BIOS) |
| `ghidra_proj/` (ignored) | Ghidra project `socom` (programs: SCUS_972.75, DNAS.BIN/.dec.bin, socom2_game.elf, 989SND.IRX) |
| `dist/` (ignored) | `socom2.exe` + DLLs |

## Build and run (developer machine)
```
./build.sh recomp      # regenerate ELF, normalize the function map, run ps2_recomp (~10 s)
./build.sh runtime     # cmake+ninja, clang, LTO off (~15 min from scratch, ~3 min runtime-only)
PS2X_PC_SAMPLER=5 ./run.sh 40    # run 40 s; logs/latest.log; prints guest thread PCs every 5 s
```
`socom2.exe` takes the ELF path as argv[1]; it finds the `.iso` next to the ELF or one level up
(`game/`) or via `PS2X_CD_IMAGE`; memory cards live in `game/disc/mc0`.
PCSX2 reference: `tools/pcsx2/pcsx2-qt.exe -batch -nogui -fastboot -logfile <log> "<iso>"`.

## License
The port (runtime fork + generated code) is GPL-3.0 because of PS2Recomp. No game data is
distributed. Horizon server is MIT.
