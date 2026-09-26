# SOCOM Unzipped -- read this first

SOCOM II (PS2, US) statically recompiled to a native PC executable, with online play through a
Horizon server. The owner is Craig, who sets priorities and makes the rulings; agents do the work. The loop is an
autonomous controller session that runs the sprints and dispatches implementer agents into worktrees.
This file is a map, not the state: it holds nothing that changes weekly, and every line points at the file that
owns the fact.

## Where the state lives

- `docs/CURRENT_SPRINT.md` -- what to do: the open sprint, its plan and the road to the next tag.
- `docs/KNOWN.md` -- what is true (proven, believed, retracted, hazards), each with its artefact, and its vocabulary.
- `docs/HANDOFF.md` -- where things are, the standing rules with their reasons, the traps, the ruling counter.
- `docs/HUMAN_TASKS.md` -- the owner's rows: what only Craig can do.
- `docs/DEVELOPING.md` -- the developer reference: build, run, tests, tools, the guards; it owns the suite counts.
- The open sprint's plan under `docs/superpowers/plans/` (CURRENT_SPRINT names it) -- its `## Log` is the live state.

## Guards -- these refuse, they do not advise (the full rules and planted tests: DEVELOPING "## Guards")

- Bulk staging (`git add -A`, `.`, `-u` without `-- <paths>`) and `git commit -a` -- enforced by: the PreToolUse hook
  `scripts/hooks/claude_pretool.sh` -> `tools_py/hooks/pretool.py`, test `tools_py/tests/test_hooks.py`;
  home `docs/GIT_STRATEGY.md` section 3.
- A commit without `-- <paths>` (allowed only mid-merge) -- enforced by: the same hook and test;
  home `docs/HANDOFF.md` section 5 rule 1.
- `--no-verify` (any prefix), commit `-n`, `-c core.hooksPath=` -- enforced by: the same hook and test;
  home `docs/GIT_STRATEGY.md` section 3.
- A push from a linked worktree; a force push, `+refspec` or delete aimed at `main` or `sprint-*`; `--mirror` --
  enforced by: the same hook and test; home `docs/GIT_STRATEGY.md` sections 2 and 3.
- `loop_lock.sh take`/`release` by hand; worktree add/remove/prune or a writing `git config` in a worktree outside
  `scripts/agent_worktree.sh` -- enforced by: the same hook and test; home those two scripts.
- Edit/Write of an existing `logs/**/*.sh` while the lock is HELD, or of `scripts/loop_lock.sh` while a run uses that
  copy; committing `loop_lock.sh` without a fresh slow-suite marker -- enforced by: the same hook (Edit/Write entry)
  and test; home the `scripts/loop_lock.sh` header. Edits made through Bash are not seen.
- Orphaned watchers (`tail`, `grep`, `sleep`) are killed at every Stop and SessionEnd -- enforced by: the reaper
  `scripts/hooks/claude_session_end.sh` -> `tools_py/hooks/reap.py`, test `tools_py/tests/test_reap.py`.
- `build.sh` refuses (exit 3) while someone else holds the lock, unless it runs as the holder's child -- enforced by:
  `build.sh`, test `tools_py/tests/test_build_sh_lock.py`. All hooks are wired in `.claude/settings.json`.

## Procedures -- by skill name (Task I2 makes each a project skill under `.claude/skills/`; the home today)

- `loop-iteration` -- every loop firing, steps in order: `docs/LOOP_PROMPT.md`.
- `agent-worktree` -- create, brief, review, merge, remove an agent's tree: `scripts/agent_worktree.sh`,
  `docs/HANDOFF.md` section 5.
- `run-gate` -- a build or game run and its record: `scripts/check_quiet_gate.sh`, `scripts/run_detached.sh`,
  `docs/HANDOFF.md` section 5 rules 5-6.
- `sprint-close` -- the close review and the known-issue stack review: `docs/DOC_MAINTENANCE.md` sections 5 and 7.

## The lock

One build or game at a time, host-wide, only through `scripts/loop_lock.sh run` (or `scripts/run_detached.sh`);
its header is the reference.

## Boundaries

KNOWN wins on any disagreement: when a document contradicts `docs/KNOWN.md`, the document is wrong.
Nothing that is the owner's is performed -- no publishing, no money, no permissions or tokens, no change to the site,
no connection to a server that is not ours; add a line to the owner's row in `docs/HUMAN_TASKS.md` instead.

Everything else -- building, running, testing, the tools and the conventions -- is in `docs/DEVELOPING.md`.
