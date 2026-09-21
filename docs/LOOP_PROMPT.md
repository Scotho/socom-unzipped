# The loop — one iteration, for whoever is the controller (SOCOM Unzipped)

Rewritten 2026-09-20. The previous text was last touched on 2026-09-14 and still aimed the loop at Sprint 6, a runtime
freeze that was lifted long ago and a ban on speed work that Sprint 8 broke on purpose; `docs/process-audit.md` §8 had
predicted exactly that. This file therefore carries **no state at all**: no sprint, no goal, no number. State lives in
`docs/CURRENT_SPRINT.md` (what to do), `docs/KNOWN.md` (what is true) and `docs/HANDOFF.md` (where things are, the
rules with their reasons, the traps). If you find yourself writing a fact about the project into this file, it belongs
in one of those.

**How it actually runs.** Nothing in the repository schedules this -- there is no cron, no hook, no ledger. The loop is
a controller session working this page one iteration after another, for as long as the owner leaves it running. The
owner (Craig) is usually away and has given the controller full authority to use its judgement; plans are
suggestions, stop rules and the owner-only list are not.

## Every iteration

1. **Look before you touch.** `git status --short`, `git log --oneline -5`, `bash scripts/loop_lock.sh check`. Other
   sessions share this working tree: a modified file you did not modify is someone else's -- do not edit or stage it.
   If the lock is held, or a `socom2*` / `pcsx2-qt` process is running, start no build and no run; **do not idle** --
   take lock-free work (step 3).
2. **Read the aim.** The first open item in `docs/CURRENT_SPRINT.md`, in its order. `docs/KNOWN.md` before forming any
   hypothesis -- it is the fastest way to avoid re-deriving a dead one. The item's spec section and plan, if it has one.
   A new item that needs more than an hour gets a plan first (`docs/superpowers/plans/`, the existing ones are the
   pattern: handoff notes, global constraints, tasks with RED/GREEN steps and exact commands, rulings).
3. **Work in bounded steps:** one hypothesis -> a failing test -> the change -> one build -> one run -> read the
   evidence. Builds and runs go through the lock (`docs/HANDOFF.md` §5 rule 6), `scripts/check_quiet_gate.sh` first.
   While one is running, do lock-free work rather than waiting: pure scorers and their tests, reading the decompilation,
   analysis of logs already on disk, documents, the filler list in the sprint file. Never return control to wait on a
   detached run -- poll its marker.
4. **Green before the commit:** `./build.sh test`, and the three-stage gate on the rebuilt exe
   (`./build.sh runtime` first) for anything touching the runtime, `recomp/`, `tools_py/parity/`, `scripts/parity/` or
   `build.sh`. A red gate is fixed before anything else. Never regress: title labels clean, online reaches the lobby,
   a mission loads, the online local player moves.
5. **Commit and push** by `docs/HANDOFF.md` §5 rules 1-4 (explicit pathspec; the never-commit list; your session's own
   trailer; `git push origin <sprint branch>`; check CI -- `secrets` runs on every push, `linux` and `windows` when
   anything outside `docs/` moved). **The repository is public:** the hooks (`bash scripts/install_hooks.sh`, once
   per clone) run the leak check before the commit and again before the push, and CI runs it over the full history;
   a hit is fixed, or a reviewed non-secret is recorded with its reason in `tools_py/release/leak_allow.txt`. Never
   `--no-verify`.
6. **Write it down where it will be read:** a dated entry on top of `docs/STATUS.md` and its "Current state" block if
   the state changed; **audit `docs/KNOWN.md`** -- promote, retire or retract every row this step touched; tick the
   plan's boxes; update the item's row in `docs/CURRENT_SPRINT.md`; a numbered ruling for every moved default or
   skipped measurement; `docs/HUMAN_TASKS.md` for anything only the owner can verify; `docs/HANDOFF.md` §2, §4, §8, §10
   when the pick-up point changes. **A committed sentence found false is corrected the same hour, where it is
   written**, with a `> Superseded by ...` blockquote -- never queued for a close-out that may not come.
7. **Then the next item.** Do not wait on the owner; do not perform what is the owner's (publish, make public,
   permissions, signing, money, the site's deploy, any server that is not ours).

## Delegation

Sub-agents are welcome for bounded work with an exact brief and a verification command: offline and static work
freely; builds of the runtime and game runs are SERIAL and go through the lock whoever starts them; at most two
C++-building agents at once. For any number a decision rests on, have a fresh agent re-derive it rather than re-read
it. A sub-agent never commits a file it was not given, and never stages with `git add -A`.

## When the sprint closes

`docs/CURRENT_SPRINT.md`'s close-out item; `docs/GIT_STRATEGY.md` for the merge and the tag; then open the next sprint:
its spec is already drafted, its plan is written against the tree as it then is, and the sprint file's header block is
rewritten -- it is the only sprint pointer in the project.

## The acceptance bar that has never changed (owner, 2026-09-09)

"Playable" means visual accuracy of the game itself, not just the shell, AND an automated test that drives a
two-instance online match to its end by one player killing the other. Both were met in Sprint 5 and must stay met.
Long term: the N64-recomp model -- game logic stays recompiled; renderer, audio, input and network are native.

## Lock protocol
The lock serializes every build and every game run (`scripts/loop_lock.sh`; its header is the
reference). **Never hold it across tool calls except through `run` or `run_detached.sh`** — a gap
between two tool calls is not renewed, and the calling shell dies when its tool call returns.
**Mixed versions:** a job started under an older `loop_lock.sh` (plain `logs/.loop_lock` file, or a
claim dir without the `logs/.loop_lock.mx` mutex) must finish before anything uses the current lock.
- Foreground: `bash scripts/loop_lock.sh run <owner> --purpose "<what>" [--wait 40] -- <cmd...>`
  takes the lock, renews its heartbeat every 60 s while `<cmd>` runs, releases on exit (also on
  failure) and returns `<cmd>`'s exit code; exit 75 = the lock was busy and `<cmd>` did not run.
  Wrap a build -> test -> gate sequence as ONE run, e.g.
  `bash scripts/loop_lock.sh run main --purpose "test+gate" -- bash -c './build.sh test && python -m tools_py.parity.gate'`
  (gate.py's own take/release are NESTED no-ops inside a run).
- Detached (game runs): `bash scripts/run_detached.sh --owner <owner> <script> <marker>` takes the
  lock, launches the script under nohup, renews every 5 min while the script's PID lives, releases
  and then writes `exit=<code>` to `<marker>`. The script must keep its work in the foreground (the
  lock lives as long as the script's PID). Poll the marker; run
  `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1` before every
  launch while you hold the lock (a finished drive.py taskkills the next run's game; it kills only
  driver modules and `socom2*.exe`, never lock-free scorers or its own callers).
- A lock is live while its **heartbeat** is fresh, not by how long ago it was taken. A take on a
  held lock reaps it only when the heartbeat is >= 15 min old **and** nothing on the busy list runs
  (games, PCSX2, cmake/ninja/clang/ld, ps2_recomp, ps2x_tests, vu1_replay, python running
  `tools_py.parity` or `unittest`); the 45-min stale break is refused while anything on that list
  runs. BUSY holds for the same owner too. `check` prints the holder, purpose and heartbeat age;
  reaps are logged to `logs/.loop_lock_history`. `take`/`renew`/`release`/`wait` still exist for old
  scripts; do not use them across tool calls.
- Offline analysis (python on logs already on disk) needs no lock. `vu1_replay.exe` and
  `python -m unittest` need none either, but they are on the busy list, so a long one delays a reap.
