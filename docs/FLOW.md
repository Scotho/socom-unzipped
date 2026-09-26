# Flow: how work moves through this repository

> **Generated -- do not edit.** Written by `python -m tools_py.flow --since 2026-09-01` (Sprint 14 M1, the review's F8) from the git history at the commit named below, the lock's queue log and `docs/BACKLOG.md`. The methods are note 03's (`docs/audits/2026-09-26-autonomy-structure-review/03-git-forensics.md`); each number names the command that reproduces it, and where the method differs from the note's the module docstring says how. Descriptive, not targets. `python -m tools_py.flow --check` exits 1 when this file is not a render of the commit it names; regenerate at the close.

Rendered at commit `48eafc671f7bb8776c35206128486ae3693d7775` (committer time 2026-09-26T09:48:35Z), since 2026-09-01 (UTC days): 1775 commits, 143 merges.

## The numbers

- **merges per day**: 143 merges on 9 days (mean 15.9 a merge day); `git log --merges` counts 143. Per day below -- command: `python -m tools_py.changelog --rev 48eafc67` (its merges, changelog.entries()), by UTC committer day; cross-check: `TZ=UTC git log --merges --since=2026-09-01T00:00:00Z --date=format-local:%F --format=%cd 48eafc67 | sort | uniq -c`
- **fix rounds per merge**: rounds: merges -- 0: 100 (69.9 %); 1: 32 (22.4 %); 2: 7 (4.9 %); 3: 3 (2.1 %); 7: 1 (0.7 %); none: 69.9 %, at most one: 92.3 %. A round counts once, at the first merge whose range brings it in; merge commits and docs(sprint-N) plan commits are not rounds -- command: `git log --no-merges --format=%s P1..P2 | grep -v -E '^docs\(sprint-[0-9]+\)' | grep -c -E 'review round|fix round'` per merge with parents P1 P2, oldest first, less the commits an earlier merge counted (note 03 section 2.2, deduplicated)
- **fix rounds per merge, broad pattern**: matches: merges -- 0: 61 (42.7 %); 1: 41 (28.7 %); 2: 23 (16.1 %); 3: 4 (2.8 %); 4: 5 (3.5 %); 5: 2 (1.4 %); 7: 2 (1.4 %); 8: 1 (0.7 %); 10: 1 (0.7 %); 19: 1 (0.7 %); 28: 1 (0.7 %); 32: 1 (0.7 %); none: 42.7 %, at most one: 71.3 % (an upper bound: every fix(scope) commit counts). The same rule -- command: `git log --no-merges --format=%s P1..P2 | grep -v -E '^docs\(sprint-[0-9]+\)' | grep -c -E 'review round|fix round|fix\(|review'` per merge, oldest first, less the commits an earlier merge counted
- **subjects saying " again"**: 45 of 1775 commits -- command: `git log --since=2026-09-01T00:00:00Z --format=%s 48eafc67 | grep -ci -- ' again'`
- **docs share of churn, seven days**: 31.0 %: 128494 of 414766 lines added + deleted, 2026-09-19T09:48:35Z to 2026-09-26T09:48:35Z -- command: `git log --numstat --no-renames --since=2026-09-19T09:48:35Z --until=2026-09-26T09:48:35Z --format= 48eafc67 | awk '$1 ~ /^[0-9]+$/ {t += $1 + $2} $3 ~ /^docs\// {d += $1 + $2} END {print d, t}'`
- **ticket wait**: not measured: the queue log was not found. Task W2 makes the lock write a `TICKET <id> waited <s>` line into logs/loop_lock.queue.log at each grant; until then there is nothing to read -- command: `grep -E 'TICKET [^ ]+ waited [0-9]+' logs/loop_lock.queue.log` (the main tree's), the median of the last field, unstamped lines and lines stamped after 2026-09-26T09:48:35Z or before 2026-09-01 left out
- **open-issue age**: not measured: the open-issues table of docs/BACKLOG.md at `48eafc67` has no Opened column; the dates live on GitHub (`gh issue list --state open --json number,createdAt`), a network read this page does not make -- command: `git show 48eafc67:docs/BACKLOG.md`, the Opened column of section 1's table, days to 2026-09-26
- **sessions**: 18 distinct Claude-Session trailers -- command: `git log --since=2026-09-01T00:00:00Z --format=%B 48eafc67 | grep '^Claude-Session:' | sort -u | wc -l`
- **commits per session**: largest first: 327, 220, 115, 85, 61, 32, 30, 21, 16, 12, 10, 9, 8, 7, 3, 3, 2, 1; median 14 -- command: `git log --since=2026-09-01T00:00:00Z --format=%B 48eafc67 | grep '^Claude-Session:' | sort | uniq -c | sort -rn`

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
| 2026-09-26 | 35 |
