# Sprint 5 — Control on the Test Map, a Kill Readout from Sourced Offsets, and the First Kill: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Settle why nobody moves on Frostfire (the uninitialised ghost flag first), confirm the sourced health/life fields in one single-player run, make the online harness unable to spend a match on an uncontrollable or hung player, then climb the engagement from contact to damage to a kill attributed by signals from different objects and processes.

**Architecture:** Zero-run work first wherever the answer may already be on disk (the object-keyed heap diff, the valve map, the at-rest facing check), a knob built before the first launch so the decisive A/B needs no build, then capped launches with decision tables. The acceptance verdict is split across the actor object and the round-state object, on both instances, read by two scorers with different primary signals.

**Tech Stack:** C++20 (llvm-mingw clang via `build.sh`), Python 3 (`unittest`, numpy, Pillow), the local Horizon server, PCSX2 as the console reference, Ghidra decomp `game/analysis/socom2_game.elf.decomp.c`, reCOM (`tools/reference/reCOM`, SOCOM 1), Git Bash + PowerShell.

**Spec:** `docs/superpowers/specs/2026-09-13-sprint-5-control-readout-and-first-kill-design.md`. **Required reading for every dispatch:** `docs/KNOWN.md`, `docs/research/19-community-and-engine-resources.md` (F1–F5), `docs/research/18-online-round-start.md` §3.9–§3.12 and §4.12–§4.13, `docs/research/11-recom-applicability.md` §1 "zNetwork".

## Handoff notes for the executing model (read once)

Sprint 4's lessons, each paid for with a run, a review round or a false sentence in a tracked file.

- **Process.** superpowers:subagent-driven-development; fresh implementer per task (Opus for guest tracing, runtime and harness design; Sonnet for tests and docs; Haiku for trivial re-reviews); a task review after each; whole-branch review; the controller merges. Ledger at `.superpowers/sdd/2026-09-13-sprint-5-control-readout-and-first-kill/progress.md`. Decisions on the owner's behalf are `Ruling: … — why — cost if wrong`.
- **`docs/KNOWN.md` has one writer: the controller.** Implementers propose edits in their report. Retractions happen on discovery, in the same hour; close-out only verifies.
- **Name the relevant research notes in every dispatch.** `research/11` named the round-state machine and sat unread for six days.
- **Reviews re-derive.** The review brief requires a "reproduced independently" section; "I read the diff" is not a review.
- **Every numeric bar names a class it does not separate** — and check the bar against the *units and sampling* of the measurement it cites. This plan's first draft applied a per-1 s-sample figure to a 2 s hold at 4 Hz and would have passed ~8 units/s of drift.
- **Measure before fixing; a condition sentence before any fix; two fix attempts maximum.** A count that matches is not a mechanism.
- **Cite item names, functions and dated entries, never `file:NN`.** Mark superseded measurements where they are written.
- **Instruments.**
  - `PS2X_CALL_TRACE_EVERY` is **one global setting** (default **500**): the first 300 calls of each slot log unconditionally, then 1 in `EVERY` for **every** slot. Count calls from `#n` indices, never from line counts. At the default, a ~19/s slot logs one call per ~26 s; at `EVERY=10` it logs ~1.9 calls/s, i.e. **~4 lines/s** (a flushed `[call]` and `[ret]` each).
  - `PS2X_CALL_TRACE_DUMP="<Name>:a<k>[+0xOFF][*[+0xOFF]]:<words>[,...]"` prints after the traced function **returns**; entries are comma-separated.
  - `PS2X_RDRAM_DUMP_AT="<path>:<Name>#<n>"` fires on the n-th call of a traced function, **not** at a time.
  - **Every instrument counts its rows and fails when empty**: trace slots, peek items, `object_diff.py`, `verdict_core.py` (`NO-DATA`), `PS2X_HLE_STATS` (prints zero-call stubs), `verdict_replay.py` (`NO-DATA`), `LADDER contact_rows=<n> rows_read=<n>`. `[call-trace] tracing <n> guest functions` is not evidence the right function was hooked. The idle-ms thunk is **`0x30cd80`**.
  - **`PS2X_PEEK` indices shift** when a chain does not resolve. Find the actor block by vtable `0x6691a0`; identify a valve by its **name-pointer word** (peek `*0x437ce8+<off>*:2`: word 0 is the name pointer, word 1 holds the value short at `+4`), never by position.
  - **Resolve every address through a pointer.** Community absolute addresses are PCSX2's; our valve pool is 0x20 lower.
  - Player actor `*0x408c58`; position words 7/8/9; health `+0x1044` (float), alive `+0xF7A` (byte, in the word at `+0xF78`); camera record `0x416054` orbits at ground radius 20.65, 19.73 above. Round state `*0x437ce8`; clock string `0x408f10`.
  - The pad file accepts 0–255 per axis; `PAD_AXIS` full deflection is a harness choice. `PS2X_SOCOM2_INPUT_SCRIPT` is timed from boot and drifts — use the file.
