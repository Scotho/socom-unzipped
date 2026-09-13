# Process audit — the loop, the validation stack, and how sprints are planned

Written 2026-09-12, end of Sprint 4, from the sprint ledger
(`.superpowers/sdd/2026-09-12-sprint-4-visible-defects-and-first-kill/progress.md`), the
task reports beside it, `docs/LOOP_PROMPT.md`, `scripts/loop_lock.sh`, `build.sh`, the
`tools_py/parity/` stack and its tests, and the four sprint spec/plan pairs. Read-only: nothing
here was built, run, or committed, and no lock was taken.

This is an audit of **how the work gets done and how it gets checked**, not of the game.

---

## Ordering principle

Items are ordered by **expected cost of the failure they prevent, divided by effort**, with two
tie-breakers applied in this order:

1. **A false green outranks a slow green.** A gate that passes when it should fail writes a wrong
   belief into a committed document, and that belief is then quoted as fact for weeks by every
   later agent. `docs/HANDOFF.md:42` ("the PCSX2 golden match is the same frozen state") is the
   measured price of this: it was two stills of a match with no input ever sent, and it aimed
   weeks of server-side work at an exonerated component. Nothing in this list costs as much as
   that, so everything that makes a false green impossible sorts above everything that makes a
   true green faster.
2. **A mechanical check outranks a rule someone must remember.** Every process failure in the
   sprint record was caught by a *person* (an implementer's honesty or a reviewer's re-derivation),
   not by a script. That worked, but it costs a review round each time and it is not durable —
   the reviewer who found the ±1 px blindness will not be here next sprint. Prefer changes that
   turn today's judgement into tomorrow's assertion.

Consequence of the principle, stated up front so the ordering is not a surprise: **the biggest
win is structural, and it is not in the loop and not in the gate.** It is that five separate
defects this sprint are one defect — *a scorer was never tested against a synthetic instance of
the thing it exists to detect* — and the project has no rule that would have caught any of them
before review. Items 1 and 2 are that finding split into the part that is live today and the part
that is a standing rule.

---

## 1. No scorer may return PASS without first asserting its instrument was live and aimed

**What breaks today.** Every verdict in the stack is computed from pixels, and nothing checks that
the pixels came from a live, correctly-configured instrument. Four independent preconditions are
unasserted: the window geometry, the freshness of the capture, the liveness of the process, and
the exit code of the thing that produced the run. Each has already produced a convincing verdict
about nothing.

**The evidence.**

- **Window geometry — and this one is live and got *worse* today.** The Task 2 fix
  (`drive.py:crop_to_content`) made the title gate score a deliberately pillarboxed run
  **18/23** where it previously scored 0/23 (ledger, "Task 2: implementer DONE, commit 193ed92").
  `gate.py:TITLE_MIN_MATCHES = 16`. A clean run scores 19/23. **So a run on a resized window now
  PASSES the title gate with two captures of margin** — where before the fix it failed loudly.
  The fix was correct in intent (the guards now match, so the probe reaches the menu instead of
  stalling), but it converted a loud failure on an invalid configuration into a quiet pass, and
  the invalid configuration is one the project explicitly forbids: the Sprint 4 plan's Global
  Constraints say "Do not resize the game window during a run", and
  `tools_py/parity/resize_window.py`'s own docstring says runs made with it "are captures to look
  at, not gate results". Nothing enforces either sentence.
- **Capture freshness.** `winshot.grab()` (`tools_py/parity/winshot.py:60-80`) reads the frame file
  the runtime rewrites every ~150 ms. It retries for 3 s on a read error and then returns the
  file's contents — **with no check that the file was written recently**. If the exe wedges,
  crashes, or stops presenting, every subsequent `grab()` returns the same stale image
  indefinitely, and every scorer downstream reads it as a screen. Ledger, Task 6 §3.10: "three of
  six two-instance runs were unusable, and one ran all SIXTEEN stick probes and wrote SIXTEEN
  screenshots against a LOBBY KEYBOARD: a complete, plausible-looking evidence set attesting to
  nothing", plus "screenshots go stale".
- **Process liveness.** `tools_py/parity/online_match_ours.py` checks exactly one precondition, at
  line ~60: that `socom2.exe` is not *already* running. After launch it never checks that either
  instance is still alive, never checks it reached gameplay, and drives `--probe` / `--play` /
  `--sweep` unconditionally. One Sprint 4 run "lost instance A outright" and still produced
  screens. The ledger records the only working liveness signal the project has —
  `PS2X_PEEK=0x416054` position rows, non-zero only in gameplay — as a rule a human is supposed to
  remember (close-out list: "verify peek @416054 is non-zero before believing ANY screenshot").
- **Exit codes and logs.** `gate.py:run_gate()` calls `drive.py` with `subprocess.run(...)` and
  never looks at the return code; it calls `montage` with output discarded; it copies the newest
  `logs/run_*.log` to `<gate>.game.log` and **never reads a byte of it**. A run that spewed
  unhandled instructions, GL errors or an assert scores exactly like a clean one.

**The change.** One helper, `tools_py/parity/preflight.py`, and four call sites.

1. `winshot.grab(hwnd, max_age=2.0)`: when the capture comes from a frame file, `os.stat(path).st_mtime`
   must be within `max_age` of now, else raise `StaleFrameError`. `drive.py`'s wait loop catches it
   once and retries, then aborts the run with a non-zero exit; the burst/step capture path lets it
   propagate. Unit-testable with a temp file and a back-dated mtime — no game, no build.
