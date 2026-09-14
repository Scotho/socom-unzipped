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
