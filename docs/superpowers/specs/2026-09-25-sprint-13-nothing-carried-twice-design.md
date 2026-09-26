# Sprint 13 design — "nothing carried twice": the player's first ten minutes, the record made true, the debts the loop pays every night

Date: 2026-09-25 (night, after the Sprint 11 and Sprint 12 closes). Written by the local controller (session
socom-pc-6c) on the owner's instruction of the same night: audit the whole project, compile the master list, clean the
documents, and open and run Sprint 13 without waiting. The audit is `docs/audits/2026-09-25-project-audit.md` (the
master list; six reports beside it); this spec is what the list became; the plan is
`docs/superpowers/plans/2026-09-25-sprint-13.md`.

## Why this is a sprint and not a task

Twelve sprints in, the project's code is in better order than its record and its carry. The audit found 133 distinct
unfinished items in six homes, six of them carried through six sprints, four oldest backlog rows carried since Sprint
6 with nobody ruling on them, and the two claims every live document made on the night ("merged as v0.11.0", "CI
green") both ahead of the facts. The player-visible defects the owner meets first (four menu screens scoring low, the
menus' tile uploads, the loading-screen strips, the mission music's dropouts, the lost saved password) have had
issues since 2026-09-23 and no sprint. Upstream has 27 unevaluated PRs, four of them silent-corruption fixes in paths
SOCOM uses, and one a path-containment fix in a class SECURITY.md puts in scope. FFmpeg ships twelve CVEs behind with
no download hash. None of this is one task; all of it is the same debt — things written down and not paid — and a
sprint whose bar is "nothing leaves it carried twice without a ruling" is the shape that pays it.

## 1. What is established (2026-09-25)

### 1.1 Where the tree stands — **[verified: the Sprint 12 and Sprint 11 CLOSED blocks]**

`main` carries Sprint 11 (`v0.11.0`) and Sprint 12 (`v0.12.0`) once their PRs merge (Sprint 11's #49 was open and
being fixed for a red suite as this was written; Sprint 12's follows it). The generated image is readable (1,771
names from one sidecar); the r0001 gate is 3/3 with PINS MATCH on the renamed tree (`s12_names_gate`, exe
`804dd172…`); r0004 builds, passes its gate and plays a round on our server; the ten upstream picks are in. The
scheduled ladder has not run since 2026-09-23 and is DISABLED; the twenty-map queue last ran 2026-09-16/17.

### 1.2 What the audit measured — **[verified: the six reports]**

- The documents: 69 findings, 45 of them REVISION (a wrong or stale claim in a live document); the four appending
  documents hold 88 % dead weight by bytes; the ruling record has three duplicated numbers and three missing texts.
- The carry: 133 rows; 21 issues cover about twenty of them; the owner's queue is about 25 decisions across six sprints.
- The harness: 155 test files, 2,805 cases, 11.5 minutes locally on the lock's busy list; 28 modules invoked by
  nothing; raw r0001 addresses in five instruments outside the per-revision table; 51 of 58 reference images
  unpinned; the lock has no queue and it cost the two controllers a hand-off on this very night.
- The runtime and build: no orphaned source; CI never compiles the game overrides or the crypto file; 20 stubs bound
  by address whose bodies throw; eight traces read after the original returns (the unwind trap KNOWN §4 names); no
  tracked frame-rate number; FFmpeg unhashed and behind; nine dependencies pinned by mutable tag.
- Outside: upstream quiet 38 days, 27 PRs unevaluated; a SOCOM II browser client appeared 2026-09-21; a public
  exploit names SOCOM II's server domain and nobody has written what our client does with a server-sent payload.
- The stranger: nothing to download (D2 unanswered); the default branch lacks INSTALL and FAQ until the merges; no
  issue carries `help wanted`; twelve issues rest their evidence on the owner's git-ignored logs; about a dozen
  launcher wording defects with no issue.

### 1.3 The rules this sprint keeps — **[the project's standing rules, restated where the audit found them bent]**