2. `drive.py`: record `GetClientRect` at launch and every 30 s into `manifest.json` as
   `client_rect`. `gate.py` reads it and **FAILs any gate whose run was not at the expected extent**
   (640×448 × `PS2X_GS_SCALE`), with the message naming the measured size. Keep `crop_to_content`
   — it is the right behaviour for a diagnostic capture — but it must never be the reason a gate is
   green.
3. `gate.py:run_gate()`: fail the gate if `drive.py` exited non-zero, and grep the copied
   `<gate>.game.log` for a small, versioned list of fatal patterns (`unhandled-instruction`,
   `Assertion`, `FATAL`, `terminate called`, `GL_ERROR`). Same shape as `build.sh`'s
   `vram_diff_check` and `expect_native`: capture, print, then assert on the output rather than
   trusting an exit code.
4. `online_match_ours.py`: an `assert_in_gameplay(client)` gate before the `--probe` / `--play` /
   `--sweep` phases, reading the `[peek] @416054` rows out of the instance's log and requiring a
   non-zero, *changing* value on both instances, plus `proc.poll() is None`. Abort non-zero
   otherwise. Add the same as step 0 of research/18 §3.6's run recipe (the Task 6 extension review
   already asked for this and it was recorded as a doc edit, not as code).

**Cost.** Half a day. No build. No game run to *write* — every piece is unit-testable against
fabricated files. One gate leg (~3 min under the lock) to confirm nothing regressed, whenever the
lock is next free.

**What it would have caught.** The sixteen screenshots against a lobby keyboard, and the run that
lost instance A (freshness + liveness). The three unusable runs of six would have aborted in
seconds instead of producing a full evidence set that a reviewer then had to disbelieve. And
today's live hole: a gate run on a resized window currently passes at 18/23.

---

## 2. Every scorer ships with a defect-injection suite, and `build.sh test` runs the Python tests

**What breaks today.** `build.sh test` — the command `docs/LOOP_PROMPT.md` goal 1 names as the
hygiene bar — **does not run a single Python test.** It builds and runs `ps2x_tests.exe` and the
`vu1_replay` fixtures, and stops. The 43 tests that guard the entire parity gate are run by hand
or not at all. Three older test files have never run in their lives. And `movie_blocks.py` — the
tool that took four review rounds and five dispatches to make trustworthy — has **zero** tests.

**The evidence.**

- `grep -n "python -m" build.sh` → one hit, inside a comment.
- `python -m unittest discover -s tools_py/tests -t .` → `Ran 43 tests ... OK`, **10.8 seconds**.
  Nothing invokes it.
- `tools_py/parity/test_compare.py`, `test_pine.py`, `test_winshot.py` are pytest-style
  module-level functions (`test_pine.py` literally does `import pytest`), living outside
  `tools_py/tests/`. `python -m unittest` cannot discover any of them, and pytest "is invoked
  nowhere" (ledger, Task 2 ruling). `test_compare.py` is three tests of `compare.score` — the
  function at the heart of the title gate — and they have never executed. This is the *same*
  defect the Task 2 ruling fixed for the new file; the pre-existing instances were never swept.
- `tools_py` has no `__init__.py`, so whole-tree discovery raises `ImportError: Start directory is
  not importable` — the reason the narrow `-s tools_py/tests` path is the only one that works, and
  the reason a stray test file silently disappears.
- Five of this sprint's defects are one class — *the scorer was never tested against a synthetic
  instance of the defect it detects*:
  | scorer | how it failed | found by |
  |---|---|---|
  | `score_title` | slid toward the pass floor on a resized window instead of failing | Task 2 |
  | `score_transition` | burst pinned to a step the event had moved past; then a fallback window that admitted unrelated frames; then the trailing unconditional burst readable as the transition | Task 2b + its review |
  | `movie_blocks.py` | non-monotonic (passed *harder* as the bug got worse: 5% → exit 1, 50% and 90% → exit 0); then blind to contiguous drops, the only shape the real bug takes (scattered 100 blocks → 10.0% FAIL, contiguous 100 → 1.8% pass) | Task 1 reviews, rounds 1 and 3 |
  | `--vram-diff` buckets | blind to a uniform ±1 px shift across the whole corpus (12/15 → 0/15) | Task 3 review |
  | `--vram-diff` acceptance bar | the `+8 px` bar in the plan never tested the class it was meant to guard | Task 3 review |
- The adversarial work that established the good properties — the reviewer's six shapes ("I could
  not break it"), the k-sweep, the scattered-vs-contiguous pairs at three sizes, the rigid-translation
  proxy validated to 2 dp — was all done in throwaway scripts in a gitignored workspace. **None of
  it is a test.** The next edit to `movie_blocks.py` can undo all four rounds in silence.

**The change.**

1. Add to `build.sh test_step`, before the C++ build:
   `python -m unittest discover -s tools_py/tests -t . -v`
   (10.8 s; it needs no compiler and no lock, so put it first and fail fast).
2. Move `test_compare.py`, `test_pine.py`, `test_winshot.py` into `tools_py/tests/` as
   `unittest.TestCase` classes. `test_pine`/`test_winshot` need a live PCSX2 / a Tk display —
   `skipUnless`, not deletion.
3. Add `tools_py/tests/test_test_hygiene.py`: walk `tools_py/`, fail if any `test_*.py` lives
   outside `tools_py/tests/`, imports `pytest`, or defines a module-level `def test_`. This is the
   Task 2 plan defect turned into an assertion, and it costs one round trip to write instead of a
   review round plus a fix round every time it recurs.
