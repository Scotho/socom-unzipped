# Flow: how work moves through this repository

> **Generated -- do not edit.** Written by `python -m tools_py.flow --since 2026-09-01` (Sprint 14 M1, the review's F8; tokens M2) from the git history at the commit named below, the lock's queue log, `docs/BACKLOG.md` and, when SOCOM_CLAUDE_TRANSCRIPTS names a directory, the sums of its transcripts' usage fields. The methods are note 03's (`docs/audits/2026-09-26-autonomy-structure-review/03-git-forensics.md`); each number names the command that reproduces it, and where the method differs from the note's the module docstring says how. Descriptive, not targets. `python -m tools_py.flow --check` exits 1 when this file is not a render of the commit it names; regenerate at the close.

Rendered at commit `17400817c7099a5477ae6e46568431a4067559b6` (committer time 2026-09-26T16:29:06Z), since 2026-09-01 (UTC days): 1866 commits, 161 merges.

## The numbers

- **merges per day**: 161 merges on 9 days (mean 17.9 a merge day); `git log --merges` counts 161. Per day below -- command: `python -m tools_py.changelog --rev 17400817` (its merges, changelog.entries()), by UTC committer day; cross-check: `TZ=UTC git log --merges --since=2026-09-01T00:00:00Z --date=format-local:%F --format=%cd 17400817 | sort | uniq -c`
- **fix rounds per merge**: rounds: merges -- 0: 114 (70.8 %); 1: 35 (21.7 %); 2: 8 (5.0 %); 3: 3 (1.9 %); 7: 1 (0.6 %); none: 70.8 %, at most one: 92.5 %. A round counts once, at the first merge whose range brings it in; merge commits and docs(sprint-N) plan commits are not rounds; rounds committed straight on a sprint branch count at the sprint's merge into main (Sprint 11's seven at PR #49) -- command: `git log --no-merges --format=%s P1..P2 | grep -v -E '^docs\(sprint-[0-9]+\)' | grep -c -E 'review round|fix round'` per merge with parents P1 P2, oldest first, less the commits an earlier merge counted (note 03 section 2.2, deduplicated)
- **fix rounds per merge, broad pattern**: matches: merges -- 0: 67 (41.6 %); 1: 50 (31.1 %); 2: 26 (16.1 %); 3: 4 (2.5 %); 4: 5 (3.1 %); 5: 2 (1.2 %); 7: 2 (1.2 %); 8: 1 (0.6 %); 10: 1 (0.6 %); 19: 1 (0.6 %); 28: 1 (0.6 %); 32: 1 (0.6 %); none: 41.6 %, at most one: 72.7 % (an upper bound: every fix(scope) commit counts). The same rule -- command: `git log --no-merges --format=%s P1..P2 | grep -v -E '^docs\(sprint-[0-9]+\)' | grep -c -E 'review round|fix round|fix\(|review'` per merge, oldest first, less the commits an earlier merge counted
- **subjects saying " again"**: 45 of 1866 commits -- command: `git log --since=2026-09-01T00:00:00Z --format=%s 17400817 | grep -ci -- ' again'`
- **docs share of churn, seven days**: 30.6 %: 126359 of 412755 lines added + deleted, 2026-09-19T16:29:06Z to 2026-09-26T16:29:06Z -- command: `git log --numstat --no-renames --since=2026-09-19T16:29:06Z --until=2026-09-26T16:29:06Z --format= 17400817 | awk '$1 ~ /^[0-9]+$/ {t += $1 + $2} $3 ~ /^docs\// {d += $1 + $2} END {print d, t}'`
- **ticket wait**: not measured: the queue log was not found. Task W2 makes the lock write a `TICKET <id> waited <s>` line into logs/loop_lock.queue.log at each grant; until then there is nothing to read -- command: `grep -E 'TICKET [^ ]+ waited [0-9]+' logs/loop_lock.queue.log` (the main tree's), the median of the last field, unstamped lines and lines stamped after 2026-09-26T16:29:06Z or before 2026-09-01 left out
- **open-issue age**: not measured: the open-issues table of docs/BACKLOG.md at `17400817` has no Opened column; the dates live on GitHub (`gh issue list --state open --json number,createdAt`), a network read this page does not make -- command: `git show 17400817:docs/BACKLOG.md`, the Opened column of section 1's table, days to 2026-09-26
- **sessions**: 18 distinct Claude-Session trailers -- command: `git log --since=2026-09-01T00:00:00Z --format=%B 17400817 | grep '^Claude-Session:' | sort -u | wc -l`
- **commits per session**: largest first: 333, 220, 199, 85, 61, 32, 30, 21, 16, 12, 10, 9, 8, 7, 3, 3, 2, 1; median 14 -- command: `git log --since=2026-09-01T00:00:00Z --format=%B 17400817 | grep '^Claude-Session:' | sort | uniq -c | sort -rn`
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
| 2026-09-26 | 53 |
