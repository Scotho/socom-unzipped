# Current sprint

The loop's aim. The `loop-iteration` skill (`.claude/skills/loop-iteration/SKILL.md`) reads this file instead of carrying a sprint pointer of its own; the controller
updates it when a sprint opens or closes, and whenever the order changes. **If you are a new controller, read
`docs/HANDOFF.md` first** -- it says what is in flight and what is owed (the traps are `docs/HAZARDS.md`); this file says what to do next.

**The goal every sprint serves:** SOCOM II running natively on PC with online play, that a stranger runs by pointing the
launcher at their own r0001 ISO and playing a round against another stranger on a hosted Horizon server -- from a public
repository another person can fork, build and contribute to.

```
branch:       sprint-19 -- OPEN 2026-10-12 10:19Z off main at 3ff74a11 (PR #138, v0.18.0), "the RE foundation" (R360,
              R365), by the main-tree controller (the owner's ruling of 2026-09-28: one controller seated in
              C:\Projects\socom_pc, every other session in its own worktree). Spec
              docs/superpowers/specs/2026-10-11-sprint-19-re-foundation-design.md (APPROVED, R365); plan
              docs/superpowers/plans/2026-10-11-sprint-19-re-foundation.md (the task table, R364-R365 and R368-R374, the
              Log); research docs/research/89-re-foundation-phase0.md and docs/research/h62/; GitHub milestone 9.
              Agents on agent/s19-* worktrees. Lock-free tasks first; chain Z-a waits for a window the owner names (R372).
closed:       Sprint 18 CLOSED 2026-10-12 (R359, full): see "Sprint 18 — CLOSED" below; Sprint 17's block in
              docs/archive/CURRENT_SPRINT-closed-sprint-17.md, Sprint 16's in docs/archive/CURRENT_SPRINT-closed-sprint-16.md.
spec (18):    docs/superpowers/specs/2026-10-01-sprint-18-the-pcsx2-door-design.md (closed with v0.18.0). The Sprint 17 spec
              (docs/superpowers/specs/2026-09-27-sprint-17-sixty-and-the-way-back-design.md) closed with v0.17.0, and the
              Sprint 16, 15, 14, 13, 12 and 11 specs with v0.16.0 down to v0.11.0.
plans:        docs/superpowers/plans/2026-10-11-sprint-19-re-foundation.md (Sprint 19, open). Closed: the Sprint 18 plan
              docs/superpowers/plans/2026-10-01-sprint-18-the-pcsx2-door.md (R339-R344, R346-R347), and the Sprint 17 plan
              docs/superpowers/plans/2026-09-27-sprint-17.md (the task table, the rulings R322-R338, R345, R348, R351-R363, R366-R367 from the global counter, the
              Outcome, the Log newest first -- its entries before 2026-09-29 in docs/archive/2026-09-27-sprint-17-log-to-2026-09-29.md and those to 2026-09-30 ~10Z in docs/archive/2026-09-27-sprint-17-log-to-2026-09-30.md and to 2026-10-01 ~00Z in docs/archive/2026-09-27-sprint-17-log-to-2026-10-01.md, then docs/archive/2026-09-27-sprint-17-log-to-2026-10-03.md and docs/archive/2026-09-27-sprint-17-log-to-2026-10-11.md; its task book 2026-09-27-sprint-17-tasks.md beside it; GitHub milestone 7).
              The Sprint 16 plan (R299-R321, R314 vacant; docs/superpowers/plans/2026-09-27-sprint-16.md) and the Sprint 15
              plan (R282-R289; R298 the close's window, superseded) with the owner's sitting (R290-R297,
              docs/superpowers/plans/2026-09-26-owner-sitting.md) are closed, Sprint 16's block in docs/archive/CURRENT_SPRINT-closed-sprint-16.md and Sprint 15's in docs/archive/CURRENT_SPRINT-closed-sprint-15.md (moved 2026-10-01); the Sprint 14 plan
              (R269-R281) too, its block in docs/archive/CURRENT_SPRINT-closed-sprint-14.md (moved 2026-09-28); the
              Sprint 13 plan's block is in docs/archive/CURRENT_SPRINT-closed-sprint-13.md (moved 2026-09-27); Sprints 12
              and 11 in docs/archive/CURRENT_SPRINT-closed-sprints-11-12.md; Sprint 10's and older in
              docs/archive/CURRENT_SPRINT-sprints-9-to-11.md (the 2026-09-25 split, R268).
issues:       milestone 8 closed 2026-10-12 (#121-#129 closed, none carried); milestone 7 closed 2026-10-12: #94, #91, #71, #70, #57, #41, #28 carried to the backlog; #59, #42,
              #32, #26 moved there under R367 (O36).
human tasks:  docs/HUMAN_TASKS.md      playtest script: docs/PLAYTEST.md
git strategy: docs/GIT_STRATEGY.md     contributing: CONTRIBUTING.md
rulings:      indexed in docs/RULINGS.md (generated: every ruling with its status and home, Sprint 10's
              R181-R244 ledger table below included) and numbered from the one counter line, docs/HANDOFF.md
              section 2 (Sprint 14 D2).
baselines:    the suite counts live in `docs/DEVELOPING.md` (the table under "Build, run, verify — a newcomer's first hour", rows 3–4) and nowhere else -- this
              line said C++ 686/686 and Python 1457 from 2026-09-20 to 2026-09-22, four sprints after they stopped
              being true, which is why `tools_py/tests/test_doc_maintenance.py` now refuses an undated count outside
              that file. `./build.sh test` exit 0 on the renamed tree (2026-09-25); last green gate: Sprint 18's close chain `s18_close_chain_20261012_085942` on `c57ea088` (2026-10-12 09:00Z-09:35Z: the Python suite 4037 `OK`, `ps2x_tests` 1328/1327/0, gate PASS 3/3, PINS MATCH 13, HELDOUT 12/12, FRAME mean 17.20 worst1s 18.18, SYNCV 24.3/s; the release step red on `iphlpapi.dll`, fixed in `7d12f7ed`, then green by hand); before it Sprint 17's close chain `s17_close_chain_20261012_060736` on `ed519ae5` (2026-10-12 06:07Z-07:04Z: the Python suite 3984 `OK`, `ps2x_tests` 1286/1285/0, gate PASS 3/3, PINS MATCH 13, HELDOUT 12/12, FRAME mean 17.20 worst1s 18.18, SYNCV 24.5/s -- the close proof); before it Sprint 17's chain 2 `s17_adopt_chain2` on `b1b3f023` (2026-10-04 17:34Z-18:53Z: gate PASS 3/3, PINS MATCH 13, HELDOUT 12/12, FRAME mean 17.06 worst1s 17.86, SYNCV 25.3/s -- research/85's adoptions); before it Sprint 17's batch-6 chain `s17_b6r3` on `368afa8c` (2026-10-02 19:02Z-21:08Z: the Python suite 3976 `OK`, gate PINS MATCH 13, HELDOUT 12/12, FRAME mean 16.99 worst1s 17.86, SYNCV 23.1/s -- N1c's adoption gate; the gate and lock fixes in); before it Sprint 17's batch-5 chain `s17_b5` on `1fd3cfdb` (2026-09-30 07:37Z-08:38Z: the Python suite 3939 `OK`, `ps2x_tests` 1159/1158/0, gate PINS MATCH 13, FRAME mean 16.72 worst1s 17.24, SYNCV 23.3/s -- C1's adoption gate; C2, the refusal count, N1 and #116-#118 behind it); before it Sprint 17's batch-4 chain `s17_b4d` on `881c5a18` (2026-09-29 10:03Z-10:55Z: gate 3/3 PINS MATCH, FRAME mean 16.90 worst1s 17.86, SYNCV 23.4/s; the quiet gates on that exe 16.67-16.92 ms, the VBlank cap); before it Sprint 16's batch-3 chain `s16_b3` on `aa030d1a` (2026-09-27 18:57Z-19:56Z: gate 3/3 PINS MATCH, HELDOUT 12/12,
              the player archive); the close gate `s16_b4g` by hand on the batch-4 exe `2430919f…` (2026-09-28 01:00Z-01:16Z: 3/3 PINS MATCH,
              HELDOUT 12/12, FRAME mean 28.82; the chain itself red on HEAD moving under other sessions' commits); the quiet baseline F0's three gates on `4cbbb14f` (median 27.09 ms, spread 7.0 %); before them the Sprint 14
              close chain `s14_close1` on `352fed01` (2026-09-26 15:29Z-16:19Z: gate 3/3 PINS MATCH, HELDOUT 12/12; the
              Sprint 14 plan's Log, 16:20Z); before it (Sprint 13, 2026-09-25): `s13_proof4_gate` 3/3 PINS MATCH (exe f90eeec0..., 22:16Z), `s13_v4_gate1` PASS on the
              same exe (23:51Z), `s13_proof3_gate` 3/3 (r0001, 20:54Z), `s13_names_r0004_gate` 3/3 PINS MATCH (r0004,
              d027546d...); the plan's Log has each; audio parity
              `s16_v0_t1b` 12/48 on the merged tree (2026-09-27, issue #91: the ambient bed 11 dB low then, 7-10 dB since R348; the Sprint 9 capture `s9_q1_parity_ours2` still reads 31/48 under today's compare)
```