4. **The standing rule, and the reason this item is here at all:** *a new or changed scorer is not
   done until it has a defect-injection test for each of — (a) a negative control (feed it a run of
   the wrong thing; `gate.py:26-33` already records "a mission run scored as a title run gives
   1/36" as a comment — make it a test); (b) monotonicity (N corrupted units must never score
   better than N/2); (c) invariance to the arrangement of the defect; (d) one instance of the
   defect class the acceptance bar names.* Put it in the plan template and in `LOOP_PROMPT.md`
   goal 1. Then port the Sprint 4 adversarial fixtures into `tools_py/tests/test_movie_blocks.py`
   and into the `--vram-diff` sensitivity table's ±1 px row (build.sh run 6 documents the numbers
   in a comment; a comment is not a check).

**Cost.** Steps 1-3: one hour, no build, no game run. Step 4's rule: free. Porting the Sprint 4
fixtures into tests: half a day, needs `build.sh test` once for the `--vram-diff` half.

**What it would have caught.** Items (b) and (c) are precisely Task 1's rounds 1 and 3; item (d) is
precisely Task 3's ±1 px finding and the `+8 px` bar defect. Four review rounds and roughly nine
dispatches of the sprint's most expensive task are attributable to properties that a
twenty-line injection test states directly. Item 1 of the rule would have caught the pre-crop
transition gate in Sprint 2 rather than after a whole window of vacuous passes.

---

## 3. Plans must pass a preflight that executes their own commands and searches the record

**What breaks today.** Plan text asserts facts about the repo and the system that are cheaply
checkable and were not checked. Three landed in Sprint 4, all caught downstream at the cost of a
ruling, a fix round or a corrected brief.

