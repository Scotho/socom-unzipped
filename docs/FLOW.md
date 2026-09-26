# Flow: how work moves through this repository

> **Generated -- do not edit.** Written by `python -m tools_py.flow --since 2026-09-01` (Sprint 14 M1, the review's F8; tokens M2) from the git history at the commit named below, the lock's queue log, `docs/BACKLOG.md` and, when SOCOM_CLAUDE_TRANSCRIPTS names a directory, the sums of its transcripts' usage fields. The methods are note 03's (`docs/audits/2026-09-26-autonomy-structure-review/03-git-forensics.md`); each number names the command that reproduces it, and where the method differs from the note's the module docstring says how. Descriptive, not targets. `python -m tools_py.flow --check` exits 1 when this file is not a render of the commit it names; regenerate at the close.

Rendered at commit `d751bc7fcf916321adeb3b9fb05b77f7f6ea0842` (committer time 2026-09-26T10:09:44Z), since 2026-09-01 (UTC days): 1802 commits, 149 merges.

## The numbers

- **merges per day**: 149 merges on 9 days (mean 16.6 a merge day); `git log --merges` counts 149. Per day below -- command: `python -m tools_py.changelog --rev d751bc7f` (its merges, changelog.entries()), by UTC committer day; cross-check: `TZ=UTC git log --merges --since=2026-09-01T00:00:00Z --date=format-local:%F --format=%cd d751bc7f | sort | uniq -c`
- **fix rounds per merge**: rounds: merges -- 0: 105 (70.5 %); 1: 32 (21.5 %); 2: 8 (5.4 %); 3: 3 (2.0 %); 7: 1 (0.7 %); none: 70.5 %, at most one: 91.9 %. A round counts once, at the first merge whose range brings it in; merge commits and docs(sprint-N) plan commits are not rounds; rounds committed straight on a sprint branch count at the sprint's merge into main (Sprint 11's seven at PR #49) -- command: `git log --no-merges --format=%s P1..P2 | grep -v -E '^docs\(sprint-[0-9]+\)' | grep -c -E 'review round|fix round'` per merge with parents P1 P2, oldest first, less the commits an earlier merge counted (note 03 section 2.2, deduplicated)
- **fix rounds per merge, broad pattern**: matches: merges -- 0: 62 (41.6 %); 1: 44 (29.5 %); 2: 25 (16.8 %); 3: 4 (2.7 %); 4: 5 (3.4 %); 5: 2 (1.3 %); 7: 2 (1.3 %); 8: 1 (0.7 %); 10: 1 (0.7 %); 19: 1 (0.7 %); 28: 1 (0.7 %); 32: 1 (0.7 %); none: 41.6 %, at most one: 71.1 % (an upper bound: every fix(scope) commit counts). The same rule -- command: `git log --no-merges --format=%s P1..P2 | grep -v -E '^docs\(sprint-[0-9]+\)' | grep -c -E 'review round|fix round|fix\(|review'` per merge, oldest first, less the commits an earlier merge counted
- **subjects saying " again"**: 45 of 1802 commits -- command: `git log --since=2026-09-01T00:00:00Z --format=%s d751bc7f | grep -ci -- ' again'`
- **docs share of churn, seven days**: 30.9 %: 128972 of 417378 lines added + deleted, 2026-09-19T10:09:44Z to 2026-09-26T10:09:44Z -- command: `git log --numstat --no-renames --since=2026-09-19T10:09:44Z --until=2026-09-26T10:09:44Z --format= d751bc7f | awk '$1 ~ /^[0-9]+$/ {t += $1 + $2} $3 ~ /^docs\// {d += $1 + $2} END {print d, t}'`
- **ticket wait**: not measured: the queue log was not found. Task W2 makes the lock write a `TICKET <id> waited <s>` line into logs/loop_lock.queue.log at each grant; until then there is nothing to read -- command: `grep -E 'TICKET [^ ]+ waited [0-9]+' logs/loop_lock.queue.log` (the main tree's), the median of the last field, unstamped lines and lines stamped after 2026-09-26T10:09:44Z or before 2026-09-01 left out
- **open-issue age**: not measured: the open-issues table of docs/BACKLOG.md at `d751bc7f` has no Opened column; the dates live on GitHub (`gh issue list --state open --json number,createdAt`), a network read this page does not make -- command: `git show d751bc7f:docs/BACKLOG.md`, the Opened column of section 1's table, days to 2026-09-26
- **sessions**: 18 distinct Claude-Session trailers -- command: `git log --since=2026-09-01T00:00:00Z --format=%B d751bc7f | grep '^Claude-Session:' | sort -u | wc -l`
- **commits per session**: largest first: 333, 220, 135, 85, 61, 32, 30, 21, 16, 12, 10, 9, 8, 7, 3, 3, 2, 1; median 14 -- command: `git log --since=2026-09-01T00:00:00Z --format=%B d751bc7f | grep '^Claude-Session:' | sort | uniq -c | sort -rn`
- **token spend**: not measured: SOCOM_CLAUDE_TRANSCRIPTS is not set. The transcripts are local to the machine that ran the sessions, so the page sums them only when the controller names their directory -- command: `SOCOM_CLAUDE_TRANSCRIPTS=<the transcripts directory> python -m tools_py.flow --usage` (Claude Code's are under ~/.claude/projects/<project-key>/), the `message.usage` fields of each `.jsonl` summed

## Merges per UTC day

| day | merges |
|---|---:|
| 2026-09-08 | 1 |
| 2026-09-18 | 2 |
| 2026-09-20 | 1 |
| 2026-09-21 | 25 |
| 2026-09-22 | 7 |
| 2026-09-23 | 18 |
| 2026-09-24 | 7 |
| 2026-09-25 | 47 |
| 2026-09-26 | 41 |
