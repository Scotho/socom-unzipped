# SOCOM Unzipped — SOCOM II: U.S. Navy SEALs, statically recompiled for PC

Goal: a `socom2.exe` that runs the US retail game (SCUS_972.75, r0001) natively on modern
Windows without a PS2 emulator, with controller support and online play against a server we
host, structured so it can be extended later. The user supplies their own disc image.

**Start here if you are a new agent:** read the "Current state" section at the top of
`docs/STATUS.md` (what works, what is next, how to resume), then the design and the task list:
`docs/superpowers/specs/2026-09-04-socom2-pc-recompilation-design.md` +
`docs/superpowers/plans/2026-09-04-implementation-plan.md` for the project as a whole, and
`docs/superpowers/specs/2026-09-11-sprint-2-host-render-and-family-b-design.md` +
`docs/superpowers/plans/2026-09-11-sprint-2-host-render-and-family-b.md` for the current
sprint (previous: `docs/superpowers/specs/2026-09-10-sprint-1-hygiene-and-native-render-design.md`
+ `docs/superpowers/plans/2026-09-10-sprint-1-hygiene-and-native-render.md`).
`docs/research/` holds the reverse-engineering and research write-ups.

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
| `build.sh`, `run.sh` | Build (`tools`, `recomp`, `runtime`, `test`, `all`) and run (`./run.sh <seconds>`) — Git Bash |
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
./build.sh test        # ps2x_tests + vu1_replay (builds both, copies vu1_replay to dist/) and
                       # replays the VU1 fixtures against their goldens, native path on and off,
                       # plus a --vram-diff equivalence check; PS2X_TEST_REPEAT=N runs the unit
                       # suite N times (determinism check)
python -m tools_py.parity.gate   # in-game gate: title / transition / mission, PASS or FAIL.
                       # Run `./build.sh runtime` first -- the gate launches dist/socom2.exe and
                       # `./build.sh test` does NOT rebuild it.
PS2X_PC_SAMPLER=5 ./run.sh 40    # run 40 s; logs/latest.log; prints guest thread PCs every 5 s
```
Knobs: `PS2X_VU1_HOST_DRAW=1` draws the native VU1 dispatcher's triangles through
`GS::submitHostTriangle` in host space instead of building/kicking a GIF packet (default off, GIF
path unchanged); `PS2X_VU1_NATIVE=0` reverts the dispatcher to the generated/interpreted VU1 path;
`PS2X_TEST_REPEAT=N` (above) repeats the unit suite for a determinism check.
`PS2X_VU1_NATIVE_TEST_CEILING=<n>` / `PS2X_VU1_NATIVE_TEST_CLIP_CEILING=<n>` lower the native
dispatcher's per-handler vertex/triangle and clipped-vertex ceilings so `build.sh test` can reach
the refusal path on the normal fixtures -- test-only, never set them for a real run. `vu1_replay
--vram-diff <outdir> [--vram-tol <pct>]` proves the host-draw and GIF paths render the same
pixels offline; `vu1_replay --no-native` forces the interpreted path for comparison.
`PS2X_PRESENT_FILTER=linear|integer|point` picks how the PS2 frame is stretched to the window:
`linear` (default) is the single aspect-fit draw with the render target's own linear sampling,
`point` samples it nearest straight to the window, and `integer` point-samples it into an
off-screen stage at floor(fit scale) times its size first and then fits that stage with linear
filtering. Presentation only -- it changes no rendering, and the title gate is green in all three.
The desktop window opens at 640x448, the frame the menus present, so at the default size the fit
scale is 1.0 and all three modes are the same 1:1 blit; the knob bites on a resized window (or the
960x544 Vita build). `python -m tools_py.parity.resize_window <w> <h>` resizes a running instance
for that comparison -- captures only, the title gate cannot score a pillarboxed window. See the
2026-09-12 entry in `docs/STATUS.md`.
`PS2X_GS_SCALE=1..4` (GL backend only, default 1) is the integer render-target scale: every
render target's GL texture is allocated at that multiple of its native GS extent and every draw
rasterises into it at that scale, so geometry is sharper while VRAM addressing, page/row
bookkeeping and every byte the guest can read back stay native. Anything the guest can observe --
the two VRAM downloads, a render target sampled as a texture, the display dump, the frame capture
-- goes through a native-sized mirror first, and `PS2X_GS_SCALE_FILTER=point|box` picks how that
mirror is produced (`point`, the default, is a `GL_NEAREST` blit; `box` averages the SxS host
texels behind each native pixel). Two consequences worth knowing: textures are still decoded at
native resolution, so an RT sampled as a texture (the full-screen display copies) gains no detail
from the scale; and an image upload into a render target only ever carries native pixels, so it
destroys the sub-native detail in the rows it covers (the movie path re-uploads a full frame every
frame). Memory cost is S^2 per colour and depth target. `PS2X_GS_SCALE_SELFTEST=1` checks, on
every native-view read, that the mirror is not stale by a batch and that each native pixel lies
inside its host block -- diagnostics only. The CPU backend (`PS2X_GS_BACKEND=cpu`, which
`build.sh test` and `vu1_replay` force) ignores both knobs and always rasterises at 1x.
`socom2.exe` takes the ELF path as argv[1]; it finds the `.iso` next to the ELF or one level up
(`game/`) or via `PS2X_CD_IMAGE`; memory cards live in `game/disc/mc0`.
PCSX2 reference: `tools/pcsx2/pcsx2-qt.exe -batch -nogui -fastboot -logfile <log> "<iso>"`.

## License
The port (runtime fork + generated code) is GPL-3.0 because of PS2Recomp. No game data is
distributed. Horizon server is MIT.
