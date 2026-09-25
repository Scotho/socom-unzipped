# Audit 2026-09-25 — the harness and tooling

Area: `tools_py/` (every module, `tools_py/tests/`, `tools_py/research/`), `scripts/` (with `scripts/parity/`,
`scripts/hooks/`), `ghidra_scripts/`, `tests/`, `server/`. Read-only; worktree `C:\projects\wt-s12` at `eb190a42`
(sprint-12, with another session's uncommitted doc edits in the working copy — cited lines are the working copy's
unless marked `HEAD:`). Nothing was built, run or tested; the suite numbers below are read from logs and CI.

Method notes. The inventory (Appendix A) is `ast.get_docstring` of every tracked `tools_py/**/*.py` except the tests,
and `git grep -l -w <module name>` over `tools_py scripts build.sh docs .github tests CMakeLists.txt server`, split
into code / test / doc hits. A "code refs" count for a module with a common-word name (`compare`, `keys`, `pins`,
`addresses`) is inflated by unrelated words; a **zero** is reliable. The scripts inventory (Appendix B) is the same
grep by file name.

## 1. Findings

| # | item | class | who | cost | evidence | why it matters |
|---|---|---|---|---|---|---|
| 1 | **CI is red on `sprint-12`'s head and on the Sprint 11 PR to `main` (#49): the same six Python failures on Linux and Windows.** | RISK | LOCKFREE-AGENT | S | `gh run view` (linux, sprint-12, `eb190a42`): "`FAILED (failures=6, skipped=152)`", "`Ran 2797 tests in 253.537s`"; PR run on `f142b513`: "`Ran 2562 tests in 247.200s` … `FAILED (failures=6, skipped=152)`", job "`tests: Python: FAILED (exit 1)`"; windows: "`Ran 2795 tests in 347.598s`" "`FAILED (failures=6, skipped=126)`" | the merge to `main` (a required check) cannot land green, and both branches read as "closed" |
| 2 | Root cause of four of the six: `test_gate_accept_pins`' fixture sets no `SOCOM_GAME_ELF`, so on a runner with no `game/` the gate refuses (rc 8) — the fix the Sprint 12 Log prescribed for `test_gate_pins` was not carried to the newer file. | TASK | LOCKFREE-AGENT | S | `tools_py/tests/test_gate_accept_pins.py:60` sets only `{"PS2X_MC_DIR": self.card}`; `test_gate_pins.py:326` sets `"SOCOM_GAME_ELF": self.game_elf`; CI: "`AssertionError: 8 != 0 : EXE dist/socom2.exe bytes=1 sha256=0000…`"; `docs/superpowers/plans/2026-09-24-sprint-12.md` Log "2026-09-25 morning — CI on `sprint-12` is red" | a test that needs the disc to pass is a CI failure by construction |
| 3 | The other two failures are **collateral**: the setUp starts four `mock.patch` objects and then asserts; when the assertion fails `tearDown` never runs and `gate.exe_line` stays mocked for `test_gate_exe_line`. | TASK | LOCKFREE-AGENT | S | `test_gate_accept_pins.py:64-75` (patches `.start()` at :70-71, `self.assertEqual(rc, 0, out)` at :75, `tearDown` at :78); CI: `test_names_the_runner_its_size_and_its_sha256` "`'EXE dist/socom2.exe bytes=1 sha256=0000…' != 'EXE /tmp/…/socom2 bytes=19 …'`"; same shape at `test_gate_pins.py:330-337` | one failure leaks into unrelated tests; `addCleanup` per patch fixes the class |
| 4 | A docs-only push reports every workflow `success` with the build **skipped**, and that was read as green: `f142b513`'s message says "CI green" while its pull-request run failed. | RISK | LOCKFREE-AGENT | S | `gh run list --branch sprint-11`: `push linux success f142b513` and `pull_request linux failure f142b513`; the push run's jobs: "`changes success` / `build skipped`"; commit `f142b513` "docs: the close proof recorded -- … CI green" | "green" must mean a build job that ran; a `ci_status` helper that skips skipped runs is a 30-line tool |
| 5 | Sprint 12's suite-count run **failed** (2 failures, names lost to a `tail -4`), and the re-run that keeps the full output was queued and has not completed; STATUS carries an unfilled placeholder for it. | UNFINISHED | LOCK-AGENT | S | `wt-s12/logs/s12_count_run.log`: "`FAILED (failures=2, skipped=100)`", "`python_rc=1`"; `logs/s12_count_run.sh:10` `… \| tail -4`; `logs/s12_after_close.sh:2-3` "the first count run kept only its tail and lost the two failing test names"; no `logs/s12_after_close.done`; `docs/STATUS.md:46` "`{COUNTS_AND_R0004}`" | the close records "`build.sh test` exit 0" while its own later count run says otherwise |
| 6 | `DEVELOPING`'s count row (the single source) reads "`Ran 2553 tests` on 2026-09-25"; the sprint-12 tree runs 2,797 (Linux CI) / 2,795 (Windows CI) / 2,562 on sprint-11 locally. | REVISION | LOCKFREE-AGENT | S | `docs/DEVELOPING.md:286`; CI lines in #1; `logs/chain22_cpp.log` (main tree): "`Ran 2562 tests in 691.641s`" | the row is the baseline strangers compare against |
| 7 | The docs say Sprint 11 is "merged to `main` as `v0.11.0`"; PR #49 is OPEN, `main` is `e63f9ba9` (PR #44), and the only remote tag is `v0.10.0`. | REVISION | OWNER | S | `docs/CURRENT_SPRINT.md:82` "(merged to `main` as `v0.11.0`…)"; `gh pr list`: "`49 OPEN sprint-11 Sprint 11: …`"; `git ls-remote --tags origin`: `refs/tags/v0.10.0` only | blocked by #1; the docs got ahead of the merge |
| 8 | **The loop lock has no queue (issue #36), and nothing hands a chain's lock from one step to the next:** `run_detached.sh` refuses at once when BUSY (exit 75, no wait), so every chain is its own poller, and on 2026-09-25 the second controller's poller took the gap between the first controller's chain steps and cost it ten minutes. | UNFINISHED | LOCKFREE-AGENT (write) / LOCK-AGENT (land, see #10) | M | `scripts/run_detached.sh:10-11` "if it is BUSY, writes "exit=75 BUSY ..." … and exits 75 without launching"; `wt-s12/logs/s12_r0004_launch.log` "`run_detached: BUSY: owner taken 5 min ago …`" ×5 a minute apart; `docs/STATUS.md:50-53` "the second controller's poller took a gap between the first one's chain steps once and cost it ten minutes"; `gh issue view 36` closing bar "A ticket (append to a queue file on the first refusal, grant to the head)" | two controllers (or a cloud and a local session) is now a normal day |
| 9 | What a queue would take (the design, not yet written anywhere but #36's one line): a `$LOCK.q/` directory of tickets `<arrival-epoch>-<owner>-<take_id>` written under the existing mutex on the first refusal; `do_take` grants only to the oldest live ticket; a waiter's ticket carries its own heartbeat and is reaped like a stale holder (REAP_MIN) so a dead waiter cannot wedge the head; `run_detached.sh --wait` joins the queue instead of exiting 75; a **chain holds one lock for all its steps** (one `run_detached` of a chain script, the convention `s12_after_close.sh` already follows) rather than one take per step; `check` prints the queue. Tests: two waiters with 5 s and 60 s polls served in arrival order under `LOOP_LOCK_SLOW_TESTS=1`. | TASK | LOCKFREE-AGENT | M | `scripts/loop_lock.sh:29-35` (the mutex every transition already runs under), `:504-513` (`do_wait`: `do_take` then `sleep "$WAIT_SEC"`, no ticket); `docs/KNOWN.md:288` "any `loop_lock.sh` change needs `LOOP_LOCK_SLOW_TESTS=1`" | fairness is a property of the grant, not of poll speed |
| 10 | Landing any `loop_lock.sh` change is itself hazardous: waiters in other sessions run the script by offset, and an edit under a running bash script breaks it. There is no written procedure for rolling out a new lock script. | RISK | LOCK-AGENT | S | memory note "Never edit a running bash script"; `scripts/loop_lock.sh:74-79` (every worktree runs its own copy, sharing the main tree's lock path) | a mixed fleet of old and new lock scripts on one lock file is the failure the queue must survive |
| 11 | `--wait N` is still a retry count while the usage line says minutes (issue #35). | UNFINISHED | LOCKFREE-AGENT | S | `scripts/loop_lock.sh:14` "`wait <owner> [max_minutes]` … retrying every minute (default 40)"; `:506-511` loops `seq 1 "$max"` sleeping `$WAIT_SEC` | a 5 s poll turns `--wait 180` into 15 minutes (KNOWN §4) |
| 12 | `ladder_job.sh` still checks the lock and then acquires it separately (issue #37, carried). | UNFINISHED | LOCKFREE-AGENT | S | `scripts/ladder_job.sh:26` "`if ! bash scripts/loop_lock.sh check \| grep -q "^FREE"; then … exit 75`"; then `:33` `ladder_frostfire.sh` takes it | the ladder loses every gap to an agent build |
| 13 | **The quiet marker is per checkout while the lock is machine-wide**: `run_detached` writes `<its own tree>/logs/.quiet` and `check_quiet_gate.sh` reads `<its own tree>/logs/.quiet`, so a launch from a worktree is invisible to `build.sh test` in the main tree and vice versa — the defect class `loop_lock.sh` fixed for itself on 2026-09-23. | RISK | LOCKFREE-AGENT | S | `scripts/run_detached.sh:53,58` `ROOT="$(cd "$HERE/.." && pwd)"`, `QUIET_MARKER="${RUN_QUIET_MARKER:-$ROOT/logs/.quiet}"`; `scripts/check_quiet_gate.sh:15-16` same; `scripts/loop_lock.sh:82` `--git-common-dir` | worktree launches are the norm now (every agent gets one) |
| 14 | `ladder_job.sh` hard-codes the main checkout (`ROOT=/c/projects/socom_pc`), so the scheduled ladder runs whatever branch that tree has checked out, with that tree's harness. `agent_worktree.sh` hard-codes `/c/projects` likewise. | RISK | LOCKFREE-AGENT | S | `scripts/ladder_job.sh:14`; `scripts/agent_worktree.sh:15` `WT_ROOT="/c/projects"` | a fork or a second clone cannot run either |
| 15 | **The ladder has not run since 2026-09-23 04:21Z** (exe `3f3a5011`); since then: ten upstream picks, the r0004 harness seams in `guest_addresses`/`env.sh`, and the renamed tree `804dd172`. | NEGLECTED | LOCK-AGENT | M | `docs/LADDER.md` last row "`2026-09-23T04:21:03Z` … `3f3a5011`"; `/c/projects/socom_pc/logs/ladder/ledger.jsonl` 9 rows; `docs/CURRENT_SPRINT.md` Sprint 11 row 6 (the picks), row 19 (the harness "three seams deep") | the only online regression net that runs on the hosted box is two sprints stale |
| 16 | The twenty-map control queue last ran 2026-09-16/17; `online_control_round.sh` changed 2026-09-24 and has not been re-run over the maps. | NEGLECTED | LOCK-AGENT | L | `docs/HANDOFF.md:38` "Twenty of twenty maps play a control round"; `docs/KNOWN.md:115` settled 2026-09-17; `git log -1 -- scripts/parity/online_control_round.sh` = 2026-09-24 | "20 of 20" is a claim about an exe three sprints old |
| 17 | The mixed-match legs (ours ↔ PCSX2) last ran 2026-09-20 (runs d, f); `env.sh`'s mixed profile is now rendered from `guest_addresses` and was not exercised since. | NEGLECTED | LOCK-AGENT | M | `docs/KNOWN.md:31-32` "(Sprint 10 Goal 3 leg 2, run f, 2026-09-20)"; `scripts/parity/env.sh:26-30` (the three legs "REPLACE it with a narrower one … rendered from the same table") | a rewire with no run behind it |
| 18 | The two-machine match has never been played, so `two_machine_readout.{sh,py}` (Sprint 7) has never had real input. | NEGLECTED | OWNER | M | `docs/HUMAN_TASKS.md:544` "`- [ ] **A second machine for the first two-machine match**`"; `scripts/parity/two_machine_readout.sh:2` "the one line the owner runs after the first TWO-MACHINE match" | dead-until-used tooling rots silently |
| 19 | The online harness defaults to a private LAN address; only `ladder_job.sh` points at the hosted box. A stranger (or a cloud session) running `online_control_round.sh` bare targets `192.168.x.x (a LAN address; masked in this copy)`. | TASK | LOCKFREE-AGENT | S | `scripts/parity/env.sh:38` `SOCOM_SERVER_IP="${SOCOM_SERVER_IP:-192.168.x.x (a LAN address; masked in this copy)}"`; `scripts/ladder_job.sh:19` `export SOCOM_SERVER_IP=3.143.65.100` | default to the hosted box or refuse when unset |
| 20 | `verdict_replay.py` keeps its own copy of the per-revision address pairs — the "three copies" `guest_addresses` says it retired now has a fourth outside it. | REVISION | LOCKFREE-AGENT | S | `tools_py/parity/verdict_replay.py:142` `ACTOR_VTABLE = 0x006691A0`, `:150` `ACTOR_VTABLES = frozenset({0x006691A0, 0x00668B20})`, `:160-163` clock pairs; `tools_py/parity/guest_addresses.py:18-19` "Before the review there were three copies of these four numbers" | the next revision column will miss this file |
| 21 | `music_state_poll.py` reads eight r0001 statics that are not in the per-revision table; on the r0004 build it would read another build's memory and report numbers (KNOWN §4's hazard exactly). | TASK | LOCKFREE-AGENT (derive with `data_via_twin`) | M | `tools_py/parity/music_state_poll.py:146` `ROUTE_ADDR = 0x49e150`, `:147` `0x49e158`, `:152` `0x48e080`, `:156` `0x3e0080`, `:157` `0x48e010`, `:169` `0x48dc48`; `guest_addresses.py:10-14` "Falling back to r0001 without evidence is the one thing this must not do" | audio work will resume on both revisions |
| 22 | `verdict_core.VALVES` spells ten r0001 peek items (`*0x437ce8…`, `*0x43668c…`) and ten r0001-only name pointers; valve identity is by name bytes, so the online verdict is revision-safe, but the pointer mode and `--round-name-ptr` are r0001-only and say nothing. | TASK | LOCKFREE-AGENT | S | `tools_py/parity/verdict_core.py:807-818`; `:800` "`ours_name_ptr: int # research/21 §2.1, ours only`"; `:868-879` `row_valve` by name bytes | a silent r0001 assumption in the scorer |
| 23 | Remaining raw guest addresses under `tools_py/parity`, classified (Section 2.3's table): 3 instruments with live r0001 literals (`music_state_poll`, `motion_pack_check`, `cam_poll`'s default spec), 2 replay/verdict copies (#20, #22), 1 simulator fixture (`sim_walk_to_b`), and message/comment text elsewhere. The Sprint 12 carry names only "research/61 §5's r0001 literals" and cites a line that moved. | REVISION | LOCKFREE-AGENT | S | `docs/research/61-name-consumers.md:280` "the call-trace addresses (`env.sh:33`, `sim_walk_to_b.py:70`)"; `scripts/parity/env.sh:48-55` now "`tools_py/parity/guest_addresses.py` is the one home for both strings"; `docs/CURRENT_SPRINT.md:76` carry | the carried item should be re-scoped to the three live instruments |
| 24 | 51 of the 58 reference PNGs (all the online/lobby/map refs, `refs.json`, the OSK refs) are in no pin standard, so the online harness's references can change without any refusal; the gate pins only 7. | NEGLECTED | LOCKFREE-AGENT | S | `scripts/parity/pins.json` "pins": 7 PNGs (`ref_main_menu_ours.png` … `refs/mission_failure_banner.png`); `git ls-files scripts/parity/*.png` = 58 (9 top, 41 `refs/`, 8 `refs/lobby/`); `tools_py/parity/online_login_ours.py:1999-2002` loads `map_*.png` unpinned | the ladder's verdicts rest on unpinned inputs |
| 25 | `scripts/parity/ref_lobby_news_title.png` is referenced by no code — only by a 2026-09 evidence manifest. | TASK | LOCKFREE-AGENT | S | grep of the stem over `tools_py scripts build.sh` empty; `docs/research/assets/22-first-kill-evidence.txt:108` | dead reference image in a public repo |
| 26 | The disc-derived audit counts 64 reference PNGs under `scripts/parity`; the tree has 58 (+1 WAV, 2.8 MB). | REVISION | LOCKFREE-AGENT | S | `docs/audits/2026-09-21-disc-derived-bytes.md:29` "`| 64 | 2.8 MB |`"; `git ls-files` count 58, `du -ch` 2.8M | the owner's decision table should count what is there |
| 27 | **28 modules are invoked by nothing** — no code, no test (Appendix A, flag "invoked by nothing"): `dbg_reads/step2/trace/writer`, `patch_fifo_trace/istat/mfifo/vif1_intc`, `ra2fun`, `resolve_mmio`, `gif_packets`, `gif_submit_timeline`, `gsdump_timeline`, `hostprof_diff`, `hostprof_stacks`, `marker_timeline`, `vu1dis`, `vu1stats_summary`, `parity/blue_marker`, `parity/frame_burst`, `parity/p2s_extract`, `parity/resize_window`, and six `research/terrain` scanners. Only `movie_blocks` has an issue (#46). | TASK | LOCKFREE-AGENT | M | Appendix A; `gh issue view 46` "`movie_blocks.py` is wired into nothing"; `tools_py/parity/blue_marker.py` has 0 code, 0 test, 0 doc hits | #46's closing bar ("a caller … or the module retired") applies to 28 more |
| 28 | The four `patch_*.py` are one-off source patchers of the vendored runtime, long applied, that still **write** into `C:/projects/socom_pc/third_party/…` when run. | RISK | LOCKFREE-AGENT | S | `tools_py/patch_mfifo.py:1` "One-off patch: add fromSPR/toSPR DMA channels…", `:5` `root = 'C:/projects/socom_pc/third_party/ps2recomp/ps2xRuntime/'`; same at `patch_istat.py:5`, `patch_fifo_trace.py:3`, `patch_vif1_intc.py:6`; last touched 2026-09-05 | dead code with write access to the runtime's source |
| 29 | Two run logs from 2026-09-04 are tracked inside `tools_py/`, with absolute paths of the owner's machine. | TASK | LOCKFREE-AGENT | S | `git ls-files tools_py` lists `tools_py/decrypt.log` (16,159 B) and `decrypt2.log` (9,349 B); `decrypt.log:426` `File "C:\projects\socom_pc\tools_py\decrypt_apache.py"`; added `329bbdac` 2026-09-04 | logs belong under git-ignored `logs/` |
| 30 | Research scripts hard-code the owner's `dist/` path. | TASK | LOCKFREE-AGENT | S | `tools_py/research/terrain/classify2.py:6` `EXE = r"C:\projects\socom_pc\dist\vu1_replay.exe"`; `eye_experiment.py:5` same | unrunnable on any other clone |
| 31 | **No Python dependency manifest.** The only requirements file lists `pytest`, which the suite forbids, and omits `unicorn`, `capstone`, `zstandard`, `pycaw`, `comtypes`, `pyaudiowpatch`; CI installs its own hand list. | TASK | LOCKFREE-AGENT | S | `tools_py/parity/requirements.txt`: "pillow / numpy / pytest"; `tools_py/tests/test_test_hygiene.py:4` "Fails on … a pytest import"; `.github/workflows/linux.yml:77` `pip install … numpy pillow zstandard`; `README.md:94` `pip install unicorn` | a stranger discovers imports one traceback at a time |
| 32 | `build.sh` calls bare `python` four times although `python_env.sh` says it is where "every shell script in this repository finds Python". | REVISION | LOCKFREE-AGENT | S | `build.sh:43,47,113,140`; `scripts/python_env.sh:2` | the rule the VM lesson produced has a hole in the main entry point |
| 33 | `fix_ghidra_csv.py` is on the build path (every `./build.sh recomp`, `build_revision.sh` step 0) and has no test. | TASK | LOCKFREE-AGENT | S | `build.sh:47`; `scripts/build_revision.sh:251`; Appendix A: `fix_ghidra_csv.py` test refs 0 | it rewrites the function map the recompiler trusts |
| 34 | 35 non-research modules have no test at all (Appendix A, "no test"), among them `dns_stub`, `iso_lbn` (imported by `disc_to_elf`), `hostprof_symbolize`, `loopback_record`, `online_match` (PCSX2), `gsdump_capture`, `pcsx2_keys`, `probe_poll`, `state_poll`, `vu1_headers`; none of the 43 `tools_py/research/` scripts has one (by design, but undeclared). | NEGLECTED | LOCKFREE-AGENT | M | Appendix A; `tools_py/disc_to_elf.py:49` `from tools_py import iso_lbn` | `iso_lbn` is on the stranger's first-run path |
| 35 | About 30 skip sites depend on **git-ignored run output** (`logs/parity/gate/…`, `logs/parity/vr_*`, a capture "not on disk"), so those cases run only on the owner's machine and rot unseen; `make_gate_fixtures.py` exists to turn such runs into committed fixtures. | NEGLECTED | LOCKFREE-AGENT | M | `tools_py/tests/test_gate.py:127,227,233,242,250,255,263,542,698,754,1218,1285` ("needs logs/parity/gate/s5_task4_dbuff", …); `test_audio_dips.py:287` "run 10's capture is not on disk"; `test_saved_password.py:81`; `test_motion_pack_check.py:50`; `tools_py/parity/make_gate_fixtures.py` | Section 2.2 classifies all 108 skip sites |
| 36 | The local Python suite takes 11.5 min and is on the lock's busy list, so every suite run blocks builds and gates machine-wide; CI runs the same suite in 4-6 min. No split into a lock-free fast set exists. | NEGLECTED | LOCKFREE-AGENT | M | `logs/chain22_cpp.log` "`Ran 2562 tests in 691.641s`"; CI "`Ran 2797 tests in 253.537s`" (Linux), "`347.598s`" (Windows); `scripts/loop_lock.sh:49-51` busy list "any python whose command line contains tools_py.parity or unittest"; `wt-s12/logs/s12_count_run.log` python+C++ 05:49:38Z → 06:02:17Z | lock time is the project's scarcest resource |
| 37 | The `--accept-pins` start-up write (issue #45) is open with a closing bar that names its test file. | UNFINISHED | LOCKFREE-AGENT | S | `gh issue view 45` closing bar "a test in tools_py/tests/test_gate_accept_pins.py that queues a gate, cancels it before the lock, and finds the standard byte-identical"; `docs/KNOWN.md:207` | a cancelled gate rewrites the shared standard |
| 38 | The title gate's four lost captures (issue #30), the never-run console-replay GL case (#41), the mission capture's unrecorded environment (#38), `PS2X_PEEK`'s silent 64-word cap (#39) are harness issues with no milestone. | UNFINISHED | LOCK-AGENT (#30, #41) / LOCKFREE-AGENT (#38, #39) | M | `gh issue list`: "`30 OPEN harness,known-issue`", "`38 … carried`", "`39 OPEN harness`", "`41 OPEN needs-disc-gate,harness`" | the gate passes 3/3 with 19/23 title captures |
| 39 | The Sprint 12 r0004 gate (`s12_names_r0004_gate`) is queued inside the same unfinished after-close chain as the count re-run. | UNFINISHED | LOCK-AGENT | M | `wt-s12/logs/s12_after_close.sh:22-23` "`bash logs/s12_r0004_chain.sh s12_names_r0004_gate`"; `docs/CURRENT_SPRINT.md:76` carry "the r0004 build with its own sidecar and its gate" | the renamed r0004 tree is unproven |
| 40 | `server/README.md` still says "No SOCOM II client has been connected yet" beside the 2026-09-19 status, lists five paths that are not in the tree, and starts with the owner's absolute path. | REVISION | LOCKFREE-AGENT | S | `server/README.md:8-10`; `:17-24` Layout: `horizon-server-database-middleware/`, `horizon-docker/`, `logs/`, `medius-plugins/`, `build-release.log` (none in `git ls-files server`); `:29` `cd C:\projects\socom_pc\server` | the README is the box's only public runbook |
| 41 | The README's "Local source changes (all marked `LOCAL FIX (socom_pc)` in code)" omits the Sprint 11 chat clamp and the app-id list, and `ChatClamp.cs` is not marked `LOCAL FIX`. | REVISION | LOCKFREE-AGENT | S | `server/README.md:223-235`; `server/horizon-server/Server.Medius/Medius/ChatClamp.cs:3` "`// Sprint 11 milestone S: …`" (no marker); commit `5b7d20e` "fix(server): forwarded chat fields are clamped"; `Server.Medius/Program.cs:73` `LOCAL FIX` app ids not in the table | the next vendor bump uses this table to carry our changes |
| 42 | **The box-as-a-service layer is not in the repository**: the backup script, its cron entry, the health script and the off-box pull live only in the git-ignored `vm/lightsail/`, and the commit that recorded Sprint 10 Goal 2 says nothing under `server/` was touched. | TASK | LOCKFREE-AGENT | S | `/c/projects/socom_pc/vm/lightsail/box/`: `socom-backup.cron`, `socom-backup.sh`, `socom-health.sh`; `vm/lightsail/backup_pull.sh`; `.gitignore:36` `vm/`; `git show dc392b3d`: "nothing tracked under server/ was touched: daily backups …, an off-box pull …, a one-line health script" | a second machine or a cloud session cannot rebuild or review the service layer |
| 43 | The off-box backup has been pulled once (2026-09-21); personas and the chat-clamp deploy (2026-09-23) came after. | RISK | OWNER | S | `vm/lightsail/backups/` holds one set `20260921T035845Z`; `docs/HUMAN_TASKS.md` (dc392b3d) "run it after anything that matters; nothing here does it for you"; `docs/CURRENT_SPRINT.md` Sprint 11 row 3 "deployed to the project box 2026-09-23 06:58Z" | the box is a single copy of the player accounts |
| 44 | Which server commit runs on the box is recorded nowhere machine-readable; Goal 2's "one item left", a build id on `/api/stats`, was never done. | UNFINISHED | LOCKFREE-AGENT (code) / OWNER (deploy) | S | `git show dc392b3d`: "The server build id on /api/stats is the one item left."; `grep -i "build\|version\|commit" server/horizon-server/Server.Medius/StatsServer.cs` → no match | a deploy claim is prose only |
| 45 | `server/config/simulated.db` is untracked and ignored since 2026-09-20 (the untracking rode on an mpeg commit), but HANDOFF still says it "always shows modified". | REVISION | LOCKFREE-AGENT | S | `git log -- server/config/simulated.db`: `619c1394 2026-09-20 fix(mpeg): …`; `.gitignore:34` `/server/config/simulated.db`; `docs/HANDOFF.md:106` "`git status` showed only `server/config/simulated.db`", `:170` "(always shows modified)" | a stranger reads a dirty-tree warning that no longer applies |
| 46 | `issues.py` has `open`, `close`, `audit`, `check-body`, `skeleton` — and nothing for what both close reviews did by hand: label `carried` + comment + move milestone, close one milestone and create the next, and the "opened N, closed N, carried N" tally. | TASK | LOCKFREE-AGENT | M | `tools_py/issues.py:445-464` (the five sub-parsers); `docs/CURRENT_SPRINT.md:86` "Opened 1, closed 0, carried 0", "the `Sprint 12` milestone held no issue and is closed"; Sprint 11 block: "the 6 in the Sprint 11 milestone carried to the backlog with the `carried` label and a comment each …, the milestone closed and Sprint 12's created" | three hand steps per issue per close, each a chance to skip one |
| 47 | The audit only sees a KNOWN §4 hazard whose headline begins `HAZARD` or `Open:`, and a row had to be re-headed so the tool could see it — the tool is shaping the prose. | NEGLECTED | LOCKFREE-AGENT | S | `docs/KNOWN.md:207` "*(Re-headed 2026-09-25 so `python -m tools_py.issues audit` can see it … the audit only asks about a headline beginning `HAZARD` or `Open:`.)*"; `tools_py/issues.py:24-27` | an issue marker (`*(issue #N)*`) is the reliable key |
| 48 | The bug-report skill tells a triager to pick one of eight area labels; `issues.py` and `github_labels.sh` define twelve (`harness`, `server`, `build`, `recomp` missing), and there is no `issues open --from-report BR-…` that writes the skeleton with the one permitted line. | REVISION | LOCKFREE-AGENT | S | `C:\projects\socom_pc\.claude\skills\s2u-bug-reports\SKILL.md` rule 6 "one area from `audio render online launcher input linux packaging docs`"; `tools_py/issues.py:52-53` `AREAS = (…, "harness", "server", "build", "recomp")`; skill step 4 "`Reported through the launcher as BR-…`" typed by hand | the skill is git-ignored, so no test holds it to the label set |
| 49 | `embed_image.py` is invoked by nothing; the launcher logo and the app icon headers it produced are committed as generated blobs while the fonts moved to build-time generation (R247). | NEGLECTED | LOCKFREE-AGENT | S | `git grep embed_image` → only its own lines; tracked `third_party/ps2recomp/ps2xLauncher/src/ui/logo_embedded/socom_unzipped_logo.h`, `ps2xShared/include/ps2x/app_icon_embedded.h` ("Generated by scripts/embed_image.py"); `third_party/ps2recomp/ps2xLauncher/CMakeLists.txt:39-45` (fonts via `embed_font.py`) | one rule for generated headers |
| 50 | `DEVELOPING`'s repository map describes `tools_py/` as six things; it holds 67 top-level modules and six packages (57,537 lines outside the tests, 25,765 in `parity/` alone). | REVISION | LOCKFREE-AGENT | S | `docs/DEVELOPING.md:23` "Python tooling: Unicorn EE harness, APACHE00 decryptor, DNAS self-decryptor, ELF builder, Ghidra CSV fixers, screenshot helper"; `git ls-files 'tools_py/*.py' \| xargs wc -l` 57537 | a stranger has no map of the harness |

## 2. Structure notes

### 2.1 Inventory summary (Appendix A and B are the full tables)

- `tools_py/`: 67 top-level modules + packages `parity/` (65 modules), `release/` (2), `story/` (5), `r0004/` (1),
  `research/symbols/` (19), `research/terrain/` (16). Test directory: **155 `test_*.py` files, 2,805 `def test_`**
  (`grep -c`), smallest `test_diagnostics_zip.py`/`test_host_window_title.py`/`test_movie_blocks_fixture.py`/
  `test_toml_names_agree.py` at 1 case, largest `test_online_verdict.py` 125, `test_verdict_replay.py` 116,
  `test_gate.py` 100, `test_revision_toml.py` 70, `test_loop_lock.py` 64.
- Invoked by nothing: 28 (finding #27). Doc-only CLIs with no code caller but a test (the Sprint 12 levers
  `bindiff_lever`, `callgraph_lever`, `offset_lever`, `string_lever`, `ui_binding_lever`, `vtable_lever`,
  `toml_stub_lever`, plus `recomp_census`, `translate_extras`, `find_ctor_thunks`, `hle_constants`, …) are fine as
  entry points but are listed nowhere as such — `toml_stub_lever.py` and `find_ctor_thunks.py` are not named in any
  document at all (Appendix A, doc refs 0).
- `scripts/`: 26 tracked top-level files and 16 under `scripts/parity/` that are code; Appendix B. Invoked by nothing
  in code: `embed_image.py` (no doc either), `flake_repro.py`, `fetch_private_inputs.sh`, `agent_worktree.sh`
  (doc-invoked, fine), `scripts/parity/drag_window.ps1`, `endpoint_ab.sh`, `lobby_rate_queue.sh`,
  `online_control_queue.sh` (all run by hand from docs).
- `ghidra_scripts/`: 6 Java + 1 patch; every one referenced from docs or `scripts/ghidra_export_functions.sh`.

### 2.2 The 108 skip sites, by what they need (`git grep -n "skipTest\|skipUnless\|skipIf\|SkipTest"`)

| need | examples | count (sites) |
|---|---|---|
| a shell/tool: Git Bash that is not WSL's, PowerShell, node, ldd | `test_build_revision.py:75` "needs a bash that is not WSL's launcher" (×8 in that file), `test_loop_lock.py:258` "Windows PowerShell not available", `test_leakcheck_external.py:112` "no node" | ~45 |
| the game (`game/` images, the r0004 capsule/card, a disc) | `test_build_revision.py:401` "needs the r0001 image game/disc/socom2_game.elf", `test_data_via_twin.py:24`, `test_decrypt_card_package.py:313`, `test_r0004_capsule.py:404`, `test_music_state_poll.py:176`, `test_overlay_repair.py:399,421`, `test_find_ctor_thunks.py:249` | ~14 |
| git-ignored run output under `logs/` | `test_gate.py` ×12 (finding #35), `test_gate_pins.py:669`, `test_audio_dips.py:287`, `test_saved_password.py:81`, `test_motion_pack_check.py:50` | ~17 |
| a build product (`dist/socom2.exe`, the launcher, `dist-release/`, the .NET server, a portable folder) | `test_knobs_line.py:16`, `test_runner_exit_codes.py:49`, `test_launcher_bug_report.py:68`, `test_make_server_zip.py:34`, `test_third_party_notices.py:94`, `test_portable_folder.py:26` | ~11 |
| Windows / a desktop | `test_hostplatform.py:75,123,128`, `test_winshot.py:26,53,122`, `test_loop_lock_closeout.py:28` | ~8 |
| the lock's slow suite (opt-in) | `test_loop_lock.py:51` "slow lock suite: set LOOP_LOCK_SLOW_TESTS=1", `:628`, `:778` "(~135 s)" | 4 |
| a live PCSX2 | `test_pine.py:39` "PCSX2 with PINE not running" | 1 |
| a full (non-shallow) clone | `test_leakcheck.py:432`, `test_pin_harness.py:77`, `test_story_timeline.py:70` | ~5 |

No test needs the loop lock itself (the lock tests set `LOOP_LOCK_PATH`), but running the suite counts as busy for
everyone else (finding #36). Skip counts seen: 100 (local count run), 152 (Linux CI), 126 (Windows CI).

### 2.3 Raw guest addresses under `tools_py/parity` and `scripts/parity`, classified

`git grep -c -i -E "0x[0-9a-f]{6}"`: `guest_addresses.py` 42 (the home), `verdict_core.py` 32, `online_match_ours.py`
26, `sim_walk_to_b.py` 21, `freeze_trace.py` 20, `music_state_poll.py` 19, `verdict_replay.py` 13, `sp_death_probe.py`
7, `object_diff.py` 6, `motion_pack_check.py` 5, then ≤5 each.

| class | where | verdict |
|---|---|---|
| live r0001 instrument constants, not in the table | `music_state_poll.py:146-169` (8 statics), `motion_pack_check.py:24-25` (`0x415E08`, `0x415E0C`), `cam_poll.py:22` default `"*0x488de8+0x120:96"` | move to `guest_addresses` or refuse on r0004 (#21) |
| second copies of table values | `verdict_replay.py:142-163` (#20); `verdict_core.py:807-818` VALVES item strings and name pointers (#22) | import from the table |
| read through the table correctly | `verdict_core.py:65,70,74,917-918`, `sp_death_probe.py:65`, `object_diff.py:355` (`ga.address(…, "r0001")` — r0001 by name, stated) | fine; the ladder is r0001 |
| simulator fixture | `sim_walk_to_b.py:60-72,107` (`SIM_ENV`, `NG_ADDR = 0x869360`) | fine — it simulates r0001 logs |
| PCSX2-side addresses (the console is r0001 by definition) | `mixed_match2.sh:91`, `mixed_match2_leg2.sh:96` `--spec 0x416054:3` (commented as the console's) | fine |
| message / docstring / sample-output text | `online_match_ours.py:2359-2493` ("round clock 0x4365c0"), `freeze_trace.py:5-48`, `two_machine_readout.py:13-216`, `online_ladder.py:176,225` | messages name r0001 on an r0004 run; low |

### 2.4 Well organised

- `scripts/loop_lock.sh` and `scripts/run_detached.sh` are the best-documented files in the area: every state,
  environment knob and test hook is in the header (`loop_lock.sh:1-79`, `run_detached.sh:1-44`), with 64 + 16 tests.
- `tools_py/parity/guest_addresses.py` is a genuine single home with provenance per value and a refusal rule
  (`:1-27`, `:57-61`, `:448`); `pins.py` + `pins.json`/`pins_r0004.json` make every gate's inputs explicit.
- `issues.py` and `docmaint.py` make the documentation contract fail in the suite instead of in review.
- `server/linux/` is small, idempotent, tested (`test_horizon_ctl.py`), and refuses to write bad JSON.

### 2.5 Not well organised

- **Outgrown files:** `online_match_ours.py` 5,278 lines, `online_login_ours.py` 2,530, `verdict_core.py` 1,374,
  `music_state_poll.py` 1,204, `sim_walk_to_b.py` 1,198, `gate.py` 1,147 (`wc -l`). The online driver is a
  quarter of `parity/`.
- **Dead or one-off code beside live code in the flat `tools_py/`**: `dbg_*` (no docstrings, `sys.path.insert` +
  `import decrypt_apache as da`, `dbg_reads.py:1-9`), `patch_*` (#28), two `.log` files (#29). A `tools_py/archive/`
  (or deletion with a line in the story) would make the directory readable.
- **Superseded scripts still tracked:** `scripts/parity/online_match_frostfire.sh:2` "LEGACY converge path,
  superseded by scripts/parity/ladder_frostfire.sh"; `mixed_match.sh` superseded by `mixed_match2.sh`
  (`mixed_match2.sh:3-4` "instead of mixed_match.sh's fixed-timing macros, which lost their place at boot";
  `docs/KNOWN.md:128` "SUPERSEDED 2026-09-20"). **Near-duplicates:** `lobby_rate_queue.sh:17-20` and
  `online_control_queue.sh:18-27` are the same loop over `online_control_round.sh` (one map ×N vs N maps ×2 passes).
  `disc_to_elf.sh` is a 25-line wrapper of `tools_py/disc_to_elf.py` (fine, documented).
- **Two modules named `readable_names.py`**: `tools_py/readable_names.py` (452 lines, the renderer) and
  `tools_py/research/symbols/readable_names.py` (92 lines, its Task 7 prototype, "Run from the repo root: python
  <this file>"). A stranger grepping for the renderer finds both.
- **Two fixture homes:** `tests/fixtures/` (88 files: audio, gate, movie, vu1) and `tools_py/tests/fixtures/` (111
  files: lobby, online, replay, mission); 8.4 MB together (`du -ch`). Nothing says which a new fixture goes in.
- **Names that mislead:** `scripts/parity/` holds harness *data* (58 PNGs, 23 step scripts, 7 JSON, 3 pnach) beside
  its scripts; `chain22_cpp.log` in the main tree's `logs/` holds the Python count. `tools_py/parity/addresses.py`
  (19 lines, "Guest addresses shared by the PCSX2 driver") beside `guest_addresses.py` (530) invites the question
  which one is the home.
- **The online harness's reach, as it stands:** against the hosted box today only `scripts/ladder_job.sh` (fixed to
  3.143.65.100) — the rest defaults to the LAN stack (#19). Two instances are needed by `online_match_ours.py`,
  `ladder_frostfire.sh`, `online_control_round.sh` and both queues; ours + PCSX2 by the three mixed legs; one
  instance by `online_login_ours.py` (login to lobby) alone. Two machines by `two_machine_readout` (never run).

## 3. Top five

1. **#1-#3, CI red with six failures on both open branches** — the Sprint 11 PR cannot merge green, and the fix
   is two small test changes (a `SOCOM_GAME_ELF` stand-in and `addCleanup` for the patches), lock-free.
2. **#8-#10, the lock queue and a chain's single hold** — two controllers on one machine is now routine, the
   hand-off gap already cost time on day one, and the design is small enough to write and test lock-free; only the
   landing needs a quiet window.
3. **#5, #39, the unfinished after-close chain** — Sprint 12 is recorded closed while its own count run failed with
   names lost and its r0004 gate never ran; one lock hold settles both and fills STATUS's placeholder.
4. **#15-#17, the online nets are stale** — the ladder (the only thing that runs on the hosted box), the twenty-map
   control queue and the mixed legs have not run on the picks, the r0004 seams or the renamed exe.
5. **#42-#44, the hosted box's service layer is outside the repository** — backups, health and the off-box pull
   live in a git-ignored folder, the one off-box copy predates two sprints of accounts, and no machine-readable
   record says which server commit is deployed.

## Appendix A — every `tools_py` module (tests excluded)

Columns: lines (`\n` count); the docstring's first line; code / test / doc hits of the module's name (see the
method note on inflated counts); flag.

| module | lines | docstring, first line | code refs | test refs | doc refs | flag |
|---|---|---|---|---|---|---|
| `tools_py/address_matcher.py` | 587 | Sprint 11 Task 10 (milestone R): match one game build's functions onto another's. | 24 | 10 | 13 |  |
| `tools_py/addresses_from_match.py` | 232 | Sprint 11 Task 19: print the r0004 column of 'runtime/socom2_addresses.h' from match.json. | 2 | 2 | 4 |  |
| `tools_py/apply_names.py` | 402 | The applier: proposals files -> readable names in the names sidecar (Sprint 12 Task 3; S12-R13, S... | 4 | 3 | 8 |  |
| `tools_py/bindiff_lever.py` | 628 | Sprint 12 Task 6: the 'bindiff' lever -- BinDiff as the SECOND signal, never a proposer alone (S1... | 0 | 1 | 2 | test-only; CLI entry |
| `tools_py/callgraph_lever.py` | 633 | Sprint 12 Task 15: the 'callgraph' lever -- callers and callees of placed pairs name the bodies b... | 0 | 1 | 2 | test-only; CLI entry |
| `tools_py/carry_names.py` | 192 | Carry one build's function names onto another build's addresses (Sprint 11 Task 19). | 3 | 1 | 15 |  |
| `tools_py/data_via_twin.py` | 409 | Where did an r0001 DATA address go in r0004? (Sprint 11 Task 19, review F5.) | 2 | 1 | 1 |  |
| `tools_py/dbg_reads.py` | 84 | (no docstring) | 0 | 0 | 1 | **invoked by nothing** (doc-only CLI) |
| `tools_py/dbg_step2.py` | 45 | (no docstring) | 0 | 0 | 1 | **invoked by nothing** (doc-only CLI) |
| `tools_py/dbg_trace.py` | 43 | (no docstring) | 0 | 0 | 1 | **invoked by nothing** (doc-only CLI) |
| `tools_py/dbg_writer.py` | 27 | (no docstring) | 0 | 0 | 1 | **invoked by nothing** (doc-only CLI) |
| `tools_py/decrypt_apache.py` | 390 | Run SOCOM II's own loader code (boot ELF + DNAS overlay) under Unicorn to | 8 | 3 | 13 |  |
| `tools_py/decrypt_card_package.py` | 70 | Decrypt the update package the server writes to the memory card, by running the loader's | 1 | 1 | 0 |  |
| `tools_py/derive_seeds.py` | 141 | Sprint 12 Task 5 (S12-R5): derive address_matcher's '--seed' list from its own seedless run. | 2 | 1 | 3 |  |
| `tools_py/disc_to_elf.py` | 554 | From your own SOCOM II disc to a buildable ELF -- the one command (Sprint 10, 2026-09-21). | 5 | 2 | 8 |  |
| `tools_py/dnas_selfdecrypt.py` | 161 | Statically decrypt the self-encrypting code blocks of SOCOM II's DNAS.BIN overlay. | 3 | 1 | 6 |  |
| `tools_py/docmaint.py` | 343 | Documentation maintenance: the registry in docs/DOC_MAINTENANCE.md, held to the tree. | 3 | 4 | 17 |  |
| `tools_py/ee_unicorn.py` | 818 | Minimal EE (R5900) execution harness on top of Unicorn (MIPS64 LE). | 7 | 1 | 4 |  |
| `tools_py/elf_symbols.py` | 249 | Sprint 11 Task 7 (U3): the function table of an ELF that still has its '.symtab'. | 19 | 2 | 5 |  |
| `tools_py/exit_codes.py` | 55 | The game's exit codes, read out of the C++ header that defines them. | 2 | 3 | 9 |  |
| `tools_py/find_ctor_thunks.py` | 223 | Enumerate an overlay's static-constructor thunks from its MWo3 header and force each as an entry. | 0 | 1 | 0 | test-only, undocumented |
| `tools_py/find_data_entries.py` | 466 | Find entry points that no branch in the image names, so no branch-based scan can see them. | 1 | 1 | 1 |  |
| `tools_py/find_escaping_branches.py` | 110 | Report conditional branches whose target lies outside their own Ghidra CSV range. | 2 | 1 | 4 |  |
| `tools_py/find_gap_functions.py` | 94 | Report executable gaps between Ghidra CSV functions that look like real function bodies. | 1 | 1 | 3 |  |
| `tools_py/find_imm_targets.py` | 91 | Find code addresses materialized as immediates (lui rX,hi ; addiu/ori rY,rX,lo) that are | 3 | 1 | 5 |  |
| `tools_py/find_interior_functions.py` | 126 | Report function starts hidden *inside* a Ghidra CSV range. | 2 | 1 | 4 |  |
| `tools_py/fingerprint.py` | 29 | Sprint 11 Task 10 (milestone R): the per-function fingerprint. | 15 | 10 | 23 |  |
| `tools_py/fix_ghidra_csv.py` | 115 | Normalize the Ghidra ExportPS2Functions CSV for PS2Recomp: | 9 | 0 | 9 | no test |
| `tools_py/ghidra_symbol_match.py` | 758 | Sprint 11 Task 7 (U3): name our anonymous functions from the SOCOM 1 demo's debug symbols. | 15 | 4 | 16 |  |
| `tools_py/gif_packets.py` | 124 | Parse the packet file written by vu1_replay (records of uint32 length + GIF packet bytes) and list | 0 | 0 | 6 | **invoked by nothing** (doc-only CLI) |
| `tools_py/gif_submit_timeline.py` | 62 | Reduce a run log's [gif-submit] lines (PS2X_GIF_TRACE) to the events that matter for the | 0 | 0 | 3 | **invoked by nothing** (doc-only CLI) |
| `tools_py/gsdump_extract.py` | 117 | Turn a PCSX2 GS dump (.gs, the new 0xFFFFFFFF format) into the console-replay fixture that ps2x_t... | 0 | 1 | 1 | test-only; CLI entry |
| `tools_py/gsdump_timeline.py` | 238 | Timeline of a PCSX2 GS dump (.gs, uncompressed): per frame, every GIF transfer by path with | 0 | 0 | 6 | **invoked by nothing** (doc-only CLI) |
| `tools_py/hle_constants.py` | 524 | HLE stub consumer census -- Sprint 5 Task 4 Step 2 (static, zero game runs). | 0 | 1 | 5 | test-only; CLI entry |
| `tools_py/hostprof_diff.py` | 71 | Symbolize the difference of two PS2X_HOST_PROF histograms (end minus start): the samples taken | 0 | 0 | 2 | **invoked by nothing** (doc-only CLI) |
| `tools_py/hostprof_stacks.py` | 91 | Fold and symbolize the call stacks of a PS2X_HOST_PROF_STACKS=1 histogram (logs/hostprof.txt | 0 | 0 | 3 | **invoked by nothing** (doc-only CLI) |
| `tools_py/hostprof_symbolize.py` | 93 | Symbolize a PS2X_HOST_PROF histogram (logs/hostprof.txt: "rva count" lines) against dist/socom2.exe | 3 | 0 | 4 | no test |
| `tools_py/iso_lbn.py` | 105 | Map disc LBNs to file names (ISO9660) and annotate a run log's CD reads. | 2 | 0 | 8 | no test |
| `tools_py/issues.py` | 473 | The known-issue stack on GitHub issues, held to the live documents. | 7 | 3 | 29 |  |
| `tools_py/knobs.py` | 289 | The PS2X_* knob registry, read out of the C++ header that defines it (Sprint 9 Goal 3). | 3 | 5 | 41 |  |
| `tools_py/make_overlay_elf.py` | 145 | Wrap decrypted Metrowerks 'MWo3' overlay dumps (and the boot ELF's own | 5 | 3 | 12 |  |
| `tools_py/marker_timeline.py` | 83 | Merge a run log's game-thread events into one ordered stream for the texture-set marker | 0 | 0 | 3 | **invoked by nothing** (doc-only CLI) |
| `tools_py/name_provenance.py` | 143 | The names sidecar: one row of provenance per readable function name (Sprint 12 Task 2; R261, S12-... | 10 | 5 | 4 |  |
| `tools_py/offset_lever.py` | 752 | Sprint 12 Task 13: the 'offset-multiset' lever, and 'prefix+offsets' (research/54, S12-R12). | 0 | 1 | 2 | test-only; CLI entry |
| `tools_py/overlay_repair.py` | 496 | Undo the r0004 capsule's baked-in stub writes in a decrypted overlay. | 3 | 1 | 4 |  |
| `tools_py/parity/addresses.py` | 19 | Guest addresses shared by the PCSX2 driver (PINE) and our runtime. | 63 | 22 | 72 |  |
| `tools_py/parity/app_volume.py` | 325 | Per-app audio session volume on the render endpoint: list it, or hold one exe's session at full v... | 2 | 1 | 3 |  |
| `tools_py/parity/audio_corr.py` | 374 | Sprint 7 Task 1e: how faithful the mixed audio is to the disc's own PCM. | 2 | 3 | 14 |  |
| `tools_py/parity/audio_dips.py` | 490 | Sudden level dips in a capture, aligned to the mixer's own dump and classified against the game log. | 2 | 4 | 7 |  |
| `tools_py/parity/audio_envelope.py` | 414 | Sprint 9: the two symptoms the owner reports in the mission music, as numbers with timestamps. | 2 | 2 | 4 |  |
| `tools_py/parity/audio_parity.py` | 315 | An audio parity test against PCSX2, in the shape of the visual gate (owner, 2026-09-20: "an audio... | 3 | 4 | 10 |  |
| `tools_py/parity/black_rows.py` | 79 | Report the brightest pixel in a row band of every black-screen capture of a run directory (defaul... | 4 | 1 | 8 |  |
| `tools_py/parity/blue_marker.py` | 51 | Sprint 9 Q0b: find the frames of a burst in which a saturated BLUE marker appears -- the arrow th... | 0 | 0 | 0 | **invoked by nothing** (no doc either) |
| `tools_py/parity/cam_poll.py` | 128 | Poll guest memory over PINE while PCSX2 runs (tools_py.parity.drive --target pcsx2 in another | 6 | 2 | 5 |  |
| `tools_py/parity/cb_trace.py` | 313 | The host audio callback trace (PS2X_AUDIO_CB_TRACE, runtime/audio_cb_trace.h): where a 50 ms hole... | 2 | 1 | 2 |  |
| `tools_py/parity/compare.py` | 84 | Score our screens against the golden set and write docs/parity/REPORT.md. | 34 | 11 | 73 |  |
| `tools_py/parity/console_compare.py` | 94 | Console-vs-ours comparison at a fixed gameplay moment: the Seeding Chaos spawn view (Sprint 6 Tas... | 1 | 2 | 3 |  |
| `tools_py/parity/dns_stub.py` | 70 | Tiny UDP DNS responder for the PCSX2 guest: answers the SOCOM II / DNAS hostnames with the | 3 | 0 | 8 | no test |
| `tools_py/parity/drive.py` | 661 | Drive one side (PCSX2 or our exe) through the shared step script and capture each screen. | 44 | 32 | 65 |  |
| `tools_py/parity/endpoint_route.py` | 254 | Move our game's audio to a chosen endpoint for one run, and put everything back -- the endpoint A... | 1 | 1 | 1 |  |
| `tools_py/parity/facing_check.py` | 381 | Sprint 5 Task 2 Step 1 -- validate the at-rest facing estimate offline (zero game runs). | 0 | 1 | 2 | test-only; CLI entry |
| `tools_py/parity/find_dialog_ptr.py` | 41 | Find a static pointer chain to the current dialog's name in a guest RAM dump taken at a known | 1 | 0 | 3 | no test |
| `tools_py/parity/frame_burst.py` | 53 | Capture the game's window at a fixed rate for a while -- the instrument for an animation the step... | 0 | 0 | 3 | **invoked by nothing** (doc-only CLI) |
| `tools_py/parity/freeze_trace.py` | 371 | Sprint 6 Task 3 Step 1 (lock-free) -- freeze_trace: where and for how long an instance's guest ro... | 0 | 1 | 12 | test-only; CLI entry |
| `tools_py/parity/gate.py` | 1147 | One command for the three screenshot gates. PASS/FAIL per gate, exit 1 on any FAIL. | 64 | 43 | 115 |  |
| `tools_py/parity/gsdump_capture.py` | 100 | Capture a multi-frame PCSX2 GS dump at a savestate: launch PCSX2, load the state over PINE, | 2 | 0 | 8 | no test |
| `tools_py/parity/guest_addresses.py` | 530 | One home for the guest addresses the parity instruments reach into the game with, and for the rule | 17 | 6 | 11 |  |
| `tools_py/parity/guest_probe.py` | 289 | The gate's guest-value probe (Sprint 6 Task 1c): a handful of guest values read from a run's [pee... | 4 | 3 | 1 |  |
| `tools_py/parity/host_samples.py` | 104 | Read run_detached.sh's host sampler CSV (marker.cpu.csv). | 0 | 1 | 1 | test-only; CLI entry |
| `tools_py/parity/hostplatform.py` | 193 | Which host are we driving the game on -- and the two things the harness does to the OS. | 10 | 8 | 6 |  |
| `tools_py/parity/keys.py` | 66 | Post keyboard messages to a game window without changing focus. | 50 | 21 | 60 |  |
| `tools_py/parity/ladder_ledger.py` | 125 | Sprint 10 Goal 1 -- "it stays up": the scheduled ladder's ledger. | 1 | 1 | 7 |  |
| `tools_py/parity/lobby_report.py` | 234 | Per-launch lobby summary from a two-instance drive log (Sprint 6 Task 2, research/28). | 3 | 2 | 3 |  |
| `tools_py/parity/loopback_record.py` | 79 | Record what Windows sends to an output device (WASAPI loopback) into a 16-bit PCM WAV. | 5 | 0 | 4 | no test |
| `tools_py/parity/make_gate_fixtures.py` | 196 | Build the committed fixtures under tests/fixtures/gate/ so tools_py/tests/test_gate.py's | 1 | 1 | 2 |  |
| `tools_py/parity/mc_trace.py` | 124 | Read the runtime's '[MC]' trace lines out of a game run log (Sprint 8 Goal 11). | 0 | 1 | 1 | test-only; CLI entry |
| `tools_py/parity/mission_fail.py` | 52 | Does a mission capture show the MISSION FAILURE screen? | 1 | 2 | 3 |  |
| `tools_py/parity/montage.py` | 14 | Tile every PNG of a directory into one labelled contact sheet: python -m tools_py.parity.montage ... | 2 | 0 | 9 | no test |
| `tools_py/parity/motion_diff.py` | 38 | Sprint 6 Task 7: is our player seen moving on the console client? A pure scorer over the PCSX2 wi... | 3 | 1 | 5 |  |
| `tools_py/parity/motion_pack_check.py` | 85 | Is the motion pack (run/motion_p.zar -> DAT_00415e08) intact in an RDRAM image? An offline check,... | 0 | 1 | 4 | test-only; CLI entry |
| `tools_py/parity/movie_blocks.py` | 546 | Find 16x16 movie blocks the GL render target is missing but shadow VRAM has. | 0 | 2 | 16 | test-only; CLI entry |
| `tools_py/parity/music_state_poll.py` | 1204 | Poll the game's EE-side sound DECISION machines on either machine and log every change of what they | 0 | 1 | 5 | test-only; CLI entry |
| `tools_py/parity/object_diff.py` | 416 | Object-keyed uninitialised-field diff -- Sprint 5 Task 4 Step 1 (Leg 0, zero game runs). | 1 | 1 | 5 |  |
| `tools_py/parity/online_ladder.py` | 430 | The engagement ladder's round loop and stop rules (Sprint 5 Amendment A: A1 per-round stop rules,... | 1 | 5 | 4 |  |
| `tools_py/parity/online_login.py` | 136 | Drive the PCSX2 SOCOM II client from savestate 9 ("LOGIN TO SOCOM II ONLINE") through universe | 3 | 3 | 6 |  |
| `tools_py/parity/online_login_ours.py` | 2530 | Drive OUR exe from boot through ONLINE -> LOGIN -> universe -> persona/password (on-screen | 11 | 24 | 30 |  |
| `tools_py/parity/online_match.py` | 140 | Two PCSX2 SOCOM II clients on the local Horizon stack: A hosts a game, B joins it, both go | 3 | 0 | 4 | no test |
| `tools_py/parity/online_match_ours.py` | 5278 | Two instances of OUR exe play a match on the local Horizon stack: A logs in and hosts a game | 16 | 29 | 35 |  |
| `tools_py/parity/p2s_extract.py` | 37 | Extract a member (default eeMemory.bin) from a PCSX2 .p2s savestate: a zip whose entries use | 0 | 0 | 3 | **invoked by nothing** (doc-only CLI) |
| `tools_py/parity/pcm_dump.py` | 64 | Sprint 9 Q0: read a PS2X_AUDIO_PCM_DUMP file -- what the EE wrote into the 989snd PCM ring (the m... | 0 | 1 | 2 | test-only; CLI entry |
| `tools_py/parity/pcsx2_ctl.py` | 260 | Stepwise control of the two PCSX2 SOCOM II instances (Sprint 4 Task 5's logs/s4_ctl.py, promoted ... | 5 | 2 | 6 |  |
| `tools_py/parity/pcsx2_keys.py` | 54 | Post keyboard messages to PCSX2's window (no focus change), using its [Pad1] keyboard bindings | 1 | 0 | 4 | no test |
| `tools_py/parity/pcsx2_shell.py` | 88 | Sprint 10 Goal 3: the console side of the mixed match pressing on what its screen shows. | 3 | 1 | 7 |  |
| `tools_py/parity/pine.py` | 113 | Minimal PCSX2 PINE client (TCP on Windows; port = PINESlot in tools/pcsx2/inis/PCSX2.ini). | 5 | 1 | 10 |  |
| `tools_py/parity/pins.py` | 275 | Pinned inputs: the record of what a measurement was computed against, and the refusal when it dri... | 11 | 7 | 38 |  |
| `tools_py/parity/probe_poll.py` | 103 | Poll the collision query object on PCSX2 at a savestate: launch PCSX2, load the state over | 1 | 0 | 4 | no test |
| `tools_py/parity/resize_window.py` | 74 | Give the running game window a CLIENT area of <w>x<h>, then exit. | 0 | 0 | 7 | **invoked by nothing** (doc-only CLI) |
| `tools_py/parity/scale_compare.py` | 42 | Sprint 7 Task 1c: is a 1280x896 frame the 640x448 frame, or a different render? | 1 | 2 | 2 |  |
| `tools_py/parity/scale_shot.py` | 224 | Sprint 7 Task 1c: one screen of the game, captured at 640x448 and at 1280x896, from the runtime. | 0 | 1 | 3 | test-only; CLI entry |
| `tools_py/parity/screen_bands.py` | 48 | The letterbox-band test: is a captured frame gameplay, or the letterboxed intro cinematic? | 4 | 1 | 3 |  |
| `tools_py/parity/sim_walk_to_b.py` | 1198 | Closed-loop dry run of the approach loop against a SIMULATED world -- no match, no game. | 1 | 6 | 10 |  |
| `tools_py/parity/sp_death_probe.py` | 1159 | Sprint 5 Task 2 Steps 2-5: one single-player run that confirms the kill readout, with the aim | 11 | 3 | 16 |  |
| `tools_py/parity/state_poll.py` | 69 | Launch PCSX2, load a savestate over PINE and sample pointer-chain specs (PS2X_PEEK syntax) as | 1 | 0 | 2 | no test |
| `tools_py/parity/stream_events.py` | 136 | Sprint 9 Q0 (2026-09-20): read the mixer's stream-event trace out of a run log and turn it into t... | 0 | 1 | 5 | test-only; CLI entry |
| `tools_py/parity/two_machine_readout.py` | 267 | Sprint 7 Task 5 (spec Goal 5): the readout the owner runs after the first TWO-MACHINE match. | 1 | 2 | 7 |  |
| `tools_py/parity/verdict_core.py` | 1374 | Pure online verdict scorers: is a side controllable, is its move path alive, is it network-starved, | 15 | 25 | 15 |  |
| `tools_py/parity/verdict_replay.py` | 1112 | Replay kill verdict from two stored run logs -- the VALVE-primary scorer (Sprint 5 Task 6 Step 1). | 3 | 5 | 14 |  |
| `tools_py/parity/winshot.py` | 217 | Focus-free capture of a top-level window's client area (PrintWindow, PW_RENDERFULLCONTENT). | 13 | 20 | 15 |  |
| `tools_py/parity/x11shot.py` | 278 | winshot's Linux half: capture a window, size it, raise it, and inject keys, under X11. | 8 | 2 | 4 |  |
| `tools_py/patch_fifo_trace.py` | 41 | Add PS2X_TRACE_FIFO=1 tracing of the VIF1/GIF/fromSPR DMA and INTC path, to diagnose the | 0 | 0 | 2 | **invoked by nothing** (doc-only CLI) |
| `tools_py/patch_istat.py` | 50 | Implement EE INTC I_STAT (0x1000F000): raise VBLANK bits on the scheduler's vblank events, | 0 | 0 | 2 | **invoked by nothing** (doc-only CLI) |
| `tools_py/patch_mfifo.py` | 255 | One-off patch: add fromSPR/toSPR DMA channels and MFIFO ring draining to ps2_memory.cpp/h. | 0 | 0 | 1 | **invoked by nothing** (doc-only CLI) |
| `tools_py/patch_vif1_intc.py` | 62 | Raise EE INTC cause 5 (VIF1) when the VIF1 interpreter processes a VIFcode with the interrupt | 0 | 0 | 1 | **invoked by nothing** (doc-only CLI) |
| `tools_py/portable_audit.py` | 295 | Sprint 9 Goal 2: what the portable folder carries is decided from import tables, and checked. | 4 | 4 | 6 |  |
| `tools_py/r0004/capsule.py` | 483 | Decode the encrypted code stack inside PSRewired's r0004 patch capsule. | 6 | 4 | 14 |  |
| `tools_py/ra2fun.py` | 35 | Map guest addresses (e.g. the ra= of a PS2X_CALL_TRACE line) to the decomp function that | 0 | 0 | 1 | **invoked by nothing** (doc-only CLI) |
| `tools_py/rdr_tree.py` | 46 | Print a parsed .rdr tree from a guest RAM dump (PS2X_RDRAM_DUMP=<file>:<seconds>). | 1 | 1 | 5 |  |
| `tools_py/readable_names.py` | 452 | The readable-name renderer: a demo mangled name -> the csv 'Name' (Sprint 12 Task 1; research/47,... | 10 | 2 | 8 |  |
| `tools_py/recomp_census.py` | 248 | Census of a ps2xRecomp output directory and its recomp_run.log, and the diff of two censuses. | 0 | 1 | 5 | test-only; CLI entry |
| `tools_py/release/leakcheck.py` | 802 | The gate that decides whether this repository may face outward -- one command, exit non-zero on a... | 11 | 4 | 13 |  |
| `tools_py/release/leakrules.py` | 395 | The shapes a leak takes, as regular expressions -- one set, shared by every mode of 'leakcheck'. | 5 | 1 | 3 |  |
| `tools_py/research/symbols/bindiff_join.py` | 470 | BinDiff's demo1 -> r0001 function matches, joined to Task 7's 987 pairs (Sprint 12, research note... | 2 | 0 | 2 | no test |
| `tools_py/research/symbols/callgraph_propagation.py` | 693 | Call-graph propagation from anchors: do callers and callees of placed pairs name the bodies between? | 1 | 0 | 1 | no test |
| `tools_py/research/symbols/class_inventory.py` | 942 | The demo's class inventory as an architecture map, and what the runtime's hooks touch (Sprint 12 | 1 | 0 | 1 | no test |
| `tools_py/research/symbols/debug_paths.py` | 52 | What the SOCOM 1 demo's .debug section actually covers: source paths by directory, and how often | 2 | 0 | 3 | no test |
| `tools_py/research/symbols/dwarf_types.py` | 1473 | What the SOCOM 1 demo's DWARF1 '.debug' section holds, walked by ccc, and which of the raw guest ... | 1 | 0 | 1 | no test |
| `tools_py/research/symbols/link_order.py` | 76 | Does link order survive between the SOCOM 1 demo and our image? (Task 7 review, socom-pc-6c) | 2 | 0 | 2 | no test |
| `tools_py/research/symbols/name_consumers.py` | 714 | Research/46 (Sprint 12 research wave, question 1): who reads a function name or a raw guest offset, | 1 | 0 | 1 | no test |
| `tools_py/research/symbols/offset_multiset.py` | 752 | Member-offset multisets as a looser body key (Sprint 12 research wave, question 9; research/54). | 1 | 0 | 1 | no test |
| `tools_py/research/symbols/readable_names.py` | 92 | Metrowerks (GNU v2 style) mangled name -> Class_Method, with the overload-collision census. | 10 | 2 | 8 |  |
| `tools_py/research/symbols/readable_proof.py` | 756 | The readable-name scheme, proven over four name sets (Sprint 12 research Q2; docs/research/47). | 1 | 0 | 1 | no test |
| `tools_py/research/symbols/sase_probe.py` | 514 | SASE, SOCOM II's voice codec: what the images say about it (research Q11, Sprint 12; read-only). | 1 | 0 | 1 | no test |
| `tools_py/research/symbols/sidecar_census.py` | 481 | The provenance sidecar (spec 1.3), checked against the tree. Sprint 12 research Q3, docs/research... | 1 | 0 | 2 | no test |
| `tools_py/research/symbols/string_correlator.py` | 714 | Strings as first-class evidence: a shared-string correlator between the SOCOM 1 demo and r0001. | 3 | 0 | 2 | no test |
| `tools_py/research/symbols/toml_names.py` | 546 | The recompiler's naming pipeline, re-derived from the tracked inputs and the recompiler's own rules. | 5 | 2 | 1 |  |
| `tools_py/research/symbols/toml_overlap.py` | 49 | How much of the 479 is new? Proposals against recomp/socom2.toml's name@addr list, and the | 1 | 0 | 4 | no test |
| `tools_py/research/symbols/vtable_anchors.py` | 114 | How far do today's body-matched pairs get a vtable-slot matcher? (Task 7c groundwork, socom-pc-6c) | 1 | 0 | 4 | no test |
| `tools_py/research/symbols/vtable_coverage.py` | 879 | Vtable coverage after 7c: the classes the bare-name RTTI walk cannot open, and what opens them. | 2 | 0 | 2 | no test |
| `tools_py/research/symbols/vtable_rtti.py` | 145 | Locate retail vtables from the class-name string alone: string -> __RTTI__ object -> vtable(s). | 4 | 0 | 5 | no test |
| `tools_py/research/terrain/classify2.py` | 74 | Both terrain program families of the spawn frame, replayed with the clip planes AND the backface-... | 1 | 0 | 1 | no test |
| `tools_py/research/terrain/clip_planes.py` | 25 | For a family-B terrain dump: the plane qwords 30-36, and per primitive the signed distances of it... | 1 | 0 | 0 | no test |
| `tools_py/research/terrain/cull_trace_scan.py` | 31 | Scan a PS2X_CULL_TRACE log (research/31 section 16): per call the guest's result / mask against t... | 1 | 0 | 0 | no test |
| `tools_py/research/terrain/deferred_trace_scan.py` | 22 | Per frame: the deferred-list enqueues ("defer" lines) and flushes ("flush" lines) of a PS2X_CULL_... | 0 | 0 | 0 | **invoked by nothing** (no doc either) |
| `tools_py/research/terrain/detail_sections_scan.py` | 34 | Per frame, every component FUN_003b6e10 sized: the main-pass count, the detail groups it will dra... | 0 | 0 | 0 | **invoked by nothing** (no doc either) |
| `tools_py/research/terrain/detail_trace_scan.py` | 23 | Scan the "detail t=... comp=... flags=... dist=... near=... count=... table=... n=... [thr:c8,ca]... | 0 | 0 | 0 | **invoked by nothing** (no doc either) |
| `tools_py/research/terrain/ee_compare.py` | 61 | Set our guest RAM at the spawn view (PS2X_RDRAM_DUMP) against the PCSX2 slot-8 savestate's eeMemo... | 0 | 0 | 1 | **invoked by nothing** (doc-only CLI) |
| `tools_py/research/terrain/eye_experiment.py` | 54 | Which of our VU1 dumps kicks the under-water terrain fan (tex0 0x36b1), and does the kicked trian... | 2 | 0 | 0 | no test |
| `tools_py/research/terrain/fan_detail.py` | 36 | (no docstring) | 3 | 0 | 0 | no test |
| `tools_py/research/terrain/fan_sizes.py` | 46 | Per stream: for tex0 0x36b1, every GIF packet whose tag has PRE=1 and PRIM type 5 (fan): (packet ... | 1 | 0 | 0 | no test |
| `tools_py/research/terrain/lod_trace_scan.py` | 26 | Scan the "lod t=... comp=... dist=... entry=... near=a/b/c far=d/e/f flags=... fade=x->y result=r... | 0 | 0 | 0 | **invoked by nothing** (no doc either) |
| `tools_py/research/terrain/node_trace_scan.py` | 50 | Scan a PS2X_CULL_TRACE log that also carries the scene-node lines ("node t=... obj=..."): pair ea... | 0 | 0 | 0 | **invoked by nothing** (no doc either) |
| `tools_py/research/terrain/patch_dump.py` | 22 | (no docstring) | 1 | 0 | 0 | no test |
| `tools_py/research/terrain/terrain_dumps.py` | 30 | Terrain (tex0 0x36b1) VU1 dumps: per dump the header counts (TOP+2.x index offset, .z vertices, .... | 1 | 0 | 0 | no test |
| `tools_py/research/terrain/unproject.py` | 72 | Fit the world->screen projective map from dump 237's vertices (world) and the no-clip replay (scr... | 1 | 0 | 1 | no test |
| `tools_py/resolve_mmio.py` | 183 | Re-derive the true effective address for every [mmio] override in recomp/socom2.toml. | 0 | 0 | 3 | **invoked by nothing** (doc-only CLI) |
| `tools_py/revision_toml.py` | 1011 | Carry a PS2Recomp configuration from one build's addresses onto another build's (Sprint 11 Task 19). | 2 | 3 | 6 |  |
| `tools_py/story/cite.py` | 591 | The citation test for 'docs/STORY.md' -- Sprint 11 Goal 6's teeth. | 9 | 3 | 22 |  |
| `tools_py/story/remap.py` | 170 | Carry the story's commit citations across a history rewrite -- spec 4.4, decision D1. | 0 | 1 | 9 | test-only; CLI entry |
| `tools_py/story/site.py` | 523 | Render the story as one page in the site's own chrome: a vertical timeline under the s2u top bar ... | 15 | 8 | 57 |  |
| `tools_py/story/timeline.py` | 107 | Rebuild 'docs/story/timeline.json' from 'docs/STORY.md' -- the machine-readable twin (spec 6.1). | 7 | 5 | 16 |  |
| `tools_py/story/witness.py` | 149 | Freeze a witness for every run, gate and log citation in 'docs/STORY.md' -- spec 4.3. | 3 | 1 | 10 |  |
| `tools_py/string_lever.py` | 616 | Sprint 12 Task 12: the 'string-set' pass -- names from the set of shared strings a body references. | 0 | 1 | 2 | test-only; CLI entry |
| `tools_py/symbol_levers.py` | 743 | Sprint 11 Task 7b: two more levers on the SOCOM 1 demo's names -- position, and a third build. | 12 | 3 | 10 |  |
| `tools_py/toml_stub_lever.py` | 268 | The 'toml-stub' pass: the toml's own 'name@addr' stub selectors as proposals (Sprint 12 Task 8, G... | 0 | 2 | 0 | test-only, undocumented |
| `tools_py/translate_extras.py` | 366 | Carry one build's forced entry points onto another build's addresses (Sprint 11 Task 19). | 0 | 1 | 2 | test-only; CLI entry |
| `tools_py/ui_binding_lever.py` | 536 | The 'ui-binding' lever: name r0001's UI script handlers from the demo's (Sprint 12 Task 14; resea... | 0 | 1 | 2 | test-only; CLI entry |
| `tools_py/vm_prune.py` | 115 | What scripts/vm_sync.sh tree must delete in the guest: files under the synced roots that the host no | 2 | 2 | 1 |  |
| `tools_py/vm_restamp.py` | 56 | What scripts/vm_sync.sh tree must touch in the guest: the files the sync actually changed. | 1 | 1 | 0 |  |
| `tools_py/vtable_lever.py` | 808 | Sprint 12 Task 4 (Task 7c): the 'vtable-slot' lever -- name a virtual function by its slot. | 0 | 1 | 3 | test-only; CLI entry |
| `tools_py/vu1_headers.py` | 140 | Print the VU1 dispatcher header counts (TOP+2.z / TOP+2.w) of a set of program dumps. | 1 | 0 | 3 | no test |
| `tools_py/vu1dis.py` | 212 | Minimal VU0/VU1 micro-program disassembler. | 0 | 0 | 11 | **invoked by nothing** (doc-only CLI) |
| `tools_py/vu1stats_summary.py` | 52 | Summarize the [vu1-stats] lines of a run log (PS2X_VU_STATS=1): per-30 s phases and the last | 0 | 0 | 5 | **invoked by nothing** (doc-only CLI) |

## Appendix B — scripts (code files; data files under `scripts/parity/` are counted in 2.1)

| script | lines | header, first line | code refs | doc refs | note |
|---|---|---|---|---|---|
| `scripts/agent_worktree.sh` | 70 | The worktree an agent gets, exactly as docs/HANDOFF.md prescribes | 0 | 2 | hard-codes `/c/projects` (#14) |
| `scripts/archive_logs.ps1` | 97 | Moves old gate stamps and run logs out of logs/ to an archive drive | 1 | 6 | |
| `scripts/bootstrap_windows.sh` | 105 | The Windows toolchain a fresh clone needs, fetched and verified | 7 | 7 | |
| `scripts/build_linux.sh` | 185 | Linux build: the same CMake tree as build.sh | 5 | 18 | |
| `scripts/build_revision.sh` | 413 | The pipeline, parameterised by disc revision | 8 | 13 | issue #48 (`--out`) |
| `scripts/check_quiet_gate.sh` | 48 | the read side of R46/A5's launch hygiene | 6 | 15 | per-tree marker (#13) |
| `scripts/disc_to_elf.sh` | 25 | Your own SOCOM II disc -> the files ./build.sh recomp needs | 4 | 7 | wrapper of `tools_py/disc_to_elf.py` |
| `scripts/embed_font.py` | 50 | a TTF into a C header, so the portable folder stays self-contained | 1 | 3 | called by the launcher's CMake |
| `scripts/embed_image.py` | 49 | a PNG into a C header | 0 | 0 | **invoked by nothing** (#49) |
| `scripts/fetch_private_inputs.sh` | 47 | Fetch the owner's git-ignored build inputs | 0 | 4 | owner/cloud entry point |
| `scripts/flake_repro.py` | 84 | Contention harness for the threaded simulation tests | 0 | 1 | one-off, KNOWN §3 cites it |
| `scripts/ghidra_export_functions.sh` | 107 | The Ghidra headless recipe that produced recomp/socom2_ghidra.csv | 1 | 2 | |
| `scripts/github_labels.sh` | 70 | the repository's label set, as code | 3 | 4 | |
| `scripts/hooks/pre-commit` | 19 | The leak check over what this commit is about to take | 5 | 9 | |
| `scripts/hooks/pre-push` | 36 | The leak check over every commit this push would publish | 0 | 5 | installed via `core.hooksPath` |
| `scripts/install_hooks.sh` | 11 | Point this clone's git hooks at scripts/hooks/ | 2 | 8 | |
| `scripts/kill_stale_drivers.ps1` | 69 | Kill stale harness DRIVERS and game instances before a launch | 7 | 11 | |
| `scripts/ladder_job.sh` | 44 | one scheduled run of the engagement ladder against the hosted server | 1 | 10 | hard-coded ROOT (#14), pre-check race (#12) |
| `scripts/loop_lock.sh` | 588 | Serializes runtime builds and game runs between agents | 15 | 33 | #35, #36 |
| `scripts/make_portable.sh` | 147 | the portable folder | 13 | 21 | |
| `scripts/make_server_zip.sh` | 72 | the hosted-server folder | 2 | 6 | |
| `scripts/pin_harness.sh` | 104 | Snapshots tools_py/ and scripts/ at <sha> into <out_dir>/harness/ | 6 | 4 | |
| `scripts/portable_libs.py` | 159 | which shared libraries the Linux portable folder carries | 3 | 3 | |
| `scripts/python_env.sh` | 56 | where every shell script finds Python | 19 | 0 | `build.sh` does not use it (#32) |
| `scripts/run_detached.sh` | 245 | Launch a long job detached, holding the loop lock | 15 | 29 | no `--wait` (#8) |
| `scripts/vm_sync.sh` | 54 | sync the tree into the socom-linux VM | 7 | 12 | |
| `scripts/parity/audio_parity.sh` | 153 | The audio parity check | 4 | 9 | |
| `scripts/parity/capture_audio_out.sh` | 29 | one briefing capture with the callback trace on | 1 | 1 | `SOCOM_DATA_ROOT` default `/c/projects/socom_pc` |
| `scripts/parity/drag_window.ps1` | 54 | hold the game window in the modal size-move loop (Sprint 7 Task 1b) | 0 | 2 | |
| `scripts/parity/endpoint_ab.sh` | 98 | The endpoint A/B | 0 | 5 | run by hand (HUMAN_TASKS) |
| `scripts/parity/env.sh` | 75 | the shared environment for the online harness scripts | 35 | 20 | LAN default (#19) |
| `scripts/parity/ladder_frostfire.sh` | 201 | TEMPLATE -- the engagement-ladder launch on FROSTFIRE | 12 | 15 | |
| `scripts/parity/lobby_rate_queue.sh` | 27 | the lobby rate, measured: ten control rounds on one map | 0 | 2 | near-duplicate of the next |
| `scripts/parity/mission_music_long.sh` | 248 | the mission-music instrument | 6 | 2 | |
| `scripts/parity/mixed_match.sh` | 87 | the mixed match, leg 1 (macros) | 5 | 6 | superseded by `mixed_match2.sh` |
| `scripts/parity/mixed_match2.sh` | 116 | leg 1 on the verified flow | 4 | 3 | last run 2026-09-20 |
| `scripts/parity/mixed_match2_leg2.sh` | 113 | leg 2: the console hosts, ours joins | 3 | 1 | last run 2026-09-20 |
| `scripts/parity/online_control_queue.sh` | 35 | control rounds on every map not yet driven online | 0 | 3 | last full pass 2026-09-16/17 |
| `scripts/parity/online_control_round.sh` | 35 | one online control round on a named map | 3 | 10 | |
| `scripts/parity/online_match_frostfire.sh` | 54 | LEGACY converge path, superseded by ladder_frostfire.sh | 4 | 6 | archive candidate |
| `scripts/parity/refs/make_voice_ref.py` | 89 | the reference voice WAV, generated and never recorded | 1 | 2 | |
| `scripts/parity/two_machine_readout.sh` | 28 | the one line the owner runs after the first TWO-MACHINE match | 2 | 5 | never had input (#18) |
