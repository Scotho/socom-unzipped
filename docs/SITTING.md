# The owner's sitting

> **Generated -- do not edit.** Written by `python -m tools_py.sitting` from `docs/HUMAN_TASKS.md` (the O rows and the `last sitting:` stamp), the rulings `docs/RULINGS.md` shows (`tools_py.rulings.rows()`), `docs/BACKLOG.md` (the `Carried` column) and `docs/PLAYTEST.md` (its build block). Change a source and regenerate; `python -m tools_py.sitting --check` exits 1 when this file is stale.

The page as of 2026-09-26, for the sitting after the one of 2026-09-17: 16 open O rows (2 answered or struck); 99 active rulings since 2026-09-17; 3 issues carried twice; the build: **NOT BUILT**.

**How to answer.** One line per item, by number -- "O5: acceptable for v1", "R271: overturn", "#25: close" -- in the next session's prompt or as a note in `docs/STATUS.md`.

## 1. The O rows

16 open, 2 answered or struck. Each stands on its default until you answer; days waited are to 2026-09-26.

| O | the hand needed | the default the loop is on | first asked | days waited |
|---|---|---|---|---|
| O1 | The legal position on shipping `socom2.exe` and the decrypted `socom2_game.elf` | no public download; builds reach testers only by your hand | 2026-09-20 | 6 |
| O2 | The release archives for `v0.10.0`, `v0.11.0` and `v0.12.0` | the drafts stay empty; the loop may build the archives short of the upload (a backlog row); publishing is always your click | 2026-09-20 | 6 |
| O3 | What the public tree holds and under which terms | nothing moves; GPL-3.0 for the whole tree; unsigned (the FAQ says what SmartScreen shows); the deploy is yours, its wording drafted in `docs/INSTALL.md` | 2026-09-20 | 6 |
| O4 | The bug pipeline's words and the site | no reply is sent (G7: no); the triage routine never opens a public issue for a security report; the relays and the message unsent; no data page | 2026-09-20 | 6 |
| O5 | PSRewired and the mixed revisions | the community preset stays `COMMUNITY_SERVER_ADDRESS_TBC`; nothing connects to a server that is not ours; Task 11b stays withdrawn; the HDD maps are out of v1… | 2026-09-17 | 9 |
| O6 | The machine's windows and a second machine | the scheduled entry stays DISABLED and the ladder runs by hand at night under the lock (S13 O1); every online result is two instances on one host | 2026-09-17 | 9 |
| O7 | Your ears and hands on the current build | the loop does not wait (the listen gate has been bypassed since 2026-09-20); no profile viewer | 2026-09-17 | 9 |
| O8 | A PLAYTEST sitting on the current build | the loop rewrites PLAYTEST for each build it can hand over; the report's log box stays OFF; the download keeps its debugger | 2026-09-20 | 6 |
| O10 | Public actions upstream | drafts ready in `docs/research/assets/63-upstream-drafts/` (S13 U4; its README orders them): the argv and printf issues with patches, the export-table one advi… | 2026-09-25 | 1 |
| O11 | The naming programme's owner rows | the defaults stand; no hand names; the 148 stay applied; nothing is looked for | 2026-09-25 | 1 |
| O12 | The crouch default | the launcher's `l3` | 2026-09-25 | 1 |
| O13 | Repository settings and history | as they are; no history rewrite | 2026-09-20 | 6 |
| O14 | The merged-branch sweep | the branches and the ruleset stay | 2026-09-20 | 6 |
| O15 | Linux on real hardware | CI and the VM stand in; R107's number stays unmeasured; the VM half (the no-audio-device sentence in LAST RUN, the Linux bug-report send) is the loop's backlog | 2026-09-18 | 8 |
| O16 | Three issues carried twice | keep all three on the backlog; the next plan that names one takes it | 2026-09-26 | 0 |
| O18 | The private-inputs location | nothing changes; the fetch script stays; the loop touches nothing (R277) | 2026-09-26 | 0 |

Answered or struck (the row stays in HUMAN_TASKS as the record):

- O9: The story's five missing days -- Answered by default (keep), 2026-09-25: S13 S4 wrote them (`d4a8f0ea`, merged `1dcaa57b`); the `../scotho` site copy is the controller's.
- O17: Merge PR #61 (Sprint 13 -> main) -- Done 2026-09-26: you granted the scope; merged `6a82caaa`, tagged `v0.13.0`. The full row is in the archive.

