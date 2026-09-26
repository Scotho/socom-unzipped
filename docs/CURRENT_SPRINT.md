# Current sprint

The loop's aim. The `loop-iteration` skill (`.claude/skills/loop-iteration/SKILL.md`) reads this file instead of carrying a sprint pointer of its own; the controller
updates it when a sprint opens or closes, and whenever the order changes. **If you are a new controller, read
`docs/HANDOFF.md` first** -- it says where the project is and what the traps are; this file says what to do next.

**The goal every sprint serves:** SOCOM II running natively on PC with online play, that a stranger runs by pointing the
launcher at their own r0001 ISO and playing a round against another stranger on a hosted Horizon server -- from a public
repository another person can fork, build and contribute to.

```
branch:       sprint-14 -- OPEN 2026-09-26 05:17Z off main at 6a82caaa (the Sprint 13 merge, PR #61, tagged v0.13.0;
              Sprint 12 merged as v0.12.0 at 74fe2a9b, PR #50; Sprint 11 as v0.11.0 at 173608af, PR #49). This
              machine's checkout is on sprint-14 (the Sprint 14 controller session); agents work in worktrees on
              agent/s14-* branches and the controller merges them. See "Sprint 14 -- OPEN" below, then the three
              CLOSED blocks. No cloud session runs from 2026-09-26.
spec:         docs/superpowers/specs/2026-09-26-sprint-14-guards-not-sentences-design.md (seven milestones G, I, W, D,
              S, E, M with a bar each, the filler X1; the acceptance bar is its section 4; section 1.5 says what the
              loss of the cloud changed). The Sprint 13, 12 and 11 specs closed with v0.13.0, v0.12.0 and v0.11.0.
plans:        docs/superpowers/plans/2026-09-26-sprint-14.md (the task table, the Log newest first, the rulings
              R269-R277 from the global counter -- no sprint-local names from this sprint on, R273); it came from
              docs/audits/2026-09-26-autonomy-structure-review.md (nine findings, options A-I, six notes beside it).
              The Sprint 13 plan (its rulings S13-R1..R14), the Sprint 12 plan (S12-R1..R25) and the Sprint 11 plan
              are closed and listed in their blocks below; Sprint 10's and older are in
              docs/archive/CURRENT_SPRINT-sprints-9-to-11.md (the 2026-09-25 split, R268).
next sprint:  Sprint 15 "borrowed confidence" (R276): docs/superpowers/specs/2026-09-26-sprint-15-borrowed-confidence-design.md
              and docs/superpowers/plans/2026-09-26-sprint-15.md, PROPOSED, opened from the confidence register at
              this sprint's close; the standing "visible defects first" order resumes inside it. Its origin, the
              cloud handoff of 2026-09-25, never ran and is kept under a NEVER RUN banner
              (docs/superpowers/plans/2026-09-25-borrowed-confidence-cloud-handoff.md).
human tasks:  docs/HUMAN_TASKS.md      playtest script: docs/PLAYTEST.md
git strategy: docs/GIT_STRATEGY.md     contributing: CONTRIBUTING.md
next ruling:  R279 (R278, 2026-09-26 08:17Z, the Sprint 14 plan's Log: while other sessions' builders hold or
              queue the lock, lock-free tasks from D, S and M run ahead of W. R269-R277, 2026-09-26 05:17Z, the Sprint 14 open, one per owner default D1-D9 of the Sprint 14
              spec: the infrastructure sprint and its order (R269); KNOWN §4 to a hazards file (R270); owner rows
              closed by default after two sittings (R271); STATUS's log archived, the changelog generated (R272);
              sprint-local ruling namespaces retired (R273); the held-out leg (R274); two building agents (R275);
              Sprint 15 is "borrowed confidence" (R276); the private-inputs location is the owner's to retire (R277).
              R265-R268, 2026-09-25 night, the project audit `docs/audits/2026-09-25-project-audit.md` §4: the four
              oldest backlog rows owned or declined, the six carried issues into Sprint 13, one home for the carry,
              ceilings on the appending documents. R264, 2026-09-25, the Sprint 12 close: Sprint 12's twenty-five rulings keep their S12-R<n>
              names in the Sprint 12 plan, the one home; the global sequence continues from here -- the "Sprint 12
              -- CLOSED" block. R263, 2026-09-24 night: the naming programme -- the rename pass R257/R261, Task 7c, BinDiff, ccc -- is Sprint 12, "the readable image"; Sprint 11 keeps Task 7 and 7b. R260-R262, 2026-09-24 night: Task 7c vtable slots through RTTI after 7b (R260); a provenance sidecar in the rename commit (R261); FID database and r0004-as-corpus declined, BinDiff replaces Version Tracking in the deferred item (R262). R257-R259, 2026-09-24 evening: the demo names apply in Class_Method form at a build window (R257); Task 7b, positional + the Aug 18 demo bridge (R258); Version Tracking and ccc deferred, the voice codecs recorded: SOCOM 1 LPC-10, SOCOM II SASE, GSM nowhere (R259). R253-R256, 2026-09-24: the closed security row retired from the public docs, history stays (R253); the r0004 reboot is an image defect, undone from the capsule's decoded stack (R254); the lock goes to the r0004 critical path first (R255); an unrunnable override is not an override (R256). R245-R252, 2026-09-23: the known-issue stack on GitHub (R252); r0004 is a real rebuild, its ELF built (R251); the package is behind the bypass, served by PSRewired (R250); r0004 is the DNAS bypass we already carry (R249); the r0004 patch is PSRewired's resident capsule (R248); option B not scheduled; the chat bound's install is the Milestone S proof, the traversal a filler row; the vendored baggage deleted -- the Sprint 11 plan's rulings section) -- nothing is renumbered. The sprint's sixty-four numbers R181-R244 are
              reconciled row by row in ONE table below ("Sprint 10's rulings ledger, R181-R244"): the decision
              in its own words, where it is written, and its status. R229 is deliberately vacant. This line used
              to carry that index as a single 2,700-character paragraph, which no reader could use; the table is
              its one home now, per docs/DOC_MAINTENANCE.md section 6.
baselines:    the suite counts live in `docs/DEVELOPING.md` ("What a green run looks like") and nowhere else -- this
              line said C++ 686/686 and Python 1457 from 2026-09-20 to 2026-09-22, four sprints after they stopped
              being true, which is why `tools_py/tests/test_doc_maintenance.py` now refuses an undated count outside
              that file. `./build.sh test` exit 0 on the renamed tree (2026-09-25); last gates (Sprint 13,
              2026-09-25): `s13_proof4_gate` 3/3 PINS MATCH (exe f90eeec0..., 22:16Z), `s13_v4_gate1` PASS on the
              same exe (23:51Z), `s13_proof3_gate` 3/3 (r0001, 20:54Z), `s13_names_r0004_gate` 3/3 PINS MATCH (r0004,
              d027546d...); the plan's Log has each; audio parity
              `s9_q1_parity_ours2` 31/48 (2026-09-20, unchanged since)
```

Markers used below: **[A]** autonomous; **[O]** the owner's hands, ears, money or decision; **[B: x]** blocked on x.
"Lock-bound" means it needs a build or a launch (the loop lock, `scripts/check_quiet_gate.sh` first -- the owner feels
long builds); "lock-free" can run at any time.

---

## Sprint 14 — OPEN 2026-09-26 05:17Z (plan `docs/superpowers/plans/2026-09-26-sprint-14.md`, "guards, not sentences")

Opened by the Sprint 14 controller off `main` at `6a82caaa` (the Sprint 13 merge, `v0.13.0`) on the owner's
instruction of 2026-09-26 ("begin with sprint 14 once sprint 13 is finished, committed, and live on main"). The
sprint came from the structure review `docs/audits/2026-09-26-autonomy-structure-review.md` (nine findings: the
record is the failure surface; rules recur, tools do not; greens that were not; an unbounded ruling log; one host,
many writers; handoffs lose state; the owner loop never closes; nothing measures cost; a thin verification
architecture). **No feature work.** Every rule that has recurred becomes something that fails on its own, every
document a session must read becomes small, generated or loaded on demand, and concurrency is capped until the host
stops corrupting measurements. The owner's word of 2026-09-26 sets aside "visible defects first" for this one sprint
(R269); the order resumes in Sprint 15.

