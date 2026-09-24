# Sprint 12, "the readable image" — handoff to the cloud controller

Date: 2026-09-24 (evening). Written by the peer session socom-pc-6c on the owner's instruction, for the Claude
cloud session that will **own Sprint 12**: flesh it out (spec, then plan), run a wide research wave with the
authority to add tasks from what it finds, then execute the sprint autonomously. The local Sprint 11 controller
keeps Sprint 11 and the machine. The owner's words: *"provide a handoff that gets the env to fully flesh out
Sprint 12, do a large wave of independent research on the subject with the authority to spin up new tasks based
on findings, and then proceed autonomously through the sprint"*, and: consider the active work on the local
machine and how merge and check-in procedure changes because of it.

Ruling R263 (`docs/superpowers/plans/2026-09-23-sprint-11.md`, "Rulings made on the owner's behalf") defines the
sprint: *the naming programme is Sprint 12, "the readable image": a readable generated image, for hooks, HLE, the
address table and voice chat; its own tooling and its own review loops; it opens with the rename pass as its first
task, so the whole of Sprint 12's gates run on the renamed tree.* R257–R262 are its seed rulings; read them.

---

## 1. Where you are, and what that changes

> **Ratified by the local controller (session socom-pc-56), 2026-09-24 evening, with these amendments — read them as part of every section they touch:**
> 1. **Task 7c is yours, not the local controller's** (R263 moved the naming programme to Sprint 12; 7b has merged). The file restriction on `tools_py/ghidra_symbol_match.py` is lifted: that module and `tools_py/symbol_levers.py` are yours on `sprint-12`.
> 2. **Research numbers:** you take 46 onward; the local controller takes none for Sprint 11's remainder (its close writes no research note).
> 3. **Git-ignored inputs beyond the four ELFs are regenerated, not fetched:** `game/r0004/match.json` (Task 10's `tools_py/address_matcher.py` over the two tracked maps and the two images), `game/demo_symbol_matches.json` and `game/demo_symbol_renames.csv` (research/44's command A), 7b's `game/demo_symbol_renames_7b.csv` (research/45's command). Each note names its command; regenerate and compare the counts the notes state before building on them.
> 4. **Proof requests are batched:** the local controller runs them at the owner's build windows only, in a worktree of `sprint-12`, together with Sprint 11's own lock-bound items (Task 6 Step 3, the r0004 online proof, the r0004 rebuild proof for `9ade5a3`); expect a window's turnaround, not an hour's. A task is DONE only when its row carries the local result.
> 5. **Sprint 11's close is unchanged:** its two lock-bound items, then the final review, the merge to `main`, the tag. You merge `origin/main` after that; until then `origin/sprint-11` daily.


You run on a fresh Ubuntu 24.04 VM with this repository cloned, no GPU, no Windows, no game, no loop lock. Every
rule in `docs/HANDOFF.md` §5 that is about *the shared Windows tree* (worktrees, junctions, the lock, "the owner
feels long builds") is moot for you, and every rule about *the public repository* (explicit pathspecs, the leak
check, the commit trailer, never commit `game/`, `vm/`, `tools/`, `logs/`) binds you exactly as it binds anyone.

What you can do here that the local machine cannot: run for hours without lagging the owner, and run CPU-heavy
static analysis (Ghidra headless, BinDiff, ccc) without the lock. What you cannot do: build or run the Windows
game, take the lock, run a gate. Every Sprint 12 item therefore has a **code half** (yours) and, where it changes
the generated image, a **proof half** (the local controller's, at a build window the owner names: recomp, runtime,
the r0001 gate 3/3 with PINS MATCH).