- Visible defects above infrastructure (the owner, 2026-09-16); never reorder unasked.
- A failing test first; the gate 3/3 on the rebuilt exe before any runtime change is called done; one build or
  launch at a time under the lock; the owner feels long builds (the owner is away for this sprint's nights).
- A claim about the tree names the artefact; a "merged as vX" names a tag that exists; a suite count is dated and
  lives in DEVELOPING; a number in a note names its command.
- What only the owner can decide gets its default and a ruling; the loop does not wait.
- Nothing that is the owner's is performed: publishing, deploying, spending, flipping permissions, filing anything
  in another project's tracker.

## 2. Goals — eight milestones, each with a bar

### Milestone V — the player's first ten minutes **[A]** — first, because the owner meets it first

- **V1** The four menu screens that score 60–88 (#30): read the archived captures, find what changed, fix the
  scorer or the render, or re-reference with the change written down. Bar: #30 closed by its artefact.
- **V2** The menus' 1 KB tile uploads (#32): a per-upload cost breakdown, then tile batching or skipping unchanged
  tiles, proven by the `[gs-gl stats]` line and the gate. Bar: #32's bar; the stats line in the gate's record.
- **V3** Streamed full-screen images read DBP at packet offset 0x14 (#31): a unit test in `ps2_gs_tests.cpp` drives
  a multi-strip stream; a loading screen compared against the console's. Bar: #31's bar.
- **V4** A tracked frame-rate number: the gate's record carries the mission stage's mean and worst frame time from
  the sampler, pinned as informational first (a refusal comes when three runs agree on the spread); README's fps
  cell dated and sourced. Bar: three gates with the line; a KNOWN §1 row; the new issue for the mission frame rate.
- **V5** The mission music (#42, #28): the quiet-window capture at night (nothing else on the endpoint), the per-minute
  DEVICE count pinned into the audio gate as informational; a route drive that skips the cinematics and makes one
  capture of at least ten minutes scored against PCSX2 (#28's bar); research/36's two documentation items and the
  per-stage sound fixture. Bar: #42 and #28 each closed or carried with a measured reason; the count line in the gate.
- **V6** The saved password on a virgin card (#27): one clean-exit launch then the relaunch, as the bar says. Bar: #27 closed.
- **V7** The online freeze's shape 2 (#34): `waitReadable` bounded by the guest clock, proven by a control round with
  the freeze-fields line. Bar: #34's bar.
- **V8** `PS2X_SOCOM2_SERVER`: a name that does not resolve refuses with a sentence in LAST RUN instead of 127.0.0.1;
  the launcher's wording defects (the blocked-LAUNCH reason, exit 66, voice in one sentence, ABOUT's credits, the
  sample ids, the crouch hint, the render-scale comment). Bar: a launcher test per defect; the FAQ's exit table
  says where each code is reachable from.

### Milestone R — the record made true and small **[A]** — second, because every session reads it first

- **R1** The archive split: the sprint file's Sprint 9–11 records to `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md` <!-- docmaint: future -->
  with a banner, the ledgers kept or pointed, the counter scan extended; HANDOFF §2 reduced to one "now" and §4/§9/§10
  archived; STATUS's Current-state block cut to its heading's promise with a dated entry per close; the two overdue
  audits moved; the 4 specs and 25 closed plans to `docs/archive/sprints-7-12/`. **R268's ceilings** in `docmaint`,
  and the "merged as vX" tag check. Bar: `docmaint` green with the new checks; every cross-reference re-pointed
  (check 6); the sprint file under its ceiling.
- **R2** DEVELOPING rewritten as current truth (its six wrong facts, the `tools_py/` map, the build block, the
  launcher paragraph); README, GIT_STRATEGY, LOOP_PROMPT, PLAYTEST, ROADMAP §6, STORY's closing lines, the archive
  README, SECURITY's hash — every REVISION row of the documents and stranger reports applied or ruled. Bar: the
  audit's D and S REVISION rows each carry a commit or a ruling in the plan's table.
- **R3** The ruling record: a note beside R107/R109/R110's second uses, the missing R114/R116/R124 recorded as
  vacant with the reason, research 43a/43b named in every citation, 35 recorded as never written. Bar: `docmaint`
  reports no duplicate ruling number (a new check) and every `R<n>` ≤ the counter resolves to text or a vacancy note.
- **R4** HUMAN_TASKS reduced to the owner's sitting (audit §3): the superseded items struck with the reason, the
  agentic ones taken by this sprint, one list of decisions with the defaults. Bar: the file under R268's ceiling;
  every remaining item is one the loop cannot take further.
- **R5** KNOWN read in full for the first time since 2026-09-23: settled §2 rows moved to §3 or §1; §4 hazards that
  describe fixed states superseded in place; positional pointers replaced by row names; the Windows-only row corrected.
  Bar: the audit's KNOWN rows applied; `issues audit` OK; the "Last audited" line says this sprint, full.
- **R6** The codex task-allocation audit's six assignments read against the master list and each taken, declined by
  ruling, or already done. Bar: a table in the plan's log.
- **R7** One home for the carry (**R267**): `python -m tools_py.issues backlog` writes `docs/BACKLOG.md` from the open <!-- docmaint: future -->
  issues plus a tracked list of ruled-out rows; `issues.py carry`, `milestone`, and the opened/closed/carried tally;
  the bug-report skill's label list made the tool's. Bar: the generated file in the registry; the next close's §7
  uses the tool for its carry.

### Milestone H — the harness pays its debts **[A]** — third, because it costs every night

- **H1** A docs-only push must not read as a green build in the summary a controller reads. As landed: a
  docs-only push starts no build run (only `secrets` and `docs` run; read a commit with `gh run list --commit`),
  because GitHub reads a run `skipped` only when every job skipped and the `changes` job always runs. Bar: a docs
  push shows no `linux`/`windows` run; a code push shows `success`/`failure` with the build run.
- **H2** The lock: a ticket queue (issue #36's design in the harness report H9), `--wait` in minutes (#35),
  `run_detached --wait`, `ladder_job.sh` taking through `run_detached` (#37), the quiet marker at the common dir, a
  written rollout procedure for a lock script waiters run by offset. Bar: #35, #36, #37 closed by their bars; two
  waiters served in arrival order in a test; one real hand-off between two chains at night.
- **H3** `--accept-pins` writes once, after the run (#45); captures record their `PS2X_*` environment (#38); the 51
  unpinned references pinned or retired, the unused one deleted; the speed-freeze re-measure from the ladder logs (R242).
  Bar: #45 and #38 closed; `pins.json` covers every reference the harness reads.
- **H4** The dead modules: 28 invoked by nothing — each documented as an entry point, retired to `docs/archive/`, or
  deleted (`movie_blocks.py` #46 first); the four `patch_*.py` archived; the two tracked logs removed; the research
  scripts' absolute paths made relative. Bar: #46 closed; `git grep` finds every remaining module invoked or listed.
- **H5** The console-replay GL test (#41): settle whether Q7 made it run; a fresh dump and the case seen RED on a
  planted change, or the case deleted with the row rewritten. Bar: #41 closed.
- **H6** Per-revision literals: `music_state_poll`, `motion_pack_check`, `cam_poll`, `verdict_replay`, `verdict_core`'s
  pointer mode through `guest_addresses`; `env.sh` defaults to the hosted box. Bar: a grep test refuses a new
  r0001 literal outside the table (the KNOWN §4 hazard's own bar).
- **H7** The suite: a lock-free fast subset (`python -m unittest discover -p 'test_*.py' -k fast` or a marker) for
  the cases that need no build product; a dependency manifest that is true; `build.sh` through `python_env.sh`;
  `fix_ghidra_csv` under test; the ~30 log-dependent skips turned into fixtures where `make_gate_fixtures.py` can.
  Bar: the fast subset under two minutes and off the busy list; CI installs from the manifest.

### Milestone C — the code's hygiene and supply chain **[A]**

- **C1** CI compiles `game_overrides_socom2.cpp`, `socom2_crypto.cpp` and the runner's link (a synthetic generated
  stub set is enough). Bar: a syntax error in the overrides file reddens CI.
- **C2** The 20 throwing stubs and HLE leg three (R265): one instrumented run records which are reached; each reached
  stub gets a real body or a KNOWN row with an issue; research/20's flagged rows' consumers listed with a verdict.
  Bar: the run's table in a research note; no throwing stub reachable in a gate.
- **C3** The after-return trap fixed in `socom2_RtNetConfigInit` and the seven traces; `PS2X_PEEK`'s cap warned (#39);
  R256's finding 9; the stale comments (the peek help, the music trace's names, the header, Nellymoser ×2, the DNAS
  `$v0`). Bar: a gate 3/3 and a control round on the rebuilt exe; #39 closed.
- **C4** FTOI's three bare casts and the NaN rule (#33); tail calls in the stats (#40); the nine unregistered stubs
  registered or removed with the reason. Bar: #33 and #40 closed by their bars.
- **C5** The build products out of the source tree: `build.sh` writes the fixed map as a build product like
  `build_revision.sh` step 0; `socom2_r0004.toml` and `socom2_ghidra.toml` untracked or regenerated with a test;
  `socom2.toml`'s header true. Bar: a recomp leaves `git status` clean; the tests.
- **C6** The supply chain: FFmpeg moved to the same channel's 7.1.5 with `URL_HASH`; every FetchContent pin a commit;
  CI's pip and apt pinned; `THIRD_PARTY_NOTICES` says the versions the build uses (nlohmann `v3.11.3`). Bar: a gate
  3/3 on the rebuilt exe with the new FFmpeg; the notices test extended to the Linux `lib/`.
- **C7** The dead configuration: the Vita/Android CMake and sources, `rajdhani_bold.h` and its font, the five
  other-game IOP modules (behind a profile the SOCOM runner does not compile), the nested upstream workflow, the
  duplicated Ghidra script. Bar: the runner builds and gates 3/3; the tree smaller by the numbers the report gives.
- **C8** `ps2HostProfStart` out of the game file; a unit test each for the libpad2 HLE, the msifrpc HLE and the
  crypto (RC4/SHA-1 against known vectors). Bar: the test binary links without stand-ins for those.

### Milestone U — upstream and outside **[A]**

- **U1** research/63: the 27 unevaluated upstream PRs, each with a verdict (take / already ours / not ours / later)
  and the reason; #218, #215, #208 recorded as covered; #217, #222, #223, #224, #216 diffed against our tree and
  taken by ruling where a test shows the defect; an external-watch table (upstream, the Cucumber fork, PSRewired,
  Horizon, PCSX2, the naming tools, the libraries) with the date last read. Bar: the note; any pick gated 3/3.
- **U2** Path containment (#239's class): a test that a translated path with `..` or a symlink cannot leave
  `hostRoot`/`cdRoot`/`mcRoot`; the fix if it fails. Bar: the test green; a SECURITY.md sentence.
- **U3** #253's emitter change (no functions header in every generated file) so a rename rebuilds only the renamed
  files. Bar: a recomp after a one-name change rebuilds one object; the gate 3/3.
- **U4** Drafts for the owner: the three #244 patches as upstream issues, a note per KEEP pick, the two BinExport
  R5900 defects — written, not filed. Bar: the drafts under `docs/research/assets/` and an O10 line.
- **U5** Memdusa: what our client does with a server-sent payload of that shape, read from the recompiled handler and
  the runtime's network path; a private note first (the finding is bounded before it is public), then the KNOWN row
  and, if the class is live, an issue and a fix. Bar: the note; a decision recorded under SECURITY.md's process.

### Milestone S — the stranger **[A]**

- **S1** README, INSTALL, FAQ and PLAYTEST true to the build: the status paragraph, the fps cell, "two players", the
  download's blocker, the GAME VERSION row, the Linux dependency list, the exit-code reachability; PLAYTEST rewritten
  for the current build. Bar: the audit's S rows applied.
- **S2** The launcher's wording defects (V8's list) with a launcher test each. Bar: `launcher_tests` green.
- **S3** The tracker for a contributor: `help wanted` on the issues a disc-less contributor can take (#39, #40, #46,
  #48 and this sprint's new ones); the twelve log-based evidences replaced by fixtures or by a sentence naming what
  the owner's machine holds; the four Dependabot PRs rebased and merged or closed with a reason; the lock issues
  marked internal. Bar: every open issue's evidence readable from a clone.
- **S4** The story's five missing days written from the record (O9's default: keep). Bar: STORY's citation checker green.
- **S5** The Linux notices: the ~76 distro libraries in `lib/` with their licences, and the notices test extended.
  Bar: the test covers the tarball.

### Milestone N — the naming programme's follow-ups **[A]**

- **N1** The runtime's own knowledge into the sidecar: the ~30 hook targets and address-table fields as a `Pass=hand`
  proposals file from the code's names; research/50's four offsets named beside their numbers; `hostprof_diff.py`
  counting by the `_0x` suffix. Bar: the applier accepts the file; a recomp with 0 extents moved; the gate 3/3.
- **N2** #48 (`--out` and the sidecar; the unresolved-names line a warning `build.sh` surfaces); the header wording;
  the r0004 build with its own sidecar and its gate (Sprint 12's item 5), at the first quiet window. Bar: #48 closed;
  `s13_names_r0004_gate` 3/3.
- **N3** The cloud's list, if a cloud session is opened for it: the 518 loose rows' second lever, the r0004 7c file
  derived, the matcher's MMIO guard, research/45's corrections, 7c's anchor count re-run, the hand candidates, toml
  hygiene, csv row extents, the unhandled-instruction census. Bar: each a task in that session's plan with a proof
  row here; else `docs/BACKLOG.md`. <!-- docmaint: future -->
- **N4** BinExport `main` against Ghidra 12.1.3 (retiring the second Ghidra); DEVELOPING pins 12.1.3. Bar: research/49's
  numbers reproduced on one install.

### Milestone O — online and the box **[A]**

- **O1** One ladder run and one mixed-match leg on the renamed tree at night; the ladder's row on the site. Bar:
  `docs/LADDER.md` gains a row on exe `804dd172…` or its successor; the mixed leg's verdict.
- **O2** The chat step (#26) and R221's talk-slot peek in one two-instance round at night. Bar: #26's bar; the peek's
  bytes recorded in KNOWN.
- **O3** The box in the repository: the backup/health/pull scripts tracked under `server/` with their secrets left
  out; the build id on `/api/stats`; the deployed commit recorded; `server/README` true; the chat clamp marked
  `LOCAL FIX`; Horizon's base commit and PR #35 recorded. Bar: `server/README` names the running commit; the scripts
  under test where they can be.

## 3. Decisions for the owner — each with the default the sprint proceeds on

The audit's §3 is the list (O1–O13). This sprint takes none of them as blocking. Two are its own:

| # | decision | default | ruling |
|---|---|---|---|
| D1 | The sprint's order: milestones V, R, H, C, U, S, N, O as above | as above (visible first, then the record, then what pays every night) | S13-R1 |
| D2 | Lock-bound runs on the owner's nights: the music capture, the ladder, the mixed leg, the chat round, the throwing-stub run, the gates of C3/C6/C7/U3 | run, one at a time, the owner away; nothing that needs their hands | S13-R2 |

## 4. The acceptance bar of the sprint

1. **Nothing leaves this sprint carried twice without a ruling:** every open issue at the close is closed by its
   artefact, or carried once with a comment, or is the owner's question by name; `docs/BACKLOG.md` exists and is <!-- docmaint: future -->
   generated; the four oldest rows have R265.
2. **CI green with the overrides compiled**, and a docs-only push starts no build run (only `secrets` and `docs`).
3. **The record under its ceilings:** `docmaint` green with R268's checks; the sprint file, HANDOFF §2, STATUS's
   state block and HUMAN_TASKS under the ceilings set at R1; every REVISION row of the audit applied or ruled.
4. **The player's first ten minutes measured:** #30, #32, #31, #27 closed by their bars; a frame-time line and a
   DEVICE-dip count in the gate's record; #42 and #28 closed or carried with a measured reason.
5. **The gate 3/3 with PINS MATCH on the sprint's final exe, one ladder run and one mixed leg on it**, the lock's
   queue proven by one real hand-off.

## 5. What this does not do

Voice (hearing the other player; a sprint of its own when the owner names it). The Vulkan, HUD and JIT LEAVE items of
research/41. The soft-double chain and the gameplay-state probe (R265). Anything that is the owner's in §3. A public
download (D2). The community preset (Goal F). A second cloud session (N3 runs only if one is opened).

## 6. Pointers

`docs/audits/2026-09-25-project-audit.md` and its six reports; `docs/superpowers/plans/2026-09-25-sprint-13.md`;
`docs/CURRENT_SPRINT.md` (the header and the Sprint 12 and 11 CLOSED blocks); `docs/KNOWN.md`; `docs/HUMAN_TASKS.md`;
the issues `#25`–`#48` and this sprint's milestone on GitHub.
