# Claude Code harness features: what the project under-uses (research notes, 2026-09-25)

Source: claude-code-guide agent against code.claude.com docs (v2.1+). Saved verbatim in substance by the coordinator because the agent could not write files.

## 1. CLAUDE.md and instruction layering
- Docs: https://code.claude.com/docs/en/memory.md , https://code.claude.com/docs/en/claude-directory.md
- Target **under 200 lines**; longer files load in full but "may reduce adherence to instructions". No hard cutoff.
- Global `~/.claude/CLAUDE.md` + project `CLAUDE.md` (or `.claude/CLAUDE.md`) load together; project wins on conflict.
- `.claude/rules/` supports **path-scoped rules** (e.g. `rules/git.md`) as the way to modularize.
- Applies here: the project has NO root CLAUDE.md; the 5,000 lines of governing docs are "please read" documents, not loaded instructions. The bare `git config` incident (2026-09-23) is the kind of rule that belongs in a small always-loaded file or, better, a hook.

## 2. Hooks
- Docs: https://code.claude.com/docs/en/hooks-guide.md , https://code.claude.com/docs/en/hooks
- Events: SessionStart, SessionEnd, PreToolUse, PostToolUse, Stop, SubagentStop, PreCompact, Compact, Notification, UserPromptSubmit, PermissionRequest, WorktreeCreate, WorktreeRemove, plus experimental TeammateIdle/TaskCreated/TaskCompleted.
- Shell command receives JSON on stdin (includes `cwd` and the tool input); exit 0 allows, exit 2 blocks with feedback.
- Docs show no example for git-scope enforcement; the pattern must be authored and tested locally.
- Sketch (PreToolUse on Bash): parse `.cwd` and `.tool_input.command`; if cwd is a worktree and command matches `git config` without `--local`/`--worktree`, exit 2. Same shape blocks `git push` from a worktree path, a `git commit` without `--`, or `loop_lock.sh take` outside the script.
- Applies here: three of the recorded incidents (bare git config, pushes from worktrees, bare commits) are Bash commands a PreToolUse hook can refuse deterministically.

## 3. Subagents, agent teams, worktrees
- Docs: https://code.claude.com/docs/en/sub-agents.md , https://code.claude.com/docs/en/agent-teams.md , https://code.claude.com/docs/en/worktrees.md
- **TaskStop does not kill child processes** started by the subagent's Bash. Documented limitation.
- Parked vs finished: a "completed" notification with background children still running is indistinguishable in the UI; no documented programmatic detector. A SubagentStop / Stop hook is the available lever.
- Agent teams are experimental (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`), off by default; in-process teammates cannot spawn background subagents.
- Worktree isolation (`isolation: worktree`) auto-cleans unchanged worktrees; Claude Code blocks `git -C ../main` / `GIT_WORK_TREE` redirection. Since v2.1.205 a junction inside a worktree is removed as a link, not followed; before that, removal could delete the target (the 2026-09-21 toolchain loss).
- Custom agents: `.claude/agents/<name>.md` frontmatter can set `model`, `tools` (allow/deny), permissions. A worker agent can be denied `git push` at the definition level.

## 4. Auto-memory
- Docs: https://code.claude.com/docs/en/memory.md
- Loads the first **200 lines or 25 KB** of MEMORY.md; the rest is silently truncated. Memory is Claude-written; CLAUDE.md is human-written and committed.
- Applies here: MEMORY.md is ~35 lines and under the limit today, but each line is a long hook; growth will hit the ceiling silently. Anything a human should also read belongs in the repo, not memory.

## 5. Context management, unattended runs, workflows
- Docs: https://code.claude.com/docs/en/context-window.md , https://code.claude.com/docs/en/workflows.md , https://code.claude.com/docs/en/headless.md
- `/compact`, PreCompact hook; long sessions degrade; fresh session per task is the recommended shape.
- Monitor: no documented cleanup/orphan collection; the 213 leaked tail/grep watchers (2026-09-25) are consistent with that. A SessionEnd/Stop hook that kills the session's own watcher tree is the lever.
- Workflows: deterministic JavaScript orchestration of subagents, resumable (completed agents return cached results), state held outside Claude's context. Candidate replacement for parts of the shell proof chain and for the "review then fix round" merge protocol.
- Headless `-p`, `--bare` (skips hooks/skills/memory/CLAUDE.md), permission modes, allowlists; `/loop` and `/schedule` for unattended cadence.

## 6. Skills vs documents
- Docs: https://code.claude.com/docs/en/skills.md
- Project skills in `.claude/skills/<name>/SKILL.md` load only when invoked (by name or description match); CLAUDE.md always loads. Use skills for multi-step procedures and large reference material; CLAUDE.md for conventions and static facts under ~200 lines.
- Applies here: LOOP_PROMPT.md (one iteration), the sprint-close review procedure (DOC_MAINTENANCE §5/§7), the worktree create/remove procedure, and the gate-running recipe are procedures that fit skills better than prose an agent is told to read.

## 7. Settings and worktrees
- Docs: https://code.claude.com/docs/en/settings.md , https://code.claude.com/docs/en/settings-reference.md
- Precedence: managed > CLI > `.claude/settings.local.json` > `.claude/settings.json` > `~/.claude/settings.json`.
- Hooks in the shared project `.claude/settings.json` apply in every worktree (each worktree checks out `.claude/`); worktree-specific behaviour is done by inspecting `cwd` inside the hook. Permission approvals from a worktree are saved to the main checkout's local settings.

## Summary table
| Incident | Lever | Note |
|---|---|---|
| bare `git config` rewrote shared .git/config | PreToolUse hook on Bash | deterministic refusal; pattern must be authored |
| TaskStop left chain children running | Stop/SubagentStop/SessionEnd hook killing the session's process tree | documented TaskStop limitation |
| 213 orphaned watchers | SessionEnd hook | no documented Monitor cleanup |
| "completed" notice while work ran | no documented detector | worktree lock check remains the workaround |
| pushes from worktrees despite the brief | agent definition `tools` deny + PreToolUse hook | two layers |
| bare commits took another task's lines | PreToolUse hook requiring `--` pathspec | |
| 5,000 lines of "read first" prose | small CLAUDE.md + `.claude/rules/` + skills for procedures | docs: under 200 lines |
