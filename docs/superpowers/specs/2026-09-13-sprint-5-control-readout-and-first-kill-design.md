# Sprint 5 — control on the test map, a kill readout from sourced offsets, and the first kill: design

Status: written 2026-09-13 as the revision of `docs/ROADMAP.md` §6 "Sprint 5" (drafted before
Sprint 4's Task 8 finished); amended twice the same day after independent review and to fold in
`docs/research/19-community-and-engine-resources.md` (`7e81197`). Scope rests on the owner's
standing instruction to proceed autonomously toward the acceptance test and on the owner's
2026-09-13 decision that the default test map is **Frostfire**. Branch `sprint-5` off `develop`
**after** `sprint-4` is merged. Executor: an Opus-class model following
`docs/superpowers/plans/2026-09-13-sprint-5-control-readout-and-first-kill.md` with
superpowers:subagent-driven-development. **Goal N here is Task N in the plan.**

**Authority.** `docs/KNOWN.md` (at `90c6b45` or later) wins over this document wherever they
disagree. Every numeric bar names at least one failure class it does **not** separate. Community and
reCOM facts are **believed, not proven** until the bar here is met on our binary.

## 1. Where Sprint 4 and research/19 leave things

- **The online movement blocker is fixed and proven on Medley only**: `sceInetInterfaceControl(0x200)`
  returned a constant; same-binary A/B in one match (`abf35bb`, `5ed29ca`).
- **Two movers close Medley** 1485.5 → 50.0 units true 3-D in ~127 s (`ours_task8_kill2`); the
  rifles fired; the players were **never** inside any contact gate. Whether damage was dealt is
  **unknown** (the offsets then watched were not health).
- **Health and life state are sourced** (`KNOWN.md` §1, `research/19` F1): `actor+0x1044` (float,
  1.0 full, `<= 0` dead) and `actor+0xF7A` (byte, 1 = alive; setter `FUN_00544210`). Team id at
  `actor+0xC8` (community values, inference). **Never read live online.**
- **The round-state object is `*0x437ce8`** (`CZNetGame`, `research/19` F2, re-verified against
  `FUN_002a76d0`): valve pointers `ng+0x0c` `mp_round_count`, `+0x10` `mp_game_over`, `+0x14`
  `player_team`, `+0x20` `mp_major_game_state`, `+0x24` `mp_minor_game_state`, `+0x2c` `late_joiner`,
  `+0x58/+0x5c` `aiteam_00/08` (believed alive per team — inference), `+0x70` `total_mp_kills`; a
  valve is `{char *name @+0, short value @+4, …}`. State bytes `+0x113/+0x114/+0x115` set by
  `FUN_002a7490`/`FUN_002a7420`/`FUN_002a73b0`. **`ng+0xde` is the game's own network-lag flag**:
  `FUN_00594cf0` sets it to 1 when idle ≥ 4501 ms and 0 below — but only on frames where it reaches
  the move-scale code. Round clock string at `0x408f10`. Value semantics are inference.
- **The best Frostfire lead is uninitialised memory** (`research/19` F3): bytes the `CZNetGame`
  constructor never writes read `0xAF` on ours and `0x00` on the console, among them `+0xd2`, the
  "You are a ghost" flag (set for late joiners by `FUN_001f5e70`, cleared on new round by
  `FUN_001f6660`). Guest `_malloc_r`/`_memalign_r`/`_realloc_r` are bound in `Compatibility.cpp`
  onto `PS2Runtime::guestMalloc`/`guestRealloc`, which recycle memory. Divergence measured;
  causation not.
- **Our valve pool is 0x20 lower than the console's**; resolve every address through a pointer.
- **On Frostfire neither player moved** (`ours_task8_frost1`, one run): `FUN_00553dc0` called 18 times
  in 0.6 s at round start and never again.
- **Engagement logic is untested live**; the lobby reaches gameplay ~4 in 10 and failures cluster
  (`kill4`–`kill7` four in a row; `kill5` burned 800 s reaching READY without a launch).

### 1.1 Where the move path can be silenced

`FUN_00551ec0` dispatches the controller: its guard's true arm calls `controller->vtbl[0x14]` =
**`FUN_00592560`**, its else arm `controller->vtbl[0xc]` = **`FUN_00594cf0`** (both vtables `0x4062d0`
and `0x6694b0` carry `0x594cf0/0x592560/0x5979a0` at `+0xc/+0x14/+0x18`). `FUN_00592560` runs
**instead of** `FUN_00594cf0`, always returns 1 and never reaches the move path; it tests time since
`actor+0xfb4` > 5 s and writes `+0xfcd/+0xfce` (respawn-like, unproven). `FUN_005979a0` (`+0x18`) holds
research/19's spectator branch (`ng+0xdc == 0 || ng+0xd2 != 0`). `FUN_00551ec0` also carries the online
respawn gate the r0001 "Enable Respawn Offline" community code nops at `0x55205C`.

Inside `FUN_00594cf0` both move-scale calls sit in `if (cVar7 == '\0')`, reached only when: no early
return on the valve `*(short *)(DAT_0043668c + 4)` ∈ {1, 2} (name unresolved) or `DAT_003df1b0 == 0`;
`controller->vtbl[0x8c]` = `FUN_00566940` (auto-move) returned 0; and the multiplayer snap-back
(`DAT_004365c0 - actor+0x420 > 0.6`, excluded on Medley only) did not fire. The `ng+0xdc && !ng+0xd2`
test there comes **after** both calls. So a ghost silences the move path upstream (dispatch to
`FUN_00592560`, the respawn gate, or the spectator path), not inside `FUN_00594cf0`.

## 2. Judgement on the ROADMAP's original Sprint 5

Its spine — measure before fixing, the harness gating itself, then the kill — was right. Its Tasks
0–2 were done inside Sprint 4, Task 5 was done on Medley, and Task 6 rested on "once the scale is 1.0
the players move", false on Frostfire. It did not know about Frostfire, the absent contact, or that
`PASS` cannot print. research/19 has since **collapsed** the health search to a confirmation and named
the round state.

| original item | verdict |
|---|---|
| Task 0 carry-over | done in Sprint 4 (9a) |
| Tasks 1–2, `0x200` cause and fix | done; the "value moves" unit test was never written → Goal 4 |
| Task 3 harness | holds, narrower → Goal 3 |
| Task 4a SP health search | collapsed to one confirmation → Goal 2 |
| Task 4b round-end readout | replaced by the `CZNetGame` valves and the clock string; `respawn` is a fallback |
| Task 5 calibration | done on Medley; partial-deflection aim is new → Goals 2, 5 |
| Task 6 first kill | holds on changed premises → Goals 5–6 |
| Task 7 HLE audit | holds, gains leg zero → Goal 4 |

## 3. Sprint goals, in order (Goal N = plan Task N)

0. **Preconditions** (no build, no run): a heartbeat lock with `loop_lock.sh run <owner> -- cmd` so
   nothing is reapable while work is in progress; `build.sh test` running the Python tests; the loop
   prompt aimed at this sprint; a stale-driver kill script; a plan preflight.
1. **Frostfire control handover.** Zero runs first (valve map, branch table, Goal 4's object diff, the
   pure control scorer from Goal 3), then a **zero-fill guest-allocation knob** built before any
   launch, then **launch 1** peeking `CZNetGame`, its self-identifying valves, health/life/team, the
   clock and the snap-back pair, and tracing the dispatch (`FUN_00551ec0`, `FUN_00594cf0`,
   `FUN_00592560`, `FUN_005979a0`), the move path, and the round-state, ghost and life setters.
   `ng+0xd2 != 0`, or `+0x113/+0x114` stalling when the move path stops → launch 2 is the zero-fill
   A/B. **One Medley control launch is unconditional** (the peek baseline and the clock round-end
   negative control). Caps: 3 usable / 8 launches, then a mandatory map ruling.
2. **Confirm the kill readout in one single-player run** (`+0x1044` steps down to `<= 0`, `+0xF7A`
   leaves 1), with partial-deflection yaw, pitch and at-rest facing calibrations riding along.
3. **An online harness that cannot spend a match proving nothing**: pure scorers (the control scorer
   lands before Goal 1's launch), controllable precondition, move-path liveness, starvation watch,
   valve reads that fail as `NO-DATA`, frame freshness — all under `build.sh test`.
4. **HLE and heap liveness audit**: leg zero (object-keyed uninitialised fields, before Goal 1's
   launch), static census with call-site consumer classes, `PS2X_HLE_STATS`, the `0x200` moves test.
5. **Engagement ladder** — controllable → contact → damage — with partial-deflection aim and a
   **two-sided** traffic rule: each side's scale is restored only by the **other** side moving, so the
   victim strafe-oscillates, the shooter micro-strafes between bursts, and **when a side alarms the
   other side moves** — measured live first, then proven in a sim whose negative test deadlocks
   without the rule.
6. **The acceptance run**, attributed by signals from different objects and processes, requiring that
   the killer fired from inside the contact gate, read by two scorers with different primary signals.
7. **Close-out.**

## 4. Non-goals

- Speed work frozen. Defaults unchanged; **the zero-fill knob ships off** unless Goal 1 proves it is
  the fix (a default change is then a ruling with a gate run).
- No patches to recompiled game logic, no community code patches, no guest-memory writes in any
  acceptance path.
- Skeleton root decay, soft-double chain, gameplay-state gate probe, mixed match, lobby hardening,
  `gate.py --baseline`, flake policy → Sprint 6.

## 5. Definition of done — each bar with the class it does not separate

- **Goal 0:** lock record `<owner> <epoch> <heartbeat> <purpose>`. `loop_lock.sh run <owner> -- cmd`
  takes, renews every 60 s while `cmd` runs, releases on exit; `run_detached.sh` renews from the job.
  **Busy list:** `socom2*.exe`, `pcsx2-qt.exe`, `cmake`, `ninja`, `clang*`, `ld*`, `ps2_recomp.exe`,
  `ps2x_tests.exe`, `vu1_replay.exe`, and any `python` running `tools_py.parity` or `unittest`.
  Reap only when the heartbeat is ≥ 15 min old **and** the busy list is empty; the stale break's clock
  is the **heartbeat** (≥ 45 min) and it is refused while anything on the busy list runs. A lock may
  not be held across tool calls except through `run` or `run_detached.sh`. Atomic claim; tests with
  fakes. *Blind:* a hung job whose wrapper keeps renewing is never reaped — `.done` markers and log
  growth are the progress evidence.
- **Goal 1 — movement bar** (per side, actor rows): net displacement from hold start to 1.5 s after
  release of a 2 s forward hold ≥ **40 units** (*blind: a half-decayed scale that still covers 40, or
  motion in the wrong direction; and the converse — a controllable hold blocked by geometry, hence any of up to 4 holds passes*); position 2 s after release within **10 units** of the position at
  release (*blind: a correction arriving later than 2 s*); net drift over a 10 s neutral window
  ≤ **5 units** (*blind: a frozen player passes it trivially — it only means something alongside the
  40*). Also reported: time from first in-game row to first passing hold. *Not reproduced* = the bar
  on **2 of 2** usable Frostfire runs; *fixed* = the bar after a change on Frostfire and on Medley,
  `build.sh test` and gate green; otherwise a condition sentence and the Medley ruling. Two Frostfire
  `NO-CONTROL`s during Goal 5 also trigger the Medley ruling.
- **Goal 2:** one SP run in which `+0x1044` takes ≥ 1 value strictly between 1.0 and 0.0 and then
  `<= 0`; `+0xF7A` leaves 1 within 2 s; watch `reads > 0`, `misses = 0`; actor word 0 still `0x6691a0`
  at the death row. A mission-failure screen with `+0x1044 > 0` (left the mission area) is not a
  death. *Blind: another float in [0, 1] that also changes at death; single-player damage vs network
  damage (rung 3 settles the latter).*
- **Goal 3:** `tools_py.tests.test_online_verdict` green inside `build.sh test`, over the pure scorers:
  `frost1` → `NO-CONTROL`; `kill2` → controllable; ~~`kill3` B → `NO-CONTROL side=B`~~ `kill3` → controllable (amended 2026-09-13: B's actor moved ~65 units; the Sprint 4 reading was the frozen camera record) and `NO-CONTROL side=B` from kill2 A paired with frost1 B; a 20 % snap-back
  and a snap-back after 1.8 s → not controllable; move-scale `#n` stalled 10 s while alive → stalled,
  but not while `+0xF7A != 1` or within 15 s of an `mp_round_count` step (*blind: the watch
  legitimately fires on death or round change, hence the disarm*); a slot that never logged →
  `NO-DATA`; a starvation watch with no NetIdle rows → `NO-DATA` (NetIdle stops with the move path);
  a valve with the wrong name pointer → `NO-DATA`; `respawn` alone → not PASS; an armed watch with zero
  reads → FAIL; a frame file older than 2 s → `StaleFrameError` (*blind: a hung renderer that keeps
  writing new files*).
- **Goal 4:** `docs/research/20-hle-liveness.md` with leg zero's object-keyed diff, the stub table with
  consumer classes and widths, `PS2X_HLE_STATS=1` printing every bound stub (zero-call ones included),
  and a `0x200` moves test. *Blind: a varying-but-wrong return passes a distinct count; the width
  column catches that shape.*
- **Goal 5:** (a) **contact:** ≥ 20 consecutive actor rows inside 3-D ≤ 22 and `|dy|` ≤ 10, R1 injected,
  both instances' move-scale `#n` advancing, the clock string changing, **and both sides' movement scale
  ≥ 0.99 on those rows** (*blind: line of sight and aiming away*; the scale clause closes the
  starved-deadlocked-pair-inside-the-gate class). (b) **aim:** yaw rate at ≥ 5 deflection levels,
  strictly increasing above the dead zone, smallest usable sweep ≤ 5° (*blind: acceleration over a
  1.0 s hold from rest; SP vs two-instance frame rate*). (c) **starvation:** primary signal the game's
  own `ng+0xde` on each instance (never 1 during a contact window); secondary NetIdle `[ret] v0`, alarm
  at **4000 ms**, bar ≤ **5000 ms** (Sprint 4's healthy worst gap was 2.7 s); every alarm clears within
  3 s of the other side moving (*blind: peaks between samples — 4 Hz peek, slower under load; `ng+0xde` is stale when the move
  path is silent — then `NO-DATA`*). (d) **rung 3 — damage:** the victim's `+0x1044` drops below 1.0
  during contact with the killer's R1 injected in the preceding 3 s and the victim's actor y not
  dropping > 20 units in the preceding 2 s (*blind: an environmental damage source coinciding with a
  burst at a stationary target*).
- **Goal 6 — PASS requires all of:** on the victim's instance `+0x1044 <= 0`, `+0xF7A != 1`, word 0
  intact; **R1 injected by the killer within 3 s before the death with the pair inside the contact gate
  throughout that window**; on the killer's instance `total_mp_kills` steps by one; the victim's team
  read from the victim instance's `player_team` valve (`*0x437ce8+0x14*:2`) and cross-checked against
  `actor+0xC8`, and **that** team's `aiteam_*` dropping by one on both instances within 2 s (host wall
  clock at read, ±0.5 s); the killer's own `+0x1044 > 0`; no victim y drop > 20 units in the 2 s before;
  no grenade injected on the victim in the 10 s before; `mp_round_count` not stepped and the clock not
  `00:00` before the death; both screens within 2 s; exit 0; `verdict_replay.py` (primary: valves)
  agrees with `KillWatch` (primary: actor fields). The unconditional Medley clock round-end control
  must show neither `total_mp_kills` nor `+0x1044` stepping. *Blind:* `total_mp_kills` and `aiteam_*`
  semantics are inference (a suicide, fall or team kill may step them — hence the fall, grenade and
  team checks); a death from a defect in the game's damage path that coincides with the killer's burst
  from inside the gate is narrowed, not excluded. One run; the launch count is recorded.
- **Close-out:** `PS2X_TEST_REPEAT=3 ./build.sh test`; final gate PASS 3/3, title s00–s19 ≥ 99 run-vs-run;
  `KNOWN.md` audited; Outcome section; the controller merges.

## 6. Sequencing, budget, risk and realism

```
Goal 0 ─┬─> Goal 4 leg 0 + Goal 3 pure control scorer (zero runs) ─> zero-fill knob build ─> Goal 1 launches (incl. Medley control) ─> ruling ─┐
        ├─> Goal 2 SP run (lock, independent) ─────────────────────────────────────────────────────────────────────────────────────────────────┤
        └─> Goal 3 harness wiring (Sprint 4 Task 8 landed)  ───────────────────────────────────────────────────────────────────────────────┴─> Goal 5 ─> Goal 6 ─> Goal 7
Goal 4 legs 1–2 fill lock time; PS2X_HLE_STATS rides the zero-fill build
```

- **Budget, plainly.** At most 8 (Goal 1) + 14 (Goal 5) + 10 (Goal 6) = **32 online launches plus two
  single-player runs**, ~5.5 h of lock at ~10 min a launch and realistically more (a successful match
  is 12–15 min). That fits a cron loop overnight, not one context. At the measured 4-in-10 lobby rate
  the chance of reaching each task's usable-match target inside its launch cap is: Goal 1 ≥ 3 of 8,
  **69 %**; Goal 5 ≥ 4 of 14, **88 %**; Goal 6 ≥ 4 of 10, **62 %**. Four lobby failures in a row pause
  the task for one lock-free step before relaunching.
- **Medley fallback.** Movement proven; two movers close it in ~127 s. Taking it does not reverse the
  owner's map decision (`--map` is a flag; the ruling is recorded).
- **Risks.** Frostfire deeper than the ghost flag (caps and ruling); the zero-fill A/B reads only if the
  knob-off instance reproduces the failure; network damage not writing `+0x1044` (rung 3 checks, ~10
  launches before the acceptance run would); partial deflection with a dead zone (measured first);
  starvation in the endgame (measured live in Goal 5 Step 1, modelled in the sim, watched two-sided);
  valve semantics as inference (the negative control).
- **Realism.** A kill in Sprint 5 is **roughly even odds**: better than before research/19 because the
  readout no longer needs a search. It hinges on (1) Frostfire's handover being the uninitialised
  ghost flag or otherwise bounded — or the Medley ruling being taken promptly — and (2) the engagement
  reaching contact at matched height with both scales fed, which has never happened. Goals 0–4 each
  land value on their own.

### 6.1 research/19 — folded in

| goal | what changed |
|---|---|
| 1 | valve map is F2 (re-verified); leading hypothesis F3's `+0xd2`; zero-fill A/B pre-built; ghost path traced upstream |
| 2 | scan, static pass and RDRAM fallback gone; one SP run confirms `+0x1044`/`+0xF7A` |
| 3, 6 | round end and attribution from `CZNetGame` valves, `player_team`, `actor+0xC8` and the clock string; `respawn` a fallback; `ng+0xde` as the starvation signal |
| 4 | leg zero (object-keyed uninitialised fields); prosper's consumer classes (F7) |

## 7. Carried over

Sprint 4's STATUS entry, whole-branch review, merge and ledger archiving (the controller's); skeleton
root decay; soft-double chain (host-`double` differential tests first); `movie_blocks.py` wiring;
title-gate client-rect assertion; lobby hardening (pull forward if Goal 5 or 6 loses more than half its
launches to the lobby); writer-PC watches (PS2Recomp PR #157) if Goal 1 needs *who* writes `ng+0xd2`;
`KNOWN.md` §2's parked-opponent question on the **console** (Goal 5 Step 1 settles ours only).
