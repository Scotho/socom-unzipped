# Sprint 14 design — "guards, not sentences": the rules become mechanisms, the record becomes small

Date: 2026-09-26 (host clock), proposed while Sprint 13 is open (Task 99, the close, not started). Written by the
reviewing session on the owner's instruction of the same night ("propose that sprint here and now as sprint 14"),
from `docs/audits/2026-09-26-autonomy-structure-review.md` (nine findings, options A–I, the six evidence notes
beside it). The plan is `docs/superpowers/plans/2026-09-26-sprint-14.md`. **Opened 2026-09-26 05:17Z** on `sprint-14` off
`main` at `6a82caaa` (the Sprint 13 merge, `v0.13.0`); the defaults of §3 are rulings R269–R277. Revised the same day
for local running:
cloud sessions are unavailable from 2026-09-26, so every task runs on the owner's machine, and the research handoff
that was to run in the cloud ("borrowed confidence") becomes Sprint 15 (§1.5, decisions D8 and D9, the filler X1).

## Why this is a sprint and not a task

Four weeks of the loop have produced a port that plays and a record that does not fit in a head: about one megabyte
of live documents, a quarter-million tokens a new controller is told to read before acting, 268 numbered rulings, and
six process documents as the six most-committed files in the repository. Every rule the record enforces by a sentence
has recurred (pathspec commits three times, same-hour correction four times, junction removal twice, a bare
`git config` after the trap was written down); almost no rule enforced by a script or a test has. Both process audits
before this one prescribed the same cure and built only its cheap slices. The industry sources the review read agree
on the shape: always-loaded instructions under about two hundred lines, deterministic gates outside the agent's
reach, single-threaded writes, files as the durable state. This sprint does no feature work. It converts the recurring
rules into hooks and tests, moves the procedures into skills that load on demand, generates the documents that are
hand-maintained today, and caps concurrency until measurements on this host mean something. The owner set aside the
"visible defects first" order for it in words on 2026-09-26; the sprint records that in D1.

## 1. What is established (2026-09-26) — **[verified: the review's notes 01–06]**

### 1.1 The rules that recur (note 02 §5)

| rule, as written | enforced by | recurrences |
|---|---|---|
| explicit pathspec; never stage another session's file | a sentence (HANDOFF §5 rule 1) | 09-13, 09-18, 09-21 |
| a false sentence corrected the same hour | a sentence (rule 11) | 09-12, 09-17, 09-19, 09-25 |
| "do not push" in a brief | a dead push URL since 09-22; bypassed by a hand-made worktree 09-23 | 09-21, 09-23 |
| `git config` in a worktree needs `--worktree` | a sentence and `scripts/agent_worktree.sh` | 09-23 |
| junctions out before `git worktree remove` | a sentence and the script | twice on 09-21 |
| never edit a running chain script | a sentence | 09-21; near-miss 09-25 |
| kill orphaned watchers | a sentence in a private memory note | 213 orphans over eight days |
| one build at a time | the lock, which `build.sh` does not consult | two builders in one tree, 09-20 |

### 1.2 The record's weight (notes 01 §1, 03 §4, §6)

HANDOFF's "read first" list sums to about 7,300 lines and 975 KB; the minimum useful subset is 2,068 lines and
268 KB. `docs/KNOWN.md` is 266 KB with 230 commits, 224 of them in the last fortnight; `docs/STATUS.md` is 260 KB of
which one block is live. There is no `CLAUDE.md`, no `.claude/settings.json`, no agent definition, and one project
skill, git-ignored. Rulings: 268 global plus two sprint-local namespaces; the counter has two homes; nine rulings a
day on average.

### 1.3 The host (note 02 §3, §4.5)

Five worktrees live at once; memory pressure made the lock's reaper drop queued jobs twice on 2026-09-25; three
frame-time gates on one exe spread 30 % because the host was not quiet; lock waits of 36 to 78 minutes were logged
the same evening. The lock queue serializes but does not batch or evict, and `build.sh` does not take it.

