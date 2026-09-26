---
name: sprint-close
description: Close a SOCOM Unzipped sprint -- use when the sprint file's close-out item is next: the documentation review and the known-issue stack review with their commands, the close-out commit, the PR to main, the tag on the merge commit, the CLOSED block and the next sprint named.
---

# The sprint close, as a checklist

**A sprint does not close until both reviews have run and their result is written into the close-out commit**
(`docs/DOC_MAINTENANCE.md` §5 and §7 are the full text; `docs/GIT_STRATEGY.md` §2 "Merging a sprint" and §4 the
merge and the tag). The open plan's Task 99 adds the sprint's own close steps.

**Two rules from Sprint 14's Log, for every command below:**
- **Never pipe a check into `tail` before a commit** -- `tail` masks the exit code (an audit's problem went through a
  merge that way, 2026-09-26). Run the check bare, or gate on its last line / `$?`, not on what `tail` returned.
- **`date -u` before every stamp** -- a stamp is read from the clock, never estimated from the sequence of events
  (the Log's stamps ran 2 h 47 min ahead on 2026-09-26). The leak hook's local time is not UTC.

## The documentation review (DOC_MAINTENANCE §5)

1. `python -m tools_py.docmaint` -- exit 0. If it fails, fix the document, not the check. **When the plan's ceiling
   fires** (the open plan's whole-file ceiling, check 7): run
   `python -m tools_py.docmaint archive-log --plan <the plan> --keep 10` -- the Log's entries older than the newest
   ten move verbatim to `docs/archive/<plan>-log-to-<date>.md` with a banner and a class A row, and the Log keeps a
   one-line pointer. It refuses when the Log is not the plan's last `## ` heading: move that section above the Log.
   Never raise the number (R279). The ratchet itself comes last -- see "The ratchet" below.
2. Every L document read for truth, in order: `KNOWN.md`, `CURRENT_SPRINT.md`, `HANDOFF.md`, `HUMAN_TASKS.md`,
   `STATUS.md`'s Current state block, `DEVELOPING.md`, `README.md` -- is every claim still true; is anything the
   sprint closed still listed as open; is anything the sprint opened missing? A fresh read-only agent's table is the
   usual form; the controller acts on it.
3. `README.md` its own pass: README's Status paragraph, sentence by sentence against `KNOWN.md`.
4. Every N document read for live state that has crept in; move it to its L document, leave a pointer.
5. Anything superseded this sprint moves to S or A with a banner naming what replaced it (archive, never delete).
   The appending documents: two CLOSED blocks in the sprint file, the third to the archive; HANDOFF §2 one "now"
   bullet; STATUS's Current state one dated bullet.
6. Stamp `docs/DOC_MAINTENANCE.md`'s **"Last full review"** line with the date (`date -u`) and the sprint; name in
   the close-out commit what the review changed ("changed nothing" is a result too). A wrong document is recorded as
   wrong -- what was claimed, what is true, how long.

## The known-issue stack review (DOC_MAINTENANCE §7)

1. `python -m tools_py.issues audit --stale-since <the day the sprint opened>` -- exit 0 before anything else; fix
   the side that is wrong (row, citation, label or issue), never the check.
2. Every open issue read against the tree: still true (met without `Closes`? close with the artefact); the bar still
   right; the evidence still where the body says; the area right. Comment only when an answer changes something.
3. Every KNOWN §2 row and every live hazard (`HAZARD` / `Open:` headlines) cites an open issue, a closed one read as
   settled, or is ruled out with its reason at its end (*no issue: a lesson, nothing left to fix*).
4. Every issue closed this sprint: `gh issue list --state closed --label known-issue --search "closed:>=<open date>"`
   -- its closing comment names an artefact and the KNOWN row agrees; no artefact means reopen, unless the owner
   closed it (then the row records the owner's words).
5. The carry: `python -m tools_py.issues carry N --comment "..." [--milestone "Sprint N+1"]` for each issue still
   open in the milestone (it refuses one already carried twice -- that is an owner question in `docs/HUMAN_TASKS.md`);
   then `python -m tools_py.issues milestone close "Sprint N" --next "Sprint N+1"`; then
   `python -m tools_py.issues backlog` regenerates `docs/BACKLOG.md` and `python -m tools_py.issues backlog --check`
   exits 0, as does `python -m tools_py.rulings --check`; an item ruled not an issue goes into `docs/backlog_ruled_out.txt` with its ruling and bar.
   `python -m tools_py.changelog --check` exits 0 too (else regenerate `docs/CHANGELOG.md` and commit it, R272).
   `python -m tools_py.flow` regenerates `docs/FLOW.md` (the flow snapshot, M1), committed in the same commit as the
   regenerated changelog; then `python -m tools_py.flow --check` exits 0.
6. Duplicates closed as not planned ("duplicate of #M"); `help wanted` / `good first issue` where they fit.
7. The record: `python -m tools_py.issues tally --since <the day the sprint opened>` -- the one sentence (opened,
   closed, carried, highest number) for the close-out commit and the plan's Log (and STATUS's Current state bullet), with what the review changed.
   Then `python -m tools_py.sitting` regenerates `docs/SITTING.md`, the owner's page, from the carry and the
   rulings just settled, and `python -m tools_py.sitting --check` exits 0 (R271, Sprint 14 D3).
8. The circuit breaker (R271, DOC_MAINTENANCE §7 step 8): an O row that has stood through two sittings without an
   answer is closed by default under a ruling, struck with the date and the default that now stands; the owner can
   reopen it by number. The page marks each such row "closes by default at the next close (R271)"; the tool only
   marks -- strike every marked row by hand in `docs/HUMAN_TASKS.md` under a new ruling from HANDOFF's counter, then
   `python -m tools_py.sitting` again and `--check` exits 0.

## The ratchet -- the last step before the close-out commit (DOC_MAINTENANCE check 7)

After every other close edit (HANDOFF §2, STATUS's block, the sprint file's CLOSED block), and while
`docs/CURRENT_SPRINT.md`'s `plans:` line still names the closing plan:
1. `python -m tools_py.docmaint ratchet` -- each ceiling's live size, current number and proposal (live plus ten
   percent, rounded up to 100, never above the current number).
2. `python -m tools_py.docmaint ratchet --write` -- rewrites the numbers in `tools_py/docmaint.py`'s `CEILINGS`; the
   close-out commit carries that file. A ceiling never goes up.
3. `python -m tools_py.docmaint` -- must print `OK` after the write; if it does not, a close edit landed after the
   ratchet: archive or shrink, never raise.

**R279, short:** the open plan's ceiling is one `CEILINGS` number like the others -- ratcheted here from the closing
plan's size, carried to the next plan, never raised; mid-sprint, `archive-log` on its Log is the remedy.

## The close-out, the merge and the tag

1. **The close-out commit** on the sprint branch, explicit pathspec: both reviews' results in one sentence each, the
   stamped "Last full review" line, `docs/BACKLOG.md`, the sprint file's **CLOSED block** (the sprint's record, the
   Outcome), the plan's Log (and STATUS's Current state bullet), HANDOFF's line, the ratcheted `tools_py/docmaint.py`. `git push origin sprint-N`; `gh run list --commit <sha>` green.
