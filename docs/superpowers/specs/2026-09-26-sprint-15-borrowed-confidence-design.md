# Sprint 15 design — "borrowed confidence": what we replaced in PS2Recomp without the evidence, who else solved it, and the trials that settle each one

Date: 2026-09-26 (host clock), proposed while Sprint 13 is open and Sprint 14 is proposed. **Opens at Sprint 14's
close** (Sprint 14 decision D8), off `main` at the Sprint 14 merge; until then this is a proposal and nothing here
changes an open sprint. The plan is `docs/superpowers/plans/2026-09-26-sprint-15.md`. The origin is the cloud
research handoff of 2026-09-25, kept verbatim with a banner at
`docs/superpowers/plans/2026-09-25-borrowed-confidence-cloud-handoff.md`: it never ran (the session that started on
2026-09-26 committed nothing) and no cloud session is available to the project from that day, so this pair rewrites
it for the owner's machine — the same question, the same three deliverables, the same owner defaults, the trials
added as the sprint's second half instead of a "candidate" for someone else to open.

## Why this is a sprint and not a task

The question: **which parts of PS2Recomp did we replace, rewrite or extend without the evidence to be sure of them,
who else has solved the same problems, and what happens when we try their answers and prove or disprove each one?**
The owner named VU1 and audio first.

