# Autonomous loop prompt (SOCOM II PC) — fired every 30 minutes by the session cron

You are continuing the SOCOM II PC static-recompilation project at C:/projects/socom_pc
autonomously. The user (Craig) is away and has given full authority to use best judgement;
plans are suggestions.

Ordered goals (user, 2026-09-11; restated 2026-09-13 at Sprint 4 close-out). **The sprint in flight
is Sprint 5** — `docs/superpowers/specs/2026-09-13-sprint-5-control-readout-and-first-kill-design.md`
and the plan `docs/superpowers/plans/2026-09-13-sprint-5-control-readout-and-first-kill.md` (commit
`ee10842`; branch `sprint-5` off `develop` once `sprint-4` is merged). Follow the plan's task order,
starting at its Task 0 (preconditions — which also replaces this pointer with
`docs/CURRENT_SPRINT.md`). Sprints 1-4 are history: the `2026-09-10-sprint-1-…`,
`2026-09-11-sprint-2-…`, `2026-09-11-sprint-3-…` and `2026-09-12-sprint-4-visible-defects-and-first-kill`
spec/plan pairs in the same two directories; Sprint 4's plan ends with an `## Outcome` section.

1. **The first-kill acceptance test** (`tools_py/parity/online_match_ours.py --until-kill`). This is
   the active goal, and it is NOT untouched: Sprint 4 built it and it has not passed. State at
   2026-09-13 (`docs/STATUS.md` "Sprint 4 landed", `docs/research/18` §4, `docs/KNOWN.md`):
   - Two instances on local Horizon reach gameplay (~4 launches in 10) and **the round runs**.
     Never write "frozen at round start" — that was retracted; the true sentence is "the round runs
     and the local player cannot move", and it has had two causes on two maps.
   - **Medley:** the movement blocker is fixed (`sceInetInterfaceControl(0x200)` returned a
     constant; same-binary A/B). Both players walk and have met — closest **50.0 units true 3-D**,
     0 % of rows inside any contact gate — and **no kill** has been observed.
   - **Frostfire, the default test map (owner, 2026-09-13):** neither player moves; the move path
     runs 18 calls in 0.6 s at round start and never again. Lead: uninitialised `CZNetGame` bytes
     (`*0x437ce8`) read `0xAF` on ours and `0x00` on the console, including the "you are a ghost"
     flag `+0xd2` (`docs/research/19` F3). Divergence measured, causation not.
   - **Kill readout:** health `actor+0x1044` (float, `<= 0` dead) and alive byte `actor+0xF7A`
     (`docs/research/19` F1), never yet read live online; `actor+0x204/+0x208` are retracted.
     `RESULT PASS` is reserved for a kill, so it cannot print today; a round ending on its clock
     prints `ROUND-END (unattributed -- NOT a kill)` and exits non-zero.
2. Hygiene: `./build.sh test` green, `python -m tools_py.parity.gate` green. Both are REQUIRED
   before any commit that touches third_party/ps2recomp/ or recomp/. A red gate is fixed first.
   `./build.sh runtime` MUST precede the gate: the gate launches `dist/socom2.exe`, and
   `./build.sh test` does not rebuild it. `./build.sh test` runs **no Python tests** until Sprint 5
   Task 0 wires `tools_py/tests` in — run them by hand after touching `tools_py/`.
3. FROZEN: emulator speed work (VU1/VU0 interpreter, scheduler batching, GS/GL caching or upload
   performance). 36-42 fps single instance is enough; two of our instances run a match at 19-21
   each, which the harness tolerates. A mixed match (ours against PCSX2) is Sprint 6, not now.
4. Native render path — **maintained, not open work**. The VU1 command dispatcher (entry pc 0x1b50
   of image d418194495c25213, `third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/`) runs 162/166
   lists natively, bit-exact `--regs all`; the residual 4 (`52 66 08 40 42`) are a documented ruling
   (`docs/research/15`). `PS2X_VU1_HOST_DRAW` (default off) and `PS2X_GS_SCALE=1..4` (default 1; S=2
   sharpens 3D only, not HUD/menus/title) are unchanged since Sprint 3. Any change here is verified
   with `dist/vu1_replay.exe --verify --native` on tests/fixtures/vu1/title and
   tests/fixtures/vu1/dispatch_0x1b50, `--vram-diff` (**checked=15 skipped=0** since Sprint 4, with
   the seam clause budgeted so a one-pixel offset still fails), and the gates.
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
2. Read `docs/KNOWN.md` (the live proven / believed / retracted list — it is the fastest way to
   avoid re-deriving a dead hypothesis, and its §3 is what the other docs used to state as fact),
   then `docs/HANDOFF.md` "START HERE" and the newest `docs/STATUS.md` entries; `git log -5`.
3. Pick the next task in the Sprint 5 plan, which serves goal 1 (goals 2 and 3 are constraints,
   goal 4 is maintenance). Work in bounded steps, in this order: one hypothesis -> one build -> one run ->
   read the evidence -> `./build.sh test` and (after `./build.sh runtime`) `gate` green ->
   commit -> push -> STATUS entry (newest on top) -> **audit `docs/KNOWN.md`: promote, retire or
   retract the entries this step touched** -> refresh the "START HERE" section of
   HANDOFF.md when the pick-up changes. Tests and the gate come BEFORE the commit (goal 2).
   **If you find a committed sentence is false, correct it in the same hour, where it is written**
   (a `> Superseded by …` blockquote, never a silent delete) — do not queue it for a close-out that
   may never arrive. `docs/process-audit.md` has the rule and the two weeks it cost.
4. Subagents are welcome for offline/static work (decomp reading, native VU1 handler work under
   third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/ verified with `dist/vu1_replay.exe
   --verify --native` on both fixture sets, server-side Horizon checks) but builds of the
   runtime and game runs are SERIAL: take `logs/.loop_lock` first.
5. Commit from the repo root C:\projects\socom_pc (its own git repo, remote
   github.com/Scotho/socom-unzipped; never `git add -A`; leave `server/config/simulated.db`
   unstaged), then `git push`. **Commit with an explicit pathspec — `git commit -m "…" -- <paths>`,**
   never a bare `git commit` after `git add`: several agents share this working tree, and a bare
   commit takes the whole index (it swept another agent's files under the wrong message on
   2026-09-13). Trailers: follow the Sprint 5 plan's commit conventions and the attribution your
   session is given — do not copy a trailer from an older commit or doc.
6. Never regress: title labels clean (s05/s06 of every run sheet), online reaches SELECT
   UNIVERSE, mission loads, and on Medley the online local player moves (`research/18` §3.12a is
   the regression recipe). A regression is fixed before moving on.

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