### 1.4 The rules this sprint keeps

- A failing test first, unittest only; the docmaint checks and their planted-defect tests are the model: **a guard
  that has never failed is not known to work**, so every hook, check and generator in this sprint is fired once
  against a planted violation before it is called done.
- Commit with an explicit pathspec; the leak check in the hooks; never `--no-verify`; the record's ceilings (R268).
- What only the owner can decide gets its default and a ruling from the **global** counter; the loop does not wait.
- Nothing that is the owner's is performed.
- Supersede in place, never rewrite history: every document this sprint shrinks is archived verbatim first.

### 1.5 The cloud is gone (2026-09-26)

No Claude cloud session is available to this project from 2026-09-26. The one that started that morning committed
nothing (the Sprint 13 plan's Log, 03:52Z: a 401 on the private inputs, a Linux build stopped at GLFW for want of the
workflow's package list, a remote branch moved and not deletable). The handoff it was to run, "borrowed confidence"
(a confidence register over everything we replaced in PS2Recomp, an external survey with an adoption framework, a
sprint candidate that tries the answers), is kept verbatim as
`docs/superpowers/plans/2026-09-25-borrowed-confidence-cloud-handoff.md` under a banner, and its substance is the
Sprint 15 pair (`docs/superpowers/specs/2026-09-26-sprint-15-borrowed-confidence-design.md`,
`docs/superpowers/plans/2026-09-26-sprint-15.md`), proposed beside this one.

What that changes here. Nothing in this sprint needed the cloud: the `[C]` marker is retired from the plan and E3's
fixture is generated on this machine. Run locally, the research gets stronger, because the register can cite the
generated code, replay the recorded VU1 dumps and count the audio dips on the recordings that already exist, so the
"code half / proof half" split and the "[local]" column of the handoff disappear. What it costs is host time: the
research is no longer free, so it does not run beside this sprint as a second stream. One slice is pulled forward as a
filler (X1): the mechanical external sweep, fan-out reading suited to Opus agents, which builds nothing and runs only
when the host is quiet. The private location that served the owner's ELF dumps to cloud sessions
(`scripts/fetch_private_inputs.sh`'s source) now has no consumer (D9).

## 2. Goals — seven milestones, each with a bar

### Milestone G — guards **[A]** — first, because it stops the damage that recurs every night

- **G1** A PreToolUse hook on Bash, `scripts/hooks/claude_pretool.sh` → `python -m tools_py.hooks.pretool`, reading
  the tool call from stdin and refusing (exit 2, one sentence on stderr): `git add -A`/`.`/`-u`; `git commit`
  without a `--` pathspec or with `-a`; `--no-verify` anywhere; `git push` when the cwd is a worktree; `git config`
  in a worktree without `--worktree` unless read-only; `git worktree remove` outside `scripts/agent_worktree.sh`;
  `loop_lock.sh take` or `release` called directly. Wired by a tracked `.claude/settings.json` so every worktree
  gets it. Bar: `tools_py/tests/test_hooks.py` feeds each planted command and asserts exit 2, and one allowed
  command per rule asserts exit 0; the refusal sentence names the rule's home.
- **G2** A PreToolUse hook on Edit and Write refusing a change to `logs/*.sh` while the lock is held by a chain, and
  to `scripts/loop_lock.sh` unless `LOOP_LOCK_SLOW_TESTS` ran (the existing blob test stays the second guard). Bar:
  the planted case in `test_hooks.py`.
- **G3** A SessionEnd and Stop hook, `scripts/hooks/claude_session_end.sh` → `python -m tools_py.hooks.reap`, that
  kills orphaned `tail`/`grep` watcher processes whose parent shell is gone and never a `bash.exe` with a live parent;
  the kill list is a pure function over a process table. Bar: a planted table of twelve processes yields the right
  five; a live run reports what it killed in one line.
- **G4** Agent definitions under `.claude/agents/`: `implementer.md` and `reviewer.md` with model, tools and the role
  brief that every sprint plan's "Reviews" line restates today. Bar: a dispatch by name works; the plan's Global
  Constraints point at them instead of restating.
- **G5** `build.sh runtime|test|release` refuses to run while another holder has the lock unless it is that holder's
  child; a memory guard in `scripts/run_detached.sh` beside the disk guard. Bar: the planted cases in the shell tests.

### Milestone I — instructions on demand **[A]** — second, because every session reads first

- **I1** A root `CLAUDE.md` under sixty lines: what this is, where the state lives, the guards that exist, the skills
  to invoke, the lock in one line. Registered class C; a test holds the line count. Bar: the test; a fresh session
  told nothing else finds the open item.
- **I2** Procedures as project skills, tracked: `loop-iteration` (LOOP_PROMPT's steps), `agent-worktree` (create,
  brief, review, merge, remove), `run-gate` (the chain and its record), `sprint-close` (DOC_MAINTENANCE §5 and §7).
  `docs/LOOP_PROMPT.md` becomes a pointer under 2 KB. Bar: a test that each skill has frontmatter and that the
  pointer is under its ceiling.
- **I3** HANDOFF made transient: the current file archived verbatim; §5's rules become one line each naming the
  guard or the home; §6's traps move to hazards; §7's instruments to DEVELOPING; a whole-file ceiling of 6,000
  bytes. Bar: docmaint green with the ceiling; every citation of a moved paragraph re-pointed (check 6).
- **I4** A docmaint check for the read-first budget: the bytes of the documents HANDOFF names under "Read, in this
  order" (STATUS by its live block) must sum under 160,000. Bar: the planted defect; the tree passes.
- **I5** KNOWN's §4 (104 standing hazards) split into `docs/HAZARDS.md` (class L), each hazard headed by the area it <!-- docmaint: future -->
  bites; KNOWN keeps §1–§3 (claims with artefacts). Bar: `issues audit` OK; the loop-iteration skill reads KNOWN
  §1–§3 before a hypothesis and the hazards by area.

### Milestone W — the host **[A] then [L]** — third, because it corrupts what the gates measure

- **W1** A WIP cap in the queue: `loop_lock.sh wait` refuses a third queued build ticket (exit 4, "queue full: do
  lock-free work"); at most two implementing agents building. Lock script change, so `LOOP_LOCK_SLOW_TESTS=1`
  green before the commit. Bar: the slow run; two nights with the cap on.
- **W2** The merged chain is the gate unit: an agent's task is `DONE (code)` at a clean review; the controller's chain
  (recomp, runtime, suites, gate, the held-out leg) runs once per batch; a red batch bisects by branch and the
  culprit is evicted with a recorded revert of its merge. Written into the loop-iteration skill and GIT_STRATEGY.
  The queue log gains `TICKET <id> waited <seconds>`. Bar: one batch gated as a batch; the ticket line in the log.

### Milestone D — decisions with status **[A]** — fourth, because the owner's sitting is what closes the carry

- **D1** `python -m tools_py.rulings` writes `docs/RULINGS.md` (class G): number, date, one line, status (active, <!-- docmaint: future -->
  superseded by, retracted, withdrawn, vacant), home; `--check` fails when stale. Bar: planted fixtures; the registry row.
- **D2** The scope rule in DOC_MAINTENANCE §6: a ruling only when an owner default, an acceptance bar or a spec goal
  moves; a threshold, a skipped measurement or a naming choice is a KNOWN row, a knob default or a test. No
  sprint-local namespaces from this sprint on. Bar: the section; the check that one counter line exists.
- **D3** `python -m tools_py.sitting` writes `docs/SITTING.md` (class G): the owner's page — the O rows with their <!-- docmaint: future -->
  defaults, the active rulings since the last sitting stamp, the issues at carry 2, the build PLAYTEST names. The
  owner answers by number, one line each. Bar: the generator's test; the page produced at the close.
- **D4** The circuit breaker: an O row that has stood through two sittings is closed by default under a ruling at the
  next close, struck with the date, reversible. Written into DOC_MAINTENANCE §7. Bar: the procedure; its first use.
- **D5** PLAYTEST always runnable: the merged chain's last step builds the release archive and writes PLAYTEST's
  build block from it. Bar: PLAYTEST never says NOT BUILT after a green chain.

### Milestone S — the record generated **[A]**

- **S1** `python -m tools_py.changelog` writes `docs/CHANGELOG.md` (class G) from merge commits and tags per sprint; <!-- docmaint: future -->
  STATUS's log below its live block is archived; STATUS keeps the block and a pointer. Bar: reproducible from
  `git log`; `--check`; the registry rows.
- **S2** A `commit-msg` hook: the subject under 120 characters, the finding in the body. Bar: the planted message.
- **S3** The ceilings ratchet: at each close a ceiling is set to the live size plus ten percent, never raised; new
  ceilings for HANDOFF (whole file), LOOP_PROMPT and CLAUDE.md. Bar: check 7's text; the numbers in `docmaint.py`.
- **S4** One home each: the lock protocol (the script header; three pointers), the never-commit list (GIT_STRATEGY),
  the ruling counter (HANDOFF; the second line removed and the test tightened to "exactly one"). Bar: docmaint.

### Milestone E — evidence that is hard to fake **[A] then [L]**

- **E1** The first PR to `main` after Sprint 13's H1 observed: `build` and `build-windows` ran on the PR head, not
  skipped. Bar: the run ids in the Log; `test_workflows.py` extended if a fix was needed.
- **E2** A held-out leg: a dozen frozen scene references under `scripts/parity/refs/heldout/`, captured by the
  controller at the first quiet window, read by no test and no agent brief (a grep test asserts it), scored only by
  the merged chain. Bar: the leg 12/12 on the sprint's final exe; the grep test.
- **E3** Recompiler re-derivation in CI: the synthetic ELF fixture recompiled on the Linux runner and diffed against
  a checked-in reference; a planted codegen change reddens it once, recorded. Bar: the CI job; the red run's id.
- **E4** Gate freshness: the gate refuses (exit 3) an exe older than the newest runtime source under
  `third_party/ps2recomp` unless `--stale-ok`, and records `TREE <head> dirty=<n>`. Bar: the temp-file test.

### Milestone M — measurement **[A]**

- **M1** `python -m tools_py.flow` writes `docs/FLOW.md` (class G) at each close: merges per day, fix rounds per <!-- docmaint: future -->
  merge (counted on the merged branch), subjects containing " again", the docs share of churn over seven days,
  median ticket wait from the queue log, open-issue age, distinct sessions and commits per session. Bar: every number
  names its command; `--check`; the first snapshot at this sprint's close.
- **M2** Token spend, local only: `--usage` reads the session transcripts when `SOCOM_CLAUDE_TRANSCRIPTS` names the
  directory; the page says "not measured" otherwise. Bar: the flag; nothing private in the tree.

### Filler X — the external sweep for Sprint 15 **[A]** — outside the order; runs only when the host is quiet

- **X1** One research note (the next free number) that collects what Sprint 15's survey will judge, and judges
  nothing: upstream `main` past `75d729c` and its branches `feature/iop-emulator` and `feature/performance-patch-1`;
  the closed and merged PRs since our base; every fork with commits of its own (137 forks on 2026-09-25 —
  `gh api repos/ran-j/PS2Recomp/forks --paginate`, then `compare` per fork, keeping `ahead_by > 0`, their subjects and
  READMEs, and which game each targets); upstream PR #254 read in depth (the DQ8 fork: whole VU1 programs compiled
  from microcode recorded at run time with differential tests against the interpreter, and the disc's own sound IRX
  modules on a small LLE IOP with both SPU2 cores — the handoff's reading of 2026-09-25, to be checked against the PR
  as it stands); `docs/research/63-upstream-triage-2026-09-25.md` §2's watch table extended by a row per source.
  No TAKE or LEAVE: that is the register's to decide, and the register is Sprint 15's. Opus agents, one bounded read
  each with a verification question, one worktree, no build; dispatched only when the queue holds no build ticket and
  no gate is running (W1's `check` says so). Bar: every number names its command; docmaint green; Sprint 15's survey
  starts from this note instead of repeating it.

## 3. Decisions for the owner — each with the default the sprint proceeds on

Rulings are issued at the open from the global counter; none is numbered here.

| # | decision | default |
|---|---|---|
| D1 | An infrastructure sprint ahead of visible defects, set aside from the standing order by the owner's word of 2026-09-26; the order G, I, W, D, S, E, M | as above |
| D2 | KNOWN §4 split into a hazards file | split |
| D3 | The circuit breaker on owner rows after two sittings | yes |
| D4 | STATUS's log archived and the changelog generated | yes |
| D5 | Sprint-local ruling namespaces retired | yes |
| D6 | Held-out captures the agents never see, taken at a quiet window | yes |
| D7 | The WIP cap at two building agents | two |
| D8 | Sprint 15 is "borrowed confidence" (its proposed pair), opened from the register at this sprint's close; the standing order resumes inside it, since the 50 ms music holes (#42) and the VU1 interpreter fallbacks are visible defects | yes |
| D9 | The private-inputs location that served cloud sessions is retired, or its credential rotated, now that no session consumes it — the owner's act; the script stays for a later cloud session | an O row at the open; the loop touches nothing |

## 4. The acceptance bar of the sprint

1. **Every rule in §1.1 has a guard that reddens on a planted violation**, and its sentence in the record is a pointer
   to the guard.
2. **The read-first set under 160 KB** by the docmaint check; `CLAUDE.md` under sixty lines; HANDOFF under 6 KB;
   LOOP_PROMPT under 2 KB; the four skills tracked.
3. **Four generated pages** (rulings, sitting, changelog, flow), each held to its source by a test; STATUS's log
   archived; one ruling counter; no sprint-local namespace.
4. **The host protected:** `build.sh` refuses outside the lock; the memory guard; the WIP cap on for two nights; one
   batch gated as a batch with its ticket waits in the log.
5. **The greens harder to fake:** a PR built on its head; the held-out leg 12/12 on the final exe; the recompiler
   re-derivation red once on a planted change; the gate refusing a stale exe.
6. **No feature work**, and the owner's sitting page produced at the close with every O row and every active ruling
   since 2026-09-17 on it.
7. **Sprint 15 named at the close** (D8): its pair confirmed or amended from what this sprint leaves and from X1's
   note if the filler ran; nothing in the pair depends on a cloud session.

## 5. What this does not do

Any runtime, renderer, audio or network change (the backlog keeps them); voice; the community preset; a public
download; anything in HUMAN_TASKS that is the owner's. It does not delete a sentence without archiving it, and it
does not raise a ceiling. It does not write the confidence register or run a trial (both Sprint 15's); X1 collects
sources and passes no verdict.

## 6. Pointers

`docs/audits/2026-09-26-autonomy-structure-review.md` and its six notes; `docs/superpowers/plans/2026-09-26-sprint-14.md`;
the Sprint 15 pair (`docs/superpowers/specs/2026-09-26-sprint-15-borrowed-confidence-design.md`,
`docs/superpowers/plans/2026-09-26-sprint-15.md`) and the handoff it came from
(`docs/superpowers/plans/2026-09-25-borrowed-confidence-cloud-handoff.md`, never run);
`docs/DOC_MAINTENANCE.md` (the classes, the checks, the ceilings); `scripts/loop_lock.sh` (the lock's reference);
`scripts/agent_worktree.sh`; `tools_py/docmaint.py`; `tools_py/issues.py`; `docs/HUMAN_TASKS.md` (O1–O15).
