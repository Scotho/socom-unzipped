# Autonomous loop prompt (SOCOM II PC) — fired every 30 minutes by the session cron

You are continuing the SOCOM II PC static-recompilation project at C:/projects/socom_pc
autonomously. The user (Craig) is away and has given full authority to use best judgement;
plans are suggestions.

Ordered goals (user, 2026-09-11, Sprint 2 — see
docs/superpowers/specs/2026-09-11-sprint-2-host-render-and-family-b-design.md and the plan in
docs/superpowers/plans/2026-09-11-sprint-2-host-render-and-family-b.md; Sprint 1 is history:
docs/superpowers/specs/2026-09-10-sprint-1-hygiene-and-native-render-design.md and
docs/superpowers/plans/2026-09-10-sprint-1-hygiene-and-native-render.md):

1. Hygiene: `./build.sh test` green, `python -m tools_py.parity.gate` green. Both are REQUIRED
   before any commit that touches third_party/ps2recomp/ or recomp/. A red gate is fixed first.
   `./build.sh runtime` MUST precede the gate: the gate launches `dist/socom2.exe`, and
   `./build.sh test` does not rebuild it -- Task 8 lost 25 minutes to a stale exe.
2. FROZEN: emulator speed work (VU1/VU0 interpreter, scheduler batching, GS/GL caching or upload
   performance). 36-42 fps single instance is enough for this sprint. The two-instance frame
   rate is a test-rig concern: run the second client of the acceptance test in PCSX2.
3. Native render path: the VU1 command dispatcher (entry pc 0x1b50 of image d418194495c25213)
   hand-written in third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/ now runs families A, B
   and C natively (123/166 lists across dump2/3/4, bit-exact `--regs all`); residual is one
   dump3 list using 0x34 (EFU maths + same-lane write conflict) and 42 dump3 lists using a
   fourth, unimplemented command family (0x70/0x52/0x66/0x40 -- Sprint 3 research). The native
   0x28 handler can also draw host-space triangles straight through `GS::submitHostTriangle`
   behind `PS2X_VU1_HOST_DRAW` (default off; the GIF path is unchanged and still what every
   golden verifies). Verified with `dist/vu1_replay.exe --verify --native` on
   tests/fixtures/vu1/title and tests/fixtures/vu1/dispatch_0x1b50, `--vram-diff` for the
   host-draw knob, and by the title gate.
4. The first-kill acceptance test (tools_py/parity/online_match_ours.py) continues unchanged.
Long term: N64-recomp model — game logic stays recompiled, renderer/audio/input/network native.

Acceptance for "playable" (user, 2026-09-09): visual accuracy of the game itself (not just the
shell) AND an automated test that drives a two-instance online match to its END by one player
shooting the other or killing them with a grenade (extend tools_py/parity/online_match_ours.py:
scripted movement/aim/fire, read the kill/round-end state from guest memory or the Horizon
world state, capture the screens). Expect many gameplay issues on the way; each is a bounded
hypothesis->build->run->evidence step.

## Every firing
1. If a game run or build is in progress (check `logs/.loop_lock` — a file with the owner and
   a start time under 20 minutes old — or a running `socom2*.exe`/`pcsx2-qt.exe`), do NOT start
   another; only one game instance and no builds during runs. Wait for the next firing.
2. Read `docs/HANDOFF.md` "START HERE" and the newest `docs/STATUS.md` entries; `git log -5`.
3. Pick the top open item that advances goal 1 or 3 (goal 2 is a constraint, goal 4 is
   untouched). Work in bounded steps, in this order: one hypothesis -> one build -> one run ->
   read the evidence -> `./build.sh test` and (after `./build.sh runtime`) `gate` green ->
   commit -> push -> STATUS entry (newest on top) -> refresh the "START HERE" section of
   HANDOFF.md when the pick-up changes. Tests and the gate come BEFORE the commit (goal 1).
4. Subagents are welcome for offline/static work (decomp reading, native VU1 handler work under
   third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/ verified with `dist/vu1_replay.exe
   --verify --native` on both fixture sets, server-side Horizon checks) but builds of the
   runtime and game runs are SERIAL: take `logs/.loop_lock` first.
5. Commit from the repo root C:\projects\socom_pc (its own git repo, remote
   github.com/Scotho/socom-unzipped; never `git add -A`; leave `server/config/simulated.db`
   unstaged), then `git push`; trailers
   `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: <url>`.
6. Never regress: title labels clean (s05/s06 of every run sheet), online reaches SELECT
   UNIVERSE, mission loads. A regression is fixed before moving on.

## Run recipes and gotchas
See docs/HANDOFF.md ("The run you will repeat", "Build", "Gotchas"). Key ones: `./build.sh
runtime` (3 min; header change = 10 min); `python -m tools_py.parity.drive --target ours
--script scripts/parity/<script> --out logs/parity/runs/<stamp> --seconds N`; montage with
`python -m tools_py.parity.montage <run> <sheet.png>` then Read the sheet; kill stray
`pcsx2-qt.exe` before drive.py; `PS2X_VU1_DUMP`/`PS2X_RDRAM_DUMP` need existing directories;
RDRAM dump paths must be Windows paths.

## Lock protocol
`scripts/loop_lock.sh take <owner>` before any `./build.sh`, `run.sh` or drive.py run (BUSY even for the same owner: a second job queues with `wait`); `renew <owner>` refreshes a held lock;
`scripts/loop_lock.sh release <owner>` after; `check` to inspect; `wait <owner> [minutes]` blocks
until it is free (stale after 45 min). Offline tools (vu1_replay, python analysis) need no lock.
