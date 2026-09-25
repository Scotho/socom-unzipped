# Project audit, 2026-09-25 — the shared brief for every audit agent

You are one of several READ-ONLY auditors of the SOCOM Unzipped project (SOCOM II PS2 statically recompiled to PC;
public repository github.com/Scotho/socom-unzipped). Work in the git worktree `C:\projects\wt-s12` (branch sprint-12,
the newest state: Sprints 11 and 12 closed 2026-09-25). Use Bash for reading (cat/sed/grep/find, `git log`, `gh`
read commands). Web tools (WebFetch, WebSearch) are allowed where your area says so.

Hard rules:
- Do NOT edit any tracked file. Do NOT commit, push, build, run tests, run the game, or touch
  `scripts/loop_lock.sh` (a machine-wide lock another job holds). Do NOT read anything under `game/` beyond listing
  file names (the game's bytes never enter a report).
- Write exactly one output file: `C:\projects\wt-s12\.superpowers\sdd\2026-09-25-project-audit\<your-area>.md`.
- Every finding cites its evidence as `file:line` (or a URL for external findings) and quotes the line or the
  number it rests on. A number you did not read from a file or a command is not a finding.
- Read `docs/HANDOFF.md` §1–§2 first (what the project is, where it stands), then `docs/CURRENT_SPRINT.md`'s two
  CLOSED blocks (Sprint 12 and Sprint 11: what was just done and what was carried), then `docs/KNOWN.md`'s section
  headings, then your area.

Report shape (one markdown file, tables):
1. **Findings table** — columns: `#` | `item` (one sentence) | `class` (one of: REVISION = a document or code claim
   that is wrong or stale; UNFINISHED = work a plan/row/issue started and did not finish; TASK = an agentic-possible
   task nobody has written down; NEGLECTED = an improvement that has been repeatedly deferred or never scheduled;
   RISK = a hazard with no owner) | `who` (LOCKFREE-AGENT = an agent can do it without the lock or the game;
   LOCK-AGENT = needs the build/game/lock on the owner's machine; CLOUD = a cloud session without a game could do it;
   OWNER = only the owner) | `cost` (S < 1 h, M < 1 day, L > 1 day) | `evidence` (`file:line`, quoted) | `why it
   matters` (one clause).
2. **Structure notes** — what is well organised and what is not in your area (duplication, dead files, files that
   have outgrown their purpose, naming that misleads a stranger), each with evidence.
3. **Top five** — your five highest-value items with one sentence each on why.
Aim for completeness over polish; 30–80 findings is normal for a wide area. Do not repeat what another area owns
(the areas are listed in each agent's prompt). Stop after writing the file and return a summary of at most 30 lines.
