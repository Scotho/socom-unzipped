# Flow: how work moves through this repository

> **Generated -- do not edit.** Written by `python -m tools_py.flow --since 2026-09-01` (Sprint 14 M1, the review's F8) from the git history at the commit named below, the lock's queue log and `docs/BACKLOG.md`. The methods are note 03's (`docs/audits/2026-09-26-autonomy-structure-review/03-git-forensics.md`); each number names the command that reproduces it, and where the method differs from the note's the module docstring says how. Descriptive, not targets. `python -m tools_py.flow --check` exits 1 when this file is not a render of the commit it names; regenerate at the close.

Rendered at commit `bbc1177ee63cfd7ae988ca198488d4d8cdf21b7d` (committer time 2026-09-26T09:38:11Z), since 2026-09-01 (UTC days): 1774 commits, 143 merges.

## The numbers

- **merges per day**: 143 merges on 9 days (mean 15.9 a merge day); `git log --merges` counts 143. Per day below -- command: `python -m tools_py.changelog --rev bbc1177e` (its merges, changelog.entries()), by UTC committer day; cross-check: `TZ=UTC git log --merges --since=2026-09-01T00:00:00Z --date=format-local:%F --format=%cd bbc1177e | sort | uniq -c`
- **fix rounds per merge**: rounds: merges -- 0: 91 (63.6 %); 1: 35 (24.5 %); 2: 9 (6.3 %); 3: 5 (3.5 %); 4: 1 (0.7 %); 18: 1 (0.7 %); 50: 1 (0.7 %); none: 63.6 %, at most one: 88.1 % -- command: `git log --format=%s P1..P2 | grep -c -E 'review round|fix round'` per merge with parents P1 P2 (note 03 section 2.2)
- **fix rounds per merge, broad pattern**: matches: merges -- 0: 50 (35.0 %); 1: 39 (27.3 %); 2: 28 (19.6 %); 3: 6 (4.2 %); 4: 5 (3.5 %); 5: 3 (2.1 %); 7: 1 (0.7 %); 8: 4 (2.8 %); 10: 2 (1.4 %); 11: 1 (0.7 %); 19: 1 (0.7 %); 28: 1 (0.7 %); 70: 1 (0.7 %); 105: 1 (0.7 %); none: 35.0 %, at most one: 62.2 % (an upper bound: every fix(scope) commit counts) -- command: `git log --format=%s P1..P2 | grep -c -E 'review round|fix round|fix\(|review'` per merge
- **subjects saying " again"**: 45 of 1774 commits -- command: `git log --since=2026-09-01T00:00:00Z --format=%s bbc1177e | grep -ci -- ' again'`
- **docs share of churn, seven days**: 31.0 %: 128462 of 414924 lines added + deleted, 2026-09-19T09:38:11Z to 2026-09-26T09:38:11Z -- command: `git log --numstat --no-renames --since=2026-09-19T09:38:11Z --until=2026-09-26T09:38:11Z --format= bbc1177e | awk '$1 ~ /^[0-9]+$/ {t += $1 + $2} $3 ~ /^docs\// {d += $1 + $2} END {print d, t}'`
- **ticket wait**: not measured: the queue log was not found. Task W2 makes the lock write a `TICKET <id> waited <s>` line into logs/loop_lock.queue.log at each grant; until then there is nothing to read -- command: `grep -E 'TICKET [^ ]+ waited [0-9]+' logs/loop_lock.queue.log` (the main tree's), the median of the last field, lines stamped after 2026-09-26T09:38:11Z or before 2026-09-01 left out
- **open-issue age**: not measured: the open-issues table of docs/BACKLOG.md at `bbc1177e` has no Opened column; the dates live on GitHub (`gh issue list --state open --json number,createdAt`), a network read this page does not make -- command: `git show bbc1177e:docs/BACKLOG.md`, the Opened column of section 1's table, days to 2026-09-26
- **sessions**: 18 distinct Claude-Session trailers -- command: `git log --since=2026-09-01T00:00:00Z --format=%B bbc1177e | grep '^Claude-Session:' | sort -u | wc -l`
- **commits per session**: largest first: 327, 220, 114, 85, 61, 32, 30, 21, 16, 12, 10, 9, 8, 7, 3, 3, 2, 1; median 14 -- command: `git log --since=2026-09-01T00:00:00Z --format=%B bbc1177e | grep '^Claude-Session:' | sort | uniq -c | sort -rn`

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
