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

## `sprints-1-6/` — the closed sprints' specs and plans

Moved 2026-09-23 (Sprint 11 Goal 1). Twelve files, one spec and one plan per sprint, kept verbatim under a banner
each. They are the design record of Sprints 1 to 6; every one of them describes work that is finished, and a reader
who took one for the current plan would be six sprints out.

They stayed under `docs/superpowers/` for a sprint after they died because this file said so — *"cited by path in
hundreds of places"* — and nothing could catch a citation a move had broken. `tools_py/docmaint.py`'s **check 6** is
what made the move safe: every backticked `docs/` path in the tree must exist, so a stale citation is now a test
failure. Forty-three citations were re-pointed in the same commit.

The files here are class **A by location** (`docs/DOC_MAINTENANCE.md` §2): a subdirectory of this one is a block moved
whole, so it needs no registry row — but every file in it still has to carry its banner, and check 5 holds it to that.

| Sprint | Closed | Spec and plan |
|---|---|---|
| 1 — hygiene and native render | 2026-09-11 | `2026-09-10-sprint-1-hygiene-and-native-render-design.md`, `2026-09-10-sprint-1-hygiene-and-native-render.md` |
| 2 — host render and family B | 2026-09-11 | `2026-09-11-sprint-2-host-render-and-family-b-design.md`, `2026-09-11-sprint-2-host-render-and-family-b.md` |
| 3 — render scale and the fourth family | 2026-09-12 | `2026-09-11-sprint-3-render-scale-and-fourth-family-design.md`, `2026-09-11-sprint-3-render-scale-and-fourth-family.md` |
| 4 — visible defects and the first kill | 2026-09-13 | `2026-09-12-sprint-4-visible-defects-and-first-kill-design.md`, `2026-09-12-sprint-4-visible-defects-and-first-kill.md` |
| 5 — control readout and the first kill | 2026-09-13 | `2026-09-13-sprint-5-control-readout-and-first-kill-design.md`, `2026-09-13-sprint-5-control-readout-and-first-kill.md` |
| 6 — correctness gate and online reliability | 2026-09-17 | `2026-09-15-sprint-6-correctness-gate-and-online-reliability-design.md`, `2026-09-15-sprint-6-correctness-gate-and-online-reliability.md` |

Sprint 5's plan is a citation of record in `docs/STORY.md` and `docs/story/timeline.json` (the first online kill), so
its path is load-bearing beyond this directory. The Sprint 1–6 plans are also still read by the ruling counter — their
`## Rulings made on the owner's behalf` sections hold live ruling numbers, and `max_ruling()` scans this directory for
exactly that reason.

Not moved, on purpose: `docs/parity/REPORT.md` (`tools_py/parity/compare.py` names it).