Seven milestones in order, then a filler — **G** guards (a PreToolUse hook refusing the eight recurring git and lock
mistakes; an Edit/Write hook for running chain scripts; a session-end hook that reaps orphaned watchers; agent
definitions; `build.sh` consults the lock; a memory guard), **I** instructions on demand (a root `CLAUDE.md` under
sixty lines; four skills replace the prose procedures; HANDOFF transient under 6 KB; a read-first budget check;
KNOWN's hazards to their own file), **W** the host (the queue refuses a third building agent; the merged chain is the
gate unit, with eviction and ticket waits logged), **D** decisions with status (a generated rulings page; the scope
rule and one counter; a generated owner's sitting page; the circuit breaker; PLAYTEST's build block written by the
chain), **S** the record generated (the changelog; STATUS's log archived; a commit-msg hook; ceilings that ratchet
down; one home each), **E** evidence that is hard to fake (a PR to `main` built on its head; a held-out capture leg;
recompiler re-derivation in CI; gate freshness), **M** measurement (a generated flow page; token spend read locally,
never committed); **X1** the external sweep for Sprint 15, filler when the host is quiet. **Every guard is fired
against a planted violation before it counts as done.** The bar is the spec's section 4; the nine owner defaults and
their rulings R269-R277 are the plan's "Owner decisions" and "Rulings" sections. The plan's Log is the live state;
this block gains its table at the close.

## Sprint 13 — CLOSED 2026-09-26 (merged to `main` as `v0.13.0` at `6a82caaa`, PR #61, 2026-09-26 ~05:00Z after the owner granted the gh token the workflow scope; the record of the sprint is the block below)

**Close-out (the PR body).** Opened 2026-09-25 08:40Z, closed 2026-09-26 04:17Z: 285 commits, 43 agent merges, every task
reviewed by a fresh agent. Closed #27, #30, #31, #33, #35, #36, #37, #38, #39, #40, #45, #46, #48; opened #45–#48, #51–#60;
carried #28, #32, #34, #59 once to the backlog and #25, #26, #42 to the owner (S13-R14, HUMAN_TASKS O16). The gate
`s13_merged_gate` 3/3 on the final exe `0633c484`; proofs 1–4 green on r0001 and r0004; CI green. Found unplanned: a
server-to-client memory write refused on the client (U6, SECURITY); the Sprint 11 chat bound is not on the game-lobby
path (O2, SECURITY 'partly fixed', #26 restated); a stub's table slot can hold an owner's resume entry (#60); the
loop lock's queue proven by a night hand-off and a first-time scheduled ladder. Not done on purpose: V5's audio steps
(the client muted), O1's console-peer leg (the owner's hands). Rulings S13-R1..R14. The DOC_MAINTENANCE §5 review
fixed 24 stale claims across nine documents and three KNOWN rows; the §7 stack read found the audit clean, relabelled
two issues, rewrote two bars, and placed three evidence notes. The Outcome in the plan has the bar row by row.

**As it stood while open:**

