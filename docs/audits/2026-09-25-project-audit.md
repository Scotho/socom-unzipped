# Project audit, 2026-09-25 — the master list

*A dated snapshot (class S, `docs/DOC_MAINTENANCE.md` §1). Written on the night Sprints 11 and 12 closed, on the owner's
instruction to the local controller (session socom-pc-6c): "audit the entire structure of the project so far and
compile a master list of needed revisions, unfinished work, open agentic-possible tasks, improvements that have been
neglected — and spin up and start your own sprint 13, cleaning up docs as you go." Every row below points at the
evidence in one of six reports under `docs/audits/2026-09-25-project-audit/` (the reports are the record; this file
is the disposition). Sprint 13's spec and plan (`docs/superpowers/specs/2026-09-25-sprint-13-nothing-carried-twice-design.md`, <!-- docmaint: future -->
`docs/superpowers/plans/2026-09-25-sprint-13.md`) are what this list became.* <!-- docmaint: future -->

## 0. How it was made, and what it found in one paragraph

Six read-only agents, one area each, under one brief (`2026-09-25-project-audit/BRIEF.md`): the documents (D, 69
findings), the runtime, recompiler and build (F, 55), the harness and tooling (H, 50), the consolidated carry (C, 133
rows, 36 duplicates merged), external research (X, 34), and the product as a stranger meets it (S, 62). Every finding
cites `file:line` or a URL and quotes the line it rests on; the controller read every report and re-checked the ones
a decision rests on. **The shape of what they found:** the project's *code* is in better order than its *record*.
The runtime has no orphaned source and the launcher no TODO; the harness has 155 test files and 2,800 cases; the
naming programme left one applier, one sidecar and ten levers whose rules are code. What has rotted is the
*appending* documents — the sprint file (958 lines, 189 KB, 12 % live), HANDOFF §2 (twelve pick-up points, three of
them "now"), STATUS's "keep it short" block (30 KB), HUMAN_TASKS (699 lines, seven "Start here" generations) — and
the *carry*: 133 distinct unfinished items in six homes, of which the 21 GitHub issues cover about twenty; six
items carried through six sprints; four oldest backlog rows carried since Sprint 6 with nobody ruling "own it or
decline it". Outside: upstream PS2Recomp has been quiet for 38 days, but 27 of its open PRs were never evaluated,
among them a path-containment fix and four silent memory-corruption fixes in paths SOCOM uses; FFmpeg ships twelve
CVEs behind with no download hash; a SOCOM II browser client appeared on 2026-09-21. And the two claims every live
document made that night — "Sprint 11 is merged to `main` as `v0.11.0`" and "CI green" — were both ahead of the
facts when the agents read them (the PR was open; the suite was red on six tests in Sprint 11's newest test file, a
root cause the Sprint 11 controller then fixed).

## 1. The state of the record on the night (what the reports found wrong, not merely stale)

| # | claim | truth on 2026-09-25 06:00Z | where | disposition |
|---|---|---|---|---|
| 1 | "Sprint 11 is merged to `main` as `v0.11.0`" (five documents) | PR #49 open; `main` at `e63f9ba9`; no tag | D1, C1, S2, H7, F5 | true once PR #49 merges and the tag is pushed (the Sprint 11 controller's, in progress at the time of writing); the documents were written ahead of the act, which is the pattern to stop — Sprint 13 Task R1 adds a check that a "merged as vX" claim names a tag that exists |
| 2 | "CI green" on Sprint 11's close commit | the Linux suite red on every code push since `d1c0a10`; the green runs were docs-only skips | H1–H4, F4, S34 | root cause found by this controller (`test_gate_accept_pins` states no revision; its mocks leak on a failed setUp), fixed on `sprint-11` by its controller; Sprint 13 Task H1 makes a docs-only skip say `skipped`, not `success`, in the branch's summary the controllers read |
| 3 | STATUS's "Next:" line said Sprint 10 waited for its merge, from 2026-09-23 through Sprint 11's whole life and close review | wrong twice over | D49 | fixed in the Sprint 12 close (it points now, it does not state) |
| 4 | DEVELOPING: "`build.sh test` runs NO Python tests"; the clock knob's default backwards; "research/61–57" | all three wrong | D3, D4, F36 | Sprint 13 Task R2 (DEVELOPING rewritten as current truth) |
| 5 | README: "two players have finished online rounds"; the fps figure undated and pre-fix; the download blamed on the wrong decision | wrong | D35–D37, S6–S7 | Sprint 13 Task S1 |
| 6 | The ruling counter: R107, R109, R110 each issued twice; R114, R116, R124 have no text; two research notes numbered 43, none numbered 35 | the record is ambiguous in six places | D55–D57 | Sprint 13 Task R3 (recorded, not renumbered: a note beside each duplicate; 43a/43b in citations) |
| 7 | The community preset "stores the address"; the raw-address preset "stays as a fallback" | the preset is a placeholder; the fallback was removed 2026-09-20 | D16, D17, F52 | Sprint 13 Task R2 |

