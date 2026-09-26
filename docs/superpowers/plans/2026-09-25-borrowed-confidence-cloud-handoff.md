# Handoff to a cloud research session — "borrowed confidence"

> **NEVER RUN — kept verbatim as the record of what was asked (2026-09-26).** Written 2026-09-25 for a Claude cloud
> session. The session that started on 2026-09-26 committed nothing (the Sprint 13 plan's Log, 03:52Z: HTTP 401 on
> the private inputs, the Linux build stopped at GLFW for want of the workflow's package list, the remote branch
> moved and not deletable — cleaned up by the local controller), and no cloud session is available to the project
> from that day. **Its substance is Sprint 15**, "borrowed confidence", rewritten for the owner's machine:
> `docs/superpowers/specs/2026-09-26-sprint-15-borrowed-confidence-design.md` and
> `docs/superpowers/plans/2026-09-26-sprint-15.md` (Sprint 14 D8). Nothing below is an instruction to anyone; the
> budget, the branch recipe, the private-inputs fetch and the "code half / proof half" split were the cloud's and do
> not apply locally. Class S by the `superpowers/` glob; dated in the filename.

---

**Budget: $250. Three deliverables, each committed and pushed before the next begins, so that whatever the budget
reaches is usable.** You are a Claude cloud session with `github.com/Scotho/socom-unzipped` cloned. The owner is
Craig (GitHub `Scotho`), who is away and has given you full authority to use your judgement inside the rules in §7.
Plans are suggestions; stop rules and the owner-only list are not.

The question this session answers: **which parts of PS2Recomp did we replace or rewrite without the evidence to be
sure of them, who else has solved the same problems, and what would a sprint look like that tries their answers
and proves or disproves each one?** VU1 and audio are the two the owner named first. Be thorough: the register in
Phase 1 decides the scope of Phase 2, not the other way round.

---

## 0. What you are, and what that changes

You run on a fresh Linux VM: no GPU, no Windows, **no disc, no game, no generated code, no loop lock**. Read
`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md` §1 first — it is the precedent for a cloud session on
this project and every rule there about the public repository binds you exactly as it bound that session.

What you can do: read every file in the tree and its history (`git log -- third_party/ps2recomp` is 426 commits of
our divergence); build the runtime library and both suites without the game (`bash scripts/build_linux.sh
--no-runner`, then `bash scripts/build_linux.sh test --no-runner`; the Python suite is `python -m unittest discover
-s tools_py/tests -t .`); use `gh` against `ran-j/PS2Recomp`, its forks and any public repository; fetch reference
code (PCSX2, Play!, DobieStation, OpenGOAL) read-only; run for hours.

What you cannot do: `./build.sh recomp`, `./build.sh runtime` with the game, the parity gate, any game run, any
measurement that reads `recomp/output/` or `game/` (both git-ignored and derived from the disc; the counts in
research/63 §5 came from the local tree and you cannot reproduce them — cite them, do not re-derive them). Every
proposal you make therefore has a **code half** (writable here) and a **proof half** (the local controller's, at a
build window: recomp, runtime, the r0001 gate 3/3 with PINS MATCH). Say which half is which, every time.

**This session changes no code.** It writes research notes, a spec and a plan. The one exception is a throwaway
spike branch if reading alone cannot settle a question (§4 rule 6), never merged.

## 1. First hour

1. `git fetch origin`; read `docs/CURRENT_SPRINT.md`'s `branch:` line — that is the open sprint's branch (it was
   `sprint-13` on 2026-09-25). Create a topic branch off it: `git checkout -b docs/borrowed-confidence
   origin/<open sprint branch>` and `git push -u origin docs/borrowed-confidence`. Docs-only commits start only the
   `secrets` and `docs` workflows. You never push to `main` or to the sprint branch; the controller merges.
