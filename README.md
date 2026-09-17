# SOCOM Unzipped — SOCOM II: U.S. Navy SEALs, statically recompiled for PC

Goal: a `socom2.exe` that runs the US retail game (SCUS_972.75, r0001) natively on modern
Windows without a PS2 emulator, with controller support and online play against a server we
host, structured so it can be extended later. The user supplies their own disc image.

**Start here if you are a new agent:** read the "Current state" section at the top of
`docs/STATUS.md` (what works, what is next, how to resume), then the design and the task list:
`docs/superpowers/specs/2026-09-04-socom2-pc-recompilation-design.md` +
`docs/superpowers/plans/2026-09-04-implementation-plan.md` for the project as a whole, and
`docs/superpowers/specs/2026-09-11-sprint-3-render-scale-and-fourth-family-design.md` +
`docs/superpowers/plans/2026-09-11-sprint-3-render-scale-and-fourth-family.md` for the most
recent sprint (previous: the `2026-09-11-sprint-2-host-render-and-family-b` and
`2026-09-10-sprint-1-hygiene-and-native-render` spec/plan pairs in the same two directories).
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

## Run it (players)
`scripts/make_portable.sh` builds `dist/portable/socom2/` (and a zip) from a finished build: the game, its DLLs, the
launcher, a README and the licences, with empty `cards/` and `logs/`. In that folder, **run
`socom_unzipped_launcher.exe`**, point it at your SOCOM II ISO (NTSC r0001), pick video and controller settings, Launch.
Nothing is installed; delete the folder to uninstall.

## Build and run (developer machine)
```
./build.sh recomp      # regenerate ELF, normalize the function map, run ps2_recomp (~10 s)
./build.sh runtime     # cmake+ninja, clang, LTO off (~15 min from scratch, ~3 min runtime-only)
./build.sh test        # ps2x_tests + vu1_replay (builds both, copies vu1_replay to dist/) and
                       # replays the VU1 fixtures against their goldens, native path on and off,
                       # plus a --vram-diff equivalence check (checked=15 skipped=0; a
                       # [vu1_replay] WARNING about a texture inside the replay's blanked
                       # framebuffer/z region fails the suite); PS2X_TEST_REPEAT=N runs the
                       # unit suite N times (determinism check). It runs NO Python tests:
                       # python -m unittest discover -s tools_py/tests -t .   (by hand, for now)
python -m tools_py.parity.gate   # in-game gate: title / transition / mission, PASS or FAIL.
                       # Run `./build.sh runtime` first -- the gate launches dist/socom2.exe and
                       # `./build.sh test` does NOT rebuild it.
PS2X_PC_SAMPLER=5 ./run.sh 40    # run 40 s; logs/latest.log; prints guest thread PCs every 5 s
```
### Build, run, verify — a newcomer's first hour

Five commands, in this order, on a clean checkout with the tools under `tools/` on the PATH
(`export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"`) and the disc image at
`game/SOCOM II - U.S. Navy SEALs (USA).iso`. The expected lines are the ones to look for; the counts are as of
2026-09-17 and only ever grow.

| # | command | the line that says it worked |
|---|---|---|
| 1 | `./build.sh recomp` | `recomp: <n> files, unhandled=0` |
| 2 | `./build.sh runtime` | `built dist/socom2.exe` (the launcher lands beside it) |
| 3 | `./build.sh test` | `Total Tests: 500` / `Passed: 500` / `Failed: 0`, then `vu1_replay` with `checked=15 skipped=0` |
| 4 | `python -m unittest discover -s tools_py/tests -t .` | `Ran 1104 tests ...` / `OK (skipped=63)` |
| 5 | `python -m tools_py.parity.gate --stamp first_run` | `GATE PASS (3/3) -> logs\parity\gate\first_run` (about 15 min; the game window opens and closes three times; do not touch the keyboard) |

`python -m tools_py.parity.gate --baseline first_run` re-scores that saved run without launching, which is the
fastest way to check a scoring change. A gate refuses to start under 4 GB free on C: (`RUN_MIN_FREE_GB`) and
while another launch holds the loop lock (`scripts/loop_lock.sh status`). Anything else: `docs/STATUS.md` has the
day-by-day, `docs/KNOWN.md` what is proven and what is believed, `docs/HUMAN_TASKS.md` the checks only a person can do.