**The evidence** (all three are the controller's own, recorded as such in the ledger).

- **Tests in a style the repo cannot run.** `docs/superpowers/plans/2026-09-12-...md:129-147`
  specifies five tests as bare `def test_pillarboxed_frame_crops_to_content():` functions. The
  repo's only runner is `python -m unittest`. The implementer shipped them, discovered
  `Ran 0 tests ... NO TESTS RAN`, flagged it honestly; the controller ruled it a plan defect and
  spent a fix round converting them. *Checkable by running the plan's own test command once.*
- **A brief that told an implementer to use a lobby configuration that cannot start a match.**
  Task 5's brief required `--same-team`; the lobby refuses to launch without players on both
  teams. Ledger: "MY BRIEF WAS WRONG on same-team — STATUS 2026-09-10 (probe4) records same-team
  as a dead end on OURS too". *The refutation was already in the project's own committed record,
  written two days earlier.* The implementer deviated and said so, which is the only reason the
  comparison was fair.
- **An acceptance bar that did not test the failure class it guarded.** The plan set `+8 px`
  29-55% as the hard bar for the `--vram-diff` widening. The widening passed it and went blind to a
  uniform ±1 px shift corpus-wide. Ledger: "My +8px bar never measured this, so the gap is in my
  brief as much as in the change." *Checkable by asking, for each bar, which failure classes it
  does **not** separate.*

**The change.** A preflight pass over the plan before the first implementer is dispatched — one
cheap agent, no build, no game run, with three mechanical duties and one writing rule:

1. **Execute or dry-run every command the plan contains.** Every `python -m ...`, every
   `git add <paths>`, every test invocation. A command that errors is a plan defect, found in
   seconds.
2. **Resolve every file:line reference.** The Sprint 4 plan's file map cites ~15 of them; a stale
   line number sends an implementer to the wrong function.
3. **Grep the committed record for every procedural assumption.** For each "do X in the lobby /
   use flag Y / expect screen Z", `grep` `docs/STATUS.md` and `docs/research/` for X. The
   `--same-team` refutation was one `grep same-team docs/STATUS.md` away.
4. **Writing rule for acceptance bars:** every numeric bar states, in the plan, *the failure class
   it separates* and *at least one failure class it does not*. "`+8 px` must still score 29-55%;
   this does not constrain sub-pixel or uniform offsets — measure ±1 px separately" is the sentence
   that was missing. This rule is the plan-side twin of item 2's rule (d).

**Cost.** ~20 minutes of agent time per sprint. No build, no game run. The writing rule is free.

**What it would have caught.** All three of the sprint's plan defects, before any of them consumed
an implementer, a reviewer, a ruling and a fix round.

---

## 4. A standing audit for the one defect class the gate structurally cannot see

**What breaks today.** All three gates score **our output against our own previous output**.
`TITLE_REF = scripts/parity/ref_main_menu_ours.png` — *ours*. The transition gate asserts a band of
rows is black. The mission gate asserts a HUD reference matched and that ≥3 hold steps were
captured (`score_mission_log`: `holds >= MISSION_MIN_HOLDS`) — it scores no pixels at all. So the
gate is a **regression fence against ourselves**, and it is structurally incapable of seeing any
defect that is stable, deterministic, and not on the title screen. It never had a chance at the
three runtime defects found this sprint, and it never will.

The three share one exact shape, and the ledger's close-out calls it out as the sprint's
cross-cutting finding: **our HLE hands the guest a constant, or a value in the wrong register,
where the guest expects a live one.**

| defect | the constant | consequence | gate saw |
|---|---|---|---|
| `ps2_stubs::rand` (`LibC.cpp:1085`) | `std::rand() & 0x7FFF` over a guest `_rand_next` frozen at 41 | 249 call sites scaling by 2⁻³¹; the disputed field could not exceed 4.0000458 *by construction* against the console's 6.3338 | nothing |
| five soft-double stubs (`sin/cos/tan/fabs/floor`) | read `$f12`, write `$f0`; guest ABI is `uint64 f(uint64 $a0) → $v0` | latent; degenerated to identity at 19 of 22 live sites because `$a0 == $v0` in the delay slot | nothing |
| `socom2_libnetb.cpp:384` `case 0x200: r(3, 0u)` | a constant where the guest reads a changing word | `msSinceNetActivity` never resets → the multiplayer movement scale pins at 0.0 → **the online blocker the project has been hunting for weeks** | nothing |

Three for three. This is the highest-yield defect class in the project and there is no instrument
for it.

**The change.** A tracked, repeatable audit — `tools_py/hle_constants.py` plus
`docs/research/19-hle-liveness.md`:

1. Enumerate every stub bound in `recomp/socom2.toml` (4c established that only bound stubs run —
   `sqrt/ceil/atan/exp` are unbound and never execute, which is itself the kind of fact this audit
   should record once rather than rediscover).
2. For each, classify statically: **returns a literal**, **returns a value derived only from host
   state**, or **returns guest-derived state**. A literal return for an API whose guest caller
   *differences* the result across calls is the signature.
3. For each "returns a literal", record in the note: the guest callers, whether any of them
   compares consecutive returns, and the ABI (`$v0`/`$f0`, argument register) checked against the
   guest routine's own disassembly — 4c's method, which is what made its contract claim
   unarguable.
4. Add a runtime knob `PS2X_HLE_STATS=1` that counts calls and **distinct return values** per stub
   over a run. A bound stub with thousands of calls and one distinct return value is the whole
   defect class, visible in one line. That is the cheap dynamic instrument the gate cannot be.

**Cost.** The static audit: one day, no build, no game run (it reads the ELF and our source).
The `PS2X_HLE_STATS` knob: half a day plus one build and one mission run.

**What it would have caught.** All three, and the third one is the sprint's headline blocker.
`sceInetInterfaceControl(0x200)` returning a constant would have shown as "1 distinct return over
N thousand calls" on any online run since the feature existed. Note the framing this justifies:
**the gate proves no regression; it is not evidence of correctness.** Say that in `LOOP_PROMPT.md`
so no future agent reads "GATE PASS 3/3" as "the game is right".

---

## 5. Retract a committed claim the moment a review overturns it, not at close-out

**What breaks today.** When a review establishes that a committed document is wrong, the
correction is queued for the close-out task. Meanwhile the wrong sentence stays in the file every
fresh session is told to read first, and the sprint may not reach close-out — Sprint 4 has not.

**The evidence.** Three retractions were queued across the day and **all three are still wrong in
the tree right now**:

> **Closed 2026-09-13 (Sprint 4 Task 9a) — at close-out, which is exactly what this section argues
> against.** All three are now retracted in place, plus a fourth (the player actor's address), plus
> the two derived restatements this section did not list: the Sprint 4 spec's own **Task 4** bullet
> (which restated the ground-height frame as fact and sent its own task at the wrong subsystem) and
> `ROADMAP.md` §3's "HANDOFF:99 and STATUS:809 still describe this wrongly". `HANDOFF.md`'s
> "START HERE" now names the sprint in flight and sends the reader to `docs/KNOWN.md` first, and
> `docs/LOOP_PROMPT.md` carries rule 1 as a step: a false committed sentence is corrected in the
> same hour, where it is written. **The elapsed time from "a reviewer proved this false" to "fresh
> sessions stopped reading it" was about a day for the first three and two weeks for the freeze
> description** — the cost this section priced, paid in full.

- `docs/HANDOFF.md:42` "The PCSX2 golden match is the same frozen state" — false; two PCSX2
  instances play a full round and advance to round 2. This sentence sent weeks of work at the
  server.
- `docs/HANDOFF.md:99` "the actor rests 14.7 above it" and `docs/STATUS.md:809` — both were
  camera-eye minus collision-hit all along; the player's feet are correct to 0.008. The Task 4
  reviewer found the clincher *in our own records*: STATUS:809's own numbers reconstruct as
  20.11 = −126.264 − (−146.371).
- Every "frozen at STARTING ROUND 1 OF 11 / waiting for a go" description — including the Sprint 4
  spec's own §1.

And `docs/HANDOFF.md`'s "START HERE" still points a fresh reader at the **Sprint 3** spec and plan
and at an "Open items" list headed by the retracted freeze description. Anything that reads
HANDOFF today — including a cron firing — gets a demonstrably false world model, plus a to-do list
whose top item is a symptom that does not exist.

**The change.** Two rules and one cheap check.

1. **A review finding that a committed sentence is false produces a same-hour edit**, committed on
   the spot by the controller, with the retraction text and the evidence pointer. Close-out then
   *verifies* retractions rather than *performing* them. The cost of the edit is minutes; the cost
   of deferring it is measured in weeks.
2. **"START HERE" names the sprint in flight**, not the last one that closed. Its first line is
   updated when a sprint branch is created, not when it merges.
3. A `tools_py/doc_claims.py` check, run by the close-out and by the preflight of item 3: every
   line in `docs/HANDOFF.md`/`docs/STATUS.md` tagged `<!-- claim: id -->` must have a matching
   entry in a small `docs/claims.md` ledger saying *measured*, *inferred* or *retracted*, with the
   run or note that establishes it. Start with the dozen load-bearing claims only — the sprint
   record shows the damage comes from a handful of sentences quoted as fact, not from the bulk.

**Cost.** Rules 1-2: free. The check: half a day, no build, no game run.

**What it would have caught.** The three retractions would already be in the tree. HANDOFF:42
would have been corrected the hour S0 returned, instead of surviving into a ROADMAP that has to
spend a paragraph undoing it.

---

## 6. Evidence and reports must survive the workspace

**What breaks today.** The durable output of a nine-task sprint lives in gitignored directories
and dies with the checkout.

**The evidence.**

- `.gitignore:16` ignores `/logs/`; `.superpowers/` is likewise untracked. Ledger, close-out:
  "every task report lives in gitignored `.superpowers/sdd/`, so durable findings DIE WITH THE
  WORKSPACE unless Task 9 carries them into STATUS or a research note", followed by a
  hand-assembled minimum-carry list of four items.
- Task 4c's fix round was report-only and the implementer "correctly flagged there was NOTHING TO
  COMMIT ... which is why 4b's report was never committed either". Two full task reports exist
  only in a temp workspace.
- Every run cited as evidence — `logs/parity/gate/s4_mb`, `s4_rand2`, `s4_abi`, `tfix3`,
  `t2b_run1/2` — is under gitignored `logs/`. The comments in `gate.py` and
  `scripts/parity/transition_probe.txt` cite these runs as the calibration for their own
  thresholds; the day `logs/` is cleaned, the thresholds have no provenance.
- **84 shell scripts** under `logs/*.sh` (`run_gate_*.sh`, `run_match_*.sh`,
  `run_task4c_mission_ab.sh`, …) are the project's actual detached-run recipes, and every one is
  gitignored. Each new task re-derives the `Start-Process`/`nohup`/`.done`-marker recipe from a
  paragraph in the plan.
- The one place this was done right shows the cost is small: Task 5 tiled fifteen cited frames into
  tracked `docs/research/assets/18-s0-evidence.png` so the citations outlive a clean.

**The change.**

1. `scripts/archive_sprint.sh <plan-basename>`: copy `progress.md`, every `task-*-report.md` and
   every `review-*.diff` into tracked `docs/sprints/<plan-basename>/`, and every
   `logs/parity/gate/<stamp>/summary.txt` cited in them into the same tree. Run it at **each task
   completion**, not only at close-out — Sprint 4 would otherwise lose everything, since it has not
   reached close-out.
2. Promote the run recipes: `scripts/run_detached.sh <script> <marker>` and
   `scripts/wait_done.sh <marker> [timeout]`, tracked, replacing the 84 one-off copies. This also
   fixes item 8's round-trip waste.
3. When a report cites frames, tile them into `docs/research/assets/` — Task 5's pattern, made the
   default rather than one implementer's initiative.

**Cost.** Half a day. No build, no game run. Mostly a shell script and a convention.

**What it would have caught.** Nothing *fails* here — that is why it sorts below the false-green
items — but it is the difference between a sprint that leaves a permanent record and one that
leaves a controller's memory. Four of Sprint 4's most valuable findings (4c's three live
divergence sites, 4b's rand mechanism, Task 1's furniture-map limits, Task 6's harness liveness
rule) are currently one `rm -rf` from gone.

---

## 7. The lock: no owner identity, no reaper, no fairness, and a race

**What breaks today.** `scripts/loop_lock.sh` records `<owner> <epoch>` and nothing else. Four
distinct defects follow.

**The evidence.**

- **Nothing reaps it.** Ledger: "task4c reported DONE but left the loop lock held (9 min, no
  socom2/pcsx2 process running...). I verified no game process was live and released the orphan,
  since a leaked lock would have starved S1's diagnostic exactly the way S1's runs starved 4c's
  A/B earlier. Worth a close-out note: `release` is currently a courtesy step an agent can skip on
  its way out." The controller had to do a process check by hand because the lock file carries no
  PID.
- **No fairness — and starvation is observed, not theoretical.** `wait` (line 20) is
  `for i in $(seq 1 $max); do take ... || sleep 60; done` — an unordered poll. Whoever polls at the
  right second wins. Ledger, Task 4c: "Its measured A/B attempt was STARVED (task 6 re-took the
  lock every ~10 min for 45 min) and killed during a lock wait before touching anything." A
  planned measurement was lost to the queue discipline, not to a technical problem.