Markers used below: **[A]** autonomous; **[O]** the owner's hands, ears, money or decision; **[B: x]** blocked on x.
"Lock-bound" means it needs a build or a launch: the loop lock, and a window -- announced by the session for a build,
named by the owner for a game run (the sitting's ruling of 2026-09-26, R297); "lock-free" can run at any time.

---

## Sprint 18 — CLOSED 2026-10-12 (merged to `main` as `v0.18.0` at `3ff74a11`, PR #138, 10:16Z; the record of the sprint is the block below)

**Close-out (the PR body).** Opened 2026-10-01 02:40Z beside Sprint 17 ("the PCSX2 door", the owner's word of
2026-10-01). It closed 2026-10-12 in full under R359: T0 and T7 ran in R352's window, with INSTALL granted by R366.
Every merged branch was reviewed by a fresh agent. Landed:
- **T1, the box's name service:** `socom-dns` on 53/udp answers SOCOM II's six host names. It was deployed
  2026-10-02 and the port opened 2026-10-11 (O33(a)).
- **T2-T6 and T10, the launcher's PCSX2 client:** a NATIVE/PCSX2 toggle with separate files (`launcher.json`,
  `config.pcsx2.json`); the PCSX2 page with SELECT, INSTALL (the official release, its digest, `tar.exe`) and the
  BIOS count; PLAY, DISC and ONLINE in the PCSX2 view; and LAUNCH, which writes PCSX2.ini's `[UI]` seed and
  `[DEV9/Eth]` and the guarded pnach, with LAST RUN.
