# Current sprint

The loop's aim. `docs/LOOP_PROMPT.md` reads this file instead of carrying a sprint pointer of its own;
the controller updates it when a sprint opens or closes.

**The goal every sprint serves:** SOCOM II running natively on PC with online play, that a stranger runs by pointing the
launcher at their own r0001 ISO and playing a round against another stranger on a hosted Horizon server. The audit of
2026-09-17 (`docs/AUDIT-2026-09-17.md`) measured the tree against that sentence; its §1 table is the gap in dependency
order, and this file's order follows it.

## 2026-09-17 (late) — Sprint 6 CLOSED and merged (`8f57cbd` on develop and main); Sprint 7 OPEN

branch: sprint-7 (off develop at `8f57cbd`)
spec: docs/superpowers/specs/2026-09-17-sprint-7-two-strangers-two-machines-design.md (owner review pending; Goal N = Task N)
plan: docs/superpowers/plans/2026-09-17-sprint-7-two-strangers-two-machines.md
audit: docs/AUDIT-2026-09-17.md
human tasks: docs/HUMAN_TASKS.md (four open: the title/intro listen, free play, the launcher with the pad, the two
server addresses; plus a second machine for Goal 5)

**Sprint 6's close-out is done**: the plan reconciled with the audit's ledger (43 of 55 boxes ticked; the 12 open are
carried by Sprint 7 or Sprint 8), rulings R81–R90, the KNOWN audit, STATUS's current state, ROADMAP §6 marked,
`PS2X_TEST_REPEAT=3 ./build.sh test` 503/503 three times, gate 3/3 (`s6_fixwave_gate`), merged and pushed.

**2026-09-18 additions (owner):** Goal 8 (plan Tasks 8-11: controller and microphone selection, FPS overlay, detail/resolution) and Task 12 (the owner's three sound reports: online-menu splice and buzz, the mission going silent). Order from here: the Goal 8 commits (the overlay's title launch is their gate), the ten-round lobby re-run on the latched press (Task 2f), then Task 12, then close-out. Task 3 stopped by its own trace (R96); the menus' upload cost goes to Sprint 8.

**Sprint 7's order (the spec's Goals 1–7):** (1) the stranger's machine, defensively — GL probe and CPU fallback,
the bounded command queue, the DPI flag and 2x default, the native-VU1 warning, audio I/O off the callback; (2) online
correctness before scale — the equal-priority time slice removed, a same-key control round, the CD stream cursor, the
ten-launch lobby rate, freeze shape 2; (3) the 21k decodes settled and fixed; (4) the hosted server (**owner**: the
machine and the two addresses); (5) the first two-machine match (**owner**: a second machine); (6) the owner's checks;
(7) close-out. The loop does not wait on (4)–(6): it works (1)–(3) and files what it cannot verify in HUMAN_TASKS.

## 2026-09-17 (audit) — Sprint 6 closing: the order for the rest of it, and Sprints 7–9 drafted (superseded above; kept for the record)

