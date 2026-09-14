# Autonomous loop prompt (SOCOM II PC) — fired every 30 minutes by the session cron

You are continuing the SOCOM II PC static-recompilation project at C:/projects/socom_pc
autonomously. The user (Craig) is away and has given full authority to use best judgement;
plans are suggestions.

Ordered goals (user, 2026-09-11; restated 2026-09-13 at Sprint 4 close-out). **The sprint in flight,
its branch, spec, plan and ledger are named in `docs/CURRENT_SPRINT.md`** — read it first; this file
carries no sprint pointer of its own. Follow that plan's task order. Sprints 1-4 are history: the `2026-09-10-sprint-1-…`,
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
     0 % of rows inside any contact gate — ~~and **no kill** has been observed~~. **Superseded 2026-09-13 — the acceptance test PASSED** (Sprint 5 ladder launch 2, `logs/parity/s5_t5_ladder2`: rounds 1–3 KILL on both scorers, independently verified; `docs/research/22-kill-readout.md` §Ladder launch 2, `docs/research/assets/22-first-kill.png`).
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
   `./build.sh runtime` MUST precede the gate when the runtime changed: the gate launches
   `dist/socom2.exe`, and `./build.sh test` does not rebuild it. `./build.sh test` runs the Python
   tests first (`python -m unittest discover -s tools_py/tests -t .`; unittest only, no pytest —
   `tools_py/tests/test_test_hygiene.py` fails on a test file that line would not find).
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
1. `bash scripts/loop_lock.sh check`. If the lock is HELD (a live heartbeat — see "Lock protocol"),
   or a `socom2*.exe`/`pcsx2-qt.exe` is running, do NOT start a build or a run: only one game
   instance and no builds during runs. **Do not idle waiting for it** — pick the next lock-free
   step of the plan (decomp reading, pure scorers and their tests, analysis of logs already on
   disk, docs) and do that this firing.
2. Read `docs/KNOWN.md` (the live proven / believed / retracted list — it is the fastest way to
   avoid re-deriving a dead hypothesis, and its §3 is what the other docs used to state as fact),
   then `docs/CURRENT_SPRINT.md`, `docs/HANDOFF.md` "START HERE" and the newest `docs/STATUS.md`
   entries; `git log -5`.
3. Pick the next task in the plan `docs/CURRENT_SPRINT.md` names, which serves goal 1 (goals 2 and 3
   are constraints, goal 4 is maintenance). Work in bounded steps, in this order (builds and runs
   under the lock, through `run` / `run_detached.sh`): one hypothesis -> one build -> one run ->
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
   runtime and game runs are SERIAL: they run under the loop lock (see "Lock protocol").
5. Commit from the repo root C:\projects\socom_pc (its own git repo, remote
   github.com/Scotho/socom-unzipped; never `git add -A`; leave `server/config/simulated.db`
   unstaged), then `git push`. **Commit with an explicit pathspec — `git commit -m "…" -- <paths>`,**
   never a bare `git commit` after `git add`: several agents share this working tree, and a bare
   commit takes the whole index (it swept another agent's files under the wrong message on
   2026-09-13). Trailers and every other commit rule: the current plan's "Commit conventions"
   (handoff notes) and the attribution your session is given — do not copy a trailer from an older
   commit or doc.
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
The lock serializes every build and every game run (`scripts/loop_lock.sh`; its header is the
reference). **Never hold it across tool calls except through `run` or `run_detached.sh`** — a gap
between two tool calls is not renewed, and the calling shell dies when its tool call returns.
**Mixed versions:** a job started under an older `loop_lock.sh` (plain `logs/.loop_lock` file, or a
claim dir without the `logs/.loop_lock.mx` mutex) must finish before anything uses the current lock.
- Foreground: `bash scripts/loop_lock.sh run <owner> --purpose "<what>" [--wait 40] -- <cmd...>`
  takes the lock, renews its heartbeat every 60 s while `<cmd>` runs, releases on exit (also on
  failure) and returns `<cmd>`'s exit code; exit 75 = the lock was busy and `<cmd>` did not run.
  Wrap a build -> test -> gate sequence as ONE run, e.g.
  `bash scripts/loop_lock.sh run main --purpose "test+gate" -- bash -c './build.sh test && python -m tools_py.parity.gate'`
  (gate.py's own take/release are NESTED no-ops inside a run).
- Detached (game runs): `bash scripts/run_detached.sh --owner <owner> <script> <marker>` takes the
  lock, launches the script under nohup, renews every 5 min while the script's PID lives, releases
  and then writes `exit=<code>` to `<marker>`. The script must keep its work in the foreground (the
  lock lives as long as the script's PID). Poll the marker; run
  `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1` before every
  launch while you hold the lock (a finished drive.py taskkills the next run's game; it kills only
  driver modules and `socom2*.exe`, never lock-free scorers or its own callers).
- A lock is live while its **heartbeat** is fresh, not by how long ago it was taken. A take on a
  held lock reaps it only when the heartbeat is >= 15 min old **and** nothing on the busy list runs
  (games, PCSX2, cmake/ninja/clang/ld, ps2_recomp, ps2x_tests, vu1_replay, python running
  `tools_py.parity` or `unittest`); the 45-min stale break is refused while anything on that list
  runs. BUSY holds for the same owner too. `check` prints the holder, purpose and heartbeat age;
  reaps are logged to `logs/.loop_lock_history`. `take`/`renew`/`release`/`wait` still exist for old
  scripts; do not use them across tool calls.
- Offline analysis (python on logs already on disk) needs no lock. `vu1_replay.exe` and
  `python -m unittest` need none either, but they are on the busy list, so a long one delays a reap.
