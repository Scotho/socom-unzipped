# Current sprint

The loop's aim. `docs/LOOP_PROMPT.md` reads this file instead of carrying a sprint pointer of its own;
the controller updates it when a sprint opens or closes.

**Sprint 5 is CLOSED, pending merge.** The acceptance test PASSED (ladder launch 2, 2026-09-13:
rounds 1-3 KILL on both scorers — `docs/STATUS.md` Sprint 5 entry, `docs/KNOWN.md` §1). Its plan's
`## Outcome` and `## Rulings made on the owner's behalf` sections carry what actually happened;
`.superpowers/sdd/2026-09-13-sprint-5-control-readout-and-first-kill/progress.md` is the working
ledger (gitignored, deleted once archived). Remaining before merge: the close-out fix wave, a
`PS2X_TEST_REPEAT=3 ./build.sh test` + final gate on a quiet host, and the controller's merge —
plan Task 7's last two boxes.

branch: sprint-5
spec: docs/superpowers/specs/2026-09-13-sprint-5-control-readout-and-first-kill-design.md
plan: docs/superpowers/plans/2026-09-13-sprint-5-control-readout-and-first-kill.md
ledger: .superpowers/sdd/2026-09-13-sprint-5-control-readout-and-first-kill/progress.md

Acceptance test (met — see above): a two-instance online match on local Horizon, driven by
`tools_py/parity/online_match_ours.py --until-kill` (now via `scripts/parity/ladder_frostfire.sh`),
ends in a kill attributed by signals from different objects and processes (plan "Goal" line;
spec §5, §5.1/§5.1.1 for the pre-registered bars actually used).

Commit conventions, lock protocol and run rules: the plan's "Handoff notes for the executing model" and
"Global Constraints" sections. Those sections win over anything older.

**Next: Sprint 6**, per `docs/ROADMAP.md` §6 — lobby hardening, the online freeze root cause,
single-player teleports, the skeleton root decay, a gameplay-state gate probe, exact-oracle math,
a mixed ours/PCSX2 match, and the rest of the revised order. This file gets a new sprint block
(branch, spec, plan, ledger) once Sprint 6's plan exists; until then it still names Sprint 5's
paths above for anyone reading its closed-out ledger.

## 2026-09-15 (evening) — Sprint 6 Task 0 done, Task 1 wired, Tasks 2–3 advanced lock-free

Everything Task 0 owed is on `develop` (`a81eb74` the block-pointer fix; `f6a4434` the depth fix; `326c9c9` the ifpopup
step; `34ed2ac` the gate wiring; `78a81d1` lobby verify-then-act; research/28 and /29). The gate PASSed 3/3 on the
block-pointer exe (`s6_blockptr`, sha `1cfef9af028a90fc…`) **with the mission-failure detector active** — the turn
teleport no longer ends the mission. The runtime freeze at `92d30f0` is over: **the ladder exe is now `a81eb74`'s**, and
the first online result on it must be recorded against that sha.

branch: sprint-6 (created 2026-09-15 evening off develop at `20db94b`; Task 0 and the lock-free Task 1-4 work went to develop first)
spec: docs/superpowers/specs/2026-09-15-sprint-6-correctness-gate-and-online-reliability-design.md (owner review pending)
plan: docs/superpowers/plans/2026-09-15-sprint-6-correctness-gate-and-online-reliability.md
ledger: .superpowers/sdd/2026-09-15-sprint-6-correctness-gate-and-online-reliability/progress.md (create on first dispatch)

**Owner's order, 2026-09-16 (after playing the build with a controller):** (1) the water shards and the occasional
flat-grey hill patch in Seeding Chaos (believed the same defect: geometry drawn untextured) — Task 5a; (2) the untested
online maps, control rounds without a kill requirement — Task 6b; (3) misc hardening; (4) audio — Task 6c (nothing
SOCOM plays reaches the host backend); (5) the launcher: an r0001 ISO pointer, a pre-launch detail-quality choice, a
visible controller test area, other easy settings (packaging outline §3); (6) the rest of the sprint work in the
controller's order. Gamepad support landed in the SOCOM input path the same day (uncommitted until its gate).