Opened by the local controller on the owner's instruction of the same night ("audit the entire structure of the
project, compile a master list, clean up docs as you go, and start your own sprint 13"). The audit is
`docs/audits/2026-09-25-project-audit.md` with six reports beside it; the spec is
`docs/superpowers/specs/2026-09-25-sprint-13-nothing-carried-twice-design.md`. Eight milestones in the order the owner
meets them — **V** the player's first ten minutes (#30, #32, #31, a frame-time line, the music #42/#28, #27, #34, the
launcher's wording), **R** the record made true and small (the archive split and R268's ceilings, DEVELOPING as
current truth, the ruling record, HUMAN_TASKS reduced to the owner's sitting, KNOWN in full, one home for the carry),
**H** the harness pays its debts (the lock's queue #36/#35/#37, #45, #38, #46, #41, the per-revision literals, the fast
subset), **C** the code's hygiene and supply chain (CI compiles the overrides, the throwing stubs, the after-return
trap, FFmpeg with a hash, the dead configuration), **U** upstream and outside (research/63's picks, path containment,
#253's emitter change, a server-to-client record refused), **S** the stranger, **N** the naming follow-ups, **O**
online and the box. The bar: nothing leaves the sprint carried twice without a ruling; CI green with the overrides
compiled; the record under its ceilings; the first ten minutes measured; the gate 3/3 plus one ladder run and one
mixed leg on the sprint's final exe. The plan's Log is the live state; this block gains its table at the close.

**Owner decisions:** `docs/HUMAN_TASKS.md` carries them, O1–O15 (reduced by Task R4, `4adbf2bc`, `1ed975a4`), with
the plan's D1–D2; each has the default the loop is on.

## Sprint 12 — CLOSED 2026-09-25 (merged to `main` as `v0.12.0` at `74fe2a9b`, PR #50; the record of the sprint is the block below)

**Goal, as R263 and the spec stated it:** a readable generated image — every proven name from the SOCOM 1 demo's symbols into the function map, in `Class_Method` form with its provenance recorded, for the hooks, HLE, the address table across revisions and voice chat; its own tooling and review loops; the whole sprint gated on the renamed tree. **Outcome:** the generated image carries **1,771 readable names with a recorded reason each** (`recomp/socom2_names.csv`, 1,840 rows with the 69 Ghidra syscall stubs; r0004 1,705 rows through `carry_names`), against about 120 on 2026-09-24. Every name came through one applier (`tools_py/apply_names.py`) from a proposals file under a rule stated in code; every rule has a holdout or a link-order measurement in its note; every number in every note names its command. The recompiler reads the names from the sidecar (`[general] names`), so the csv's `Name` column is untouched and the renamed tree differs from the old one in identifiers only. **The local proof (Task 3 Step 4, 2026-09-25 04:51–05:38Z; the r0004 leg 07:24–07:40Z — `s12_names_r0004_gate` 3/3 PINS MATCH on the r0004 runtime built with its own 1,705-name sidecar):** recomp `14882 files, unhandled=114399, unmapped=0` with `Loaded 1840 display names`; against the pre-rename output **1,771 files renamed, 0 extents moved, 0 functions dropped** (`S12-R11 … OK`); the runtime built from scratch (exe `804dd172…`); `build.sh test` exit 0; **the r0001 gate `s12_names_gate` 3/3 with PINS MATCH** — on `cb56fc8`, this branch merged with Sprint 11's final `3bb866f`. The sprint was executed by a Claude cloud session (no game, no lock) on `sprint-12` under `docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`; the local half (the proof, the merge, this block) is session socom-pc-6c's.

| Task | State | Evidence |
|---|---|---|
| 0 the open: spec, plan, the research wave, the inputs regenerated | done | `6c35ed1`; spec `docs/superpowers/specs/2026-09-24-sprint-12-the-readable-image-design.md`, plan `docs/superpowers/plans/2026-09-24-sprint-12.md`; research/47–61 (46 is the peer's day-one record) |
| 1 the readable-name renderer | done | `tools_py/readable_names.py`, 19 tests; 868 of 871 set-D rows rendered, 0 collisions, longest 41 |
| 2 the provenance sidecar | done | `tools_py/name_provenance.py` (read, write, audit), 69 `Pass=ghidra` rows backfilled, `carry_names` carries it |
| 3 the applier; every lever applied to the sidecar; the r0004 sidecar; **the proof** | done | `cd2fbfc` (1,491 names) then Tasks 6 and 8 (1,771); 5 held, 1 refused, 0 contradictions; the local proof above |
| 3a the recompiler runs in the cloud; the census tool | done | `ps2_recomp` on Linux in 52 s; `tools_py/recomp_census.py` (5 tests) reproduces 14,882 / 7,958 `FUN_` / 6,750 `sub_` / 171 named — the same census this machine measured before the rename |
| 3b the recompiler reads display names from the sidecar | done | `d83afc9`: `[general] names`, `makeName`, the `// Function:` header; a synthetic-ELF case in `ps2xTest`; `revision_toml --set-names`, `build_revision.sh` step 3 |
| 4 Task 7c, the `vtable-slot` pass | done | `tools_py/vtable_lever.py`, 27 tests; 211 classes resolve by RTTI; 199 rows at 0.75; leave-one-out 37/0; research/60 |
| 5 the r0004 seed list | done | `tools_py/derive_seeds.py`, `recomp/r0004_seeds.txt` (294 seeds); `match.json` reproducible at 81.56 % |
| 6 BinDiff as the second signal | done | research/49; `tools_py/bindiff_lever.py`, 24 tests; 21 `prefix+bindiff` rows, 0 contradictions on the 828 under the bounded rule; S12-R22, S12-R23 |
| 7 the demo's types beside the probes' offsets | done | `OFFSET_NAMES` in `tools_py/parity/guest_addresses.py` (root_node 0x2E8 = `CZSealBody::m_root`, +0x7c from SOCOM 1), 8 tests, no number changed; research/50 (536 DWARF1 layouts) |
| 8 the `toml-stub` pass and the toml-to-sidecar agreement test | done | `baa525c`: 274 applied, 214 of 223 stub selectors agree, 9 are not csv rows |
| 9 what a stranger sees | done | `dd2ec66`: HOW_IT_WAS_BUILT "How the generated code got its names", DEVELOPING "Names in the generated code", the symbols README's script rows, research/59 |
| 10 the wave's added tasks: 12 `string-set`, 13 `offset-multiset` + `prefix+offsets`, 14 `ui-binding`, 15 `callgraph` | done | `tools_py/string_lever.py` 214 (+45 loose); `offset_lever.py` 188 + 43; `ui_binding_lever.py` 124 + 83 (20/20 with research/11); `callgraph_lever.py` 235 (+522 loose, 106 promoted); holdouts 0 wrong each |
| 11 the close | done | this block; the two reviews below; the PR and the tag |

**Carried out of Sprint 12** (to the backlog with the `carried` label unless a line names another home): the 518 loose rows that wait for a second independent lever; the Outcome's follow-ups — the `// Function:` header wording and a header on named stubs, `build_revision.sh --out` copying the sidecar beside the toml, research/50's nine other safe offsets in `sp_death_probe`/`verdict_core`/the runtime, the csv's Ghidra-split boundaries (0x00183024 and the 64 rows inside vtable data, research/60 §7), `std::unexpected`/`std::terminate` as `Pass=hand` candidates, the 41 toml addresses that are not csv rows, the 26 toml names research/57 §3 calls wrong, constructors under research/51's variant C; research/61 §5's r0001 literals outside the per-revision table (Sprint 11 carried it here; nothing in Sprint 12 took it). To the owner (HUMAN_TASKS "Sprint 12 close — what needs you"): the seven defaults D1–D7 to confirm or overturn, and the five big engine routines' hand review (D5).

**Rulings.** Sprint 12's rulings are `S12-R1`–`S12-R25` in the plan's "Rulings made on the owner's behalf" (the one home; the cloud numbered in its own namespace by the handoff's §5). **R264** (2026-09-25, the local controller): they keep those names — renumbering twenty-five rulings cited across fifteen notes and the plan would buy nothing and risk a wrong citation; the global counter continues from HANDOFF's next free number, and any later ruling that touches a Sprint 12 decision cites the `S12-R<n>` it amends. The owner can overturn it.

**The two reviews the close ran (DOC_MAINTENANCE §5 and §7), 2026-09-25:** The §5 review read every live document (a read-only agent's table of 60 rows across thirteen documents; the controller applied 45 of them in this commit): the sprint file's header rewritten for two closed sprints and no open one; `HANDOFF`'s state line, gates and worktree list; `HUMAN_TASKS`' new section and its Sprint 12 window struck as done; `STATUS`'s top bullet, its dated entry and its `Next:` line (which had said "Sprint 10 is CLOSED, what is left is the merge" since 2026-09-23, through the whole of Sprint 11 and its close review — corrected to a pointer); `DEVELOPING`'s `recomp/` row, its names paragraph ("research/61–57" was a backwards range) and its green-run rows; README's status paragraph and two table cells; `ROADMAP` §6 and `STORY`'s Sprint 12 promise superseded in place; `GIT_STRATEGY`'s NOW line; the symbols README's note number (46 → 61, S12-R25); HOW_IT_WAS_BUILT's tense; KNOWN's new §1 row, §4 lesson and §4 hazard; three documents' "thirteen research notes" corrected to fifteen (47–61). The §7 review: `python -m tools_py.issues audit --stale-since 2026-09-24` OK; all twenty open issues read against the tree — none met, none closed, four commented (#25 the Python half's cause is fixed by Sprint 11's `587709d0`; #28 and #42 the audio-out branch merged as `ae862a8` and its finding is in KNOWN; #40 research/57 §3 and Task 8's agreement test as adjacent measurements); nothing closed since 2026-09-24; **one issue opened by the review, #48** (the `--out` hazard above), the highest number now; the `Sprint 12` milestone held no issue and is closed; the six issues Sprint 11 carried (#25, #26, #33, #37, #38, #42) were never in Sprint 12's milestone and are **ruled not carried twice** — a single-theme sprint took nothing from the backlog, so they remain `carried` once, in the backlog; the story's missing days are the one item carried twice, an owner question in HUMAN_TASKS (row O9 since 2026-09-25). Opened 1, closed 0, carried 0.

## Sprint 11 — CLOSED 2026-09-25 (merged to `main` as `v0.11.0`; the record of the sprint is `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`)

**Goal, as the plan stated it:** close the chat hole on both sides, answer the upstream-IOP question with a measured divergence table, land the r0004 groundwork, finish the public repository's owes. **Outcome:** all four, plus what the r0004 package's arrival opened (Task 19) and what the two demo discs opened (Tasks 7 and 7b). Sprint 12 ("the readable image", R263) already runs in the cloud on branch `sprint-12`; its local half is session socom-pc-6c's; this machine's checkout stays on `sprint-11`. *(Sprint 12 closed 2026-09-25: see its block above.)*

| Task | State | Evidence |
|---|---|---|
| 1 the open block | done | the record block, archived 2026-09-25 to `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md` |
| 2, 2b the chat receive wrap; the record readers bounded | done | `f2064d3`, `6aed718`; the two-instance chat proof (chain 11) |
| 3 the server clamp | done | `5b7d20e`, `4d7e481`; deployed to the project box 2026-09-23 06:58Z |
| 4 README and SECURITY narrowed | done | `3efa6a7` |
| 5 U1 the differential test's result | done | research/40 §9 (R245) |
| 6 U2 the upstream picks | done | Step 2 `f65da5f` (research/42); Step 3 all ten KEEP, each gated 3/3 (vram 15/15 where it applies; #241 also the online lane), the combined branch 891/891 and `s11_picks_keep_gate` 3/3, fast-forwarded `3bb866f4`, verdicts `6be03dac` |
| 7, 7b U3 the demo's symbols | done | `007d651`…`f1efa5b` (987 names matched, 479 safe proposals, research/44); 7b `716f969`…`7feebf0` (6 image-wide positional names, the Aug 2003 demo corroborates 704 pairs, research/45); applying them is Sprint 12's first task (R257, R263) — applied in Sprint 12 (Task 3; 476 of them, 3 held; gate `s12_names_gate` 3/3) |
| 8 U4 the fork's takeable pieces | done as 8a, 8b, 8c | 8a chain 11 (`s11_u_translators_gate`); 8b `2381c8a` (four subsystems per runtime, `s11_rtstate_gate` 3/3; the CD group and `g_iopHeapNext` left, KNOWN §4); 8c chain 12 (`s11_savestate_gate` 3/3) |
| 9 `build_revision.sh` | done | Task 9 (`5a2dc44`'s parent); step 0 makes the fixed map a build product `9ade5a3`, `06cccc9`, proven `s11_r0004_rebuild1` 3/3 with a clean tree |
| 10 the matcher and the address table | done | `a201221`…`86c2912`; the relinked-body method `e92691a` (81 % on r0004) |
| 11 the launcher's revision plumbing | done; 11b withdrawn | `098ef08`, `50831a0`; 11b waits on D1, reopened by R251 (HUMAN_TASKS O5) |
| 12 the leak gate's sixth leg | done | `c0e60e3`, `a021c52` |
| 13 the bug pipeline's GitHub half | done | `4c8ad5e`; two owner words in HUMAN_TASKS (O4) |
| 14, 15, 16, 17 the install page and FAQ; how it was built; the dead history and badges; the vendored baggage | done | the merge-forward `4732892`; `3615dbb`; `f4a2f87` |
| 18 the VM ring; the release-draft workflow | Step 2 done; Step 1 measured, carried | `4d10d71`; the VM's suites are not green there (issue #25, carried); the `v0.10.0` draft's archives are the owner's |
| 19 the r0004 capsule and package | done | the package obtained the sanctioned way and decoded (R250, R251); the ELF built; the reboot solved to its root — two of the capsule's stub words baked into the dumped image, undone from its decoded write stack (`07dc937`…`259bb48`); the harness made per-revision three seams deep (`91f245f`…`189b118`, `4ab6e9f`…`0a01ba3`); **gate 3/3 `s11_r0004_probe2` and `s11_r0004_rebuild1`; a scored online round on our own server `s11_r0004_round2c`**. Carried: D1 the distribution, Goal F, the capsule's r0004-layout stub table, what r0004 expects of its package data |
| filler: audio-out, the music dips | done | `ae862a8` after two fix rounds |
| also, none of it in the plan | done | the recompiler's cross-row continuation fix `5f3b354`, `77f02bc` (`s11_cfa_gate` 3/3); an override the runtime cannot execute is not an override `38161fd`, `1b47be2` (`s11_override_gate` 3/3, R256); the closed security row retired from the public docs on both branches (R253, the owner's); `--accept-pins` keeps every pin `fccf3b5d`; research/43b (what changed in r0004), /46 (the readable image, day one) |

**Carried out of Sprint 11.** To Sprint 12: the rename pass with its provenance sidecar (R257, R261), Task 7c (R260), BinDiff and the ccc types (R259, R262), the toml names into the generated output, research/61 §5's r0001 literals outside the per-revision table. To the owner, HUMAN_TASKS "Sprint 11 close — what needs you" (now in `docs/archive/HUMAN_TASKS-to-2026-09-25.md`, each item's live row in its table): D1, Goal F, the two bug-pipeline words, the `v0.10.0`/`v0.11.0` archives, the branch sweep (now with `sprint-11`), the VM ring, the five big engine routines' hand review, the Horizon box's unmodelled `MediusVersionServer`. To the backlog with the `carried` label and a comment each: issues #25, #26, #33, #37, #38, #42; the Sprint 11 milestone closed, Sprint 12's created.

**The close proof (chain 22, on the close commit `d8518bd0`):** the runtime rebuilt, the suites three times over (`PS2X_TEST_REPEAT=3`; C++ 881/881 and the Python suite 2,562 OK, the same numbers CI printed green on that commit for `secrets`, `linux` and `windows`), the r0001 gate **`s11_close_gate` 3/3** (exe `b74a6132…`). The one suite failure on the way was this close's own: the tracked story timeline out of step with STORY after the review's edit, regenerated (`d8518bd0`).

**The two reviews the close ran (DOC_MAINTENANCE §5 and §7), 2026-09-25:** The §5 review read every live document and applied 30 of its 36 rows (`8612c2d3`; two rows were code fixes that landed as `0061a2b0`, `a8329c5` and `6658d863`; the rest are this commit's): Sprint 12's existence written into every live document; GIT_STRATEGY's sprint-10 line and HANDOFF's first-hour CI line corrected; FAQ's Bluetooth attribution replaced by KNOWN §1's measured retraction; the two dangling gitlinks removed; STORY's three missing days stated in the document and carried; the audit's uncited KNOWN rows went 20 → 0 once the three rows below got their issues. The §7 stack review: 18 issues opened this sprint (#25–#42, the stack's birth under R252) and three at the close (#45 the accept-pins start-up write, #46 `movie_blocks.py`, #47 VU0 flag latency), 1 closed (#29), 20 open; the 6 in the Sprint 11 milestone carried to the backlog with the `carried` label and a comment each (#25 #26 #33 #37 #38 #42; none is in Sprint 12's plan), the milestone closed and Sprint 12's created; highest issue #47.

#### Sprint 11's rulings ledger, R245-R263 (reconciled at the close; this table is the one home)

Nineteen numbers, nineteen rulings: **no number is vacant and none is reused.** One was retracted on substance
(R249, by R251) after being half-corrected the same evening (R250); one is the owner's own (R253); and R263 moved the
naming programme to Sprint 12, so five of this sprint's rulings are carried rather than closed here. The working
notes behind this table are `.superpowers/sdd/2026-09-23-sprint-11/progress.md`.

| R | The decision (its own key words) | Where it is written | Status |
|---|---|---|---|
| R245 | "**option B is not scheduled**" — the real IRX agrees with our model on 1,775 of 1,794 calls, and 13 of the 19 disagreements are emulator gaps, so a 1,500–2,500-line native libsd is not justified | `plans/2026-09-23-sprint-11.md`, "Rulings made on the owner's behalf"; the row is `docs/KNOWN.md` §1 | stands — Task 5 closed on it: the two model alignments `7b44d70`, `776e423`, the streamer blind spot a filler row, the three #244 patches written up |
| R246 | "the chat bound's **install** is the proof Milestone S ships on; **the traversal is a filler row**" | same rulings section; `docs/KNOWN.md` §2 holds the row (issue #26) | stands — the traversal is still unobserved and carries as a filler item; the README claims only "bounded on the client, clamped on the server" |
| R247 | "**the vendored tree's baggage goes**" — `vita/`, `android/`, `ps2xStudio/` deleted, the four font headers generated at build time | same rulings section | stands; **done** (Task 17, `f4a2f87`) |
| R248 | "the r0004 patch is **PSRewired's resident capsule**, and the build applies it, not a package" | same rulings section; `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, the 14:30Z block | stands **as to what the capsule is** (ps2-packer ELF, encrypted code stack, `mc0:UPDATE.DAT` probe) — its second half, "not a package", is **superseded by R250 and R251**: the package exists and was obtained |
| R249 | "**'r0004' is the DNAS bypass**, which this build already has; no second recompilation; Task 11b withdrawn" | same rulings section; `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, the 16:00Z block | **RETRACTED on substance by R251** (2026-09-23 night), after R250 had already shown it half wrong. What survives of it: the decoder, the `PS2X_SOCOM2_DNAS_BYPASS` knob and the `versionString` correction, all landed |
| R250 | "**R249 was half right**: the DNAS bypass is the door, and the r0004 package is behind it, served by PSRewired" | same rulings section; `docs/archive/HUMAN_TASKS-to-2026-09-25.md`, the r0004 section ("Evening correction (R250)") | stands — and the route it named (PCSX2 + their pnach + their DNS, the update saved to the card, `APACHE00.ZDB` out with mymcplus) is the route that was walked the same night |
| R251 | "**r0004 is a real rebuild and its ELF exists**" — the package in hand and decoded, the overlays read through PINE, `build_revision.sh r0004` built the ELF (5,016,016 B, `62f4f877…`) | same rulings section; `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, the 02:5xZ block; `docs/archive/HUMAN_TASKS-to-2026-09-25.md`, r0004 D1 (row O5 of `docs/HUMAN_TASKS.md` since 2026-09-25) | stands; **done** — the r0004 gate is 3/3 (`s11_r0004_probe2`) and the build plays online on our server (`s11_r0004_round2c`). It **reopened HUMAN_TASKS D1** (the per-player pipeline is the owner's to accept) and left Task 11b moot |
| R252 | "**the known-issue stack opens on GitHub issues**" — every defined unresolved KNOWN defect a public issue cited from its row, `tools_py.issues audit` holding the stack to the documents, KNOWN still winning | same rulings section; `docs/GIT_STRATEGY.md` §7 and `docs/DOC_MAINTENANCE.md` §7 | stands; **done** (issues #25–#42; #29 closed by the owner the same night). Its audit is run at this close |
| R253 | **the owner's**: "one closed KNOWN §2 row and every pointer to it are **retired from the public documentation**; history and the old branch tips stay" ("history is fine") | same rulings section; `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, the 13:00Z block | stands; **done** on `sprint-11` (`0bf1a5d`) and on `main` (PR #43, `a548dd1`) |
| R254 | "the r0004 reboot is **an image defect, undone from the capsule's decoded write stack**, never patched per call site" | same rulings section; `docs/KNOWN.md` §2's r0004 row | stands; **done** — `tools_py/overlay_repair.py` (`07dc937`) in its stack-driven form after two re-reviews (`3bac4a2`, `3eba1b3`, `259bb48`); zero words change in r0001 |
| R255 | "**the loop lock goes to the r0004 critical path first**"; batch work yields after its current hold | same rulings section; `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, the 13:00Z block | stands — **spent**: the r0004 critical path is complete, and the lock ran the close's batch (ten picks, the rebuild proof) afterwards under the same rule |
| R256 | "**an override the runtime cannot execute is not an override**" — `dispatchSyscallOverride` falls through to the built-in when the handler is in no function table | same rulings section | stands; **done** (`38161fd`, `1b47be2`; r0001 gate 3/3 `s11_override_gate`). Finding 9 (`GetEntryAddress` still returns the unrunnable handler) is deliberately deferred |
| R257 | "the demo names apply to the function map in **`Class_Method` form, one reviewed commit at a build window**" — the 479 proposals, the `Mangled` column kept, the prefix matches reviewed by hand for the big engine routines | same rulings section; `docs/research/44-*` §2 | stands, **carried to Sprint 12 by R263**: the rename pass is Sprint 12's first task. Amended there already — `S12-R1` (the four defaults), `S12-R3`/`S12-R12`/`S12-R22` (a second mechanical signal replaces the hand reading, then the five big engine routines return to the owner's hand), `S12-R11` (the recomp half proved in the cloud), and 3 of the 479 measured wrong and held (`S12-R8/R9`, `S12-R17`, `S12-R20`) — **done in Sprint 12** (Task 3: 476 of the 479 applied, proven `s12_names_gate` 3/3) |
| R258 | "**Task 7b**: positional naming between anchors and the Aug 18 2003 demo as a bridge, lock-free, a second proposals file under its own rule, never the csv directly" | same rulings section; `docs/research/45-*` | stands; **done in Sprint 11** — R263 kept 7b here and it completed (`716f969`, `5388f05`, `80a3d60`, `7feebf0`: 6 image-wide positional names, the bridge corroborating 704 pairs and adding none, 167 tests). Its output file is Sprint 12's to apply |
| R259 | "**deferred to a future sprint**: Ghidra Version Tracking as a cross-check of the 987, and the ccc route for the demo's `.debug` types"; the voice-codec record (SOCOM 1 LPC-10, SOCOM II SASE, GSM nowhere) | same rulings section; `docs/research/44-*` addendum | stands **as amended by R262** (BinDiff in place of Version Tracking). **Carried to Sprint 12**, where both deferrals were taken up (BinDiff = S12 Task 6, ccc = research/50). One amendment owed here: the S12 Log's `LOCAL:` line on research/56 — the "Nellymoser" reading in KNOWN's voice-chat row, research/23, the Sprint 8 voice plan and two source comments is an **inference**, and the "11025 Hz / 58.05 ms" belongs to two other `lgaud` callers |
| R260 | "**Task 7c: vtable-slot matching through RTTI**, its own lock-free task after 7b lands, a third proposals file (pass `vtable-slot`)" | same rulings section; the peer's scripts, now `tools_py/research/symbols/` | **carried to Sprint 12** by R263, and by the ratified handoff (`b53f956`) it is the cloud session's, not local. Amended there by **`S12-R16`**: the key is the demo's own *qualified* RTTI string, 211 classes resolve (not 111), the vtable start is a fixed point, and the constructor half of the rule is **withdrawn** — **done in Sprint 12** (Task 4: 199 `vtable-slot` rows, research/60) |
| R261 | "R257's rename commit also writes **a tracked provenance sidecar** beside `recomp/socom2_ghidra.csv` (address, name, source pass, score, evidence); the csv itself keeps only `Name`" | same rulings section | **carried to Sprint 12** with R257. Amended there by **`S12-R13`/`S12-R4`**: the sidecar is the *one home* of a name and the recompiler reads it (`[general] names`), so the csv's `Name` column is never rewritten by the applier at all — R261's intent kept, its mechanism improved — **done in Sprint 12** (Tasks 2 and 3: `recomp/socom2_names.csv`, 1,840 rows, both audits 0 findings) |
| R262 | "**declined**: a custom Ghidra Function ID database, and r0004 as a version-tracking corpus"; **amends R259** — BinDiff replaces Version Tracking, the ccc types carry a layout-age caveat | same rulings section | stands — **the decline stands on its own reasons**; its "99.66 % identical" figure was **corrected in place 2026-09-25** (that is r0001's self-match, KNOWN §1; r0004 against r0001 is research/43b's ~81 % run, itself unreproducible per `S12-R5`). The BinDiff and ccc halves are **carried to Sprint 12** (done there, and narrowed by `S12-R22`/`S12-R23`) — **done in Sprint 12** (Task 6 and research/49 for BinDiff; research/50 and Task 7 for the ccc types) |
| R263 | **the owner's question answered**: "**the naming programme is Sprint 12, not Sprint 11**" — Sprint 11 keeps Task 7 and 7b; the rename pass, 7c, BinDiff and ccc move to Sprint 12, "the readable image", which opens with the rename pass so its gates run on the renamed tree | same rulings section; this file, the `next sprint:` line | stands; **done** — Sprint 12 closed 2026-09-25 with every task done and the proof green (`s12_names_gate` 3/3); the peer's measurement scripts are tracked at `tools_py/research/symbols/` |

*Paths written `plans/...` are relative to `docs/superpowers/`; all others are from the repository root. "Same rulings
section" means `docs/superpowers/plans/2026-09-23-sprint-11.md`, "Rulings made on the owner's behalf".*

**What changed state during the sprint:** R249 was **retracted** by R251 after R250 had shown it half wrong — the only
retraction in the range; R248's second half was superseded by the same pair; R259 was amended by R262 within a day; and
R263 carried R257, R260, R261 and the deferred halves of R259/R262 into Sprint 12. **Collisions: none. Missing: none.
Vacant: none.**

**Carried to Sprint 12** (the naming programme, R263): **R257**, **R260**, **R261**, and the deferred BinDiff/ccc halves
of **R259** and **R262**. R258's Task 7b was completed here; only its proposals file travels.

---

#### Sprint 12's `S12-Rn` rulings and `LOCAL:` lines that touch these rows (for the global sequence at the merge)

The Sprint 12 cloud session numbers its rulings `S12-R<n>` in `docs/superpowers/plans/2026-09-24-sprint-12.md` and <!-- docmaint: future -->
leaves the global numbering to the local controller at the merge (its §Rulings: *"the global counter is the local
controller's to fold in"*). These are the ones that amend a Sprint 11 fact or ask Sprint 11 for something; the rest are
internal to that sprint. Read `origin/sprint-12` for the full set.

| S12-R / `LOCAL:` | The decision or request (its own key words) | Where it is written | What it touches in Sprint 11 |
|---|---|---|---|
| S12-R1 | "the four naming defaults stand as the spec states them" — `Class_Method`, argument suffix only on collision, **no hand-named row ever renamed by a proposals file**, the 138 sub-64-byte pairs stay out | `plans/2026-09-24-sprint-12.md`, Rulings | **R257** — confirms its form and fixes its rule 5 |
| S12-R3 | "**no prefix pair is admitted on a person's reading**; R257's 'reviewed by hand for the big engine routines' is replaced for this sprint by a second mechanical signal" (`prefix+bindiff` or a vtable slot; never a prologue alone) | same, Rulings | **R257**, explicitly |
| S12-R12 | "an `offset-multiset` pass is Task 13 … and **an independent body key is a valid second signal for a prologue pair** (amends S12-R3)" — 44 of R257's prologue pairs admitted as `prefix+offsets` | same, Rulings | **R257**'s 159 prefix matches |
| S12-R22 | "**BinDiff confirms under a bounded rule and never proposes alone**; the big engine routines stay the owner's hand review (amends S12-R3 and D5)" — 21 of the 159 confirmed; `CMission::Init` 0.200, `ThrottlesPreTick` 0.006 | same, Rulings | **R257** (the hand review returns) and **R262** (BinDiff as the cross-check) |
| S12-R23 | "**BinDiff is not a confirming key for promotion** (narrows S12-R22), and a BinDiff contradiction of another lever's strict row is a dispute to read" | same, Rulings | **R262**'s "BinDiff replaces Version Tracking" — it is a second signal, not an oracle |
| S12-R8, S12-R9, S12-R17, S12-R20 (with S12-R10, retired by S12-R13) | **three of Task 7's pairs measured wrong and held** — row 478 is `MediusGetBuildTimeStamp` not `Net…`; `sceCdDiskReady` is 0x0018ef70 as the toml binds it; the UI binding table outranks the sub-64-byte `exact` anchor at 0x27a250; the applier keeps a tracked holds file | same, Rulings | **R257** — its 479 proposals become **476 with 3 held**, and one of the 987 anchors is withdrawn |
| S12-R11 | "a rename that moves a decoded range is accepted only when **the cloud's own recomp** shows no new `unmapped`/`unhandled` and no function dropped; and the recompiler is built and run in the cloud for that" | same, Rulings | **R257**'s "the commit carries a recomp, the runtime rebuild and the r0001 gate" — the recomp half moves off the local lock |
| S12-R13 | "**the sidecar is the one home of a name, and the recompiler reads it**; the csv's `Name` column is never rewritten by the applier" (amends S12-R4's letter; retires S12-R10, narrows S12-R11) | same, Rulings | **R261** — keeps its intent, replaces its mechanism |
| S12-R4 | "the csv and the sidecar are the one home of a name; **the toml's stub list stays a handler selector**, held to the csv by a test" | same, Rulings | **R261**, and **R263**'s "the toml names into the generated output" item |
| S12-R16 | "**Goal 3's rules are amended to what research/51 measured**" — the qualified RTTI string as the key, **211** classes not 111, the vtable start a fixed point, **the constructor rule withdrawn** | same, Rulings | **R260** (Task 7c's stated rule and yield) |
| S12-R5 | "research/43b's `match.json` rate (**81.1 %, 12,071 placements**) **is not reproducible from tracked inputs**"; the documented recipe gives 67.26 %, seed-derived 81.6 %; Task 5 commits a seed list | same, Rulings | **R251**'s r0004 carry and **R262**'s corrected number |
| S12-R2 | "the tools are installed **natively under `/home/user/tools/`**, not in a container, and **a refusal retires the goal**" (Ghidra 11.0.3, BinExport 12 patched for R5900, BinDiff 8, ccc) | same, Rulings | **R259**/**R262** — the route their deferred items actually took |
| S12-R25 | "**research/46 is the peer's day-one record; the consumers note is research/61**"; the handoff amended to "47 onward" | same, Rulings | the ratified Sprint 12 handoff's item 2 (Sprint 11's `b53f956`), where research 46+ had been given to the cloud |
| S12-R6 | "**research numbers 46–59 are Sprint 12's**; the sequence is shared with Sprint 11, **whose close writes no note**" | same, Rulings | this close — no research note is numbered here |
| `LOCAL:` 2026-09-25 morning (CI) | "**Sprint 11's to fix, in its tests**" — twelve Python tests (`test_gate_pins` ×10, `TestGateDiskRefusal`, `BuildRevisionRepairMapTest`) fail on every runner since `91f245f`/`aea1966` because `launch_revision` refuses with no game ELF; the proposed shape is `gate.launch_env(…, default_ok=True)` and a synthetic `SOCOM_GAME_ELF` naming `r0001` | same, Log (newest first) | **R251/Task 19's review fix** — `sprint-11`'s `linux` workflow has been red on every non-docs push since 2026-09-23 21:29Z; `sprint-12` goes green one push after this lands |
| `LOCAL:` 2026-09-24 late night (4) | "**Sprint 11's rows to amend**" — research/56: no image carries a "Nellymoser" string (only the `NellyNull` assert macro), so KNOWN's voice-chat row, research/23, the Sprint 8 voice plan and two source comments state an **inference**; and "11025 Hz / 58.05 ms" belongs to two other `lgaud` callers (the voice object opens at 8000 Hz, reads every 80 ms) | same, Log | **R259**'s voice-codec record |
| `LOCAL:` 2026-09-24 night (research/61 §5) | "**Sprint 11's to rule on** (an r0004 run reads r0001's place)" — r0001 addresses outside the per-revision table at `scripts/parity/env.sh:33`, `sim_walk_to_b.py:70`, the LOD globals `game_overrides_socom2.cpp:1926-1971`, `Kernel/Stubs/MPEG.cpp:1973` | same, Log | the per-revision hazard of **R251/R254** (`docs/HAZARDS.md` recompiler's defect class). `env.sh` was fixed since, by the online slice (`4ab6e9f`…`0a01ba3`); the other three stand |
| `LOCAL:` 2026-09-24 night (research/58) | "**R262's '99.66 % identical to r0001' is r0001's self-match** … the number in the Sprint 11 plan is the local controller's to amend in place" | same, Log | **R262** — amended in place 2026-09-25 (rides the close commit) |
| `LOCAL:` 2026-09-25 early | "**D5's hand review of R257's five big engine routines is a HUMAN_TASKS line**" — `CMission::Init` 0x002ad290, `CSealCtrl::ThrottlesPreTick` 0x005966a0, `CZSealBody::GetNodePos` 0x005df930, `CActionTxtrMachine::Open` 0x0021f850, `CNodeAction::Open` 0x002b4f40; a hand name goes in the sidecar with `Pass=hand` | same, Log | **R257** — filed: HUMAN_TASKS "Sprint 11 close — what needs you" item 7, and named with its five addresses in the "Sprint 12 close" section (both now in `docs/archive/HUMAN_TASKS-to-2026-09-25.md`; the live row is O11) |
| `LOCAL:` 2026-09-25 morning (the close of the cloud's side) | "**when Sprint 11 closes and `main` carries it**, merge `origin/main` into `sprint-12` and run the PROOF row's four commands in a worktree of `sprint-12`; the sprint merges to `main` after that proof, as a Sprint 12 PR the local controller opens" | same, Log | the merge and the batched proof window — Sprint 12's PROOF REQUESTED row (Task 3 Step 4: recomp, runtime, the C++ suite, the r0001 gate 3/3 with PINS MATCH) — **done 2026-09-25 05:40Z** (`83e9696c`, gate `s12_names_gate` 3/3 PINS MATCH; run on `sprint-12` merged with `origin/sprint-11` directly, before Sprint 11 reached `main`) |

*Sprint 12's own plan lists more `S12-R` numbers (R7, R14, R15, R18, R19, R21, R24 and the rest); they are internal to
that sprint's levers and touch no Sprint 11 row. `S12-R6` is the cloud's own statement that the two sprints share one
research-note sequence, which is why every number above is folded at the merge rather than renumbered now.*

## The standing backlog and the Sprint 10 ledger (kept live at the 2026-09-25 split)

*The Sprint 9, 10 and 11 records that stood between here and the Sprint 11 close were moved verbatim on 2026-09-25
(Sprint 13 Task R1, R268) to `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`: "Sprint 11 — the record of the sprint" (the task-by-task record, the worktree table, the timestamped blocks such as 14:30Z, 16:00Z, 02:5xZ and 13:00Z), "The close, 2026-09-22 evening → 2026-09-23 morning", "Sprint 10 — CLOSED 2026-09-23", "The order, reworked 2026-09-20", "Sprint 9, milestone P", "Sprint 9, milestone Q", "Sprint 10, REORGANIZED 2026-09-20" (with its chunk table, its road table and "Rulings (R181-R183)"), "The playthrough, 2026-09-22" (the R236-R240 blocks), the Sprint 10 and Sprint 11 drafts, "Rulings made on the owner's behalf (no plan of their own)" (R174-R178) and "The Sprint 9 record". A citation of any of those block names means that
file. The two blocks below stay because the standing backlog is the filler list this file must keep
(`docs/DOC_MAINTENANCE.md`, the first review's lesson 1) and the ledger says it is the one home of R181-R244;
Sprint 11's ledger R245-R263 stays above for the same reason.*

#### Standing backlog, carried from the roadmap 2026-09-23 -- superseded 2026-09-25

**Superseded 2026-09-25 by R265 and R267** (`docs/audits/2026-09-25-project-audit.md` §4). The eight-item filler list
that stood here (moved from `docs/ROADMAP.md` §6 on 2026-09-23; its text is in this file's history before the Sprint 13
close) is no longer the queue: `docs/BACKLOG.md` is the carry's one home (R267), and the rows R265 declined are in
`docs/backlog_ruled_out.txt` with their bars. Where each item went: 1, the EE soft-double chain, **declined** by R265
(`soft-double-chain`); 2, HLE audit leg three, **owned** by Sprint 13 Task C2 (the plan's C2 row); 3, the gameplay-state
probe, **declined as a gate leg** by R265 (`gameplay-state-probe`), and 5, its `rx`-hold teleport count, goes with it;
4, the online freeze, is issue #34 (`docs/HAZARDS.md` network), its `waitReadable` shape bounded by V7 (`160ffdae`) with the
console-peer run as its bar; 6, the two believed render rows, carry R265's retire-or-test bar (`render-believed-rows`);
7, voice, and 8, multiplayer security, are `docs/BACKLOG.md` rows (the `voice-*` rows, `multiplayer-security`).

**Resolved 2026-09-25:** the citation R243 makes, `docs/research/40-upstream-divergence.md` (`83c02d98`), is in this
tree; the note that said it lived only on `agent/upstream` is withdrawn.

#### Sprint 10's rulings ledger, R181-R244 (reconciled at the close; this table is the one home)

Sixty-four numbers, sixty-three rulings: **R229 is deliberately vacant** -- it was declared free in words when Q4's
rulings were renumbered to R211-R217, and no decision was ever issued under it. Nothing here is renumbered. The
working notes behind this table are `.superpowers/sdd/2026-09-22-sprint-10-close/report-rulings.md`.

| R | The decision (its own key words) | Where it is written | Status |
|---|---|---|---|
| R181 | "secret scanning, push protection and Dependabot alerts are **ON**", turned on by the controller under the owner's words | `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, "Rulings (R181-R183)" | stands |
| R182 | "rulesets on `main` and `sprint-*` … with one deviation: **no CODEOWNERS review** required and no bypass" | `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, "Rulings (R181-R183)" | stands |
| R183 | "the leak check is the monitor's rules **adapted for a SOURCE tree**, not copied" | `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, "Rulings (R181-R183)" | stands |
| R184 | "**the mid-sprint merge to `main`**" -- the hardening and the developer setup reach `main` before the sprint closes | `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, Sprint 10 reorganized | stands (merged `92b92c6`, PR #6) |
| R185 | "any drift **refuses**, whatever `--only` asked for" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q1b-gate-pins.md` §4 | stands |
| R186 | "the harness is **recorded, never compared**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q1b-gate-pins.md` §4 | stands |
| R187 | "an operator's extra `PS2X_*` variable **is a drift**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q1b-gate-pins.md` §4 | stands |
| R188 | "the first run that prints a mapping hash is **refused until accepted**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q1b-gate-pins.md` §4 | stands |
| R189 | "the state stream is **absorbed, not waited on**" on a latched stall; re-anchor when the window comes back | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q6-latched-stall-bound.md` §5 | stands |
| R190 | "`Present` is **droppable at the cap** on a latched stall" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q6-latched-stall-bound.md` §5 | stands |
| R191 | "the bounds: **512 rectangle pieces, 8 per key, 256 palettes, 4 MB**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q6-latched-stall-bound.md` §5 | stands |
| R192 | "**no launch from this branch**" -- the gate and the stall run are the controller's | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q6-latched-stall-bound.md` §5 | stands |
| R193 | "the mapping is **per profile**, and a default mapping is **not written and not sent**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-goal-8-controller-mapping.md` | stands |
| R194 | "the environment string is **the whole table or nothing**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-goal-8-controller-mapping.md` | stands |
| R195 | "the keyboard table is **data but not rebindable** from the page" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-goal-8-controller-mapping.md` | stands |
| R196 | "the sticks and Triangle's pressure are **not in the table**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-goal-8-controller-mapping.md` | stands |
| R197 | "'per-profile presets' is read as **the mapping saved per profile, nothing more**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-goal-8-controller-mapping.md` | stands |
| R198 | "**bind on RELEASE, B held cancels, a tap of B binds B**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-goal-8-controller-mapping.md` | stands |
| R199 | "the section switch is **launcher state, not a setting**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-goal-8-controller-mapping.md` | stands |
| R200 | "the override is a runtime **`replaceFunction` wrap**, not a `recomp/socom2.toml` stub; **no recompile**" | `docs/archive/sprints-7-12/2026-09-20-sprint-10-goal-9-online-credentials.md` | stands |
| R201 | "the persona name keeps **every character the game's keyboard has**" | `docs/archive/sprints-7-12/2026-09-20-sprint-10-goal-9-online-credentials.md` | stands |
| R202 | "the password is **capped at 12** in the launcher" | `docs/archive/sprints-7-12/2026-09-20-sprint-10-goal-9-online-credentials.md` | stands |
| R203 | "`PS2X_DEV` enters the harness **below the gate's env pin**, and the pin is **not widened** for it" | `docs/archive/sprints-7-12/2026-09-20-sprint-9-goal-3-knob-retirement.md` | stands |
| R204 | "`PS2X_INPUT_MAPPING` is **the eighteenth Shipping name**" | `docs/archive/sprints-7-12/2026-09-20-sprint-9-goal-3-knob-retirement.md` | stands -- and `docs/KNOBS.md` (generated) is the one home of the counts; two L documents that said 151/20 were corrected at this close |
| R205 | "`PS2X_LAUNCHER_API_BASE` is a **Dev** knob read through `ps2x::knob`" | `docs/archive/sprints-7-12/2026-09-20-sprint-9-goal-3-knob-retirement.md` | stands |
| R206 | `SchedTrace.cpp`'s two later helpers "are **migrated under rule 2**"; a no-raw-`getenv` check joins `test_knobs_registry` | `docs/archive/sprints-7-12/2026-09-20-sprint-9-goal-3-knob-retirement.md` | stands |
| R207 | "Every **Path-kind** knob is constrained to the portable folder, or refused -- **but not in this pass**" | `docs/archive/sprints-7-12/2026-09-20-sprint-9-goal-3-knob-retirement.md` | stands; its work is still queued |
| R208 | "the `[knobs]` line **never writes a credential's value**: `PS2X_SOCOM2_LOGIN_PASS` is printed as `[redacted]`" | `docs/archive/sprints-7-12/2026-09-20-sprint-9-goal-3-knob-retirement.md` | stands |
| R209 | "Q2's **Task 8 VM ring deferred** to the sprint close, **CI is the Linux ring**, the VM stays off" | road-table row 6 in `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, which carries its parenthetical ("R209 deferred it here") | stands -- it has no written block of its own; the VM ring did not run at the close and carries to Sprint 11 Task 18 |
| R210 | "the keyboard's **gameplay mapping** is honoured **only in developer mode**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q3-mouse-leaves-keyboard-narrowed.md` | stands; made, and Q3 merged `0c172a6` |
| R211 | "while the game runs the pad drives the launcher **NEVER**; the switch is the one button" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q4-launcher-rest.md` | stands |
| R212 | "the switch is **a binding, in BUTTONS**, with OFF beside it; **the guide by default**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q4-launcher-rest.md` | stands |
| R213 | "an Xbox pad's guide button is read from **XInput's ordinal 100** on Windows" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q4-launcher-rest.md` | stands |
| R214 | "**no header bar on the game window in this pass**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q4-launcher-rest.md` | stands; deliberately not done |
| R215 | the game window's title is "&lt;game&gt; -- SOCOM Unzipped" and "the harness's key moved with it" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q4-launcher-rest.md` | stands |
| R216 | "the launcher's cues play at **0.45 of their rendered level**, and the setting lives on AUDIO" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q4-launcher-rest.md` | stands |
| R217 | "the cache is **keyed by content, not by path**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q4-launcher-rest.md` | stands |
| R218 | "**Goal 4 is closed on its own stop rule, without a launch**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q5-headset-button.md` | stands |
| R219 | "Sprint 8's **R113 stands with its meaning corrected**, and the HLE is not changed for it" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q5-headset-button.md` | stands (it corrects R113, outside this range) |
| R220 | "the HLE's state word **stays at '1 once, then 2'**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q5-headset-button.md` | stands |
| R221 | "the one launch worth making is **a peek, not a proof**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q5-headset-button.md` | stands; still queued |
| R222 | "the console-replay case runs wherever `game/console_replay` exists and **says 'skipped' where it does not**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q7-residuals.md` | stands |
| R223 | "the card's cluster count is walked **once per game-side change, not per poll**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q7-residuals.md` | stands |
| R224 | "a card root that cannot take a file **answers 'no card' and leaves exit 72**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q7-residuals.md` | stands |
| R225 | "a write past the card's capacity is **refused whole with `sceMcResFullDevice` (-3)**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q7-residuals.md` | stands |
| R226 | "the microphone resampler walks the product **`phase + step * k`, not a running sum**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q7-residuals.md` | stands |
| R227 | "the stub helpers live in **namespace `stub_support`** with a global using-directive in the header" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q7-residuals.md` | stands |
| R228 | "the synthetic Linux packaging test asserts the **executable bit on Linux only**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-q7-residuals.md` | stands |
| R229 | -- | this table, and nowhere else since 2026-09-23 (it was declared free in words in the index line this table replaced) | **deliberately vacant**: no ruling was ever issued under this number. It is not missing and it is not reused |
| R230 | "the expectations file holds **sha256 digests of whole game files, in the tree**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-disc-to-elf.md` | stands |
| R231 | "a difference in the image's *shape* is **a note, not a refusal**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-disc-to-elf.md` | stands |
| R232 | "the four **DNAS cipher addresses are recorded rather than derived**" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-disc-to-elf.md` | stands |
| R233 | "the extracted tree is **verified by size** against the image's own directory records" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-disc-to-elf.md` | stands |
| R234 | "`CONTRIBUTING.md` now says **the game build is supported**, on the evidence of one disc image on one machine" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-disc-to-elf.md` | stands |
| R235 | "the from-nothing run **reused the toolchain archives** already in the main tree's bootstrap cache" | `docs/archive/sprints-7-12/2026-09-21-sprint-10-disc-to-elf.md` | **closed** by the genuine clone-to-game run recorded in `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md` |
| R236 | "the launcher's **default window is the game's own 640x448**" | `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, the R236 block | stands -- it **overturns R92**, Sprint 7's 2x default |
| R237 | "the prefilled login leaves the player path" | `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, the R237 block | **REWRITTEN 2026-09-23 by W10**: the persona survives a virgin-card restart, the saved password does not, so **the prefill stays** until the clean-exit launch settles which side loses the write |
| R238 | "a failure the player can see **must never be silent**"; `setMcCommandResultLocked` prints `[mc] command <n> FAILED …` in every build | `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, the R238 block | stands **as corrected in place** -- the first telling (reclassing two Dev knobs to Shipping) was wrong and the correction is kept beside it |
| R239 | "the online blop was charged to bank `0x00a00000`'s one-shots" | `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, the R239 block | **withdrawn by its own A/B** -- the bank is cleared |
| R240 | "the join driver **presses REFRESH LIST before JOIN GAME, and takes a channel**" | `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`, the playthrough block | stands; landed in `00d8348`, and R244 proves its path through the ladder |
| R241 | "the four external-repo items … **become Sprint 11 milestone U, early**" | `docs/archive/sprints-7-12/2026-09-22-sprint-10-close.md` | stands |
| R242 | "**Goal 4's per-map kill routes carry to Sprint 11 as [A] filler**; the speed-freeze half is re-measured from existing logs" | `docs/archive/sprints-7-12/2026-09-22-sprint-10-close.md` | stands -- it supersedes road-table row 3 in `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md` |
| R243 | "milestone U item 1's **step (b) is redefined as a differential test**, not a music-parity number" | `docs/archive/sprints-7-12/2026-09-22-sprint-10-close.md` | stands; committed `564ef99`. Its citation `docs/research/40-upstream-divergence.md` was on `agent/upstream`; in this tree since (`83c02d98`) |
| R244 | "**W8's fallback run is not run separately**: the ladder streak proves the join driver's R240 path" | `docs/archive/sprints-7-12/2026-09-22-sprint-10-close.md` | stands; committed `22d1900` |


**Below R181, kept verbatim from the index line this table replaced** (they are Sprint 9's and earlier, and no part
of this reconciliation): R179-R180 are Sprint 10 Goal 9's, recorded in its plan -- the password plain in
`config.json`, and prefill-never-submit; R178 is Q0's conductor grains (child sounds, registers, markers, from the
open reference), in `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`'s "Rulings made on the owner's behalf"; R177 is Q0's mix device buffer, 20 ms x 4, measured, the same block; R176 is P4's ADVANCED section --
what went in it and what did not; R175 is P6's -- the preset switch needs no launch and the server keeps advertising
its IP, the same block; R174 is Goal 12's split -- the mapping data path lands in Sprint 9 Q3, the UI is Sprint 10;
R152-R168 are reserved by the Goal 3 plan; R169-R171 are Goal 10's music fixes, COMMITTED in `eca5450`; R172 is Goal
10's declined proposal -- the concurrency cap, not taken, waiting on Q1's instrument; R173 is P3's, the pad display
staying live while the game runs.

**Three rulings changed state during the sprint and one changed state at the close:** R236 overturns R92 (Sprint 7);
R238 was corrected in place after its first telling was shown false; R239 was withdrawn by the very A/B it asked for;
and R237's premise was reversed by W10 on 2026-09-23. **Collisions: none. Missing: none.**

---

*The "Standing rules" block that closed this file until 2026-09-25 was deleted, not archived: it duplicated
`docs/HANDOFF.md` §5, the one home of the rules, and still said to push to `sprint-9` (the 2026-09-25 audit, D21).*

*Sprints 9 to 11: `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`. Sprint 8 and earlier: `docs/archive/CURRENT_SPRINT-to-sprint-8.md` (the record, unedited; nothing in either is an instruction).*
