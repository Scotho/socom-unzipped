# Sprint 11, Goal 6 — "the progress story" (design)

Written 2026-09-19 (host clock) by the controller, as the full design for the Sprint 11 spec's
**"Goal 6 — the progress story (owner, 2026-09-20)"**
(`docs/superpowers/specs/2026-09-20-sprint-11-release-hardening-design.md`). The goal entered the record in
`91b038d` — *"Sprint 11 Goal 6 -- the progress story: a linear, fun timeline from the first render, drawn from the
commit history and the monitor project's run index (owner 2026-09-20)"*.

**Authority.** `docs/KNOWN.md` wins over this document wherever they disagree, as it wins over every spec. Where this
document and the Sprint 11 spec disagree, the Sprint 11 spec is the owner's text and wins on *what* the goal is; this
document only settles *how*.

**Status: drafted, not opened.** Sprint 11 is drafted and Goal 6 is ordered last inside it. §1 says why a draft is
being written now anyway and exactly what the later pass must still do.

**Dates and the clock.** `docs/HANDOFF.md` §3: *"the documents and commit subjects are stamped 2026-09-20 for a
session the host clock calls 2026-09-19. Do not 'correct' either; when you write a date, use the host's."* This
document uses the host's. The story itself makes one choice and states it once in its own header: **its dates are git
author dates** (`git log --date=short`), because those are the dates a script can read and a reader can re-derive. A
document dateline that is one day ahead is not an error to fix, and the story does not reconcile the two.

**What was read to write this.** The Sprint 11 spec in full (Goal 1 and D1, Goal 2, Goal 3, Goal 9, "Decisions that
are the owner's", "Order inside the sprint"); the Sprint 9 spec in full; `docs/KNOWN.md` §§1-4;
`docs/audits/2026-09-20-test-harness-and-process-audit.md` (HO-I, SV-1, SV-3, HO-2); `docs/GIT_STRATEGY.md` §§4-5;
`docs/CURRENT_SPRINT.md` (read-only — the sprint-9 controller owns it); `tools_py/parity/gate.py`;
`tools_py/tests/test_test_hygiene.py` and `test_map_refs.py` as the shape a test in this suite takes;
`../socom_monitor/README.md`, `scan.py` and `build.py`; and git itself. Every number below was produced by a command
on this host, not recalled.

Repo-level facts, measured while writing (they move; re-measure before quoting):

| Fact | Command | Value |
|---|---|---|
| Commits on `sprint-9` | `git rev-list --count HEAD` | **742** |
| Days with commits | `git log --format=%ad --date=short \| sort \| uniq -c` | 2026-09-02 .. 2026-09-20, **17 of 18 calendar days** (there is no 09-03) |
| Tags | `git tag` | **none** |
| Where `main` is | `git log -1 --format=%h main` / `develop` | both **0e14323**; Sprint 9 is unmerged |
| `logs/` in the repository | `git ls-files logs \| wc -l` | **0** — `/logs/` is git-ignored |
| Pictures in the repository | `git ls-files docs/research/assets` | **8 files** |
| Run directories on this host | `ls -d logs/parity/*/` | **250**, plus 150 under `logs/parity/gate/` |
| Gate summaries | `ls logs/parity/gate/*/summary.txt` | **148**, of which **2** carry the `EXE ... sha256=` line |
| `docs/STORY.md` | `ls` | does not exist |

---

## 1. Why a draft now, when the sprint orders this goal last

The Sprint 11 spec's "Order inside the sprint" puts Goal 6 near the end: *"Goal 6 (the story, last, when there is an
ending to write)"*. Writing a draft now is not a violation of that ordering, and the reason is worth stating rather
than assuming:

- **The timeline to date is finished history.** The first 742 commits happened. `55f5170` (2026-09-02, the Unicorn EE
  harness and the APACHE00.ZDB decryptor) will not move, and neither will the first kill on 2026-09-13
  (`811b886`, run `s5_t5_ladder2`). What the release changes is the *end* of the story, not its body.
- **The record rots faster than the story does.** The evidence this story rests on is already thinning: twelve cited
  gate stamps were archived to `D:\socom_archive` on 2026-09-13 (`logs/ARCHIVED_TO_D.txt`); the whole Linux evidence
  set stayed in the VM and six run ids cited in `docs/KNOWN.md` have no artefact on this host; two commit hashes cited
  in `docs/STATUS.md` do not resolve at all (§4.2). Writing the collector and the citation test now means the next
  loss is caught by a test instead of discovered by a reader.
- **It is lock-free.** Every part of this goal is pure Python and prose. It can be worked in the windows where the
  loop lock is held by a build or a launch, which is exactly the filler `docs/CURRENT_SPRINT.md` asks for.

**What the later pass must do to close it — the four things a draft cannot contain:**

1. **The release entry.** The story ends at the release: the tag (`v1.0.0`, `docs/GIT_STRATEGY.md` §4), the archives
   and their `SHA256SUMS`, the repository going public. None of that exists; there is not one tag today.
2. **The D1 citation reconciliation.** If the public history is rewritten or re-imported, every commit hash in the
   story changes or disappears. §4.4 designs for it; the later pass runs it.
3. **The pictures.** §5 says which milestones have one and recommends a line; the owner draws the line and the images
   are added to the tree in that pass, not this one.
4. **The site page.** Goal 3's territory, in `../scotho`, which belongs to the hosted-server session. §6 writes the
   contract; the later pass agrees it with that session.

Anything the draft writes about the present must therefore be written so that adding an ending is an *append*, not a
rewrite. That is a constraint on the entry format (§2) and on the data file (§6), and it is why the story is ordered
strictly by date with no "and finally" framing anywhere but the last entry.

---

## Status, 2026-09-20 (second pass, same night)

The four things §1 said the later pass must add were taken as far as the record allows the same night, on the
owner's instruction, without publishing anything:

- **Pictures — done, ten of them**, all frames the project's own program produced, none over 1 MB, 2.27 MB in total,
  copied to `docs/story/img/` and inventoried one row each in `docs/story/PICTURES.md` (the disc-derived table's
  input). Four were already tracked under `docs/research/assets/`. `cite.py` now fails on a picture that is uncaptioned,
  untracked, missing, over budget, outside `docs/story/img/`, un-inventoried, or a second one in the same entry. The
  line stays the owner's (§9 Q1); what was picked is a conservative reading of §5.3 — no contact sheet, no frame
  from a run whose directory holds `server-side.log` without inspecting it, no asset lifted from the disc.
- **The site page — built locally, not deployed.** `tools_py/story/site.py` renders `docs/STORY.md` +
  `docs/story/timeline.json` into `docs/story/index.html`: one self-contained page in the landing site's own palette and
  type, pictures from `img/`, per-entry anchors `#<date>-<slug>` (the URL shape §6.2 asks the site for), each commit
  citation a link to the repository's commit page. It is the reference rendering the hosted-server session takes a copy
  of; nothing was pushed to `../scotho` or to any live host. `timeline.json` rows now carry `id` and `picture` for it.
- **D1 reconciliation — the mechanism, not the decision.** `tools_py/story/remap.py` does §4.4's three paths (a
  mapped rewrite, an unmapped rewrite with unique subjects, an unmapped rewrite with a duplicate that is reported and
  never guessed), tested against a fake history. D1 itself is still the owner's, and until it is answered the citation
  format stays as it is.
- **The release entry — a template, because there is no release.** `docs/story/release-entry.template.md` names
  every field the release run stamps and where each comes from; `cite.py` fails the suite on a `{{`/`}}` placeholder
  left in `STORY.md`, so a pasted-but-unfilled template cannot ship. The uncited "Where it stands tonight" section is
  what it replaces.

Still open after this pass, and Sprint 11's: the editorial cut to 45 entries or fewer (§2.4's note), the owner's four
questions in §9, and the release itself.