## 2. The rulings since the last sitting

99 active rulings dated on or after 2026-09-17, oldest first. Each stands until you overturn it; an overturn is its number and the word. Left out: 202 active rulings have no date in the label, which cannot be placed before or after the sitting (`docs/RULINGS.md` lists every ruling).

- **R81** (2026-09-17) the guest clock counts wall time by default; the 2026-09-08 exclusion of VU1 and render back-pressure time is now `PS2X_CLOCK_EXCLUDE=1` for an A/B. -- overturn by number
- **R82** (2026-09-17) texture-cache CLUT ids are keyed on the palette's content (FNV-1a over the snapshot), not the CLUT serial. -- overturn by number
- **R85** (2026-09-17) the ten-launch lobby-rate measurement was skipped in favour of the twenty-map sweep and the ladder launches, which reached the lobby on 22 of 24 attempts with… -- overturn by number
- **R86** (2026-09-17) the sceMpeg HLE's demux always consumes its whole input; a video packet the game's stream callback refuses is taken anyway, an audio packet it refuses is set a… -- overturn by number
- **R87** (2026-09-17) the picture presenter drops pictures overdue by a whole interval instead of drifting behind real time, and the decode lookahead is eight pictures (two, the har… -- overturn by number
- **R88** (2026-09-17) a demux call that consumes nothing lets a ready guest thread of any priority run once (`EeScheduler::yieldToAnyReady`), a deliberate departure from the kernel'… -- overturn by number
- **R89** (2026-09-17) the launcher's server picker ships with placeholder addresses for the community and Unzipped servers, and the default preset stays Custom until ours is hosted. -- overturn by number
- **R90** (2026-09-17) the ISO handoff, the hostname resolution, the server's `-PublicIp` and the harness's `env.sh` landed in one fix wave under tests, gated once on the rebuilt exe… -- overturn by number
- **R91** (2026-09-17) `GL_ARB_clip_control` absent is a note, not a fallback trigger. -- overturn by number
- **R93** (2026-09-17) the drag bar is read over the drag window, not the whole stage. -- overturn by number
- **R94** (2026-09-17) the 2x comparison takes two launches of its own (640x448 and 1280x896, same boot screen at launch+40 s, both from the runtime's exported frame) instead of ridi… -- overturn by number
- **R95** (2026-09-18) a 0.15 stick dead zone is applied in all three host pad paths, not just SOCOM's own poll. -- overturn by number
- **R96** (2026-09-18) the page trace ran on the offline mission stage and on the online login stage of a launch that missed the lobby, not on an online gameplay round, because the l… -- overturn by number
- **R97** (2026-09-18) the 989snd PCM ring plays a 256-frame block only if the game rewrote it since the head last played it; a stale block is silence and counts (`pcmUnderruns`, on… -- overturn by number
- **R98** (2026-09-18) the mission dump's bar "RMS never at zero for 10 s under the HUD" is replaced by "no quieter than the pre-change baseline": the driven mission stage ends with… -- overturn by number
- **R106** (2026-09-18) the audio bar (the intro correlating with the disc at 0.99) is read from the gate's driven title stage in the VM (Task 10), not from the bare boot Task 8 plann… -- overturn by number
- **R107b** (2026-09-18) the Linux audio bar (the title music correlating with the disc at 0.99) is not readable in the VM and moves to the owner's real-GPU run (HUMAN_TASKS). -- overturn by number
- **R108b** (2026-09-19) per-call overhead is not the menus' cost, so the tile coalescer (Task 2) and its bar (Task 3) are not built. -- overturn by number
- **R109b** (2026-09-19) The launcher's default preset moves from `custom` to `unzipped` now that 3.143.65.100 is real — why: the Sprint 7 spec said the default switches "when ours is… -- overturn by number
- **R110b** (2026-09-19) The static IP ships in the launcher rather than a DNS name — why: no domain is owned and buying one is the owner's money; `horizon-ctl.sh public-ip` and the pr… -- overturn by number
- **R111** (2026-09-19) Task 2's test was written before the script but never seen RED (the script followed in the same step); its six cases were run GREEN only — why: the rule's purp… -- overturn by number
- **R123** (2026-09-19) the fix moves to the consumer. -- overturn by number
- **R124** (2026-09-19) a hard ceiling on pending GS command bytes. -- overturn by number
- **R125** (2026-09-19) the goal closes on the symptom, not on the 60 ms/s proxy. -- overturn by number
- **R139** (2026-09-19) a crouch shortcut. -- overturn by number
- **R173** (2026-09-19) the CONTROLLER page's live pad DISPLAY stays alive while the game runs -- it moves no focus, and a player who alt-tabs to check a pad should not find a dead pi… -- overturn by number
- **R151** (2026-09-20) the release executable keeps `-O1` for the generated code; `-Os`, and both LTO scopes, are not built. -- overturn by number
- **R208** (2026-09-21) The `[knobs]` line never writes a credential's value: `PS2X_SOCOM2_LOGIN_PASS` is printed as `[redacted]`, in developer mode too. -- overturn by number
- **R245** (2026-09-23) option B is not scheduled. -- overturn by number
- **R246** (2026-09-23) the chat bound's install is the proof Milestone S ships on; the traversal is a filler row. -- overturn by number
- **R247** (2026-09-23) the vendored tree's baggage goes. -- overturn by number
- **R248** (2026-09-23) the r0004 patch is PSRewired's resident capsule, and the build applies it, not a package. (amended: see the ledger) -- overturn by number
- **R250** (2026-09-23) R249 was half right: the DNAS bypass is the door, and the r0004 package is behind it, served by PSRewired. -- overturn by number
- **R251** (2026-09-23) R249 retracted on substance; r0004 is a real rebuild and its ELF exists. -- overturn by number
- **R252** (2026-09-23) the known-issue stack opens on GitHub issues. -- overturn by number
- **S12-R1** (2026-09-24) the four naming defaults stand as the spec states them: `Class_Method` with an argument-list suffix only on collision (D1); no hand-named row is ever renamed b… -- overturn by number
- **S12-R2** (2026-09-24) the tools are installed natively under `/home/user/tools/`, not in a container, and a refusal retires the goal. -- overturn by number
- **S12-R3** (2026-09-24) no prefix pair is admitted on a person's reading; R257's "reviewed by hand for the big engine routines" is replaced for this sprint by a second mechanical sign… -- overturn by number
- **S12-R4** (2026-09-24) the csv and the sidecar are the one home of a name; the toml's stub list stays what it is, a handler selector, held to the csv by a test. (amended: see the led… -- overturn by number
- **S12-R5** (2026-09-24) research/43b's `match.json` rate (81.1 %, 12,071 placements) is not reproducible from tracked inputs, and the sprint's r0004 carry rests on the documented reci… -- overturn by number
- **S12-R6** (2026-09-24) research numbers 46–59 are Sprint 12's, assigned in Task 0b's table; 60 is Task 4's note. -- overturn by number
- **S12-R7** (2026-09-24) the sidecar's backfill is 69 Ghidra rows, not 113 hand rows; the placeholder predicate is anchored and shared by the audit and the carry; uniqueness is scoped… -- overturn by number
- **S12-R8** (2026-09-24) a `string-set` pass is Task 12, and Task 7's row 478 is held out of the rename until a body read settles it. research/53 measured the set of shared strings a b… -- overturn by number
- **S12-R9** (2026-09-24) row 478 is wrong, and the applier keeps a tracked holds file. -- overturn by number
- **S12-R11** (2026-09-24) a rename that moves a decoded range is accepted only when the cloud's own recomp shows no new `unmapped` or `unhandled` continuation and no function dropped; a… -- overturn by number
- **S12-R12** (2026-09-24) an `offset-multiset` pass is Task 13 at 0.75, and an independent body key is a valid second signal for a prologue pair (amends S12-R3). research/54: the multis… -- overturn by number
- **S12-R13** (2026-09-24) the sidecar is the one home of a name, and the recompiler reads it; the csv's `Name` column is never rewritten by the applier (amends S12-R4's letter; retires… -- overturn by number
- **S12-R14** (2026-09-24) leading underscores are stripped where the live sanitiser would rewrite them, with research/47's `u`×k spelling only as the collision fallback. research/47's R… -- overturn by number
- **S12-R15** (2026-09-24) the UI script-binding table is a pass, Task 14. research/55 §4.2: both builds carry a table of (command string, handler) rows; the demo names 131 of its 147 ha… -- overturn by number
- **S12-R16** (2026-09-24) Goal 3's rules are amended to what research/51 measured. -- overturn by number
- **S12-R17** (2026-09-24) `sceCdDiskReady` is 0x0018ef70, as the toml binds it; Task 7's row for 0x0018ed78 is held, the third line of the holds file. -- overturn by number
- **S12-R18** (2026-09-24) a `callgraph` pass is Task 15, in two tiers, and two independent keys agreeing is the sprint's promotion rule. research/52: the caller side alone adds 45 pairs… -- overturn by number
- **S12-R19** (2026-09-24) a name is legal when the LIVE sanitiser returns it unchanged; the code generator's unused copy is not a bar. research/61 §1.5:… -- overturn by number
- **S12-R20** (2026-09-24) the UI script-binding table outranks a sub-64-byte `exact` anchor, and a held address is no anchor for any lever. -- overturn by number
- **S12-R22** (2026-09-24) BinDiff confirms under a bounded rule and never proposes alone; the big engine routines stay the owner's hand review (amends S12-R3 and D5). research/49: raw B… -- overturn by number
- **R253** (2026-09-24) one closed KNOWN §2 row and every pointer to it are retired from the public documentation; history and the old branch tips stay. -- overturn by number
- **R254** (2026-09-24) the r0004 reboot is an image defect, undone from the capsule's decoded write stack, never patched per call site. -- overturn by number
- **R255** (2026-09-24) the loop lock goes to the r0004 critical path first. -- overturn by number
- **R256** (2026-09-24) an override the runtime cannot execute is not an override. -- overturn by number
- **R257** (2026-09-24) the demo names apply to the function map in `Class_Method` form, one reviewed commit at a build window. (amended: see the ledger) -- overturn by number
- **R258** (2026-09-24) Task 7b: positional naming between anchors and the Aug 18 2003 demo as a bridge, lock-free, a second proposals file under its own rule, never the csv directly. -- overturn by number
- **R259** (2026-09-24) deferred to a future sprint: Ghidra Version Tracking as a cross-check of the 987, and the ccc route for the demo's `.debug` types; the voice-codec record is in… -- overturn by number
- **R260** (2026-09-24) Task 7c: vtable-slot matching through RTTI, its own lock-free task after 7b lands, a third proposals file (pass name `vtable-slot`, scored below `exact`). (ame… -- overturn by number
- **R261** (2026-09-24) R257's rename commit also writes a tracked provenance sidecar beside `recomp/socom2_ghidra.csv` (address, name, source pass, score, evidence), carried by… (ame… -- overturn by number
- **R262** (2026-09-24) declined, with the peer's reasons: a custom Ghidra Function ID database (it is `fingerprint.py` plus the callee-set pass re-implemented, and cannot cross the 7… -- overturn by number
- **R263** (2026-09-24) the naming programme is Sprint 12, not Sprint 11. -- overturn by number
- **S12-R21** (2026-09-25) a hold names an (address, proposed name) pair, not an address. -- overturn by number
- **S12-R23** (2026-09-25) BinDiff is not a confirming key for promotion (narrows S12-R22), and a BinDiff contradiction of another lever's strict row is a dispute to read, not a tie to i… -- overturn by number
- **S12-R24** (2026-09-25) a hold can un-apply; an alias is not a contradiction; the entry row keeps `entry`; a Ghidra-split tail is not a function. -- overturn by number
- **S12-R25** (2026-09-25) research/46 is the peer's day-one record; the consumers note is research/61. -- overturn by number
- **S13-R1** (2026-09-25) the order is V, R, H, C, U, S, N, O. -- overturn by number
- **S13-R2** (2026-09-25) lock-bound runs on the owner's nights are allowed, one at a time, never a game window when the owner has said they are at the machine, nothing that needs their… -- overturn by number
- **S13-R3** (2026-09-25) the frame-time pin is informational until three gates agree on its spread; the refusal rule is set then, from the numbers. -- overturn by number
- **S13-R4** (2026-09-25) a live write primitive jumps the order. -- overturn by number
- **S13-R5** (2026-09-25) a run whose stages FAIL sets no standard. -- overturn by number
- **S13-R6** (2026-09-25) the codex audit's work is dispositioned on its merits; its allocation to a second model, and the head-to-head that would measure it, are declined. -- overturn by number
- **S13-R7** (2026-09-25) process-specific loopback capture is not added as an audio instrument now. -- overturn by number
- **S13-R8** (2026-09-25) the link-resolving containment applies to the memory-card root only; the disc and host roots keep the lexical walk. -- overturn by number
- **S13-R9** (2026-09-25) a server name that does not resolve is a LAST RUN notice, not a process exit code. -- overturn by number
- **S13-R10** (2026-09-25) the oversized function bounds go to the backlog as issue #55, not this sprint. -- overturn by number
- **S13-R11** (2026-09-25) no cloud session was opened this sprint, so the [C] tasks are dispositioned without one: N3 is done by R7 (`docs/BACKLOG.md` is the carry's home); U3 (#253's e… -- overturn by number
- **R264** (2026-09-25) they keep those names — renumbering twenty-five rulings cited across fifteen notes and the plan would buy nothing and risk a wrong citation; the global counter… -- overturn by number
- **R265** (2026-09-25) R265 the four oldest backlog rows owned or declined; R266 the six issues Sprint 11 carried go once into Sprint 13's milestone; R267 one home for the carry (… -- overturn by number
- **R266** (2026-09-25) R265 the four oldest backlog rows owned or declined; R266 the six issues Sprint 11 carried go once into Sprint 13's milestone; R267 one home for the carry (… -- overturn by number
- **R267** (2026-09-25) R265 the four oldest backlog rows owned or declined; R266 the six issues Sprint 11 carried go once into Sprint 13's milestone; R267 one home for the carry (… -- overturn by number
- **R268** (2026-09-25) R265 the four oldest backlog rows owned or declined; R266 the six issues Sprint 11 carried go once into Sprint 13's milestone; R267 one home for the carry (… -- overturn by number
- **S13-R12** (2026-09-26) the close's issue-stack read, acted on. -- overturn by number
- **S13-R13** (2026-09-26) the frame-time pin stays informational; #59 carries with the measured reason. -- overturn by number
- **S13-R14** (2026-09-26) the carried-twice three go to the owner, the rest carry once to the backlog. #25 (the Linux VM suites; no Sprint 13 task), #26 (the chat bound's path; O2 resta… -- overturn by number
- **R269** (2026-09-26) an infrastructure sprint ahead of visible defects, in the order G, I, W, D, S, E, M. -- overturn by number
- **R270** (2026-09-26) KNOWN §4's standing hazards move to their own file (`docs/HAZARDS.md`, class L, headed by the area each bites), KNOWN keeping §1–§3. -- overturn by number
- **R271** (2026-09-26) an owner row that has stood through two sittings without an answer is closed by default at the next close, under a ruling, struck with the date and the default… -- overturn by number
- **R272** (2026-09-26) STATUS's log below its live block is archived verbatim and the changelog is generated from the merge commits and tags (`python -m tools_py.changelog`, class G). -- overturn by number
- **R273** (2026-09-26) sprint-local ruling namespaces are retired from this sprint on; the global counter in HANDOFF is the only one, and its second line in CURRENT_SPRINT goes (Task… -- overturn by number
- **R274** (2026-09-26) a held-out capture leg the implementing agents never see, twelve references under `scripts/parity/refs/heldout/`, taken by the controller at a quiet window, re… -- overturn by number
- **R275** (2026-09-26) at most two building agents at once, enforced by the queue (a third build ticket is refused with "queue full: do lock-free work"). -- overturn by number
- **R276** (2026-09-26) Sprint 15 is "borrowed confidence", opened from the confidence register at this sprint's close, its pair proposed beside this one (… -- overturn by number
- **R277** (2026-09-26) the private location that served the owner's ELF dumps to cloud sessions has no consumer and is the owner's to retire or rotate (HUMAN_TASKS row O18); the fetc… -- overturn by number
- **R278** (2026-09-26) while the lock is held or queued by other sessions' builders, lock-free tasks from Milestones D, S and M may run ahead of Milestone W; W's tasks start at the f… -- overturn by number

## 3. The issues carried twice

3 issues carried twice at `Carried` 2 or more in `docs/BACKLOG.md`: keep each on the backlog, or close it as not planned under a ruling.

- #25 (linux, carried 2) The Linux VM's suites are not green on the merged tree: four C++ and four Python cases
- #26 (harness, carried 2) No run has shown a received chat line crossing the client bound: the harness cannot open the chat box
- #42 (audio, carried 2) About 50 ms of the mission music is lost between the mixer's render() and the device, on any endpoint

## 4. The build

**NOT BUILT**: `docs/PLAYTEST.md` names no archive for the current tree; there is nothing to play yet.
