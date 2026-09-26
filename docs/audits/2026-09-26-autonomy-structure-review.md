# How the autonomous development structure is holding — a review, 2026-09-26

*Class S (snapshot, dated in the filename). Read-only: nothing was built, run, committed or locked for this review.
Requested by the owner on 2026-09-25 night: "a wholeistic review of how the autonomous development structure is holding
thus far", industry comparison, and options to adjust course. Tree read at `3804d10b`..`5ea83ecf` with Sprint 13 open
and Task 99 (the close) not started, so Sprint 13 counts are provisional.*

**Evidence.** Six read-only agents, one question each, wrote the notes beside this file in
`docs/audits/2026-09-26-autonomy-structure-review/`: 01 the process as designed; 02 outcomes and incidents from the
project's own record and the assistant's memory notes; 03 git forensics with every command; 04 agentic-workflow practice
2025-2026 (Anthropic, Cognition, OpenAI, Cursor, Amp, Google, METR, DORA, arXiv); 05 conventional process practice
(Google's engineering docs, SRE, ADRs, merge queues, Shape Up, Kanban, DORA, decomp projects); 06 Claude Code harness
features. Every number below is in one of those files with its command or URL. Where a source is secondary or
vendor-claimed, the notes say so; this file repeats the flag where it matters.

---

## 1. The verdict

The structure works as a production line and is failing as a memory. Four weeks produced 1,616 commits, thirteen
sprints, a playable port with online rounds, a 2.6x test-suite growth in five days, a review loop that catches blocking
defects, and a retraction culture the field would envy. That is the strong half. The weak half is the record the loop
runs on: about one megabyte of "live" documents, a quarter of a million tokens a new controller is told to read before
acting, 268 numbered rulings in thirty days, six process documents as the six most-committed files in the repository,
and a run of incidents whose recurrence the record itself predicted. The project's own 2026-09-25 audit said it in one
line: the code is in better order than the record. This review agrees, and adds the industry comparison: every
credible practitioner source converges on small always-loaded instructions, deterministic gates outside the agent's
reach, single-threaded writes, and files (not sessions) as the durable state. The project has the last of these in
excess and the first two in deficit.

The one-sentence recommendation: **spend the next sprint converting rules into mechanisms and prose into generated or
on-demand material, and cap concurrency until the host stops corrupting measurements.** Details in section 5.

---

## 2. What is holding

| Strength | Evidence (notes file) |
|---|---|
| **Throughput.** 1,616 commits in 30 days; 302 commits and 51 merges on 2026-09-25 alone; 40 % of commits land between local midnight and 09:00 | 03 §1 |
| **First-pass review quality.** Of 112 merges, 65 % needed no fix round and 89 % at most one; median merged branch is 3 commits | 03 §2.2 |
| **Review catches real defects.** Sprint 13 C4's reviewer found the resume-target tail-call hazard (a blocking find, now #60) | 01 §7, 02 §9 |
| **Retraction culture.** KNOWN's §3 exists; latency fell from two weeks (2026-09-12) to same-hour (2026-09-14) to an explicit "retract on discovery" rule; the last four retractions were the instrument's fault, not the game's | 02 §4.9, §9 |
| **Enforcement is moving into code.** Ten docmaint checks, each fired against a planted defect; the leak gate on hook, push and CI; the machine-wide lock with a ticket queue that "served every ticket in arrival order tonight"; agent worktrees with a dead push URL | 01 §5, 02 §5 |
| **The issue stack.** Opened 2026-09-23; 32 issues, median time-to-close 37 h; harness issues 80 % closed | 03 §10 |
| **Ordering discipline.** "Visible defects above infrastructure" has held since 2026-09-16 and is restated in every spec | 01 §12 |
| **Self-awareness.** Five audits in fourteen days, each naming the rule-vs-tool thesis; the 2026-09-25 audit's 403 findings had a disposition each | 02 §2 |

Nothing in this review argues for undoing any of these.

---

## 3. What is bending — nine findings

Ranked by how much they cost per week, with the industry comparison beside each.

### F1. The record is the failure surface, and it is growing faster than the code

- Live documents under `docs/*.md`: 18 files, 1.04 MB. The ordered "read first" set in HANDOFF sums to about
  7,300 lines / 975 KB (roughly 250k tokens) if STATUS is counted whole; the minimum workable subset is still
  2,068 lines / 268 KB. (01 §1)
- The six most-committed files in the repository are process documents. `docs/KNOWN.md` has 230 commits, 224 of them
  in the last 14 days, three times the most-committed source file. 41.9 % of commits with a diff touch only Markdown.
  Docs were 17.7 % of lines ever added and 24.0 % in the last week. (03 §4, §6)
- Duplicated homes persist despite single-source rules: the ruling counter in two files, the lock protocol in four
  places, the never-commit list in two, the worktree recipe in two. HANDOFF §5 rule 4 is 14 lines of which 5 are its
  own retraction trail; trap 6 is two superseded blockquotes around one live sentence. (01 §9)
- Median commit subject is 126 characters; 42 % of merge subjects exceed 200; the longest is 1,184. The merge line
  is being used as the sprint's outcome record. (03 §5)

**Industry.** Anthropic's Claude Code guidance targets CLAUDE.md under 200 lines and says bloated instruction files
"cause Claude to ignore your actual instructions"; a practitioner analysis puts the median well-performing file at
300-350 words with negative returns past 1,000 words (single source, flagged). Google's engineering-docs chapter reports
that its unowned wiki decayed until "around 90 % of the documents had no views or updates in the previous few months",
and prescribes an owner, a last-reviewed date with an expiry reminder, and one purpose per document. SRE practice
separates the transient handoff (read once at shift start, then discarded) from the durable runbook and the
per-event postmortem; HANDOFF is doing all three jobs. (04 Q1, Q5; 05 §1, §3; 06 §1)

### F2. Rules recur; tools do not

Every rule-only fix in the record has a recurrence; almost no tool fix does. (02 §5)

| Rule | Recurrences |
|---|---|
| Explicit pathspec, never stage another session's file | 09-13, 09-18, 09-21 |
| Correct a false sentence the same hour | 09-12 (two weeks), 09-17, 09-19, 09-25 (twelve places) |
| "Do not push" in a brief | ignored 09-21; the tool that replaced it was bypassed by hand 09-23 |
| Remove junctions before `git worktree remove` | twice on 09-21 |
| Never edit a running chain script | 09-21 cost a capture; near-miss 09-25 |
| A launch script must set the server | class recorded 09-20; happened 09-25 |
| Kill orphaned watchers | 213 accumulated over eight days |

Both process audits (2026-09-12, 2026-09-20) prescribed subsystems that were never built: the run queue, the
results store, the hitch ledger, the claims registry, the skip budget, the preflight. Only the cheap mechanical slices
landed. The de-facto hitch ledger is the assistant's private memory directory (34 notes), which is outside the
repository and therefore exactly what a controller handoff loses. (02 §2.3, §4.6)

**Industry.** Anthropic: "Unlike CLAUDE.md instructions which are advisory, hooks are deterministic"; "If Claude
already does something correctly without the instruction, delete it or convert it to a hook." Lean practice calls this
poka-yoke: quality "caused, not controlled". The harness has PreToolUse, Stop, SubagentStop and SessionEnd hooks and
per-agent tool deny lists; the repository uses none of them and has no root CLAUDE.md, so every rule reaches an agent
only if the agent reads the right paragraph. (04 Q1, Q3; 05 §4; 06 §2, §3, §7)

### F3. Claims ahead of the fact, and greens that were not

- On 2026-09-25 five live documents said Sprint 11 was merged as `v0.11.0` while the PR was open and no tag
  existed. The suite counts in DEVELOPING are behind the merges that cite them by a few cases. HANDOFF's "LATEST"
  pick-up bullet is a day and six merges stale. (01 §9.2, 02 §4.1)
- "CI green" was six red Python tests read through docs-only skips, and both sprint merges to `main` passed their
  required checks on skipped builds ("a PR to `main` has never been built as a PR", Sprint 13 H1). (02 §4.3)
- The gate compares our runs to our earlier runs, a regression fence against ourselves; the 2026-09-12 audit called
  this "the highest-yield defect class in the project" and it is still the design. (02 §2.1, 01 §12)

**Industry.** A first-hand audit of 101 "tests pass" claims found 35 % false, 34 of them stale (passed before the
agent's last edit); the mechanical defeat is to require the final gate run to postdate the last file change.
SpecBench measures the gap between visible-test pass rate and held-out pass rate and finds it grows about 27 points per
tenfold increase in code size; even human-supervised runs showed a 14.5-point gap. The published mitigations with
evidence are held-out checks the agent never sees and scoring computed outside the agent's sandbox. Emulator and decomp
projects put their effort into one high-volume mechanical differential gate (PCSX2 replays 2,000+ scenes and
image-diffs them; OpenGOAL re-decompiles every file on every build against checked-in references). (04 Q3; 05 §6)

### F4. Rulings are an unbounded prose decision log

268 global rulings in 30 days (about nine per active day), cited about 2,993 times, plus two sprint-local namespaces.
The counter read R179 while R240 was in use; three numbers were issued twice; three cited numbers had no text; one
agent numbered "from R200 into taken ground". Many rulings are operational one-offs (a threshold moved, a
measurement skipped) rather than decisions the owner would want to overturn. The owner's implied duty is to audit
about ninety rulings per five days. (01 §4, §10; 02 §4.8; 03 §8)

**Industry.** ADR practice is also append-only and monotonic, and survives scale only because records are scoped to
architecturally significant decisions, carry a status (accepted, superseded-by, deprecated) and a maintained index.
Minting a permanent record for an operational one-off is category confusion; those belong in a runbook or a lint rule.
Retrospective anti-pattern literature names the failure: "when you have too many top priorities, you effectively have
no top priorities." (05 §2, §4)

### F5. One host, many writers, corrupted measurements

- Between three and six Claude sessions have shared one machine and one repository; five worktrees were live at once.
  Host memory pressure made the lock's reaper remove queued launches and a build twice on 2026-09-25; three frame-time
  gates on one exe spread 30 % on the mean "because the host was not quiet"; a timing test was widened rather than
  fixed; 213 orphaned watchers slowed every bash start. (02 §3, §4.4, §4.5)
- The lock queue serializes but does not batch or evict: C2 waited 78 minutes for one hold; queued waits of 36 to 48
  minutes were logged the same evening. (02 §6)
- `build.sh` does not know about the lock; two `./build.sh runtime` share one build directory. (02 §2.3)

**Industry.** Cognition's 2026 position after reversing its 2025 essay: "Multi-agent systems work best today when
writes stay single-threaded and the additional agents contribute intelligence rather than actions." Anthropic's agent
teams doc: three focused teammates "often outperform five scattered ones"; two agents editing one file "leads to
overwrites". Merge queues make a single validation resource cheap by batching candidates and auto-evicting failures;
the lock has neither. Kanban's WIP limit is the direct control. (04 Q2; 05 §3, §4)

### F6. Controller handoffs lose state, and sessions run long

Thirteen pick-up generations between 2026-09-20 and 2026-09-25; the archive's own banner miscounts them. Each
boundary records a loss: unfinished worktrees at a session limit, ownership re-established by asking the owner, three
of four artefacts already written, nine owner rows stale by three days. 814 commits carry a session URL but only 17
distinct ones (about 48 commits per session). The 2026-09-20 audit's HO-6 stated the mechanism: seven incidents lived
"only in the controller's context, which is exactly what is lost at a handoff." (02 §4.10; 03 §1.3)

**Industry.** Anthropic's long-running harness: one unit of work per fresh context, with a progress file and git
history read at every start; "after two failed corrections, `/clear` and rewrite the prompt". Every vendor hands
context through a written artefact, never through chat history. A progress file that is written but not read at
start-up "has the cost without the benefit." (04 Q1, Q3, Q5)

### F7. The owner loop is shaped to never wait, and so never closes

Fifteen owner rows, each with a default the loop proceeds on; the oldest have waited eight days in the current file
and much longer in substance (the two-machine match carried since Sprint 7; six music listens owed since
2026-09-17; the listen gate bypassed since 2026-09-20). PLAYTEST cannot be run because no archive exists for the
current tree. The previous HUMAN_TASKS reached 104 KB with seven "Start here" generations and was never drained. The
loop's autonomy is real (302 commits with the owner away) and the cost is that the human's irreducible acts pile up
undone while defaults harden into facts. (01 §10; 02 §8)

**Industry.** The one credible multi-week solo case study (one engineer, four agents, nine weeks) kept the human in a
steering role and confined the fully autonomous agent to non-core work; its failure seam was undocumented behavioural
contracts. Nobody credible reports a sustained unattended loop with no human rulings, and no case study reports a
ruling cadence. Shape Up's devices, an explicit appetite per bet and a circuit breaker that cancels rather than rolls
forward, are the missing controls here. (04 Q6; 05 §4)

### F8. Nothing measures cost or flow

The record has no mention of model usage, token spend, or cost anywhere in the state documents; the one recorded
usage event is three review agents dying on HTTP 429 on 2026-09-17, which produced the Opus-for-mechanical-work rule.
There is no trend line for fix rounds per merge, rework, lock wait per ticket, or doc share of churn; this review
computed them once by hand. (02 §2.2; 03 throughout)

**Industry.** The metric set that recurs is autonomy rate, human-intervention rate, tokens per merged change,
rework rate and change-failure rate, each against a baseline. DORA's repeated finding is that AI raises throughput and
instability together; a loop merging many agent branches a day should be tracking the instability half, not just the
green count. Tokens per merged change is the cheapest early warning for gate-gaming and correction spirals. (04 Q4;
05 §5)

### F9. The verification architecture is thinner than the field's for a project of this kind

The parity gate is three stages (title, transition, mission) scored against our own earlier captures; the PCSX2 golden
comparison was itself retracted once as "the same frozen state"; audio parity sits at 31/48 unchanged since
2026-09-20; CI builds without generated game code and "proves nothing about the game." Static recompilation has no
byte-identical oracle, which raises rather than lowers the value of a captured-reference replay harness. (01 §11,
§12; 05 §6)

---

## 4. The trend in one line

More reliable and heavier at once: nine new enforced mechanisms between 2026-09-20 and 2026-09-25, and in the same
window 133 unfinished items in six homes and a sprint file that was 12 % live. Reliability moved from people to tools;
weight moved from tools to the record. (02 §9)

---

## 5. Options

Speculative, ranked by leverage per unit of lock-free work. None needs a build. Each says what it buys, costs and risks.

### A. Convert the recurring rules into hooks and tool denials (F2, F5)

- A project `.claude/settings.json` with PreToolUse hooks on Bash that refuse: `git config` without `--worktree` or
  `--local` when cwd is a worktree; `git push` from any worktree path; `git commit` without a `--` pathspec;
  `loop_lock.sh take` outside the sanctioned scripts; editing a file under `logs/*.sh` while a chain runs. A
  SessionEnd or Stop hook that kills the session's own watcher tree. Hooks in the shared project settings apply in every
  worktree. (06 §2, §7)
- Agent definitions under `.claude/agents/` for implementer and reviewer roles, with `git push` denied at the
  definition and the model set per role, replacing the per-brief sentence.
- Buys: the seven recurring rules in F2 stop depending on memory. Costs: a day of authoring and testing (the docs show
  no example for these patterns). Risk: a hook with false positives gets switched off; each hook needs its planted-defect
  test, the same discipline docmaint already uses.

### B. Progressive disclosure: a small always-loaded file, procedures as skills, a transient handoff (F1, F6)

- A root CLAUDE.md under 60 lines: the five rules that stop damage, where the state lives, how to find the rest.
  Anthropic's own guidance says the size matters more than the content.
- The procedures that are prose today become project skills invoked on demand: one loop iteration, create and remove a
  worktree, run a gate, the sprint close's §5/§7 reviews. LOOP_PROMPT.md becomes the skill's body.
- HANDOFF shrinks to the SRE shape: what is in flight, what is owed, what to do first, under a byte ceiling of a few
  kilobytes, rewritten at every handoff, with its durable content moved to DEVELOPING (reference), KNOWN (hazards) or
  a skill (procedure).
- A measurable target: the read-first set under 40k tokens. A docmaint check can enforce it the same way the ceilings
  are enforced today.
- Buys: a new controller acts in minutes, not after a quarter-million tokens; adherence improves for the rules that
  remain. Costs: two or three days of consolidation. Risk: losing a trap nobody remembers; mitigated by moving text to
  the archive rather than deleting it, which the project already does well.

### C. Reform the rulings into a decision log with status and scope (F4, F7)

- A ruling only when an owner default, an acceptance bar, or a spec goal moves. Everything else (a threshold, a skipped
  measurement, a naming choice) goes where its consequence lives: a KNOWN row, a test, a knob's registry entry.
- One generated index (`tools_py` already parses the definitions) with status per ruling: active, superseded-by,
  retired. The owner's sitting reads the active set, which should be a few dozen, not 268.
- Retire the sprint-local namespaces or make them the only scheme; two counters is the failure that already happened.
- Buys: the owner can actually exercise the overturn right the rulings promise. Costs: a classification pass over
  268 entries, mechanical, an Opus agent's afternoon. Risk: an operational one-off that mattered loses its number;
  the archive keeps the text.

### D. Put the record on a diet by generating it (F1, F3)

- STATUS becomes a generated log from git, gate summaries and issue events, with a hand-written current-state block
  under its existing ceiling; the 2,574-line file is archived as class A.
- KNOWN splits: §1 and §2 (claims, with artefacts and issues) stay live and small; §4's 104 standing hazards move to
  a hazards file that skills and hooks cite by anchor, each hazard with an owner check where one is possible.
- Ratchet the byte ceilings down at each close instead of holding them; a ceiling that only prevents growth
  institutionalizes the current size.
- Buys: the documents that are edited 230 times a fortnight stop being hand-maintained; the "written ahead of the act"
  class shrinks because the generator writes after the act. Costs: a generator and its test. Risk: a generated log
  loses the reasoning that the hand-written entries carry; keep reasoning in the merge commit and the plan's Log, which
  is where it already is.

### E. Make the greens harder to fake (F3, F9)

- CI must build PRs to `main` on the PR head (Sprint 13 H1's fix, if landed, closes this; verify on the next PR).
- A gate-freshness invariant: the gate summary records the tree hash and refuses a claim whose exe or tree predates the
  last edit; docmaint's check 3 already has the dated-count shape to extend.
- One held-out leg: a capture set the implementing agents never see, run by the controller at merge, so a scorer tuned
  to the visible set is caught. The field's version is PCSX2's 2,000 scenes; a dozen frozen scenes would already change
  the information content of "3/3".
- A recompiler re-derivation check in CI: recompile a fixed ELF fixture and diff against a checked-in reference, the
  OpenGOAL pattern, so a codegen change cannot pass on "the suites are green".
- Buys: "gate 3/3" starts to mean what readers think it means. Costs: capture and reference upkeep. Risk: a held-out set
  that drifts becomes a flake source; version it with the pins.

### F. Cap concurrency and protect measurements (F5)

- A WIP limit enforced by the lock: at most two implementing agents building, one game run, and no gate while any
  build runs; the ticket queue already knows the count.
- A memory guard beside the disk guard in `scripts/run_detached.sh`.
- Batch the proof: one merged-chain gate per evening over all merged agent branches (the merge-queue pattern) rather
  than a gate per task, with auto-eviction of the branch whose bisect fails. Sprint 13's `s13_merged_chain` is already
  this shape; make it the rule.
- Move non-game agents' builds off the host (the Linux VM or a cloud session) so the host is quiet when it measures.
- Buys: measurements that mean something, fewer reaper casualties, shorter waits. Costs: less parallelism on paper.
  Risk: none measurable; the median branch is three commits and the queue waits were up to 48 minutes, so
  parallelism was already buying less than it cost.

### G. Give the owner a sitting that closes (F7)

- A generated one-page digest at each close: active rulings since the last sitting, one line each with the overturn
  handle; the owner rows with their defaults; the one build the playtest needs. The owner answers by number.
- Always-runnable playtest: the release archive is a chain step, not an owner act, so PLAYTEST never says "NOT BUILT".
- Shape Up's circuit breaker for owner rows: an item that has waited two sittings is closed as "default accepted" by
  ruling, visibly, instead of carried.
- Buys: the fifteen rows drain; defaults become decisions. Costs: a generator; a half-hour of the owner per week.
  Risk: an item closed by default that the owner wanted; the ruling is overturnable and the archive keeps it.

### H. Instrument the loop (F8)

- A small `tools_py` flow report from git and the lock's queue log, printed at each close and kept as a dated snapshot:
  merges per day, fix rounds per merge, subjects containing "again", doc share of churn, median lock wait per ticket,
  work-item age of open issues. Token spend per session if the session logs can be read locally; failing that, the
  count of sessions and their lengths.
- Buys: the first trend lines; the ability to see gate-gaming or a correction spiral as rising cost per merged change.
  Costs: a day. Risk: metrics that get optimized; keep them descriptive, no targets for a sprint.

### I. Course options

1. **Stay the course, apply A and F now.** Cheapest; fixes the recurring incidents and the measurement corruption.
   Leaves the record growing.
2. **A consolidation sprint (Sprint 14) with no feature work: A, B, C, D, H.** The record's weight is the project's
   largest measured cost and every option above is lock-free, which is the loop's scarcest resource. This is the
   recommendation. It is also what the 2026-09-12 audit said: "almost none of what is wrong with the process is
   competing for [lock time]."
3. **Single-writer mode: one implementing agent at a time, unlimited readers (reviewers, researchers).** Cognition's
   model. Defensible on the evidence (three-commit branches, 48-minute waits, host contention), but it trades the
   overnight throughput the owner has valued. Recommended as F's cap of two rather than one.

---

## 6. What not to change

Worktrees with a dead push URL; review by a fresh agent that did not write the code; KNOWN's promoted/retracted
contract; the issue stack with a bar per issue; planted-defect tests for every check; the ticket queue; "visible
defects above infrastructure"; the acceptance bar unchanged since 2026-09-09. These are the parts the industry
sources describe as best practice, and the record shows them working.

---

## 7. Limits of this review

- Nothing was built, run or re-derived; every number is read from a file, a `git` query or a `gh` query. Sprint 13 was
  open throughout and its counts are provisional.
- The assistant's memory directory was read as evidence; it is private and untracked, so a reader of the repository
  cannot check those citations. That is itself finding F2.
- Industry sources vary in quality. The notes mark secondary and vendor-claimed figures; in particular, the "35 %
  false claims" figure is one developer's two weeks, the instruction-length numbers are one practitioner's analysis,
  the DORA threshold tables need a year attached because DORA dropped its tiers in 2025, and I found no published
  post-mortem of an autonomous loop that failed over weeks, so publication bias is real.
- Cost and token data do not exist in the record, so F8 is an absence, not a measurement.
- This file was written by a Claude session, the same class of actor it reviews; the writer and the reviewed share a
  model and may share blind spots (the codex audit of 2026-09-23 made the same caveat).
