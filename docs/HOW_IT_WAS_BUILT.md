# How it was built

*For a curious stranger. This page explains the method: what a "static recompilation" is in this project, who did
which part of the work, how a change was allowed to become a commit, and which of the project's own mistakes were
kept on the record because they are the part worth reading.*

This is not a pitch. The work was done by AI agents in a loop run by one person, and the page states the weight and
the limits of both halves of that sentence. It holds no live state on purpose — for what is true today, follow the
pointers at the end. Every dated claim below names the commit that proves it.

## What a static recompilation is here

SOCOM II: U.S. Navy SEALs is a PlayStation 2 game from 2003. This project does not emulate it in the usual sense.
The game's own MIPS machine code was translated **once, ahead of time**, into C++ source, which a normal compiler
builds into a native Windows or Linux executable. The recompiler is a fork of PS2Recomp, extended for this one game.

Two things had to happen before that was even possible. The executable on the disc is a loader; the game proper is
two encrypted code overlays beside it, which the loader unwraps with the console's copy-protection library. Running
that cipher offline recovers the overlays without a console (`55f5170`, 2026-09-02). And the function map the
recompiler needs came out of Ghidra wrong in a way that silently corrupts everything — one 46 KB stretch of unrelated
code had been folded into a single function — so it had to be normalised and re-exported before any of the translated
code could be trusted (`ac7de47`, 2026-09-04).

The target shape is the one the Nintendo 64 recompilation projects settled on, and it is the acceptance bar the owner
set (quoted in `docs/LOOP_PROMPT.md`): **the game's logic stays recompiled; the renderer, audio, input and network are
native code written for this project.** What is still emulated is the console around the game — the EE kernel and
scheduler, the DMA controller, the vector units, the IOP services at the RPC boundary.

Nothing from the game ships. The program reads the player's own disc, and refuses a pressing it does not support
rather than half-working.

## Who did what

**The agents** — Claude models driven through Claude Code — wrote most of the code, most of the tests, the parity
harness, the online drivers, the launcher and nearly all of the documents in `docs/`. They also wrote the audits of
their own process, which is why those read the way they do.

**The owner** (Craig, GitHub `Scotho`) owns everything the agents structurally cannot: the idea, the disc, the machine
the work runs on, the money for the hosted server, the decision to make the repository public, and the judgement calls
about what mattered next. Concretely, and this is the part that is easy to undersell:

- **The hands and the ears.** The first time a person played the build rather than a script was 2026-09-16, and that
  one evening set the order of the whole following week: there was no sound at all, and a flat grey patch of hillside
  came and went in the first mission (`7eed518`).
- **The bugs no test was ever going to find.** Escape closed the game instead of pausing it; a PC pad could never
  crouch, because the game reads how hard Triangle is pressed and a pad reports every press as full (`8bf72c5`,
  `c64373a`, both 2026-09-19). On 2026-09-22 the owner's first save on a fresh install failed and the second launch
  worked (`152579a`).
- **Looking at the pictures.** On 2026-09-14 the owner looked at the test frames the gate had been producing for
  three sprints and saw two defects nobody had been looking for, one of which no check had ever flagged (`3220e68`).
- **The things a model cannot do.** Listening on a real speaker. Feeling whether the aim is right. Deciding that
  online consistency comes before anything else. Paying for a server. Publishing.

The honest summary is the owner's own, in `docs/STORY.md`: most of the code was written by AI agents in a loop they
run, and their part was mostly playing it, noticing what was off, and deciding what mattered next. Neither half of
that would have produced this on its own.

## The loop

There is no scheduler and no framework. The loop is a controller session working one page — `docs/LOOP_PROMPT.md` —
one iteration after another, for as long as the owner leaves it running. Seven steps, in order:

1. **Look before you touch.** Other sessions share the working tree; a modified file you did not modify is someone
   else's.
2. **Read the aim** — the first open item in the sprint file, and the ledger of what is already known, before forming
   any hypothesis.