The four git-ignored inputs the whole programme reads arrive through `scripts/fetch_private_inputs.sh` from a
private HTTPS location. **You run it yourself, in the session, after checking out `sprint-12`** (§2): the
environment's variables `S2U_INPUTS_URL` and `S2U_INPUTS_AUTH` are set for the session, and the script lives on
`sprint-12`, not on `main`. (A setup script cannot do it: the sandbox runs setup scripts before the clone and
without the environment's variables — proven 2026-09-24 evening, exit 6.) Thirty-three seconds per fresh
session; a session that already has them prints "present" four times. Their
digests are in the served `SHA256SUMS`; `docs/research/44-demo-symbols.md` §1 names the demo's. **They are the
owner's own dumps and never enter the repository in any form — not a byte, not a hex dump in a test fixture.**
Tests use synthetic images, as `tools_py/tests/test_elf_symbols.py` and `test_ghidra_symbol_match.py` do.

Plugins do not carry into the cloud (`docs/HANDOFF.md`'s superpowers skills are a local plugin). Their discipline
is written into §4 below in plain words; follow it from here, not from memory of the skills.

## 2. First hour, all of it lock-free

1. The branch (§5): `git fetch origin`, then `git checkout sprint-12` if `origin/sprint-12` exists (a first
   session created and pushed it on 2026-09-24), else `git checkout -b sprint-12 origin/sprint-11 && git push -u
   origin sprint-12`. Then `git merge origin/sprint-11` so the ratified handoff and everything after it is in.
2. `bash scripts/fetch_private_inputs.sh` — four times "fetched" (33 s) or "present". If it says the URL is not
   set, the session started on an environment without the two variables: stop and tell the owner.
   `python -m tools_py.elf_symbols game/demo_scus_972_05/SCUS_972.05 | head -3` proves the demo ELF reads.
3. `bash scripts/install_hooks.sh` (the leak check in pre-commit and pre-push; never `--no-verify`).
4. Read, in this order: `docs/HANDOFF.md` §1–§2 and §5; `docs/GIT_STRATEGY.md` §2–§3; `docs/DOC_MAINTENANCE.md`
   §6; `docs/research/44-demo-symbols.md`, `45-positional-and-bridge-names.md`; `tools_py/research/symbols/README.md`
   (the measurements behind R260–R262, with the scripts that reproduce every number); the Sprint 11 plan's Task 7
   and its rulings R245–R263; `docs/KNOWN.md` §4's struct-offset row (why raw offsets in hooks are a cost).
5. `python -m unittest discover -s tools_py/tests -t . 2>&1 | tail -3` — the Python suite is your ring; it needs
   no disc. The count is stated in `docs/DEVELOPING.md` and nowhere else.
6. Write the spec (§3). Nothing else first.

## 3. Phase 1 — the spec and the plan (the first day)

The spec goes under `docs/superpowers/specs/` as `<date>-sprint-12-the-readable-image-design.md`, the plan
under `docs/superpowers/plans/` as `<date>-sprint-12.md`, in the shape of the Sprint 11 pair (read
`2026-09-21-sprint-11-r0004-and-the-community-server-design.md` and `2026-09-23-sprint-11.md` for the shape: goals
with a bar each, tasks with Files / Interfaces / Steps with pasted evidence, global constraints, owner decisions
with the default each proceeds on, rulings). The spec must answer, with numbers where the notes already have them:

- **Who consumes a name.** The recompiler (the CSV's `Name` is the generated function's C identifier and its
  filename, `recomp/socom2.toml` feeds it); the runtime hooks (`game_overrides_socom2.cpp`, `socom2_addresses.h`);
  HLE; the parity tools that address fields by raw offset (`tools_py/parity/verdict_core.py`,
  `guest_addresses.py`); the address table across revisions (`tools_py/carry_names.py`); voice chat (Q5: SOCOM II's
  codec is **SASE** — `SaseEncVad`/`SaseDec` source paths in all three SOCOM II builds — research/44's addendum;
  SOCOM 1's demo used LPC-10, which SOCOM II does not ship).
- **What "readable" means and its bar.** Names in `Class_Method` form with the mangled original kept
  (`Mangled` column), overloads disambiguated by an argument suffix only where the readable name is not unique
  (2 of 479 collide; 255 names over 607 functions across the demo's whole table); a legal C identifier and a legal
  filename; **provenance on every name** (R261: address, name, source pass, score, evidence, in a tracked sidecar
  carried by `carry_names`). A name without a recorded reason is a defect.
- **The acceptance bar of the sprint.** The renamed tree builds and passes the r0001 gate 3/3 with PINS MATCH (the
  local proof); every proposal file's acceptance rule is stated in code, not in prose (Task 7's six hurdles are the
  model); every number in every note names its command.
- **The seed tasks from R257–R263**, in this order, each with its code half and its proof half:
  1. The rename pass: the 479 (`game/demo_symbol_renames.csv`, regenerated by research/44's command A) plus 7b's
     six (research/45) applied to `recomp/socom2_ghidra.csv` in readable form, the provenance sidecar, the
     `carry_names` change, tests. Proof: local (recomp, runtime, gate).
  2. **Task 7c — vtable slots through RTTI — is YOURS** (R263 moved the whole naming programme to Sprint 12; R260's
     "after 7b" condition is met, 7b merged at `7feebf0`). Start from `tools_py/research/symbols/vtable_rtti.py`
     and `vtable_anchors.py` (the peer's measurements: 111 classes resolve to exactly one retail vtable, 1,154
     demo slots against 1,496 retail; 54 resolve to several, 66 names absent, 14 templates skipped). A third
     proposals file under its own rule, pass name `vtable-slot`, scored below `exact`; slots aligned on
     body-matched fixed points, equal-count runs by position, constructors from the vtable-pointer store.
     `tools_py/ghidra_symbol_match.py` and `tools_py/symbol_levers.py` are yours on `sprint-12` from the branch's
     first commit; the local controller does not edit them on `sprint-11` after `07166d3` (an exception would be a
     `LOCAL:` line).
  3. BinDiff as the independent cross-check of the 987 pairs (R262 replaced Ghidra Version Tracking with it);
     the Ghidra headless container is `tools/ghidra/docker/`.
  4. The ccc route for the demo's DWARF1 types, with the layout-age caveat (R262): the demo is SOCOM 1, a year
     older; every field offset is confirmed against SOCOM II access patterns before a hook may use it; the
     `.debug` covers 95 units, mostly FTS and the LPC-10 codec, so expect engine types to be partial.
  5. The toml's 656 stub names into the generated output (today `ps2_recompiled_stubs.h` declares
     `sceCdDelayThread` as `sub_0018DBB8`): a recompiler change with synthetic-ELF tests; proof local.
- **Owner decisions**, each with the default you proceed on: the naming style (default `Class_Method`); whether
  hand-named rows may be renamed (default no, R257's rule 5); whether the 138 pairs between the score line and the
  64-byte rule are ever proposed (default no, research/44 §7); whether a rename may change a name the parity
  tools cite in comments (default yes, comments are not contracts).

Then the plan: tasks in dependency order, each bounded to a day, each with its verification command and its
review shape. The plan's task table carries a **"needs the local tree"** column (§5).

## 4. Phase 2 — the research wave (with the authority to add tasks)

A wave of independent, read-only investigations, each its own research note `docs/research/NN-<slug>.md`
(next free number after 45; the sequence is shared with Sprint 11, so take the number when you commit and merge
`origin/sprint-11` first), each in research/44's discipline: every number names the command that produces it;
demo bytes and addresses only, never bytes in the repository; a "what this means for a task" section at the end.
Run them in parallel with sub-agents (§6) and read every one yourself. **Authority:** a finding that changes the
plan becomes a task in the Sprint 12 plan with a ruling (§5 numbering), without waiting for anyone; a finding that
retires a seed task retires it with a ruling that says what it cost. The questions, from the two outside reviews
audited on 2026-09-24 (R262's declines stand unless a note overturns them with numbers):

1. **The name consumers, exhaustively.** Every place a function name or a raw guest offset is read or written:
   the recompiler's CSV import and identifier sanitiser (`third_party/ps2recomp/ps2xAnalyzer/src/elf_analyzer.cpp`
   `importGhidraMap`, `ps2xRecomp/src/lib/code_generator.cpp` `sanitizeIdentifierBody`), the toml's stub list, the
   runtime's `replaceFunction` wraps, the address table, the parity tools' offsets. Output: the map the spec's first
   bullet needs, and the list of offsets a type would name.
2. **The readable-name scheme, proven.** `tools_py/research/symbols/readable_names.py` is the sketch. Decide the
   overload suffix (argument types from the mangling vs a short hash), templates, anonymous namespaces, the
   `__sinit_*` initialisers, the 96-character cut; prove uniqueness over the demo's 9,703 and over all proposal
   files; prove every output is a legal identifier and Windows filename.
3. **Provenance sidecar design.** One tracked file beside the CSV (address, name, source pass, score, evidence,
   date), the reader in `carry_names`, the audit that refuses a `Name` change without a sidecar row. Decide whether
   the recompiler's own `sub_*` gap-fill names get rows (default: they are placeholders, no row).
4. **BinDiff on demo1 → r0001**, diffed against the 987 pairs: agree / disagree / new, by pass. BinDiff's
   flow-graph similarity is the one signal that survives edited bodies; report what it adds and its false-pair rate
   against the 828 proved pairs (research/45's holdout method).
5. **ccc / DWARF1**: what the demo's `.debug` actually holds (compile units, types, locals) after a real DWARF1
   walk; which engine structs have layouts; for each candidate field the parity tools use by offset, whether the
   SOCOM II access pattern agrees. Output: a types note and the list of offsets that can be named safely.
6. **Vtable coverage after 7c** (7c is yours; this is its follow-up): the classes 7c could not open (66 names absent in retail,
   54 multi-vtable, 14 templates), and what would open them (the qualified `Q2` name, template bare names).
7. **Call-graph propagation from anchors**: callers-of-named and callees-of-named as evidence for the unnamed
   bodies between them, with the 828 as truth for a false-pair rate. Task 10's matcher has the callee side;
   measure whether the caller side adds anything at a rule of "unique both ways".
8. **Strings as first-class evidence**: research/11 matched reCOM's 540 literals; measure a shared-string
   correlator over all string references (not only tie-breaks), false-pair rate against the 828.
9. **Member-offset multisets** as a looser body key: the multiset of load/store displacements per function, unique
   both ways, false-pair rate against the 828 (the fingerprint already keeps displacements exactly).
10. **The FTS application layer and the class inventory as an architecture map**: the 1,212 classes and their
    method counts (CZSealBody 351, CSealCtrlAi 140, CZKit 110, CZOnlineLobby 65, CNetCnf 38) against what the
    project already knows (research/11, /19, /20); which subsystems the hooks touch, and which are named by nothing
    yet. Output: the map, and the classes whose naming would pay first for online play and voice.
11. **SASE**: what the strings, the call structure and the data tables say about the codec (frame size, sample
    rate, bit rate, VAD), without naming a vendor the evidence does not name; what Q5 (voice chat) would need
    from it. Output: a note that Q5's owner can start from.
12. **The recompiler's naming pipeline end to end** (task 5's groundwork): where `sub_*` comes from (the analyzer's
    gap fill, `recomp/extra_functions.txt`), why the toml's names stop at the stub list, and the smallest change
    that carries every known name into `recomp/output`.
13. **The Nov 25 2003 prototype and the Aug 28 beta** (research/03): not in hand; write what each would add
    (the Nov 25 build sits between r0001 and r0004's Nov 3 2004 id) so the owner can decide whether to look.
14. **What a stranger sees**: with names applied, what `recomp/output` reads like, what `docs/HOW_IT_WAS_BUILT.md`
    and `DEVELOPING.md` must say about names, provenance and the two proposal-file rules.

## 5. Coordination with the local machine — the procedure that changes

Two controllers, one repository, one open sprint on `main`'s doorstep. The rules:

- **Branch.** `sprint-12` opens off `origin/sprint-11` (not off `main`: Sprint 11 is still open and carries Task 7,
  7b, the symbol scripts and `scripts/fetch_private_inputs.sh`). You push **only** to `sprint-12` (the sandbox's
  push protection enforces this: the session's working branch and nothing else). Merge `origin/sprint-11` into
  `sprint-12` at least daily and whenever the local controller reports a landing (the r0004 rows, Sprint 11's close); when
  Sprint 11 closes, merge `origin/main`. Never rebase a pushed branch; never push to `sprint-11`; never open a
  PR to `main` — slices to `main` are the local controller's (`docs/GIT_STRATEGY.md` §2, "the controller opens
  and merges every slice"), and Sprint 12's slices go after Sprint 11's close.
- **Files you never edit on `sprint-12`** (they are Sprint 11's live state and would conflict at every merge):
  `docs/CURRENT_SPRINT.md`, `docs/HANDOFF.md`, `docs/STATUS.md`, `docs/HUMAN_TASKS.md`, `docs/KNOWN.md` rows that
  Sprint 11 owns. Your live state lives in the Sprint 12
  plan (a "Log" section with dated lines, newest first) and in your research notes. The local controller mirrors
  what it needs into the sprint file and STATUS at each merge, and rewrites `CURRENT_SPRINT.md`'s header when
  Sprint 12 becomes the open sprint.
- **Rulings.** Number yours `S12-R1`, `S12-R2`, … in the Sprint 12 plan's "Rulings made on the owner's behalf".
  The global counter in `docs/HANDOFF.md` is the local controller's; it folds your rulings into the sequence at
  the merge. A ruling says what was decided, what it cost, and that the owner can overturn it.
- **Proof requests.** A task whose code half is done and whose proof needs the machine gets a row in the plan's
  task table: state `PROOF REQUESTED`, the exact commands (`./build.sh recomp`, `./build.sh runtime`, the gate
  line), the commit to check out, and what "green" means. Push it. The local controller runs it in a worktree of
  `sprint-12` at the owner's window and appends the result to the same row in a docs commit on `sprint-12`
  (`git pull --rebase` before every push, both sides). Until then the task is `DONE (code), PROOF PENDING`; a
  task never becomes DONE on the cloud's word.
- **Reviews.** Every task is reviewed by a fresh sub-agent that did not write it, against the spec and against
  the code, findings named `file:line`, then fix rounds until the re-review is clean — the loop Sprint 11's
  ledger shows (`review-<a>..<b>.diff` per round). Keep the review diffs under `.superpowers/sdd/2026-09-2N-sprint-12/`
  (git-ignored: it is your working memory, not the record; the record is the commits and the plan's log).
- **CI.** A non-docs push to `sprint-12` costs an hour on a hosted runner (Linux only, no generated code, no
  gate). Batch pushes; check `gh run list --branch sprint-12 --limit 1`; keep it green.
- **The owner relays.** The owner reads both sessions. When you need the local controller (a merge landed? a
  window?), write it in the plan's log with a `LOCAL:` prefix; the owner or the controller picks it up. Do not
  wait: do the next lock-free task.

## 6. Phase 3 — executing the sprint

The loop, per task, in the repository's discipline (`docs/LOOP_PROMPT.md` and `HANDOFF.md` §5, minus the lock):

1. **Look before you touch:** `git status --short`, `git log --oneline -5`, `git fetch origin`; merge
   `origin/sprint-11` if it moved.
2. **A failing test first**, unittest only (`tools_py/tests/`, no pytest-style files: `test_test_hygiene.py`
   refuses them), on a synthetic image; RED pasted into the task's step; then the change; GREEN pasted.
3. **Bounded sub-agents** for the mechanical halves, each with an exact brief (files it may touch, the
   verification command, the stop rule) and a report; a sub-agent never commits a file it was not given. For any
   number a decision rests on, a fresh agent re-derives it rather than re-reads it.
4. **Commit with an explicit pathspec**, subject `type(scope): what and why` carrying the finding, the trailer
   your session is given (never one copied from an older commit), the leak check green.
5. **Review** (§5), fix rounds, then push `sprint-12` and check CI.
6. **Write it where it is read:** the plan's task row and its log line; a research note when the task produced a
   number; `> Superseded by …` on any committed sentence that turned out false, the same hour.
7. **The next task.** Do not wait on a person; what only the owner can decide gets its default and a ruling.

Stop rules: never a byte of the game in the repository; never a rename applied to `recomp/socom2_ghidra.csv`
without its sidecar rows and its acceptance rule in code; never a number in a note without its command; never
a push anywhere but `sprint-12`; never a PR to `main`; never an edit to the files in §5; never an action that is
the owner's (publish, deploy, spend, flip permissions — `HANDOFF.md` §5 rule 13).

## 7. The environment, for the owner

One repository (`Scotho/socom-unzipped`) is all the session needs; the site side is deployed. The environment
carries the two variables (`S2U_INPUTS_URL`, `S2U_INPUTS_AUTH`) and **no setup script** (see §1: setup scripts
run before the clone and without the variables). Network access is the owner's choice: **Full** needs no list;
**Custom** replaces the Trusted list, so it must then carry what the wave installs, not only the private host:
`s2u.scotho.com`, `*.ubuntu.com` (apt: Java for Ghidra, build tools for ccc), `pypi.org`,
`files.pythonhosted.org`, `github.com`, `api.github.com`, `raw.githubusercontent.com`,
`objects.githubusercontent.com`, `release-assets.githubusercontent.com`, `codeload.github.com` (Ghidra's and
ccc's releases), `*.zynamics.com` (BinDiff), `*.docker.io` and `*.docker.com` if the Ghidra container is used.
The two environment values are in the owner's git-ignored `vm/lightsail/s2u-private-inputs.md`.

The first prompt to the session:

> You are the Sprint 12 controller. Read `docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md` on
> `origin/sprint-11` first and do exactly its §2, then §3, §4, §6 in order. The local Sprint 11 controller owns
> the machine and Sprint 11; you own Sprint 12, Task 7c included on branch `sprint-12`. Proceed without waiting on anyone;
> what needs the machine gets a PROOF REQUESTED row; what is the owner's gets a default and a ruling.