2. `bash scripts/install_hooks.sh` — the leak check in pre-commit and pre-push. Never `--no-verify`.
   Then `bash scripts/fetch_private_inputs.sh` — the four git-ignored ELFs (the r0001 and r0004 game images,
   the two demo executables) from the owner's private location, verified against its `SHA256SUMS`; "fetched"
   or "present" four times. If it says the URL is not set, the session started on an environment without the
   two variables: say so in your first note and continue without them — nothing in this handoff requires them,
   they only let you check a fork's claim against the real image (`python -m tools_py.elf_symbols
   game/disc/socom2_game.elf | head -3` proves the read). **They are the owner's own dumps and never enter the
   repository in any form** — not a byte, not a hex dump in a fixture, not a count only they could give.
3. Read, in this order: `docs/HANDOFF.md` §1, §2, §5; `docs/KNOWN.md` all four sections (it wins on any
   disagreement — its vocabulary Proven / Believed / Retracted / Hazard is the vocabulary of your register);
   `docs/DOC_MAINTENANCE.md` §3 and §4 (which document may hold which fact; what the suite checks — a new file
   under `docs/` needs a registry row and a class, and `docs/HANDOFF.md`'s ruling counter is checked mechanically);
   `docs/GIT_STRATEGY.md` §2 and §7; `docs/LOOP_PROMPT.md` (the acceptance bar that has never changed: game logic
   recompiled, renderer/audio/input/network native — the N64-recomp shape).
4. Then the prior art on your own question, so you extend it rather than repeat it:
   - `docs/research/40-upstream-divergence.md` — base `14b1e5c`, upstream since = one squash `75d729c` (#244); §2's
     table of what we changed by subsystem is **the seed inventory of Phase 1**.
   - `docs/research/41-cucumber-fork.md` — the MrCoolTheCucumber fork read for design; the owner's ruling "read for
     design, identify specific pieces, do not merge wholesale" and the bar "an overwhelming case" for a large take.
   - `docs/research/42-upstream-cherry-picks.md` and `63-upstream-triage-2026-09-25.md` — PRs #205–#253 already
     have verdicts (TAKE / ALREADY OURS / NOT OURS / LATER); §2 of 63 is the external-watch table you will extend.
     Do not re-triage a PR with a verdict unless Phase 1 shows the verdict rested on confidence we do not have.
   - `docs/research/04-ps2recomp-internals.md`, `12`, `13`, `15` (VU1: the `0x1b50` dispatcher and its families,
     162/166 programs native keyed by FNV hash, the 4 left to the interpreter), `32-audio-path.md`,
     `36-989snd-decomp-audit.md` (the 989snd model against Ziemas' decompilation; 989DSTRM.IRX is **not**
     decompiled), `20-hle-liveness.md`, `65-throwing-stubs-hle-stats.md`.
   - `docs/audits/2026-09-25-project-audit.md` and its `external.md` beside it; `docs/BACKLOG.md` (the open issues
     with their closing bars — issue #42 the 50 ms music dropouts, #33 the FTOI NaN rule, #32 texture uploads, #59
     the frame-rate bar, #55 the function bounds).
   - `docs/superpowers/specs/2026-09-25-sprint-13-nothing-carried-twice-design.md` and
     `docs/superpowers/plans/2026-09-25-sprint-13.md` — the shape your Phase 3 pair must take.
5. `ls docs/research | sort -n | tail -3` — take the next free number for your first note (65 was the last on
   2026-09-25; another session may have taken 66 by the time you read this). Take the next free ruling number from
   `docs/HANDOFF.md` §2 only if you make a ruling; you probably will not — you propose, the controller rules.

## 2. Phase 1 — the confidence register (deliverable 1, about 30% of the budget)

`docs/research/<n>-confidence-register.md`. One row per feature of PS2Recomp that this project **replaced,
rewrote, or extended past upstream** in `third_party/ps2recomp/` — research/40 §2's table is the starting list;
`git log --stat 8736759..HEAD -- third_party/ps2recomp` is the ground truth. Be thorough: not only VU1 and audio.
At minimum walk: the VU1 interpreter and the native programs (`ps2xRuntime/src/lib/vu/`), the VU0 macro path and
the recompiler's `vu_translator.cpp`, the FPU translator (upstream's is plain IEEE with no PS2 clamping — say what
ours does and what tests prove it), the GS OpenGL backend against the CPU rasteriser oracle, VIF1, the GIF arbiter,
the DMAC (only VIF0/VIF1/GIF channels execute upstream), the EE scheduler and timers, SIF/RPC and `ps2_iop_host`,
each IOP module we wrote or changed (`snd989`, `lgaud`, `eznetcnf`, `dbcman`, `mcserv`), the host mixer
(`snd989_mixer.cpp`), the MPEG/IPU path, the CD/ISO path, the save-state container, memory cards, pads, the
recompiler's function-boundary and jump-table handling.

For each row, in KNOWN's vocabulary:

| Column | What goes in it |
|---|---|
| Subsystem, files | the paths, and the commits since the vendor base (`git log --oneline 8736759..HEAD -- <path>`, counted) |
| What we replaced and why | one or two sentences, citing the research note or commit that made the change |
| How it is validated today | the unit tests by file (`ps2xTest/src/*`), whether the three-stage gate exercises it (title / transition / mission — `tools_py/parity/gate.py`), whether an oracle exists (PCSX2 reference captures; the CPU rasteriser for GL; the interpreter for native VU1 — `vu1_replay`, `vu1_native_tests.cpp`), and what KNOWN §1 proves about it |
| Confidence | **Proven** (a KNOWN §1 row with its artefact), **Believed** (KNOWN §2, or tests that pass without an oracle), **Untested** (no test reaches it), **Hazard** (KNOWN §4) |
| The gap | what would have to be true for the current implementation to be wrong, and what the game would show |
| The experiment that would settle it | in this project's terms: a RED test, a differential run, a gate pin, an audio dip count (`tools_py/parity/audio_dips.py`), a `[vu1-stats]` line — and whether it needs the local tree |
| Open issue | the `#N` if one exists; "candidate" if one should |

Order the rows by **what a player would notice first** if the row is wrong, then by how cheap the experiment is.
The two the owner named (VU1: the interpreter fallback's 4 programs, the FTOI NaN rule #33, cycle modelling vs the
native path; audio: the 989snd RPC model's slots and envelopes, the streamer inferred from the IRX alone, the host
mixer's 50 ms holes #42, `libsd.cpp` untouched, headset `lgaud`) must each get a paragraph, not just a row.

**Every number names its command.** A sentence about the tree cites a path and, where it matters, a line. A claim
you cannot check from here is marked "[local]" and listed in §0 of the note as a question for the controller.

Commit and push the note before starting Phase 2. Its §0 is a "state at last push" block you update on every push.

## 3. Phase 2 — the external survey and the adoption framework (deliverable 2, about 45%)

`docs/research/<n+1>-external-survey.md`. The register's Believed / Untested / Hazard rows define what you are
looking for: **who has solved this same problem, how, and under what licence.**

### 3.1 Sources, all of them

1. **Every open PR on `ran-j/PS2Recomp`.** `gh api 'search/issues?q=repo:ran-j/PS2Recomp+is:pr+is:open'` gave 71
   on 2026-09-25; research/42 and /63 hold verdicts for #205–#253. New ground is everything else, and first among
   it **#254, "Compile whole VU1 programs and run sound IRX modules natively (DQ8 fork)"** (Sinan-Karakaya,
   2026-09-25, draft, 120 files, +20,730/−3,241): a VU pipeline model with compiled regions, whole VU1 programs
   compiled from microcode recorded at run time with **differential tests against the interpreter**, and the game's
   own sound modules (LIBSD, SDRDRV, PCMPLAY) running unmodified on a small emulated IOP with both SPU2 cores under
   `ps2xIOP/src/lle`. It predates #244 and conflicts with it in 20 files; MSVC cannot build it yet. That PR is a
   direct answer to both of the owner's subsystems and deserves the deepest read of the survey: what is the design,
   what would it cost us to take the SPU2 and the LLE IOP given that our 989snd is an HLE model at the RPC boundary,
   and does an LLE IOP running the disc's own `989SND.IRX` and `989DSTRM.IRX` fit the acceptance bar
   ("audio native") or contradict it? Say so either way, with the reasoning.
2. **Upstream `main` past `75d729c`** (`pushed_at` was 2026-09-25 18:49Z, so it has moved) and the branches
   `feature/iop-emulator` and `feature/performance-patch-1`. Closed and merged PRs since our base too.
3. **Every fork with commits of its own.** `gh api repos/ran-j/PS2Recomp/forks --paginate` (137 on 2026-09-25); for
   each, `gh api repos/<owner>/PS2Recomp/compare/ran-j:main...<owner>:<default>` and keep the ones with
   `ahead_by > 0`; read their commit subjects, their README, and any docs. The Cucumber fork (research/41) and the
   DQ8 fork (#254) are known; find the rest. Note which target a specific game — a fork built for one title tells
   you which hardware the title leaned on and how they modelled it.
4. **Every public repository that is a PS2 static recompilation or builds on PS2Recomp**: GitHub search for
   `PS2Recomp`, `ps2xRuntime`, `ps2 static recompilation`, `ps2recomp` in names, topics and READMEs; the upstream
   wiki and Discord where public. Peer methodology from the N64 and Xbox 360 recompilation projects (N64Recomp
   and its game ports, XenonRecomp) counts where the problem is shared: how they validate a native replacement of
   a hardware unit, how they handle interpreter fallbacks, how they test.
5. **Emulators as reference implementations, for the specific gaps only** — not a survey of emulators. PCSX2's VU
   interpreter and microVU for VU semantics we are unsure of (flags, clamping, FTOI on NaN, the pipeline stalls
   the native path skips); PCSX2's SPU2 for ADPCM decode, ADSR envelopes and the 240 Hz tick the 989snd model
   infers; Play! and DobieStation where their code is simpler to read; OpenGOAL's `game/sound/989snd`
   re-implementation, which research/32 already leaned on. For each: the file, the licence of that file's project,
   and whether it is an oracle to test against or a design to borrow.

### 3.2 The adoption framework

For every candidate that maps onto a register row, one entry with:

- **Problem it solves**, tied to the register row by name.
- **How it solves it** — the mechanism in two to five sentences, with the file paths in their tree.
- **Licence, and the consequence.** Ours is GPL-3.0-only (the vendored recompiler; the executable links it), so:
  GPL-3.0 / GPL-3.0-or-later / MIT / BSD / ISC / Zlib can be **taken**, with a row in `THIRD_PARTY_NOTICES.md` and
  the text under `LICENSES/` (`CONTRIBUTING.md` rule 7 and `tools_py/tests/test_third_party_notices.py`); GPL-2.0-only
  cannot be linked; anything with no licence file is design-only. Name the licence file you read.
- **Adoption path**, one of four: **TAKE** (cherry-pick or port the code; say what conflicts with our divergence
  — research/40's rule: anything touching `ps2xIOP/` or the post-#244 `vu/` tree is an idea, not a patch),
  **REIMPLEMENT** (their design, our code, our tests), **BORROW THE IDEA** (a mechanism or a test strategy, no
  code), **LEAVE** (with the reason: the owner's "overwhelming case" bar for large takes, research/41 §7–§9).
- **What would validate adoption**, in our terms: the RED test, the differential run, the gate result, the
  measured number and what it is today. A candidate with no validation you can name is BORROW THE IDEA at best.
- **Landing cost**: does it need a recomp? a gate? does it move the pins? does it touch the release closure?

### 3.3 The agentic glance

Where a fork or project shows signs of being built by AI agents — `CLAUDE.md`, `AGENTS.md`, `.cursorrules`,
Co-Authored-By trailers naming Claude, Codex or Copilot, commit cadence and PR bodies in the agent register —
add a short section comparing **their validation framework to ours**: do they test-first with the failing run
quoted, keep a proven/believed ledger, gate on a reference capture, review with a fresh agent, run differential
tests against an interpreter or oracle (the DQ8 fork's differential tests are the first thing to compare with
`vu1_native_tests.cpp`), and what do they do that we do not? Cursory means one paragraph per project and one table
at the end; it is not a review of their code. Anything worth borrowing goes into the framework as BORROW THE IDEA.

### 3.4 What the note ends with

An extension of research/63 §2's external-watch table (a row per source: what to watch, why, how often); a ranked
shortlist of at most ten candidates for Phase 3, each with its register row, its path and its validation; and the
list of everything you read and set aside, one line each, so nobody re-reads it. Commit and push before Phase 3.

## 4. Phase 3 — the sprint candidate (deliverable 3, about 25%)

A spec and a plan under `docs/superpowers/specs/<date>-sprint-14-candidate-borrowed-confidence-design.md` and
`docs/superpowers/plans/<date>-sprint-14-candidate.md`, in the Sprint 13 pair's shape: goals with a bar each; global
constraints; tasks with Files / Interfaces / Steps with the RED and GREEN commands written out; a **"needs the local
tree"** column (proof half vs code half); owner decisions each with the default the sprint proceeds on; rulings
numbered `S14-R<n>` **as proposals** — the sprint number, its name and its opening are the owner's and the
controller's (`docs/LOOP_PROMPT.md` "When the sprint closes"); you do not touch `docs/CURRENT_SPRINT.md`.

Rules for the tasks:

1. **One approach per task**, from the Phase 2 shortlist, each stating: the register row it would settle, the
   adoption path, the RED test that fails today, the measurement that decides it (and its value today), the stop
   rule (what result ends the task as "tried, not adopted", which is a valid and recorded outcome).
2. **Spikes before commitments.** Where the survey cannot tell whether a design fits, the task is a bounded spike
   with a question and a time box, in the shape of research/14's GS scale spike; its output is a recommendation,
   and a second task, conditional on it, does the work.
3. **Validation is the task, not the afterthought.** Adoption of a VU1 approach is validated by the differential
   run against the interpreter over the recorded dumps and by the gate's pins; adoption of an audio approach by
   `audio_dips.py`'s count on the mission recording and by `audio_parity.py`; a performance approach by the gate's
   `FRAME mean= worst1s=` line (issue #59, informational today). Name the tool for every task. If our validation
   framework cannot measure what a candidate claims, the first task is to extend the framework, and say so.
4. **Open-ended by design.** Each milestone ends with a task "what the tried approaches taught, and the next three
   candidates" with the authority to add tasks from findings (the Sprint 12 cloud handoff §4 is the precedent for
   that authority). The plan's Log is where a session writes what it learned; the register is updated from it.
5. **Communication with the main harness** (the local controller running `docs/LOOP_PROMPT.md`), written into the
   plan's global constraints: proof requests are batched into a named "Proof requests" section, each with the
   exact commands and the expected result, and are run at the owner's build windows — expect a window's turnaround;
   a task is DONE only when its row carries the local result. `LOCAL:` lines mark what only the local tree can
   answer. Anything only the owner can verify goes to `docs/HUMAN_TASKS.md` as a proposal in the plan, not an edit
   to that file. Findings that change a Believed row are proposed as KNOWN edits in the plan; the controller
   applies them. Disagreements with a prior verdict (research/42, /63) are stated with the evidence, never by
   silently changing the note.
6. **If reading cannot settle a question that a two-hour spike can**, do the spike on a branch named
   `spike/<slug>`, build with `--no-runner`, record the result in the note, and delete the branch or leave it
   unmerged with "throwaway" in its last commit subject. The suites are your ring; nothing else is.

## 5. Budget and checkpoints

- Push after every deliverable and at least once per two hours of work; the "state at last push" block in each
  note's §0 says what is done and what is next, so a session that ends mid-phase hands off cleanly.
- At **85% of the budget**, stop research and write Phase 3 from what you have; a shorter plan with every task
  validated beats a longer one without.
- Do not spend budget building what you cannot prove here: no attempts to build the game, no attempts to fetch the
  disc or generated code from anywhere (there is nowhere; they never leave the owner's machine).
- Sub-agents are welcome for bounded reads (one fork each, one PR each, one emulator file each) with an exact brief
  and a verification question; they never commit.

## 6. Owner decisions, each with the default you proceed on

1. **May the survey recommend replacing the 989snd HLE model with an LLE IOP running the disc's own IRX** (the DQ8
   fork's approach)? Default: yes as a candidate, with the acceptance bar ("audio native, the N64-recomp shape")
   argued explicitly for and against; the owner decides the sprint.
2. **May a candidate that changes the generated image's shape (a recompiler change, a naming change, the #206
   function bounds) be in the sprint?** Default: only as a task marked "needs the local tree" with a full recomp and
   `--accept-pins` in its proof half, and behind a ruling proposal.
3. **Is upstreaming part of the sprint?** Default: no new upstream PRs from this session (Sprint 13 U4 drafted them
   and `docs/HUMAN_TASKS.md` O10 owns filing); note what we could give back, per candidate.
4. **Register rows that are Proven today** are excluded from Phase 2 by default; include one only if a source
   contradicts the proof, and say which artefact it contradicts.

## 7. The rules that bind (the repository is public)

- Explicit pathspec on every commit, never `git add -A`; `type(scope): what and why` subjects; the commit trailer
  the environment sets for this session; never `--no-verify`; the leak hooks stay installed.
- Never commit anything under `game/`, `vm/`, `tools/`, `logs/`, `recomp/output*/`, or any byte derived from the
  disc — not a hex dump, not a fixture, not a count you could only get from the generated code.
- A new file under `docs/` needs a `docs/DOC_MAINTENANCE.md` §3 row with a class (research notes are dated
  snapshots — class S; a spec and a plan follow the Sprint 13 pair's rows). Run
  `python -m unittest tools_py.tests.test_doc_maintenance` before every push.
- Nothing about a security mechanism in a tracked file (`SECURITY.md`'s process; S13-R4). If a source you read
  describes an exploit of the game's network code, note "see SECURITY.md" and no more.
- You do not merge, tag, publish, open issues, file upstream PRs, or edit `docs/CURRENT_SPRINT.md`,
  `docs/HANDOFF.md`, `docs/KNOWN.md`, `docs/HUMAN_TASKS.md` or `docs/STATUS.md`. You propose edits to them in the
  plan; the controller applies them. If something in this handoff is wrong about the tree, say so in your first
  note's §0 and proceed on the tree.

Start with §1. Nothing else first.