**Next, in order (2026-09-17 afternoon):** the owner's order is done through item 5 — Task 5a water/terrain (research/31), Task 6b the twenty-map sweep (research/33, 19 of 20 play), the guest clock fix and the audio path (research/32: bank sounds, streams, the PCM title music), the launcher first cut (Task 8b, `770d5fb`). The title music is clean (research/32 §7.1, evening: three sceMpeg HLE faults fixed under tests). Now: (1) a ladder launch on the current exe for the 2-of-2 online kill bar (`s6_ladder12`, done: 3 kills in 4 rounds); (2) the owner's hands-on tests — in `docs/HUMAN_TASKS.md` (the title/intro listen, free play, the launcher with the Xbox pad; Task 6c Step 4, Task 8b Step 4), done in parallel; (3) Task 8 harness items -- done; Foxhunt's fall-damage row and the PCM ring's address are settled; (4) Task 7 mixed match; (5) the portable folder (Task 8b Step 5).

## 2026-09-15 — Sprint 6 drafted; lock-bound work queued for an owner window (superseded above; kept for the record)

**Sprint 6 is drafted, not opened**: spec `docs/superpowers/specs/2026-09-15-sprint-6-correctness-gate-and-online-reliability-design.md`
and plan `docs/superpowers/plans/2026-09-15-sprint-6-correctness-gate-and-online-reliability.md` (owner review pending;
Tasks 0–1 are owner-agreed items). Branch `sprint-6` is created only after Task 0's two fix branches merge.
A packaging/launcher/installer outline is at `docs/superpowers/specs/2026-09-15-game-client-package-and-installer-outline.md`.

**Rule since 2026-09-15: builds, gates and launches only in a host window the owner names** (they lag the owner's
machine; a contended mission gate's frame file went stale 176 s). Lock-free work continues in between.

State of the working tree on `fix/gl-depth-precision` (nothing committed):
- Depth fix: `./build.sh test` green (Python 845 OK, ps2x_tests 454/454, vram-diff 15/15); title PASS `s6_depth`,
  transition PASS `s6_depth_r2`; mission FAIL `s6_depth_m2` on the HELP pop-up class only (6/6 gameplay-band holds,
  diffs 0.00–0.05, `s30_holdW.png` shows "PRESS X TO CONTINUE").
- `ifpopup` gate step: `tools_py/parity/drive.py` `popup_present()` + `ifpopup+<delay>:BTN` (test-first,
  `tools_py/tests/test_drive_popup.py` 5/5), one before each of the six holds in `scripts/parity/gameplay_probe.txt`.
  Mission rerun `s6_depth_m3` was killed at the owner's request (host contention) — **one mission gate is owed**.
- README carries the `PS2X_GS_DEPTH_LEGACY` entry (commits with the depth fix).

**Queued for the next window, in order** (plan Task 0; each command is in the plan):
1. `gate --only mission --stamp s6_depth_m4` on the current exe → commit the depth fix and the ifpopup step, push, ff-merge to develop.
2. Branch `fix/gs-block-pointer`; paste the seven-region test (plan Task 0b Step 2); build `ps2x_tests` → RED; the
   two-line fix in `GS.cpp`; `./build.sh runtime && ./build.sh test && gate --stamp s6_blockptr`; motion_pack_check 48 → 0.
3. Open `sprint-6` and start Task 1 (lock-free scorers first).

## Paused 2026-09-14 (owner) — open threads after Sprint 5 merged (superseded above; kept for the record)

Sprint 5 is merged (develop = main = 2ae4d79). Work paused mid-investigation of two Seeding Chaos defects the owner
spotted in gate frames. Both are written up and both have a named cause; neither fix has landed.

- **Branch `fix/gl-depth-precision`** (not merged): the GL depth-precision fix for the grey water shards, plus the
  docs commits made while it was checked out (`6e41064` pipeline blind spot + ROADMAP §6 additions, `b09227f` and this
  KNOWN entry, research/25 and /26). Its build/test/gate run was in flight at the pause — check
  `logs/parity/gate/s6_depth*` and the branch's last commit before trusting anything.
- **Not started: the GS block-pointer fix** (research/25 §9) — the ×8 in `sceGsExecLoadImage`/`StoreImage`, which
  corrupts 48 animation clips and causes the single-player turn teleport. Its independent verification was in flight.
  It needs its own branch off develop, a seven-region round-trip test, and a full gate for blast radius.
- **ROADMAP §6 item 5** gained two owner-agreed additions: a console-vs-ours gameplay image comparison, and a
  mission-failure screen failing the gate's mission stage.

To resume: read `docs/KNOWN.md` §2's two new rows and research/25 §7–§9 and /26, then finish the verification and the
two fixes in that order.