- **Stale-at-45-minutes is a silent double-take.** `STALE_MIN=45`, and `renew` exists but is
  optional and is not in the run recipes. A `build.sh runtime` after a header change is ~10 min; a
  full gate is ~20; an online match is ~12. A chain of two of those without a `renew` crosses 45
  minutes, and the next `take` **succeeds while the game is still running** — the exact condition
  the lock exists to prevent, with no warning on either side.
- **`take` is not atomic.** Lines 11-13 test `[ -f "$LOCK" ]` and then `echo > "$LOCK"` as separate
  operations. Two agents entering within the same instant both see no file and both believe they
  hold it. Low probability, unbounded cost (two builds in one `build-clang` tree, which the plan
  itself calls unsafe), and the fix is one line.

**The change.** Rewrite `loop_lock.sh` around an atomic claim and a liveness record:

1. Claim with `mkdir "$LOCK.d"` (atomic on every filesystem) or `set -o noclobber; : > "$LOCK"`,
   instead of test-then-write.
2. Write `<owner> <epoch> <pid> <purpose>` — the PID of the *shell* that took it. `check` and
   `take` treat a lock whose PID is gone **and** with no `socom2*.exe`/`pcsx2-qt.exe` running as
   reapable, and reap it with a log line. That is exactly the manual procedure the controller
   performed, mechanised.
3. **FIFO.** `wait` appends `<owner> <epoch>` to `logs/.loop_queue` and only claims when it is the
   head; `take` refuses when a queue is non-empty and the caller is not at its head. This is the
   one change that makes a long-running task's measurement survive a chatty neighbour.
4. Keep `STALE_MIN=45` but make a stale break **loud**: the breaker prints the reaped owner and
   appends to `logs/.loop_lock_history`, so a starved task can show it was robbed. And put
   `renew` into `scripts/run_detached.sh` (item 6) so long jobs renew without anyone remembering.

