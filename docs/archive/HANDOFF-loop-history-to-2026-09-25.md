# HANDOFF.md -- the loop's pick-up history and the pre-playtest sections (archived 2026-09-25)

> **ARCHIVED 2026-09-25 (Sprint 13 Task R1, R268) -- superseded by the live `docs/HANDOFF.md`.** Moved out of the
> live file verbatim: from §2 "Where it stands", the two "Picking up after ..." blockquotes, three stale state bullets and the nine
> "Where the loop is now / was" bullets older than the one it keeps; all of §4 "The work, in order" (Sprint 9's
> milestones P and Q and the Sprint 10-12 shape); all of §10 "What the owner should decide before the playtest"
> (the playtest was 2026-09-22). **Nothing below is an instruction:** three bullets here say "is now", and none of
> them is. Kept whole and in the order the live file had them, edited only where a citation pointed at a block or a
> path that has since moved. The current pick-up point is `docs/HANDOFF.md` §2; the dated account of each day is
> `docs/STATUS.md`'s log.

## §2, "Where it stands": the pick-up points (the blockquotes first, then the bullets, as they stood)

> **Picking up after Sprint 11's close (2026-09-25)?** `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`'s "Sprint 11" record, its **2026-09-25** paragraph and the worktree table; then the r0004 row in KNOWN §2 — the reboot is solved to its root, the gate is **3/3** (`s11_r0004_probe2`) and the build plays a scored online round on our own server (`s11_r0004_round2c`); the ledger `.superpowers/sdd/2026-09-23-sprint-11/progress.md` names what was running at the hand-back (a probe agent and the repair's fix round, both lock-bound). The lock's priority order is the r0004 critical path first (R255).
>
> **Picking up after the Sprint 11 night (2026-09-23, 14:00Z)?** Start at `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`'s "Sprint 11 —
> OPEN" block: what landed (Tasks 11, 2b, 8a, 8c and 19 followed on 2026-09-23 afternoon), and the table of agent worktrees holding unfinished, part-reviewed work — each row
> says the branch, the last commit, the review verdict and the next step. Then the plan
> (`docs/superpowers/plans/2026-09-23-sprint-11.md`) and, on disk, the ledger
> `.superpowers/sdd/2026-09-23-sprint-11/progress.md` with every report and review beside it. The night ended on the
> session limit, not on a decision: nothing in those worktrees is wrong, it is unfinished. Two harness facts first
> (KNOWN §4): `loop_lock.sh --wait N` is a retry count, and a fresh worktree needs `./build.sh runtime --no-runner`
> before `test`.

- **Sprint 10 is MERGED to `main` (`f15acfa`, `v0.10.0`, 2026-09-23); Sprint 11 is open on branch `sprint-11` and
  closing 2026-09-25.** Sprint 9, "A stranger's first run", is MERGED to `main` (`4415254`, `v0.9.0`, 2026-09-20). Sprint 9 done: Goal 1 (failures explain themselves),
  Goal 2 (release build, import-closure archives, `SHA256SUMS`; Windows zip 55.7 MB), **P1 and P2** (Goal 10's music:
  the queue, the ramp ownership and the stream loop flags, R169-R171, `eca5450`), **P3** (Goal 9's pad gate, R173,
  `3b12fa4`), and **the first half of P4** (`1966fa6`: the page-change flash and the top bar's two alignments).
  Landed but not closed out: Goal 8 (REPORT A BUG and the ONLINE status line) -- see P5, and read its row first,
  because three of its four documentation artefacts turn out to be already written.
- **Where the loop was (2026-09-25 early) -- Sprint 11 is CLOSED and on `main` as `v0.11.0`; Sprint 12 runs in the cloud on `sprint-12`.** Read `docs/CURRENT_SPRINT.md`'s "Sprint 11 — CLOSED" block (the outcome table, the carry, the rulings ledger R245–R263) and then the Sprint 12 handoff `docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`: the cloud session owns Sprint 12 on `sprint-12`; the local half (its PROOF REQUESTED rows, the merges, the mirroring into this file and STATUS) is session socom-pc-6c's; a new local controller starts by asking the owner which of the two it is. This machine's checkout stays on `sprint-11`; nothing lands there any more except a hotfix. The close's own record: `docs/STATUS.md`'s 2026-09-25 entry and `docs/HUMAN_TASKS.md` "Sprint 11 close — what needs you".
- **Where the loop was (2026-09-24 16:30Z) -- `sprint-11` at `07dc937`+, pushed through `2381c8a`; `main` at `a548dd1`.** The second night: Tasks 17, 13, 8b, 6 Step 2, audio-out and the cross-row recompiler fix merged and gate-proven; the r0004 build's reboot traced to two capsule words in our dumped image and repaired (KNOWN §2's r0004 row is the whole chain), and, by 16:30Z, **the r0004 gate 3/3** (`s11_r0004_probe2`) once the gate's harness learned the revision (`tools_py/parity/guest_addresses.py`, one pin standard per revision); one KNOWN row retired from the public docs on both branches at the owner's word. Next: Task 6 Step 3 (the picks gated in research/42 §4's order), then the plan's remaining tasks. Traps this night taught, all in KNOWN §4: `--accept-pins` rewrites the shared standard at gate start-up (even a cancelled gate); a dumped image carries the resident patcher's writes; an agent's bare `git config` killed the main tree's push once more (per-worktree config, `scripts/agent_worktree.sh`).
- **Where the loop is now (2026-09-23 05:10Z) -- Sprint 10 is on `main` (`f15acfa`, PR #24, tag `v0.10.0`);
  `sprint-11` is open off it with seven agent branches merged forward (`4732892`) and its opening chain running
  (the runner rebuilt with the chat wrap and the address table, the suite, gate `s11_open_gate`, the two-instance
  chat proof). Read `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md` "Sprint 11 -- OPEN" for what landed overnight and what is next; the plan
  is `docs/superpowers/plans/2026-09-23-sprint-11.md`. Two traps this night taught, both fixed: a worktree's
  `loop_lock.sh` resolved to a private lock (`9b39523`), and `git config` in a worktree writes the SHARED config, so
  the dead push URL disabled the main tree's push too (`4b5eb3f`; per-worktree config now).
- **Where the loop was (2026-09-23 morning) -- Sprint 10 is CLOSED; what is left of it is the merge to
  `main` and the annotated tag `v0.10.0`, and Sprint 11 is open on
  `docs/superpowers/plans/2026-09-23-sprint-11.md`** (eighteen tasks across milestones S, U, R and P; eight owner
  decisions, each with the default the loop proceeds on, in `docs/HUMAN_TASKS.md`'s top block). Overnight, under the
  owner's twelve-hour mandate: the endpoint A/B gave its verdict -- the mission music's DEVICE dips **survive a wired
  endpoint** (wired 14 against Bluetooth 11), so they are ours and three `docs/KNOWN.md` rows that blamed the owner's
  speaker are retracted in place; W10 split the card question -- the persona survives a virgin-card restart, the
  saved password does not, so **R237 is rewritten and the prefilled login stays**; W6 did not reproduce but cannot be
  closed (the walk never reaches the church and the capture wrote no environment); W8 is proven by the ladder
  (R244); and the sprint's sixty-four rulings R181-R244 are reconciled into one table in `docs/CURRENT_SPRINT.md`.
  The full account is `docs/STATUS.md`'s 2026-09-23 entry.
- **Where the loop was (2026-09-21 evening) -- Sprint 10's autonomous stack is DONE and on `main` in four
  slices; `docs/STATUS.md`'s top entry is the list.** Eleven chunks went to Opus agents in their own worktrees and
  were paid for in this tree, each with its gate: Q1b (the gate pins its inputs), Q6 (the stall bound), the threaded
  flake, Q3b+Goal 8 (mapping and the remapping UI), Goal 9 (the credentials, end to end), Goal 2 (the box as a
  service), Q2/Goal 3 (knob retirement and the flip), Q3 (the mouse out, the keyboard narrowed), Q4 (the window
  switch, the window's chrome, menu sounds), Q5 (closed under its stop rule), Q7 (four residuals). The suite counts are `docs/DEVELOPING.md`'s, as the baselines bullet above
  says; the ladder streak is `docs/LADDER.md`'s, generated. **What is left is the owner's hands** (`docs/HUMAN_TASKS.md`: a pad
  session, the prefilled login, Q4's four tries, the disc-derived-bytes decisions, the ladder window) **or a quiet
  machine** (Goal 4's kill routes, Goal 3's tasks 5 and 7, ladder 5-7, Q2's VM ring, Q7's gate-scored residuals).
  **Two traps this day taught, both in KNOWN:** a `replaceFunction` wrap's post-call code runs at the scheduler's
  unwind, not at the return; and a header defining state in an anonymous namespace gives every translation unit its
  own copy -- the stub helpers depended on that, the suite could not see it, the gate could.
- **Where the loop was (2026-09-20 evening) -- the repository is PUBLIC and Sprint 10 is reorganized around
  hardening it.** The owner flipped `github.com/Scotho/socom-unzipped` public after the sweep and the history rewrite,
  bypassed the owner gate on the audio listen, and set the priority: harden the development and build process a
  stranger can now fork; no easy player setup until then; nothing sensitive can ever be published. Read
  `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md` "Sprint 10, REORGANIZED" -- milestone H, H1 and H2 done that evening: the leak check
  (`tools_py/release/leakcheck.py`, six modes, three exit states, `leak_allow.txt` the ledger), the git hooks
  (`bash scripts/install_hooks.sh` once per clone -- **do it in your first hour**), CI `secrets.yml` with gitleaks,
  GitHub's secret scanning and push protection and the rulesets (R181-R183). **H3-H8 followed the same night:** the
  Windows toolchain bootstrap and `build.sh --no-runner` with a `windows` workflow (green on `a175ec7`: bootstrap from nothing, the build in 4 min, Python 1571 OK, ps2x_tests 701/0, the VU1 verify OK; `build-windows` joined `main`'s required checks), the
  suite's debris to the temp directory, `THIRD_PARTY_NOTICES.md` + `LICENSES/` with a test, the release folder and
  the bug report's scrubber through the gate (gate `s10_h6_scrub_gate` 3/3), the disc-derived-bytes audit
  (`docs/audits/2026-09-21-disc-derived-bytes.md`, decisions the owner's), the release-draft workflow. Next: the
  Goals resume in the reorganized order; the music thread below is filler now, not the live thread. Two traps
  learned: a GitHub Windows runner resolves `bash` to WSL's from Python (use `tools_py/tests/shell.BASH`), and a
  docs-only push used to cancel the running build (fixed).
- **Where the loop was (2026-09-21 03:00 UTC) -- the music, round four.** Read `docs/archive/sprints-7-12/2026-09-20-sprint-10-music-round-four.md` task 4 top to bottom before touching audio: the real 989snd decompilation (`research/989snd-ziemas/`, audit research/36) corrected the model; the music-only capture pair (`scripts/parity/music_only_mission.txt`, `logs/s10_music_round4_ours_only.sh`, `logs/s10_music_round4_repin.sh`) is the instrument, with stereo alignment and the dip classifier (`tools_py/parity/audio_dips.py`) and the EE cue-sequencer poll (`music_state_poll`); the stereo interleave fix (`c6502ea`) is the day's find and the owner's fifth listen (HUMAN_TASKS) its bar. Open: the mission's 10-27 s music pauses (the stems are fired by the play-sound API's callers :242150/:242232 -- `PS2X_CALL_TRACE` next), the PCM ring's 300-400 ms feed stalls (the PSS demux thread parked in `sceMpegGetPicture`), and why the console's sequencer holds a 9 s voice cue for 120 s. Two traps learned today are in memory: never edit a running chain script; kill a chain's survivors by listed PID, never by pattern.
- **Where the loop is now (2026-09-20 19:40 UTC):** Sprint 10 is under way on `sprint-10`. Goal 1: the ladder job exists, its verifier gap is fixed, streak 1 of 7 (`docs/LADDER.md`); the Task Scheduler entry stays DISABLED until the owner names a window. Goal 3: BAR MET -- both legs of the mixed match run on the hosted server on the verified flow, twice in a row each (the Goal 3 plan has every run and what it found; its task 7 is the one refinement left). Next in the spec's order: Goal 2 (the hosted box as a service -- the server session's work, coordinate), Goal 4 (per-map kill routes), the carried Q items. The owner's ear on the music is still the next input (HUMAN_TASKS round three).
- **Where the loop was at 09:00 UTC:** Sprint 9 is closed on the machine's side and merged to `main` as `v0.9.0`; Sprint 10 is open on `sprint-10`. The last thing done: Q0 -- the mission ambience was a CONDUCTOR sound our mixer never ran (R178), found by the audio parity check the owner asked for; read `docs/archive/sprints-7-12/2026-09-20-sprint-9-q0-mission-music-investigation.md` sections 6d-6f before touching audio: the instrument, the finding, the verdicts (gate 3/3, parity 31/48), and the four things left open with their numbers. **Gates as left:** `s9_q0_children_gate` 3/3 on exe sha256 `b3abebd5...`; suite 686/686 and Python 1457 three times over; CI green `7de8492`; audio parity `s9_q1_parity_ours2` 31/48 -- the check's first PASS is Sprint 10's to earn (the bed's level, the movie audio's level). **The owner's input is next** (HUMAN_TASKS "round three": listen on `dist/socom2.exe` through the JBL; the ladder window; the blue arrow). Sprint 10 Goal 1's job exists and ran once (LOBBY-FAIL, ledgered); its Task Scheduler entry is DISABLED until the owner names a window. Q0b, Q1b-Q7 carried into Sprint 10 -- `docs/CURRENT_SPRINT.md` has the order.
- **Nobody else is known to be in the tree** as of 2026-09-19: `git status` showed only `server/config/simulated.db`,
  which is always modified and is never committed. The Goal 10 session's work is committed; the Goal 3 plan is
  committed and not started.
- **A playtest by the owner is planned.** The order of work exists to make that session worth their time.

## §4 as it stood

## 4. The work, in order

`docs/CURRENT_SPRINT.md` is the list; this is its shape and the reasoning, so you can re-derive it when it changes.

- **Sprint 9, milestone P -- "worth the owner's evening", ends in the tag `playtest-1`:** P1 the music's two bugs
  (queue, ramp) with the confirming trace first; P2 the universal half (stream looping for menus and lobby, a
  concurrency cap and headroom); P3 the pad driving both windows; P4 the launcher's small defects (page-change flash,
  two alignments, ADVANCED section, tooltips); P5 Goal 8's close-out; P6 the server by name (unblocked: the DNS record
  exists); P7 the release candidate, gated and tagged; P8 the owner plays it (`docs/PLAYTEST.md`).
- **Milestone Q -- after the playtest, ends in the merge and `v0.9.0`:** Q0 the owner's notes first; Q1 the audio
  instrument so the music cannot silently return; Q2 Goal 3, knob retirement (a written 9-task plan; the most
  expensive item in the sprint); Q3 the mouse leaves and the keyboard is narrowed (depends on Q2's developer mode --
  see trap 1); Q4 the rest of the launcher (guide button, game window style, menu sounds from the player's ISO, profile
  viewer); Q5 voice, the headset's button; Q6 Goal 11, the latched-stall memory bound; Q7 residual filler; Q8 close.
- **Sprint 10** -- it stays up (the scheduled ladder, moved back from Sprint 9 Goal 5), the hosted box as a service,
  the mixed match with PCSX2 both ways, per-map kill routes, the first two-machine match (owner), a real DB (owner).
- **Sprint 11 -- as run**, four milestones rather than the goal list its spec was drafted as: **S** the chat hole
  closed on both sides; **U** upstream and external (the divergence table, the recompiler fixes, the demo disc's
  names); **R** the r0004 groundwork, which became an r0004 build that gates 3/3 and plays online; **P** the public
  repository's remaining owes (the download, the bug pipeline, the licences, the story, the VM ring). Nineteen tasks
  and **eight** owner decisions, each with the default the loop proceeds on (`docs/HUMAN_TASKS.md`).
  *(This bullet said "six owner decisions (D1-D6)" and listed the spec's draft goals until 2026-09-25.)*
- **Sprint 12, "the readable image"** -- the demo-name rename pass into the function map, vtable slots through RTTI,
  BinDiff as the cross-check, the ccc types with the layout-age caveat. **Closed 2026-09-25**: 1,771 readable names
  from one sidecar, every one with its provenance, proven `s12_names_gate` 3/3 on the renamed tree
  (`docs/superpowers/plans/2026-09-24-sprint-12.md`; run in a Claude cloud session, closed by the local controller).

**Why this order:** by what the owner meets first (the music, every session), then by dependency (the keyboard
narrowing needs Goal 3's developer mode; a public archive needs the
licence inventory), then by cost (Goal 3 is a full generated rebuild, three gates and an online round -- it must not
stand between the owner and a playable build). Sprint 9 was ten goals in the order they were thought of; it is now
eleven in the order they matter. Nothing was dropped.

## §10 as it stood

## 10. What the owner should decide before the playtest

1. **Who plays.** If the archive goes to anyone but the owner, Sprint 11's decision D2 arrives early: the portable
   archive contains `socom2.exe` (code recompiled from the game) and `socom2_game.elf` (the game's decrypted code).
   For the owner alone on their own machine it is not a question.
2. **The keyboard ruling** (trap 1): gameplay keys survive as the harness's path in developer mode, players get menus
   and typing. Overturning it means moving the harness to the pad path first -- a sprint of its own.
3. ~~**The persona switch** (P6)~~ -- **withdrawn 2026-09-19, it was not a real decision.** It asked the owner to
   approve a measurement for a cost that cannot occur: the launcher's preset string never reaches the game
   (R175, KNOWN §4), so switching the default to `socom.scotho.com` orphans nothing. Nothing is owed here. The
   related question that IS the owner's, if they ever want it: whether the hosted server should advertise its
   NAME rather than its IP -- that string is guest-visible, and that one would want measuring first.
4. **Is a friend on another network available for the playtest?** If so, the first two-machine match (carried since
   Sprint 7, and carried past Sprint 10's close) is answered in the same evening. It is the one item on the
   "what a stranger still lacks" list that no amount of machine time can close.
5. **Whether the release build should drop imgui and the dump/trace families** -- decided on Q2's size number, but the
   owner should know the trade: a smaller download against a shipped build that is harder to diagnose.