## Status, 2026-09-20 (third pass: the owner's rewrite)

On the owner's instruction, the same day: (1) one entry removed at the owner's instruction; (2) every entry rewritten shorter and plainer — casual, to the point,
the technical detail kept in the `How:` line and the interesting numbers kept in the body, the hedging cut; (3) the
pruning audit done: 52 entries became 44 by merging ten pairs that told one story (a mission loads / its first frames;
the title labels / the world stops coming apart; the speed-up / the first scripted walk; the round that "would not
start" / online players can move again; the KNOWN file / the retractions; the mission stage grading the cinematic /
the check learns what failure looks like; the teleport found / the teleport fixed; the launcher / the audit of the
same day; the lobby presses / the launcher learns your pad; the server's name / the playtest build) and adding four
for what landed on 2026-09-20 (the music chased to the speaker; the audio parity test and the conductor sound;
v0.9.0 and the scheduled ladder; a console and a PC in one match). Citations were inherited from the merged entries
rather than rewritten, so nothing verified was lost; the four new entries cite hashes and runs checked the same
night. (4) The site page rebuilt as a vertical timeline in the landing site's own tree, `../scotho/sites/s2u/story.html`,
built locally and not deployed.

## Status, 2026-09-20 (fourth pass): the D: archive reviewed

The owner asked whether `D:\socom_archive` had been used. It had not, beyond the spec naming it. Reviewed: 2.4 GB,
13,378 PNGs. It holds the twelve gate stamps archived on 2026-09-13 (`gate/first`, `native_default`, `famc`,
`mission2`/`3`, the `hostdraw_*`, `pf2_*` and `native_on_*` A/B sets), the pre-Sprint-4 run logs
(`logs/run_20260906_000315` to `run_20260909_144538`, gzipped), the first kill's acceptance bundle
(`acceptance/s5_ladder2`, with its own SHA256SUMS), and the Sprint 5 SDD reports. What the story took from it: one
picture, the last frame of the very first gate run, which is the save-to-card dialog the probe answered blindly (the
2026-09-11 entry), inventoried with the archive as its provenance. What it did not take: any contact sheet, and any
run whose readout also survives under `logs/`, which the witnesses already pin. The archive is not a citation target:
citations stay on paths a clone can reason about, and the archive's readouts are pinned through their surviving
`logs/parity/gate_<name>.out` files where one exists (spec 4.3, level 3).

The same pass, on the owner's instruction: every em dash in the prose replaced (commas, colons, full stops,
parentheses), the entry and era headings switched to a plain hyphen, the preface and closing rewritten in the author's
voice, and the foreword signed Scotho. Subject fragments on `Cited:` lines quote commits and keep their dashes.

## 2. Scope and shape

### 2.1 What the story is

A **linear, readable timeline** of one project, first commit to release, in date order, written for a player. Every
entry is a thing that changed on the screen or in a match. It is read start to finish, so length is a cost.

### 2.2 What the story is not — four boundaries, each with its owner

- **Not a changelog.** A changelog is complete, per-release and organised by component. This is selective, per-day and
  organised by what a person noticed. Release notes belong to Goal 0's release-draft workflow.
- **Not the development-process document.** How the project was built — the controller/subagent loop, sprints, specs
  and plans, TDD with a watched RED, the parity gate, numbered rulings, `docs/HUMAN_TASKS.md` — is **Goal 2**, which
  the Sprint 11 spec already scopes: *"A separate document on how it was built ... Linked from the README, not in
  it."* The story links to it and does not absorb it. §9 Q2 records the disagreement about where the line sits and
  the recommendation.
- **Not `docs/KNOWN.md`.** KNOWN is the standing list of what is proven, believed, retracted and hazardous, maintained
  after every task. The story is frozen prose about the past. Where the story states a fact about today, it states it
  by quoting KNOWN, and KNOWN wins.
- **Not `docs/STATUS.md`.** STATUS is a 2,399-line log, newest on top, of which only the "Current state" block is
  current (`docs/HANDOFF.md`). The story is the opposite artefact: short, oldest first, and nothing in it is a pointer
  to what to do next.

### 2.3 The entry format, fixed

One shape, used by every entry, so the page is scannable and so a script can both propose and verify one:

```markdown
### 2026-09-13 — The first kill

**Two copies of the game, on one PC, shot each other -- and the scoreboard agreed.**

For eleven days "online" had meant two programs sitting in the same lobby. On this day a driven match on
Frostfire ended the way a match is supposed to end: one player's health went to zero, the killfeed said so, and
two independent readers of the game's own memory agreed on who did it -- on three rounds in a row.

How: the health field is a float at `actor+0x1044` and the alive byte is `actor+0xF7A`; both scorers watch them.

But: it is one launch, two automated instances on one machine against a server on that same machine, on one map
with a hand-built route -- and round four of the same launch missed every shot.

Cited: `811b886`, `5f1de26`, run s5_t5_ladder2, docs/research/22-kill-readout.md
Picture: docs/story/img/2026-09-13-first-kill.png -- both screens, "socomc fragged socome with M4A1"
```

The parts, and the rule for each:

| Part | Rule |
|---|---|
| **Date** | `### YYYY-MM-DD` — the git author date of the entry's principal commit, `--date=short`. Ascending, no gaps filled, no invented dates. |
| **Title** | Four to eight words, plain English, no jargon. |
| **Hook** | One bold sentence, the thing a player enjoys. It is the only sentence permitted to be enthusiastic. |
| **Body** | Two to five sentences. What it was like before, what changed, why it mattered. |
| **How** | **At most one line**, prefixed `How:`. This is where an offset, an acronym or a mechanism is allowed to appear. Omitted whenever the entry survives without it — most do. |
| **But** | One sentence of qualification. **Mandatory on every entry the do-not-say table (§7.2) covers**; optional elsewhere. It is not a hedge bolted on: it is the sentence that keeps the story checkable. |
| **Cited** | One line, the machine-readable citations, in the grammar of §4.1. Every entry has at least one citation the test can verify with no `logs/` and no network. |
| **Picture** | Optional, at most one, only under §5's rules, always captioned with what it demonstrates. |

### 2.4 How many entries, and why that number

**Settled: 30 to 40 entries, hard cap 45.**

The two obvious rules are both wrong, and it is worth saying why rather than just picking a number:

- **One per commit is 742 entries.** Not a story; a `git log` with adjectives.
- **One per sprint is nine entries** (Sprints 1-9; Sprints 10-11 are not open) — and it loses the best material in
  the project. The 198 commits before Sprint 1 existed contain the first boot, the first main menu, the first OpenGL
  backend, the first mission, the first online lobby and the first online match, and they have **no sprint record at
  all**: no branch, no spec, no close-out. A per-sprint story starts on 2026-09-10 and a reader never learns how the
  game got on the screen. It also reproduces an artefact of the project's own bookkeeping — sprint numbers slid (what
  is now Sprint 10 was drafted as Sprint 9, with the same title), and goal numbers are not the order of work inside
  Sprint 9 (`docs/CURRENT_SPRINT.md`: *"Goal numbers are kept as they are in the spec, the commits and the plans; the
  P/Q labels are the order"*). A reader should not inherit our filing system.

The rule that produces the number: **an entry earns its place when a player could have watched it happen.** A menu
appearing, a mission loading, the first sound, a lobby, a kill, twenty maps, a launcher, a second operating system, a
server with a name. By that rule the landmark record is about 26 entries before anything from Sprints 9-11 is added,
and the release and its run-up add a handful. Thirty-five is also about two entries per working day at the dense end
of the project (2026-09-13 alone carries 138 commits) and one every few days at the sparse end, which reads as a pace
rather than a list.

The cap is a bar, not a target: the owner's own bar is *"reads it start to finish"*, and forty-five entries at five
sentences is already a twenty-minute read.

**Where entries are allowed to be thin:** a day with no visible change gets no entry. There is no obligation to cover
every sprint, and the story will say nothing at all about several days in the middle of Sprint 6. That is honest — the
work on those days was invisible by design.

---


**Recorded 2026-09-20, after the first draft was rendered and audited.** The draft came out at 52 entries against
the 30-40 settled above and the cap of 45. The overshoot is not padding: the adversarial verification pass found
twelve milestones the five era writers had missed — among them the day the gate was caught scoring the intro
cinematic, the lobby rate going from 6 in 10 to 10 in 10, the sound reports run to ground, and REPORT A BUG, the only
place a player can talk back — and the whole-document audit then judged that the 2026-09-12..14 era, eleven entries
in three days, "reads like a changelog with adjectives". Both are right. The cap was set before the coverage check
existed, and the coverage check should win over the cap; but the audit's cut is the later editorial pass's first job
(§1, and Phase C of the plan): merge the rand, movie-blocks and KNOWN-created entries into two, and fold "The test
stops grading the wrong screen" into "The check that had been passing for free", which tell one story. Target after
that pass: 45 or fewer, with nothing the verification pass added lost.

## 3. The sources and the script

The owner's requirement is the reason this section exists: *"Sources, read by a script and not by memory."* It is the
right requirement and this project has earned it — `docs/KNOWN.md` §3's closing note and the 2026-09-20 audit's HO-D
(*"static reading reported as fact"*) are both about claims made from recollection.

### 3.1 Where it lives

**`tools_py/story/`**, a new package beside `tools_py/parity/`:

```
tools_py/story/__init__.py
tools_py/story/collect.py     # reads the sources, proposes candidates. CLI: python -m tools_py.story.collect
tools_py/story/cite.py        # the citation grammar, resolver and verifier (pure core; imported by the test)
tools_py/story/remap.py       # D1: rewrite citation hashes through a filter-repo commit map (section 4.4)
tools_py/tests/test_story_collect.py
tools_py/tests/test_story_cite.py
tools_py/tests/test_story_guards.py
```

Constraints that come from the suite it joins, not from taste: tests live in `tools_py/tests/` and nowhere else, they
are `unittest` and must not import pytest, and no module-level `def test_` — all three are enforced by
`tools_py/tests/test_test_hygiene.py`, which exists because three pytest-style files in `tools_py/parity/` had never
executed at all (`docs/audits/2026-09-12-process-audit.md` item 2). The runner is one line of `build.sh`:
`python -m unittest discover -s tools_py/tests -t .`.

### 3.2 What it reads

1. **Git history.** `git log --date=short --format=...` over the release ref; `git log --diff-filter=A --name-only`
   for the first appearance of a file (a good, cheap signal: the day `tools_py/parity/gate.py` first appears is the
   day the gate existed). Merges are read but not proposed as entries on their own — there are exactly three merge
   commits in the whole history and only `d270022` and `b65fe46` are sprint merges, so "merged at" is a fact about
   Sprint 7 and about nothing else.
2. **`logs/parity/gate/*/summary.txt`** — the three-stage gate. One line per stage that ran, plus, on two of 148
   summaries, `EXE <path> bytes=<n> sha256=<hex>` (`tools_py/parity/gate.py`). The first clean 3/3 (`famb`,
   2026-09-11) is a candidate; so is the first gate scored on a release executable (`s9_g2_release_gate`).
3. **`logs/*.done` and `logs/parity/drive_*.txt`** — run outcomes. The `.done` vocabulary is fixed by
   `scripts/parity/ladder_frostfire.sh`: `KILL`, `NO-KILL`, `NO-DATA`, `NO-CONTROL`, `LOBBY-FAIL <class>`, `CRASH`,
   `PIN-FAIL`, `EXIT-<rc>`. The drive logs carry `RESULT ...` and `LADDER-SUMMARY ...` lines.
4. **`../socom_monitor`'s index — optional, and behind a flag.** `scan.Repo(root).runs()` and `run_detail(id)` give
   every run's kind, status and grouped screenshots without re-deriving any of it. It is genuinely useful and it is
   **not a dependency**: the monitor is a separate project outside this repository, a stranger's clone will not have
   it, and its own published snapshot is heavily partial (`out/site/data/build.json`: 563 runs, 1,666 images kept,
   **86,411 skipped**, and one error — `"run:vm: bad run id"`, because `vm` is in `scan.DENY_COMPONENTS`, so the
   entire Linux evidence set is unaddressable through it). So: `--monitor <path>`, absent by default, and the emitted
   candidates record `"monitor": "absent"` when it was not used. A source that changes the output must say whether it
   ran.

**What it must not read, ever:** `logs/parity/*/server-side.log` (account names, session tokens, client addresses —
withheld by `scan.is_withheld` for that reason, and cited by KNOWN only as a local path), `logs/bug_reports/` (another
session's, and report text is untrusted data), anything under `vm/keys/` or `server/config/*.json`. This is not
hypothetical caution: a tool whose job is to copy evidence into a published document is exactly the shape of tool
that publishes what it should not.

### 3.3 What it emits

Into **`logs/story/`** — inside the git-ignored `/logs/`, deliberately, because nothing the collector writes is a
publishable artefact:

- `logs/story/candidates.json` — the proposals. One object per candidate: `date`, `kind` (`commit` / `gate` / `run` /
  `first-file`), `signal` (why it was proposed, in words), `citations` (already in §4.1's grammar, already resolved),
  `witness` (§4.3), `pictures` (paths that exist, with sizes), and `notes` (anything the collector noticed and could
  not classify).
- `logs/story/timeline.draft.json` — the same set in the shape of §6's published data file, so the editorial pass
  edits rather than transcribes.
- `logs/story/shots/` — copies of the proposed screenshots, so a writer can look at forty candidate frames without
  walking 250 run directories. Copies, never moves; the collector opens `logs/` read-only apart from its own output
  directory.

### 3.4 What it deliberately does not do

**It proposes; the editorial pass chooses and writes.** This split is the Sprint 11 spec's own wording — *"The script
proposes the timeline's candidate entries ... the editorial pass chooses and writes"* — and it is preserved here as a
rule with teeth, not as a description:

- The collector **never writes under `docs/`**. It refuses an `--out` path that resolves inside `docs/`, and there is
  a test for the refusal. A generated `docs/STORY.md` would be a changelog with a template, which §2.2 rules out.
- It **never writes prose.** No titles, no hooks, no bodies. A `signal` field says *"first `summary.txt` with three
  PASS lines"*; it does not say *"the gate went green for the first time"*.
- It **never ranks importance** beyond the mechanical signals it can defend. It cannot know that the `vf0` fix
  mattered more than the day's other thirty commits.
- It **never copies an image into the tree.** Adding a picture to the repository is a decision under Goal 1's
  disc-derived table and the owner's line (§5), taken by a person, in a commit of its own.

### 3.5 Its tests

All RED first, each watched failing as an assertion rather than as an import error:

1. **Git reader, against a synthetic repository** built in a temp directory (three commits, one merge, one file
   addition): asserts subjects, short hashes, `--date=short` dates, that the merge is classified and not proposed, and
   that a file addition produces a `first-file` candidate. A synthetic repository, not this one, because a test pinned
   to this history fails on every commit.
2. **Gate summary parser, against fixture strings**, including three that have already bitten someone: a clean 3/3; a
   2/3; a summary with no `EXE` line (146 of 148 on this host); and — the important one — a **PASS line containing the
   substring `-> FAIL`**, which `s9_p1_gate`'s mission line really does (`CONSOLE spawn score=21.7 ... -> FAIL
   (s28_none.png ...)`, a print-only check under R78). A parser written with `grep FAIL` mislabels a clean 3/3 gate,
   and the test asserts that this one does not.
3. **Marker parser**, one case per word in the `.done` vocabulary, plus `EXIT-<rc>` with a number.
4. **Run-id syntax**, borrowed rather than reinvented: one plain path component, with `..`, absolute paths, drive
   letters, UNC paths and the denied components (`.git`, `vm`, `server`, `game`, `cards`) each refused by name.
5. **The monitor-absent path**: the collector runs with no `--monitor`, emits candidates, and records
   `"monitor": "absent"`. Then with a stub module, and records that it ran.
6. **Determinism**: two runs over identical inputs produce byte-identical `candidates.json`. A diff then means the
   record changed, which is the only reason a diff should ever appear.
7. **The refusal**: `--out docs/anything` exits non-zero having written nothing.

---

## 4. The citation test — the goal's teeth

The goal's own sentence is *"a test fails if an entry cites something that does not exist."* This section makes that
concrete, because a vague version of it is worth nothing: the project already ships citations that do not exist.

### 4.1 The grammar

Citations are parsed, not guessed, so a malformed citation is a failure rather than a silent skip. On the `Cited:`
line, comma-separated, each one of:

| Form | Example | Means |
|---|---|---|
| `` `<sha>` `` + subject fragment | `` `811b886` `` the ladder's second launch | a commit in this repository |
| `run <id>` | `run s5_t5_ladder2` | a directory under `logs/parity/` |
| `gate <stamp>` | `gate famb` | a directory under `logs/parity/gate/` |
| `<tracked path>` | `docs/research/22-kill-readout.md` | a path that `git ls-files` lists |

**Amended 2026-09-20, after the first document was rendered.** This table first said a citation was a bare hash
and nothing else. A bare hash list is unreadable to the audience the document is for -- a reader who is not going to
run `git show` learns nothing from `811b886` -- so each commit citation carries a few words of its subject, and the
separator is ` · ` rather than a comma, because commit subjects in this project contain commas. **The fragment is
not decoration: the test asserts it occurs in the commit's real subject** (`cite.check_citation`, kind
`fragment-mismatch`), which makes the readable half of the citation a second assertion and catches exactly the defect
the first verification pass found six times -- a hash that resolves, attached to a claim it does not support.

Anything else on that line is a parse failure. Prose may contain a link to the site, the monitor or an archive drive;
the `Cited:` line may not (§4.5).

### 4.2 Commits

`git cat-file -e <sha>^{commit}` — and three things beyond existence, because existence is the weakest of the checks
available:

- **Unambiguity.** `git rev-parse --verify` on the short form; an ambiguous abbreviation fails. The history is 742
  commits today and will be larger; seven characters will collide eventually.
- **The recorded subject and date match.** The data file stores the author date and the subject line beside the hash,
  and the test compares them with git. A hash that resolves to a *different* commit is precisely what a rewritten
  history produces, and existence alone would pass it.
- **Reachability from the published ref**, not merely presence in the object store. A commit on a deleted branch that
  happens to survive locally is not a citation a reader can follow.

**This check bites today, which is the argument for it.** `docs/STATUS.md` cites `841a6fc` (the VU1 register-file
build) and `60fe75c` (the first-boot flow to the main menu). Both were run against this repository while writing this
document:

```
$ git cat-file -e 841a6fc^{commit}
fatal: Not a valid object name 841a6fc^{commit}
$ git cat-file -e 60fe75c^{commit}
fatal: Not a valid object name 60fe75c^{commit}
```

They predate the move into the project's own repository (`4b0bbf9`, 2026-09-10) and nothing in the tree notices. The
story must not repeat them, and this test is what makes "must not" mechanical.

**Scope, stated so nobody widens it by accident:** the test reads `docs/STORY.md` and `docs/story/timeline.json` and
nothing else. Pointing it at `docs/STATUS.md` would red the suite on day one over two historical citations in a log
file that is explicitly not current. If those two are ever worth fixing, that is a STATUS hygiene task with its own
commit, not this test's business.

### 4.3 Run ids and gate stamps, and the fact that `logs/` is not in the repository

This is the part a naive design gets wrong. `/logs/` is git-ignored and `git ls-files logs` returns nothing: **on CI,
and on any clone but the owner's, there is no run to check.** A test that needs `logs/` therefore has two bad options
— fail everywhere, or skip. Skipping is worse than it looks: the 2026-09-20 audit's SV-3 records that the Python skip
count is never checked and that two gate-scorer tests have skipped on every run since their artefacts went. A skip is
how a test stops existing without anyone deciding that it should.

**The design: every run citation carries a frozen witness, in the tree.** For each `run`/`gate` citation the data file
holds:

```json
{"kind": "run", "id": "s5_t5_ladder2", "witness": {
   "source": "logs/s5_t5_ladder2.done",
   "text": "done 0 mpexit=0 KILL harness=171290b5524e... sha256=234b4772cd0a8bf8...",
   "bytes": 96,
   "sha256": "<sha256 of that file>",
   "captured": "2026-09-19",
   "archived": false }}
```

Then the test has three levels and never has a fourth called "skipped":

1. **Always, in any clone, with no `logs/` and no network:** the witness exists, is well formed, its `source` is a
   path under `logs/`, and **the entry's claim words appear in the witness text** — an entry that says a kill happened
   cites a witness containing `KILL`; an entry that says a gate passed cites a witness with three `PASS` lines. This
   is the check that runs in CI, and it is the one that catches the common failure, which is not a missing file but a
   sentence that has drifted away from its evidence.
2. **When `logs/` is present** (the owner's machine, and the release build): re-read `source`, compare size and
   sha256, fail on a mismatch. A changed artefact under a citation is a louder problem than a missing one.
3. **When `logs/` is present and the file is gone:** fail — *unless* the witness says `"archived": true` with an
   archive note. That case is real: `logs/ARCHIVED_TO_D.txt` records twelve cited gate stamps moved to
   `D:\socom_archive` on 2026-09-13, several of which keep a surviving readout at `logs/parity/gate_<name>.out`. An
   archived witness must still carry its frozen `text`, and the surviving readout is the preferred `source` where
   there is one.

**What it costs.** The witness is a copy of evidence, and a copy can be wrong in a way the original is not. Two
mitigations, both cheap: the collector writes witnesses (a person never types one), and the level-2 sha256 comparison
re-proves every witness on the one machine that can. What it buys is a citation that means something to a stranger who
will never have `logs/` — which is the whole point of publishing the story.

### 4.4 What happens when D1 rewrites history and every hash changes

The Sprint 11 spec is explicit that this is live: Goal 1.3a records that a personal literal is still in history
in two commits, so *"D1 cannot be 'as it is': either a targeted `git filter-repo --replace-text` with an
owner-approved force-push, or a fresh history"*, and Goal 1.4 adds: *"The progress story (Goal 6) cites commits by
hash; a fresh-history public repository keeps those citations true only if the story links to the archive or quotes
instead of linking. Say which before writing the story."* This section is that answer.

**What actually happens, mechanically.** `git filter-repo --replace-text` rewrites every commit from the first
affected commit forward. The literal landed in a Sprint 8 plan and was redacted in the tree, but the rewrite is not
local to those two commits: every descendant is re-parented and re-hashed, so in practice **every hash in the story
changes**. A fresh-import public repository is worse and simpler: there is one commit, and every citation is dangling.
In both cases the citation test goes red. **That is the test working.** The design goal is not to avoid the red; it is
to make clearing it mechanical instead of editorial.

Four decisions make it mechanical:

1. **No hash appears in the prose.** `docs/STORY.md`'s `Cited:` line carries the hash; the prose carries none. (The
   `How:` line may quote a commit *subject* — words, which survive any rewrite.) A rewrite therefore edits one list
   per entry, in one file plus the data file, and never a sentence.
2. **Every commit citation stores what survives a rewrite.** Author date and subject line, in the data file, beside
   the hash. `git patch-id` is recorded too and is useful for a message-only rewrite, but it is not the key: a
   `--replace-text` rewrite changes content, so patch-ids move for the affected files.
3. **`tools_py/story/remap.py`.** `git filter-repo` writes `.git/filter-repo/commit-map` (old sha, new sha, one pair
   per line). `remap.py --map <file> --timeline docs/story/timeline.json` rewrites every hash through it, refreshes
   the stored subjects and dates from the new history, and prints what it could not resolve. Where there is no map — a
   fresh import — it falls back to a lookup by `(author date, subject)` in the new history, and **anything that is not
   a unique match is printed for a person to settle, never guessed.** One test per path: a mapped rewrite, an unmapped
   rewrite with unique subjects, and an unmapped rewrite with a duplicate subject that must be reported and not
   auto-resolved.
4. **If D1 chooses a fresh public repository with this one kept private** — the case where no remap can help, because
   the commits genuinely are not there — the recommendation is: **keep the hashes, say once what they are, and quote
   the subject inline.** The story's header carries one sentence: *"Commits are cited by their hash in the project's
   development repository, which is private; each citation carries its date and its subject so the claim reads without
   it."* Then `docs/story/commits.json` — the date/subject/sha witness, tracked in the public repository — becomes the <!-- docmaint: future -->
   citation of record, and the test verifies the story against *it* rather than against `git`, with the git check
   enabled by a flag that the owner's machine sets. **The alternative — dropping hashes — is rejected**: it makes the
   story uncheckable, and checkable is the one property the owner asked for by name. It costs a reader the ability to
   run `git show`, and that cost belongs in the story's header rather than hidden.

**Ordering consequence, stated plainly:** the story's *text* can be written before D1 is answered; the citation
*format* cannot be frozen until it is. This draft is the text. Whoever closes the goal answers D1 first, or writes
into a format that will change.

### 4.5 A citation to something outside the repository

Refused as a citation; permitted as a link in prose, if the entry also carries an in-repo citation.

The rule is one sentence: **a citation is a promise the reader can check.** `../socom_monitor` is another project on
the owner's machine; `D:\socom_archive` is a drive nobody else has; `https://s2u.scotho.com` can change without a
commit; a forum thread can vanish. None of those can be verified by a test in this suite, and a citation the test
cannot verify is decoration. So:

- The grammar refuses them on the `Cited:` line (parse failure, not a warning).
- The test asserts **every entry has at least one citation verifiable with no `logs/` and no network** — in practice a
  commit or a tracked path. This is the strongest single line in the test and the cheapest to enforce.
- An external link in prose is fine and is sometimes the honest thing (the monitor's run pages, the community work
  this project stands on). It is a link, and the story says so.

### 4.6 Where it runs

In the Python suite, `python -m unittest discover -s tools_py/tests -t .`, which `./build.sh test` runs first and
which CI runs on ubuntu-24.04. The baseline in `docs/CURRENT_SPRINT.md` is **Python 1368 OK**; this goal adds to it.

Two properties the suite demands and this test must have: it must not import pytest and must not define a module-level
`def test_` (`test_test_hygiene.py` fails the suite on either), and it must **not** be one of the tests that quietly
skips. When `docs/STORY.md` does not exist yet, the test asserts that the data file does not exist either, and passes
— that is a real assertion about a consistent state, not an abstention.

---

## 5. The picture policy

### 5.1 The fact that reframes the question

**Every picture the record points at lives under `/logs/`, which is git-ignored and has never held a tracked file**
(`git ls-files logs` → 0). The repository contains exactly **eight** files under `docs/research/assets/`:

```
18-s0-evidence.png   22-first-kill.png   22-first-kill-evidence.txt
31-console-dump-cpu-replay.png   31-console-dump-gl-replay-before.png
31-console-dump-gl-replay-fixed.png   31-console-water-texture-ct16.png
launcher-first-cut.png
```

So "one picture per milestone where a run captured one" is not a decision to *link* pictures — it is a decision to
**add files to a repository that Goal 1 is trying to make clean and clonable**. That should be said out loud before
anyone picks favourites.

### 5.2 Which milestones actually have a picture

Checked against the filesystem on this host:

**Have one:**

| Milestone | Artefact |
|---|---|
| First boot to the main menu (2026-09-05) | `logs/host/host_*.png` — 18 frames. **Cited by no document**, so an entry using it must say what it is rather than inherit a claim |
| First scored side-by-side against the console (2026-09-07) | `logs/parity/ours_a_sheet.png` + `logs/parity/golden_sheet.png` — a real A/B, 717 KB and 711 KB |
| Menu roller and textured mission (2026-09-07) | `logs/parity/ours_e_sheet.png` |
| First in-mission frames (2026-09-07) | `logs/parity/mission_merge/host_*.png` — uncited |
| First lobby, on the reference emulator (2026-09-07) | `logs/parity/online/login/01_universe.png` .. `07_save_card.png` |
| First online match, reference (2026-09-07) | `logs/parity/online/match/montageAB2.png` |
| Our own exe logs in, hosts, and plays (2026-09-08) | `logs/parity/ours_login/`, `ours_host/`, `ours_match/` |
| First online gameplay on the VU1 build (2026-09-10) | `logs/parity/match_play5_sheet.png` |
| First passing three-stage gate (2026-09-11) | `logs/parity/gate/famb/{title,transition,mission}_sheet.png` |
| **First kill (2026-09-13)** | **`docs/research/assets/22-first-kill.png` — already tracked**; both screens, reads "socomc fragged socome with M4A1 / SEALS VICTORIOUS!" |
| The twenty-map sweep (2026-09-17) | 20 × ~48 frames, **no contact sheet** — a writer must pick one (`A_14b_map_<slug>.png` is the map-selection proof, `A_final.png` the round end) |
| Hosted round and hosted kill (2026-09-19) | `logs/parity/s8_hosted_control2/`, `logs/parity/s8_hosted_kill/A_kill_r*.png` |
| Linux (2026-09-18) | `logs/parity/vm/launcher_*.png` — and the monitor **cannot serve these**: `vm` is a denied component, which is the single error in its snapshot |
| The launcher (2026-09-17 onward) | `docs/research/assets/launcher-first-cut.png` — tracked — and `logs/launcher_shots_goal8/` |
| The water and terrain work | `docs/research/assets/31-console-dump-gl-replay-{before,fixed}.png` — tracked, and a genuine before/after |

**Have none:**

- **The first single-player mission loads and runs (2026-09-06).** Nothing. The evidence is a STATUS narrative and
  four commits. This is a milestone the owner's own list names, and it will have to be a picture-less entry.
- **The first gate attempt** (`first`, 2/3, 2026-09-10) — archived; only `logs/parity/gate_first.out` survives.
- The twelve archived gate stamps — text readouts only.
- Every pre-Sprint-7 landmark **inside the monitor's published snapshot**: 78 of 563 runs have an image there and none
  is older than Sprint 7. The PNGs are on disk; the snapshot is not a way to show them.

### 5.3 The recommendation

The line is the owner's — the Sprint 11 spec says so — and this is the controller's recommendation, with its cost:

1. **A small, fixed set: at most twelve pictures**, listed one per row in a `docs/story/PICTURES.md` inventory that is
   also a row in Goal 1's disc-derived decision table. Twelve, because the story is 30-40 entries and a picture every
   third entry reads as illustration, where forty reads as an asset dump.
2. **Every picture is a frame our own program produced**, at the resolution the game runs, uncropped except to remove
   a desktop. No texture, model, audio file or any asset lifted out of the disc — that is a different act, and Goal 1
   already has a row for `tests/fixtures/**`.
3. **Prefer before/after pairs.** They are the best illustration of our own output, because the *defect* is ours: the
   intro-movie macroblocks, the grey water shards, the CLUT-serial explosion that stopped every online round. A frame
   of a broken render is unambiguously a picture of our program's behaviour.
4. **Precedent, not a new step:** `docs/research/assets/22-first-kill.png` and the four `31-*` frames are tracked
   already and have been since Sprints 5-6. Publishing the repository publishes them. The story adding a handful more
   of the same kind is a change of degree — the owner should still be told the number.
5. **Against: contact sheets.** They are the easy choice and the wrong one — `s9_p1_gate/mission_sheet.png` is
   **12.1 MB** and `transition_sheet.png` is 14.2 MB, and twenty-three frames at once looks like a dump rather than an
   illustration. A single chosen frame is both smaller and better.
6. **Never from a run whose directory holds `server-side.log`** without inspecting the frame itself: those runs are
   withheld from the monitor because the *logs* carry account names and tokens, and a lobby screenshot can carry a
   persona name too.

**The cost, stated beside the benefit:** twelve frames is roughly 3-10 MB added to a repository whose front page is
supposed to invite a clone; each is a permanent row in the licence and accreditation inventory (Goal 5) and in the
disc-derived table (Goal 1); and D2 — the legal question about the executable as well as the assets — bears on all of
them. The benefit is that a timeline about a renderer with no rendered frames in it asks the reader to take the whole
story on trust, which is the opposite of this goal.

**Who decides:** the owner. §9 Q1 states the question in the form it needs answering.

---

## 6. Delivery

### 6.1 In this repository

- **`docs/STORY.md`** — the prose, linked from the README. The README link is Goal 2's rewrite (which also moves the
  agent-facing material out), so the link lands in that goal's commit, and this goal's bar records that it must.
- **`docs/story/timeline.json`** — the machine-readable twin, tracked. The test asserts that the two agree in both
  directions: every entry in the prose is in the data and vice versa, with matching dates and citations. Two artefacts
  that can drift are a defect generator; one test removes the class.
- **`docs/story/PICTURES.md`** — the inventory of §5.3, one row per published image.
- **`docs/story/commits.json`** — only if D1 lands on a fresh public history (§4.4.4). <!-- docmaint: future -->

The data file's shape, version 1:

```json
{"schema": 1,
 "generated": "2026-09-19",
 "clock": "git author dates, --date=short; see docs/HANDOFF.md section 3 on the one-day document skew",
 "repo": {"head": "<sha>", "commits": 742},
 "entries": [
   {"id": "2026-09-13-first-kill",
    "date": "2026-09-13",
    "title": "The first kill",
    "hook": "...",
    "qualification": "...",
    "citations": [
      {"kind": "commit", "sha": "811b886",
       "subject": "docs: THE ACCEPTANCE TEST PASSED -- ...", "author_date": "2026-09-13"},
      {"kind": "run", "id": "s5_t5_ladder2", "witness": {"...": "..."}},
      {"kind": "path", "path": "docs/research/22-kill-readout.md"}],
    "picture": {"path": "docs/story/img/2026-09-13-first-kill.png", "caption": "..."}}
 ]}
```

`schema` is there because §4.4 says the citation form changes when D1 is answered; a consumer needs to be able to
refuse a shape it does not know.

### 6.2 On the landing site — a request, not an edit

Goal 3 revises `../scotho` `sites/s2u`. **That tree belongs to the hosted-server session and this controller does not
edit it.** The precedent is Sprint 8's Goals 12 and 13 and Sprint 10's Goal 2: the requirement is written here, the
other session does the work, and the two agree the contract in a spec section.

**What the site needs from us** (proposed contract, for that session to accept, amend or refuse):

1. `docs/story/timeline.json` — the whole timeline as data, so **the site does not re-derive it**. The site has no
   access to `logs/`, should not run `git log`, and must not become a second implementation of §3's collector that
   drifts from the first. One producer, one artefact.
2. `docs/STORY.md` — the prose, if the site prefers to render markdown rather than build from the JSON. Both are
   published; the JSON is authoritative for dates, ids and citations.
3. The picture files at a stable published path (`docs/story/img/`), each named by its entry id and each referenced
   from the JSON's `picture.path`. No image the JSON does not name.
4. A stated cadence: these files change when the story changes, which is rarely. No polling and no build-time fetch
   from this repository — the site takes a copy at deploy.

**What we ask back, in one line:** a stable per-entry URL shape (`/story#<entry id>`), so `docs/STORY.md` and the page
can cross-link and so a bug report or a forum post can point at one moment.

**What neither side ships:** anything derived from `logs/` that is not already in `docs/story/`. The site never reads
this repository's run directories.

---

## 7. The honesty constraint

### 7.1 The rule

**The story is checkable, so it must not repeat a retracted claim, and each big win carries its qualification.**
Written as a rule an editor can apply:

> Before an entry is written, its claim is looked up in `docs/KNOWN.md` §3 (retracted) and §1 (proven, *with the
> artefact*). If the claim is in §3, the entry is about the retraction, not the claim. If it is in §1, the entry
> quotes the artefact's own limits in its `But:` line. If it is in neither, the entry cites the commit and says only
> what that commit's diff supports.

Three supporting rules, each from something that has already gone wrong here:

- **Every number carries its conditions.** "Two instances, one PC, one NAT, one map" is not a footnote; it is part of
  the number. KNOWN §4, and `a1e168b`, whose commit title is *"I broke my own rule"*: *"A false sentence reads as a
  claim someone could challenge; a number carries no visible sign of being stale."*
- **Striking a headline is not enough.** `95ecb21`: *"Striking a claim's headline and leaving its consequences
  standing is the more dangerous half."* If an entry drops a claim, it drops the sentences that rested on it.
- **A retraction is a good entry, not an embarrassment.** The best single item in the record is the grey-water
  retraction: a theory with *"Against: none found"* written under it, killed by one disconfirming run and retracted
  **seven minutes later** (the 2026-09-20 audit calls it the best case on record). A story that contains only wins is
  both less true and less fun than one that contains that.

### 7.2 The do-not-say table — its home is here

This table is part of this spec, and `docs/STORY.md`'s own header links to it. It is not copied into the story (a
second copy drifts) and it is not left in a survey nobody re-reads. Its authority is `docs/KNOWN.md`; where KNOWN and
this table disagree, KNOWN wins and this table is what gets fixed.

| Do not write | What the record supports |
|---|---|
| "SOCOM II runs on PC" | It runs from the player's own NTSC SCUS-97275 **r0001** disc. A non-r0001 image exits 67 (R130). No game data ships. The r0004 revision the community server runs would need a second, separate recompilation that does not exist. |
| "It runs at 60 fps" | The measured numbers are 43-45 fps in one fixed Frostfire control round; 58-60 presents/s on the *login screen* under four spinning cores; 0.8-2.9 fps in the VM on software GL. There is no steady-state gameplay figure on a clean host, and KNOWN §4 says gates are host-load sensitive. |
| "Every map works online" | Twenty previously-untested maps ran a **scripted no-kill control round**, two instances on one PC against a local server, on 2026-09-17 — two days before the hosted box existed. `docs/research/33-online-map-coverage.md`'s own headline is **18 of 20**; one straggler passed only after a fall-damage guard was added to the harness. Only Frostfire has a kill route. |
| "Two strangers can play each other" | **No human pair has ever played.** Every online result is two driven instances on the owner's PC. The two-machine match is `docs/audits/2026-09-17-audit-and-code-review.md` G5, open since Sprint 7. |
| "A round has been played on the hosted server" (unqualified) | True — `s8_hosted_control2`, `s8_hosted_kill` — with both instances **behind one home NAT on one machine**. KNOWN's own row ends *"Still unexercised: two DIFFERENT networks."* |
| "The kill is repeatable" | `s6_ladder8` was 4/4 on KillWatch and **KILL, KILL, NO-KILL unattributed, NO-DATA** on the second scorer. The plan's two-scorer bar is recorded as **not met**. On the hosted server it was 2 kills in 4 rounds. |
| "The music is fixed" | Three fixes landed under watched RED tests (R169-R171, `eca5450`) and are **measured INERT in the only mission driven**: 55 stream requests, 55 played, 0 refused, 0 queued, 0 replaced. The owner's verdict on the previous round of fixes was *"no"*. **No ear has confirmed the current build.** |
| "The audio is sample-exact" | True of the *decode* against the disc (the title loop correlates 1.000). There is **no correlation number for mission audio**. |
| "Voice chat works" | No pad button talks — all sixteen bits, both talk routes, four peek rounds. The expected result of speaking into a lobby is written in `docs/HUMAN_TASKS.md` (since 2026-09-25 `docs/archive/HUMAN_TASKS-to-2026-09-25.md`): *"the other side hears NOTHING."* |
| "The Linux client is done" | It builds, boots, matches Windows' boot frame to 0.008 grey levels and passes the title stage at Windows' 19/23 — **inside a VirtualBox VM on a software rasteriser**. No real Linux machine or GPU has run it; R107b defers the audio bar to one. |
| "A stranger can install and play" | No stranger has. The first build cut for a person, `playtest-1` (2026-09-20), was played by the OWNER and failed at step 6 of fourteen on the mission music; `docs/PLAYTEST.md` is stamped from that run. A stranger, a clean machine and a second network remain unexercised. |
| "The gate proves it's correct" | KNOWN §4: *"The gate proves regression only."* It was blind to the 15-bit `rand`, the skeleton decay and the soft-double chain; the grey water sat in every gameplay gate frame for three sprints and passed every time. A deliberately pillarboxed run passes the title gate **with margin**. |
| "672 C++ and 1368 Python tests pass" (as evidence of correctness) | True as a count. The 2026-09-20 audit lists **five ways the C++ runner exits 0 while broken**, and **148 of 150 gate summaries carry no exe hash** — *"'Gate 3/3' can be a statement about yesterday's exe."* |
| "Frozen at round start" / "the ghost flag" / "depth quantisation causes the shards" / "2x sharpens the HUD" / "`+0x204` is health" | All **retracted**, KNOWN §3. If they appear at all, they appear as the story of being wrong. |
| "the kill1 / kill2 / kill3 runs" | `ours_task8_kill1/2/3` contain **no kills** — the bursts hit nothing because the players were never within range in three dimensions. The first kill is `s5_t5_ladder2`. |
| "the Horizon server" as SOCOM's original service | It is a community server emulator this project self-hosts. **Nothing has ever connected to PSRewired**, and nothing will until the owner reports their answer. |
| Any celebration of the honesty culture that omits its own failures | The project's rule is *retract on discovery*; the first three retractions happened at close-out anyway, about a day late, and the freeze description stayed false for roughly two weeks. The 2026-09-20 audit's verdict: *"What is weak is that every guard is a sentence."* |

### 7.3 The one mechanical guard that is possible

Prose cannot be tested. One narrow thing can: **a literal-phrase check.** `tools_py/story/cite.py` also reads
`docs/STORY.md` for a short list of retracted phrasings drawn from KNOWN §3 (`frozen at round start`, `ghost flag`,
`depth quantisation`, `sharpen the HUD`, `+0x204`, and `kill1`/`kill2`/`kill3` used as kills) and fails on a hit; and
for a jargon list (`GS`, `IOP`, `VU1`, `DMAC`, `VIF`, `GIF`, `CLUT`, `XGKICK`, `sceMpeg`, `FMAC`, `SPU`, `DMAtag`)
appearing outside a `How:` line or a citation — which is the mechanical half of the owner's *"a stranger can tell what
happened ... without knowing what a GS or an IOP is"*.

**Its limits, said before anyone over-trusts it:** it catches phrasings we already know about and cannot catch a new
false claim; the jargon check measures *placement*, not clarity — an entry can be incomprehensible with no banned word
in it. It exists because the 2026-09-20 audit's verdict on this project is that *"every guard is a sentence"*, and
because a negative control is cheap: the guard's own tests plant one banned phrase and one stray acronym and assert
each is caught, exactly as Goal 9 plants a secret of each class. It does not replace the read.

---

## 8. The bar

The owner's bar, and what makes each part checkable:

| The bar | How it is met | Who says so |
|---|---|---|
| "The owner reads it start to finish and it is fun" | Nothing mechanical touches this. The length cap (§2.4) and the one-hook-per-entry rule serve it; neither proves it. | **The owner.** The controller's position is that this is the real bar and the other two are hygiene — and that the closing pass must not report the mechanical two as though they satisfied the first. |
| "A stranger can tell what happened and in what order without knowing what a GS or an IOP is" | Strict date order with no forward references; the jargon check (§7.3) as the mechanical floor; a read by someone who has not worked on the project as the rest. | A person, with the check as a floor. |
| "Every dated claim carries a citation that the test proves exists" | §4, in the Python suite: the grammar, the commit checks, the three witness levels, and the at-least-one-verifiable-anywhere rule. Green in CI with no `logs/` and no network. | The suite. |

Two additions this design makes to the owner's bar, because they follow from it:

- **The story and the data file agree**, asserted in both directions (§6.1).
- **Every entry the do-not-say table covers carries a `But:` line**, and the review that closes the goal walks the
  table row by row. This one is a sentence-guard, and it is recorded as such rather than dressed up as a test.

---

## 9. The open questions that are the owner's

Listed here rather than buried, each with the controller's recommendation and what it costs. None of them blocks the
draft; all four block the close.

### Q1 — the picture line

**The question.** How many pictures of the running game may the public repository and the landing page carry, and of
what kind? The Sprint 11 spec reserves this to the owner: *"checked against Goal 1's rule that no disc-derived asset
ships beyond what fair illustration of our own output needs — the owner decides that line."*

**Recommendation:** at most twelve; all frames our own renderer produced; prefer before/after pairs; no extracted
assets; one inventory row each in `docs/story/PICTURES.md` and in Goal 1's decision table (§5.3). **Cost:** 3-10 MB in
the tree, a permanent row per image in two inventories, and D2's legal question applies to each. **If the owner says
zero**, the story still works — it loses its best illustrations and gains nothing, but that should be a choice rather
than a default.

### Q2 — is the development record part of the story, or of Goal 2?

**The question.** The agentic loop — controller and subagents, specs and plans, TDD with a watched RED, the parity
gate, 176 numbered rulings, three self-audits — is unusual, and is arguably the most interesting thing about the
project. Goal 2 already owns it (*"A separate document on how it was built"*), and D4 asks separately what of
`docs/dev/` is published at all.

**Recommendation: the loop is Goal 2's document; the story carries at most three process entries, and only where a
process event changed the game in a way a reader can see.** The candidates: the day the parity harness was invented
and the console became the grader (2026-09-07) — without it the rest of the timeline has no yardstick; the 2026-09-14
pause, when the owner stopped the work over two defects they had spotted in gate frames; and the CLUT-serial
regression (2026-09-16, `docs/research/34-online-round-freeze-clut-serials.md`), where the project broke its own
online play and found it by bisecting over four of its own launches. Each links to Goal 2's document for the
machinery. **Why not more:** a story that keeps stepping out to admire its own process stops being a story a player
enjoys, which is the bar. **What it costs:** the single most distinctive thing about this project gets one page of its
own instead of being woven through, and a reader who skips the link misses it.

### Q3 — how citations survive D1

**The question.** Does the public repository carry this history (rewritten), or start fresh with this one kept private
as the archive? §4.4 is the design either way; the owner's answer decides which half runs.

**Recommendation:** decide D1 on Goal 1's audit numbers first, as the Sprint 11 spec already says. For the story
specifically, **keep hashes in both cases**: run `remap.py` for a rewrite, and for a fresh import add the one header
sentence plus `docs/story/commits.json` as the citation of record. **Cost of the fresh-import case:** a reader cannot <!-- docmaint: future -->
`git show` a citation, and the date and subject beside it are what they get instead. **Rejected:** dropping hashes,
which trades the goal's one hard property for tidiness.

### Q4 — does the story name the owner, and the models that did the work?

**The question.** Two different questions that are usually asked as one.

**The owner.** Recommendation: **by role — "the owner" — unless they say otherwise.** Their name and e-mail are in 742
commits' metadata, and Goal 9 makes publishing that metadata a *deliberate* decision rather than a default (*"A
private repository's `user.email` is often a personal one; the public one should be deliberate"*). A story that names
them in prose pre-empts a decision Goal 9 is explicitly keeping open. **Cost:** it reads a little distant, and it is
their project; if they want their name on it, that is a one-line change and the right one.

**The models.** Recommendation: **one line in the story's header and one paragraph in Goal 2's document — and no
per-entry attribution.** The reason is evidence, not modesty: the 2026-09-20 audit's HO-I counted the trailers across
the history — **415 `Claude Fable 5.1`, 226 `Claude Opus 5`, 6 `Claude Opus 4.8`** (a model no session here ever ran,
mandated by an old HANDOFF), **71 with none** (from before the rule existed), and 239 carrying a `Claude-Session:`
line that a 2026-09-13 rule forbade. Per-entry model attribution would therefore be wrong in at least six places and
absent in seventy-one, and the story would be asserting something the record cannot support — the exact failure mode
this whole document is built to avoid. **What the header can say and defend:** that the work was done by an autonomous
agent loop under the owner's direction, that the commit trailers name which models, and that Goal 2's document
explains the arrangement. **Cost:** a reader curious about which model did what is sent to `git log` and to a caveat
about six wrong trailers — which is the truth.

---


**How the first draft resolved this, pending the owner's answer (2026-09-20):** the preface names "the owner" as a
role, not by name, and says in one sentence that most of the building was done by AI agents in a loop the owner
steers. No model is named. The whole-document audit found that three entries already assumed the reader knew about
"agents" and "the loop" without ever having been told, so saying it once, plainly, was better than the accidental
alternative. The owner can overturn this in either direction — name the people and models, or take the sentence out.

## 10. Implementation plan

In the style of `docs/superpowers/plans/`: ordered tasks, each small enough to be one commit, **RED first for anything
with code in it** — the RED watched failing as an assertion, not as a compile error or an import error.

**Scope:** `tools_py/story/`, `tools_py/tests/test_story_*.py`, `docs/STORY.md`, `docs/story/`. No runtime change, so
**no gate is owed**; `./build.sh test` and CI are the bar. **Do not touch:** `docs/CURRENT_SPRINT.md` (the sprint
controller's), `server/` and `../scotho` (the hosted-server session's), `docs/KNOWN.md` beyond a row this goal
actually settles.

### Phase A — the test before the story (all of it can run before a word is written)

- [ ] **Task 1 — the citation grammar and the resolver's pure half.** RED: `test_story_cite.py` asserts the grammar
      parses the four forms, refuses a URL, refuses `D:\...`, refuses a two-component run id, and refuses an entry
      whose `Cited:` line is empty. GREEN: `tools_py/story/cite.py`, pure — no git, no filesystem. One commit.
- [ ] **Task 2 — commit citations against git.** RED: a synthetic repository in a temp directory; cases for a valid
      hash, a hash that does not exist, an ambiguous abbreviation, and a hash whose stored subject disagrees with
      git's. GREEN: the git checks in `cite.py`. One commit.
- [ ] **Task 3 — run and gate citations, the witness, and the three levels.** RED: a fixture `logs/` in a temp
      directory; cases for witness-only (no `logs/`), witness plus matching file, witness plus **mismatched sha256**,
      missing file without `archived`, missing file with `archived` and surviving text, and a claim word absent from
      its witness. Plus one case asserting that **no path through the test skips**. GREEN. One commit.
- [ ] **Task 4 — the story/data agreement and the at-least-one-verifiable rule.** RED: an entry present in the prose
      and absent from the JSON; the reverse; dates that disagree; an entry whose only citation is a run id. GREEN.
      One commit.
- [ ] **Task 5 — the guards (§7.3), with their negative controls.** RED: a planted retracted phrase and a planted
      stray acronym outside a `How:` line, each asserted caught; plus a case proving the acronym is allowed inside a
      `How:` line and inside a citation. GREEN. One commit.
- [ ] **Task 6 — the empty-state case.** RED: with no `docs/STORY.md` and no `docs/story/timeline.json` the test
      passes by asserting both are absent; with one present and the other missing it **fails**. GREEN. One commit.
      This is what lets Phase A land before Phase C and still mean something.

### Phase B — the collector

- [ ] **Task 7 — the git reader.** RED: synthetic repository; subjects, short hashes, `--date=short` dates, the merge
      classified and not proposed, `first-file` candidates. GREEN: `collect.py`'s git source. One commit.
- [ ] **Task 8 — the gate and marker readers.** RED: fixture strings — a 3/3, a 2/3, no `EXE` line, and the
      **`-> FAIL` inside a PASS line**; one case per `.done` outcome word. GREEN. One commit.
- [ ] **Task 9 — the optional monitor source, determinism, and the refusal to write under `docs/`.** RED: four cases
      — `"monitor": "absent"` with no flag, a stub module recorded as present, byte-identical output over two runs,
      and `--out docs/x` exiting non-zero having written nothing. GREEN. One commit.
- [ ] **Task 10 — `remap.py` (D1).** RED: a mapped rewrite resolves; an unmapped rewrite with unique subjects
      resolves by `(date, subject)`; an unmapped rewrite with a **duplicate subject is reported and not guessed**.
      GREEN. One commit. Written now, run in Phase D.

### Phase C — the editorial pass (prose; no RED, but the suite must stay green)

- [ ] **Task 11 — run the collector on this machine and read its output.** Nothing from `logs/story/` is committed;
      the commit, if any, is the corrections this spec needs.
- [ ] **Task 12 — `docs/STORY.md` and `docs/story/timeline.json`, entries up to the last merged commit.** One commit,
      and the first time the citation test runs on real data. Every entry the §7.2 table covers carries its `But:`
      line.
- [ ] **Task 13 — `docs/story/PICTURES.md`, the inventory, with no images added yet.** One commit. It is a proposal
      to the owner (Q1) and a row in Goal 1's table.
- [ ] **Task 14 — the README link** (lands with Goal 2's README rewrite, not before it) **and the site contract**
      (§6.2) relayed to the hosted-server session as a request. One commit here, one message there.

### Phase D — the close, at the release (the four things §1 named)

- [ ] **Task 15 — D1 reconciliation.** The answer known; `remap.py` run or the fresh-history header adopted; the test
      green against the published history. One commit.
- [ ] **Task 16 — the pictures**, once the owner has drawn the line: the images added, the inventory filled, the
      captions written. One commit, or one per image if the owner wants them approved individually.
- [ ] **Task 17 — the release entry.** The tag, the archives, `SHA256SUMS`, the repository public. One commit.
- [ ] **Task 18 — the site page** goes up through the hosted-server session, from the JSON and the markdown.
- [ ] **Task 19 — close-out.** The §7.2 table walked row by row against the finished text; a KNOWN row if anything
      was settled; `./build.sh test` green; the owner reads it.

### Close

`./build.sh test` exit 0 with the new Python tests green; CI green; no gate owed. Then the Sprint 11 spec's Goal 6
bullet gains a pointer to this document and the date it was written, and `docs/CURRENT_SPRINT.md`'s Sprint 11 block is
the sprint controller's to update — **not this document's author's**.