- **T8 and T9:** `docs/PCSX2_PLAY.md` and the launcher's icon.
- **T0, the spike:** research/90.
- **T7, the proof:** from a clean home, INSTALL fetched v2.8.2 from GitHub; LAUNCH, the game's own network wizard on
  automatic answers, and a persona made in the game took it to our lobby (2026-10-12 08:34Z). The box's name
  service answered, and LAST RUN read "PCSX2 closed" (KNOWN §1, `logs/s18_proof/`).

The close proof: chain `s18_close_chain_20261012_085942` on `c57ea088`: gate 3/3 PASS, PINS MATCH (13), HELDOUT 12/12, FRAME 17.20 / 18.18 ms, exe `0f670cc4…`; its release step found `iphlpapi.dll` unknown to the audit (fixed in `7d12f7ed`, test first), and the release build then ran green. Issues since the open: opened 10, closed 9 (#121-#129, the
task issues), carried 0; #132 (the launcher `--screenshot` segfault) to the backlog; the highest #132. Milestone 8 closed. The Outcome in the plan has each task's bar.

Next: Sprint 19, the reverse-engineering sprint, opens off `main` (R360, R365; spec
`docs/superpowers/specs/2026-10-11-sprint-19-re-foundation-design.md`, plan
`docs/superpowers/plans/2026-10-11-sprint-19-re-foundation.md`).
