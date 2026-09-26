---
name: run-gate
description: Run a build, a game launch or the three-stage parity gate under the loop lock and record it -- use before any `./build.sh`, game run, gate or chain, and when a runtime, recomp/, tools_py/parity/, scripts/parity/ or build.sh change needs its gate.
---

# A build or gate run, and its record

What a controller runs. The lock's full rules (the queue, the reaper, mixed versions, the rollout of a new lock
script) are `scripts/loop_lock.sh`'s header; the gate's options are `tools_py/parity/gate.py`'s docstring. Sources:
the old `docs/LOOP_PROMPT.md` "Lock protocol" (`docs/archive/LOOP_PROMPT-to-2026-09-26.md`), `docs/HANDOFF.md` §5
rules 5-6 and §7 "Instruments".

**When the gate is owed** (HANDOFF §5 rule 5): anything touching `third_party/ps2recomp/`, `recomp/`,
`tools_py/parity/`, `scripts/parity/` or `build.sh` -- `./build.sh test` and the three-stage gate green BEFORE the
commit, `./build.sh runtime` first when the runtime changed (`build.sh test` does not rebuild `dist/socom2.exe`).
**One build or launch at a time, host-wide** (rule 6): the owner feels long builds and game runs on this machine;
two-instance online runs only when the owner is away.

## Steps

1. **Quiet and free?** `bash scripts/check_quiet_gate.sh` -- exit 0 proceeds, exit 3 names who holds the quiet
   marker (a launch is running: start nothing). `bash scripts/loop_lock.sh check` -- `FREE`, or `HELD` with the
   holder, purpose and heartbeat age, then any `QUEUED:` lines. If held, do lock-free work; never hold the lock
   across tool calls any other way than steps 2-3.
   When a lock-script rollout is under way (a new `scripts/loop_lock.sh` landing; the procedure is `docs/HAZARDS.md`'s
   lock area), this applies:
   **Mixed versions:** a job started under an older `loop_lock.sh` (plain `logs/.loop_lock` file, or a
   claim dir without the `logs/.loop_lock.mx` mutex) must finish before anything uses the current lock.
2. **Foreground** (a build, the suites, a short gate):
   `bash scripts/loop_lock.sh run <owner> --purpose "<what>" [--wait <minutes>] -- <cmd...>` -- takes the lock,
   renews its heartbeat while `<cmd>` runs, releases on exit, returns `<cmd>`'s exit code; **exit 75** = busy and
   `<cmd>` did not run. `--wait` is wall-clock MINUTES and queues (a ticket, served in arrival order); a take
   without `--wait` is refused while anyone is queued. **A chain is ONE holding** -- wrap it whole:
   `bash scripts/loop_lock.sh run main --purpose "test+gate" -- bash -c './build.sh test && python -m tools_py.parity.gate'`
   (the gate's own take/release are NESTED no-ops inside a run).
3. **Detached** (game runs, the gate, anything long):
   `bash scripts/run_detached.sh --owner <o> --wait <min> <script> <marker>` -- queues in the foreground first
   (background the call if the wait may be long), launches `<script>` under nohup, renews while its PID lives,
   releases, then writes `exit=<code>` to `<marker>` (`exit=75 BUSY|TIMEOUT`, `exit=3 REFUSED` under 4 GB free
   disk or 3 GB free memory). The script keeps its work in the foreground. Poll the marker; never return control
   to wait on it. Never edit a chain script while it runs (bash reads it by offset).
4. **Before every launch while you hold the lock** (first line of the chain script):
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1` -- a finished `drive.py`
   taskkills the next run's game; it kills only driver modules and `socom2*.exe`.
5. **The gate:** `python -m tools_py.parity.gate --stamp <name>` (`--only <stage>`; `SOCOM_EXE` for another exe;
   `--baseline <stamp>` re-scores with no launch). Title about 3 min, transition about 3, mission about 11; refuses
   under 4 GB free on C:. Results: `logs/parity/gate/<stamp>/summary.txt`. **The bar: three `PASS` lines (3/3) and
   `PINS MATCH scripts/parity/pins.json (<n> compared)`.** A pin drift is exit 7, not a FAIL: find what moved;
   `--accept-pins` rewrites the shared standard and is a ruling, never a reflex.
6. **The record** -- one Log line in the open plan, stamped from `date -u` (never estimated): the gate name, the
   verdict, the exe hash (from the summary's `EXE ... sha256=` line), the stamps, the commit it ran on, e.g.
   "gate `s14_x_gate` 3/3, PINS MATCH (13 compared), exe `d6deb35f…`, 22:16Z at `<hash>`"; the same stamp goes
   in the commit body or STATUS entry (`docs/GIT_STRATEGY.md` §3). A red gate is fixed before
   anything else.
