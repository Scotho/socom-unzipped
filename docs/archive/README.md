# docs/archive

Documents that were superseded and would mislead a reader who took them for instructions. **Nothing here is an
instruction.** They are kept whole and unedited because other documents cite them as the record -- retractions marked
in place, how a sprint was opened, what a handoff once said.

Opened 2026-09-20 at the controller handoff. Sprint 11 Goal 1 decides whether this directory is published (under
`docs/dev/`), kept private, or deleted.

The **Was** column gives each file's path *before* the move. Those paths are gone by definition, so they are written
in italics rather than as backticked citations -- a backticked path in this tree is a claim that the file is there,
and `tools_py/docmaint.py`'s check 6 holds every document to it.

| Here | Was (the old path; gone) | Why it moved | Still cited by |
|---|---|---|---|
| `HANDOFF-reference-to-2026-09-13.md` | *docs/HANDOFF.md* | Its "START HERE" described Sprint 5 as the sprint in flight, four sprints late, and it was the first file the loop prompt sent a new agent to. Its reference half (run recipes, the env-gated diagnostics list, gotchas, landmarks) is still useful. | `docs/KNOWN.md` §3, `docs/STATUS.md`, `docs/process-audit.md`, `docs/research/17` and `18` -- wherever they say "`HANDOFF.md` Open items, item N", the retractions are marked in place in this file. `scripts/parity/env.sh` and `online_match_frostfire.sh` cite its note on the advertised address. |
| `HANDOFF-2026-09-08.md` | *docs/HANDOFF-2026-09-08.md* | A one-day handoff from the project's first week; it mandates a commit trailer for a model that no session here runs. No inbound citations. | -- |
| `HANDOFF-AUDIT-2026-09-14.md` | *docs/HANDOFF-AUDIT-2026-09-14.md* | The audit that opened Sprint 6. History. | `docs/STATUS.md`, the Sprint 6 spec and plan |
| `CURRENT_SPRINT-to-sprint-8.md` | the dated blocks of *docs/CURRENT_SPRINT.md* from Sprint 5's pause to Sprint 8's close | The live file had become a reverse-chronological log in which the order of work was one paragraph among thirty, with four superseded sets of "standing rules" and "next" lists below it. | `docs/AUDIT-2026-09-17.md` (its §4 lists the drift it found there) |

Not moved, on purpose: the Sprint 1-6 specs and plans under `docs/superpowers/` (cited by path in hundreds of places;
they move in Sprint 11 Goal 1, as one block, with a link check), and `docs/parity/REPORT.md` (`tools_py/parity/compare.py`
names it).