3. **Work in bounded steps:** one hypothesis, one failing test, the change, one build, one run, read the evidence.
   One machine means builds and game runs are serialised behind a lock; while one runs, the session takes work that
   does not need the lock rather than waiting.
4. **Green before the commit** — the suite, and the three-stage gate on the rebuilt executable for anything that
   could change what the game does.
5. **Commit and push** with an explicit pathspec, never `git add -A`. Since 2026-09-21, a proven item goes to `main`
   the day it is proven, on its own pull request, rather than waiting for the sprint to close.
6. **Write it down where it will be read** — the status log, the known/believed ledger, the plan's boxes, a numbered
   ruling for anything decided on the owner's behalf, the owner's queue for anything only they can check.
7. **Then the next item.** Do not wait on the owner; do not do what is the owner's.

Sub-agents take bounded work with an exact brief and a verification command; they never commit a file they were not
given. A standing rule from the owner on 2026-09-17 (`docs/AUDIT-2026-09-17.md` §5) splits the work by model:
mechanical work to one, judgement work to another.

Work is grouped into numbered sprints, each meant to end in something a stranger could notice. A sprint gets a spec,
then a plan with numbered tasks, exact commands, and rulings; specs and plans live in `docs/superpowers/` and are kept
exactly as written, which is why they read like working notes. They are records of what was decided on a day, not
descriptions of the tree today.

## How a change was allowed to become a commit

**A test first, watched failing.** The convention is not "write a test": it is write the test, run it, watch it fail
*for the right reason*, and quote the failing assertion in the report. The reason is written down in
`docs/process-audit.md` — tests written after the change have passed for the wrong reason in this project more than
once.

**The suite.** C++ unit tests, a replay of recorded drawing programs against a committed golden state, and a Python
suite covering the tooling. `docs/DEVELOPING.md` owns the current counts; no other document is allowed to state them,
because four documents once held that number and one of them was right.

**The three-stage parity gate.** One command boots the built game three times — the title screen, the transition into
a mission, and the mission itself — scores each stage against reference captures, and returns PASS or FAIL with an
exit code. The references come from the retail disc running in PCSX2, driven by the same scripts as our build. That
emulator-as-golden-reference is the only outside opinion the project has about whether a frame is right.

**What the gate proves, and what it does not.** It proves the game still looks and behaves the way it did last time
at those three points. It is a regression check, not a correctness check, and it has two structural blind spots that
are written down in `docs/KNOWN.md` §4 rather than hidden:

- **A defect present in every run looks exactly like the reference.** Title and mission scoring compare our runs to
  our own earlier runs.
- **The gate records which binary it ran and almost nothing else** about the inputs that decide the score — the
  reference images, the memory card it boots from, the drive scripts, the environment. Any of those can drift and
  change every score silently.

## What is written down, and why

- **The known/believed ledger.** Four sections: proven, with the artefact; believed, with the experiment that would
  settle it; retracted; and standing hazards. It was created on 2026-09-12 (`2d9f73a`) and already carried six dead
  sentences on its first day. The rule is that a committed sentence found false is corrected the same hour, in place,
  where it was written — a blockquote saying what superseded it, never a quiet delete. Since 2026-09-23 the ledger
  has a public counterpart: each open defect is also a GitHub issue labelled `known-issue`, cited from its row, with
  its evidence and the bar that closes it — the conventions are `docs/GIT_STRATEGY.md` §7 and the sprint-close
  review in `docs/DOC_MAINTENANCE.md` §7.
- **Numbered rulings.** Every default moved and every measurement skipped on the owner's behalf gets a number, a
  reason, and a cost-if-wrong. The counter that hands out the next number is itself checked by a test, because it once
  drifted far enough that an agent obeying it would have collided with sixty-two existing rulings — it offered R179
  from 2026-09-20 to 2026-09-22 while R241 was in use (`docs/DOC_MAINTENANCE.md` §0; `c5c0170`).
- **The owner's queue.** The loop adds anything only the owner can verify to it and moves on rather than blocking.
- **A class per document.** Every perpetuating document has one, deciding what may be written in it, and a test fails
  on a document nobody classified. This page's class forbids it a live number.
