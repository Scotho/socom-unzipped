# docs/archive

Documents that were superseded and would mislead a reader who took them for instructions. **Nothing here is an
instruction.** They are kept whole and unedited because other documents cite them as the record -- retractions marked
in place, how a sprint was opened, what a handoff once said.

Opened 2026-09-20 at the controller handoff. It is published where it stands, with the rest of the tree: decision
D4's default -- "all of it stays where it is; nothing moves to `docs/dev/`" -- has stood since 2026-09-23
(the decisions table of `docs/archive/HUMAN_TASKS-to-2026-09-25.md`; row O3 of `docs/HUMAN_TASKS.md` since 2026-09-25), and the repository has been public since 2026-09-20.

> Superseded 2026-09-25 (Sprint 13 R2): this said "Sprint 11 Goal 1 decides whether this directory is published
> (under `docs/dev/`), kept private, or deleted" -- a decided question written as open (documents audit row 65).

The **Was** column gives each file's path *before* the move. Those paths are gone by definition, so they are written
in italics rather than as backticked citations -- a backticked path in this tree is a claim that the file is there,
and `tools_py/docmaint.py`'s check 6 holds every document to it.

| Here | Was (the old path; gone) | Why it moved | Still cited by |
|---|---|---|---|
| `HANDOFF-reference-to-2026-09-13.md` | *docs/HANDOFF.md* | Its "START HERE" described Sprint 5 as the sprint in flight, four sprints late, and it was the first file the loop prompt sent a new agent to. Its reference half (run recipes, the env-gated diagnostics list, gotchas, landmarks) is still useful. | `docs/KNOWN.md` §3, `docs/STATUS.md`, `docs/audits/2026-09-12-process-audit.md`, `docs/research/17` and `18` -- wherever they say "`HANDOFF.md` Open items, item N", the retractions are marked in place in this file. `scripts/parity/env.sh` and `online_match_frostfire.sh` cite its note on the advertised address. |
| `HANDOFF-2026-09-08.md` | *docs/HANDOFF-2026-09-08.md* | A one-day handoff from the project's first week; it mandates a commit trailer for a model that no session here runs. No inbound citations. | -- |
| `HANDOFF-AUDIT-2026-09-14.md` | *docs/HANDOFF-AUDIT-2026-09-14.md* | The audit that opened Sprint 6. History. | `docs/STATUS.md`, the Sprint 6 spec and plan |
| `CURRENT_SPRINT-to-sprint-8.md` | the dated blocks of *docs/CURRENT_SPRINT.md* from Sprint 5's pause to Sprint 8's close | The live file had become a reverse-chronological log in which the order of work was one paragraph among thirty, with four superseded sets of "standing rules" and "next" lists below it. | `docs/audits/2026-09-17-audit-and-code-review.md` (its §4 lists the drift it found there) |
| `CURRENT_SPRINT-sprints-9-to-11.md` | the blocks of *docs/CURRENT_SPRINT.md* from "Sprint 11 — the record of the sprint" to the end, cut 2026-09-25 (Sprint 13 Task R1, R268) | The live file was 190 KB with about 12 % of it live; a close review read the newest block and never the stack under it (the 2026-09-25 audit, `docs/audits/2026-09-25-project-audit/documents.md` §2). The standing backlog and the ledgers R181-R244 and R245-R263 stayed live; the stale "Standing rules" block was deleted. The live file now has a byte ceiling (`tools_py/docmaint.py` `CEILINGS`). | `docs/KNOWN.md` (the R237 block), `docs/archive/HUMAN_TASKS-to-2026-09-25.md`, both ledgers in `docs/CURRENT_SPRINT.md`, `docs/research/58-other-builds.md` |
| `HANDOFF-loop-history-to-2026-09-25.md` | from *docs/HANDOFF.md*: §2's older pick-up points (nine "Where the loop is now / was" bullets, two "Picking up after ..." blockquotes, three stale state bullets), all of §4 "The work, in order", all of §9 "What the owner said on 2026-09-20" and all of §10 "What the owner should decide before the playtest"; cut 2026-09-25 (Sprint 13 Task R1, R268) | §2 offered twelve pick-up points, three of them "now" and out of date order; §4 laid out Sprint 9's milestones as the order and §10 asked for decisions before a playtest that ran on 2026-09-22 (the 2026-09-25 audit, D11-D14). §2 now keeps one "now" bullet under a byte ceiling. | `docs/HANDOFF.md` §2, §4, §9 and §10 (pointers), `docs/archive/HUMAN_TASKS-to-2026-09-25.md` (the decisions paragraph), `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md` (R175) |
| `HUMAN_TASKS-to-2026-09-25.md` | *docs/HUMAN_TASKS.md* as it stood at `a2699ba0`, whole; cut 2026-09-25 (Sprint 13 Task R4) | 699 lines under a 2026-09-22 banner, seven "Start here" generations and 20 open checkboxes dated 2026-09-17 to 2026-09-21, about half of them superseded and a quarter of them work the loop could take (the 2026-09-25 audit, D50-D53, D61). The live file is one table of what only the owner can decide or do (O1-O15); this one opens with each old item's disposition. | `docs/CURRENT_SPRINT.md` (the Sprint 11 and 12 carry and the R250/R251 rows), `docs/KNOWN.md`, `docs/STATUS.md`'s log, `docs/PLAYTEST.md` (the italic item names), the Sprint 11 and 12 plans, the 2026-09-25 audit's reports (by line), `scripts/parity/capture_audio_out.sh`, `tools_py/tests/test_audio_capture_script.py`, and every archived plan that says HUMAN_TASKS |

Moved the same day, to `docs/audits/` rather than here (they are dated snapshots, class S by location, not superseded
documents): *docs/process-audit.md* is `docs/audits/2026-09-12-process-audit.md` and *docs/AUDIT-2026-09-17.md* is
`docs/audits/2026-09-17-audit-and-code-review.md`. Every citation was re-pointed in the same commit.

## `sprints-7-12/` — the closed sprints' specs and plans, continued

Moved 2026-09-25 (Sprint 13 Task R1): Sprints 7 to 10's four specs and twenty-six plans (every sprint plan dated
2026-09-17 to 2026-09-22, the fix wave's two included), each kept verbatim under a banner inserted after its title.
The directory is named for the span it will hold: the Sprint 11 and 12 specs and plans stay under `docs/superpowers/`
until a later close moves them, because they are still the newest record a controller reads. The pre-sprint design
documents of 2026-09-04 to 2026-09-15 (the recompilation design, the parity harness, the package outline and their
plans) stayed where they are: they are not a sprint's, and nothing yet supersedes them.

It was done the way `sprints-1-6/` was: the files moved with `git mv`, each batch (the audits, the specs, the plans)
followed by `python -m tools_py.docmaint` so check 6 named every citation the batch had left behind, and every
citation re-pointed in the same commit -- full paths, the Sprint 10 ledger's `plans/<name>` shorthand (expanded to
the full new path so check 6 can hold it), the story's generated `timeline.json` and `index.html`, the leak ledger
`tools_py/release/leak_allow.txt` (it keys two allowances by path), two test docstrings and a script comment. Class A by
location, like `sprints-1-6/`: no registry rows, a banner each, and `max_ruling()` reads them (it reads all of
`docs/archive/` since the same day).

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