- **Run name → per-instance logs** (`logs/` is git-ignored; run dirs hold only PNGs): `kill1` = `logs/run_[AB]_20260912_230022.log`, `kill2` = `run_[AB]_20260912_231341`, `kill3` = `run_[AB]_20260912_232834`, `frost1` = `run_[AB]_20260913_004754` (each confirmed by the drive log's liveness row count — Task 0 preflight). `PS2X_PEEK` caps every item at **64 words** silently; split longer items. `0x45a0c0:1` is the word holding `DAT_0045a0c1` as its byte 1.
- **Harness hazards.** Liveness is non-zero **and** distinct **and** responds to a hold **and** the displacement holds after release. A finished `drive.py` taskkills the next run's game — run `scripts/kill_stale_drivers.ps1` (Task 0) before every launch. `MediusPlayerReport` is not a round end; `respawn` is not a kill. **Starvation is two-sided.** Each side's own movement (`lx`, `ly`, `rx`; only pitch escapes) is multiplied by its scale, but what **restores** a side's scale is received bytes — i.e. the **other** side moving. ~~A side that stands still to aim starves its partner.~~ *(Contradicted 2026-09-13 — 3c ~48 s mutual standing at f12 = 1.0; Amendment A.)* When one side alarms, the *other* side moves. The lobby reaches gameplay ~4 in 10 and failures cluster. Efficiency is team-level. The simulation is wall-clock timed and can manufacture regressions (fixed-name temp files, walls that let strafes through) — check the harness before the code under test.
- **HLE signature test (no run):** identical across our images, different on the console's = our surface. It now covers **uninitialised heap memory** (`0xAF` vs `0x00`), and address-keyed diffs miss heap objects — key by object (static → block → field).
- **reCOM and community tools are SOCOM 1 or PCSX2-layout.** Documented is believed, not proven.
- **Commit conventions.** `git commit -- <paths>` with an explicit pathspec (a bare commit after `git add` swept another agent's files into `872d8d6`). Never `git add -A`. `server/config/simulated.db` unstaged; `ONBOARDING.md` untracked. Push after each commit. Trailer `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` only. Research tasks do not commit; the controller commits notes.
- **Standing rulings.** Branch in the main checkout, never a worktree (a junction once deleted `game/` and `tools/`). The loop lock around every build and every game run, **held only through `scripts/loop_lock.sh run <owner> -- <cmd>` (foreground) or `scripts/run_detached.sh` (detached)**, both of which renew the heartbeat — never `take` in one tool call and work in the next (a gap between tool calls is not renewed). Wrap a build → test → gate sequence as one `run` of a script. `index.lock` → wait 10 s, retry.

## Global Constraints

- Branch `sprint-5` off `develop` after the controller merges `sprint-4`, and not while `git status --short -- tools_py/parity/online_match_ours.py tools_py/parity/sim_walk_to_b.py tools_py/parity/online_login_ours.py docs/research/18-online-round-start.md` is non-empty.
- Defaults do not move (`PS2X_GS_SCALE=1`, `PS2X_GS_SCALE_FILTER=point`, `PS2X_PRESENT_FILTER=linear`, host-draw off, native VU1 on); the zero-fill knob ships **off**.
- `./build.sh test` exit 0 and the gate green before any commit touching `third_party/ps2recomp/`, `recomp/`, `tools_py/parity/{drive,gate,compare}.py`, `scripts/parity/` or `build.sh`. Harness-only commits to `online_match_ours.py`/`online_login_ours.py`/`sim_walk_to_b.py` need `build.sh test` and the simulation.
- `./build.sh runtime` before any run on a changed runtime; batch header changes (~10 min rebuild).
- Game runs detached (`Start-Process -FilePath "C:\Program Files\Git\usr\bin\bash.exe" -ArgumentList "<script>"`, or `nohup bash <script> &`), polled through a `.done` marker, the lock renewed by the script. Copy every cited run's exact command into the task's note.
- **No patches to recompiled game logic, no community code patches, no guest-memory writes in any acceptance path.** Speed work frozen. Do not resize the game window. LF line endings.

---

## File map

| Path | Responsibility |
|---|---|
| `scripts/loop_lock.sh`, `tools_py/tests/test_loop_lock.py` | Task 0: heartbeat lock, reaper, refused stale break, atomic claim |
| `scripts/run_detached.sh` (new), `scripts/kill_stale_drivers.ps1` (new) | Task 0: detached runs that renew the lock; kill stale `tools_py.parity` drivers and games |
| `build.sh` (`test_step`); `tools_py/tests/test_test_hygiene.py` (new); three tests moved from `tools_py/parity/` | Task 0 |
| `docs/CURRENT_SPRINT.md` (new), `docs/LOOP_PROMPT.md`, `docs/HANDOFF.md` "START HERE" | Task 0 |
| `tools_py/parity/object_diff.py` (new) | Task 4 leg 0: object-keyed field diff across RDRAM images and peek logs (supersedes the planned `actor_diff.py`) |
| `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp` (`PS2Runtime::guestMalloc` and the growth path of `PS2Runtime::guestRealloc` — these back the **bound** `_malloc_r`/`_memalign_r`/`_realloc_r` in `Kernel/Stubs/Compatibility.cpp`; `LibC.cpp`'s `memalign` is not bound); `tools_py/parity/online_login_ours.py` (`PS2X_GUEST_MALLOC_ZERO_B` per-instance mapping) | Task 1: `PS2X_GUEST_MALLOC_ZERO=1` (default off) |
| `docs/research/21-frostfire-control-handover.md` (new) | Task 1 |
| `tools_py/parity/sp_death_probe.py` (new), `scripts/parity/gameplay_death.txt` (new) | Task 2 |
| `docs/research/22-kill-readout.md` (new) | Tasks 2, 5, 6 |
| `tools_py/parity/online_match_ours.py`, `online_login_ours.py`, `winshot.py` | Tasks 3, 5, 6 |
| `tools_py/parity/verdict_core.py` (new, pure scorers), `tools_py/tests/test_online_verdict.py`, `tools_py/tests/fixtures/online/` | Task 3 |
| `tools_py/parity/sim_walk_to_b.py` | Tasks 3, 5: `nocontrol`, starvation model, `endgame` |
| `tools_py/parity/verdict_replay.py`, `tools_py/tests/test_verdict_replay.py` | Task 6 |
| `tools_py/hle_constants.py` (new), `docs/research/20-hle-liveness.md` (new), the stub dispatch point in `Kernel/` (locate from `recomp/socom2.toml`) | Task 4 |
| `docs/STATUS.md`, `README.md`, `docs/ROADMAP.md` §6, this plan | Task 7 |

---

### Task 0: Preconditions

No build, no game run. Steps 1–3 must land before Task 1's first launch.

**Files:** as in the file map (Task 0 rows).

**Interfaces:**
- Produces: `loop_lock.sh take|renew|release|check|wait|run` (existing verbs keep their CLI; `LOOP_LOCK_PATH` env override for tests); `loop_lock.sh run <owner> [--purpose <p>] -- <cmd…>` takes the lock, renews the heartbeat every 60 s from a background loop while `<cmd>` runs, releases on exit (including on failure) and returns `<cmd>`'s exit code; lock record `<owner> <epoch> <heartbeat_epoch> <purpose>`; `scripts/run_detached.sh <script> <marker>` (launches the script, renews the lock every 5 min while the script's PID lives, writes `<marker>` on exit with the exit code); `scripts/kill_stale_drivers.ps1` (kills `tools_py.parity` Python processes and `socom2*.exe`, prints what it killed); `docs/CURRENT_SPRINT.md` (`branch:`, `spec:`, `plan:`, `ledger:`).

- [x] **Step 1: Plan preflight (~20 min).** Execute or dry-run every lock-free command in this plan; resolve every function, address and path it cites (grep the decomp, `ls`); grep `docs/STATUS.md` and `docs/research/` for each procedural assumption; check every bar's blind class **and its units against the cited measurement**. Defects go to the ledger; the controller fixes the plan before Task 1 dispatches.
- [x] **Step 2: The lock.** Atomic claim (`mkdir "$LOCK.d"`). `renew` updates the heartbeat; `run` and `run_detached.sh` renew it automatically. **Busy list:** `socom2*.exe`, `pcsx2-qt.exe`, `cmake`, `ninja`, `clang*`, `ld*`, `ps2_recomp.exe`, `ps2x_tests.exe`, `vu1_replay.exe`, and any `python` whose command line contains `tools_py.parity` or `unittest` (`Get-CimInstance Win32_Process`). `take` on a held lock **reaps** only when the heartbeat is ≥ 15 min old **and** the busy list is empty, appending the reaped record to `logs/.loop_lock_history`. The stale break keeps its 45 minutes but its clock is the **heartbeat**, not take-time, and it is **refused** while anything on the busy list runs. `release` exits 1 if not the holder. **Do not key anything on the calling shell's PID** — it dies when the agent's tool call returns. Header comment: "never hold the lock across tool calls except through `run` or `run_detached.sh`".
- [x] **Step 3: Test the lock** with fakes (an env-injected process-list command, a back-dated heartbeat): stale heartbeat + empty busy list → reaped; stale heartbeat + a fake `ninja`, `vu1_replay.exe` or `python -m unittest` → BUSY; fresh heartbeat + nothing → BUSY; heartbeat 50 min old + a fake `socom2.exe` → stale break refused; `run -- sleep 130` with a 60 s renew keeps the heartbeat under 70 s old throughout and releases on exit; `run -- false` releases and exits 1; two racing `take`s → one `TAKEN`; non-holder `release` → exit 1. *Blind class:* a hung job whose wrapper keeps renewing is never reaped — the `.done` marker and log growth are the progress evidence.
- [x] **Step 4: `run_detached.sh` and `kill_stale_drivers.ps1`**, with the renew loop tied to the job PID, not the caller.
- [x] **Step 5: Python tests in `build.sh test`.** First command of `test_step`: `python -m unittest discover -s tools_py/tests -t . -v`. Move `test_compare.py`, `test_pine.py`, `test_winshot.py` into `tools_py/tests/` as `unittest.TestCase` (`skipUnless` for PCSX2/display). `test_test_hygiene.py` walks **`tools_py/` only** (the build trees under `research/ps2recomp/build/_deps/libdwarf-src/` carry their own `test_*.py`) and fails on a `test_*.py` outside `tools_py/tests/`, a `pytest` import, or a module-level `def test_`. Run `./build.sh test` once under the lock; record the Python test count.
- [x] **Step 6: The loop's aim.** `docs/CURRENT_SPRINT.md`; `docs/LOOP_PROMPT.md` cites it, puts the acceptance test first among active goals, points at the plan's commit conventions instead of carrying a trailer, and on a held lock does lock-free plan work instead of waiting; `docs/HANDOFF.md` "START HERE" names Sprint 5.
- [x] **Step 7: Commit** with an explicit pathspec (and `git rm` for the moved tests); push. (Archiving Sprint 4's ledger is the controller's, not this task's.)

---

### Next, before Task 1's first launch (both zero-run, lock-free, parallel): Task 4 Step 1 (leg 0) and Task 3 Step 0 (the pure scorers, so launch 1 is scored by code, not by hand).

---

### Task 1: Frostfire control handover

**Files:** create `docs/research/21-frostfire-control-handover.md`; modify `ps2_runtime.cpp` (`guestMalloc`, `guestRealloc` growth) and `online_login_ours.py` (the `_B` mapping) for the knob; modify runtime files only if a later step's fix is bounded.

**Interfaces:**
- Consumes: spec §1 and §1.1; research/19 F2/F3; Task 4 Step 1's object diff; `scripts/parity/online_match_frostfire.sh` (the command that reached Frostfire gameplay first launch, `ours_task8_frost1`; committed from the git-ignored `logs/s4_task8_frost1.sh`); `frost1`/`kill1`/`kill2` logs.
- Produces: `PS2X_GUEST_MALLOC_ZERO=1` (default off); a verdict (*not reproduced* / *fixed* / *not fixed + ruling*) with the branch table and every run's command; the **self-identifying valve peek spec** (offsets plus the expected name-pointer value for each) that Tasks 3, 5 and 6 consume.

- [x] **Step 1: Zero-run preparation.**
  1. **Verify research/19 F2 against the decomp before relying on it** (done once during planning, repeat and record): in `FUN_002a76d0`, `mp_major_game_state` (`0x3f10a0`) comes from `FUN_003520d0` into `param_1[8]` (`+0x20`), `mp_minor_game_state` into `[9]`, `player_team` (`0x3f10e8`) from `FUN_00351ff0` into `[5]` (`+0x14`), `late_joiner` (`0x3f10f8`) into `[0xb]` (`+0x2c`), `mp_game_over` (`0x3f0f88`) into `[4]` (`+0x10`), `total_mp_kills` (`0x3f1268`) into `[0x1c]` (`+0x70`). `FUN_003857c0` builds only the `B*LISTVAR` lists. `FUN_002a7420` writes `+0x114` and the `+0x20` valve, `FUN_002a73b0` writes `+0x115` and the `+0x24` valve, `FUN_002a7490` writes `+0x113`. Confirm `mp_round_count` (`+0x0c`) and `aiteam_00/08` (`+0x58/+0x5c`) the same way.
  2. **Record each valve's name-pointer value** from `spawn_ours3.rdram` (block at `*0x437ce8`) so the harness can check word 0 of each `*0x437ce8+<off>*:2` peek. Resolve the name of the valve behind `DAT_0043668c` (the first early-out in `FUN_00594cf0`).
  3. **Write the branch table into research/21 before launching**: for each way the move path can stop (spec §1.1: `FUN_00551ec0` dispatching `controller->vtbl[0x14]` = `FUN_00592560` **instead of** `vtbl[0xc]` = `FUN_00594cf0`; the spectator branch in `vtbl[0x18]` = `FUN_005979a0`; the online respawn gate in `FUN_00551ec0`; inside `FUN_00594cf0` the `DAT_0043668c` valve and `DAT_003df1b0` early-outs, `FUN_00566940` (`vtbl[0x8c]`) returning non-zero, the snap-back), the row that shows it, the value that means "this stopped it", and what it implicates. *Blind class:* reachability, not firing.
  4. **Confirm Task 3 Step 0's `score_control` CLI runs over `frost1` and `kill2`** and reproduces `NO-CONTROL` / controllable; launch 1 is scored with it.
- [x] **Step 2: Build the zero-fill knob before any launch.** `PS2X_GUEST_MALLOC_ZERO=1` zero-fills the block returned by `PS2Runtime::guestMalloc` and the grown tail in `PS2Runtime::guestRealloc` (these back the bound `_malloc_r`/`_memalign_r`/`_realloc_r`; `guestCalloc` already zeroes). Add `PS2X_GUEST_MALLOC_ZERO_B` to `online_login_ours.py`'s per-instance environment mapping (the `PS2X_SOCOM2_NET_STATS_B` pattern). Unit test: with the knob a freed-and-reallocated block reads zero, without it the old bytes survive, and a grown `realloc` keeps the old prefix. Batch Task 4 Step 4's `PS2X_HLE_STATS` into the same build. One `loop_lock.sh run` of `./build.sh runtime && ./build.sh test && python -m tools_py.parity.gate` (knob off = no behaviour change). Commit.
- [x] **Step 3: Launch 1 (Frostfire).** `scripts/kill_stale_drivers.ps1`; lock; `run_detached.sh`. Start from `scripts/parity/online_match_frostfire.sh` (already `--map frostfire`; takes the output directory as its argument; set `PS2X_SOCOM2_SERVER` to this machine's LAN address), replacing its peek and trace environment with:
  - `PS2X_PEEK="0x416054:3,*0x408c58:64,*0x408c58+0xc0*:32,*0x408c58+0x400:12,*0x408c58+0x174:1,*0x408c58+0xF78:24,*0x408c58+0x1044:8,*0x437ce8:64,*0x437ce8+0x100:21,*0x437ce8+0x0c*:2,*0x437ce8+0x10*:2,*0x437ce8+0x14*:2,*0x437ce8+0x20*:2,*0x437ce8+0x24*:2,*0x437ce8+0x2c*:2,*0x437ce8+0x58*:2,*0x437ce8+0x5c*:2,*0x437ce8+0x70*:2,*0x43668c:2,0x4365c0:1,0x45a0c0:1,0x3df1b0:1,0x45a1c8:1,*0x44fa90:2,0x4413d8:1,*0x437ce8+0x0c**:3,*0x437ce8+0x10**:3,*0x437ce8+0x14**:3,*0x437ce8+0x20**:3,*0x437ce8+0x24**:3,*0x437ce8+0x2c**:3,*0x437ce8+0x58**:3,*0x437ce8+0x5c**:3,*0x437ce8+0x70**:3,*0x43668c*:3,0x408f10:2,0x408c58:4"` *(Amended 2026-09-13 by Task 1 Step 1's verified chain: `+0x174` low 16 bits = 8 is the spawn-dead signature; `+0xF78:24` covers `+0xFB0` (= 6 on the death-handler branch), `+0xFCF`, `+0xFD3`; `+0x1044:8` covers `+0x1061`; `**:3` items check each valve by its name bytes because name pointers are platform-specific; `*0x44fa90`/`0x4413d8` are JoinAsSpectator, filled lazily.)*
  - `PS2X_CALL_TRACE="0x553dc0:MoveScale,0x594cf0:PlayerUpd,0x592560:CtlAlt14,0x5979a0:CtlSpec18,0x551ec0:ActorUpd,0x30cd80:NetIdle,0x2a7420:SetMajor,0x2a73b0:SetMinor,0x2a7490:SetMyMajor,0x1f5e70:GhostSet,0x1f6660:GhostClr,0x2232a0:GhostClr2,0x2b7d60:SpawnGhost,0x544210:SetLife,0x543d50:SpawnDead,0x543b90:GhostRevive,0x598840:InputEnable"` with **`PS2X_CALL_TRACE_EVERY=10`** (global). *(SpawnDead's `ra` names the branch: `0x2b7e74` JoinAsSpectator, `0x2b7ea0` ghost with respawn-game on, `0x2b7eb0` ghost with respawn-game off, `0x599dfc` `FUN_00599b60`; InputEnable's `a0` is the value and `ra` `0x5cf840` is ai::STOPALL.)*
  - `PS2X_CALL_TRACE_DUMP` on `PlayerUpd` (controller in `a0`): `a0+0x170:1` and `a0+0x4*+0x400:9`.
  - **Log size:** `kill2` logged ~5550 MoveScale calls in 293 s (~19/s); at `EVERY=10` a slot of that rate logs ~1.9 calls/s = **~4 lines/s** (`[call]` + `[ret]`, flushed), and `NetIdle`/`ActorUpd` may run faster. Check the log's size at the liveness point and abort the run if it passes 200 MB.
- [x] **Step 4: Read launch 1.** Zero-rows check on every slot and item first (an empty slot or a valve whose name pointer does not match fails the run). Score each side with `python -m tools_py.parity.verdict_core score-control <run_A.log> <run_B.log>` (spec §5 Goal 1's bar, with its three blind classes printed beside the verdict). Then: *(done, but the zero-fill A/B sub-branch specifically never ran — its precondition, the ghost-spawn chain firing, did not hold on launch 1; R21.)*
  - **Both move** → one of the two usable runs *not reproduced* needs; launch again (Step 6 counts).
  - **Reproduces with `SpawnDead` from `ra` `0x2b7ea0`/`0x2b7eb0` AND `+0x174 == 8` AND `ng+0xd2 != 0`** (amended 2026-09-13: the verified spawn-ghost chain; `+0x113/+0x114` stalling alone no longer triggers the A/B — name its row from the branch table instead) → **launch 2 is the A/B**: same binary, instance A `PS2X_GUEST_MALLOC_ZERO=1`, instance B off (per-instance knob, the `PS2X_SOCOM2_NET_STATS_B` pattern), same peeks. **The A/B reads only if instance B (knob off) reproduces the failure**; if B moves too, the run says nothing about the knob and counts as a *not reproduced* sample. Zero-fill moves and default does not → condition proven; go to Step 5 with the fix being the knob or a narrower zeroing.
  - **Reproduces otherwise** → name the level from the branch table (`ActorUpd`/`SpawnGhost`/`SpawnDead`/`GhostSet`/`GhostClr`/`GhostClr2`/`GhostRevive`/`InputEnable`/`PlayerUpd`/`MoveScale` `#n` and the early-out values), then the condition sentence.
  - Every usable Frostfire run also yields the first live reads of `+0x1044`, `+0xF7A` and the valves: record them.
- **Launch 1 outcome (2026-09-13, 3 launches, 1 usable):** the A/B precondition is **not met** (ghost chain did not fire); stop row **R6**, the snap-back, because the ground probe misses at spawn (KNOWN §2). Zero-row rule amended: an empty trace slot that is a *predicted negative* is recorded with its `jal`-only caller check, not a failure. **Launch 2 is Frostfire with launch 1's spec plus** (amended after research/23 and its review) traces `0x5b0840:ProbeQueue,0x5b0800:ProbeBatch,0x5b0420:ProbeTake,0x5b5d40:ProbeEval,0x31de90:GridQuery,0x252150:VoiceVu0Upload,0x251a98:VoiceVu0Mode,0x24fac0:VoiceFftSel` (`EVERY=10`; `0x2d3cf0` is tail-called and cannot be hooked), dumps `ProbeEval:a1:19,ProbeEval:a1+0x48*:32,ProbeEval:a1+0x48*+0xc*:4,ProbeEval:a0+0x28*+0x30:3`, peeks `*0x45c380+0x684:4,*0x45c380+0x694:1,*0x45c380+0x6b4:3,*0x45c380+0x6c0:1,*0x45c380+0x6cc:1,*0x45c380+0x778:3,0x44f070:3,0x44d588:5,0x44f354:2,0x3df1c8:1,*0x408c58+0x2c0:4,*0x408c58+0xf40:1,*0x44d588*:19,0x1d55a0:1`, and `PS2X_RDRAM_DUMP_AT` per instance (distinct paths) on `ProbeEval#600` (one spec per process). Reading: ProbeEval rows with `ra` 0x5b0478, GridQuery with `ra` 0x5b0828; the discriminator is the collision grid's nodes + free = 8192 vs a zero free head (pool exhausted = chain cut, `FUN_002d7580`); ~20 MB log + 32 MB image per instance; then the Step 5b Medley control with the same set as the hit contrast.
- [x] **Step 5: Condition sentence, then fix if bounded.** *(Draft from launch 1: "the Frostfire local player's ground probe never hits at the spawn point, so `actor+0x420` is never stamped and the online snap-back suppresses MoveScale from clock 0.6 s; why the probe misses is open.")* "X never becomes true on Frostfire because Y", with the evidence line, before any fix. **Two fix attempts maximum**, in our runtime only. Success: the movement bar on both sides on Frostfire and on Medley (Step 5b's launch serves if it follows the fix; otherwise one more Medley launch, counted), `./build.sh test` and gate green. *(One fix attempt used, not two: the condition was VU0 `vf0.w = 0` on StartThread contexts, not the zero-fill knob — `b625291`, authorised without a pre-fix trace per R27.)*
- [x] **Step 5b: The Medley control launch — unconditional, whatever Steps 4–5 found.** One Medley launch with launch 1's full peek and trace spec: the movement bar (the Medley baseline for every Frostfire value), the first Medley reads of the valves, health, life and team, and **Task 6's clock round-end negative control** — after the movement holds nobody fires, the round ends on its clock, and the run records that `total_mp_kills`, `aiteam_*` and `+0x1044` do not step while `mp_round_count` does. Keep both sides moving in small strafes through the idle wait (two-sided starvation). Counts against the cap; if the lobby fails it, relaunch until one usable Medley control exists, still inside the 8. If the fix is the zero-fill knob, changing its default is a separate ruling with its own gate run.
- [x] **Step 6: Caps and the map ruling (mandatory).** **3 usable matches, hard cap 8 launches** across Steps 3–5b, Medley launches included (P(≥ 3 usable in 8) ≈ 69 % at 4 in 10). The usable-match count is Frostfire matches plus the Medley control; if the cap is reached without the Medley control, it takes priority over further Frostfire launches from launch 7. *Not reproduced* needs 2 of 2 usable Frostfire runs meeting the bar. Record a `Ruling:` — fixed or not reproduced → Frostfire for Tasks 5–6; otherwise → **Medley**, with research/21 handing Sprint 6 the condition as far as it got and a PCSX2 Frostfire pair (plus writer-PC watches, PS2Recomp PR #157, if the question is *who* writes `ng+0xd2`). **During Task 5, two Frostfire `NO-CONTROL` results also trigger the Medley ruling.** Four lobby failures in a row: do one lock-free step before relaunching.
- [x] **Step 7: Commit** research/21 and any runtime change with its test (`git commit -- <paths>`). Propose `KNOWN.md` edits to the controller.

---

### Task 2: Confirm the kill readout in one single-player run, with the aim calibrations riding along

Needs the lock for one run; independent of Task 1.

**Files:** create `scripts/parity/gameplay_death.txt`, `tools_py/parity/sp_death_probe.py`, `docs/research/22-kill-readout.md`.

**Interfaces:**
- Consumes: `scripts/parity/gameplay_damage.txt` (navigation to the HUD; its second attempt with `*0x408c58` was killed by a stale driver, so it has never completed); research/19 F1; the pad file.
- Produces: the Goal 2 confirmation table; the yaw-vs-deflection table, pitch sign/rate, and the at-rest facing check consumed by Task 5.

- [x] **Step 1: Validate at-rest facing offline — zero runs.** On `kill2`'s logs, take the actor and camera rows **immediately before** each forward probe starts (the player at rest), compute `atan2(actor − camera)`, and compare with the probe's displacement direction. Report the error distribution. *Blind class:* the samples come from **Medley only** and from open ground; camera collision near walls is unsampled. Adopt for Task 5 only if p90 ≤ 5°, and re-check on the ruled map's first Task 5 match before relying on it there. *(p90 23.85° at rest over 9 clean holds, ~55° over a relaxed gate of 117–132 — DO-NOT-ADOPT, R12. Task 5 aimed from the actor-matrix heading found in Step 2/3 below instead.)*
- [x] **Step 2: The script and probe.** `gameplay_death.txt` reaches the HUD. `sp_death_probe.py` launches `drive.py` with `PS2X_SOCOM2_INPUT_FILE`, waits for distinct non-zero `0x416054` rows, runs the calibrations (Step 3), then walks into the level and **stands in the open until killed, capped at 240 s** (`FAIL NO-DEATH` at the cap). Peek: `0x416054:3,*0x408c58:64,*0x408c58+0xF78:1,*0x408c58+0x1044:1,*0x408c58+0xc0*:32,0x408c58:4`.
- [x] **Step 3: Ride-along calibrations.** Yaw: `rx` = 0x80 ± {16, 32, 48, 64, 96, 127}, 1.0 s each from rest, both directions, facing from the at-rest `atan2` (if Step 1 adopted it) and from the camera circle fit; report the dead zone and deg/s per level — the bar is **strictly increasing above the dead zone**. Pitch: one 1.0 s `ry=0` and one `ry=255`, sign and rate from camera-minus-actor elevation. *Blind classes:* a 1.0 s hold from rest includes the look acceleration (0.44 s dead time measured in Sprint 4), so per-level rates mix ramp and steady state; SP frame rate is not two-instance frame rate.
- [x] **Step 4: Run once** (lock, `kill_stale_drivers.ps1`, `run_detached.sh`). *(4 launches, 3 usable — `e685b82`.)*
- [x] **Step 5: Read it against spec §5 Goal 2**: intermediate `+0x1044` values, `<= 0`, `+0xF7A` leaving 1 within 2 s, `reads > 0` and `misses = 0`, word 0 still `0x6691a0`. A MISSION FAILURE screen with `+0x1044 > 0` (the player left the mission area) is *not a death*; rerun once with the walk shortened. *Blind class of this bar:* another float in [0, 1] that also changes at death — which is why the first online death at rung 3 (with the valves) is the second confirmation. If no death in two runs, the SP half closes as "not observed" and the first online death (Task 5 rung 3) becomes the only confirmation before Task 6. *(4 launches, 3 usable, e685b82: death was NOT observed — health went 1.0 → 0.721/0.392 then MISSION FAILURE, never ≤ 0. Closed "not observed" per the plan's own fallback, R28; the online death at ladder launch 2 became the sole confirmation.)*
- [x] **Step 6: Arm it.** `--health-offset 0x1044` plus `--alive-offset 0xF7A` as the harness defaults; replay Step 4's log through the watch offline and show it fires at the death rows. Commit research/22, the script, the probe and the arming change. Propose `KNOWN.md` edits (the SP confirmation; still "not read live online").

---

### Task 3: An online harness that cannot spend a match proving nothing

Step 0 runs before Task 1's first launch (new files only). Steps 1–5 may start at once (Sprint 4's Task 8 has landed); lock-free except for the confirming launch, which should be the next scheduled Task 1 or 5 launch.

**Files:** create `tools_py/parity/verdict_core.py`, `tools_py/tests/test_online_verdict.py`, `tools_py/tests/fixtures/online/` (trimmed `frost1` A/B, `kill2` A/B probe and closest-approach windows, `kill3` B probes); modify `online_match_ours.py`, `winshot.py`, `sim_walk_to_b.py`.

**Interfaces:**
- Produces, **pure** (no IO) in `verdict_core.py`, plus a CLI (`python -m tools_py.parity.verdict_core score-control|move-path|contact|starvation <logs…>`) that prints rows read and exits 2 on `NO-DATA`. **One control bar — the spec's**, used by both the precondition and Task 1's scoring:
  - `score_control(rows, pad_events, hold) -> ControlVerdict(ok, net_units, snapback_units, drift_units)`: over actor rows, net displacement from hold start to release + 1.5 s ≥ **40** *(blind: a half-decayed scale that still covers 40; motion in the wrong direction)*; position at release + 2 s within **10** of the position at release *(blind: a correction later than 2 s)*; net drift over the preceding 10 s neutral window ≤ **5** *(blind: a frozen player passes it trivially)*. Precondition holds are 2 s forward holds; the Sprint 4 fixtures (`frost1`/`kill2`/`kill3`) only contain the harness's **1.5 s** facing probes, so the fixtures are scored on those (hold length from the pad events, window release + 1.5 s) — preflight defect 4. *Further blind class:* a controllable player whose hold runs into geometry (`kill2` A `Aapp00_walk` 2.00 s → 21.72 units) fails the 40 — hence a side passes if **any** of its up-to-4 holds passes, with the heading varied between holds.
  - `score_move_path(call_indices_by_time, alive_rows, round_rows, now) -> ok | stalled_since | disarmed | NO-DATA`: MoveScale `#n` must advance within 10 s; **disarmed** while `+0xF7A != 1` or within 15 s of an `mp_round_count` step *(blind: legitimately silent on death or round change — hence the disarm)*; a slot with zero lines ever → `NO-DATA`.
  - `score_starvation(netidle_rows, lagflag_rows) -> ok | alarm(side, since) | NO-DATA`: primary the game's own `ng+0xde` byte from the `*0x437ce8:64` peek (1 = the game's lag state, set at idle ≥ 4501 ms); secondary NetIdle `[ret] v0` with alarm at **4000 ms** and bar ≤ **5000 ms**; no NetIdle rows, or `ng+0xde` rows while the move path is silent → `NO-DATA`, never "healthy" *(blind: peaks between samples — `ng+0xde` peek rows come at `PS2X_PC_SAMPLER=0.25` = 4 Hz, slowing to ~0.6 s under load (`kill2` B near closest approach); NetIdle `[ret]` rows at `EVERY=10` come at the thunk's call rate / 10, unmeasured until launch 1)*.
  - `read_valve(peek_item, expected_name_ptr) -> value | NO-DATA`.
  - `score_contact(rowsA, rowsB, callsA, callsB, clock_rows, scale_rows) -> contact_rows`: consecutive rows inside 3-D ≤ 22 and `|dy|` ≤ 10 with MoveScale `#n` advancing on both instances, the clock string changing, **and both sides' latest `f12` ≥ 0.99** *(blind: line of sight, aiming away)*.
- Produces, IO wrappers in `online_match_ours.py` (Sprint 4's Task 8 has landed, so this is the file as merged): `assert_controllable(side, tail, sh)` (up to 4 two-second holds with the heading varied between them, each scored by `score_control`; a side is controllable if any hold passes; both sides fail → `RESULT NO-CONTROL`, exit 3; one → `RESULT NO-CONTROL side=<X>`); `MovePathWatch` (refuses to start unless `PS2X_CALL_TRACE` includes MoveScale **and** `PS2X_CALL_TRACE_EVERY` ≤ 20); round state from `read_valve` over `mp_round_count`, `mp_game_over`, `aiteam_*` and the clock string, with `respawn` demoted to a fallback round-end signal; `winshot.grab(hwnd, max_age=2.0)` raising `StaleFrameError`.

- [x] **Step 0 (before Task 1's first launch; lock-free; touches only new files): the pure scorers and their tests.** `verdict_core.py` and `test_online_verdict.py` with the fixtures — everything in Step 1 that does not need `online_match_ours.py` — so launch 1 is scored by code. Commit after `python -m unittest tools_py.tests.test_online_verdict -v`.
- [x] **Step 1: Failing tests first** *(the `kill3` fixture line was amended in place before implementation, R5: Sprint 4 read the frozen camera record, not the actor, on kill3 B)*, over the fixtures and synthetic rows: `frost1` → `NO-CONTROL`; `kill2` → controllable; ~~`kill3` B → `NO-CONTROL side=B`~~ `kill3` → controllable, `NO-CONTROL side=B` from kill2 A + frost1 B (Ruling, 2026-09-13: B's actor moved; Sprint 4 read the frozen camera); a synthetic +24-unit rubber-band snapped back within 0.6 s, a 20 % snap-back, and a snap-back at release + 1.8 s → not controllable; 6 units/s of neutral drift → not controllable; MoveScale `#n` stalling for 10 s while alive → stalled, while `+0xF7A != 1` → disarmed; a never-logged slot → `NO-DATA`; a starvation watch with no NetIdle rows → `NO-DATA`; NetIdle at 4200 ms → alarm; `ng+0xde = 1` → alarm; a hung instance (rows repeating, clock frozen) inside the gate → `contact_rows = 0`; a pair inside the gate with both `f12 = 0.0` → `contact_rows = 0`; a valve with the wrong name pointer → `NO-DATA`; `respawn` alone → not PASS; an armed health watch with zero reads → FAIL; a back-dated frame file → `StaleFrameError` *(blind: a hung renderer that keeps writing new files)*.
- [x] **Step 2: Implement** until green; thresholds are named constants with the measurement behind each and its blind class in the comment (the control bar against `research/18` §3.12's 28–38 units per 1 s sample during a hold and the 40 u/s forward calibration).
- [x] **Step 3: Defect injection per scorer**: a negative control, monotonicity (a smaller displacement never passes where a larger fails), and one instance of the guarded class for each.
- [x] **Step 4: Simulation**: all scenarios green; add `nocontrol` (the player ignores the pad → `NO-CONTROL` inside the probe window).
- [x] **Step 5: Commit** after `./build.sh test`. The confirming launch's report states which checks fired or stayed quiet and why.

---

### Task 4: HLE and heap liveness audit

Leg 0 (Step 1) runs **before Task 1's first launch**; the rest fills lock time.

**Files:** create `tools_py/parity/object_diff.py`, `tools_py/hle_constants.py`, `docs/research/20-hle-liveness.md`; modify the stub dispatch point (knob) and add the `0x200` unit test.

- [x] **Step 1: Leg 0 — object-keyed uninitialised-field diff (zero runs).** `python -m tools_py.parity.object_diff --static 0x437ce8:0x14c --static 0x408c58:0x1100 --static 0x415ff0:0x200 <our images> -- <console images>` follows each static to its block in every image and prints, per offset, the value set on ours and on the console, flagging bytes `0xAF` (or any constant) on all of ours and zero on the console. It prints the images read and the block address found in each, and exits 2 when a static does not resolve. Reproduce research/19 F3's list for `*0x437ce8`; extend to the actor and camera objects. Also runs over peek logs (the vtable-keyed actor block) so the `frost1`/`kill2` `+0xd0/+0xd4/+0x20c` diff is reproducible.
- [x] **Step 2: Static census with consumer classes.** For each bound stub (`recomp/socom2.toml`), per `jal` site follow `$v0`/`$f0` through the delay slot and classify: ignored / zero-test / const-compare / arithmetic / stored (research/19 F7, prosper's `nid_gate_scan`; report *unresolved* rather than stopping at the first branch). Tag each stub *constant by spec* / *constant by omission* / *wrong shape*, with its return register and width against the guest routine's ABI. Rank constant stubs whose sites are arithmetic or stored first.
- [x] **Step 3: The `0x200` moves-not-constant unit test** (a delivered packet changes the word; `PS2X_SOCOM2_NET_STATS=0` keeps it constant).
- [x] **Step 4: `PS2X_HLE_STATS=1`** — per bound stub: calls, distinct returns (saturating at 64), first/last; prints **every** bound stub, zero-call ones included. Built with Task 1 Step 2's knob; rides Task 1's launch 1. *Blind class:* a varying-but-wrong return passes a distinct count.
- [x] **Step 5: Fix only the obvious and one-line**, each with a moves test, `build.sh test` and gate green; the rest to Sprint 6 in research/20. Commit.

---

## Amendment A — 2026-09-13, the owner-requested broad review (binding; supersedes Tasks 5–6 text below where they conflict)

Source: `.superpowers/sdd/2026-09-13-sprint-5-control-readout-and-first-kill/broad-review.md` (Opus), re-derived facts in its §0 (scripts under the session scratchpad `broad/`). Durable facts are copied into `docs/KNOWN.md` the same hour. Rulings R42–R52 in the ledger.

**Facts that changed the plan (verified offline by the review):** spawns are deterministic per map; Frostfire's are 691 units apart in 2-D with dy 42 (two discrete floors), Vigilance's ~1485 with dy 95 on continuous terrain. On 3c the two movers *swapped* floors (A climbed at ~(686, 938), B descended at ~(652, 1230)) — the camera-steered loop lost that contact, not the map. Mutual standing does **not** starve either side (3c ~48 s both neutral at f12 = 1.0, NetIdle ≤ 1547 ms; kill2 39.6 s); every alarm on record is inside a peer freeze or a pinned-mover window. The actor-matrix yaw settles within one 4 Hz row of an `rx` release online (62/62 holds). A clock round end keeps the actor block and resets both players to their spawns, so one lobby success can carry several rounds.

**A1. Tasks 5 and 6 are one ladder (R42).** Every ladder launch is fully armed (`--until-kill`, KillWatch, valves, both screens); every round is scored rung 1 / 2 / 3 / KILL by both scorers from stored logs; the first round meeting the amended Goal 6 on both scorers **is** the acceptance run. Rung 3 is recorded, not a gate before firing to kill. **Cap: 16 launches** for the ladder (replacing 14 + 10). Stop rules per usable **round**: three usable rounds at rung 1 without rung 2 → swap the mover (B descends via ~(652, 1230)); two usable rounds at rung 2 without rung 3 → the Step 4 damage-path decision, **or the grenade option** (A7). **Medley/Vigilance is not a contact fallback** — only if Frostfire loses *control*.

**A2. `--rounds N` (default 4) (R43).** After a round end or kill: re-find the actor by vtable, re-arm the move-path disarm window (`ROUND_STEP_DISARM_S`). Round 1 carries the precondition and the rung-0 smoke; rounds 2..N engage only. Each round scored independently.

**A3. Default engagement (R44).** Shooter = **host A**; victim = joiner **B, standing at its spawn**. A follows a recorded waypoint route (`tools_py/parity/routes/frostfire.json`, source rows cited) to B's floor, closes into the engagement band, stops, aims with partial-`rx` pulses closed-loop on the actor matrix (read 0.5 s after each pulse), fires bursts until death or clock. Victim strafe-oscillation and shooter micro-strafe are **flags, default off**; "the other side moves" survives only as a reaction when a side's scale < 0.99 or `ng+0xde` = 1 **with both round clocks running**. Task 5 Step 1's five measurement legs are **cut** (passive per-round NetIdle/alarm readout in the LADDER line instead); Step 2's deadlock negative test is **not a commit gate** (keep a frozen-peer reactive-rule test). Goal 5(b) becomes **reported** (a rung-0 `rx` pulse table ±64/±80/±96, 0.3 s each); its bar is "closed-loop aim reaches tolerance in ≤ 6 iterations on ≥ 80 % of aim cycles". **Teleport detector:** an actor row step > 30 units not explained by a forward hold aborts the aim cycle (`TELEPORT`); inside a fire window the round is `NO-DATA`.

**A4. Rung 0 in the first ladder launch (R45).** `PS2X_GS_STATS=1` on both instances; pass = MoveScale ≥ 17 calls/s over 60 s with both clocks running, clock string at real time (≥ 0.95), `back-pressure:` waits not in the hundreds; `PS2X_GS_MAX_PENDING_FRAMES=0` is the A/B knob. *(Instrument parameters, registered 2026-09-13, R67 — not acceptance bars: MoveScale ≥ 17/s over the first pause-free 60 s with both clocks running; clock-string rate ≥ 0.95; back-pressure waits < 100 per side in that window. Route start after the precondition: nearest same-floor waypoint within 60 units, else `NO-DATA route-start` (R65). The ladder template passes `--auto-swap` (R66). The Frostfire route default is `routes/frostfire_v2.json` via `--route` (R64).)* After R40/R41 land with the gate green, **the runtime is frozen** until the ladder ends unless a stop rule names a runtime cause; the exe sha is recorded in the ledger.

**A5. Launch hygiene (R46).** Every launch: runs a **pinned harness snapshot** (`git archive <sha> tools_py scripts` into the run dir, RESULT line prints harness and exe commits); records a **1 s host CPU sampler** (total + both `socom2.exe`) into the run dir; writes `logs/.quiet` while running (no `build.sh test`, sims, unittest suites, >5 MB log parsing or decomp searches by any agent while it exists); `run_detached.sh` and `gate.py` **refuse below 4 GB free on C:**. Budget at **~20 min per launch average** (the record: usable 12–23 min).

**A6. Lobby pull-forward, minimal (R47).** Before the first ladder launch: the screen-verified re-send for dropped map CROSS and dropped READY (from the untracked `logs/s5_t1_launch8c_driver.py`) moves into `online_login_ours.py` with tests over the 8a/8b/8c screenshots, plus a per-stage lobby timeout ≤ 3 min. Full hardening stays Sprint 6.

**A7. Grenade option (R48).** After two usable rounds at rung 2 without rung 3, the shooter may switch to a grenade on the stationary same-floor victim (the objective allows shot or grenade): one throw-distance calibration, a self-damage guard; Goal 6's "no grenade on the victim in the 10 s before" reads the **victim's** own pad only.

**A8. Process conventions (R49).** Independent verification of a reading only when it authorises a fix, launch change or default; promotes/retracts KNOWN or moves a bar; rests on a static-analysis negative; or is the first live read of a PASS field — one round; otherwise a ≤ 15 min controller spot-check. Tool/harness code: one fix round then a residual ruling, unless the residual can produce a false PASS. One writer per area (C++ runtime; online harness `online_*`/`sim_walk_to_b`/`verdict_*`; gate `drive`/`gate`/`compare`/`scripts/parity`; KNOWN = controller), claimed in the ledger. Foreign C++ WIP: run the Python stage only and record `C++ stage deferred: foreign WIP`. At most one dispatched agent waits on the lock at a time; waits happen inside a tool call, never by ending a turn. New red TDD files are `wip_test_*.py` until green. Harness commits are reviewed in slices of ≤ ~500 lines.

---

### Task 5: Engagement ladder

**Only runs when:** Task 3 has landed; Task 1's ruling is recorded; Task 2's yaw table exists.

**Files:** modify `online_match_ours.py`, `online_login_ours.py` (`PAD_AXIS` partial deflection), `sim_walk_to_b.py`; append to research/22.

**Interfaces:**
- `Shell.pad(seconds, buttons, sticks, axes=None)` with explicit 0–255 axes; `aim_yaw(me, target_xz, tail, sh) -> (err_before, err_after)`, closed loop to `|err| ≤ AIM_TOL_DEG` (6.0) in ≤ 6 iterations.
- `--endgame cooperative`, built on the two-sided rule (**each side's scale is restored only by the other side moving**): inside `ENDGAME_UNITS` (150.0, 3-D) the victim (B) stops approaching and **strafe-oscillates** continuously (`lx` alternating at the smallest deflection that moves, 0.4 s per leg, excursion ≤ ~8 units) — this feeds the **shooter's** counter; the shooter (A) closes to the contact gate, levels and aims, and **micro-strafes between bursts** (one 0.3 s `lx` leg, alternating direction, then re-aim) so that its aim-and-fire windows never exceed ~2 s of standing still — this feeds the **victim's** counter. `StarvationWatch` runs `verdict_core.score_starvation` on **both** instances (primary `ng+0xde`, secondary NetIdle alarm 4000 ms). **When a side alarms, the other side moves**: victim alarms → the shooter suspends firing and walks a 1.0 s strafe leg; shooter alarms → the victim walks a 1.0 s leg toward the shooter. There is no "shooter stuck" trigger (standing still to aim is healthy by design). `NO-DATA` from the watch (no NetIdle rows — NetIdle stops with the move path) stops the engagement and is reported, never treated as healthy. Banner prints roles, both oscillations and the alarm source.
- `LADDER rung=<n> controllable=<A,B> contact_rows=<n> rows_read=<n> damage=<yes/no/unarmed> kill=<yes/no> starvation_alarms=<n> alarms_cleared=<n> max_idle_ms=<A,B> lagflag_rows=<A,B>` (`NO-DATA` in any field whose rows were zero).

- [ ] **CUT by Amendment A3 (R44):** replaced by a passive per-round NetIdle/`ng+0xde` readout in the `LADDER` line; the five measured legs were never run as their own step. **Step 1: Measure what feeds the counter, on ours, inside the first Task 5 match** (before the approach, ~75 s, both sides alive and controllable): five 15 s legs, recording both sides' NetIdle `v0`, `ng+0xde` and MoveScale `f12` — (a) both still; (b) A still, B parks; (c) A still, B rotates in place (`rx`); (d) A still, B strafe-oscillates; (e) **B parked, A fires R1 bursts while standing still** (does firing feed B's counter?). Record for each leg whether the *other* side's idle counter resets. This settles `KNOWN.md` §2's parked-opponent question for ours (the console half stays open) and sets the sim's `rotation_feeds` and `firing_feeds` parameters. *Blind class:* 0.25–0.6 s peek sampling and NetIdle's (launch-1-measured) trace sampling miss sub-second resets; a leg showing resets at the Sprint 4 cadence (1.10 s mean, 2.7 s worst) counts as feeding.
- [x] **Step 2: Simulation with a two-sided starvation model.** `sim_walk_to_b.py` gains per-side idle ms reset only by the **other** side's traffic — translation always, rotation iff `rotation_feeds`, firing iff `firing_feeds` (Step 1's measurements; until Step 1 runs, both `False`, and re-run the tests with the measured values afterwards) — the scale `clamp((5000 − (idle − 1500)) × 0.001, 0, 1)` applied to translation **and rotation** (not pitch), `ng+0xde` set at idle ≥ 4501 ms, and rows `[ret] NetIdle #n v0=<ms>` and `MoveScale #n f12=<scale>` with advancing `#n` (today's sim writes `f12=1.0` every tick and cannot see starvation). New `endgame` scenario: a parked victim on a ledge above part of the shooter's path, a wrong yaw gain, a dead zone, and **aim-and-fire windows long enough (≥ 8 s of shooter standing still in total) that the victim's counter would pass 5500 ms without the rule**. Assertions, all of them: **neither side's idle ever exceeds 5500 ms**; every alarm clears within 3 s; ≥ 20 contact rows **with both scales ≥ 0.99 on those rows**; final aim error ≤ 6°. **Negative test that fails without the fix:** the identical scenario with the other-side-moves rule and the shooter's micro-strafe disabled must violate the 5500 ms assertion (it must be *this* removal that breaks it — run it with `rotation_feeds` both `True` and `False` and require the violation in both). All existing scenarios stay green.
- [x] **Step 3: The live ladder.** Caps: **at most 6 usable matches, hard cap 14 launches** (the stop rules need ≤ 4 usable: P(≥ 4 usable in 14) ≈ 88 %, P(≥ 6) ≈ 51 % at 4 in 10; caps are ceilings). Every run: `kill_stale_drivers.ps1`, lock, `run_detached.sh`, the Task 1 peek spec (health, life, valves, clock) and `PS2X_CALL_TRACE="0x553dc0:MoveScale,0x30cd80:NetIdle"` with `EVERY=10`. *(Cap superseded by Amendment A1: one merged 16-launch ladder replaced this task's standalone 14 plus Task 6's 10. Landed in 3 launches — 1, 1b, 2 — reaching KILL on rounds 1–3 of launch 2.)*
  - **Rung 1 — controllable** (Task 3's precondition; on Frostfire, two `NO-CONTROL`s trigger the Medley ruling).
  - **Rung 2 — contact**: spec §5 Goal 5(a) with (c) holding *(blind: line of sight, aiming away)*.
  - **Rung 3 — damage**: spec §5 Goal 5(d) — the victim's `+0x1044` drops below 1.0 during contact, the killer's R1 in the preceding 3 s, no victim y drop > 20 units in the preceding 2 s *(blind: an environmental damage source coinciding with a burst)*. This is also the first online confirmation that network damage writes `+0x1044` — and the second confirmation of Task 2's bar.
- [x] **Step 4: Stop rules (one set, used everywhere).** Three usable matches without rung 2 → stop, write the closest approach (3-D, `dy`, where each side stuck). **Two usable matches reaching rung 2 without rung 3** → stop with both screens at contact and decide: shots missing (the frames show impacts elsewhere) vs a damage path that does not write `+0x1044` (take one online RDRAM image pair with `PS2X_RDRAM_DUMP_AT` on a `SetLife` or MoveScale call count shortly after a burst, and run `object_diff.py`). Any starvation alarm that does not clear within 3 s of the other side moving, or any `NO-DATA` from the watch during an engagement → stop the match, fix before the next launch. Launch cap reached → stop with the same write-up. *(None of these fired: rounds 1–3 of ladder launch 2 reached rung 3/KILL directly, so the rung-2-without-rung-3 branch and the grenade option (A7) were never needed; the ladder stopped per R72 at the first confirmed PASS.)*
- [x] **Step 5: Commit** each harness change a run depended on (`build.sh test` + simulation green). Propose `KNOWN.md` edits per rung; mark rows of `research/18` §4.13 superseded as rungs are met.

---

### Task 6: The acceptance run

**Only runs when** Task 5 reached rung 3 (which arms `+0x1044` online from that moment).

**Files:** create `tools_py/parity/verdict_replay.py`, `tools_py/tests/test_verdict_replay.py`; modify `online_match_ours.py` (`KillWatch`), research/22, `README.md`.

**Interfaces:**
- `KillWatch` **primary signal: the actor fields** — victim instance `+0x1044 <= 0` and `+0xF7A != 1` with word 0 intact; corroborated by the valves.
- `verdict_replay.py <run_A.log> <run_B.log>` **primary signal: the valves** — killer-instance `total_mp_kills` step and `aiteam_*` drop on both instances within 2 s; corroborated by the actor fields. Prints `KILL killer=… victim=… t=…`, `NO-KILL <reason>` or `NO-DATA <item>` (exit 0/1/2), imports nothing from `online_match_ours` or `verdict_core` (a test asserts the import set).
- Both scorers read the victim's team from the victim instance's `player_team` valve (`*0x437ce8+0x14*:2`), cross-checked against `actor+0xC8`, and require that team's `aiteam_*` to drop (semantics of both valves: inference).
- PASS = both scorers agree **and** every condition of spec §5 Goal 6 — in particular **the killer's R1 injected within 3 s before the death with the pair inside the contact gate (3-D ≤ 22, `|dy|` ≤ 10) throughout that window**, which neither the valves nor the actor fields can supply on their own (a death from an unrelated damage path moves all three signals together).

- [x] **Step 1: `verdict_replay.py`, test-driven**: a Task 5 rung-3 log (damage, no kill → `NO-KILL`); the Task 1 Step 5b Medley **clock round-end control**, which exists unconditionally (→ `NO-KILL`, `total_mp_kills`, `aiteam_*` and `+0x1044` unchanged while `mp_round_count` steps — the free negative control; missing → Task 6 does not start); synthetic kill; synthetic mutual death; synthetic victim fall (y drop > 20 units) → `NO-KILL fall`; synthetic grenade on the victim → `NO-KILL self`; synthetic death with no killer R1 in the 3 s before → `NO-KILL unattributed`; synthetic death with R1 but the pair 40 units apart → `NO-KILL unattributed`; `aiteam_*` of the wrong team dropping → `NO-KILL team`; missing valve → `NO-DATA`.
- [x] **Step 2: Run.** Caps: **4 usable matches, hard cap 10 launches.** Success: spec §5 Goal 6 (P(≥ 4 usable in 10) ≈ 62 % at 4 in 10), both screens within 2 s, exit 0, `verdict_replay.py` independently `KILL` with the same killer and victim. *(Superseded by Amendment A1: Task 5 and Task 6 became one 16-launch ladder, and this task's own caps were never separately spent — the acceptance run landed on ladder launch 2, the 3rd launch of 16 shared with Task 5.)*
- [x] **Step 3: Disagreement is the finding**, never a pass: fix whichever scorer is wrong with a test reproducing it, then re-score the stored logs (no relaunch). *(Never exercised — KillWatch and `verdict_replay` agreed on rounds 1–3, independently re-derived clause by clause.)*
- [x] **Step 4: On success**: record the command, artefacts, launch count and both verdict lines; tile both screens into tracked `docs/research/assets/22-first-kill.png`; the same hour, mark superseded every tracked "not reached" sentence (`LOOP_PROMPT.md`, `HANDOFF.md`, `ROADMAP.md` §4, `STATUS.md` Current state). *(The PNG landed same-hour, `5f1de26`; the doc-wide "not reached" sweep did not happen "the same hour" as written — it is this Task 7 close-out, flagged as a concern in `ladder-launch2-report.md`.)*
- [ ] **NOT APPLICABLE — no cap was exhausted.** **Step 4b: On cap exhaustion — named deliverable**: research/22 §"Acceptance attempts" with, per launch, its outcome (lobby failure class / `NO-CONTROL` / highest rung / each scorer's verdict line), the closest 3-D approach and contact rows, both screens at the best moment tiled into `docs/research/assets/22-attempts.png`, and a ranked next-instrument list for Sprint 6. *(The acceptance test PASSED at ladder launch 2, 3 of the shared 16-launch cap, so this deliverable was never triggered.)*
- [x] **Step 5: Commit** (`git commit -- <paths>`).

---

### Task 7: Close-out

- [x] Verify (not perform) retractions and superseded markers for everything this sprint changed.
- [x] `docs/STATUS.md` Current state + a dated Sprint 5 entry; `README.md` knobs (`PS2X_GUEST_MALLOC_ZERO`, `PS2X_HLE_STATS`, `--endgame`, `--health-offset`/`--alive-offset` defaults, `LOOP_LOCK_PATH`, `run_detached.sh`); `LOOP_PROMPT.md`; `HANDOFF.md`; `CURRENT_SPRINT.md`; `ROADMAP.md` §6.
- [x] Tick boxes against reality; write the **Outcome** section, including launch counts per task against their caps.
- [ ] **PENDING, after this docs close-out and the close-out fix wave land.** `PS2X_TEST_REPEAT=3 ./build.sh test`; final gate (`--stamp s5_head_1x`) PASS 3/3, title s00–s19 ≥ 99 run-vs-run against the merge-base stamp. *Blind class:* a regression fence, not correctness.
- [ ] **PENDING — controller-owned, after the final gate above.** `scripts/archive_sprint.sh` (controller-owned if it exists by then); commit; push. **The controller merges.**

---

## Self-review

- **Spec coverage:** spec Goal N = Task N throughout (0 preconditions, 1 Frostfire, 2 SP readout, 3 harness, 4 HLE/heap audit, 5 engagement, 6 acceptance, 7 close-out).
- **Execution order:** Task 0 → (Task 4 Step 1 ∥ Task 3 Step 0, zero runs) → Task 1 Steps 1–2 (knob + `PS2X_HLE_STATS`, one build) → Task 1 launches incl. the unconditional Medley control, interleaved under the lock with Task 2's single run → Task 3 Steps 1–5 (Sprint 4 Task 8 has landed; no longer gated) → Task 5 → Task 6 → Task 7; Task 4 Steps 2–5 fill lock time.
- **Budget:** at most 8 + 14 + 10 = 32 online launches plus two single-player runs — ~5.5 h of lock at ~10 min a launch and realistically more; an overnight cron loop, not one context. Chance of each usable-match target inside its cap at 4 in 10: Task 1 ≥ 3 of 8 69 %, Task 5 ≥ 4 of 14 88 %, Task 6 ≥ 4 of 10 62 %. Every task before Task 5 lands value on its own.
- **Review round 1 Criticals, as now addressed.** C1 — two-sided: the victim strafe-oscillates (feeds the shooter), the shooter micro-strafes between bursts (feeds the victim), an alarming side is rescued by the *other* side moving, the watch reads the game's `ng+0xde` plus NetIdle (alarm 4000 ms, bar 5000 ms) on both instances and reports `NO-DATA` rather than health when rows stop; Task 5 Step 1 measures parked / rotating / strafing / standing-fire legs; the sim asserts no idle > 5500 ms, alarms clear, contact rows with both scales ≥ 0.99, and its negative test removes the other-side-moves rule and must deadlock whether or not rotation feeds. C2 — `loop_lock.sh run` renews foreground work, the busy list covers builds, test binaries and Python test runs, reaping needs a 15-min-stale heartbeat and an empty busy list, and the 45-min break runs on the heartbeat and is refused while anything busy runs. C3 — PASS splits actor fields and valves across both instances, requires the killer's R1 from inside the contact gate, reads the victim's team from `player_team` and `actor+0xC8`, and has an unconditional clock round-end negative control; `total_mp_kills` and `aiteam_*` semantics are flagged as inference.
- **Bars and their blind classes** sit beside each bar in spec §5 and in Tasks 1, 2, 3 and 5: movement ≥ 40 (half-decayed scale, wrong direction), snap-back ≤ 10 (correction later than 2 s), drift ≤ 5 (frozen player), move-path 10 s (death/round change — disarmed), contact 20 rows (line of sight; the scale clause closes the deadlocked-pair class), starvation (sub-sample peaks), Goal 2 (another float changing at death), rung 3 (environmental damage coinciding with a burst), facing p90 (Medley-only samples), yaw (acceleration from rest), frame age (hung renderer writing new files).
- **Preflight corrections applied:** valve constructors (`FUN_003520d0`/`FUN_00351ff0`); `DAT_0043668c` early-out as a valve read; `FUN_00592560` runs instead of `FUN_00594cf0` (vtable `+0x14` vs `+0xc`) and `FUN_005979a0` (`+0x18`) is traced; `FUN_00566940` confirmed at `+0x8c`; `EVERY` global, ~4 lines/s per ~19/s slot at `EVERY=10`; `RDRAM_DUMP_AT` on a call count; zero-fill in `PS2Runtime::guestMalloc`/`guestRealloc` (the bound allocators), with `_B` mapping; hygiene test scoped to `tools_py/`; one control bar shared by precondition and Task 1 scoring, landed before launch 1.

---

## Outcome — what actually happened, and where reality diverged from this plan

Written at close-out (Task 7, 2026-09-13), after the acceptance test PASSED on ladder launch 2.
The boxes above are ticked against reality, not intent. Headline facts live in `docs/KNOWN.md`;
the dated narrative is `docs/STATUS.md`'s Sprint 5 entry; the sprint's own ledger is
`.superpowers/sdd/2026-09-13-sprint-5-control-readout-and-first-kill/progress.md` (gitignored,
deleted at archive) — this section and the next are its durable copy.

**Result: the acceptance test PASSED.** `bash scripts/parity/ladder_frostfire.sh --pinned
logs/parity/s5_t5_ladder2`, HEAD `171290b`, exe sha `234b4772cd0a8bf8` (frozen at `92d30f0`).
Round 1 scored `KILL killer=A victim=B t=141.33` on both KillWatch (actor fields: `+0x1044`
1.0 → 0.298 → 0.0, `+0xF7A` 1 → 2, word 0 intact) and `verdict_replay` (valves: `total_mp_kills`
0→1 on the killer's instance, `aiteam_08` 1→0 on both, the killer's R1 burst inside the attribution
window (3-D ≤ 60, `|dy|` ≤ 10) 0.59 s before), independently re-derived clause by clause. Rounds 2 and 3 repeated it in the
same lobby. Round 4 reached rung 2 only (111 in-tolerance bursts, no kill). Screens tiled into
`docs/research/assets/22-first-kill.png` (`5f1de26`). The kill frames' ages for this run are bounded
by the screen files' mtimes (0.23–0.38 s after each death read, research/22), not by a recorded
`screen_age_s`: that recording landed in `98f6417`, after the kill. The run's logs are pinned by
`tools_py/tests/fixtures/replay/l2r1_*.txt` and archived under `D:/socom_archive/acceptance/s5_ladder2/`
(manifest `docs/research/assets/22-first-kill-evidence.txt`).

**The plan's own shape held better than Sprint 4's did.** The zero-run-first ordering (Task 4 Step
1, Task 3 Step 0, Task 2 Step 1 before any launch) paid for itself repeatedly, and the
"measure-before-fix, condition sentence before any fix" rule caught two wrong causes (the ghost
flag, the exhausted-grid theory) before either could waste a build. What did not hold was the plan's
own estimate of how far Tasks 5–6 could run as separately-capped, five-measured-leg, single-round
engagements — the owner-requested broad review rewrote that half of the plan in place as
**Amendment A**, and the acceptance run came from the rewritten path, not the original one.

### Launch counts against caps

| task | cap | used | outcome |
|---|---|---|---|
| Task 1 (Frostfire control) | 3 usable / 8 launches | **8 + 2 over-cap** (R33: the Medley control could not be skipped) | ghost-flag lead retracted (launch 1); ground-probe miss found and fixed via the VU0 `vf0` constructor (launch 2 verified the cause, launch 3 verified the fix); Medley clock round-end control landed on launch 8c |
| Task 2 (SP kill readout) | not capped (one run) | **4 single-player runs, 3 usable** | health/alive confirmed statically and armed as harness defaults; death **not observed** in SP (closed per R28); the actor-matrix heading field found (p90 1.57°) |
| Task 5 + 6 (merged ladder, Amendment A1) | 16 launches (replacing the original 14 + 10) | **3 of 16** (launch 1, 1b, 2) | rung 1 only on launch 1/1b (route arrived but ran out of round-clock budget before R70's fix); **KILL on launch 2, rounds 1–3**; round 4 reached rung 2 |
| Sprint total online launches | 8 + 14 + 10 = 32 planned | **8 + 2 + 3 = 13** used (plus 4 SP runs) | Amendment A's merge, the lobby pull-forward and the R70/R71 route-budget fix cut the launch count to well under half the plan's ceiling |

### Rulings summary (R1–R72), grouped by theme

The full one-line ledger is in the section below; this groups it for a reader who wants the shape,
not the count.

- **Process and parallel-agent conventions** (R1–R3, R11, R13–R14, R17–R19, R38, R46, R49): the
  loop lock's heartbeat/mutex/reap design (three review rounds, one accepted residual — a ≥30 s
  stall inside a mutex, R17); area claims and foreign-WIP handling after a C++ compile broke under
  another agent's WIP; the calibrated rule for when a finding needs independent verification versus
  a controller spot-check (broad review §B6, below).
- **Frostfire control** (R4–R9, R12, R21, R27, R31–R32, R37): the ghost-flag chain was real but
  never fired; the actual stop was the ground probe missing at spawn because VU0 `vf0.w = 0` on
  `StartThread` contexts, fixed at the constructor without a pre-fix trace (R27, "the sprint's
  single largest win" per the broad review); Frostfire stays the map for Tasks 5–6 (R32/R37) with a
  Medley clock round-end control as the unconditional negative fixture (R31, R33).
  Also here: `kill3`'s Sprint 4 "frozen" reading was the camera record, not the actor (R5); the
  camera cannot supply a heading at all (R12).
- **Harness correctness bars** (R6–R7, R10, R16, R23–R26, R28, R58, R60, R63): the online scorers'
  bars (control, contact, starvation, the kill valves) each went through at least one adversarial
  review round; `verdict_replay.py` alone absorbed R53/R56/R58/R60/R63 across four review rounds
  before the first ladder match, closing false-KILL and false-FAIL holes that a static reading could
  not have found.
- **The GS command backlog and runtime freeze** (R35, R39–R41, R54–R55, R59, R61): the single-player
  gameplay stall (unbounded `m_pending` growth in the GS backend) was fixed as a correctness bug,
  not speed work; the runtime is frozen at `92d30f0` for the whole ladder once the fix's own review
  rounds closed.
- **The gate's own correctness** (R29–R30, R34): the mission stage had scored the intro cinematic
  since 2026-09-12, found by a review, fixed to require live gameplay holds.
- **Amendment A — the broad review's rewrite of Tasks 5–6** (R42–R52, R62, R64–R68): merges Task 5
  and 6 into one ladder, pre-registers the acceptance bars before any match is scored, simplifies
  the engagement to a recorded route plus a standing victim, adds launch hygiene (pinned snapshot,
  CPU sampler, disk refusal, a quiet window), pulls the lobby's dropped-press re-send forward, and
  derives the Frostfire route from collision geometry (research/24) rather than a live scout.
- **Route budget and the ladder's own tuning** (R64, R69–R72): the route-time budget was rebuilt
  from the measured follower rate (7.5–11.3 u/s, not the plan's original estimate) across two fix
  rounds, the lobby's READY re-send was made toggle-aware, and the ladder stopped at the first
  confirmed PASS rather than spending the remaining 13 launches.

### Process lessons (broad review §B)

- **A calibrated rule for independent verification**, now in the plan's own handoff notes and
  `LOOP_PROMPT.md`: a reading gets one review round only if it *authorises* something (a fix, a
  default, a launch change), *promotes or retracts* a KNOWN row or a bar, rests on a **negative from
  static analysis** (two of this sprint's biggest overturns were exactly this shape — "not linked",
  "the grid is exhausted" — and tail calls make "zero callers" unreliable), or is the **first live
  read** of a field a PASS clause will use. Otherwise: a controller spot-check in ≤ 15 minutes.
  Applied retroactively, it would have skipped the Task 2 Step 1 review (a failed adoption bar costs
  nothing wrong) and the launch 3 verification (no decision changed), and would still have caught
  every finding that mattered.
- **Tools and harness code get one fix round, then a residual ruling** — unless the residual can
  produce a false PASS, in which case the plan's two-attempt cap does not apply and review keeps
  going until it does not (this is exactly why `verdict_replay.py` took four rounds while the loop
  lock took three and then accepted a residual).
- **One writer per area, claimed in the ledger**, after a C++ compile broke under another agent's
  uncommitted WIP mid-sprint. A `logs/.quiet` marker during launches now keeps `build.sh test`, the
  gate, `unittest` and large-log parsing off the host while a match runs, and every launch's own CPU
  sampler makes a violation visible in the data rather than inferred after the fact.
- **A stale number is more dangerous than a false sentence**, restated again this sprint: the
  "~5 s" round-step timing in spec §5.1.1 R60 was measured at closer to 33 s once a real kill
  existed to time it against. It did not change any verdict (the forward windows end at the round
  step either way), but it is exactly the class of thing that reads as settled until someone re-times
  it — see `docs/KNOWN.md` §4 for the standing correction.

### Parked to Sprint 6

Per the broad review's revised order (`broad-review.md` §C8, folded into `docs/ROADMAP.md` §6):
lobby hardening to completion (four failure classes still unhandled beyond the two pulled forward);
the online freeze root cause (3–17 s guest stops under host load, believed but not verified to be
host load); single-player teleports (a PCSX2 comparison first); the skeleton root decay
(re-measured on the post-`vf0` exe before any new investigation); a gameplay-state probe as the
gate's first correctness leg; the soft-double `exp` chain and `__ieee754_rem_pio2f` against exact
oracles; a mixed ours/PCSX2 match; HLE audit leg three; harness and gate process cleanup
(`gate.py --baseline`, the sim's pre-existing stack/route flake, the redundant main-context `vf0`
line; the lock tests' smoke default is done, `2858774`, as amended by R73: one reaper race and one
mutex double-entry check stay always on, plus a stamp tying `scripts/loop_lock.sh` to its last green
slow run); the parity PNG export moved off the GL thread; the display
environment and zbp divergence against a console image; VU memory aliasing (latent, no reachable
caller); and automated disk hygiene. Also parked: the close-range aim loop's lack of ammo awareness
or re-aim escalation (round 4 fired 111 bursts at an in-tolerance miss with no correction — this is
Sprint 7's repeatability item, not a Sprint 6 one, per `docs/KNOWN.md` §4).

## Rulings made on the owner's behalf

Every decision the controller took without the owner, in the order taken, each with its reasoning
and what it costs if wrong. Copied out of the gitignored sprint ledger before archiving, so these
survive the workspace. Numbers are the ledger's own R-numbers; a few (R4, R25, R39, R65–R67) cost
nothing if wrong and are recorded for completeness rather than risk.

1. **R1** — dispatch Task 4 Step 1 and Task 3 Step 0 in parallel despite the default no-parallel-implementers rule: the plan mandates it, the files are disjoint, commits use explicit pathspecs — cost if wrong: an index.lock retry, or one rebase.
2. **R2** — build `PS2X_HLE_STATS` (Task 4 Step 4) inside Task 1 Step 2's runtime build, since the plan says to batch them — cost if wrong: one ~10 min rebuild.
3. **R3** — Task 0's commit runs `build.sh test` AND the gate under one `loop_lock.sh run`, since Global Constraints bind both — cost if wrong: ~15 min of lock.
4. **R4** — Task 1 Step 4's "GhostCtl" level means the `GhostSet`/`GhostClr` trace slots — cost if wrong: none (a reading aid only).
5. **R5** — `kill3` is controllable, not `NO-CONTROL side=B`: Sprint 4 read the frozen camera record, the actor itself moved ~65 units — cost if wrong: one fixture expectation.
6. **R6** — snap-back is defined as the peak excursion in [release, release+2 s] minus the displacement at +2 s, robust to sampler rate — cost if wrong: a coast-then-stop pattern reads as a snap-back.
7. **R7** — `CONTACT_ROW_MAX_GAP_S = 1.25` (measured max gap 1.06 s) — cost if wrong: a stall of up to 1.25 s gets bridged inside a contact run.
8. **R8** — the lock's record moves inside the claim directory, the judged line is captured before the judge runs, and the grave is verified after the move — cost if wrong: one more lock rewrite.
9. **R9** — `kill_stale_drivers.ps1` kills only driver modules and `socom2*.exe`, never ancestors or parallel scorers — cost if wrong: a stale scorer survives (harmless, no game affected).
10. **R10** — the real-scale 130 s lock test runs only behind `LOOP_LOCK_SLOW_TESTS=1` — cost if wrong: a timing bug that only shows at real scale is missed by default.
11. **R11** — every lock claim/reap/renew/release runs under a short `mkdir` mutex, no restore path, `LOCK LOST` is loud — cost if wrong: another review round, and a mutex holder dying mid-transition delays others up to 30 s.
12. **R12** — Task 5 aims from the actor-side heading field or measured displacement, never camera `atan2`, since the plan's own adoption bar (p90 ≤ 5°) failed at p90 23.85° — cost if wrong: none (camera facing stays available as an unused fallback).
13. **R13** — the lock token is named `t.<epoch>.<pid>.<rand>`, staleness reads from the token name, and every destructive step re-checks `mx_mine()` first — cost if wrong: a fourth fix round with a fresh implementer.
14. **R14** — the always-on lock test suite is trimmed to ~110 s; full counts run only behind `LOOP_LOCK_SLOW_TESTS=1` — cost if wrong: a rare lock regression is caught only by the slow suite.
15. **R15** — Task 1 Step 2 starts building before Task 0's re-review lands, under the already-committed lock — cost if wrong: a build overlaps a test run, which the gate would show.
16. **R16** — the `PS2X_HLE_STATS` tail-call undercount is folded into Task 4's census dispatch as a documentation fix, not a separate runtime fix round — cost if wrong: a zero-call row is misread until Task 4 corrects it.
17. **R17** — accept the loop lock's one remaining residual (a two-holder window on a ≥ 30 s stall inside a critical section), inherent to any lease lock without kernel locking — cost if wrong: two jobs overlap after a machine sleep, but loudly reported (`LOCK LOST`).
18. **R18** — Task 3 Steps 1–5 (harness wiring) wait until Task 1's launch 1 finishes, since that launch agent may relaunch from the same file — cost if wrong: ~30 min of idle harness time.
19. **R19** — Task 3 Steps 1–5 run now, and the next online launch (the Medley control) waits for Task 3 to land, so it is scored by the hardened harness — cost if wrong: 1–2 h of launch latency.
20. **R20** — Task 4 Step 5 fixes only `sceGsSetDefDBuff`'s argument ABI and clear-packet seeding; the display-environment mismatch, zbp and `rem_pio2f` defer to Sprint 6 — cost if wrong: a render change the gate misses (`--vram-diff` covers it).
21. **R21** — drop the zero-fill A/B for Frostfire (its precondition, the ghost chain firing, never held); launch 2 carries the ground-probe instruments instead, and the knob ships off — cost if wrong: the A/B is still available for a later question.
22. **R22** — defer the VU-memory aliasing fix to Sprint 6: no reachable caller in SOCOM II, and the range change touches every hardware access — cost if wrong: none observed.
23. **R23** — zero `ng+0xde` rows read `NO-DATA`, never "healthy", unless NetIdle itself alarms — cost if wrong: extra `NO-DATA` stops where the game state was actually fine.
24. **R24** — a starved-scale hold (some rows, min < 1.0) retries as `NO-DATA`; a fully silent move path fails outright; `NO-CONTROL` stays terminal — cost if wrong: up to 6 attempts spent on a genuinely starved peer.
25. **R25** — keep `winshot.grab`'s default `max_age=None`; evidence screenshots pass at 2.0 s — cost if wrong: none.
26. **R26** — park the simulation's pre-existing stack/route step-cap flake (1 of 3 at HEAD) to Sprint 6's lobby/loop hardening list — cost if wrong: a real endgame regression could hide behind the flake until Task 5's own endgame scenario is added.
27. **R27** — authorise the VU0 `vf0` fix (constructor sets `(0,0,0,1)`) without a pre-fix trace: it is correct hardware behaviour regardless of the exact cause, and the post-fix census discriminates — cost if wrong: a changed VU0 path on non-main threads, fenced by the gate, `--vram-diff` and run-vs-run.
28. **R28** — Task 2 Goal 2's single-player half closes "not observed" per the plan's own fallback; the first online death (ladder rung 3) becomes the sole confirmation — cost if wrong: none beyond the plan's own stated fallback.
29. **R29** — the gate coverage owed for `e685b82` (the scripts/parity commit) is satisfied by the next gate run on a tree containing it, not a dedicated run — cost if wrong: none (the file it touches is not read by `gate.py`); later corrected to name the close-out gate specifically once the timing was checked.
30. **R30** — fix the mission-gate HUD check (it had scored the intro cinematic since 2026-09-12) as its own small dispatch this sprint, since every later gate PASS is cited as evidence and the final close-out gate must mean gameplay — cost if wrong: one gate-file change and one gate run.
31. **R31** — the "Frostfire fixed" verdict takes its second usable sample from Task 5's first gated match rather than raising Task 1's launch cap; launch 8 covers the still-owed Medley control — cost if wrong: Task 5 starts before the second sample, but its own control precondition would stop the match on `NO-CONTROL` anyway.
32. **R32** — provisional map ruling: Frostfire stays for Tasks 5–6; Task 5 must add floor-aware approach and fix the `closest_3d` bug before engaging — cost if wrong: Frostfire's two floors eat Task 5's contact budget, triggering its own three-usable-without-rung-2 stop rule.
33. **R33** — allow up to 2 over-cap launches for the Medley control specifically, since Task 6 cannot start without its clock round-end negative fixture — cost if wrong: ≤ 2 extra launches, ~30 minutes.
34. **R34** — the mission gate scorer requires ≥ 2 consecutive gameplay hold pairs differing by a mean of ≥ 3.0, checks capture count against logged holds, and logs `STALE FRAME` at holds — cost if wrong: the gate now FAILs on presentation stalls that previously passed silently (the correct direction to be wrong in).
35. **R35** — bounded GS back-pressure in `Present` is in scope as a correctness fix (unbounded memory growth and frozen presentation), not frozen speed work — cost if wrong: single-player runs slower; online pacing risk was reasoned through in the implementer's report.
36. **R36** — scale the loop lock's renew-timing test bound from 3.5 s to 4.5 s to absorb full-suite load jitter — cost if wrong: a marginally slow renew passes when it should not.
37. **R37** — final Task 1 Step 6 map ruling: "Frostfire fixed" = the launch 3c movement bar plus the Medley bar on launch 8c after the vf0 fix; Frostfire stays for Tasks 5–6 with floor-aware approach (carries R31/R32 forward as final).
38. **R38** — full-suite green coverage for the control-round commits (`0118c95`/`b89c4c0`) comes from the GS-backpressure agent's own locked `build.sh test` run on the same shared tree, not a separate run — cost if wrong: a Python-only regression slips until the close-out `PS2X_TEST_REPEAT=3` run.
39. **R39** — accept the back-pressure wait placed at the game thread's `VBlankStart` rather than literally inside `Present()` (which runs on the GL thread) — the spec's intent, a bounded queue with a capped wait, holds either way — cost if wrong: none beyond the review that checked it.
40. **R40** — the back-pressure stall latch is a consumer-progress heartbeat: it engages only on no progress for the full cap and clears on any progress — cost if wrong: another review round.
41. **R41** — clamp the next VBlank host deadline to at least "now minus one period" after a back-pressure wait, dropping accumulated debt rather than letting the guest run up to 4× real time to catch up — cost if wrong: slightly fewer guest frames in already-throttled heavy scenes.
42. **R42** — merge Tasks 5 and 6 into one 16-launch ladder in which every round is itself an acceptance attempt, replacing separately-capped engagement and acceptance phases — cost if wrong: rung data and acceptance attempts mix in one log, but each round is scored independently anyway.
43. **R43** — `--rounds N` defaults to 4 per launch — cost if wrong: round time is lost if later rounds in one lobby behave differently from the first.
44. **R44** — the default engagement is a host shooter following a recorded waypoint route to a standing victim at spawn, with strafing/micro-strafe choreography off by default and Task 5 Step 1's five measurement legs cut in favour of a passive per-round readout — cost if wrong: mid-fight starvation is still caught by the reactive rule and the watch, just not pre-measured.
45. **R45** — a rung-0 smoke test of the GS-backpressure exe runs inside the first ladder launch, and the runtime is frozen once R40/R41 land — cost if wrong: a runtime fix that's later found necessary has to wait for a stop rule to justify unfreezing.
46. **R46** — launch hygiene becomes tooling: a pinned harness snapshot per launch, a 1 s host CPU sampler, a `logs/.quiet` marker, refusal below 4 GB free, and a ~20 min/launch budget — cost if wrong: about an hour of tooling work for marginal benefit.
47. **R47** — pull the lobby's screen-verified re-send (dropped map CROSS, dropped READY) forward into Sprint 5, minimally, before the first ladder launch — cost if wrong: 2–3 hours of zero-run work.
48. **R48** — a grenade option is available after two usable rounds reach rung 2 without rung 3, scoped so the "no grenade on the victim in the 10 s before" check reads only the victim's own pad — cost if wrong: one throw-distance calibration spent (never used — the kill came from rifle fire).
49. **R49** — process conventions for parallel agents: one verification round per authorising/promoting/negative-static/first-live-read finding else a controller spot-check; one fix round for tools unless the residual can false-PASS; one writer per area claimed in the ledger; a foreign-WIP rule; at most one agent waiting on the lock; `wip_test_*` naming; review slices of ≤ ~500 lines.
50. **R50** — spec §5 Goals 5/6's acceptance bars are pre-registered before any ladder match is scored and never move after a kill is seen — cost if wrong: a bar later judged too loose or too tight must wait for a second sprint to correct, rather than being adjusted mid-run.
51. **R51** — Medley/Vigilance is never a contact fallback map; a stuck engagement swaps the mover instead — cost if wrong: a route failure on Frostfire costs rounds that a map swap might have saved.
52. **R52** — Sprint 6's order follows the broad review's §C8 priority list (repeatability-enabling work first, then visible correctness, then the gate's blindness, then latent items).
53. **R53** — spec §5.1.1's clarifications resolve ambiguous readings without loosening any bar, committed before any ladder match — cost if wrong: a first kill that happens to destroy the actor needs a second kill to confirm (it got three).
54. **R54** — fix the idle-spin defect (a half-core spinning after a back-pressure wait) before the runtime freeze, since two instances on one host plus load-induced freezes make it material — cost if wrong: one more runtime review round.
55. **R55** — judge the title run-vs-run ≥ 98.8 bar as phase-aware under host load (a shifted-pair re-score is accepted evidence); a quiet-host title rerun is treated as a close-out formality — cost if wrong: a real title regression hides behind a phase-shift claim, though the shifted-pair check guards against exactly that.
56. **R56** — tighten `verdict_replay.py`'s §5.1.1 bars pre-match: a kill-step window scoped to the same round and paired one-to-one, round-clipped forward windows, freeze detection by window rate, a > 20 s delay reading as `NO-KILL timing`, shooter defaulting to A, and the clock rate as measured (0.57–0.72 guest s/host s) — cost if wrong: a genuine kill with an unusually early kill-valve step reads as non-KILL (bounded to a 3 s window).
57. **R57** — record the `s5_hygiene` mission-gate FAIL as inconclusive under host load (Valheim running), resolved by the close-out quiet-host gate rather than investigated now — cost if wrong: a real stall recurrence only surfaces at close-out instead of immediately.
58. **R58** — the `+0xF7A` alive-byte clause passes on any intact victim row reading `!= 1` within [death, death+2 s host], with the killer's health `> 0` required on every intact row within ±0.5 s — cost if wrong: an alive byte that leaves 1 late for an unrelated reason could pass (bounded to 2 s, and the actor block must stay intact).
59. **R59** — accept the `s5_gsbp3` mission-gate miss as the host-load class, given the same-build mission-only rerun PASSed; the close-out gate must run on a quiet host — cost if wrong: a timing-sensitive mission regression surfaces only at close-out.
60. **R60** — §5.1.1: the step-to-restart freeze is the round boundary; forward attribution windows end at the round step; late kill-valve steps within 20 s still count; pairing is consumed at selection, not later; the alive byte must read 1 in the 2 s before death; a destroyed killer reads unattributed with coverage; team checks are symmetric; window overlap is strict — cost if wrong: none observed (every clause has its own regression test).
61. **R61** — freeze the runtime at `92d30f0` for the whole ladder; no runtime commits land until the ladder ends unless a stop rule names a runtime cause — cost if wrong: a known one-frame jitter after a blocking `sceInetRecv` stays unfixed through the ladder.
62. **R62** — derive Frostfire's spawn-to-spawn connectivity from collision geometry offline (research wave 24) before any route-dependent launch, rather than scouting live; if no connection exists, the controller rules a different engagement — cost if wrong: one scouting round spent finding out live instead.
63. **R63** — register the round-boundary detection parameters (step window, restart offset, freeze cap) and a double-death `NO-DATA` rule in spec §5.1.1 before any ladder match — cost if wrong: a freeze that starts exactly on a round step is misread as a boundary.
64. **R64** — the corrected `routes/frostfire_v2.json` becomes the default Frostfire route via a new `--route` option; the older 3c-derived route stays loadable — cost if wrong: an unscouted route segment, bounded by the follower's no-progress budget and the mover-swap rule.
65. **R65** — a route "start" is the nearest same-floor waypoint within 60 units; otherwise `NO-DATA route-start` — cost if wrong: none (a diagnostic classification only).
66. **R66** — the ladder launch template always passes `--auto-swap` — cost if wrong: none.
67. **R67** — the rung-0 instrument parameters (MoveScale rate, clock-string rate, back-pressure wait count) are registered in plan Amendment A4 as instrument parameters, not acceptance bars — cost if wrong: none.
68. **R68** — a rung-0 FAIL is recorded in the `LADDER` line and the ladder continues its rounds regardless (a `RUNG0-NO-DATA` for missing instruments also continues) — cost if wrong: engaging on a degraded runtime, but visibly recorded rather than silently accepted.
69. **R69** — the lobby's READY re-send fires only when two fresh frames about 1 s apart both show not-ready, since READY is a toggle and a stray re-send would un-ready the player — cost if wrong: a truly dropped READY press waits roughly 2 s longer than it needs to.
70. **R70** — the route time budget derives from the measured follower rate (20 + 3×length/7.5 u/s), capped so at least 120 s of round clock remains for closing and fighting — cost if wrong: a follower stuck but very slowly sliding could burn more round time than intended before the no-progress guard fires.
71. **R71** — when the round clock cannot be read at all, cap the route budget at 360 − 120 − elapsed host seconds since round start (floor 0 → `NO-DATA route-no-time`; no round start reading → 120 s flat) — cost if wrong: round 1's worst-case margin is accepted at ~8.5 s (typical case ~99 s).
72. **R72** — stop the ladder at the first confirmed PASS, per the plan's own "the first round meeting Goal 6 on both scorers IS the acceptance run" — cost if wrong: none (13 of 16 launches went unspent, available if a re-check were ever needed).

### Close-out rulings (added after the whole-branch review, 2026-09-14)

- **R73** — the always-on lock suite keeps one reaper race (4 takers × 2 rounds) and one mutex double-entry check, plus a hygiene stamp tying `scripts/loop_lock.sh`'s blob to the last green `LOOP_LOCK_SLOW_TESTS=1` run — reinstates R14's intent after the close-out smoke removed them — cost if wrong: ~10 s per `build.sh test`.
- **R74** (retroactive tooling default) — ladder launches pin the harness by default, `--live` opts out — the passing run was pinned; unpinned launches read a moving tree — cost if wrong: none.
- **R75** — whole-branch review minors M1–M3, M5–M8, M10–M12 parked to Sprint 6; M4 (`--engage-dy` refused on route/cooperative) and M9 (health-event key names) fixed — cost if wrong: small, listed.
- **R76** — the close-out gate is accepted as title PASS + transition PASS + mission PASS on the same-exe mission rerun (`s5_head_1x_b`); the first mission FAIL was an in-game HELP pop-up pausing gameplay, not a stall — cost if wrong: an intermittent mission stage until Sprint 6 dismisses the pop-up (the scorer fails it honestly).
- **R77** — always-on lock tests may take up to ~30 s (measured 22–27 s at ~71 % host CPU), keeping R73's minimum race — cost if wrong: ~10 s per `build.sh test`.