**Cost.** Two hours for the script plus a small test. No build, no game run — a fake-PID unit test
covers the reaper.

**What it would have caught.** The orphaned lock (reaped automatically in seconds rather than by a
controller who happened to look), and Task 4c's starved A/B run, which was a planned measurement
that simply never happened.

---

## 8. The loop prompt is stale, self-contradictory, and its cadence pays for waiting

**What breaks today.** `docs/LOOP_PROMPT.md` is the highest-privilege document in the project — it
fires unattended every 30 minutes with "full authority to use best judgement". It is currently
describing a sprint that ended yesterday.

**The evidence.**

- Line 7: "the most recent sprint is **Sprint 3**", with goals dated 2026-09-11 and a state
  paragraph (162/166 lists, `PS2X_GS_SCALE`) that predates everything Sprint 4 did. Goal 4 says
  "the first-kill acceptance test continues unchanged". A firing right now would pick work against
  Sprint 3's goals, read `HANDOFF.md`'s Sprint-3 "START HERE" (item 5), and commit to `develop`
  while nine tasks of reviewed work sit unmerged on `sprint-4`.
- **The commit trailer contradicts the plan.** `LOOP_PROMPT.md:64` mandates
  `Co-Authored-By: Claude Fable 5.1`; the Sprint 4 plan's commit conventions mandate
  `Co-Authored-By: Claude Opus 5 (1M context)`. Two in-repo instructions, same field, different
  values.
- **Goal 1's scope excludes the validation stack.** "Both are REQUIRED before any commit that
  touches `third_party/ps2recomp/` or `recomp/`." Sprint 4's riskiest commits — Tasks 2, 2b and the
  `movie_blocks.py` work — touched `tools_py/` and `scripts/parity/` and are therefore *exempt from
  running the gate*. The gate is the one thing in the repo whose own change most needs the gate.
- **Round trips spent waiting.** The ledger and the user's own list record agents "returning
  control while merely waiting on detached runs". With a 30-minute cron, a ~20-minute gate and a
  ~10-minute header rebuild, a firing that starts a gate is very likely to be overlapped by the
  next firing, whose step 1 says "do NOT start another ... Wait for the next firing" — i.e. a
  whole cycle is discarded rather than spent on the substantial offline work (decomp reading,
  static VU1 work, research notes) that step 4 explicitly says needs no lock.

**The change.**

1. **Make the sprint pointer generated, not typed.** `LOOP_PROMPT.md` cites
   `docs/CURRENT_SPRINT.md`, a three-line file (`branch`, `spec`, `plan`, `ledger`) written by the
   controller when a sprint branch is created. One place to be stale instead of four
   (LOOP_PROMPT, HANDOFF START HERE, STATUS, ROADMAP).
2. **One trailer, one source.** Delete the trailer text from `LOOP_PROMPT.md` and point at the
   plan's commit conventions.
3. **Widen goal 1:** the gate and `build.sh test` are required before any commit touching
   `third_party/ps2recomp/`, `recomp/`, **`tools_py/`, `scripts/parity/` or `build.sh`**. A change
   to the gate is exactly when a green gate is evidence of something.
4. **Fix the busy-firing branch.** Step 1 currently says "wait for the next firing". Replace with:
   if the lock is held, do offline work from a standing queue (`docs/OFFLINE_QUEUE.md` —
   decomp reading, static audits like item 4, research-note consolidation, test backfill) and
   return with a note. A held lock should cost zero cycles, not one.
5. **Never return control while waiting.** Codify `scripts/wait_done.sh <marker> <timeout>` (item
   6) as the only sanctioned way to wait on a detached run, and say in the prompt: returning to the
   controller while a run is in flight is a defect, not a checkpoint.
6. Reconsider 30 minutes. The natural period is the longest indivisible unit (a full gate, ~20 min,
   or a match, ~12 min). 45 minutes with a lock-aware offline branch would waste fewer firings than
   30 with a bare abort; but the offline branch (4) matters more than the number.

**Cost.** An hour of editing plus the two tracked scripts from item 6. No build, no game run.

**What it would have caught.** Not a wrong answer — a wrong *aim*, which is worse in an unattended
loop: any firing today would start from a Sprint 3 world model and a retracted open-items list.
Plus the recurring round-trip tax on every detached run all sprint.

---

## 9. Promote the run-vs-run baseline compare into the gate

**What breaks today.** The check every implementer actually trusts — "title s00-s19 ≥ 99 against
`s3_head_1x`" — is not in the gate. It is a **code snippet pasted into the plan's handoff notes**
for each implementer to run by hand, with a warning that the distinction confused a reviewer last
sprint. The gate's own numbers score against a fixed internal reference and "read much lower by
design".

**The evidence.** The Sprint 4 plan's handoff notes carry six lines of Python for this, plus: "The
`>= 99` bar is a run-vs-run `compare.score`, never the gate's `summary.txt` numbers (those score
against the gate's internal reference and read much lower by design; this confused a reviewer in
Sprint 3). `compare.score` takes **PIL Images, not paths**". Every task report in the sprint quotes
a run-vs-run figure (Task 1: "99.6-99.9 vs s3_head_1x"; 4b: "99.70-100.00"; 4c: "99.6-100.0"),
each computed by hand. `tools_py/parity/compare.py` already has `report()`, which does all of this
and writes a markdown table with per-screen deltas against a previous report — and the gate does
not call it.

**The change.** `gate.py --baseline logs/parity/gate/<stamp>` scores each `sNN` capture against
the same-named capture of the baseline run and FAILs on any `s00..s19` below a threshold
(default 99.0), printing the per-capture table into `summary.txt`. Record the baseline stamp in
`docs/CURRENT_SPRINT.md` (item 8) so a fresh implementer inherits it instead of being told. Exclude
`s20..s22` explicitly in code, with the reason (attract-movie frames swing 55-100 across runs of
identical binaries — 4b measured this and had to prove it on a third run when `s14` came in at
98.70).