Knobs (the behaviour-changing ones documented in full below; this is not the complete list --
other behaviour-changing knobs exist under `getenv("PS2X_` in `third_party/ps2recomp/ps2xRuntime/`
without a full entry here, grouped roughly by area: GS (`PS2X_GS_NO_ZTEST`,
`PS2X_GS_NO_DIRTY_REFRESH`, `PS2X_GS_RT_TEXTURE`, `PS2X_GS_TEX_FROM_CPU`), VU
(`PS2X_VU1_XGKICK_CYCLE_EXACT`, `PS2X_VU1_XGKICK_IMMEDIATE`, `PS2X_VU0_FAST`,
`PS2X_VU1_FMAC_CHECK`), EE/GIF/VIF (`PS2X_EE_ROUND`, `PS2X_GIF_PRIORITY_SORT`,
`PS2X_VIF1_NO_IRQ_STALL`), build-time/IOP (`PS2X_ENABLE_DEBUG_UI`, `PS2X_IOP_ENABLE_PLUGINS`), and
paths/networking (`PS2X_MC_DIR`, `PS2X_DEFAULT_BOOT_ELF`, `PS2X_SOCOM2_SERVER`,
`PS2X_SOCOM2_HOSTS`, the `PS2X_SOCOM2_INPUT_*` family). Their exact effect is read at each knob's
`getenv` use site, not written up here:
`PS2X_VU1_HOST_DRAW=1` draws the native VU1 dispatcher's triangles through
`GS::submitHostTriangle` in host space instead of building/kicking a GIF packet (default off, GIF
path unchanged); `PS2X_VU1_NATIVE=0` reverts the dispatcher to the generated/interpreted VU1 path
(it runs 162 of the corpus's 166 lists natively, bit-exact; the residual 4 are documented in
`docs/research/15-vu1-fourth-family.md`); `PS2X_VU1_FAST=0` and `PS2X_VU1_GEN=0` drop to the exact
interpreter, which with `--no-native` is how `vu1_replay` goldens are made;
`PS2X_GS_BACKEND=cpu` picks the CPU rasteriser (anything else, including unset, is the GL backend;
`build.sh test` and `vu1_replay` force `cpu`); setting `PS2X_SOCOM2_PAD` (to any value) enables the
host input path the parity harness drives (keyboard: arrows/WASD/IJKL, Enter=START, Backspace=SELECT,
ZXCV=Square/Cross/Circle/Triangle, QE=L1/R1, 13=L2/R2, 24=L3/R3; **gamepad 0 -- an Xbox/XInput or DirectInput pad --
since 2026-09-16, OR-ed with the keyboard, sticks past a 15 % dead zone override the keyboard axes**; the start
banner names the pad or says `gamepad none`; **`PS2X_HOST_GAMEPAD=0` disables every host gamepad read** -- the gate and the
online launch scripts set it, because a plugged-in controller makes the game skip its controller-configuration screens
at boot), `PS2X_SOCOM2_MOUSE=1` adds mouse look; `PS2X_TEST_REPEAT=N` (above) repeats the unit suite for a
determinism check.
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
texels behind each native pixel). Any value other than the exact string `box` (including a typo,
or the variable unset) silently selects `point` -- there is no warning. Two consequences worth knowing: textures are still decoded at
native resolution, so an RT sampled as a texture (the full-screen display copies) gains no detail
from the scale; and an image upload into a render target only ever carries native pixels, so it
destroys the sub-native detail in the rows it covers (the movie path re-uploads a full frame every
frame). Memory cost is S^2 per colour and depth target. `PS2X_GS_SCALE_SELFTEST=1` checks, on
every native-view read, that the mirror is not stale by a batch and that each native pixel lies
inside its host block -- diagnostics only. The CPU backend (`PS2X_GS_BACKEND=cpu`, which
`build.sh test` and `vu1_replay` force) ignores both knobs and always rasterises at 1x.
The value is read once and clamped into 1..4, so anything out of range silently becomes the nearest
end. `S=2` is verified on both draw paths (gate stamps `s3d_2x_host` for host-draw; `s3d_2x_gif`
title + mission and `s3d_2x_gif_t2` transition for the GIF path) and sharpens geometry but **not**
the HUD, menus or title, which are textured quads drawn at native texel density; `S=3` and `S=4`
are admitted by the clamp and **untested** — at `S=4` a colour target is 67 MB and
`getDepthTarget`'s zero-fill is a 67 MB one-off per ZBP. See the 2026-09-12 Sprint 3 and Task 5
entries in `docs/STATUS.md`.
**Online (two instances on the local Horizon server).** `python -m tools_py.parity.online_match_ours`
drives instance A (host) and B (joiner) through login, lobby and a match; see
`docs/research/18-online-round-start.md` §3.6 and §4.9 for full recipes. Runtime knobs:
`PS2X_SOCOM2_NET_STATS` (default **on**) makes `sceInetInterfaceControl` code `0x200` return a real
RX byte count; `0` restores the old constant and **reproduces the online movement defect** (the
guest's ms-since-network-activity never resets, the multiplayer movement scale decays to 0 and the
local player cannot move) -- an opt-out kept so the fix can be A/B'd on one binary.
`PS2X_SOCOM2_NET_TRACE` (any value) enables the netcode trace, `PS2X_SOCOM2_NET_TRACE_PEERS=<n>`
sets how many datagrams are hex-dumped per direction (default 16), and `PS2X_SOCOM2_NET_TRACE_ALL`
(default off) hex-dumps **every** datagram rather than only ports below 10000 (the only way to
content-inspect the DME aux-UDP traffic). `PS2X_SOCOM2_UDP_SHIFT=<n>` shifts an instance's peer UDP
ports (instance B uses 2), and `PS2X_SOCOM2_RSA_KEY=b` gives an instance the second precomputed
RSA key pair so two exes on one host do not publish the same public key. `PS2X_RUN_LOG=<path>`
(read by `run.sh`) pins the log file, so a driver can tail the game's own `[peek]` rows. The
drivers pass instance-B-only variants: `PS2X_SOCOM2_NET_STATS_B=0` turns the `0x200` fix off for
B alone (one match carries both legs of an A/B), `PS2X_SOCOM2_RSA_KEY_B=b` gives B its own key.
`online_match_ours.py` flags added in Sprint 4: `--converge` (both instances walk toward each
other); `--until-kill` (implies `--converge`; runs until a kill or round end is observed, captures
both screens and prints one `RESULT` line naming the signal -- **`RESULT PASS` is reserved for a
kill**, a round that ends on its clock prints `ROUND-END (unattributed -- NOT a kill)` and exits
non-zero, and expiry of `--kill-timeout` (default 420 s) is a clean FAIL); `--engage`/`--engage-dy`
(true 3-D actor-to-actor range and height tolerance for contact), `--fight-seconds`, `--no-route`
(ignore the mined Medley corridor); `--map <name>` (default **`frostfire`**, the owner's test map
since 2026-09-13; the highlighted row is verified against a reference crop in
`scripts/parity/refs/map_<name>.png` before CROSS is pressed, and a map with no reference aborts)
and `--map-scan <n>` (with `--only A`: walk the map list n rows and capture each, which is how a new
reference crop is made); `--health-offset <byte offset from the actor base>` with
`--health-range lo:hi` arms the health watch -- unset, the health signal is off and the run says so,
and an armed watch that reads nothing fails the run. `docs/research/19` sources health at
`0x1044` (alive byte `0xF7A`). **Both are armed by default since Sprint 5 Task 2**
(`--health-offset 0x1044` / `--alive-offset 0xF7A`; `'none'` disarms either) -- a health death
counts only as a transition (the same actor address must read alive, `0 < v <= 1`, before a
dead-range read), so a first read of `0.0` or of uninitialised heap is not a kill
(`tools_py/tests/test_kill_watch.py`), and `PS2X_PEEK` must cover the offset or the run refuses to
launch rather than failing later with `reads=0`. Map references are committed for Frostfire and
Medley. **As of Sprint 5's close the acceptance test has PASSED**: a Frostfire ladder match ends in
a kill scored by two independent readers (KillWatch on the actor fields above, `verdict_replay.py`
on the round-state valves) -- see `docs/STATUS.md` and `docs/KNOWN.md`. Harness pieces:
`drive.py` scripts gain an `ifburst` step (fire a capture burst only if the preceding `ifref`
matched), and `python -m tools_py.parity.movie_blocks <dumpdir>` checks a `PS2X_GS_DUMP_DISPLAY`
capture for 16x16 blocks black on the GL target but present in shadow VRAM (limits:
`docs/research/16` §9.1.1; wired into no automation).