- **A cited timeline**, where every dated claim carries its commit hashes and run records, and a test fails if a
  citation stops pointing at something real.

## The things that went wrong, and were kept

These are on the record deliberately. They are also the only part of the method that generalises.

**A check can pass quietly.** The gate's middle stage was supposed to watch the screen go black as the game enters a
mission. It counted black frames from anywhere in the run, boot screens included, so it stayed green whether or not
the game ever reached the fade — and a dialog at boot meant it never did. Six earlier runs, re-read against the fixed
rule, had examined zero frames in the window that counts. All six had passed (`e70af9a`, `148dffa`, 2026-09-10/11).

**A defect in every run is invisible to a comparison against yourself.** SOCOM II rolls dice in 249 places. The
stand-in for the C library's random function returned fifteen bits where the game expects thirty-one, so for the whole
life of the project every roll came up almost the lowest number it could — under a green gate the entire time
(`ede2096`, 2026-09-12).

**A ruling written in prose cannot fail.** A measured decision to build the release at a lower optimisation level was
recorded in three documents and applied in none; the build script went on doing the opposite for six days, and it was
found by asking why an archive was larger than the number those three documents quoted (`210cb78`, 2026-09-20). The
generalisation in `docs/KNOWN.md` §4: a ruling that names a default, a threshold or a flag should get a test that
reads the real artefact and asserts the ruled value.

**An instrument may be opt-in; a failure may not.** When the owner's first save failed, the build they were playing
recorded nothing about it, so the fault could not be explained afterwards. The first attempt at a fix was wrong on its
own terms. The real hole was that a *failed* card command printed nothing at any setting; making every failure print
one line, in every build, found the bug the same night (`152579a`, 2026-09-22).

**A narrative document that holds live state rots.** The roadmap was audited against the tree for the first time on
2026-09-22. Nine of its twenty-five checkable claims still held; two were wrong in a way that would actively misdirect
an agent, including an instruction to go and edit goals in a file that had been rewritten two days earlier to contain
no goals at all (`04a9af1`). The documents that stayed true and the ones that rotted did not differ in care — they
differed in whether anything could fail. The class schema and its test came out of that (`c5c0170`).

**The rule arrived before the practice.** Retract-on-discovery was adopted, and then broken, by the project that
adopted it; one commit that same week is titled "I broke my own rule" (`a1e168b`, 2026-09-13).

**Agents are confidently wrong, in writing.** On 2026-09-14 a cause for a visual defect was published at 13:39 and
refuted at 13:46 by its own author, when the defect survived switching off the thing blamed for it (`5655f5c`).

Every one of these was found by a person, or by an instrument built after the fact — not by the gate that was green
over it. That is the single most useful thing the project learned about itself, and the countermeasures all have the
same shape: **turn a judgement into something that can fail.**

## Where to read the real thing

| Document | What it is |
|---|---|
| `docs/STORY.md` | The timeline, first commit to today, every claim cited |
| `docs/KNOWN.md` | Proven, believed, retracted, and what will bite again. It wins on any disagreement |
| `docs/CURRENT_SPRINT.md` | The live queue |
| `docs/HANDOFF.md` | What a new controller reads first |
| `docs/LOOP_PROMPT.md` | The loop, in full, carrying no state |
| `docs/DEVELOPING.md` | The build, the tests, the knobs, the harness |
| `docs/GIT_STRATEGY.md` | Branches, slices, tags, releases |
| `docs/DOC_MAINTENANCE.md` | The document classes and the checks that hold them |
| `docs/process-audit.md`, `docs/AUDIT-2026-09-17.md` | Two dated audits of this process, warts included |
| `docs/HUMAN_TASKS.md` | What is waiting on the owner |
| [issues labelled `known-issue`](https://github.com/Scotho/socom-unzipped/issues?q=is%3Aissue+is%3Aopen+label%3Aknown-issue) | Every open defect with its evidence and the bar that closes it; the conventions are `docs/GIT_STRATEGY.md` §7 |
