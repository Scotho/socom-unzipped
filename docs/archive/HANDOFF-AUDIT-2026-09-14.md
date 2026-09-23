# Claude Workflow Handoff Audit - 2026-09-14

> **ARCHIVED.** An audit of the handoff process written 2026-09-14 and superseded by `docs/audits/2026-09-20-test-harness-and-process-audit.md` and `docs/DOC_MAINTENANCE.md`. Kept because it is cited; read it as history only. See `docs/DOC_MAINTENANCE.md` (class A).


Audience: the Claude/controller agent supervising the autonomous sprint workflow.

Goal under audit: native SOCOM 2 on modern machines, lightly modernized and maintainable for a community project.

## Executive Verdict

The project has made real, goal-relevant progress. This is no longer just a recompilation scaffold: the Windows native executable builds, boots, drives menus, reaches single-player gameplay, and can run two local Horizon-backed online instances through Frostfire. Sprint 5 produced the first confirmed online kill in the native port, with independent scorers agreeing on rounds 1-3 of `s5_t5_ladder2`.

Do not treat Sprint 5 as merge-complete yet. During this audit, the first final gate at `logs/parity/gate/s5_head_1x/summary.txt` failed mission liveness:

```text
PASS title
PASS transition
FAIL mission ... 0 live hold pairs (need 2)
```

A mission-only rerun then passed at `logs/parity/gate/s5_head_1x_b/summary.txt`:

```text
PASS mission ... 4 live hold pairs (need 2)
```

The controller recorded R76 accepting the close-out gate as title PASS plus transition PASS from `s5_head_1x`, and mission PASS from the same-exe rerun `s5_head_1x_b`. The remaining close-out work is the uncommitted final fix wave for I1-I3.

## Current Working Tree

Observed branch: `sprint-5`, at `ab3559c` (`origin/sprint-5` same commit when checked). The final verification report notes that the close-out build/test/gate actually ran before these uncommitted fix-wave edits, on the same runtime/exe path; preserve that distinction.

Do not revert or absorb unrelated local/user state:

- `server/config/simulated.db` is modified.
- `ONBOARDING.md` is untracked.
- Notable uncommitted final-fix-wave files include `README.md`, `docs/STATUS.md`, `docs/research/21-frostfire-control-handover.md`, `docs/research/22-kill-readout.md`, the Sprint 5 plan, `scripts/parity/ladder_frostfire.sh`, `scripts/parity/online_match_frostfire.sh`, `tools_py/parity/online_match_ours.py`, `tools_py/tests/test_loop_lock.py`, `tools_py/tests/test_verdict_replay.py`, and the replay fixture docs/scripts.
- `tools_py/tests/fixtures/replay/l2r1_A.txt` and `tools_py/tests/fixtures/replay/l2r1_B.txt` are untracked new files.
- `docs/research/assets/22-first-kill-evidence.txt` is an untracked new manifest.

That fixture work appears to be in-flight work for I1: it adds a `dense` trimming mode, local ladder-2 round-1 fixtures, a `TestLadderLaunch2Round1Kill` test in `test_verdict_replay.py`, and an acceptance manifest. A direct offline check of the new pair passed: `python -m tools_py.parity.verdict_replay tools_py/tests/fixtures/replay/l2r1_A.txt tools_py/tests/fixtures/replay/l2r1_B.txt --offset-b 5.60` returned `KILL killer=A victim=B t=141.33 round=1`. However, the new fixture and manifest files are not tracked yet.

Narrow checks run during this audit:

- `python -m unittest tools_py.tests.test_verdict_replay.TestLadderLaunch2Round1Kill -v` passed 5/5.
- `python -m unittest tools_py.tests.test_loop_lock.TestRaces.test_smoke_racing_reapers_with_process_list_latency_one_wins tools_py.tests.test_loop_lock.TestInterleavings.test_smoke_stale_mutex_takers_never_double_enter -v` passed 2/2 in 21.47 s.
- `python -m unittest tools_py.tests.test_loop_lock.TestSlowSuiteStamp -v` failed because `tools_py/tests/fixtures/loop_lock_slow_green.txt` does not exist.

## What Is Validated

The following claims are supported by tracked docs plus local logs/artifacts:

- Native pipeline exists: decrypted overlays are merged and recompiled through the PS2Recomp fork into `dist/socom2.exe`.
- Single-player reaches the mission/HUD path; title and menus run around 59 fps; Albania 5-1 is visible but still has gameplay correctness issues.
- Sprint 3's native VU1 state is stable: 162/166 lists native and bit-exact, with four documented residual lists.
- Sprint 4 correctly fixed several false-green classes: macroblock root cause, gate silent failures, vram-diff coverage, `rand()` width, soft-double ABI binding, and the Medley online movement blocker.
- Sprint 5 fixed Frostfire control through VU0 `vf0.w = 1` on `StartThread` contexts (`b625291`), then fixed the single-player present stall by bounding GS backlog (`8281254`/`7448601`/`92d30f0`).
- The acceptance run is credible: `bash scripts/parity/ladder_frostfire.sh --pinned logs/parity/s5_t5_ladder2`, harness `171290b`, exe sha `234b4772cd0a8bf8...`, rounds 1-3 KILL on KillWatch and `verdict_replay`, with death/health/team/screen evidence and an independent re-derivation.
- The off-repo archive now exists at `D:/socom_archive/acceptance/s5_ladder2` with logs, screenshots, harness snapshot, and `SHA256SUMS`.
- The mission-only close-out rerun `s5_head_1x_b` passed after the first full `s5_head_1x` gate failed mission liveness.
- `PS2X_TEST_REPEAT=3 ./build.sh test` is recorded in `.superpowers/.../closeout-verify-report.md`: native C++ `450/450` on all 3 runs, Python `837` OK with 63 skipped.
- R76 is recorded: the first mission failure was a paused HELP pop-up class, not a stale-frame or cinematic false green; dismissal is parked to Sprint 6.

## What Is Not Yet Closed

1. Final verification needs the ruling preserved, not reopened silently.

The latest complete three-stage gate directory (`s5_head_1x`) has title/transition PASS and mission FAIL. The mission-only rerun (`s5_head_1x_b`) has mission PASS, and R76 accepts the combination. If a reviewer disagrees with R76, require a fresh full three-stage gate rather than reinterpreting these artifacts after the fact.

2. Acceptance evidence is still not durable enough in the repo.

The archive exists, local `l2r1_A/B.txt` fixtures have appeared, a passing-kill test is present, and `docs/research/assets/22-first-kill-evidence.txt` exists. But those new proof files are not tracked yet. Finish I1: track the fixtures and manifest, then run the targeted replay test before commit.

3. R73 is only partly addressed.

`test_loop_lock.py` now has WIP always-on smoke slices for one reaper race and one stale-mutex double-entry check, plus a visible `TestSlowSuiteStamp` test. The two smoke tests passed when run directly, but the stamp test failed because `tools_py/tests/fixtures/loop_lock_slow_green.txt` is missing. Finish or re-rule the stamp side explicitly.

4. Docs still need a final WIP review before staging.

Examples found in tracked files:

- `docs/CURRENT_SPRINT.md` still lists final verification as future/pending even though the close-out report now records test repeat plus R76 gate acceptance.
- `docs/STATUS.md` still has at least one stale top-line value in the base tree (`802` tests); the close-out report records `837`.
- `docs/STATUS.md` still phrases fixed Frostfire control as `vf0.w = 0` in the top summary lines, even though the shipped fix is `vf0.w = 1` on `StartThread` contexts.
- `README.md` still says the ladder template's pinned default and exit codes are "being revised by a close-out fix wave"; the current script header already describes pinned-by-default and `--live`.
- Some roadmap and handoff sections are correct only through superseding blockquotes; this is hard for new contributors to follow.

Clean the docs after the final gate result, not before.

## Sprint Audit

Sprint 1-2: useful foundation work. The project bootstrapped native execution, parity references, and early renderer/VU paths. The biggest lesson was process-oriented: screenshots and "it booted" were too weak without liveness and negative controls.

Sprint 3: strong renderer/VU milestone. Render-target scale, presentation filtering, native VU1 families, and `--vram-diff` coverage moved the port materially toward modern-machine playability. Residual VU1 lists were documented rather than hidden.

Sprint 4: high-value correction sprint. It fixed the online Medley movement blocker and several test blind spots. It also exposed the main process hazard for this project: false greens from harness/scorer assumptions. The sprint ended with an acceptance harness but not an acceptance pass.