2. **The PR** `sprint-N -> main`: `gh pr create --base main --head sprint-N --title "Sprint N: <its name>"`, body =
   the close-out block from `docs/CURRENT_SPRINT.md`. Wait for `build`, `build-windows` and `leakcheck`, then
   `gh pr merge --merge` -- a merge commit, never squash (the per-task commits are the record cited by hash).
3. **The tag on the PR's merge commit** -- not on `origin/main`'s tip: a slice or an outside PR can land between the
   merge and the tag, and Sprint 13's own tag was briefly pushed on the wrong commit. After `git fetch origin`:
   `sha=$(gh pr view <N> --json mergeCommit -q .mergeCommit.oid)`; `git rev-list --parents -n 1 $sha` must print
   three hashes (the commit, then its two parents); then `git tag -a v0.N.0 $sha -m "Sprint N: <its name>"` and
   `git push origin v0.N.0`. Record the merge hash,
   the PR number and the tag in the CLOSED block's heading (`merged to main as v0.N.0 at <hash>, PR #M`).
4. **The next sprint named**: the CLOSED block and HANDOFF say what comes next -- a sprint the owner or the plan names
   (its spec agreed, its plan written against the tree, its milestone on GitHub, the sprint file's header rewritten --
   the only sprint pointer in the project), or "not yet planned; the owner names it". Until one opens, no sprint
   branch is open and a change goes on a topic branch (`docs/GIT_STRATEGY.md` §2).