## 2. The master list, by theme

Columns: **who** — LOCKFREE (an agent without the lock or the game), LOCK (the machine, the lock, the game), CLOUD (a
game-less cloud session), OWNER (only the owner); **cost** S < 1 h, M < 1 day, L > 1 day; **disposition** — `S13 <task>`
(a Sprint 13 task), `#N` (an existing issue it closes or carries), `NEW #` (an issue Sprint 13 opens), `O<n>` (the
owner's sitting, §3), `R<n>` (ruled here, §4), `backlog` (written down, not scheduled). A row's evidence is the report
finding in its `source` column.

### A. The player's first ten minutes (what a player meets, in order)

| # | item | who | cost | source | disposition |
|---|---|---|---|---|---|
| A1 | The last four menu screens score 60–88 on every gate since Sprint 9 and the gate keeps passing | LOCKFREE (saved captures) | S | #30, S57, C83 | S13 V1 |
| A2 | The menus upload one atlas a frame as 1 KB tiles, 80–133 ms/s | LOCK | M | #32, S58, C98 | S13 V2 |
| A3 | Streamed full-screen images: DBP at packet offset 0x14 never read; loading-screen strips | LOCK | M | #31, S59, C97 | S13 V3 |
| A4 | The mission frame rate has no issue, no bar, no tracked number; README's 43–45 fps is a 2026-09-16 reading | LOCK | M | S7–S8, F51 | S13 V4 (a frame-time line in the gate's record, pinned as informational first) + NEW # |
| A5 | About 50 ms of mission music lost after `render()` on any endpoint; the quiet-window capture never made | LOCK (a quiet night) | M | #42, C58 | S13 V5 |
| A6 | The mission music degrades with time; needs a route and a ≥ 10-minute capture scored against PCSX2 | LOCK | M | #28, C59 | S13 V5 |
| A7 | A virgin card keeps the persona and loses the saved password; owed one clean-exit launch | LOCK | S | #27, C73 | S13 V6 |
| A8 | The online freeze's shape 2: `waitReadable` blocks the EE up to 10 s | LOCK | M | #34, C74, S29 | S13 V7 |
| A9 | Launcher wording defects: the blocked-LAUNCH reason for a missing path, exit 66 unreachable, voice described three ways, ABOUT credits SDL2, sample ids fail their own check, the crouch hint names a key the map binds elsewhere, three render scales in a comment for four | LOCKFREE | S | S9–S15, F53 | S13 S2 |
| A10 | The launcher default `crouchShortcut = "l3"` differs from the knob's registered default `off` | OWNER (which default) | S | F54 | O12 |
| A11 | `PS2X_SOCOM2_SERVER`: a name that will not resolve silently becomes 127.0.0.1; PLAYTEST admits the failure is invisible | LOCK | S | C91, S25 | S13 V8 |
| A12 | Mixed revisions bounce silently from each other's games; the launcher's mismatch line covers only server-vs-build | OWNER (two rooms or two servers) | M | C24, S28 | O5 |
| A13 | Fullscreen at desktop resolution as the window policy, scored by the gate (Q7 §3) | LOCK + OWNER | S | C104 | backlog (the owner's playtest list) |

### B. The record: documents and process

| # | item | who | cost | source | disposition |
|---|---|---|---|---|---|
| B1 | CURRENT_SPRINT.md is 958 lines / 189 KB, 12 % live; the archive split under DOC_MAINTENANCE's own rules, with the ruling-counter scan extended to the new archive file | LOCKFREE | M | D structure notes, D20–D26 | S13 R1 |
| B2 | HANDOFF §2's twelve pick-up points, three headed "now"; §4 and §10 two sprints stale; rule 4 hard-codes sprint numbers; "notes 01-34"; the first hour points at the closed plan | LOCKFREE | M | D9–D19, F6 | S13 R1 |
| B3 | STATUS's Current-state block is 30 KB under "keep it short"; Sprint 11 has no dated entry | LOCKFREE | S | D49 | S13 R1 |
| B4 | HUMAN_TASKS: 699 lines, seven "Start here" generations, 20 open checkbox items of which ≥ 9 are superseded and ~7 are agentic; a 2026-09-22 banner still on top; D-numbers reused three ways | LOCKFREE, then OWNER (one sitting) | M | D50–D53, D61, C125 | S13 R4 (pruned into one "what needs you" list, §3 of this audit is its draft) |
| B5 | DEVELOPING is a dated history in an L document: six wrong facts (Python tests, the clock knob, recomp ~10 s, the pre-redesign launcher, a removed knob, the spliced paragraph) and a `tools_py/` map of six things for 67 modules | LOCKFREE | M | D3–D8, D67, F36, H50 | S13 R2 |
| B6 | KNOWN: §2 is half settled rows (26 of 50); four §4 hazards describe fixed states; a §4 bullet says the mission stage FAILS; the Windows-only row lists the recompile step Sprint 12 ran on Linux; positional pointers ("§1's first row") rotted | LOCKFREE | M | D27–D34, D68, S45, S55 | S13 R5 (a full read of KNOWN, the first since 2026-09-23) |
| B7 | README, GIT_STRATEGY, LOOP_PROMPT, PLAYTEST, ROADMAP §6, STORY's closing lines, the archive README, SECURITY's hash: the stale sentences the reports list | LOCKFREE | S | D35–D48, D65, S24, S42–S44, S50 | S13 R2 / S1 |
| B8 | The ruling duplicates (R107, R109, R110) and the missing texts (R114, R116, R124); research 43 ×2, 35 missing | LOCKFREE | S | D55–D57 | S13 R3 |
| B9 | `docs/process-audit.md` and `docs/AUDIT-2026-09-17.md` overdue for `docs/audits/`; 4 specs and 25 closed plans still under `docs/superpowers/`; the codex task-allocation audit triaged by nothing | LOCKFREE | S | D62–D64 | S13 R1 (moves) and R6 (the codex audit's six assignments read against this list) |
| B10 | The carry has six homes and issues cover a sixth of it; most plans were never ticked; "carried twice" applies only to issues in a milestone | LOCKFREE | M | C structure notes | S13 R7: one carry home (this list's successor: `docs/BACKLOG.md`, generated from the issues plus the ruled-out rows) and `issues.py carry` | <!-- docmaint: future -->
| B11 | A "merged as vX" claim, a suite count, a worktree list: duplicated facts with no home; a size ceiling nobody enforces | LOCKFREE | S | D structure notes | S13 R1 adds a docmaint check (byte ceilings on the four appending documents; a tag-existence check for "merged as v") |
| B12 | The story's five missing days (three of Sprint 11, two of Sprint 12), carried twice | LOCKFREE to write; OWNER to keep or drop | M | D54, S49, C128 | O9; S13 S4 writes them if kept |

### C. The harness and the lock

| # | item | who | cost | source | disposition |
|---|---|---|---|---|---|
| C1 | The lock has no queue; a 5 s poller beats a 60 s poller; a chain's steps release between them; `run_detached` cannot wait | LOCKFREE (code + tests), LOCK (the rollout) | M | #36, H8–H10, C76 | S13 H2 (the ticket queue, the design in H9; a rollout procedure for a script that waiters run by offset) |
| C2 | `--wait N` is a retry count while the usage says minutes | LOCKFREE | S | #35, H11 | S13 H2 |
| C3 | `ladder_job.sh` checks then takes; hard-codes the main checkout | LOCKFREE | S | #37, H12, H14 | S13 H2 |
| C4 | The quiet marker is per checkout while the lock is machine-wide | LOCKFREE | S | H13 | S13 H2 |
| C5 | `--accept-pins` writes the standard at start-up | LOCKFREE | S | #45, H37 | S13 H3 |
| C6 | Captures record none of their `PS2X_*` environment | LOCKFREE | S | #38, C78 | S13 H3 |
| C7 | `PS2X_PEEK` caps at 64 words silently | LOCKFREE (runtime build to prove) | S | #39, F16 | S13 C3 |
| C8 | `movie_blocks.py` is wired into nothing; 28 modules invoked by nothing; four `patch_*.py` that write into the vendored tree; two 2026-09-04 logs tracked in `tools_py/`; research scripts with the owner's absolute paths | LOCKFREE | S | #46, H27–H30 | S13 H4 (retire or document each; `patch_*` archived) |
| C9 | The console-replay GL test never ran and its dump is gone — or Q7 made it run (the record contradicts itself) | LOCK | S | #41, C84 | S13 H5 (settle which; delete or fixture) |
| C10 | Raw r0001 addresses outside `guest_addresses.py`: `music_state_poll` (8), `motion_pack_check`, `cam_poll`'s default spec, `verdict_replay`'s fourth copy, `verdict_core`'s pointer mode; `env.sh` defaults to a LAN address | LOCKFREE | M | H19–H23, F12 | S13 H6 |
| C11 | 51 of 58 reference PNGs in no pin standard; one unused | LOCKFREE | S | H24–H26 | S13 H3 |
| C12 | The scheduled ladder is disabled and has not run since 2026-09-23; three large changes since; the 20-map queue last ran 2026-09-16/17; the mixed-match legs 2026-09-20 | LOCK (nights) + OWNER (the schedule) | M–L | H15–H17, C87 | S13 O1 (one ladder run and one mixed-match leg on the renamed tree at night); the schedule stays O6 |
| C13 | The Python suite: 11.5 min locally and on the busy list; no lock-free fast subset; ~30 skip sites need git-ignored run output; 35 modules with no test; `fix_ghidra_csv` on the build path untested; no dependency manifest; `build.sh` calls bare `python` | LOCKFREE | M | H31–H36, F35 | S13 H7 |
| C14 | `issues.py` lacks `carry`, milestone close/open and the tally; the audit only sees `HAZARD`/`Open:` headlines; the bug-report skill names eight labels of twelve | LOCKFREE | M | H46–H48 | S13 R7 |
| C15 | Chat traversal: no run has shown a received line crossing the client bound; a harness chat step | LOCK | M | #26, C72 | S13 O2 |
| C16 | R221: one peek of the talk-slot bytes in a live round | LOCK | S | C53 | S13 O2 (rides the same round) |
| C17 | Goal 3 tasks 5 and 7 (the parked opponent; "seen by the other"); Goal 4's per-map kill routes; the speed-freeze re-measure from logs | LOCK / LOCKFREE (the re-measure) | M–L | C85–C86 | backlog, except the re-measure → S13 H3 |

### D. The runtime, the recompiler, the build, the supply chain

| # | item | who | cost | source | disposition |
|---|---|---|---|---|---|
| D1 | CI never compiles `game_overrides_socom2.cpp`, `socom2_crypto.cpp` or the runner | LOCKFREE | S | F7, F41 | S13 C1 |
| D2 | 20 stubs bound by address whose whole body throws; nothing records whether the game reaches them | LOCK (one instrumented run) | S | F1 | S13 C2 |
| D3 | The after-return trap: `socom2_RtNetConfigInit` and seven traces read or write after the original returns | LOCKFREE (code) + LOCK (gate) | S | F10, F11 | S13 C3 |
| D4 | Hook targets and address-table fields named in code but not in the sidecar (~30); four offsets research/50 named still raw | LOCKFREE, proof at a window | S | F13, F14, C43 | S13 N1 |
| D5 | Three bare-cast FTOI sites; the NaN rule; the emitter's `shift == 0` arm; PMULT row | LOCK | S | #33, C95, C96 | S13 C4 |
| D6 | `PS2X_HLE_STATS`/`CALL_TRACE` miss tail calls; nine toml stubs bind nothing | LOCK | M | #40, C81 | S13 C4 |
| D7 | `build_revision.sh --out` drops the names sidecar; an unresolved names file is only an info line | LOCKFREE (test) + LOCK (message) | S | #48, C37 | S13 N2 |
| D8 | `build.sh` rewrites the tracked map in place on every recomp; `socom2_r0004.toml` and `socom2_ghidra.toml` are tracked build products; `socom2.toml` says "generated" | LOCKFREE | S | F28, F30, F32, F33 | S13 C5 |
| D9 | FFmpeg `n7.1-241205` ships twelve CVEs behind; downloaded with no `URL_HASH`; nine FetchContent pins by mutable tag; CI's pip and apt unpinned | LOCKFREE (pins) + LOCK (the FFmpeg move needs a gate) | S–M | X25–X28, F38–F40 | S13 C6 |
| D10 | Vita/Android CMake and sources; `rajdhani_bold.h` generated unused; five other-game IOP modules; the nested upstream workflow; the duplicated Ghidra script | LOCKFREE | S | F20, F21, F24, F26, F27, C101 | S13 C7 |
| D11 | `ps2HostProfStart` defined in the game file; the test binary's stand-ins; libpad2/msifrpc/crypto HLE with no unit test | LOCKFREE | M | F8, F9, F22 | S13 C8 |
| D12 | The CD group and `g_iopHeapNext` per-TU copies (8b's leftovers), no issue | LOCK | M | F23, C99 | NEW # (backlog) |
| D13 | 114,399 `unhandled-instruction` lines never classified; silent zeros for unmapped COP0/FCR/VU control registers | CLOUD | M | F2, F3 | S13 N3 (a census; the Ghidra-bounds fix stays backlog) |
| D14 | VU0 macro-mode flag latency (#47); the invocation stack pool never frees (Q7 §3); the display environment/PMODE/zbp darker than the console; GS local→host readback; research/25's outstanding items; the soft-double chain; HLE leg three; the gameplay-state probe; the two believed render rows | LOCK | L each | #47, C102–C115 | §4: R265 rules on the four oldest; the rest backlog with the `carried` label and their closing bars written |
| D15 | LTO and `-Os` never built for the release; the size measurement promised to the owner | LOCK | M | C106, C107 | backlog |
| D16 | R256's finding 9: `GetEntryAddress` still returns the unrunnable handler | LOCKFREE | S | F49, C29 | S13 C3 |
| D17 | Stale code comments: the peek help's retracted actor chain; the music trace's r0001 names; the overrides header "r0001-only"; "Nellymoser" ×2; the raylib "4.2.0" joke; the DNAS `$v0` comment | LOCKFREE | S | F15, F17, F19, C30, C52, X28 | S13 C3 |
| D18 | No tracked benchmark, budget or fps bar | LOCK | M | F51 | S13 V4 |

### E. Upstream and outside

| # | item | who | cost | source | disposition |
|---|---|---|---|---|---|
| E1 | 27 open upstream PRs never evaluated (#205–#225, #228, #233, #235, #239, #242, #253); three already covered in our tree and only need recording (#218, #215, #208) | CLOUD/LOCKFREE (triage), LOCK (any pick) | M | X1–X6 | S13 U1 (research/63: the table, verdicts; picks by ruling) |
| E2 | Upstream #239 path containment: parent traversal and symlinks resolving outside `hostRoot`/`cdRoot`/`mcRoot`; SECURITY.md puts the class in scope; ours unchecked | LOCKFREE | M | X7 | S13 U2 (a test first; a fix if it fails) |
| E3 | Upstream #217 (SIF RPC aliasing), #222 (time-slice vs DI/EI), #223 (zero-QWC END tag), #224 (DMAC bit 31), #216 (the heap cap) — silent-corruption fixes in paths SOCOM uses | LOCKFREE (diff) + LOCK (gate) | M | X5, X6 | S13 U1 |
| E4 | Upstream #253: drop the functions header from every generated file so a rename does not rebuild everything | CLOUD (recomp) + LOCK (runtime build) | S | X3 | S13 U3 |
| E5 | The three #244 patches "upstream-reportable", never reported; the ten KEEP picks unmerged upstream with no note from us; the BinExport R5900 defects unreported | OWNER (public actions) | S | X9, X10, X20, F48 | O10 (drafts prepared by S13 U4) |
| E6 | PSRewired: `r0004nodns.elf` never recorded; **Memdusa** — a public exploit in which a server sends a payload the game loads, with SOCOM II's domain in its list; what our client does with such a packet is written nowhere | LOCKFREE (read the client's handler; private until assessed) | M | X12, X13 | S13 U5 (a private note first, under SECURITY.md's process; public only when the finding is bounded) |
| E7 | Horizon: the base commit `1a7b9cd` recorded nowhere; open PR #35 (graceful disconnect) the one candidate | LOCKFREE | S | X14, X15 | S13 O3 |
| E8 | `Jaabrakus/socomrebirth` (2026-09-21): a SOCOM II browser client on Play!, a tester in a PSRewired match; `BLVCKBURN/socom-native` (SOCOM 1, cite-only); Hidden Palace's Jul 9 2002 SOCOM 1 press beta | OWNER (to know) | S | X21–X23 | O11 (recorded in research/63) |
| E9 | BinExport `main` builds against Ghidra 12.x: retire the second Ghidra install; DEVELOPING pins "12.1" where only 12.1.3 works | CLOUD | M | X18, X19 | S13 N4 |
| E10 | PCSX2-MCP verdict only in agent memory; nlohmann "as fetched" vs `v3.11.3`; a 404 research citation; no external-watch table | LOCKFREE | S | X16, X27, X32, X structure | S13 U1 (the watch table) |

### F. The stranger, the contributor, the tester

| # | item | who | cost | source | disposition |
|---|---|---|---|---|---|
| F1 | No issue carries `help wanted` or `good first issue`; 12 of 21 rest their evidence on the owner's git-ignored logs; a third of the tracker is the owner's lock | LOCKFREE | S–M | S30–S33, D59 | S13 S3 (labels on #39 #40 #46 #48 and the U/E tasks' new issues; fixtures for the twelve; the lock issues kept but marked internal) |
| F2 | Four Dependabot PRs open and failing since 2026-09-21 | LOCKFREE (rebase, CI) then the controller merges | S | S35 | S13 S3 |
| F3 | GitHub's default branch has no INSTALL or FAQ; nothing to download; the v0.10.0 draft has no assets; the release-draft workflow's verify half never ran | OWNER (D2, the archives) | M | S1, S3, C2, C3 | O1, O2 |
| F4 | `main`'s ruleset needs 0 approvals while CODEOWNERS says every change is reviewed; Dependabot security updates disabled; no homepage, topics or Discussions; SECURITY's one-week promise has no mechanism | OWNER | S | S39–S41, S46 | O13 |
| F5 | The Linux tarball ships ~76 distro libraries with no notices row; the notices test checks `.dll` only | LOCKFREE | M | S47 | S13 S5 |
| F6 | The story's frames and video are outside the disc-derived-bytes audit | OWNER (the H7 decision covers it) | S | S48 | O3 |
| F7 | The launcher's reply promise vs the never-reply policy; the post-send invitation to a public issue vs SECURITY; the site relays unconfirmed; the moderator's confirmation pending since 2026-09-23 | OWNER | S | S16–S19, S22, C15, C16 | O4 |
| F8 | No account/data page: what the server keeps, how to reset a password | OWNER (policy) then LOCKFREE (the page) | M | S20 | O4 |
| F9 | INSTALL/FAQ omit the GAME VERSION row; FAQ's Linux list lacks `curl` and the X11-only switch; exit 67's reachability | LOCKFREE | S | S9, S26, S54 | S13 S1 |
| F10 | PLAYTEST names a 2026-09-21 build and decisions already made; steps 1, 2, 4, 5, 8, 10, 12–14 have no recorded answer | LOCKFREE (rewrite) then OWNER (a sitting) | S | S24, C126 | S13 S1; O8 |

### G. Audio and voice

| # | item | who | cost | source | disposition |
|---|---|---|---|---|---|
| G1 | The audio parity check as a gate stage; its first PASS (31/48 since 2026-09-20) | LOCK | M | C61 | S13 V5 (the DEVICE-dip count pinned as informational first) |
| G2 | Level residuals (bed 7–12 dB under; the title ring; movie audio 18 dB low); cue 4 held 120 s on the console; five emitters at volume 0; R172's concurrency cap; research/36's fix list items 4, 5, 7; R178's unmodelled grains; Q7's audio residuals; the per-stage sound fixture | LOCK / LOCKFREE (36's 5 and 7, the fixture) | M each | C62–C68, C71 | S13 V5 takes research/36's doc items and the fixture; the rest backlog with bars written |
| G3 | Voice: hearing the other player (the Sprint 8 plan's Task 5, never built); SetRecordGain; the DME framing; the promised research/35 | LOCK | M–L | C54–C57 | backlog (a sprint of its own when the owner names voice) |
| G4 | The owner's listens (six sprints owed) | OWNER | S each | C60 | O7 |

### H. The naming programme's follow-ups (cloud-able)

| # | item | who | cost | source | disposition |
|---|---|---|---|---|---|
| H1 | `hostprof_diff.py` counts generated code by the `FUN_` prefix; the rename landed without the fix | LOCKFREE | S | C42 | S13 N1 |
| H2 | The `// Function:` header wording and a header on named stubs; `build_revision --out` (see D7) | CLOUD + LOCK proof | S | C34 | S13 N2 |
| H3 | The r0004 build with its own sidecar and its gate (Task 3 Step 4's item 5) | LOCK | M | C25 | S13 N2 (run at the first quiet window; the chain exists) |
| H4 | The 518 loose rows: a second independent lever; a 7c file for r0004 derived, not carried; the matcher's MMIO guard; research/45's lead-list corrections; 7c's anchor count re-run; hand-name candidates; toml hygiene (41 non-rows, 26 wrong names); csv row extents (the split at 0x00183024, 64 rows inside vtable data) | CLOUD | S–L | C31, C28, C45–C47, C38, C39, C36 | S13 N3 (a cloud session's plan, if one is opened) else backlog |
| H5 | 148 of 236 slot namings rest on equal counts with no fixed point — hold them? Whether to look for a named Aug 28/Nov 25 build; the tail-truncated demo images | OWNER | S | C48, C50, C51 | O11 |
| H6 | A `Pass=hand` proposals file for the five big engine routines | OWNER (the read) | S | C32, D5 | O11 |

### I. Online, the server, the box

| # | item | who | cost | source | disposition |
|---|---|---|---|---|---|
| I1 | The box-as-a-service layer (backup cron, health, off-box pull) lives only in the git-ignored `vm/lightsail/`; the off-box backup pulled once; no machine-readable record of the deployed server commit; `server/README` stale three ways; the chat clamp unmarked | LOCKFREE (repository half) + OWNER (a backup pull) | S–M | H40–H45, C18 | S13 O3 |
| I2 | Horizon does not model `MediusVersionServer` and three other messages both revisions send | OWNER (schedule) | M | C17 | O5 |
| I3 | The two-machine match, never played (six sprints) | OWNER | M | C89, H18 | O6 |
| I4 | The free-plan credit ends around March 2027 with no reminder | OWNER | S | C20 | O13 |
| I5 | Multiplayer security beyond the chat hole is unaudited | LOCKFREE (a read audit, private) | L | C116 | S13 U5's second half if the first bounds it; else backlog |

## 3. The owner's sitting — every decision in one list, with the default the loop is on

These are the rows the loop cannot take further. Each has stood through two or more sprints; answering them in one
sitting is what turns most of the carry into closures. The loop proceeds on the default in the third column.

| O | decision | the default the loop is on | rows |
|---|---|---|---|
| O1 | **D2, the legal position on shipping `socom2.exe` + `socom2_game.elf`** — it blocks every public download | no public download | A/F3, C5 |
| O2 | The release archives for `v0.10.0`, `v0.11.0`, `v0.12.0`; the verify half's first real trial | the drafts stay empty; the loop can build the archives short of `gh release upload` | C2, C3 |
| O3 | H7-A/H7-C (disc-derived bytes in the tree: fixtures, ~240 pictures, the story's frames and video); D3 (the licence split); D4 (`docs/dev/`); D5 (signing); D6 (the landing page's deploy) | nothing moves; unsigned; GPL-3.0 for the tree | C6–C10, S48 |
| O4 | The two bug-pipeline words (I1, I2); the site relays; the moderator's confirmation; what the server keeps about players | no reply promised; no public-issue invitation for security; no data page yet | S16–S22, C15, C16 |
| O5 | D1 (the r0004 distribution), Goal F (PSRewired's answer), two rooms or two servers for mixed revisions, `MediusVersionServer` on the box | the community preset stays a placeholder; nothing connects to a server that is not ours | C21–C24, C17 |
| O6 | The ladder's schedule window; the two-machine match; the VM evening (#25) | the ladder runs by hand at night; the VM stays off | C87, C89, C124 |
| O7 | The listens (six owed); the four Q4 tries; the CONTROLLER page on a real pad; the prefilled login with the real persona | the loop does not wait | C60, C119–C122 |
| O8 | A PLAYTEST sitting on the current build | the loop rewrites PLAYTEST for the build it can hand over | C126 |
| O9 | The story's missing five days: keep (the loop writes them) or drop under a ruling | keep; written by an agent from the record (S13 S4) | C128 |
| O10 | Public actions upstream: file the three #244 patches, note our verdicts on the ten picks, report BinExport's two R5900 defects | drafts prepared; nothing filed | X9, X10, X20 |
| O11 | The naming programme's owner rows: the seven defaults D1–D7; the 148 equal-count slot namings; the five routines' hand read; whether to look for a named 2003 build; the truncated demo images | the defaults stand; the 148 stay applied; nothing is looked for | C32, C33, C48, C50, C51 |
| O12 | The launcher's crouch default (`l3` in the launcher, `off` in the knob) | the launcher's `l3` (the owner set it 2026-09-20) | F54 |
| O13 | Repository settings: 0 approvals vs CODEOWNERS; Dependabot security updates; homepage, topics, Discussions; SECURITY's one-week promise; the free-plan credit reminder; the commit author e-mail; `simulated.db` and the chat-path mechanics in public history | as they are | S39–S41, S46, C11–C13, C20 |

## 4. Rulings made here (the global sequence; the owner can overturn any)

- **R265 (2026-09-25) — the four oldest backlog rows, own or decline (ROADMAP §5's ask, carried since Sprint 6):**
  the EE soft-double chain and `__ieee754_rem_pio2f` are **declined** until a gate, a control round or a player
  names a numeric defect that points at them (six sprints without one is the evidence); HLE audit leg three is
  **owned**: Sprint 13 Task C2 takes its bounded list (the consumers of research/20's flagged rows) together with the
  throwing-stub census; the gameplay-state probe is **declined as a gate leg** — the ladder, the twenty-map queue and
  the online verdict are the correctness legs the project built instead — and its one live number, the `rx`-hold
  teleport count, becomes a backlog issue with a bar; the two believed render rows (the transition strip, the
  intro-cinematic freeze) get a retire-or-test bar: three gates and three ladder runs on the renamed tree without a
  sighting retire them to KNOWN §3. Cost: four rows stop being carried; what it forgoes is a numeric oracle nobody has
  needed.
- **R266 (2026-09-25) — the six issues Sprint 11 carried (#25, #26, #33, #37, #38, #42) are carried once, into
  Sprint 13's milestone, where each has a task (O1, O2, C4, H2, H3, V5); an issue that leaves Sprint 13 unclosed is
  the owner's question at its close.** Cost: none; it is the §7 rule applied.
- **R267 (2026-09-25) — the carry gets one home.** `docs/BACKLOG.md`, generated by `python -m tools_py.issues backlog` <!-- docmaint: future -->
  from the open issues plus a tracked list of the ruled-out rows (each with its ruling), replaces the six places the
  reports found; the sprint file's blocks keep their carry paragraphs as records and point there. Cost: one generator
  and a registry row; what it buys is that "carried twice" can be counted.
- **R268 (2026-09-25) — the appending documents get ceilings.** `docmaint` fails when the sprint file, HANDOFF §2,
  STATUS's Current-state block or HUMAN_TASKS exceed a byte ceiling set at the split (Task R1), and when a live
  document says "merged to `main` as vX" for a tag that does not exist on origin. Cost: a check and a habit; what it
  buys is that this audit's largest finding cannot recur silently.

## 5. What became Sprint 13

The spec (`docs/superpowers/specs/2026-09-25-sprint-13-nothing-carried-twice-design.md`) turns the dispositions <!-- docmaint: future -->
marked `S13 …` into eight milestones with a bar each — **V** the player's first ten minutes, **R** the record made
true and small, **H** the harness pays its debts, **C** the code's hygiene and supply chain, **U** upstream and
outside, **S** the stranger, **N** the naming programme's follow-ups, **O** online and the box — ordered by what the
owner meets first (the project's standing rule: visible defects above infrastructure), then by what pays every night
(the lock), then by what a stranger sees. The plan (`docs/superpowers/plans/2026-09-25-sprint-13.md`) is the task <!-- docmaint: future -->
table. Everything marked `backlog` above is written into `docs/BACKLOG.md` by R267 with its bar, and everything <!-- docmaint: future -->
marked `O<n>` is the owner's sitting in `docs/HUMAN_TASKS.md`, which Task R4 reduces to exactly §3 of this file.