**Cost.** Half a day. No build. Verifiable against stored runs already on disk — **no game run
needed** to develop or test it.

**What it would have caught.** Nothing that was missed — the manual version worked, because the
implementers were conscientious. It sorts here rather than higher for exactly that reason. Its
value is that the next implementer is not relying on a paragraph in a plan, and 4b's honest
handling of a 98.70 becomes the mechanical default rather than a "GOOD BEHAVIOUR WORTH NOTING"
entry in a ledger.

---

## 10. Make the review's actual mechanism explicit, and spend the rounds earlier

**What the reviews caught today** — the record is strong, and the pattern in it is worth naming.
Per-task reviews found: the plan's test-discoverability defect (reproduced, not just asserted);
`movie_blocks.py`'s non-monotonicity and then its arrangement-blindness and then its global
furniture map masking a second screen; the `--vram-diff` ±1 px blindness; `score_transition`'s
trailing-burst quiet pass; Task 4's attribution being one level too high (the blend's `saved` copy
frozen at the console's value); Task 6's *entire named gate being wrong* plus three false sentences
and unanalysed data already sitting on disk; and Task 4c's inherited severity being overstated.

**The mechanism they share, in every single case, is independent re-derivation by a different
route:**

- Task 3's reviewer **reimplemented the C++ scorer in Python** and reproduced the counts on all 15
  dumps, then built a rigid-translation proxy validated to 2 dp.
- Task 1's reviewers **built their own fixtures** — six shapes the implementer had not tried, a
  20-present capture, their own mixed corruption.
- Task 6's reviewer **recomputed `(m^17)^d mod N == m`** for both keypairs and re-decoded all 604
  datagrams.
- Task 4c's reviewer **disassembled all five routines out of the ELF** and checked the delay slot
  of every one of 22 call sites.
- Task 4's reviewer found the clincher by **re-doing STATUS:809's arithmetic**.

Reviews that merely read the diff found the minor items. Reviews that rebuilt the measurement found
every single one of the eight findings that changed a conclusion.

**What the reviews did *not* catch.** Two things, both structural rather than per-task:

- The **cross-cutting** finding (item 4 — three defects, one shape) emerged only in the
  controller's close-out consolidation. No per-task reviewer could have seen it; nothing in the
  process looks across tasks until the sprint ends.
- The **cost**. Task 1 was a one-deleted-line runtime fix, correct in round 0 and never disputed.
  Four fix rounds and ~9 dispatches went into the *check tool*, and the tool exists to prove that
  one line. Item 2's injection rule is the cheap way to buy what those rounds bought.

**The change.**

1. **The review brief requires a "reproduced independently" section**, naming the route taken to
   re-derive the headline number *without reusing the implementer's code or harness*. If the route
   is "I read the diff", the review is not complete. This is already what the good reviews did; it
   is currently emergent, and it is the highest-yield practice in the project.
2. **A mid-sprint cross-task pass**, once, after the first wave completes: one agent reads every
   task report to date and answers a single question — "do any two of these findings have the same
   shape?" Sprint 4's answer was worth the entire remaining sprint, and it arrived at close-out
   instead of at midday.
