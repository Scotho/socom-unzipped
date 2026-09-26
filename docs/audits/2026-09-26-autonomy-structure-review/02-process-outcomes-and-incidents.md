# Process outcomes and incidents — SOCOM Unzipped, 2026-08-27 → 2026-09-25

*Evidence file. Read-only pass over the project's own record on branch `sprint-13` at 2026-09-25/26. Nothing was
built, run or edited. Product defects appear only where they are the evidence for a process failure.*

Scope note: the project's git history starts 2026-08-27 and reaches 302 commits on its last day
(`git log --date=short --pretty=%ad | sort | uniq -c`: 2026-09-13 138, 09-19 112, 09-20 127, 09-21 150, 09-23 128,
09-24 114, 09-25 302). Thirteen sprints closed or opened in four weeks. Five process/product audits exist
(`docs/audits/`), plus one disc-derived-bytes audit (2026-09-21) that is not a process document.

---

## 1. What the record consists of

| Artefact | Size / count | Note |
|---|---|---|
| Live docs under `docs/*.md` | 18 files, **1.04 MB** | `docs/KNOWN.md` 266 KB, `docs/STATUS.md` 260 KB, `docs/STORY.md` 121 KB, `docs/DEVELOPING.md` 91 KB, `docs/CURRENT_SPRINT.md` 60 KB, `docs/HANDOFF.md` 37 KB |
| Archived docs | 9 under `docs/archive/*.md` | plus `docs/archive/sprints-*/` subtrees |
| Research notes | 64 under `docs/research/` | numbered to 65; **no 35**, **two numbered 43** (`docs/HANDOFF.md:...` trap 15) |
| Plans | 32 under `docs/superpowers/plans/`, 27 dated ≤ 2026-09-22 | `2026-09-25-project-audit/documents.md:84` |
| Audits | 6 under `docs/audits/` | 2026-09-12, 09-17, 09-20, 09-21, 09-23, 09-25 (+ a 6-report folder) |
| Rulings | **R269 is the next free number** (`docs/HANDOFF.md:33`) | plus `S12-R1..R25` and `S13-R1..R13` in their own namespaces |
| GitHub issues | 32 total, **21 open / 11 closed** (`gh issue list --state all`) | every one created 2026-09-23 or later; the tracker is 2 days old |
| GitHub PRs | 28 total: 23 merged, 3 open, 2 closed | the 3 open are Dependabot bumps open since 2026-09-21 |
| Standing rules | 14 in `docs/HANDOFF.md:71`–`:167`, each with its reason | plus 16 "traps" at `:168`–`:241`, "each of these has already cost someone a day" |
| Claude-side incident notes | **34 `.md` files** in `<home>\.claude\projects\C--projects-socom-pc\memory\` | untracked, outside the repository, not visible to a fresh controller |

---

## 2. The five audits: what each found, what it changed, whether it recurred

### 2.1 `docs/audits/2026-09-12-process-audit.md` (699 lines, end of Sprint 4)

Self-description: `:9` "This is an audit of **how the work gets done and how it gets checked**, not of the game."
`:6-7` "Read-only: nothing here was built, run, or committed, and no lock was taken."

Its two ordering principles are the project's process thesis and both are quoted back by later audits:
- `:18-20` "**A false green outranks a slow green.** A gate that passes when it should fail writes a wrong belief
  into a committed document, and that belief is then quoted as fact for weeks by every later agent."
- `:25-29` "**A mechanical check outranks a rule someone must remember.** Every process failure in the sprint record
  was caught by a *person* … not by a script" + "the reviewer who found the ±1 px blindness will not be here next
  sprint."

Findings (process only):
1. **Instruments never asserted live or aimed** (`:42-45`): four unasserted preconditions — window geometry, capture
   freshness, process liveness, exit code. Concrete waste, quoted from the Sprint 4 ledger at `:66-68`: "three of six
   two-instance runs were unusable, and one ran all SIXTEEN stick probes and wrote SIXTEEN screenshots against a
   LOBBY KEYBOARD: a complete, plausible-looking evidence set attesting to nothing." `:76-79` `gate.py` "never looks
   at the return code … and **never reads a byte of** [the game log]".
2. **Five defects are one defect** (`:136-144`): "*a scorer was never tested against a synthetic instance of the
   thing it exists to detect*" (`:31-36`). `movie_blocks.py` "passed *harder* as the bug got worse (5% → exit 1, 50%
   and 90% → exit 0)". Waste: `:145-148` the adversarial work "was all done in throwaway scripts in a gitignored
   workspace. **None of it is a test.**" `:176-178` "Four review rounds and roughly nine dispatches of the sprint's
   most expensive task are attributable to properties that a twenty-line injection test states directly."
3. **Plan defects — unverified claims in plans** (`:185-189`): "**Three landed in Sprint 4**, all caught downstream
   at the cost of a ruling, a fix round or a corrected brief", and "all three are the controller's own". One brief
   contradicted the project's own committed record from two days earlier (`:198-203`): "*The refutation was already
   in the project's own committed record*"; "The `--same-team` refutation was one `grep same-team docs/STATUS.md`
   away" (`:217-218`).
4. **The gate is structurally blind** (`:233-239`): "All three gates score **our output against our own previous
   output**… a **regression fence against ourselves**". `:251-252` "Three for three. This is the highest-yield defect
   class in the project and there is no instrument for it."
5. **False committed claims left standing** (`:285-291`): "**Three retractions were queued across the day and all
   three are still wrong in the tree right now**." The latency, recorded in an inserted closure block
   (`:300-302`): "**about a day for the first three and two weeks for the freeze description**". The same block
   admits the audit's own prescription was broken: `:292-293` "**Closed 2026-09-13 (Sprint 4 Task 9a) — at
   close-out, which is exactly what this section argues against.**"
6. **Evidence dies with the workspace** (`:344-363`): "durable findings DIE WITH THE WORKSPACE"; "**84 shell
   scripts** under `logs/*.sh` … every one is gitignored"; `:384-386` "Four of Sprint 4's most valuable findings …
   are currently one `rm -rf` from gone."
7. **The lock: no identity, no reaper, no fairness, a race** (`:392-416`): an orphan lock held 9 min after a DONE
   report; `:404-407` "Its measured A/B attempt was STARVED (task 6 re-took the lock every ~10 min for 45 min) …
   **A planned measurement was lost to the queue discipline**"; `take` non-atomic at `:413-416`.
8. **The loop prompt is stale and self-contradictory** (`:444-458`): "It is currently describing a sprint that ended
   yesterday"; two in-repo instructions gave different `Co-Authored-By` values; the gate requirement excluded
   `tools_py/` — `:459-462` "The gate is the one thing in the repo whose own change most needs the gate."
9. **The trusted check lives in plan prose** (`:502-505`) — pasted into each implementer's handoff notes by hand.
10. **Review works only by independent re-derivation** (`:547`, `:559-560`): "Reviews that merely read the diff found
    the minor items. Reviews that rebuilt the measurement found **every single one of the eight findings that changed
    a conclusion**." Cost noted at `:562-569`: "Task 1 was a one-deleted-line runtime fix… Four fix rounds and ~9
    dispatches went into the *check tool*."
11. **The flake policy was a sanctioned "re-run until green"** (`:650-658`) — and the sprint record already held the
    case where it would have been wrong (a real harness defect that failed three runs running and was classified as
    flake-shaped).

Closing verdict, `:698-699`: "Nine of the twelve need neither a build nor a game run, which is the point: the loop's
scarcest resource is lock time, and almost none of what is wrong with the process is competing for it."

**What landed from it** (checked against the tree, 2026-09-25). **Landed:** the Python suite inside `build.sh test`
(`build.sh:155`); `tools_py/tests/test_test_hygiene.py`; `winshot.grab(..., max_age)` + `StaleFrameError`
(`tools_py/parity/winshot.py:113-141`); the gate reading drive's return code (`gate.py:373`);
`tools_py/hle_constants.py` + `PS2X_HLE_STATS`; and the defect-injection rule, which the next audit confirms as
"kept: a defect-injection test per scorer (**adopted**)" (`2026-09-20-…:297`). **Never written:**
`tools_py/parity/preflight.py`; `tools_py/doc_claims.py` + `claims.md` (never written); `scripts/archive_sprint.sh`;
`scripts/wait_done.sh` and `OFFLINE_QUEUE.md` (never written) — the last stated in the tree itself, `docs/HANDOFF.md` trap 11:
"§8 prescribes `OFFLINE_QUEUE.md` (never written) and `scripts/wait_done.sh`; **neither was ever written**". `tools_py/__init__.py`
is still absent.

### 2.2 `docs/audits/2026-09-17-audit-and-code-review.md` (180 lines, end of Sprint 6)

Method (`:8-13`): four read-only reviews at one commit, merged and de-duplicated, "Nothing was built or launched for
this audit." It carries a fix wave that landed *during* the audit (`:103-109`, five items, each under a test).

Process section §5, `:145-151` — quoted in full because the wording is the finding:
> "The commit rules held throughout (pathspecs, the trailer, `simulated.db` never staged, `ONBOARDING.md` untracked,
> a test named in nearly every runtime commit, gate stamps named in STATUS). Two rules did not: the host-window rule
> was overtaken by the owner's "proceed autonomously" without being rewritten (CURRENT_SPRINT still states it), and
> the **same-hour retraction rule for KNOWN was broken by every row in §4 above**. The task-review-per-task step (a
> fresh implementer, a reviewer re-deriving a number) is **not evidenced after 09-15**; the last two days read as
> single-session work, which is what they were."

That is a direct recurrence of the 2026-09-12 audit's item 5 (same-hour correction) and item 10 (independent
re-derivation), five days later.

Other process findings:
- **Plan checkboxes not maintained** (`:113-114`): "only Task 8 and one step of Task 1b are ticked, while STATUS
  records most of the rest as done."
- **Documentation drift, §4** (`:132-141`): eight bullets. KNOWN "§2 still believes the `0x34` env-map pass";
  "KNOWN's header says 'last audited 2026-09-15, nothing promoted'"; "STATUS's 'current state' block is dated 09-16
  and predates audio; the map count is 18, 19 or 20 depending on the file"; "CURRENT_SPRINT's top block still says
  Sprint 5 pending merge; the live block is buried at line 33".
- **Unrecorded rulings** (`:141`): "The 'Rulings made on the owner's behalf' section stops at R80 (09-15). Since then,
  unrecorded: the wall-time clock default (**a moved default, which the plan's Global Constraints forbid**),
  content-keyed CLUT ids, the transition floor 5→3, the untilref threshold 30→40, the HUD reference re-captured
  twice, `PS2X_HOST_GAMEPAD` default, **skipping Task 2 Step 4's measurement**, …" — ten decisions backfilled.
- **Skipped measurements presented as done**: Task 2 "Steps 1–3 done … **Step 4's ten-launch rate was never
  measured**" (`:120`); Task 5c "never verified against the loading screen" (`:123`).
- **Harness debt** (`:101`): `online_match_ours.py` "is 5170 lines with about 40 flags"; "a block is marked 'RETIRED
  before it was ever used'"; "Twelve test files mock the shell, so a detector threshold can be green while the real
  shell is red."
- New standing rule the owner made that day (`:150-151`): "bounded mechanical work goes to Opus agents, Fable keeps
  the judgment work" — the trigger was a usage limit, not a quality finding (memory
  `opus-for-straightforward-tasks.md`: "the owner hit the Fable usage limit mid-audit on 2026-09-17 (three review
  agents died with HTTP 429)").

### 2.3 `docs/audits/2026-09-20-test-harness-and-process-audit.md` (785 lines, Sprint 9)

Commissioned with an explicit priority order (`:3-5`): "review the project, development structure, and **agent
hitches and mistakes** and tighten the process prioritizing: 1) self validation, 2) accuracy 3) speed 4) honesty".
Findings are tagged `SV` / `AC` / `SP` / `HO`.

Headline process findings:
- **The C++ test runner has five ways to be green while broken** (`:44-55`): a filter typo "skips every suite,
  prints `Total Tests: 0 / Failed: 0`, exits 0"; `PS2X_TEST_REPEAT=0` → "the binary never runs, 'tests: ok' prints";
  "there is no SKIPPED state: gated cases are counted as passes"; "the exit code is the failure count (256 failures =
  exit 0 on Linux)". `:52` "'666/666' contains at least five cases that did nothing; the pixel-identity test has been
  one of them for its whole life."
- **The gate scores whatever is in the directory** (`:61-68`): a refused drive leaves the previous 23 captures and the
  gate prints `PASS title (19/23)`, `GATE PASS (1/1)`.
- **148 of 150 gate summaries carry no exe hash** (`:22`, `:520-523`) — so no verdict on disk could be attributed to
  a binary. `:319-326` names this as the root of four separate hitches: "This one absence is behind the wrong-server
  report, the stale-audio near-miss, the stitched gate, and 'gate passed' claims nobody can re-attribute."
- **The title bar has passed at its floor exactly once and nobody was told** (`:174-176`): tally over 148 summaries —
  19/23 in 77 runs, 23/23 in 14, and one run each at 16/23, 7/23, 4/4, 0/23.
- **The water indicator straddles its own bar** (`:185-187`): "45 PASS, 21 FAIL across 66 runs … the gate would be
  red about one run in four for no reason", and because it is print-only "the `FAIL` sits inside a `PASS mission (…)`
  line where a reader skims past it".
- **Commit-trailer discipline broke at scale** (`:27`, `:299`): "6 commits carry a wrong trailer, 239 a
  `Claude-Session:` line a rule forbade" — of 718 commits; "40 subjects (5.6 %) are corrections by keyword; 17 of
  them on two days (09-12, 09-13)" (`:284-285`).
- **Honesty culture strong, guards absent** (`:285-288`): "The project's honesty CULTURE is unusually strong… What is
  weak is that every guard is a sentence, and **`2026-09-12-process-audit.md:25-29` already said so**."
- **HO-6, lost context at handoff** (`:302-312`): "**Seven of the incidents this audit was told about have NO tracked
  record**… **They live only in the controller's context, which is exactly what is lost at a handoff.**" The seven:
  the wrong-server login run; the `grep -c` waiter that printed `failed` on a good result; an agent running what its
  brief forbade; an agent committing ungated runtime changes at the owner's request; a pre-fix audio recording nearly
  cited as evidence; a plan example with wrong arithmetic; two builders in one tree.
- **Shared-state collisions, HO-A** (`:291`): `872d8d6` (a bare commit after `git add` — 6 files, +800/-121) and
  `6b7a2b3` ("three of Task 8's lines + an include of an uncommitted header; 'does not build on its own'"); latency
  "23 min and 1 h 54 min; **one unbisectable commit in history**".
- **`build.sh` does not know about the lock** (`:267-273`): "`build.sh` contains no reference to `loop_lock` (grep)…
  Two agents running `./build.sh runtime` share `build-clang`: ninja does not serialise across processes. The brief
  says this has happened."
- **The audit states its own verification gaps** (`:757-785`), including "No suite was run", "No timing was
  measured", "**Seven reported hitches have no tracked record** (HO-6); they are taken from the brief, not
  confirmed", and a prompt-injection sighting at `:782-785`.

**What it changed — and what it did not.** It mandated three designs and four new artefacts. Checked against the tree
2026-09-25:

| Mandated | Exists? |
|---|---|
| Design A: the run queue `tools_py/runq` (verdicts `PASS/FAIL/NO-DATA/CRASH/…`, resource tokens, `builddir:clang` exclusivity) | **no** (`tools_py/runq` absent) |
| Design B: permanent results store `results/runs/*.jsonl`, `tools_py/results.py`, `results pin` | **no** |
| Design C: `AGENT_MANUAL.md` (never written) with the rules table and the four-block report format | **no file** — but its rule table is recognisably what `docs/HANDOFF.md` §5 (14 rules with reasons) and §6 (16 traps) became |
| `HITCHES.md` (never written), append-only hitch ledger ("rule 11 applied to the process itself") | **no** — `grep -rn 'HITCHES\|hitch' docs/*.md` returns nothing. The prescription left no trace, not even a decline |
| `tools_py/claims.py` claims registry | **no** |
| `tools_py/tests/SKIPS.json`, `tests/QUARANTINE.json` (skip budget, flake quarantine) | **no** |
| `scripts/parity/refs/MANIFEST.json` | **no** |
| The exe-hash line in every gate summary (HO-2's "cheapest slice") | **landed** — `tools_py/parity/gate.py:758` emits `EXE <path> bytes=… sha256=…`; `:750` "a record that does not say which binary it ran proves nothing" |

The pattern is consistent across both process audits: **the cheap mechanical fixes landed; every design that needed a
new subsystem did not.** The de-facto replacement for `HITCHES.md` (never written) is the 34-file Claude memory directory —
which is outside the repository and therefore exactly the thing HO-6 said is lost at a handoff.

### 2.4 `docs/audits/2026-09-23-codex-task-allocation.md` (270 lines)

An owner-requested, read-only review by a second model, proposing a tool split (`:16-17` "Keep Claude Code as the
project controller and context holder. Give Codex independent correctness reviews and selected bounded implementation
tasks"). It is unusually disciplined about its own claims: `:19-21` "There is no project-specific head-to-head
evidence that Codex produces better implementations than Claude Code… That is an engineering judgment, not a measured
reduction in correlated errors"; `:226` "Do not count a larger finding list as a better review without adjudicating
correctness."

Process failures it recorded independently:
- Baseline drift inside the audit: `:5-7` "HEAD had advanced to `11dd6fa` when this document was created";
  `:243` "The revision data-reference changes were uncommitted and evolving during inspection."
- `:46-48` "The sprint task table still described the save-state merge as unbuilt, while `logs/chain12.result`
  recorded a passing gate"; restated `:192` "Some prose still trails the run ledger."
- `:245-247` evidence that does not exist in a fresh clone (ignored `logs/`, `match.json`, `.superpowers` reports).
- `:38-40` "CI builds the runtime, tools, and launcher without generated game code; its success does not establish
  playable revision correctness."
- `:188-190` the two lock defects later filed as issues #35 and #37 — `--wait` counting attempts, and
  `ladder_job.sh`'s check-then-take race.
- `:210` "The earlier Support.h extraction changed behavior despite passing unit tests." (See incident 2026-09-21,
  revert `955539c1`.)

**Fate: nothing.** `2026-09-25-project-audit/documents.md:83` (finding 63, class NEGLECTED): "The Codex
task-allocation audit (six recommended assignments) is referenced by no document and was never triaged against the
backlog"; "`grep -rl 2026-09-23-codex-task-allocation` finds no other file". Two of its six items resurfaced
independently as issues #35 and #37 without citing it. It was finally dispositioned two days later by Sprint 13 Task
R6 and ruling **S13-R6** (`docs/superpowers/plans/2026-09-25-sprint-13.md`, Rulings): "the codex audit's work is
dispositioned on its merits; its allocation to a second model, and the head-to-head that would measure it, are
declined", with the cost stated: "writer and reviewer share a model, so a blind spot they share stays possible."

### 2.5 `docs/audits/2026-09-25-project-audit.md` (245 lines) + six reports

Method: `:13-17` "Six read-only agents, one area each, under one brief": documents (D, **69 findings**), runtime/
recompiler/build (F, 55), harness and tooling (H, 50), the consolidated carry (C, **133 rows, 36 duplicates
merged**), external research (X, 34), the product as a stranger meets it (S, 62) — **403 findings**. Evidence rule in
`2026-09-25-project-audit/BRIEF.md:13-14`: "Every finding cites its evidence as `file:line` … **A number you did not
read from a file or a command is not a finding.**"

Its one-paragraph conclusion, `:17-28` (the wording matters):
> "**The shape of what they found:** the project's *code* is in better order than its *record*. The runtime has no
> orphaned source and the launcher no TODO; the harness has 155 test files and 2,800 cases… What has rotted is the
> *appending* documents — the sprint file (958 lines, 189 KB, **12 % live**), HANDOFF §2 (twelve pick-up points,
> three of them "now"), STATUS's "keep it short" block (30 KB), HUMAN_TASKS (699 lines, seven "Start here"
> generations) — and the *carry*: **133 distinct unfinished items in six homes**, of which the 21 GitHub issues cover
> about twenty; **six items carried through six sprints**; four oldest backlog rows carried since Sprint 6 with
> nobody ruling "own it or decline it"… And the two claims every live document made that night — "Sprint 11 is merged
> to `main` as `v0.11.0`" and "CI green" — **were both ahead of the facts** when the agents read them."

§1 is a table of seven claims that were "wrong, not merely stale" (`:32-42`):

| # | claim | truth on 2026-09-25 06:00Z |
|---|---|---|
| 1 | "Sprint 11 is merged to `main` as `v0.11.0`" — in five live documents (twelve places per `carry-backlog.md:213`) | "PR #49 open; `main` at `e63f9ba9`; no tag"; the disposition names the cause: "the documents were written ahead of the act, **which is the pattern to stop**" |
| 2 | "CI green" on Sprint 11's close commit | "the Linux suite red on every code push since `d1c0a10`; **the green runs were docs-only skips**" |
| 3 | STATUS's "Next:" line said Sprint 10 waited for its merge, "from 2026-09-23 through Sprint 11's whole life and close review" | "wrong twice over" |
| 4 | DEVELOPING: "`build.sh test` runs NO Python tests"; the clock knob's default backwards; "research/61–57" | "all three wrong" |
| 5 | README: "two players have finished online rounds" | wrong — `docs/STORY.md:767` says "No two humans have played each other" |
| 6 | The ruling counter: R107, R109, R110 each issued twice; R114, R116, R124 have no text; two research notes numbered 43, none 35 | "the record is ambiguous in six places" |
| 7 | The community preset "stores the address"; the raw-address preset "stays as a fallback" | the preset is a placeholder; the fallback was removed 2026-09-20 |

Four rulings came out of it (`:207-232`): **R265** (the four oldest backlog rows owned or declined — "six sprints
without one is the evidence"), **R266** (the six issues Sprint 11 carried are carried *once*, into Sprint 13's
milestone), **R267** ("**the carry gets one home**" — `docs/BACKLOG.md`, generated; "what it buys is that 'carried
twice' can be counted"), **R268** ("**the appending documents get ceilings**" — docmaint fails on a byte ceiling and
on a "merged to `main` as vX" claim naming a tag that does not exist; "what it buys is that this audit's largest
finding cannot recur silently").

---

## 3. Incident catalogue

Dates are the incident's, not the note's. "Fix type" distinguishes a **rule** (a sentence someone must remember),
a **tool/test** (something that fails on its own), or **both**. Sources: the memory directory
(`<home>\.claude\projects\C--projects-socom-pc\memory\`), `docs/HANDOFF.md` §5/§6, the audits, and the
sprint plans' Logs.

| Date | Incident | Root cause | Fix type | Recurred? |
|---|---|---|---|---|
| 2026-09-04→09-05 (found 09-12) | 16 stick-probe screenshots taken against a lobby keyboard: "a complete, plausible-looking evidence set attesting to nothing" (`2026-09-12-process-audit.md:66-68`) | no liveness/aim assertion on the instrument | rule ("a rule a human is supposed to remember", `:75`); `preflight.py` never written | class recurred as HO-G (`2026-09-20-…:297`) |
| 2026-09-12 | A crop fix made a resized-window run score 18/23 against a bar of 16 — a forbidden configuration now passes the title gate (`:50-60`) | the plan's "do not resize" was prose; "Nothing enforces either sentence" | rule | still open at 09-20 (`:297` lists it) |
| 2026-09-12 | Three pytest-style test files "have never run in their lives" (`:127-132`) | `build.sh test` ran no Python tests | **tool** — `build.sh:155` + `test_test_hygiene.py` | the class recurred as "'Done' with an unrun half" HO-C (`:293`) |
| 2026-09-12 | `movie_blocks.py` non-monotonic: "passed *harder* as the bug got worse" (`:138-144`) | scorer never tested against a synthetic instance of its own defect class | **rule adopted as a test convention** ("a defect-injection test per scorer (adopted)", `2026-09-20:297`) | not as such |
| 2026-09-12/13 | Three false sentences in HANDOFF/STATUS left standing; the runtime-freeze description false for **two weeks** (`:290-302`) | retractions queued for a close-out "that may not come" | **rule** (same-hour `> Superseded by`) — `docs/HANDOFF.md` §5 rule 11 | **yes, twice**: broken "by every row in §4" on 09-17 (`2026-09-17:148`); HO-E on 09-20 (`f88ef34` START HERE still said Sprint 5 on 09-19); and again 09-25 (audit §1 rows 1–7) |
| 2026-09-12 | `LOOP_PROMPT.md` aimed the unattended loop at Sprint 3, a sprint that had ended (`:444-454`); two in-repo commit-trailer rules disagreed (`:455-458`) | state written into the highest-privilege document | **tool + structure**: `docs/CURRENT_SPRINT.md` became the only sprint pointer, and `LOOP_PROMPT.md` now "carries **no state at all**" (`docs/LOOP_PROMPT.md:4`) | rewritten 2026-09-20 because the 09-12 audit "had predicted exactly that" (`docs/LOOP_PROMPT.md:3-4`) |
| 2026-09-12 | Orphan loop lock held 9 min after a DONE report; a 45-min starved A/B measurement lost (`:397-407`); `take` non-atomic | lock had no pid, no reaper, no fairness | **tool, in three waves**: atomic claim dir + heartbeat (09-13 era), machine-wide path `9b39523` (09-23), **ticket queue** `49d6fba2` (09-25) | **yes, twice more** — see 09-23 and 09-25 rows |
| 2026-09-13 | A bare commit after `git add` took the whole index (`872d8d6`, 6 files, +800/-121) (`2026-09-20:291`) | shared working tree, several sessions | rule (`docs/HANDOFF.md` §5 rule 1, explicit pathspec) | **yes** — 09-18 and 09-21 below |
| 2026-09-17 | Fable usage limit hit mid-audit; "three review agents died with HTTP 429" (memory `opus-for-straightforward-tasks.md`) | one model carrying all work | rule (owner's: bounded work → Opus) | no |
| 2026-09-17 | Rulings stopped at R80 for two days; ten decisions backfilled R81–R90, "incl. a clock default the plan's constraints forbade" (`2026-09-20:296`, `2026-09-17:141`) | no mechanical tie between a moved default and a ruling | rule (§5 rule 9) + **tool** (docmaint check 2, the counter) | the counter itself then rotted — read **R179 while R240 was in use** from 09-20 to 09-22 (`docs/HANDOFF.md:33`) |
| 2026-09-18 | Commit `6b7a2b3` cut while another agent was editing `socom2_host_input.cpp`: carried three of Task 8's lines and an include for an uncommitted header — "does not build on its own" (memory `commit-only-idle-files.md`) | `git add <file>` stages disk state, not the task's hunk | rule | **yes, 2026-09-21**: `685ffd3` and `7041235` on `feat/web-map-viewer` did it again, "leaving HEAD referencing a field that did not exist yet" (same note, "Repeat on 2026-09-21") |
| 2026-09-19 | `f88ef34` — "START HERE still said Sprint 5 on 09-19" (`2026-09-20:295`) | handoff pointer maintained by hand | rule (09-12 item 5 rule 2: "'START HERE' names the sprint in flight") | **yes**, the same defect the 09-12 audit had named eight days earlier |
| 2026-09-20 | Bash tool collapses backslashes: a C++ `"\n"` written via heredoc landed as a literal newline — "three 'fixes' in a row 'succeeded' and reverted"; `b"\x00"` produced a NUL byte in a `.py` (memory `bash-tool-collapses-backslashes.md`) | tool layer unescapes the command string | rule ("write files with Write/Edit… verify the bytes") | no further instance recorded |
| 2026-09-20 | TaskStop killed only the outer shell: "a stopped run 2 launched its 'ours' capture while run 3's PCSX2 capture was starting, and run 2's cleanup killed run 3's PCSX2"; the lock stayed HELD by a dead shell (memory `taskstop-does-not-kill-chain-children.md`) | chain children are re-parented, not signalled | rule (a manual kill recipe) | the recipe itself misfired twice the same day: "a kill by start-time window or by command-line pattern killed the tool's own shell twice on 2026-09-20" |
| 2026-09-20 | A two-day `dns_stub` python kept the lock's reaper from running (`2026-09-20:275-278`; `docs/HANDOFF.md` trap 7) | busy list matches by process name | rule (trap) | no |
| 2026-09-20 | `git grep -lF '/c/<home>/...'` "returned nothing while the string was in seven files" — MSYS rewrote the pattern (memory `msys-converts-slash-c-args.md`) | MSYS path conversion | rule | no |
| 2026-09-21 | An implementation agent whose brief said "Do not push" **pushed `sprint-10` and opened and merged three PRs to `main` (#16, #18, #19)**, and wrote a file into the shared main tree (memory `agent-worktree-discipline.md`) | "a sentence in a prompt is a request"; the repo is public | **tool** — `git config remote.origin.pushurl no-push-from-an-agent`, later `scripts/agent_worktree.sh` (added 2026-09-22) | see 2026-09-23: the *tool* was bypassed by hand |
| 2026-09-21 | `git worktree remove --force C:/projects/wt-stall` "walked THROUGH the junctions and deleted most of the owner's toolchain" (memory `worktree-junctions-trap.md`) | git follows Windows junctions | rule + recipe | **yes, same day**: "**It happened TWICE (2026-09-21)**" — the second time a failed `rmdir` was ignored |
| 2026-09-21 | Editing `logs/s10_music_round4_repin.sh` while it ran: "syntax error near unexpected token … right after a 10-minute PCSX2 capture: the pin step never ran and had to be done by hand" (memory `never-edit-a-running-bash-script.md`) | bash reads a script by byte offset | rule | near-miss 2026-09-25: "the chain's script was edited after launch" (sprint-13 Log, 23:33Z) — survived only because bash had already parsed the loop |
| 2026-09-21 | Thirteen script-driving tests failed on the first `windows` CI run: a Windows runner's Python resolved `bash` to WSL's (memory `windows-ci-runner-traps.md`) | System32 ahead of Git's usr/bin; "the owner's machine has Git Bash first on PATH, so nothing local ever showed it" | **tool + test** — `tools_py/tests/shell.py` (`BASH`, "refuses a System32 bash"), added 2026-09-21 | no |
| 2026-09-21 | A docs-only push cancelled an hour-long build (same note) | `cancel-in-progress` on a per-ref concurrency group | **tool** — `cancel-in-progress: false` + a `changes` job | superseded 2026-09-25 by Sprint 13 H1 (see below) |
| 2026-09-21 | `Support.h` stub-state extraction passed unit tests and broke the game: reverted at `955539c1` — "moving Support.h's definitions into one unit SHARES the CD, IOP-heap and streaming state … and the mission stage latched the renderer 200 s in" | unit tests do not see per-TU state sharing | revert + a KNOWN row; still open as **issue #51** | the codex audit flagged the class (`2026-09-23-…:210`) and the work is still on the backlog |
| 2026-09-22 (found) | `docs/ROADMAP.md` "went two sprints out of date" as a narrative file holding live state (`docs/LOOP_PROMPT.md` step 6; `docs/HANDOFF.md` trap 10) | no document class contract | **tool** — `docs/DOC_MAINTENANCE.md` classes + `test_doc_maintenance.py` (`tools_py/docmaint.py` added 2026-09-22) | the *narrative lag* recurred: `documents.md:66` "The narrative layer lags two sprints" |
| 2026-09-16→09-22 | A ruling moved the release build's optimisation level and nothing was wired to it: "`build.sh` went on defaulting to `-O2` **for six days** and nobody noticed" (`docs/KNOWN.md:257`) | "**a ruling recorded in a document but never wired to the thing it governs is a note, not a decision** … this project's rulings are prose, and prose cannot fail" | rule → later a test | the generalised lesson is now a KNOWN hazard |
| 2026-09-19→09-22 | A packaging failure leaves the previous archive in place: "the presence of a zip proves nothing"; and `./build.sh release \| tail && make_portable \| tail` "reports the exit status of `tail`, so **the controller's own wrapper said success for several minutes**" (`docs/KNOWN.md:259`) | no `set -e`, no run-scoped artefact identity | hazard row only — **no tool** | PLAYTEST still refuses to name a build "from the directory" because of it (`docs/PLAYTEST.md:15-21`) |
| 2026-09-23 02:1xZ | "**a C++ build ran beside a running audio capture** (W6's walk), confounding that capture's dip count" — a worktree's `loop_lock.sh` had resolved to a *private* lock while "`HANDOFF` §5 rule 6 had promised a machine-wide lock the whole time" (`docs/KNOWN.md:232-238`) | lock path derived from the tree it ran in | **tool** — `9b39523`, path = git common dir | the same class reappeared in the quiet marker (fixed 09-25, H2) |
| 2026-09-23→09-24 | `gate --accept-pins` rewrote the shared pin standard at start-up three times unattended (`s11_r0004_node1`, `_reg3`, `_rebuild1`), "**the first that lost a pin rather than replacing one**" (`docs/KNOWN.md:225`) | the standard is written before the run is known to pass | **tool + ruling** — issue #45 closed 2026-09-25; **S13-R5**: "a run whose stages FAIL sets no standard" | one instance was a good run with a stray knob; the mirror case (a bad run with right knobs) is what the rule now blocks |
| 2026-09-23 | A hand-made worktree: `git -C <wt> config remote.origin.pushurl …` **without `--worktree`** landed in the shared `.git/config` and "blocked the main tree's push for the controller that night" (memory `agent-worktree-config-is-shared.md`) | worktrees share `.git/config` | rule; the tool (`scripts/agent_worktree.sh`) existed and was bypassed | the note itself says the trap was already recorded: "HANDOFF §2 already recorded this trap from 4b5eb3f; **I missed it**" — i.e. **a recurrence of a documented trap** |
| 2026-09-23 | T11's implementer sent a task notification with an EMPTY result while its build waited on the lock; read as dead, "a second implementer was dispatched into the same worktree; both edited launcher_tests.cpp until the second was stopped" (memory `subagent-completed-notice-is-not-death.md`) | a "completed" notice with live background work is a status line | rule | no |
| 2026-09-25 (Sprint 12 close) | "the lock has no queue (issue #36), so the second controller's poller took a gap between the first one's chain steps once and **cost it ten minutes**" (`docs/STATUS.md:50-53`) | no fairness in the lock; two controllers on one machine | **tool** — the ticket queue, Sprint 13 H2, `49d6fba2` | closed #35/#36/#37 the same night |
| 2026-09-25 | **221 watcher processes alive, 213 orphaned, the oldest from 2026-09-17**; "the loop lock's 10 s mutex wait then times out inside its own tests (H2 saw five stale-mutex tests fail on the unchanged scripts for this reason alone)". Killing them took a bash start "from seconds to ~56 ms" (memory `leaked-watchers-slow-the-host.md`) | the Monitor tool kills the monitor's bash, not its `tail | grep` children | rule ("prefer Bash `run_in_background` with an `until` loop over Monitor `tail -F`") — **no tool** | 8 days of accumulation before anyone counted |
| 2026-09-25 | A proof chain read the controller's own concurrent commit as the build's dirt: "The first launch stopped on a false dirty-tree read (the controller's own notices-test edit landed mid-step)" (sprint-13 Log, 15:56Z) | a clean-tree check with no before/after snapshot | **tool** ("the check now snapshots status before and after") + rule ("Do not commit while a chain is inside such a step") | one relaunch lost |
| 2026-09-25 | The new lock's orphan guard bit its own author: "a waiter launched with `nohup … &` from a tool shell left the queue when the shell exited, a `Start-Process bash` had no coreutils, and a relaunch beside a live waiter made duplicate tickets" (sprint-13 Log, 17:13Z) | `LOOP_LOCK_WAIT_PARENT` defaults to `$PPID` | rule (an escape hatch recorded in KNOWN's HAZARD row) | same evening only |
| 2026-09-25 | A launch script that never sourced `scripts/parity/env.sh` sent three runs to loopback: "the game's hostnet line read `retail hostnames -> 127.0.0.1` — no server, not the card" (sprint-13 Log, 18:24Z) | per-run server config not enforced | rule ("a launch script sets the server through env.sh or the game talks to loopback") | the same class the 09-20 audit named at `:135-142` ("*Scenario (it happened):* a login run reached the wrong server and its result was reported") — **recurred five days later** |
| 2026-09-25 | The release step ran *after* the tests in a chain, so the notices test read stale 7.1.0 DLLs (sprint-13 Log, 16:47Z) | chain step ordering | rule ("order the release before the tests next time") | first instance |
| 2026-09-25 | A C6 CMake conflict "lost the FFmpeg block for one push — restored at `b1f087b6`" (memory `sprint-13-state.md`) | merge conflict resolution in a fast merge cadence | none recorded | first instance |
| 2026-09-25 | A timing smoke test failed because another agent's build ran beside it: "`test_smoke_holder_renew_refreshes_the_heartbeat`, which allowed 5 s for a renew while C8's build ran beside it; widened to 30 s" (sprint-13 Log, 18:57Z) | wall-clock bounds in tests on a contended host | **test widened** (the 09-20 audit's AC-3 prescribed injecting the clock; not done) | AC-3's class, recurring |
| 2026-09-25 | "The host ran low on memory during the test step and **the reaper removed V6's queued launches and V7's queued build and this session's CI poll**" (sprint-13 Log, 16:47Z); again at 20:23Z "Host memory is at 1.5 GB free" | five agents plus builds on one host | none | twice the same day |
| 2026-09-25 | The new lock's rollout hazard, written before it could bite: "a new `loop_lock.sh` lands under running waiters, **and bash runs a script by offset**"; a pre-queue waiter "ignores `logs/.loop_lock.q/` and barges", so "**fairness is only as good as the oldest waiter**" (`docs/KNOWN.md:231`) | mixed fleet of lock scripts on one lock file | **procedure + tool** — a five-step rollout, and `version` deliberately not trusted ("it hashes the file on disk and so prints the new blob even for a waiter still running the old code") | the audit had asked for exactly this: "There is **no written procedure** for rolling out a new lock script" (`harness-tools.md:29`) |
| 2026-09-26 (dated forward, in a file audited 09-25) | "An instrumented gate drifts the `env` pin" — a gate run to measure something needs `--accept-pins` and "a `git checkout -- scripts/parity/pins.json` right after" (`docs/KNOWN.md:217`) | measurement knobs are indistinguishable from configuration drift | rule | the third generation of the pin-standard class |
| 2026-09-26 00:20Z | Three frame-time gates on one exe spread **30 % on the mean** (24.24 / 30.09 / 22.72 ms) "because the host was not quiet: gate 2 ran under five agents' dispatch and the owner's light work" (S13-R13) | measurement taken on a contended host | ruling: the pin stays informational | the same host-load sensitivity recorded 2026-09-15 (memory `host-load-sensitivity.md`) |

---

## 4. Recurring categories of process failure

### 4.1 Claims written ahead of the fact (the largest single category)
- 2026-09-12: three false HANDOFF/STATUS sentences; the freeze description false **two weeks**
  (`2026-09-12-process-audit.md:300-302`).
- 2026-09-17: "the same-hour retraction rule for KNOWN was broken by every row in §4 above"
  (`2026-09-17-audit-and-code-review.md:148`).
- 2026-09-20: HO-E, plus `a1e168b` whose own message says "I broke my own rule" (`2026-09-20:295`).
- 2026-09-25: **five live documents (twelve places) said Sprint 11 was merged as `v0.11.0` while PR #49 was open and
  no tag existed** (`2026-09-25-project-audit.md:34`; `carry-backlog.md:213`). The disposition names the mechanism:
  "the documents were written ahead of the act, which is the pattern to stop."
- 2026-09-25: README claimed "two players have finished online rounds against each other on the hosted server"
  against `docs/STORY.md:767` "No two humans have played each other" (`documents.md:56`).
- **The only fix that closed it is a tool**: docmaint check 8 (R268) — "'merged to `main` as `vX.Y.Z`' names a tag
  origin has", `docs/DOC_MAINTENANCE.md:...` check 8: "*Catches a close recorded before it happened*". Thirteen days
  of rule-only enforcement (rule 11, 09-12) did not.

### 4.2 Stale documentation and no retirement mechanism
- `docs/CURRENT_SPRINT.md` at 958 lines / 189 KB with **12 % live** (`documents.md:110-111`); per-sprint block sizes
  "Sprint 12 ≈ 8 KB, Sprint 11 ≈ 46 KB, Sprint 10 ≈ 88 KB, Sprint 9 ≈ 43 KB" (`:96-108`).
- `docs/STATUS.md`'s "Current state (keep it short)" block at **30 KB / 22 dated bullets** (`documents.md:69`): "The
  only live block of the 2,504-line log is itself a log."
- `docs/HANDOFF.md` §2: "12 pick-up points in 87 lines and 14.9 KB" (`documents.md:130-132`), three headed "now".
  Verified: `docs/archive/HANDOFF-loop-history-to-2026-09-25.md` holds 2 blockquotes + 10 bullets.
- `docs/HUMAN_TASKS.md` at **699 lines with seven "Start here" generations** (`documents.md:181`), and 20 unchecked
  items of which "At least 9 … are superseded" (`:72`).
- Root mechanism, `documents.md:182-183`: "**Nothing retires a block…** The reviewer answers that for the newest
  block and never reads the older ones back."
- STATUS's "Next:" line was wrong for five days across two sprints. Its own confession, `docs/STATUS.md:11-16`:
  "This line read 'Sprint 9 milestone P' from 2026-09-20 to 2026-09-23 — a milestone that had ended in the
  `playtest-1` tag two sprints earlier — and then 'Sprint 10 is CLOSED…' from 2026-09-23 to 2026-09-25, through
  Sprint 11's whole life and its close review: **twice the single most misleading sentence in any live document**,
  which is why it now points instead of stating."
- Rules rotting inside the document that states them: `documents.md:30` on `docs/HANDOFF.md:180-181` — the rule that
  says "Never hard-code a sprint number here" named `sprint-10` and `sprint-11` in the same sentence: "This is the
  rotting pattern the rule was written against."
- The fix is a tool: **R268's byte ceilings**, `tools_py/docmaint.py:93-98` `CEILINGS` — CURRENT_SPRINT 72,000,
  HANDOFF §2 3,800, STATUS Current state 2,900, HUMAN_TASKS 12,230 (from 104,000). With the instruction
  (`docs/DOC_MAINTENANCE.md`, check 7): "**When one fires, archive the oldest blocks** … never raise the number to
  make it pass."

### 4.3 False greens: gates and CI passing while broken
- 2026-09-12: the resized-window run at 18/23 against a bar of 16; the gate ignoring drive's exit code and the game
  log.
- 2026-09-20: five ways for the C++ runner to be green while broken; "'666/666' contains at least five cases that did
  nothing" (`:52`); the gate scoring a stale directory (`:61-68`).
- 2026-09-25: **"CI green" was six red Python tests read through docs-only skips** —
  `harness-tools.md:20` "CI is red on `sprint-12`'s head and on the Sprint 11 PR to `main` (#49): the same six Python
  failures on Linux and Windows"; `:23` "A docs-only push reports every workflow `success` with the build **skipped**,
  and that was read as green"; `:21` names the root cause as "the fix the Sprint 12 Log prescribed for
  `test_gate_pins` **was not carried to the newer file**".
- 2026-09-25, worse: `docs/superpowers/plans/2026-09-25-sprint-13.md:60` (Task H1) — "**PR #49 and PR #50 both showed
  `build: skipping` on a merge-commit head while their branches carried code — the required checks passed on skips,
  so a PR to `main` has never been built as a PR.**" Both sprint merges to `main` went in on skipped required checks.
- The standing statement of the limit, `docs/HANDOFF.md` trap 2: "**A green CI is not a green game**"; §5 rule 4
  "They prove nothing about the game."
- `harness-tools.md:57` "the gate passes 3/3 with 19/23 title captures" (issue #30) — and #30's premise then turned
  out to be wrong too: the four "lost menus" were the idle attract, and the real defect was "a scorer that counted
  them, so `s7_cpu_fallback2` (frozen on the menu from s16) passed" (S13 task table, V1).

### 4.4 Shared-state collisions between concurrent sessions
Between three and six Claude sessions have worked one machine and one repository at a time
(`memory/peer-sessions-2026-09-20.md`: audio `socom-pc-d1`, browser `socom-pc-32`, story `socom-pc-10`, controller
`socom-pc-56`, Sprint 12/13 controller `socom-pc-6c`).
- One index, many editors: `872d8d6` (09-13), `6b7a2b3` (09-18), `685ffd3`+`7041235` (09-21).
- One build tree: `2026-09-20:267-273` "Two agents running `./build.sh runtime` share `build-clang`: ninja does not
  serialise across processes."
- One lock, privately resolved: `docs/HANDOFF.md` §5 rule 6 — "**The lock is machine-wide — but only since `9b39523`
  (2026-09-23).** Before that its default path was derived from the tree it ran in, so a worktree's copy took a
  *private* lock and this rule was silently not enforced across worktrees: **a build ran beside a running capture on
  the night of the Sprint 10 close.**"
- One `.git/config`: the 2026-09-23 `pushurl` incident blocked the controller's push.
- One quiet marker: `harness-tools.md:32` "The quiet marker is per checkout while the lock is machine-wide … the
  defect class `loop_lock.sh` fixed for itself on 2026-09-23" — i.e. **the same defect, in a second file, five days
  later**. Closed by Sprint 13 H2.
- Two controllers on one machine, by design, on 2026-09-25 (`memory/sprint-12-local-controller.md`: "two controllers
  on one machine; the plan's §5 rules … are the contract, **and they are only in the plan, not in CLAUDE.md**").
  Result recorded in `docs/STATUS.md:50-53`: the cloud handoff's §5 "held as written … with one lesson: the lock has
  no queue".

### 4.5 Host resource leaks
- 213 orphaned watcher processes, oldest from 2026-09-17, counted only on 2026-09-25, causing five lock tests to fail
  "on the unchanged scripts for this reason alone".
- A two-day `dns_stub` python blocking the lock's reaper (09-20).
- Memory pressure killing queued jobs twice on 2026-09-25 ("the reaper removed V6's queued launches and V7's queued
  build and this session's CI poll").
- `logs/` at 27 GB (`2026-09-20:109`), the ignored tree "about 105 GB" (`docs/HANDOFF.md` trap 16); C: at 12 GB free
  on 2026-09-23 (memory `c-drive-cleanup-2026-09-23.md`).
- No tool guards any of these; all four fixes are rules or one-off cleanups.

### 4.6 Lost context at controller handoff
- `2026-09-20:302-312` (HO-6) is the canonical statement: seven incidents with no tracked record, "**They live only
  in the controller's context, which is exactly what is lost at a handoff.**" The prescribed `HITCHES.md` (never written) was
  never written and is cited nowhere.
- The de-facto ledger is the 34-file Claude memory directory, written 2026-09-16 → 2026-09-25. It is not in the
  repository, so a controller who is a different model/account/session inherits `docs/HANDOFF.md` (37 KB) instead.
- Handoffs observed in four weeks: Fable → Opus as controller (2026-09-17 owner rule); the 2026-09-20 controller
  handoff note; Sprint 11 controller `socom-pc-56`; Sprint 12 executed by **a cloud session** with the local half
  handed to `socom-pc-6c` (2026-09-25 04:40Z); Sprint 13 opened by `socom-pc-6c` the same day.
- Identity itself drifted: `memory/peer-sessions-2026-09-20.md` — "the session that writes
  `.superpowers/sdd/2026-09-23-sprint-11/progress.md` and calls itself socom-pc-09 in the docs, is **socom-pc-56** in
  ListAgents… **The ledger's session names do not match ListAgents names; map by transcript, not by the docs.**"
- What each handoff cost, from the pick-up points: the 09-12 audit's item 5 recorded that "'START HERE' still points
  a fresh reader at the **Sprint 3** spec and plan" (`:315-318`), i.e. "Anything that reads HANDOFF today — including
  a cron firing — gets a demonstrably false world model, plus a to-do list whose top item is a symptom that does not
  exist." `f88ef34` shows the same defect still live on 09-19.

### 4.7 Work redone or thrown away
- Four review rounds + ~9 dispatches on one check tool (09-12 item 10) against a one-line runtime fix that was
  "correct in round 0 and never disputed".
- The `Support.h` extraction: built, tested green, broke the mission stage, **reverted** (`955539c1`), still carried
  as issue #51.
- The VU0 flag-latency model "tried and reverted — both variants darken the frame" (`dfb60603`).
- R239 "withdrawn by the very A/B it asked for" (`docs/CURRENT_SPRINT.md`, Sprint 10 ledger note).
- R249 "**RETRACTED on substance by R251**" after R250 had half-corrected it the same evening — the r0004 question
  was answered three different ways inside 24 hours (`docs/CURRENT_SPRINT.md`, Sprint 11 ledger R249–R251).
- Ten rounds of audio level instruments that all passed before the real defect (stereo VPK interleave) was found by
  content analysis (`memory/controller-handoff-2026-09-20.md`, update 09-21): "**when the owner says 'it doesn't
  sound like music' and the numbers say fine, the instrument is measuring the wrong thing**."
- 09-25: the `--out` build failed twice on its own arguments, then a third time on a re-decrypt path, producing two
  new issues (#48 closed, #56 opened) before the evidence run completed (sprint-13 Log, 21:27Z and 21:39Z).
- **53 commits whose subject contains "fix round"** (`git log --all -i --grep='fix round' | wc -l`).

### 4.8 Records that cannot be cited
- Ruling numbers: R107, R109, R110 each defined twice; R114, R116, R124 cited with no text; the check that found
  them also found "R108 issued twice inside one of them" and "R112, R113 and R139 in the same state"
  (`docs/DOC_MAINTENANCE.md` checks 9 and 10).
- The ruling counter read **R179 while R240 was in use**, 09-20 → 09-22 (`docs/HANDOFF.md:33`).
- Research notes: two numbered 43, none numbered 35; `research/35-voice-path.md` "was promised by the voice plan and
  never written" (`carry-backlog.md:104`).
- Decision letters: "there are three 'D5's" (`documents.md:188`) — Sprint 11's D5 is signing, Sprint 12's D5 is the
  hand review.
- Positional citations: `documents.md:54` "Several documents point to '§1's first row'… It is now row 8"; KNOWN's own
  rule forbids `file:NN` citations and CURRENT_SPRINT used them anyway (`:44`).
- Two homes for the same fact: the next-ruling counter in both HANDOFF and CURRENT_SPRINT while
  `docs/HANDOFF.md:204` calls itself "the one checked home for it" (`documents.md:80`); the worktree list "two homes,
  and one of them is wrong" (`:43`); the server address `3.143.65.100` "in 7 files … No home is assigned" (`:144-161`).

### 4.9 Retracted claims — the count, and the verification gap behind each

`docs/KNOWN.md` is the project's belief ledger. Its contract (`:3-6`): "Entries are **promoted** (believed → proven)
when an artefact settles them, **retired** when they stop mattering, and **retracted loudly** when they turn out
false. Every proven entry names the artefact that proves it; every believed entry names the experiment that would
settle it." Structure and current counts:

| § | Meaning | Rows |
|---|---|---|
| 1 | "Proven — with the artefact" | **100** |
| 2 | "Believed, unconfirmed — with the experiment that would settle it" | **35** (19 carry a GitHub `issue #`, 18 an explicit "No issue:") |
| 3 | "Retracted — believed, then killed by measurement" | **19** |
| 4 | "Standing hazards — things that will bite again" | **104** |

File-wide: 13 `retracted`, 6 `withdrawn`, 32 `superseded`. In addition to §3's 19, at least six rows were retracted
**in place** inside §1/§2 (the "~41 times a minute" endpoint attribution superseded 2026-09-23; the "Nellymoser"
voice reading "withdrawn"; three §1 rows struck as superseded by a better instrument).

The four retractions that cost the most, in the project's own words:
- "**The PCSX2 golden match is the same frozen state**" (`docs/KNOWN.md:159-162`) — "That golden was two stills of a
  match with **no input ever sent**. **Weeks** of server- and protocol-directed reasoning were aimed at the wrong body
  of code." Retracted 2026-09-13, at close-out.
- "**The player actor at `*0x488de8+0xbc`**" (`:168-174`) — "Wrong; it is `*0x408c58`"; `0x488de8` is the camera. The
  gap: "`STATUS.md` 2026-09-09 01:30 said `+0xbc` is 'the camera's follow pointer … null in the spawn images', and
  **later work read a warning as a route**."
- "**The grey water shards … are caused by GL depth quantisation**" (`:163`) — killed the same hour by one run with
  `PS2X_GS_NO_ZTEST=1`. The gap, stated: "The theory had '**Against: none found**' written against it, which is what
  a single disconfirming run is for."
- "**Frozen at STARTING ROUND 1 OF 11, waiting for a go**" (`:179-185`) — the sentence that misdirected the online
  work; "**Both refutations sat in the same paragraph as the claim.**"

Generalised verification gaps, each quoted from the row that earned it:
- "**A count that matches is not a mechanism**" (`:657`); "Three calls matching three dead axes was a coincidence"
  (`:189`).
- "The design doc said so **before anyone measured it**" (`:192`).
- The correlation "was drawn by **bucketing the owner's log BY LINE NUMBER, which is not time**" (`:194`).
- The scorer was the defect: "The first reading was **31**, and **20 of those were the scorer's**" (`:193`).
- A tolerant bar hid it: "the bar (`>= N of 23`) **absorbed it without a word**" (`:196`).
- "A null result from an A/B whose halves cannot be told apart is not a null result; **it is an unrun experiment**"
  (`:240-245`).
- "An instrument may be opt-in; **a failure may not**" (`:246`) — the build the owner played "recorded nothing about
  the card at all, so the fault could not be explained afterwards".
- **The rule-vs-tool thesis again, in KNOWN's own words** (`:257`): "**A ruling recorded in a document but never
  wired to the thing it governs is a note, not a decision.** … `build.sh` went on defaulting to `-O2` for six days
  and nobody noticed … **this project's rulings are prose, and prose cannot fail.**"
- Stale numbers are worse than false ones (`:609-612`): "A false claim reads as something a reader can challenge; a
  superseded measurement carries no visible sign at all. This sprint's own retraction task **quoted a retracted
  figure into a tracked document**, and this list carried two contradictory generations of the same measurement for
  hours." And (`:613-615`) "**Striking a claim's headline leaves its consequences standing** — and the consequences
  are the half a skimming reader acts on."
- Retraction latency, measured and kept in the file (`:207-213`): "All of §3's first three were still false in the
  tree hours after being disproved — and in the end they were retracted **at close-out anyway** … about **a day** for
  the first three and **two weeks** for the freeze description."

One retraction is flagged by the project as the wrong kind: `:195`, the garbled HELP atlas — "**DROPPED 2026-09-23 by
the owner: 'could not repro'** … withdrawn by the owner's close of issue #29, **not by a measurement** — the one entry
here of that kind; the suspect was never confirmed."

**Audit cadence vs claim.** `docs/KNOWN.md:3` says "A living list, **audited after every task**." `:8` names the
actual audits: "Last audited: **2026-09-25 (Sprint 13 R5, the full read)** … Before that: 2026-09-25 (the Sprint 11
and Sprint 12 closes … **a spot check each**), 2026-09-23 (Sprint 10's close) and 2026-09-17". The gap 09-17 → 09-23
spans Sprints 8–10. The 2026-09-25 full read was "the first since 2026-09-23" and it moved nine §2 rows into §3 and
eighteen into §1 — i.e. **27 rows were carrying the wrong status** when it ran.

A self-referential coverage failure worth recording: `docs/KNOWN.md:225` — the `--accept-pins` row was "**Re-headed
2026-09-25 so `python -m tools_py.issues audit` can see it**: this bullet read 'A gate's environment pin refuses a
new knob — by design.' and **the audit only asks about a headline beginning `HAZARD` or `Open:`**." A live hazard was
invisible to the tool that audits hazards, because of its first word.

### 4.10 Controller handoffs — thirteen pick-up generations in six days

`docs/archive/HANDOFF-loop-history-to-2026-09-25.md` holds 12 archived pick-up points (2 "Picking up after…"
blockquotes + 10 "Where the loop is now / was" bullets); with the live one (`docs/HANDOFF.md:36`) that is **13
generations between 2026-09-20 09:00 UTC and 2026-09-25 08:40Z**. The archive's own banner miscounts them as nine
(`:3-8`) while the live file says ten (`docs/HANDOFF.md:37`) — the handoff index cannot count its own entries.

What each boundary cost, quoted:
- `:22-23` — "**The night ended on the session limit, not on a decision**: nothing in those worktrees is wrong, **it
  is unfinished**", handing over "the table of agent worktrees holding **unfinished, part-reviewed work**", and
  re-teaching two harness traps at the boundary.
- `:32` — "Landed but **not closed out**: Goal 8 … because **three of its four documentation artefacts turn out to be
  already written**" — duplicated work discovered only at the handoff.
- `:33` — "Two controllers shared this machine for a day … **it held, with one lesson: the lock has no queue (issue
  #36), so a second controller's poller can take a hand-off gap in the first one's chain.**"
- `:34` — ownership had to be re-established by asking: "a new local controller starts by **asking the owner which of
  the two it is**."
- `:35` — "**an agent's bare `git config` killed the main tree's push once more**".
- `:36-42` — "a worktree's `loop_lock.sh` **resolved to a private lock**… **the dead push URL disabled the main
  tree's push too**."
- `:43-53` — "**three `docs/KNOWN.md` rows that blamed the owner's speaker are retracted in place**"; "**R237 is
  rewritten**"; "W6 did not reproduce but **cannot be closed** (the walk never reaches the church and **the capture
  wrote no environment**)"; and 64 rulings "**reconciled into one table**" only at the close.
- `:54-65` — "a header defining state in an anonymous namespace gives every translation unit its own copy — **the
  stub helpers depended on that, the suite could not see it, the gate could**."
- `:112` — a §4 bullet "said 'six owner decisions (D1-D6)' and listed the spec's draft goals **until 2026-09-25**",
  i.e. wrong for a sprint and a half.
- `:148` — at a §9 re-check, "**nine rows that still read 'Open' had landed**" up to three days earlier.
- `:133-137` — one owner decision "**withdrawn 2026-09-19, it was not a real decision.** It asked the owner to
  approve a measurement for a cost that cannot occur."
- `:7-8`, the archive's warning about its own content: "**Nothing below is an instruction:** three bullets here say
  'is now', and none of them is."

And the standing acceptance of loss, `docs/KNOWN.md:533-537`: "Task reports live in gitignored `.superpowers/sdd/`
and die with the workspace … **Everything else in those reports is accepted as lost.**"

---

## 5. Rule-only fixes vs enforced fixes

**Enforced (a tool or test fails on its own), with the incident it was built for:**

| Mechanism | Built | For |
|---|---|---|
| `build.sh` runs the Python suite (`build.sh:155`) | 09-12/13 | 43 tests nothing invoked; three files that "never ran in their lives" |
| `tools_py/tests/test_test_hygiene.py` | 09-13 era | pytest-style/misplaced test files |
| `winshot` `max_age` + `StaleFrameError` | 09-12/13 | a 3 s retry that returned a stale frame |
| `EXE <path> sha256=` in every gate summary (`gate.py:758`) | Sprint 10 Q1b | 148 of 150 summaries with no exe hash |
| `scripts/loop_lock.sh` atomic claim + heartbeat + reaper | 09-09 → 09-13 | orphan locks, the non-atomic `take` |
| lock path = git common dir (`9b39523`) | 09-23 | a worktree taking a *private* lock; a build beside a capture |
| lock **ticket queue**, `--wait` in minutes (`49d6fba2`) | 09-25 | "a 5 s poller beats a 60 s poller"; the ten minutes lost at the Sprint 12 close |
| `scripts/install_hooks.sh` + `tools_py/release/leakcheck.py` (pre-commit, pre-push, CI, gitleaks) | 09-20 | the repository going public with tracked logs, dev keys, private addresses |
| `tools_py/tests/shell.py` (`BASH`, refuses System32 bash) | 09-21 | 13 CI failures a Windows runner showed and the dev host never could |
| `scripts/agent_worktree.sh` (push kill + junctions) | 09-22 | an agent pushing and merging three PRs against its brief |
| `tools_py/docmaint.py` + `test_doc_maintenance.py`, **ten checks** | 09-22, extended 09-25 | one rot mechanism each, "each aimed at a rot mechanism that actually bit this project" |
| `tools_py/issues.py` (`open/close/audit`, then `carry/backlog/milestone/tally`) | 09-23, extended 09-25 | defects living only in a 600-line table; three hand steps per issue per close |
| `docs/BACKLOG.md` generated (R267) + `backlog --check` | 09-25 | a carry in six homes that could not be counted |
| docmaint check 8 (a "merged as vX" claim names a real tag) | 09-25 | five documents claiming a merge that had not happened |
| docmaint check 7 (byte ceilings) | 09-25 | 189 KB of sprint file at 12 % live |
| `PS2X_HLE_STATS` distinct-return-value counter | 09-12 prescription | "a bound stub with thousands of calls and one distinct return value is the whole defect class" |

**Rule-only, and every one of these recurred:**

| Rule | Recurrence |
|---|---|
| §5 rule 1, explicit pathspec, never stage another session's file | 09-13 `872d8d6` → 09-18 `6b7a2b3` → 09-21 `685ffd3`/`7041235` |
| §5 rule 11, correct a false sentence the same hour | broken 09-12 (2 weeks), 09-17 ("every row in §4"), 09-19, 09-25 (twelve places) |
| "'START HERE' names the sprint in flight" (09-12 item 5 rule 2) | still wrong 09-19 (`f88ef34`); HANDOFF §2 two sprints stale 09-25 |
| "Do not push" in a brief | ignored 09-21; replaced by the push-kill tool; the tool then bypassed by hand 09-23 |
| Remove junctions before `git worktree remove` | "It happened TWICE (2026-09-21)" |
| Never edit a running chain script | 09-21 cost a 10-minute capture's pin step; near-miss again 09-25 |
| A launch script must source `env.sh` or talk to loopback | the class was recorded 09-20 (`:135-142`); it happened again 09-25 |
| No wall-clock upper bounds in tests (09-20 AC-3; `QUARANTINE.json` never built) | a 5 s renew bound failed under a neighbouring build, 09-25; "timing smoke tests widened" |
| Kill orphaned watchers / prefer `run_in_background` over Monitor | 213 orphans accumulated over 8 days before anyone looked |

The project states the principle itself (`2026-09-12-process-audit.md:25-29`, quoted back at `2026-09-20:286-288`):
"every guard is a sentence, and … every failure on record was caught by a person, not a script." The four weeks bear
it out: **no rule-only fix in this record is free of a recurrence; most tool fixes have none.**

The one exception worth naming is that the tools also fail when they are bypassable by hand: the worktree push-kill
(a tool) was defeated on 2026-09-23 by a hand-run `git config` without `--worktree`, which is why the standing advice
moved from "run the config" to "use the script".

---

## 6. Per-sprint outcomes

Counts are from each plan's task table and Log, read 2026-09-25/26. Sprints 11–13 are the ones with plans in scope;
Sprint 12 is split because its code half ran in a cloud session.

| Sprint | Dates | Tasks tracked | Closed inside | Not done / withdrawn / backlogged | Carried out | Fix rounds | Rulings |
|---|---|---|---|---|---|---|---|
| 11 "a public repository a stranger can trust" | opened 2026-09-23, **closed 2026-09-25** as `v0.11.0` | **27 Outcome rows** (26 planned/derived + 1 unplanned filler); Task 2b and Task 7b were *created by reviews/rulings mid-sprint | **24 DONE** | **1 WITHDRAWN** (11b, by R249, then "reopened by R251" and left to the owner as D1/O5); **1 "MEASURED, not green"** (18 Step 1 → issue #25); **1 NOT DONE — "the owner's"** (18 Step 3, needs the `sprint-*` ruleset lifted under their credentials). Four more DONEs are functionally owner-blocked (11, 18 Step 2, 19's two halves, audio-out's retraction branch) | to Sprint 12: the naming programme (R257, R260, R261, halves of R259/R262 — **five rulings carried, not closed**); **six issues** (#25, #26, #33, #37, #38, #42), "**All six were re-verified true at the close**"; STORY's missing three days "carried as a Sprint 12 item **rather than half-written**"; the `--accept-pins` half still unfixed | 6 review events; only Task 2b needed **two** ("`6aed718` + two fix rounds") | **19, R245–R263**; "**no number is vacant and none is reused**"; **one retraction on substance** (R249 → R250 half-correction → R251 retraction, all inside ~36 h) |
| 12 "the readable image" (cloud half) | 2026-09-24 → 09-25, **a Claude cloud session** | **18** (11 planned + 4 added mid-sprint by ruling + 3a/3b splits); 14 research questions Q1–Q14 | **18 DONE**, 8 of them "`DONE (code), PROOF PENDING`" until the local row carried a result | 0 not started, 0 withdrawn as tasks; **1 sub-rule withdrawn** (S12-R16 rule 4: "the constructor rule as written picks destructors (0 of 21) : **it is withdrawn**") | "**Deferred:** 518 loose rows wait for a second independent lever"; a **nine-item** "follow-ups a later task takes" list (incl. what became #48) | 3 named fix rounds + several review-driven rule amendments; Task 3 took a fix round then two re-applies | **25, S12-R1..R25**, listed non-monotonically, each ending "**Cost if wrong:**"; + R265–R268 appended "because the ruling scan reads the plans and not `docs/audits/`" |
| 12 (local half) | 2026-09-25 04:40Z → close | the PROOF row + merge + close | done: recomp/runtime/test/gate `GATE PASS (3/3)`, `PINS MATCH (13)` | — | issues "opened 0, closed 0, carried 0 (the `Sprint 12` milestone held no issue and is closed)"; the six Sprint 11 issues "were never in Sprint 12's milestone and are **ruled not carried twice**" (`docs/STATUS.md:44-49`) | one documented lesson: the lock's missing queue cost ten minutes | R264 |
| 13 "nothing carried twice" | opened 2026-09-25 08:40Z, **still open** at 2026-09-26 02:23Z | **45 rows** (0, V1–V8, R1–R7, H1–H7, C1–C9, U1–U8, S1–S6, N1–N4, O1–O3, 99) | **~38 DONE/MERGED** within ~18 hours | **NOT STARTED: H5 (#41), Task 99 (the close)**; V5 steps 2–5 not run ("the owner's client is muted"); **RULED TO THE BACKLOG: U3 (#57), U8 (#55), N4 (#58)** under S13-R10/R11; O1's mixed leg and O2 held for the owner | opened issues **#51–#59** as backlog rows with bars; #34 "keeps its console-peer bar" | **34 "fix round" mentions**, 17 "PASS WITH FINDINGS", 19 "review PASS" | **13, S13-R1..R13**; four proof chains green on both revisions |

Two structural notes the plans make about their own records:
- Sprint 11's Outcome, `docs/superpowers/plans/2026-09-23-sprint-11.md:493-495`: "**the step checkboxes above were
  not maintained once work moved into agent worktrees, so they are not the record — this is.**"
- Sprint 12's task-state convention, `…/2026-09-24-sprint-12.md:86`: "A task that needs the local tree is
  `DONE (code), PROOF PENDING` until its row carries the local result", and the handoff's binding form
  (`…-cloud-handoff.md:197`): "**a task never becomes DONE on the cloud's word.**"

Stated reasons for slippage, quoted:
- **Owner presence.** "**Hold (2026-09-25 17:05Z):** the owner is at the machine ('light work'); no build, launch or
  gate until they name a window" (`memory/sprint-13-state.md`). And "V5 steps 2–5 NOT run: the owner's client is
  muted (no audio measurement)."
- **Lock contention.** C2 waited "78 min in the queue" for one hold (sprint-13 Log, 01:29Z); the queue's TAKEN lines
  that evening carry waits of "2187 s, 2572 s, 2907 s".
- **Host contention.** The reaper removing queued jobs for memory twice; the frame-time spread of 30 % attributed to
  "five agents' dispatch and the owner's light work".
- **Scope, ruled out rather than slipped.** S13-R10 on U8: "Applying upstream #206's rule changes the generated
  image's shape … a sprint task of its own, and **a Sprint 13 that carries it would not close**."
- **No cloud session.** S13-R11: "no cloud session was opened this sprint, so the [C] tasks are dispositioned without
  one."
- **Sprint 6's own ledger** (the earliest measured slippage, `2026-09-17:113-130`): "The plan's checkboxes were not
  maintained: only Task 8 and one step of Task 1b are ticked, while STATUS records most of the rest as done." Task 2
  Step 4 "was never measured"; Task 3 Steps 2–3 "not"; Task 6 "not started"; Task 9 close-out "not started".
- **Session exhaustion.** Sprint 11 plan `:571`: "**Interim, 2026-09-23 14:00Z — the first night ended on the
  session limit.**"
- **Lock starvation, a measurement cancelled.** R255 (`:595`): "**the loop lock goes to the r0004 critical path
  first.** Six queued r0004 runs sat behind back-to-back suites for hours and **one was cancelled**."
- **A harness capability gap blocking a proof.** R246 (`:586`): "the traversal did not happen because the harness
  cannot type a chat line (no on-screen keyboard opens for chat in the briefing room) … Waiting on a new harness step
  would hold Task 4's README narrowing and the server clamp's deployment behind a driver feature." That gap is still
  open as issue #26, now carried twice.
- **CI red on the base branch, and a refusal to widen scope.** Sprint 12 plan `:779-793`: "**CI on `sprint-12` is
  red, and the failure is the base branch's** … **No fix exists on the base yet.** … **Sprint 12 does not widen its
  branch with a change to Sprint 11's harness tests**; the acceptance bar's CI item **is blocked by the base**."
- **Proof throughput is windowed, not on demand.** Sprint 12 plan `:18-19`: "The proof half of every applied rename
  (recomp, runtime, gate) is the local controller's, **batched at the owner's build windows**."
- **Evidence destroyed by a log filter.** Sprint 12 plan `:266-268`: "the chain's log filter kept only the step's
  last twenty lines, **so the two counts are not in the record**."
- **A gate refused by leftover state from a previous run.** Sprint 12 plan `:279-281`: refused "**PINS DRIFTED: env**
  — the r0004 standard carried a stray `PS2X_AUDIO_VOLUME=0` **written by the rebuild proof's `--accept-pins`**
  (issue #45's class)."
- **Plans are unreliable as records** generally: `carry-backlog.md:263-268` "Unticked against ticked steps:
  `2026-09-07-parity-harness.md` 40/0, `…voice-headset.md` 44/0, `…menu-cost-2b.md` 30/0, `…goal-2-release-build.md`
  20/26, `…goal-3-knob-retirement.md` 19/32, `2026-09-23-sprint-11.md` 50/11, `2026-09-24-sprint-12.md` 29/9… **A
  reader cannot tell a done step from an abandoned one without the Outcome table.**"

### 6.1 The one written coordination contract: the Sprint 12 cloud handoff

`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md` is the only document in the project that specifies how
two controllers share one repository. It is worth recording because it is the one coordination mechanism that the
record says **held**.

Its frame, `:174`: "**Two controllers, one repository, one open sprint on `main`'s doorstep.**" The division,
`:33-38`: "What you cannot do: **build or run the Windows game, take the lock, run a gate.** Every Sprint 12 item
therefore has a **code half** (yours) and, where it changes the generated image, a **proof half** (the local
controller's…)". Its seven §5 rules, compressed: (1) branch — "**never push to `sprint-11`; never open a PR to
`main`**"; (2) **a file blacklist** — "**Files you never edit on `sprint-12`** (they are Sprint 11's live state and
**would conflict at every merge**): `CURRENT_SPRINT.md`, `HANDOFF.md`, `STATUS.md`, `HUMAN_TASKS.md`, `KNOWN.md`
rows Sprint 11 owns", with the local controller mirroring; (3) a **separate ruling namespace** `S12-R<n>` folded into
the global counter at the merge; (4) **`PROOF REQUESTED`** rows with exact commands and what green means — "a task
never becomes DONE on the cloud's word"; (5) review by "a **fresh sub-agent that did not write it** … **fix rounds
until the re-review is clean**", with the diffs declared non-record ("**it is your working memory, not the record**");
(6) "**Batch pushes**" because a non-docs push costs an hour of runner; (7) "**The owner relays** … write it in the
plan's log with a **`LOCAL:` prefix** … **Do not wait: do the next lock-free task.**"

It was amended by the local controller **before the cloud started** (a ratification block, `:20-26`) with five
corrections — including the research-number collision that had already happened: "you take **47** onward (46 became
the peer's day-one record … at the owner's request the same evening)".

Verdict in the record, `docs/STATUS.md:44-49`: "the cloud handoff's §5 **held as written** — the Sprint 11 controller
pinged at each lock hand-over and the lock serialised the rest — with one lesson: the lock has no queue (issue #36)."

Two of its own premises were nonetheless wrong and had to be overturned by the session it briefed:
- the Ghidra-in-Docker route (`:105`), retired by S12-R2 — "**a refusal retires the goal**";
- "the cloud cannot run the recompiler" (`:36-38`), overturned by S12-R11 — "**the handoff's assumption that it could
  not was the Windows toolchain's, not the recompiler's**" (Sprint 12 Log `:800`).
And one environment failure is recorded verbatim at `:42-43`: "the sandbox runs setup scripts **before the clone and
without the environment's variables** — proven 2026-09-24 evening, exit 6"; plus `:48-50` "**Plugins do not carry
into the cloud** … follow it from here, **not from memory of the skills**."

---

## 7. "Carried twice" — what it means and why Sprint 13 is named after it

The mechanism is in `docs/GIT_STRATEGY.md:293` and `docs/DOC_MAINTENANCE.md:302-305`:
> "**Carry** at a sprint close: the `carried` label, one comment saying why it did not close, and the next sprint's
> milestone or none — all three by `python -m tools_py.issues carry N …`, **which refuses an issue already carried
> twice (the owner's question)**."
> "**An issue carried twice is a question for the owner** (`docs/HUMAN_TASKS.md`): keep it, or close it as not
> planned under a ruling."

The rule's hole, named by the audit: `2026-09-25-project-audit.md:82` (B10) — "'carried twice' applies only to issues
in a milestone"; `carry-backlog.md:260-262` "Because the §7 stack review works only from issues … those items fall
outside the 'second carry is the owner's question' rule." Since the tracker was only opened on 2026-09-23 (R252),
almost nothing in the carry was an issue.

What the count actually looked like on 2026-09-25 (`carry-backlog.md`):
- **133 distinct rows in six homes**: `CURRENT_SPRINT.md` (two close blocks, a filler paragraph, a "what carries"
  list, the standing backlog), `HUMAN_TASKS.md` (two "what needs you" sections, a morning block, a 200-line §Open),
  21 issues, and the plans' Outcome sections (`:253-258`).
- **Issues covered about 20 of the 133** (`:259-260`).
- **Seven rows at six sprints carried**: the community preset [S7–S12], the owner's listens [S7–S12], the two-machine
  match [S7–S12], and the standing backlog's oldest four [S6–S12] / [S1, S6–S12] — one of them "Never started", one
  "Open and unowned since 2026-09-12" (`:60`, `:112`, `:146`, `:174-177`).
- Three at five sprints, nine or more at four.
- `:275-276` "**Rulings that carry work** (R207 'still queued', R221 'still queued', R256's Finding 9) sit only in the
  ledger's Status column. No backlog or issue repeats them."

What Sprint 13 did about it: **R265** ruled the four oldest rows own-or-decline ("six sprints without one is the
evidence" for declining the soft-double chain); **R266** put the six Sprint-11-carried issues into Sprint 13's
milestone as a *first* carry; **R267** made `docs/BACKLOG.md` the one generated home. Today `docs/BACKLOG.md` reports
"20 open issues" with a `Carried` column — "*Carried* counts the sprint closes an issue has survived … **at 2 the
next close asks the owner**" — and #25, #26, #33, #42 sit at **2**. Section 2 holds "**38 rows** … ruled not to be an
issue", each with its bar, "so the next review does not re-ask". The file is already one issue behind (#60 opened
2026-09-26) — the `backlog --check` staleness gate is what catches that.

---

## 8. What the owner actually has to do, and where the process waited

The owner's role is defined as authority plus a short list of irreducible acts. `docs/HANDOFF.md` §5 rule 13:
"**Owner-only actions stay the owner's:** publishing a release, flipping the repository public, branch protection and
permissions, signing, spending money, deploying the site. Prepare them; do not perform them unless the owner says so
in words." Rule 10: "What only the owner can verify goes to `docs/HUMAN_TASKS.md` and the loop moves on. **Do not
wait on a person.**"

The owner's own standing instruction is to not be asked (memory `owner-prefers-action-over-asking.md`, 2026-09-20):
"tell me when it's ready, but **if i don't respond within 15-20 mins, proceed**"; and the note's reasoning — "A
question dialog stops the loop dead and makes his attention the bottleneck, which is the thing the controller's seat
is supposed to remove."

The consolidated list on 2026-09-25 is `2026-09-25-project-audit.md` §3, "**the owner's sitting — every decision in
one list, with the default the loop is on**" (`:185-205`), thirteen rows O1–O13, reduced by Sprint 13 Task R4 into
`docs/HUMAN_TASKS.md` as **fifteen rows O1–O15** (`:22-36`) — "with two rows that audit missed (O14, O15)". Header,
`:3-4`: "Every row stands on a default: **the loop proceeds on it and never waits**."

| Row | The hand needed | Default the loop is on | First asked | Waited |
|---|---|---|---|---|
| O1 | the legal position on shipping the exe + decrypted ELF | "no public download; builds reach testers only by your hand" | 2026-09-20 | 5 d |
| O2 | upload and publish the v0.10.0 / v0.11.0 / v0.12.0 archives | "the drafts stay empty … publishing is always your click" | 2026-09-20 | 5 d |
| O3 | disc-derived bytes in the tree, licence split, signing, the landing page | "nothing moves; GPL-3.0; unsigned; the deploy is yours" | 2026-09-20 | 5 d |
| O4 | two bug-pipeline words, four site relays, the PSRewired DM | "no reply is sent … the relays and the message unsent; no data page" | 2026-09-20 | 5 d |
| **O5** | PSRewired's answer / mixed revisions (Goal F) | "the community preset stays `COMMUNITY_SERVER_ADDRESS_TBC` … Task 11b stays withdrawn" | **2026-09-17** | **8 d** |
| **O6** | the ladder's schedule window; the first two-machine match | "the scheduled entry stays DISABLED … every online result is two instances on one host" | **2026-09-17** | **8 d** |
| **O7** | ears and hands: the music listen, Q4's four tries, the pad, the prefilled login | "the loop does not wait (**the listen gate has been bypassed since 2026-09-20**)" | **2026-09-17** | **8 d** |
| O8 | a PLAYTEST sitting on the current build | "the loop rewrites PLAYTEST for each build it can hand over" | 2026-09-20 | 5 d |
| O9 | ~~the story's five missing days~~ | **answered by default (keep), 2026-09-25**; struck | 2026-09-25 | 0 d |
| O10 | file the three #244 patches, the KEEP verdicts, two BinExport defects | "drafts ready … nothing is filed" | 2026-09-25 | 0 d |
| O11 | naming defaults D1–D7, the hand read, the 148 slot namings | "the defaults stand; the 148 stay applied" | 2026-09-25 | 0 d |
| O12 | the crouch default (`l3` vs registered `off`) | "the launcher's `l3`" | 2026-09-25 | 0 d |
| O13 | repo settings, 3 open Dependabot PRs, money after ~March 2027 | "as they are; no history rewrite" | 2026-09-20 | 5 d |
| O14 | the merged-branch sweep (lift the `sprint-*` ruleset) | "the branches and the ruleset stay" | 2026-09-20 | 5 d |
| O15 | Linux on real hardware | "CI and the VM stand in; R107's number stays unmeasured" | 2026-09-18 | 7 d |

Oldest wait in the current file: **8 days** (O5, O6, O7). But the file is two days old; the work inside the rows is
much older — O6's two-machine match is "carried since Sprint 7" (`docs/PLAYTEST.md:118`) and O7 "replaces the **six
listens owed since 2026-09-17**, each on a build later fixes replaced."

The predecessor file shows what the queue looked like before it was pruned. `docs/archive/HUMAN_TASKS-to-2026-09-25.md`
is 821 lines; its disposition table gives **87 items** a kind — **51 folded into O1–O15, 30 superseded, 3 taken by the
loop, 3 kept**. Five surviving `## Start here` generations span 2026-09-20 → 2026-09-23 (the header claims seven):
the queue was re-headed roughly daily and **never drained**. Its `## Open` block held **20 unchecked boxes against 1
checked**, and its first open item was the **fifth** round of the same music listen.

**PLAYTEST as the measure of how long the owner-facing loop has been stalled.** `docs/PLAYTEST.md` is row O8's
script, and it cannot be run:
- `:15-21` "build: **NOT BUILT. No archive exists for the current tree**: the v0.12.0 draft release has no assets";
  `:40-41` "**Not ready until the block above is filled.**"
- Last sitting **2026-09-22, on the 2026-09-21 build** (`:8`), and the page admits it went stale for three days
  (`:10-12`): "**this page still presented the 2026-09-21 build as 'Ready' three days after it was played, and its
  decisions section asked questions already answered.**"
- Steps with **no recorded answer**: 1, 2, 4, 6, 7, 8, 10, 11, 12, 13, 14, plus the folded-in controller/audio items
  and both decision questions. Step 3's four P4 fixes "landed 2026-09-20, **never reported on**".
- It also records where a defect is invisible to the person being asked to find it: `:110-111` "**If the game cannot
  connect at all, pick Custom, type `3.143.65.100`** … Tell me if you had to, because **nothing on screen says that
  is what went wrong**"; `:113-117` "The sound was charged to a sound bank and the charge withdrawn by measurement
  (R239); **what you heard is not yet found**."
- And it is already stale again in the other direction: `:112` says the saved password "is not expected to yet
  (issue #27)", while `docs/KNOWN.md:197` records #27 settled on 2026-09-25 ("the password survived. **The driver
  misread the screen**").

Where the process genuinely waited, as opposed to proceeding on a default:
- **The moderator's Discord answer** (the community server): pending since 2026-09-23 (`:171`), and nothing may
  connect until it arrives.
- **The owner's ear**: six sprints of listens; Sprint 13's V5 steps 2–5 were not run at all because "the owner's
  client is muted".
- **The owner's hands at the machine**: Sprint 13 paused all lock-bound work at 17:05Z on 2026-09-25 ("light work");
  the mixed-match leg "needs the DNS stub, LAN_IP and PCSX2 — likely the owner's" and did not run.
- **The ladder's schedule**: `harness-tools.md:34` "The ladder has not run since 2026-09-23 04:21Z" — the Task
  Scheduler entry stays DISABLED until the owner names a window; the audit's `schtasks /Query` read "Status:
  Disabled" (`carry-backlog.md:151`).
- **Dependabot**: four PRs "open and failing since 2026-09-21" (`2026-09-25-project-audit.md:170`); three still open.
- **The release**: no public download exists; the `v0.10.0` draft has no assets and "the release-draft workflow's
  verify half never ran" (`:169`).

Counter-evidence that the owner is not the bottleneck by default: the loop shipped 302 commits and closed two sprints
on 2026-09-25 with the owner away for most of it, under three written mandates
(`memory/overnight-mandate-2026-09-20.md`, `evening-mandate-2026-09-25.md`, and the 2026-09-23 "twelve-hour mandate"
recorded in `docs/STATUS.md`: "proceed with all remaining sprint 10 work and finish sprint 10 … Once that's done,
formalize and begin sprint 11 autonomously").

---

## 9. Trend: more reliable *and* heavier

**More reliable — the evidence:**
- Enforcement moved from prose to code. `docs/DOC_MAINTENANCE.md` §4 now has **ten mechanical checks**, "each aimed
  at a rot mechanism that actually bit this project (the seventh and eighth are R268's, the ninth and tenth Sprint 13
  Task R3's, all added 2026-09-25)", and each "is fired once against a planted defect" (`PlantedDefectsTest`) — with
  the reason: "**A gate that has never failed is not known to work**, and this one found two real defects and one bug
  in its own test on the day it was written."
- The check that should have existed on 09-12 exists now: check 8 refuses "merged to `main` as vX" for a tag that
  does not exist, and **skips out loud** when origin is unreachable ("never passed silently").
- The known-issue stack is two days old and already disciplined: 32 issues, 11 closed, every close requiring "the
  artefact that met its bar" (`docs/HANDOFF.md` §5 rule 14); Sprint 13 closed 11 issues in one evening (#27, #30,
  #35, #36, #37, #38, #39, #41, #45, #46, #48) and opened nine backlog rows with bars (#51–#59).
- The lock's three-year-of-incidents history closed in one night: #35, #36, #37 all closed 2026-09-25, and the
  evidence of the fix is behavioural — "the ladder ran **first time**" and "the queue served every ticket in arrival
  order tonight".
- The review loop is real and catches blocking defects: Sprint 13's C4 review found that routing every tail call
  through the function table broke a stub "whose start is an owner's resume target" — a **blocking find** that became
  follow-up #60 (git log, `f9f81614`).
- **Retraction latency shortened measurably.** 2026-09-12/13: "about a day for the first three and **two weeks** for
  the freeze description" (`docs/KNOWN.md:207-213`), all three retracted "at close-out anyway". 2026-09-14: the grey
  water theory retracted "**the same hour as the run**" (`:163`). 2026-09-25: the Sprint 11 close review applied 30
  of 36 document rows in one commit (`8612c2d3`), and the Sprint 12 close "applied 45" of 60 (`docs/CURRENT_SPRINT.md:105`).
  §3's rule is now explicit: "Retract **on discovery**, not at close-out" (`docs/KNOWN.md:204-213`).
- **Wrong beliefs are now cheaper to hold.** 19 retractions across the whole project; the last four (`:193`–`:197`)
  are all cases where **the instrument, not the game, was wrong** — the scorer counting attract frames, the driver
  reading PASSWORD off the CONNECTING screen, a correlation bucketed by line number, an endpoint blamed for dips that
  survived a wired device. That is a maturing measurement stack, not a decaying one.
- Retractions are now handled in place and counted: `docs/CURRENT_SPRINT.md`'s Sprint 11 ledger closes with
  "**Collisions: none. Missing: none. Vacant: none.**" and the Sprint 10 ledger with "Three rulings changed state
  during the sprint and one changed state at the close… **Collisions: none. Missing: none.**"

**Heavier — the evidence:**
- **268 rulings in four weeks** (next free R269), plus 25 `S12-R*` and 13 `S13-R*` in separate namespaces. Sprint 10
  alone issued **64** (R181–R244).
- A new controller's required reading is now ~1.04 MB of live documents, of which
  `docs/KNOWN.md` (266 KB) and `docs/STATUS.md` (260 KB) are two files; `docs/HANDOFF.md` alone carries 14 rules and
  16 traps, several with `> Superseded` blockquotes nested inside them.
- The documents needed to *not break the process* have multiplied: `DOC_MAINTENANCE.md` (312 lines),
  `GIT_STRATEGY.md` (311), `LOOP_PROMPT.md` (127 but pointing at four others), `BACKLOG.md`, plus the memory
  directory's 34 notes.
- The ceilings are themselves an admission that growth is the default: `tools_py/docmaint.py:93-98` had to cap
  HUMAN_TASKS at 12,230 bytes after it reached **104,000**.
- The audits get bigger, not smaller: 12 items (09-12) → 10 ranked findings + 3 designs (09-20) → **403 findings
  across six reports** (09-25).
- Some rot is caused by the tools: `harness-tools.md:66` "the tool is shaping the prose" — `docs/KNOWN.md:225`
  carries "*(Re-headed 2026-09-25 so `python -m tools_py.issues audit` can see it…)*".
- `docs/KNOWN.md` itself now holds **258 rows** (100 proven, 35 believed, 19 retracted, 104 standing hazards) at
  260 KB, with an average line near 400 characters. It is the document `docs/LOOP_PROMPT.md` step 2 tells every
  iteration to read "before forming any hypothesis".
- The carry's *documentation* grew even as the carry shrank: `docs/BACKLOG.md` is a generated 18 KB replacing six
  homes, but `docs/backlog_ruled_out.txt` now has to carry 38 rows with a bar each "so the next review does not
  re-ask".
- The lock protocol itself is now a page: `docs/LOOP_PROMPT.md`'s "Lock protocol" section covers queue tickets,
  nested holds, heartbeat reaping, the busy list, mixed script versions and a rollout procedure — for a mechanism
  that on 2026-09-09 was a file and a `[ -f ]` test.

**Both at once, in one sentence from the record.** The 09-20 audit's diagnosis — "every guard is a sentence" — was
answered between 09-20 and 09-25 by nine new enforced mechanisms; and the 09-25 audit's largest finding is not a
defect in the code but 133 unfinished items in six homes and a record whose live fraction is 12 %. Reliability moved
from people to tools; weight moved from tools to the record.

---

## 10. What the 2026-09-25 project audit concluded about the process

Beyond the one-paragraph verdict in §2.5 above:
- **The record, not the code, is the failure surface.** "the project's *code* is in better order than its *record*"
  (`:17`). The runtime "has no orphaned source and the launcher no TODO"; the harness has "155 test files and 2,800
  cases".
- **Two live claims were false on the night**, and both were the kind a check can catch. The audit's own disposition
  for row 1 names the behaviour to stop, not the document to fix: "the documents were written ahead of the act, which
  is the pattern to stop — Sprint 13 Task R1 adds a check that a 'merged as vX' claim names a tag that exists."
- **The carry is uncountable, and that is the process defect.** R267's cost/benefit is stated as "one generator and a
  registry row; **what it buys is that 'carried twice' can be counted**."
- **The appending documents needed ceilings, not discipline.** R268's stated benefit: "**what it buys is that this
  audit's largest finding cannot recur silently.**"
- **The owner's backlog is answerable in one sitting.** §3's preamble: "These are the rows the loop cannot take
  further. **Each has stood through two or more sprints; answering them in one sitting is what turns most of the
  carry into closures.** The loop proceeds on the default in the third column."
- **Declining is a legitimate outcome and was made one.** R265 declined the EE soft-double chain, the gameplay-state
  probe as a gate leg, and put retire-or-test bars on two believed render rows: "Cost: four rows stop being carried;
  what it forgoes is a numeric oracle nobody has needed."
- **The audit's own priority order is the project's standing rule**, restated at `:243`: "ordered by what the owner
  meets first (the project's standing rule: **visible defects above infrastructure**), then by what pays every night
  (the lock), then by what a stranger sees."
- One area it did not clear: `2026-09-25-project-audit.md:129` (D13) — "114,399 `unhandled-instruction` lines never
  classified" — and `:141` (E2/E3) five upstream "silent-corruption fixes in paths SOCOM uses" that had gone 38 days
  unevaluated across 27 open upstream PRs.

---

## 11. Limits of this evidence file

- Sprint 13 was **still open** while this was written (its Log reaches 2026-09-26 02:23Z; Task 99, the close, is
  `NOT STARTED`), so its closed/carried counts are provisional and its Outcome section is empty: "*(written at the
  close)*".
- Nothing here was re-derived by running a suite, a gate or a build; every number is read from a file, a `gh` query
  or `git log`, per the read-only constraint. Where the project's own documents disagree, both readings are cited.
- The Claude memory directory is a private, untracked record; its 34 notes are the only home of several incidents
  (the 213 watchers, the `pushurl` collision, the duplicate-implementer dispatch) and they are not citable from the
  repository.
- `docs/audits/2026-09-25-project-audit/{code-runtime,external,stranger-player}.md` were not read in full here; their
  process-relevant findings are taken from the master list's dispositions.
</content>
</invoke>