**Sprint 5 knobs and tools.**
`PS2X_HLE_STATS=1` prints, per bound HLE stub (`recomp/socom2.toml`),
its call count, distinct returns (saturating at 64) and first/last value, including zero-call stubs
-- a varying-but-wrong return still passes a distinct count, and tail-called stubs (a recompiled
`J` straight to a C++ function) undercount because they skip the dispatch table.
`PS2X_GS_DEPTH_LEGACY=1` restores the GL backend's pre-2026-09-15 depth mapping (`gl_Position.z =
z/2^32 * 2 - 1` under the default clip range), which rounds window depth to multiples of 128 GS z
units for every z below ~2^30 and so let a Z16S scene keep only ~512 distinct depths. The default
now carries integer GS z exactly into the `GL_DEPTH_COMPONENT32F` test: `glClipControl(GL_ZERO_TO_ONE)`
with z passed through when GL 4.5 / `ARB_clip_control` is available (logged as `[gs-gl] depth
mapping: clip-control`), else `gl_FragDepth` from the interpolated z (exact, no early-z). The
mapping is replicated on the CPU in `runtime/gs/gs_gl_depth.h` and pinned by the `GSGlDepth` unit
suite. It is a precision fix, **not** the Seeding Chaos water fix (`docs/research/27`).
`PS2X_GS_MAX_PENDING_FRAMES=<n>` (default **3**) bounds the GS command backlog: the EE waits at
`VBlankStart` while more than `n` guest frames are recorded ahead of the GL replay thread; `0`
restores unbounded back-pressure, the pre-fix backlog that let `m_pending` grow to gigabytes when the
replay thread fell behind (fixed as a correctness bug, `8281254`/`7448601`/`92d30f0`), but **not** the
pre-`R54` idle wait -- the idle-spin fix (`92d30f0`) stays in either way, so `0` is not a full A/B of
the pre-fix runtime. `PS2X_CYCLE_CLOCK=guest` makes
the idle wait account the remaining cycles itself instead of a host-clock deadline -- **this is not
an A/B of the pre-`R54` scheduler path**; the idle-spin fix (`92d30f0`) landed on the host-clock
path, and `guest` is an alternate accounting mode on top of it, untested as a toggle of the older
behaviour.
`PS2X_CLOCK_EXCLUDE=0` stops subtracting the host time VU1 runs and the render back-pressure wait report
(`ps2GuestClockExcludedNs`) from the guest clock, so timer T0 -- the game's frame dt -- follows wall time;
the default (1) is the 2026-09-08 behaviour, which ran an online round at two thirds speed (research/34
section 6: 195 ms of VU1 and 290 ms of back-pressure per second excluded). `PS2X_CLOCK_CAP_MS=<ms>` still
bounds a single gap (a stall must not become a 300 ms dt). `PS2X_CLOCK_TRACE=1` prints, once a second,
`gap_ms` / `excluded_ms` / `lost_ms` beside the cycle clock.
`PS2X_AUDIO_DUMP=<file.wav>` writes the 989snd mix (48 kHz stereo) as it is rendered -- bank sounds only until the
VAG streams land (research/32 section 5); a run the harness kills leaves the WAV header's sizes at zero, so read
the file by its length.
`PS2X_AUDIO_PCM_DUMP=<file>` writes the first 256 KiB the EE DMAs into the 989snd PCM ring (the title music), each
write as `{offset, bytes}` then the bytes, to check the ring's layout offline (research/32 section 7).
`online_match_ours.py` flags from the Sprint 5 engagement ladder (Amendment A): `--rounds N`
`PS2X_WINDOW_SIZE=<w>x<h>` opens the game window at that size and `PS2X_WINDOW_SIZE=fullscreen` borderless over
the desktop; unset keeps the 640x448 default the gate depends on.

**The launcher** (`dist/socom_unzipped_launcher.exe`, built by `./build.sh runtime` next to `socom2.exe`): one
window that owns `config.json` beside it and starts `socom2.exe socom2_game.elf` with the `PS2X_*` environment,
so nobody sets a variable by hand. Disc: the ISO path (Browse), verified by hashing `SCUS_972.75` out of the image
against the r0001 digest -- Launch stays off until it matches. Video: Native / Sharp (2x) / Sharper (3x, untested)
detail (`PS2X_GS_SCALE`), the presentation filter, 640x448 / 1280x896 / fullscreen. Controller: the pad raylib sees,
sticks and buttons live (the same calls the game's input poll makes), mouse look and its sensitivity. Online: server
address, profile (its own `cards/<profile>/`), and a second-instance checkbox (UDP shift 2, key b, `cards/<profile>_b`).
Launch writes `logs/run_<stamp>.log`; Copy diagnostics puts the last log and `config.json` under `diagnostics/`.
`--selftest` prints the verified disc and the environment and exits; `--launch-test [seconds]` starts the game the
way the button does and reports whether it is still running after that long.
(default 4) plays N rounds on one lobby success, re-finding the actor by vtable and re-arming the
move-path disarm window after each round or kill, with one `LADDER round=<n> …` line per round and
a `LADDER-SUMMARY`; `--route <file>` picks the waypoint route for `--endgame route`/`cooperative`
(default `tools_py/parity/routes/frostfire_v2.json` for `--map frostfire`, derived from collision
geometry in `docs/research/24`; the older 3c-derived `routes/frostfire.json` stays loadable); `--endgame
route` (the Amendment A default) has the stander wait at spawn while the mover follows the route,
closes into the contact band, aims with partial-`rx` pulses read from the actor matrix and fires,
teleport-checked throughout; `--endgame cooperative` adds victim strafe-oscillation and shooter
micro-strafing between bursts so each side keeps feeding the other's starvation counter;
`--mover {A,B}` (default A, the host) picks which side walks and shoots; `--auto-swap` swaps
`--mover` once on a `SWAP-MOVER` stop instead of ending the run; `--control-round` (implies
`--converge`) runs the clock round-end negative control -- nobody fires, both sides alternate
strafe legs until the round ends on its own clock, and `RESULT CONTROL-ROUND` requires
`total_mp_kills`, `aiteam_*` and the health word to stay unchanged. `--health-offset`/
`--alive-offset` default to `0x1044`/`0xF7A` as covered above.
Loop lock: `LOOP_LOCK_PATH` overrides the lock's base path (tests use it to avoid touching the real
lock). `tools_py/tests/test_loop_lock.py` runs by default as a smoke of 7 lock tests (claim, renew,
release, one reap, one quiet-marker check, and -- Ruling R73 -- one reaper race of 4 takers x 2 rounds
with 0-0.3 s of process-list latency plus one stale-mutex double-entry check), ~25 s measured under
host load (the race alone ~8-9 s), plus a hygiene test that fails when `scripts/loop_lock.sh`'s git
blob differs from `tools_py/tests/fixtures/loop_lock_slow_green.txt`, the blob of the last green
`LOOP_LOCK_SLOW_TESTS=1` run. That variable runs the whole suite (~16 min: every race, interleaving,
`run`/`run_detached` test and the real-scale `run -- sleep 130` renewal). `scripts/run_detached.sh`
(launched with `--purpose launch*` for an online match) writes a quiet marker (`logs/.quiet`, keyed to
the Windows pid) that tells other agents to stay off `build.sh test`, the gate, `unittest` and
large-log parsing while a match runs; records a host CPU sampler into the run directory (nominally one
row per 1 s, measured one row per ~3.1 s on ladder launches 1b and 2); refuses to start below 4 GB free
on `C:`; and takes the loop lock for the job. `scripts/pin_harness.sh` archives `tools_py`/`scripts` at
a given commit into `<out_dir>/harness` and records `HARNESS_COMMIT`/`EXE_BUILD`; it does not run or
re-exec anything. The ladder template runs that snapshot with `PYTHONPATH=<snapshot>` plus
**`PYTHONSAFEPATH=1`** from the repo root, so a pinned run cannot accidentally import the live tree
instead (Python otherwise puts the current directory ahead of `PYTHONPATH`).
`scripts/parity/ladder_frostfire.sh --pinned <outdir>` is the ladder launch template: it pins the
harness, proves the snapshot imports, dry-runs first, then runs the pinned `online_match_ours.py
--rounds … --endgame route --route … --auto-swap` under `run_detached.sh` (which does the disk and
lock checks) and returns; nothing polls -- the caller watches `logs/<name>.done`. Killing stale
drivers (`scripts/kill_stale_drivers.ps1`), a running Horizon stack and persona B are preconditions the
caller meets, not steps the template takes; its header carries the exit codes and knobs. `tools_py/parity/verdict_replay.py <run_A.log> <run_B.log> [--per-round]` is
the second, independent kill scorer (primary signal: the round-state valves -- `total_mp_kills`,
`aiteam_*`, the clock -- corroborated by the actor fields), test-driven against synthetic and real
fixtures per spec §5.1.1, and importing nothing from `online_match_ours.py` or `verdict_core.py` by
design, so a parser bug in one cannot hide behind agreement with the other. `tools_py/parity/
verdict_core.py` holds the pure, IO-free scorers (`score-control`, `move-path`, `contact`,
`starvation`) both the harness's own preconditions and Task 1's launch-1 scoring share, with a CLI
for offline replay of any stored log pair.
`socom2.exe` takes the ELF path as argv[1]; it finds the `.iso` next to the ELF or one level up
(`game/`) or via `PS2X_CD_IMAGE`; memory cards live in `game/disc/mc0`.
PCSX2 reference: `tools/pcsx2/pcsx2-qt.exe -batch -nogui -fastboot -logfile <log> "<iso>"`.

## License
The port (runtime fork + generated code) is GPL-3.0 because of PS2Recomp. No game data is
distributed. Horizon server is MIT.