The divergence is 425 commits on the vendored recompiler and runtime since the vendor base
(`git log --oneline 8736759..HEAD -- third_party/ps2recomp | wc -l`, 2026-09-26, on `sprint-13`). What validates
those commits today is the three-stage gate against our own earlier captures, the interpreter as the oracle for the
native VU1 programs, the CPU rasteriser as the oracle for the GL backend, and unit tests that in many subsystems have
no oracle at all. The 2026-09-26 structure review named this the project's thinnest architecture (F3, F9: "a
regression fence against ourselves"); the 2026-09-12 audit called the same thing "the highest-yield defect class in
the project". Two visible defects sit on the two named subsystems: the 50 ms holes in the mission music (#42) and the
music that degrades with time in a mission (#28); the VU1 path keeps four programs on the interpreter and a FTOI
NaN rule that Sprint 13 C4 recorded as "the Cucumber fork's rule, not hardware-verified" (#33 closed on the tests,
so the rule is Believed, not Proven); the macro-mode flag latency is open (#47).

A task could survey one fork. A sprint is needed because the register decides the scope — every replaced subsystem
gets a row before any is judged — and because each borrowed answer must be tried under a stop rule and its result
recorded either way. "Tried, not adopted" is a valid outcome and is written down.

## 1. What is established (2026-09-26) — **[verified: the tree and the notes named]**

### 1.1 The divergence — the seed inventory

`docs/research/40-upstream-divergence.md` §2 is the table of what we changed by subsystem against base `14b1e5c`,
with upstream since it one squash (`75d729c`, PR #244). `docs/research/41-cucumber-fork.md` read the
MrCoolTheCucumber fork for design under the owner's ruling "read for design, identify specific pieces, do not merge
wholesale" and set the bar "an overwhelming case" for a large take. `docs/research/42-upstream-cherry-picks.md` and
`docs/research/63-upstream-triage-2026-09-25.md` hold verdicts (TAKE / ALREADY OURS / NOT OURS / LATER) for PRs
#205–#253, and 63 §2 is the external-watch table this sprint extends. The walk list the register must cover at
minimum: the VU1 interpreter and the native programs (`third_party/ps2recomp/ps2xRuntime/src/lib/vu`), the VU0
macro path and the recompiler's VU translator, the FPU translator (upstream's is plain IEEE with no PS2 clamping),
the GS OpenGL backend against the CPU rasteriser, VIF1, the GIF arbiter, the DMAC, the EE scheduler and timers,
SIF/RPC and the IOP host, each IOP module we wrote or changed (`snd989`, `lgaud`, `eznetcnf`, `dbcman`, `mcserv`),
the host mixer, the MPEG/IPU path, the CD/ISO path, the save-state container, memory cards, pads, and the
recompiler's function-boundary and jump-table handling.

### 1.2 The validation that exists

- The gate: three stages (title, transition, mission) scored against pinned references, `tools_py/parity/gate.py`,
  3/3 with PINS MATCH as the bar; the last on 2026-09-26 (`s13_merged_gate`, the Sprint 13 plan's Log).
- VU1: `vu1_replay` and `third_party/ps2recomp/ps2xTest/src/vu1_native_tests.cpp` run the native programs against
  the interpreter over recorded dumps; `ps2_vu1_tests.cpp` beside it; 162 of 166 programs native, keyed by hash,
  four on the interpreter (`docs/research/12-vu1-entry0-ui-path.md`, `13-vu1-family-b-world-objects.md`,
  `15-vu1-fourth-family.md`).
- Audio: `tools_py/parity/audio_dips.py` (the dip count on a recording) and `tools_py/parity/audio_parity.py`
  (31/48 since 2026-09-20, unchanged); the 989snd model against Ziemas' decompilation in
  `docs/research/36-989snd-decomp-audit.md` (989DSTRM.IRX is not decompiled: the streamer is inferred from the IRX
  alone); the path in `docs/research/32-audio-path.md`.
- The record: `docs/KNOWN.md`'s vocabulary — Proven (§1, with an artefact), Believed (§2), Retracted (§3), Hazard
  (§4, or the hazards file once Sprint 14 I5 lands) — is the register's vocabulary, and KNOWN wins on any
  disagreement.
- **Assumed from Sprint 14** (this sprint opens at its close): the held-out leg the agents never see (E2), gate
  freshness (E4), the recompiler re-derivation in CI (E3), the merged chain as the gate unit with eviction (W2), the
  WIP cap (W1), the guards (G1–G5), the skills (I2) and the generated pages (D1, D3, S1, M1). Every proof in this
  sprint runs through that chain. If Sprint 14 closes without one of these, the plan's Task 0 says which and the
  trials' bars fall back to the three-stage gate alone, recorded as such.

### 1.3 What running locally changes, against the handoff

The handoff was written for a machine with no disc, no generated code and no lock, so every proposal had a "code
half" and a "proof half", every claim about the tree was marked "[local]", the ELFs came through a credential, and
the record's documents were off-limits. None of that holds here:

- The register cites the generated code and the recordings directly; the "[local]" column is gone.
- The differential tools run here: the VU1 replay over the recorded dumps and the dip counter over the existing
  mission recordings are lock-free reads of `logs/`; a new capture is a lock-bound step at a quiet window.
- A proposal has lock-free steps and lock-bound steps inside one task, in the shape every sprint uses, and the
  lock-bound ones batch through the merged chain (Sprint 14 W2) rather than a "Proof requests" section.
- Edits to KNOWN, HUMAN_TASKS and the sprint file are the controller's, made under review, as in any sprint.
- Time boxes replace the dollar budget (D5). The branch, hook and fetch recipe becomes the `agent-worktree` skill.

### 1.4 The two subsystems the owner named

**VU1.** Four programs still run on the interpreter; the native path skips the pipeline stalls the interpreter
models, and no cycle model exists on it; the FTOI NaN rule is a fork's rule under a unit test, not a hardware trace;
#47's flag latency is open. The interpreter is the oracle for the native programs and nothing is the oracle for the
interpreter but PCSX2 and hardware. The gap: a native program that diverges from the interpreter on an input the
recorded dumps never carried, or an interpreter that diverges from hardware on flags or clamping; what the game would
show is a wrong vertex, a wrong clip, a flicker on one model family.

**Audio.** The 989snd model is an HLE at the RPC boundary (slots, envelopes, the 240 Hz tick inferred), the
streamer is inferred from the IRX alone, the host mixer loses about 50 ms per minute somewhere between render and
the device (#42), and the music degrades over a long mission (#28); `libsd` is untouched and the headset module
(`lgaud`) is ours. The gap: an envelope or a stream cadence the model gets wrong by design rather than by a bug;
what the game shows is the two open issues. Upstream PR #254 (the DQ8 fork) answers both subsystems at once with a
whole-program VU1 compiler tested differentially against the interpreter and the disc's own sound modules on an LLE
IOP with both SPU2 cores — the handoff's reading of 2026-09-25, to be re-read as the PR stands (Sprint 14 X1 if it
ran, else this sprint's X2).

### 1.5 The rules this sprint keeps

- A failing test first, unittest only; RED and GREEN pasted; a trial's measurement named before the trial runs, with
  its value today.
- KNOWN wins; a finding that moves a Believed row moves it in KNOWN with its artefact, in the same commit as the
  evidence, never by a silent edit of a research note.
- Commit with an explicit pathspec; the leak check in the hooks; never `--no-verify`; nothing under `game/`, `vm/`,
  `tools/`, `logs/`, `recomp/output*/` or any byte derived from the disc enters the tree — not a hex dump, not a
  fixture, and a count from the generated code is cited with its command, never pasted as data.
- Nothing about a security mechanism in a tracked file (`SECURITY.md`'s process; S13-R4).
- What only the owner can decide gets its default and a ruling from the global counter (Sprint 14 D5: no
  `S15-R` names); the loop does not wait. Nothing that is the owner's is performed.
- No upstream PR is filed from this sprint (D3); what we could give back is noted per candidate for row O10.

## 2. Goals — five milestones, each with a bar

### Milestone R — the register **[A]** — first, because it decides the scope of everything after it

- **R1** `docs/research/<n>-confidence-register.md` (the next free number; class S by the glob): one row per feature
  of PS2Recomp we replaced, rewrote or extended, from research/40 §2 and `git log --stat 8736759..HEAD --
  third_party/ps2recomp`, over the whole walk list of §1.1. Columns: subsystem and files (with the commit count since
  the base, counted); what we replaced and why (the note or commit); how it is validated today (the unit tests by
  file, whether the gate exercises it, whether an oracle exists, what KNOWN §1 proves); confidence in KNOWN's
  vocabulary — Proven, Believed, Untested, Hazard; the gap (what would have to be true for ours to be wrong, and what
  the game would show); the experiment that would settle it (a RED test, a differential run, a gate pin, a dip count,
  a `[vu1-stats]` line — lock-free or lock-bound); the open issue or "candidate". Ordered by what a player would
  notice first if the row is wrong, then by how cheap the experiment is. Bar: every number names its command; every
  confidence cites the KNOWN row or the test file; a fresh reviewer finds no replaced subsystem without a row.
- **R2** The VU1 paragraph: the four interpreter programs by hash and what each draws; the native path's skipped
  stalls and the cycle question; the FTOI NaN rule's provenance and the one hardware trace or cited source that
  would settle it; #47; the replay's coverage of the recorded dumps (`vu1_replay` run here, its counts). Bar: each
  claim with its artefact; the row's experiment named with today's number.
- **R3** The audio paragraph: the RPC model's slots and envelopes against research/36; the streamer's inference;
  the mixer's 50 ms holes with the dip counter run over the existing mission recordings (`audio_dips.py`, counts and
  the recording named); #28; `libsd`; `lgaud`. Bar: as R2.

### Milestone X — the survey and the adoption framework **[A]** — second, from the register's non-Proven rows

- **X1** The sources: Sprint 14 X1's external sweep if it ran (its note is the starting point and is not repeated),
  else the sweep itself — upstream `main` past `75d729c` and its branches, the closed and merged PRs since the base,
  every fork with commits of its own (`gh api repos/ran-j/PS2Recomp/forks --paginate`, `compare` per fork,
  `ahead_by > 0`), every public PS2 static recompilation, the peer methodology of N64Recomp's ports and XenonRecomp.
  A PR with a verdict in research/42 or 63 is not re-triaged unless the register shows the verdict rested on
  confidence we do not have, and then the disagreement is stated with the evidence. Bar: research/63 §2's watch
  table extended by a row per source; everything read and set aside listed one line each.
- **X2** Upstream PR #254 read in depth as it stands: the design, the differential tests against the interpreter
  (compared with `vu1_native_tests.cpp` first), the LLE IOP and the SPU2 cores, the twenty-file conflict with #244,
  whether MSVC builds it now, and the question the owner's bar poses — does an LLE IOP running the disc's own
  `989SND.IRX` and `989DSTRM.IRX` fit "audio native, the N64-recomp shape" or contradict it — argued explicitly
  for and against (D1). Bar: the section answers the question either way with the reasoning.
- **X3** Emulators as reference implementations for the specific gaps only: PCSX2's VU interpreter and microVU for
  the semantics the register marks unsure (flags, clamping, FTOI on NaN, the stalls); PCSX2's SPU2 for ADPCM, ADSR
  and the 240 Hz tick; Play! and DobieStation where simpler to read; OpenGOAL's 989snd re-implementation. For each:
  the file, the licence of that file's project (the licence file named), and whether it is an oracle to test
  against or a design to borrow. Bar: no emulator surveyed beyond a register row's gap.
- **X4** The adoption framework, one entry per candidate that maps onto a register row: the problem (the row by
  name); the mechanism in two to five sentences with the paths in their tree; the licence and its consequence
  (ours is GPL-3.0-only — GPL-3.0, GPL-3.0-or-later, MIT, BSD, ISC and Zlib can be taken with a row in
  `THIRD_PARTY_NOTICES.md` and the text under `LICENSES/`; GPL-2.0-only cannot be linked; no licence file means
  design-only); the path — TAKE, REIMPLEMENT, BORROW THE IDEA, LEAVE — with research/40's rule that anything
  touching the IOP tree or the post-#244 VU tree is an idea, not a patch, and research/41's "overwhelming case" bar
  for a large take (D6); what would validate adoption in our terms with the number today (no validation nameable
  means BORROW THE IDEA at best); the landing cost (a recomp, a gate, the pins, the release closure). The agentic
  glance: one paragraph per project built by agents on their validation framework against ours, one table at the
  end, anything worth borrowing filed as BORROW THE IDEA. The note ends with a ranked shortlist of at most ten
  candidates, each with its register row, its path and its validation. Bar: the shortlist; every entry's licence
  file named; docmaint green.

### Milestone T — the trials **[A] then [L]** — the sprint's second half, written from the shortlist

- **T0** The checkpoint: the trial tasks written into the plan from the shortlist, one approach per task, each
  stating the register row it would settle, the adoption path, the RED test that fails today, the measurement that
  decides it and its value today, the tool that measures it, the stop rule (what result ends it as "tried, not
  adopted"), and its lock-bound steps. Spikes before commitments: where the survey cannot tell whether a design fits,
  the task is a bounded spike with a question and a time box in the shape of
  `docs/research/14-gs-render-target-scale-spike.md`, its output a recommendation, and a second task conditional on
  it. The two named subsystems' trials come first (D7). Bar: the plan's table carries the tasks; no trial without a
  measurement and a stop rule.
- **T<n>** Each trial in its own agent worktree: RED first; the code; the suites; review by a fresh agent; the merged
  chain at a quiet window with the gate 3/3, the held-out leg, and the trial's own measurement; the outcome recorded
  as ADOPTED (the KNOWN row moves, the register row moves) or TRIED, NOT ADOPTED (the reason and the number, kept in
  the register and the Log; the branch left unmerged with "throwaway" in its last subject, or reverted). A VU1
  trial is validated by the replay against the interpreter over the recorded dumps and by the gate's pins; an
  audio trial by the dip count on the mission recording and by `audio_parity.py`; a performance trial by the gate's
  `FRAME mean= worst1s=` line (#59). Bar: every trial ends in one of the two outcomes with its number.

### Milestone V — the framework extended where a claim cannot be measured **[A]**

- **V<n>** Where a candidate's claim has no measurement in our tools, the first task is to build the measurement:
  a scorer, a replay leg, a dip counter over a new capture, a differential job in the suite — under a planted
  case, in the docmaint pattern. Bar: the measurement reads a known number on a known input before any trial uses it.

### Milestone L — the lessons **[A]** — at the end of every milestone

- **L<n>** "What the tried approaches taught, and the next three candidates": the register updated from the Log;
  KNOWN rows moved with their artefacts; the shortlist re-ranked; new trial tasks added with the authority the
  Sprint 12 cloud handoff §4 set as precedent. Bar: the register's confidence column matches KNOWN at every close of
  a milestone.

## 3. Decisions for the owner — each with the default the sprint proceeds on

Rulings are issued at the open from the global counter; none is numbered here.

| # | decision | default |
|---|---|---|
| D1 | May the survey recommend replacing the 989snd HLE model with an LLE IOP running the disc's own IRX (the DQ8 fork's approach)? | yes, as a candidate, with the acceptance bar ("audio native, the N64-recomp shape") argued for and against; the owner decides whether it becomes a trial |
| D2 | May a candidate that changes the generated image's shape (a recompiler change, a naming change, the function bounds of #55) be a trial? | only with a full recomp, the recompiler re-derivation green, `--accept-pins` after a green run, and a ruling from the global counter |
| D3 | Is upstreaming part of the sprint? | no new upstream PRs; what we could give back is noted per candidate for row O10 |
| D4 | Register rows that are Proven today are excluded from the survey | excluded, unless a source contradicts the proof, and then the artefact it contradicts is named |
| D5 | Time boxes in place of the handoff's dollar budget | the register one loop day, the survey two, T0 on the third; a phase past its box hands the rows done to the next; the sprint closes when the shortlist is exhausted or on the seventh day, whichever is first |
| D6 | The "overwhelming case" bar for a large take (research/41) | stands; a TAKE over about five hundred lines needs a ruling |
| D7 | The order of trials | the two named subsystems first (VU1, audio), then the register's order |

## 4. The acceptance bar of the sprint

1. **The register exists**, with a row for every replaced subsystem in §1.1's walk list, the two named subsystems
   paragraphed, every number with its command, every confidence with its artefact.
2. **The survey exists**, with the watch table extended, #254 answered either way, the licences named, the
   shortlist of at most ten with a validation each, and the set-aside list.
3. **At least three trials run to a recorded outcome** — ADOPTED with the KNOWN row moved, or TRIED, NOT ADOPTED
   with the number — the first two on the named subsystems; every trial through the merged chain with the gate 3/3
   and the held-out leg green.
4. **No Believed row a trial touched is left Believed:** each moved to Proven or Retracted in KNOWN with its
   artefact, in the commit that carried the evidence.
5. **No regression:** the gate 3/3 with PINS MATCH and the held-out leg on the sprint's final exe; audio parity not
   below 31/48; the dip count on the mission recording not above the register's number.
6. **The record's ceilings hold**; the register and the survey are class S snapshots and not read-first documents.

## 5. What this does not do

A wholesale merge of any fork (research/41's ruling stands). Any upstream filing (O10). The naming programme's
follow-ups (the backlog keeps them: #55, #57, #58 and the rows once marked cloud-able). Voice, the community preset,
a public download, anything in HUMAN_TASKS that is the owner's. A trial that fails its stop rule is recorded and
stopped, not extended.

## 6. Pointers

`docs/superpowers/plans/2026-09-26-sprint-15.md` (the plan); `docs/superpowers/plans/2026-09-25-borrowed-confidence-cloud-handoff.md`
(the origin, never run); `docs/superpowers/specs/2026-09-26-sprint-14-guards-not-sentences-design.md` (§1.5, D8,
D9, X1); `docs/research/40-upstream-divergence.md`, `41-cucumber-fork.md`, `42-upstream-cherry-picks.md`,
`63-upstream-triage-2026-09-25.md`; `docs/research/04-ps2recomp-internals.md`, `12`, `13`, `15`, `32`, `36`, `20`,
`65`; `docs/audits/2026-09-25-project-audit.md` and `docs/audits/2026-09-25-project-audit/external.md`;
`docs/audits/2026-09-26-autonomy-structure-review.md` (F3, F9, option E); `docs/BACKLOG.md`; `docs/KNOWN.md`.
