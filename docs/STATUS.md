# Project status — "Current state" below is kept current; the dated log that stood under it is archived

## Current state (keep it short; update when it changes, dated entries below are the log)
- **2026-09-26 05:17Z -- Sprint 14 ("guards, not sentences") is OPEN on `sprint-14` off `main` at `6a82caaa`, where Sprint 13 merged to `main` as `v0.13.0` (PR #61).** Live state: the plan's Log (`docs/superpowers/plans/2026-09-26-sprint-14.md`); the block: `docs/CURRENT_SPRINT.md` "Sprint 14 -- OPEN". No feature work (R269-R277). Next: Sprint 15 (R276). Owner rows: O16, O18.
- Older state bullets: the twenty below the one above (2026-09-19 to 2026-09-25 early) became dated
  entries of the log below on 2026-09-25, verbatim, one each (Sprint 13 Task R1, R268). This block has a byte
  ceiling (`tools_py/docmaint.py` `CEILINGS`): when the state changes, replace the bullet above and make the old
  one an entry.
- Build: `./build.sh all`; tests `./build.sh test` (the Python suite first, then `ps2x_tests` + the VU1 fixture verify + `--vram-diff`). Gate: `python -m tools_py.parity.gate` -- title/transition/mission, the mission stage requiring live gameplay.
- Next: `docs/CURRENT_SPRINT.md`'s `branch:` line says which sprint is open, and its top block what to do; this line
  carries no sprint number any more. New controller: `docs/HANDOFF.md` first. (This line read "Sprint 9 milestone P"
  from 2026-09-20 to 2026-09-23 -- a milestone that had ended in the `playtest-1` tag two sprints earlier -- and then
  "Sprint 10 is CLOSED, what is left is the merge and `v0.10.0`" from 2026-09-23 to 2026-09-25, through Sprint 11's
  whole life and its close review: twice the single most misleading sentence in any live document, which is why it
  now points instead of stating.)



## Where the log went

Until 2026-09-26 a dated log stood here, newest first, about 2,500 lines back to the first boot; it is archived
verbatim in `docs/archive/STATUS-log-to-2026-09-26.md` (Sprint 14 Task S1, R272), and a STATUS entry cited by date
before that day means that file. What merged and when is `docs/CHANGELOG.md`, generated from the merge commits and
the `v*` tags (`python -m tools_py.changelog`); why is the merge commit's message and the open sprint's plan, its
"## Log" (`docs/superpowers/plans/`, the plan `docs/CURRENT_SPRINT.md` names). Nothing is appended below this
paragraph any more: where the block above says "the log below" or "make the old one an entry", a superseded state
bullet goes to the plan's Log.
