# Current sprint

The loop's aim. `docs/LOOP_PROMPT.md` reads this file instead of carrying a sprint pointer of its own;
the controller updates it when a sprint opens or closes.

branch: sprint-5
spec: docs/superpowers/specs/2026-09-13-sprint-5-control-readout-and-first-kill-design.md
plan: docs/superpowers/plans/2026-09-13-sprint-5-control-readout-and-first-kill.md
ledger: .superpowers/sdd/2026-09-13-sprint-5-control-readout-and-first-kill/progress.md

Acceptance test (the active goal): a two-instance online match on local Horizon, driven by
`tools_py/parity/online_match_ours.py --until-kill`, ends in a kill attributed by signals from different
objects and processes (plan "Goal" line; spec §5).

Commit conventions, lock protocol and run rules: the plan's "Handoff notes for the executing model" and
"Global Constraints" sections. Those sections win over anything older.