3. **Prefer an exact oracle to a heuristic one, and say so in the plan.** The sprint's two
   trustworthy checks — `vu1_replay --verify --regs all` and the ABI tests with `$v0` pre-seeded
   `0xDEADBEEFCAFEF00D` — cost zero review rounds, because a bit-comparison has no calibration to
   get wrong. The two expensive ones (`movie_blocks.py`'s agree-fraction/furniture map,
   `--vram-diff`'s by-design buckets) are heuristics, and between them consumed six review rounds.
   When a heuristic is unavoidable, item 2's injection suite is the price of admission.

**Cost.** Free (brief wording) plus ~30 minutes of agent time per sprint for the cross-task pass.

**What it would have caught.** The cross-cutting HLE-constant finding at midday rather than at
close-out — which matters because it is the shape of the online blocker that the sprint's headline
task was hunting for the rest of the day.

---

## 11. Smaller, worth doing, not worth arguing about

- **`gate.py` drops `montage`'s output and `drive.py`'s exit code** (`run_gate`, two
  `subprocess.run` calls with the result discarded). Covered by item 1; listed separately because
  it is two lines.
- **`loop_lock.sh release` always exits 0**, even when the lock was not held (line 17's
  `&& ... || echo` chain). An agent cannot detect that its release was a no-op.
- **`crop_to_content` is applied per-frame to both the live capture and the reference thumbnail**
  (`drive.py:82`, and the `untilref`/`ifref` builders), which makes the comparison's effective zoom
  content-dependent. `scripts/parity/ref_save_prompt_ours.png` genuinely has a black border —
  measured content rows 24-424 of 448, cols 31-613 of 640 — so post-crop it is rescaled ~1.12× in y
  against the band coordinates that `transition_probe.txt`'s header calibrated *before* the crop
  existed ("rows 47..62 of the 160x112 thumbnail are the dialog text only"). The guard still works
  because the dialog dominates the distance (measured dist 0.0 vs 25.7-33.0), but the calibration
  comment is now describing a band that has moved. Re-measure the band, or crop only when the
  client rect is not the expected extent (which item 1 makes available).
- **`tools_py` has no `__init__.py`**, so `python -m unittest discover -s tools_py` raises
  `ImportError`. One empty file, and whole-tree discovery works.

---

## What is *not* worth doing

Stated plainly, because the record makes each of these look attractive and each would cost more
than it returns.

1. **Do not build a console-golden parity gate.** It is the obvious answer to item 4 ("the gate
   only compares us to us") and it is the wrong one. `compare.py:report()` and the PCSX2 golden
   sets already exist and are not wired into the gate — deliberately. A console-golden gate needs a
   PCSX2 run per gate leg, doubling the lock time that item 7 shows is already the project's
   scarcest resource, and it would be *flaky by construction*: boot timing drifts (4b measured a
   45-second lead between two runs of the same binary), the attract movie is out of phase, and the
   RNG stream is now wall-clock-seeded. It would produce exactly the "known intermittency, re-run
   the leg" culture that item 12 below warns about, at maximum cost. The right instrument for
   console divergence is a *targeted* one — the RDRAM/field comparisons Tasks 4, 4b and 6 actually
   used, which found real numbers (`+0x5c` 4.000021 vs 6.3338) in minutes.
2. **Do not make the RNG deterministic for the gate.** It is the natural reaction to 4b's "the RNG
   is NO LONGER REPRODUCIBLE run to run", and the 4b review already measured why it does not
   work: a fixed clock pins the **seed**, not the **stream**, and the same task measured a 45-second
   boot-timing spread that moves the stream anyway. Determinism here buys the appearance of control,
   not control.
3. **Do not add more review rounds.** Task 1 shows the ceiling: four rounds of adversarial review
   on a check tool, each one finding something real, and the last one still parked a documented
   residual. Review found everything it could find; the lever is item 2 (make the property a test,
   once) and item 3 (find the plan defect before dispatch), not more of the thing that already
   works.
4. **Do not chase the ~1-in-5 one-frame transition strip yet.** It is unattributed and it is one
   frame, and the cost of chasing it is game runs under the lock. But see item 12 — the *policy*
   around it needs fixing even though the defect does not.

---

## 12. The flake policy is a slow leak, and it is the item I would fix last but not never

**What breaks today.** The Sprint 4 plan's handoff notes document two transition-gate
intermittencies and instruct: "**Neither is a regression signature.** Re-run the leg
(`--only transition --stamp <s>_t2`); escalate to an A/B against the merge base only if the same
signature repeats." That is a written, sanctioned "re-run until green" — and the sprint record
contains the exact case where it would have been wrong. Task 1's transition gate failed **three
runs running**, was classified as flake-shaped ("N frames examined, need 5", peak 0 — intermittency
(a), verbatim), and turned out to be a *real* harness defect: the burst pinned to a step the dialog
had moved past. It was found by the controller comparing ifref distances, not by the policy, and
the policy would have had the third re-run pass on a short boot and the defect survive.

**The change.** Not the abolition of re-runs — flakes are real. Three cheap constraints:

1. Every re-run is **recorded in `summary.txt`**: attempt number, and both verdicts. A leg that
   needed a re-run is never reported as a clean PASS.
2. A signature that repeats **twice** escalates, not three times — and "escalate" means A/B against
   the merge base, which is what the plan already says; only the count changes.
3. Both known intermittencies get a **distinguishing assertion** rather than a description.
   Intermittency (a) is now *structurally impossible* after Task 2b (a run that fired no
   conditional burst FAILs outright) — so **delete it from the handoff notes**, because a stale
   "known flake" is a licence to ignore a real signal. Intermittency (b), the one-frame residual
   strip, gets a count in `summary.txt` (`residual_strip_frames=N`) so its rate is measured rather
   than remembered as "about 1 in 5".

**Cost.** An hour, no build, no game run (the counting is in `score_transition`, testable against
stored runs).

**What it would have caught.** Task 1's three-run transition failure, escalated after two runs
instead of being investigated because the controller happened to be suspicious.

---

## Summary table

| # | Item | Effort | Build? | Game run? |
|---|---|---|---|---|
| 1 | Preconditions before verdicts (geometry, frame freshness, liveness, exit codes, log scan) | ~0.5 d | no | 1 gate leg to confirm |
| 2 | Defect-injection suites for every scorer + `build.sh test` runs the Python tests | 1 h + 0.5 d | 1 for the vram-diff half | no |
| 3 | Plan preflight: execute the plan's commands, resolve its refs, grep the record, name each bar's blind class | ~20 min/sprint | no | no |
| 4 | Standing HLE constant/ABI audit + `PS2X_HLE_STATS` | 1 d + 0.5 d | 1 for the knob | 1 mission run |
| 5 | Retract on discovery; START HERE names the sprint in flight | free + 0.5 d | no | no |
| 6 | `archive_sprint.sh`, tracked run/wait helpers, tiled evidence assets | ~0.5 d | no | no |
| 7 | Lock: atomic claim, PID + reaper, FIFO queue, loud stale-break, auto-renew | ~2 h | no | no |
| 8 | `CURRENT_SPRINT.md`, one trailer, widened goal 1, offline branch on a busy lock, never return while waiting | ~1 h | no | no |
| 9 | `gate.py --baseline` (run-vs-run ≥ 99 promoted out of the plan text) | ~0.5 d | no | no |
| 10 | Review brief requires independent re-derivation; one mid-sprint cross-task pass; prefer exact oracles | free + 30 min | no | no |
| 11 | Small fixes (exit codes, `release` status, crop band re-measure, `__init__.py`) | ~1 h | no | no |
| 12 | Flake policy: record re-runs, escalate at two, delete the now-impossible known flake | ~1 h | no | no |

Nine of the twelve need neither a build nor a game run, which is the point: the loop's scarcest
resource is lock time, and almost none of what is wrong with the process is competing for it.