branch: sprint-6
spec: docs/superpowers/specs/2026-09-15-sprint-6-correctness-gate-and-online-reliability-design.md
plan: docs/superpowers/plans/2026-09-15-sprint-6-correctness-gate-and-online-reliability.md (its checkboxes are being
reconciled with the audit's §3 ledger in the close-out; until then §3 is the truth)
audit: docs/AUDIT-2026-09-17.md
human tasks: docs/HUMAN_TASKS.md (the owner's hands-on checks and the two facts only the owner has: the community
server's address and ours)

**Where Sprint 6 stands (audit §3).** Done: Tasks 0, 1, 5a/5b, 6b, 6c (bar the listen), 8, 8b (bar the pad test), and
the audit's fix wave (the ISO handoff, hostname resolution, the server's `-PublicIp`, the harness `env.sh`, the launcher's
server picker). Partial: Task 2 (the ten-launch lobby rate never measured), Task 3 (freeze shape 2 unrooted), Task 4
(met in practice, the strict two-scorer bar unrecorded), Task 7 (tooling in, leg 1 had no joiner). Not started: Task 6,
Task 9. ROADMAP §6's items 10–12 were never carried into the plan and stay dropped.

**Standing rules (superseding the older blocks below where they differ).** The owner's "proceed autonomously" (2026-09-17)
replaces the host-window rule: builds, gates and launches run whenever the host is free, one launch at a time, through
`scripts/run_detached.sh` under the loop lock, with `build.sh test` and suites held while a launch runs. Commits with
explicit pathspecs, never `git add -A`; `server/config/simulated.db` never staged; `ONBOARDING.md` untracked; the
Co-Authored-By trailer; a failing test first for every runtime change; `build.sh test` and the 3-stage gate before a
commit that touches the runtime, the recomp or the parity tools. Bounded mechanical work goes to Opus subagents with an
exact brief and a verification command; judgment stays here (owner, 2026-09-17). What only the owner can verify goes to
`docs/HUMAN_TASKS.md` and the loop moves on. Every moved default and every skipped measurement gets a numbered ruling
(R81 onward) in the plan's "Rulings made on the owner's behalf".

**Next, in order (the rest of Sprint 6 = its close-out, then Sprint 7 opens):**
1. Commit the fix wave (all suites green over the merged tree; gate on the rebuilt exe first, since the runtime changed).
2. Close Sprint 6 honestly (Task 9): reconcile the plan's checkboxes with audit §3; the KNOWN audit (audit §4: the `0x34`
   row, the frozen-exe row, the excluded-waits row, the repeatability row, the lobby rows, the motion-pack row, the
   header line); rulings R81+ for the unrecorded decisions (audit §4's list); STATUS's current-state block rewritten;
   ROADMAP §6 marked; `PS2X_TEST_REPEAT=3 ./build.sh test` and a full gate; merge `sprint-6` into `develop` and `main`;
   the ledger archived.
3. Open Sprint 7 (below): its spec and plan drafted from the audit, the plan's first tasks being the stranger's-machine
   defences and the online-correctness items that need no owner.

## Sprint 7 — "Two strangers, two machines, one hosted server" (drafted 2026-09-17, audit §6)

A friend on another PC joins a round on a Horizon instance the project hosts, both from the portable zip. Ends in
something a stranger notices: they got into a lobby from the zip, against a server with a name.

1. **The stranger's machine, defensively** (autonomous): the GL capability probe with a CPU-backend fallback and a visible
   error (audit §2.2 F2); a bound on the pending command queue when the back-pressure latch trips (F3); the HIGHDPI flag
   and a launcher default of 2x (F8); the native-VU1 mismatch warning (F7); the ISO handoff already in.
2. **Online correctness before scale** (autonomous): the equal-priority time slice removed under a test (audit §2.3, the
   scheduler finding: settle it before shipping online); a same-RSA-key control round or a per-profile key; the CD stream
   cursor fix; Task 2 Step 4's ten-launch lobby rate; Task 3's shape-2 freeze A/B.
3. **The 21k decodes** (autonomous): settle the page-marking hypothesis with `PS2X_GS_TRACE_PAGES`, fix the marking
   granularity, add the decodes-per-present budget to the console-replay GL test; then the ladder's RUNG0 bar passes.
4. **The hosted server** (**owner** for the machine and the two addresses; autonomous for the rest): a machine, a public
   address or name, the router's forwards per `server/README.md`, `start-servers.ps1 -PublicIp`, the picker's two
   placeholders replaced, the launcher default switched to SOCOM Unzipped, `server/` packaged as a zip.
5. **The first two-machine match** (**owner** hands-on with a second machine; scripts and readout autonomous): both
   directions of hosting, from the portable zip, over the internet; NAT and clock-skew findings to KNOWN §1 or §2.
6. **The HUMAN_TASKS items reported** (**owner**).

## Sprint 8 — "It looks and sounds finished, and it does not scare the machine" (drafted 2026-09-17; revised 2026-09-18 after Sprint 7)

What Sprint 7 handed over, in the order the goal sentence wants it:

1. **The menus' render cost, at the root.** The login and lobby screens upload 7-11k 1 KB tiles a second at 80-133 ms/s of
   render time (four to six times gameplay's 20-28 ms/s), which is what drops the login screen to 12-30 fps under GL
   back-pressure on this machine (KNOWN §2), what put the menu music's fill late (the buzz the owner heard; the ring now
   silences instead of looping, R97), and what made the driven presses miss (latched, 6b7a2b3). Trace the login screen's own
   pages, break the upload cost down per call, batch the tiles. Bar: the login screen at 60 fps with a spinning four-core
   load AND `bp_pending` under 2; `pcm_underruns` stays 0. Autonomous.
2. **Voice: serve the headset.** Task 9c's spike (KNOWN §2): the game binds 'BLIP', calls lgAudInit, then polls Enumerate and
   EnumHint against our "no device" answer and nothing else. Answer Enumerate with one device when `PS2X_MIC_DEVICE` is set,
   let Open succeed, serve GetAvailableRecordingBytes/Read from HostMic's ring; a WAV of what the game read as the proof;
   then the owner's two-machine "can you hear me". Autonomous up to the two-machine check.
3. **Audio residuals.** The one remaining slot exhaustion when six long-lived streams overlap (are two of them meant to end?
   the mixer said they were playing for a whole mission); the stream-start underfill; the aside-cap parity fix and the
   scratch leak; a per-stage sound regression fixture (the repeat detector and the correlation, on every gate dump).
   Autonomous; owner listen.
4. **Window policy** beyond Sprint 7's selectors: fullscreen at desktop resolution scored by the gate; render targets sized
   from use are in (Task 1c). Autonomous; **owner** picks the default.
5. **Bare-run robustness:** `socom2.exe` with no argument reads `config.json`; an exit-code taxonomy the launcher shows (65
   is the first); the diagnostics zip; `SHA256SUMS`; a release build (`-Os`/LTO, stripped, harness DLLs dropped, under 100
   MB). Autonomous; signing is **owner** money and identity.
6. **Knob retirement pass 2** (about 90 `PS2X_*` now) into a config file plus `--dev`; the stub-state header into a `.cpp`;
   the invocation stack pool. Autonomous.
7. Task 5c verified against the loading screen; the VU0 flag latency; the readback PBO ring. Autonomous.
8. An installer (Inno, outline §6) if wanted. **Owner** decision.

Carried from Sprint 7 unchanged because they are the owner's: the hosted server and its two addresses (Task 4), the first
two-machine match (Task 5), the hands-on checks in `docs/HUMAN_TASKS.md` (now six: the title/intro listen, free play, the
launcher with the pad and its pick, the microphone meter, the sound re-listen, the two addresses).

## Sprint 9 — "Console players in the same lobby, and it stays up" (drafted 2026-09-17)

1. Task 7 both directions with screen-verified PCSX2 steps. Autonomous.
2. A nightly job: N consecutive ladder passes and the lobby rate tracked and published. Autonomous; **owner** names the machine.
3. Per-map kill routes for the sweep maps; the two-instance speed freeze lifted. Autonomous.
4. Task 6's math oracles and HLE leg 3 as filler. Autonomous.
5. Stats and clans across restarts (a real DB) if wanted; the public README and the legal-position text. **Owner** decisions.

---

*The dated blocks below are the record of how Sprint 6 was opened and run; where they state rules or "next" lists, the
block above supersedes them.*

## 2026-09-15 (evening) — Sprint 6 Task 0 done, Task 1 wired, Tasks 2–3 advanced lock-free

Everything Task 0 owed is on `develop` (`a81eb74` the block-pointer fix; `f6a4434` the depth fix; `326c9c9` the ifpopup
step; `34ed2ac` the gate wiring; `78a81d1` lobby verify-then-act; research/28 and /29). The gate PASSed 3/3 on the
block-pointer exe (`s6_blockptr`, sha `1cfef9af028a90fc…`) **with the mission-failure detector active** — the turn
teleport no longer ends the mission. The runtime freeze at `92d30f0` is over: **the ladder exe is now `a81eb74`'s**, and
the first online result on it must be recorded against that sha.

branch: sprint-6 (created 2026-09-15 evening off develop at `20db94b`; Task 0 and the lock-free Task 1-4 work went to develop first)
spec: docs/superpowers/specs/2026-09-15-sprint-6-correctness-gate-and-online-reliability-design.md (owner review pending)
plan: docs/superpowers/plans/2026-09-15-sprint-6-correctness-gate-and-online-reliability.md
ledger: .superpowers/sdd/2026-09-15-sprint-6-correctness-gate-and-online-reliability/progress.md (create on first dispatch)

**Owner's order, 2026-09-16 (after playing the build with a controller):** (1) the water shards and the occasional
flat-grey hill patch in Seeding Chaos (believed the same defect: geometry drawn untextured) — Task 5a; (2) the untested
online maps, control rounds without a kill requirement — Task 6b; (3) misc hardening; (4) audio — Task 6c (nothing
SOCOM plays reaches the host backend); (5) the launcher: an r0001 ISO pointer, a pre-launch detail-quality choice, a
visible controller test area, other easy settings (packaging outline §3); (6) the rest of the sprint work in the
controller's order. Gamepad support landed in the SOCOM input path the same day (uncommitted until its gate).

**Next, in order (2026-09-17 afternoon):** the owner's order is done through item 5 — Task 5a water/terrain (research/31), Task 6b the twenty-map sweep (research/33, 19 of 20 play), the guest clock fix and the audio path (research/32: bank sounds, streams, the PCM title music), the launcher first cut (Task 8b, `770d5fb`). The title music is clean (research/32 §7.1, evening: three sceMpeg HLE faults fixed under tests). Now: (1) a ladder launch on the current exe for the 2-of-2 online kill bar (`s6_ladder12`, done: 3 kills in 4 rounds); (2) the owner's hands-on tests — in `docs/HUMAN_TASKS.md` (the title/intro listen, free play, the launcher with the Xbox pad; Task 6c Step 4, Task 8b Step 4), done in parallel; (3) Task 8 harness items -- done; Foxhunt and the PCM ring settled; (3b) Task 8b Step 5 done (`scripts/make_portable.sh`); (4) Task 7 mixed match; (5) the portable folder (Task 8b Step 5).

## 2026-09-15 — Sprint 6 drafted; lock-bound work queued for an owner window (superseded above; kept for the record)

**Sprint 6 is drafted, not opened**: spec `docs/superpowers/specs/2026-09-15-sprint-6-correctness-gate-and-online-reliability-design.md`
and plan `docs/superpowers/plans/2026-09-15-sprint-6-correctness-gate-and-online-reliability.md` (owner review pending;
Tasks 0–1 are owner-agreed items). Branch `sprint-6` is created only after Task 0's two fix branches merge.
A packaging/launcher/installer outline is at `docs/superpowers/specs/2026-09-15-game-client-package-and-installer-outline.md`.

**Rule since 2026-09-15: builds, gates and launches only in a host window the owner names** (they lag the owner's
machine; a contended mission gate's frame file went stale 176 s). Lock-free work continues in between.

State of the working tree on `fix/gl-depth-precision` (nothing committed):
- Depth fix: `./build.sh test` green (Python 845 OK, ps2x_tests 454/454, vram-diff 15/15); title PASS `s6_depth`,
  transition PASS `s6_depth_r2`; mission FAIL `s6_depth_m2` on the HELP pop-up class only (6/6 gameplay-band holds,
  diffs 0.00–0.05, `s30_holdW.png` shows "PRESS X TO CONTINUE").
- `ifpopup` gate step: `tools_py/parity/drive.py` `popup_present()` + `ifpopup+<delay>:BTN` (test-first,
  `tools_py/tests/test_drive_popup.py` 5/5), one before each of the six holds in `scripts/parity/gameplay_probe.txt`.
  Mission rerun `s6_depth_m3` was killed at the owner's request (host contention) — **one mission gate is owed**.
- README carries the `PS2X_GS_DEPTH_LEGACY` entry (commits with the depth fix).

**Queued for the next window, in order** (plan Task 0; each command is in the plan):
1. `gate --only mission --stamp s6_depth_m4` on the current exe → commit the depth fix and the ifpopup step, push, ff-merge to develop.
2. Branch `fix/gs-block-pointer`; paste the seven-region test (plan Task 0b Step 2); build `ps2x_tests` → RED; the
   two-line fix in `GS.cpp`; `./build.sh runtime && ./build.sh test && gate --stamp s6_blockptr`; motion_pack_check 48 → 0.
3. Open `sprint-6` and start Task 1 (lock-free scorers first).

## Paused 2026-09-14 (owner) — open threads after Sprint 5 merged (superseded above; kept for the record)

Sprint 5 is merged (develop = main = 2ae4d79). Work paused mid-investigation of two Seeding Chaos defects the owner
spotted in gate frames. Both are written up and both have a named cause; neither fix has landed.

- **Branch `fix/gl-depth-precision`** (not merged): the GL depth-precision fix for the grey water shards, plus the
  docs commits made while it was checked out (`6e41064` pipeline blind spot + ROADMAP §6 additions, `b09227f` and this
  KNOWN entry, research/25 and /26). Its build/test/gate run was in flight at the pause — check
  `logs/parity/gate/s6_depth*` and the branch's last commit before trusting anything.
- **Not started: the GS block-pointer fix** (research/25 §9) — the ×8 in `sceGsExecLoadImage`/`StoreImage`, which
  corrupts 48 animation clips and causes the single-player turn teleport. Its independent verification was in flight.
  It needs its own branch off develop, a seven-region round-trip test, and a full gate for blast radius.
- **ROADMAP §6 item 5** gained two owner-agreed additions: a console-vs-ours gameplay image comparison, and a
  mission-failure screen failing the gate's mission stage.

To resume: read `docs/KNOWN.md` §2's two new rows and research/25 §7–§9 and /26, then finish the verification and the
two fixes in that order.