Sprint 5: real breakthrough, but fragile. It delivered Frostfire control and the first native online kill. It also expanded the harness substantially: lobby resend, per-round laddering, freeze/starvation detection, route geometry, scorer bars, pinned harness snapshots, and lock discipline. This is powerful but not yet community-maintainable; it needs consolidation, durable fixtures, and simpler default workflows.

## Risks Against The Original Goal

The native-port goal is broader than "one first kill." These are the highest-risk gaps:

- Repeatability: the acceptance kill is a single confirmed ladder launch. Round 4 missed indefinitely despite being inside the aim tolerance, which points to aim/fire control still being brittle.
- Stability: online freezes under host load remain unrooted. Rung 0 failed on A due to back-pressure waits even with Valheim closed and VirtualBox left open.
- Gameplay correctness: single-player teleports, skeleton-root/camera decay, and the HELP-pop-up mission gate flake all matter for "lightly modernized playable port."
- Evidence hygiene: key proof still depends on gitignored logs and an off-repo archive unless the manifest/fixture lands.
- Maintainability: the harness now has many knobs, route files, scorers, stop rules, and launch wrappers. Without a trimmed contributor path, community maintainers will struggle to distinguish required defaults from sprint-only instruments.

## Merge Checklist

Before merging Sprint 5:

- Preserve R76 in the ledger/docs: `s5_head_1x` title/transition PASS plus mission FAIL, then `s5_head_1x_b` mission PASS accepted as close-out gate.
- Confirm the full `PS2X_TEST_REPEAT=3 ./build.sh test` result stays attached to the intended tree/runtime in the ledger.
- Finish I1: tracked ladder-2 kill fixture/test plus repo manifest for `D:/socom_archive/acceptance/s5_ladder2`.
- Finish I2/R73: always-on lock race slice and slow-suite hygiene stamp, or a clearly documented controller re-ruling.
- Finish I3: update `CURRENT_SPRINT.md`, remove committed "Draft, uncommitted" banners, correct suite counts/status text, and make Sprint 6 the unambiguous next pointer.
- Run one final `git status --short --branch`; explicitly account for `server/config/simulated.db`, `ONBOARDING.md`, and any in-flight fixture edits.

## Recommended Sprint 6 Order

1. Close Sprint 5 honestly: final gate result, R73/I1 evidence hardening, and docs sync.
2. Acceptance repeatability: fix the aim/fire loop that caused round 4's 111 in-tolerance misses; then require repeated ladder passes under the pinned harness.
3. Lobby hardening: classify dropped CROSS/news-to-rooms correctly, isolate READY behavior, and make failures cheap.
4. Online freeze/back-pressure root cause: separate host-load artifact, runtime pacing, VSync waits, and GS back-pressure.
5. Gameplay-state gate probe: make the gate detect a controllable actor and state change, not just bright HUD bands.
6. Single-player visible correctness: teleports, skeleton-root/camera decay, camera height, and any reset artifacts.
7. Exact-oracle/HLE audit leg three: display-env constants, rem_pio2f precision, VU-memory aliasing, timer/IRQ assumptions.
8. Maintainability pass: retire sprint-only knobs, document a contributor "build, run, verify" path, and make acceptance fixtures cheap to replay.

## Controller Rules To Preserve

- No build, gate, game launch, or expensive unittest while a loop lock or quiet marker is active. On this Windows host use `C:/Program Files/Git/bin/bash.exe`; bare `bash` may not resolve.
- Do not accept screenshots alone for gameplay claims. Require liveness, guest-memory fields, or independent scorer agreement.
- Pre-register acceptance bars before launches. If a live PASS field or bar changes, require independent re-derivation before declaring the sprint goal met.
- Keep the runtime frozen at `92d30f0` for the accepted ladder evidence until Sprint 6 intentionally reopens runtime work.
- Avoid `git add -A`; stage explicit paths only. Do not revert local modifications that are not owned by the current task.
- Treat every green timing run as a sample, not a verdict. Repeat only after the measurement itself is trustworthy.

## Bottom Line

Sprint 5 is a legitimate milestone toward the native SOCOM 2 community port: it proves local online gameplay can reach a real kill in the native executable. The next controller action is not "start a shiny new sprint"; it is to finish the close-out proof so this milestone survives future maintenance: passing final gate or investigated failure, tracked acceptance fixture, tracked archive manifest, restored lock race coverage, and cleaned handoff/status docs.
