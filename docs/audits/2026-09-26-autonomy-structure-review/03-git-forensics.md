# 03 — Git forensics: socom_pc

Repository: `C:\projects\socom_pc`, branch `sprint-13`. Read-only session, 2026-09-25.

**Snapshot caveat.** Other agent sessions were committing while these commands ran. `HEAD` was
`3804d10b` (1614 commits) when the run started and `76701f4a` (1616 commits) when it finished.
Tables below are labelled `n=1614` or `n=1616` accordingly; the difference is two commits and
changes no conclusion. Author dates are used throughout unless stated; the repo's committer
timezone is **-0300**, so "local hour" below means the owner's wall clock and "UTC" is local+3.

Everything here is reproducible by re-running the command printed above each table from
`C:\projects\socom_pc`.

Scratch artefacts (intermediate dumps, re-usable):
`…\scratchpad\forensics\` — `all_subjects.txt`, `merge_subjects.txt`, `merges_flat.txt`,
`numstat_all.txt`, `classify.awk`, `merge_rounds.txt`, `ruling_first2.txt`, `issues.json`.

---

## 0. Shape of the repo (orientation)

```sh
git rev-list --count HEAD
git log -1 --format='%H %ad' --date=iso
git log --date=short --format='%ad' | sort | head -1
git ls-files | awk -F/ '{print $1}' | sort | uniq -c | sort -rn
git ls-files | awk -F. 'NF>1{print tolower($NF)}' | sort | uniq -c | sort -rn | head -10
```

| fact | value |
|---|---|
| commits | 1616 (1614 at start of run) |
| first commit (author date) | 2026-08-27 |
| last commit | 2026-09-25 23:24 -0300 (and later during the run) |
| calendar span | 30 days; 28 of them have commits |
| tracked files | 2213 |

Tracked files by top directory, and by extension:

| dir | files | | ext | files |
|---|---|---|---|---|
| `tools_py/` | 473 | | `.cs` | 421 |
| `server/` | 469 | | `.py` | 376 |
| `third_party/` | 413 | | `.png` | 276 |
| `docs/` | 229 | | `.cpp` | 200 |
| `tests/` | 158 | | `.md` | 194 |
| `scripts/` | 139 | | `.h` | 193 |

```sh
git ls-files '*.cpp' '*.h' '*.hpp' '*.c' '*.cc' | awk -F/ '{print $1"/"$2}' | sort | uniq -c | sort -rn
```

→ `387 third_party/ps2recomp`, `6 tests/fixtures`, `1 docs/research`.

**There is no `src/`.** The project's C++ — the PS2 runtime, recompiler, launcher, IOP and the
C++ test suite — lives entirely in `third_party/ps2recomp/`, which is a fork this project
edits (426 commits touch it). `server/horizon-server/` is 448 C# files (vendored Horizon).
`research/` is **gitignored** (`/research/` is line 1 of `.gitignore`) and holds ten cloned
external repos, so it contributes **zero** to every git-based number below; the project's own
research notes are the 73 tracked files in `docs/research/`. Generated recompiler output is
gitignored too (`/recomp/output/`, `/recomp/build/`, `/third_party/ps2recomp/build*/`), so no
table here is polluted by machine-generated code.

**What the numbers say.** The directory names lie about the architecture: the thing normally
called "the source tree" is a vendored path, the thing called "research" is invisible to git,
and the largest tracked language by file count (C#) is a server the project did not write. Any
docs-vs-code ratio therefore has to name its denominator explicitly, which sections 4 does.

---

## 1. Cadence

### 1.1 Commits and merges per day

```sh
git log --date=short --format='%ad' | sort | uniq -c | awk '{print $2, $1}'
git log --merges --date=short --format='%ad' | sort | uniq -c | awk '{print $2, $1}'
```

(n=1614 commits, 112 merges)

| date | commits | merges |
|---|---:|---:|
| 2026-08-27 | 1 | — |
| 2026-08-29 | 5 | — |
| 2026-08-30 | 2 | — |
| 2026-08-31 | 1 | — |
| 2026-09-01 | 2 | — |
| 2026-09-02 | 2 | — |
| 2026-09-04 | 36 | — |
| 2026-09-05 | 55 | — |
| 2026-09-06 | 7 | — |
| 2026-09-07 | 33 | 1 |
| 2026-09-08 | 19 | — |
| 2026-09-09 | 38 | — |
| 2026-09-10 | 32 | — |
| 2026-09-11 | 37 | — |
| 2026-09-12 | 61 | — |
| 2026-09-13 | 138 | — |
| 2026-09-14 | 20 | — |
| 2026-09-15 | 35 | — |
| 2026-09-16 | 23 | — |
| 2026-09-17 | 34 | — |
| 2026-09-18 | 58 | 2 |
| 2026-09-19 | 112 | — |
| 2026-09-20 | 127 | 1 |
| 2026-09-21 | 150 | 28 |
| 2026-09-22 | 42 | 4 |
| 2026-09-23 | 128 | 18 |
| 2026-09-24 | 114 | 7 |
| 2026-09-25 | **302** | **51** |

Derived: mean **57.6 commits/day** over the 28 active days. The last 7 days (09-19 → 09-25)
carry **975 commits = 60.4 %** of all history, at **139.3/day**. The last 24 h alone (09-25)
is **18.7 %** of the repo's entire history and **45.5 %** of all merges ever made.

### 1.2 Hour-of-day distribution

```sh
TZ=UTC git log --date=format-local:'%H' --format='%ad' | sort | uniq -c   # UTC
git log --format='%ad' --date=format:'%H' | sort | uniq -c                # local -0300
```

(n=1616)

| local hour | commits | | local hour | commits |
|---:|---:|---|---:|---:|
| 00 | 97 | | 12 | 85 |
| 01 | 84 | | 13 | 68 |
| 02 | 118 | | 14 | 71 |
| 03 | 60 | | 15 | 49 |
| 04 | 68 | | 16 | 67 |
| 05 | 73 | | 17 | 64 |
| 06 | 64 | | 18 | 69 |
| 07 | 48 | | 19 | 62 |
| 08 | 39 | | 20 | 71 |
| 09 | 54 | | 21 | 53 |
| 10 | 56 | | 22 | 67 |
| 11 | 81 | | 23 | 46 |

UTC equivalents are the same series shifted +3 (UTC peak 05:00 = 117, matching local 02:00 = 118).

```sh
git log --format='%ad' --date=format:'%H' | awk '{h=$1+0; if(h<6) b="00-05"; else if(h<9) b="06-08"; else if(h<18) b="09-17"; else b="18-23"; c[b]++; n++} END{for(k in c) printf "%-6s %5d %5.1f%%\n",k,c[k],100*c[k]/n}'
```

| local band | commits | share |
|---|---:|---:|
| 00–05 deep night | 500 | 30.9 % |
| 06–08 early | 151 | 9.3 % |
| 09–17 daytime | 595 | 36.8 % |
| 18–23 evening | 370 | 22.9 % |

```sh
git log --format='%ad' --date=format:'%a' | sort | uniq -c | sort -rn
```

| day | commits |
|---|---:|
| Fri | 435 |
| Sun | 274 |
| Sat | 233 |
| Mon | 204 |
| Wed | 191 |
| Thu | 181 |
| Tue | 98 |

### 1.3 Who commits

```sh
git log --format='%an <%ae>' | sort | uniq -c | sort -rn
git log --format='%B' | grep -i '^Co-Authored-By:' | sed 's/.*: //' | sort | uniq -c | sort -rn
git log --format='%B' | grep -c '^Claude-Session:'
git log --format='%B' | grep '^Claude-Session:' | sort -u | wc -l
```

| author | commits |
|---|---:|
| Craig Smith `<the owner's address>` | 1573 |
| Claude `<noreply@anthropic.com>` | 31 |
| GTTeancum | 10 |
| hedgeg0d | 2 |

| `Co-Authored-By` model | commits |
|---|---:|
| Claude Fable 5.1 | 1059 |
| Claude Opus 5 (1M context) | 436 |
| Claude Opus 4.8 | 6 |
| Claude Opus 5.5 (1M context) | 4 |
| **total with a Claude trailer** | **1505 (93.1 %)** |

`Claude-Session:` lines: 814 commits, but only **17 distinct session URLs** — ~48 commits per
session URL on average.

**What the numbers say.** Output is not spread evenly across the month; it is a rising ramp that
turns near-vertical in the final week, with 09-25 producing 302 commits and 51 merges in one
day. **40.3 % of all commits land between local midnight and 09:00**, and the single busiest
hour of the day is 02:00 — the repo's peak productivity is while the owner is asleep. 93 % of
commits carry a Claude co-author trailer, and the 17-session / 814-commit ratio says the work
arrives in long-running sessions rather than many short ones. Tuesday is the quietest weekday by
a factor of four against Friday.

---

## 2. Merge shape

### 2.1 Merge subject markers

```sh
git log --merges --format='%H|%ad|%s' --date=short > merge_subjects.txt
grep -o -E 'review PASS[A-Za-z ]{0,25}' merge_subjects.txt | sort | uniq -c | sort -rn
grep -vci 'review' merge_subjects.txt
git log --merges --format='%s' | awk '{print $1}' | sort | uniq -c
```

(112 merge commits)

| marker in merge subject | merges |
|---|---:|
| contains `review` at all | 25 |
| `review PASS WITH FINDINGS` | 12 |
| `review PASS` (bare) | 4 |
| `review PASS after one fix round` | 2 |
| `review PASS WITH FINDINGS then the …` | 2 |
| `review PASS with two doc fixes folded in` | 1 |
| `review PASS on the finding` | 1 |
| `review PASS on leak safety` | 1 |
| **no review word at all** | **87 (77.7 %)** |
| contains `RED` | 4 |
| contains `GREEN` | 6 |
| contains `fix round` | 2 |

Merge subject style split: `Merge …` (git default, edited) 82; `merge: …` (conventional) 30.

### 2.2 Fix rounds, measured from the merged branch rather than the subject

Merge subjects record review outcome only 22 % of the time, so the per-merge round count was
recomputed by counting commits **on the merged side** whose subject says `review round` or
`fix round`:

```sh
git log --merges --format='%H %P' > merge_parents.txt
while read -r m p1 p2 rest; do [ -z "$p2" ] && continue
  n=$(git log --format='%s' "$p1..$p2" | grep -c -E 'review round|fix round')
  c=$(git rev-list --count "$p1..$p2")
  echo "$m|$c|$n"
done < merge_parents.txt
```

| review/fix rounds on the merged branch | merges | share |
|---:|---:|---:|
| 0 | 73 | 65.2 % |
| 1 | 27 | 24.1 % |
| 2 | 6 | 5.4 % |
| 3 | 5 | 4.5 % |
| 18 (one outlier branch) | 1 | 0.9 % |
| **2 or more** | **12** | **10.7 %** |

Branch size at merge (commits reachable from `p2` but not `p1`):

| stat | value |
|---|---:|
| n | 112 |
| mean | 9.3 commits |
| median | **3 commits** |
| max | 232 commits |
| total | 1045 commits |

`review round N` across all commit subjects (n=1614):

```sh
grep -o -E 'review round [0-9]+' all_subjects.txt | sort | uniq -c
awk -F'|' '$3 ~ /review round/ {print $2}' all_subjects.txt | sort | uniq -c
```

| | count | | date | review-round commits |
|---|---:|---|---|---:|
| `review round 1` | 35 | | 2026-09-10 | 1 |
| `review round 2` | 5 | | 2026-09-11 | 1 |
| `review round 3` | 1 | | 2026-09-13 | 6 |
| | | | 2026-09-23 | 3 |
| | | | 2026-09-24 | 1 |
| | | | 2026-09-25 | **35** |

### 2.3 RED/GREEN test counts in subjects

```sh
awk -F'|' '{d=$2;s=$3; if (match(s,/RED [0-9]+ \/ GREEN [0-9]+/)) print d, substr(s,RSTART,RLENGTH)}' all_subjects.txt | sort
awk -F'|' '{d=$2;s=$3; if (match(s,/GREEN [0-9]+/)) print d, substr(s,RSTART,RLENGTH)}' all_subjects.txt | sort
```

| date | marker |
|---|---|
| 2026-09-25 | GREEN 935 |
| 2026-09-25 | GREEN 938 (×2) |
| 2026-09-25 | RED 1 / GREEN 944 |
| 2026-09-25 | RED 6 / GREEN 947 |

The `RED n / GREEN n` convention exists **only on 2026-09-25** — it is a Sprint 13 innovation,
five commits old. Test-suite growth therefore has to be reconstructed from `docs/DEVELOPING.md`
instead (section 9).

**What the numbers say.** The merge subject is not a reliable review record: 78 % of merges never
mention review, and the RED/GREEN convention the brief expected is one day old. Measured from
the branch side instead, **65 % of merges needed no fix round and 89 % needed at most one** —
first-pass review success is high. The median merged branch is **3 commits**, so the unit of work
is small even though the mean (9.3) is dragged up by a 232-commit outlier. "PASS WITH FINDINGS"
(12) outnumbers bare "PASS" (4) three to one: reviews usually produce findings that are recorded
rather than blocking.

---

## 3. Rework

### 3.1 Subject-prefix census

```sh
awk -F'|' '{print $3}' all_subjects.txt | grep -o -E '^[a-z]+(\([^)]*\))?(!)?:' | sed -E 's/\(.*\)//' | sort | uniq -c | sort -rn
```

(n=1614)

| prefix | commits | | prefix | commits |
|---|---:|---|---|---:|
| `docs:` | 683 | | `refactor:` | 18 |
| `fix:` | 238 | | `build:` | 18 |
| `feat:` | 141 | | `runtime:` | 15 |
| `test:` | 35 | | `perf:` | 13 |
| `merge:` | 30 | | `chore:` | 13 |
| `parity:` | 29 | | `diag:` | 11 |
| `recomp:` | 22 | | `research:` | 10 |
| `tools:` | 21 | | `ci:` | 10 |
| `harness:` | 21 | | `symbols:` | 8 |

`fix:` is **238 / 1614 = 14.7 %** of all commits and **238 / (238+141) = 62.8 %** of the
`fix:`+`feat:` pair.

### 3.2 Rework keywords

```sh
awk -F'|' '{print $3}' all_subjects.txt | grep -c -E '^(fix|revert|retract)'
awk -F'|' '{print $3}' all_subjects.txt | grep -c -E '^Revert '
for p in retract reopen " again" "second time" regress revert rollback undo "did not" broke regression; do
  printf "%-14s %s\n" "$p" "$(awk -F'|' '{print $3}' all_subjects.txt | grep -ci -- "$p")"; done
```

| signal | commits |
|---|---:|
| subject starts `fix`/`revert`/`retract` | **244** (15.1 %) |
| `Revert "…"` (git-generated revert) | **0** |
| contains `revert` anywhere | 5 |
| contains `retract` | 9 |
| contains ` again` | 44 |
| contains `reopen` | 2 |
| contains `regress` | 3 |
| contains `regression` | 3 |
| contains `broke` | 8 |
| contains `did not` | 9 |
| contains `rollback` / `roll back` / `second time` / `re-open` | 0 |
| contains `undo` | 1 |

### 3.3 Concurrent-touch approximation

The brief's exact "same file within 24 h from a different branch" is not cheaply computable
here (agent branches are merged and their commits interleave by date, not by topology), so the
approximation used is **commits per file in the last 7 days**:

```sh
git log --since=2026-09-19 --name-only --format='' --no-renames | grep -v '^$' | sort | uniq -c | awk '$1>=5' | wc -l
git log --since=2026-09-19 --name-only --format='' --no-renames | grep -v '^$' | sort | uniq -c | awk '$1>=10' | wc -l
git log --since=2026-09-19 --name-only --format='' --no-renames | grep -v '^$' | sort -u | wc -l
git log --name-only --format='' --no-renames | grep -v '^$' | sort -u | wc -l
```

| measure | value |
|---|---:|
| distinct files touched, last 7 days | 1005 |
| distinct files touched, all history | 2097 |
| files with **≥5** commits in last 7 days | **147** |
| files with **≥10** commits in last 7 days | **50** |

**What the numbers say.** There are **zero** `git revert` commits in 1616 — rework is expressed
as forward `fix:` commits, never as history rewind. `fix:` at 14.7 % of all commits outnumbers
`feat:` 238-to-141. Explicit failure language is rare (9 `retract`, 3 `regress`, 8 `broke`), but
44 subjects say " again", which is the largest single rework signal and is not captured by any
prefix convention. In the last week, 50 files were committed to ten or more times, and 1005 of
the repo's 2097 ever-touched files were touched — nearly half the tracked surface moved in 7 days.

---

## 4. Documentation vs code

### 4.1 Churn (lines added/deleted), classified by path

```sh
git log --numstat --format='C|%H|%ad' --date=short --no-renames > numstat_all.txt
awk -v SINCE=""           -f classify.awk numstat_all.txt   # whole history
awk -v SINCE="2026-09-19" -f classify.awk numstat_all.txt   # last 7 days
```

`classify.awk` buckets each numstat row by path prefix: `docs/`, `tools_py/tests/`→tests_py,
`tests/`→tests_fixtures, `third_party/ps2recomp/ps2xTest/`→tests_cpp, rest of
`third_party/ps2recomp/`→cpp_engine, `tools_py/`→tools_py, `server/`→server_cs, `scripts/`,
`recomp/`→recomp_inputs, any other `*.md`→md_root. Binary rows (`-`) are skipped. Merge commits
produce no numstat rows, so this counts leaf commits only.

**Whole history:**

| category | added | deleted | file-touches | share of added |
|---|---:|---:|---:|---:|
| `third_party/ps2recomp/` (C++ engine) | 258 947 | 101 902 | 1517 | 39.1 % |
| `docs/` | 115 703 | 36 978 | 1902 | 17.5 % |
| `tools_py/` (non-test) | 68 309 | 6 866 | 692 | 10.3 % |
| `tools_py/tests/` | 53 942 | 1 490 | 573 | 8.2 % |
| `recomp/` (symbol/name inputs) | 53 913 | 8 756 | 69 | 8.1 % |
| `server/` (C#) | 46 589 | 196 | 522 | 7.0 % |
| `ps2xTest/` (C++ tests) | 43 877 | 2 704 | 366 | 6.6 % |
| `scripts/` | 12 143 | 3 057 | 319 | 1.8 % |
| other | 6 667 | 608 | 149 | 1.0 % |
| root `*.md` | 1 236 | 823 | 87 | 0.2 % |
| `tests/` fixtures | 333 | 22 | 28 | 0.1 % |
| **total** | **661 659** | **163 402** | 6224 | |
| *(all `*.md` anywhere, cross-cut)* | *109 928* | *36 325* | *1964* | *16.6 %* |

**Last 7 days (≥ 2026-09-19):**

| category | added | deleted | file-touches | share of added |
|---|---:|---:|---:|---:|
| `third_party/ps2recomp/` (C++ engine) | 130 734 | 95 323 | 719 | 38.4 % |
| `docs/` | 80 746 | 34 349 | 1328 | 23.7 % |
| `tools_py/` (non-test) | 39 503 | 3 780 | 379 | 11.6 % |
| `tools_py/tests/` | 29 747 | 1 054 | 362 | 8.7 % |
| `recomp/` | 27 588 | 1 637 | 34 | 8.1 % |
| `ps2xTest/` | 15 869 | 2 493 | 247 | 4.7 % |
| `scripts/` | 8 695 | 2 478 | 213 | 2.6 % |
| other | 5 312 | 522 | 107 | 1.6 % |
| `server/` | 1 312 | 168 | 55 | 0.4 % |
| root `*.md` | 883 | 760 | 64 | 0.3 % |
| `tests/` fixtures | 221 | 0 | 10 | 0.1 % |
| **total** | **340 610** | **142 604** | 3518 | |

Rolled up:

| roll-up | history | last 7 d |
|---|---:|---:|
| docs (`docs/` + root `*.md`) | 17.7 % | 24.0 % |
| code (`third_party/ps2recomp` non-test + `tools_py` non-test + `scripts` + `server`) | 58.3 % | 52.9 % |
| tests (`tools_py/tests` + `ps2xTest` + `tests/`) | 14.8 % | 13.5 % |
| generated-ish inputs (`recomp/`) | 8.1 % | 8.1 % |
| docs add:delete ratio | 3.13 : 1 | 2.35 : 1 |
| C++ engine add:delete ratio | 2.54 : 1 | **1.37 : 1** |

### 4.2 Current tree size, in lines

```sh
git ls-files '*.md' | xargs wc -l | tail -1
git ls-files docs | grep -E '^docs/[^/]+\.md$' | xargs wc -l | tail -1
for f in docs/STATUS.md docs/KNOWN.md docs/DEVELOPING.md docs/HANDOFF.md; do wc -l < "$f"; done
cat docs/superpowers/plans/*.md | wc -l ; cat docs/superpowers/specs/*.md | wc -l
git ls-files 'third_party/ps2recomp/**' | grep -E '\.(cpp|h|hpp|c|cc)$' | grep -v '/ps2xTest/' | xargs wc -l | tail -1
git ls-files 'tools_py/**' | grep '\.py$' | grep -v '^tools_py/tests/' | xargs wc -l | tail -1
```

Documentation:

| target | lines | files |
|---|---:|---:|
| all tracked `*.md` | **72 585** | 194 |
| `docs/**/*.md` | 70 392 | 174 |
| `docs/*.md` (top level only) | 8 015 | 18 |
| `docs/archive/` | 27 962 | 51 |
| `docs/research/` | 24 786 | 73 |
| `docs/superpowers/` | 5 921 | 15 |
| `docs/audits/` | 3 553 | 13 |
| `docs/story/` | 83 | 2 |
| `docs/parity/` | 72 | 2 |
| `docs/superpowers/plans/*.md` | **3 485** | 7 |
| `docs/superpowers/specs/*.md` | **2 436** | 8 |
| `docs/STATUS.md` | **2 574** | 1 |
| `docs/DEVELOPING.md` | **937** | 1 |
| `docs/STORY.md` | 904 | 1 |
| `docs/KNOWN.md` | **658** | 1 |
| `docs/HANDOFF.md` | **375** | 1 |
| `README.md` / `CONTRIBUTING.md` / `ONBOARDING.md` | 165 / 109 / 72 | 3 |

Largest single docs (top 6):

| file | lines |
|---|---:|
| `docs/archive/sprints-7-12/2026-09-19-sprint-9-goal-1-failures-explain-themselves.md` | 3 196 |
| `docs/archive/sprints-7-12/2026-09-17-sprint-7-two-strangers-two-machines.md` | 2 749 |
| `docs/STATUS.md` | 2 574 |
| `docs/archive/sprints-7-12/2026-09-20-sprint-9-goal-3-knob-retirement.md` | 2 342 |
| `docs/archive/sprints-7-12/2026-09-18-sprint-8-linux-client.md` | 2 230 |
| `docs/research/18-online-round-start.md` | 1 876 |

Source:

| target | lines | files |
|---|---:|---:|
| C++ engine `third_party/ps2recomp/` **excluding** `ps2xTest/` | **154 695** | 336 |
| C++ tests `ps2xTest/` | 40 962 | — |
| Python `tools_py/` **excluding** `tools_py/tests/` | **59 989** | 172 |
| Python tests `tools_py/tests/` | 44 995 | — |
| `scripts/*.sh|*.ps1` | 4 693 | — |
| `server/**/*.cs` (vendored Horizon) | 16 814 | — |

### 4.3 Doc-to-source ratios

Excluded from every "source" figure: `research/` (gitignored external clones), `recomp/output/`
and `recomp/build/` (gitignored generated recompiler output), `third_party/ps2recomp/build*/`,
`dist*/`, and binary assets. Three defensible denominators, because the project has no `src/`:

| denominator | source lines | doc : source |
|---|---:|---:|
| A — all non-test source the project edits, **including** the `third_party/ps2recomp` fork and `scripts/` but excluding vendored `server/` C# | 219 377 | **0.33 : 1** |
| B — everything, including tests and the vendored C# server | 322 148 | 0.23 : 1 |
| C — strictly non-`third_party`, non-`server` project code (Python + scripts, non-test) | 64 682 | **1.12 : 1** |

**What the numbers say.** Denominator A is the honest one: **one line of documentation for every
three lines of source**, 72 585 vs 219 377. Documentation's share of *churn* is lower than its
share of *volume* would suggest at 17.7 % of all lines ever added, but it is rising — 24.0 % in
the last week, a 6-point jump. Docs are also the most rewritten category by add:delete ratio
except the engine: 3.13 added per deleted over history, tightening to 2.35 in the last week,
which means recent doc work is increasingly replacement rather than accretion. The C++ engine's
last-7-day ratio of **1.37 added per deleted** is the sharpest signal in this table: for every
three lines written into the engine last week, two lines were removed. `docs/archive/` alone
(27 962 lines) is larger than `docs/research/` and nearly four times the entire top-level docs
set — most of the documentation corpus by volume is retired sprint narrative.

---

## 5. Commit subject length

```sh
git log --format='%H|%ad|%s' --date=short > all_subjects.txt
git log --merges --format='%H|%ad|%s' --date=short > merge_subjects.txt
awk -F'|' '{print $3}' all_subjects.txt | awk '{print length($0)}' | sort -n | \
  awk '{a[NR]=$1;s+=$1} END{print "n="NR,"mean="s/NR,"median="a[int((NR+1)/2)],"p90="a[int(NR*0.9)],"max="a[NR]}'
awk -F'|' '{print $3}' all_subjects.txt | awk 'length($0)>200' | wc -l
```

| population | n | mean | median | p90 | max |
|---|---:|---:|---:|---:|---:|
| all commits | 1614 | **145.9** | 126 | 232 | **1184** |
| true merge commits (`git log --merges`) | 112 | **176.2** | 150 | 335 | 511 |
| non-merge commits | 1532 | 144.6 | 126 | 224 | 1184 |
| `docs…`-prefixed commits | 689 | 142.8 | 121 | 218 | 784 |

| threshold | all commits | merge commits |
|---:|---:|---:|
| > 100 chars | 1145 (70.9 %) | 46 |
| > 200 chars | **249 (15.4 %)** | **47 / 112 = 42.0 %** |
| > 300 chars | 80 (5.0 %) | 21 |
| > 500 chars | **22 (1.4 %)** | **1** |
| > 1000 chars | 1 | 0 |

Caveat: `grep '^Merge '` finds only 82 merges; the other 30 use a `merge:` conventional prefix.
The merge row above uses `git log --merges` (all 112), not the subject text.

Longest subjects:

| chars | date | opening |
|---:|---|---|
| 1184 | 2026-09-24 | `feat(names): the applier, and the first 1,491 names applied to the sidecar (Sprint 12 Task 3, Goal 1; R257, R261, …` |
| 784 | 2026-09-24 | `docs(research): 47, 51, 55, 57 -- the readable-name rule set (R1-R12, 0 sanitiser changes and 0 collisions …` |
| 751 | 2026-09-24 | `feat(names): the sidecar at 1,840 rows / 1,771 readable names …` |

**What the numbers say.** The 50-character subject convention is not in use anywhere: the
*median* subject is 126 characters, 71 % exceed 100, and the longest is 1184 characters on a
single line. Merge subjects run 21 % longer than ordinary ones (median 150) and 42 % of them
exceed 200 characters, because the merge line is being used as the sprint's outcome record —
it carries task numbers, issue numbers, ruling numbers, RED/GREEN counts and review verdict in
one unwrapped line. Doc commits are marginally *shorter* than the average, so subject inflation
is not a documentation-specific habit.

---

## 6. Churn hotspots

```sh
git log --since=2026-09-12 --name-only --format='' --no-renames | grep -v '^$' | sort | uniq -c | sort -rn | head -25
git log             --name-only --format='' --no-renames | grep -v '^$' | sort | uniq -c | sort -rn | head -25
```

### 6.1 Top 25, last 14 days (since 2026-09-12)

| # | commits | file | kind |
|---:|---:|---|---|
| 1 | 224 | `docs/KNOWN.md` | process doc |
| 2 | 152 | `docs/CURRENT_SPRINT.md` | process doc |
| 3 | 107 | `docs/superpowers/plans/2026-09-25-sprint-13.md` | process doc |
| 4 | 92 | `docs/HUMAN_TASKS.md` | process doc |
| 5 | 68 | `docs/STATUS.md` | process doc |
| 6 | 67 | `docs/HANDOFF.md` | process doc |
| 7 | 49 | `docs/DEVELOPING.md` | process doc |
| 8 | 46 | `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp` | test code |
| 9 | 43 | `tools_py/parity/online_match_ours.py` | code |
| 10 | 39 | `README.md` | process doc |
| 11 | 37 | `tools_py/parity/online_login_ours.py` | code |
| 12 | 35 | `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` | code |
| 13 | 32 | `third_party/ps2recomp/ps2xLauncher/src/main.cpp` | code |
| 14 | 31 | `docs/superpowers/plans/2026-09-24-sprint-12.md` | process doc |
| 15 | 30 | `third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp` | test code |
| 16 | 28 | `docs/superpowers/plans/2026-09-23-sprint-11.md` | process doc |
| 17 | 27 | `third_party/ps2recomp/ps2xTest/CMakeLists.txt` | build |
| 18 | 25 | `third_party/ps2recomp/ps2xTest/src/main.cpp` | test code |
| 19 | 24 | `docs/story/index.html` | doc/site |
| 20 | 23 | `docs/archive/sprints-7-12/2026-09-20-sprint-10-music-round-four.md` | process doc |
| 21 | 23 | `docs/STORY.md` | process doc |
| 22 | 23 | `docs/ROADMAP.md` | process doc |
| 23 | 22 | `tools_py/parity/gate.py` | code |
| 24 | 22 | `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp` | code |
| 25 | 21 | `tools_py/release/leak_allow.txt` | config |

Process docs occupy **14 of the top 25** and **7 of the top 7**.

### 6.2 Top 25, whole history

| # | commits | file | kind |
|---:|---:|---|---|
| 1 | 230 | `docs/KNOWN.md` | process doc |
| 2 | 152 | `docs/CURRENT_SPRINT.md` | process doc |
| 3 | 149 | `docs/STATUS.md` | process doc |
| 4 | 118 | `docs/HANDOFF.md` | process doc |
| 5 | 107 | `docs/superpowers/plans/2026-09-25-sprint-13.md` | process doc |
| 6 | 92 | `docs/HUMAN_TASKS.md` | process doc |
| 7 | 69 | `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` | code |
| 8 | 50 | `tools_py/parity/online_match_ours.py` | code |
| 9 | 50 | `README.md` | process doc |
| 10 | 49 | `tools_py/parity/online_login_ours.py` | code |
| 11 | 49 | `docs/DEVELOPING.md` | process doc |
| 12 | 46 | `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp` | test code |
| 13 | 43 | `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp` | code |
| 14 | 41 | `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` | code |
| 15 | 36 | `…/ps2xRuntime/src/lib/vu/native/socom2_dispatch_0x1b50.cpp` | code |
| 16 | 32 | `third_party/ps2recomp/ps2xLauncher/src/main.cpp` | code |
| 17 | 31 | `tools_py/parity/gate.py` | code |
| 18 | 31 | `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt` | build |
| 19 | 31 | `docs/superpowers/plans/2026-09-24-sprint-12.md` | process doc |
| 20 | 31 | `build.sh` | build |
| 21 | 30 | `tools_py/tests/test_gate.py` | test code |
| 22 | 30 | `third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp` | test code |
| 23 | 30 | `third_party/ps2recomp/ps2xTest/CMakeLists.txt` | build |
| 24 | 30 | `third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp` | code |
| 25 | 29 | `third_party/ps2recomp/ps2xTest/src/main.cpp` | test code |

Process docs: **10 of the top 25**, and **6 of the top 6**.

### 6.3 Top 15, last 7 days

| commits | file |
|---:|---|
| 110 | `docs/KNOWN.md` |
| 107 | `docs/superpowers/plans/2026-09-25-sprint-13.md` |
| 105 | `docs/CURRENT_SPRINT.md` |
| 65 | `docs/HUMAN_TASKS.md` |
| 56 | `docs/HANDOFF.md` |
| 49 | `docs/DEVELOPING.md` |
| 31 | `docs/superpowers/plans/2026-09-24-sprint-12.md` |
| 29 | `docs/STATUS.md` |
| 28 | `docs/superpowers/plans/2026-09-23-sprint-11.md` |
| 27 | `…/ps2xRuntime/src/lib/game_overrides_socom2.cpp` |
| 26 | `README.md` |
| 25 | `…/ps2xTest/src/launcher_tests.cpp` |
| 24 | `docs/story/index.html` |
| 23 | `…/plans/2026-09-20-sprint-10-music-round-four.md` |
| 23 | `docs/STORY.md` |

**What the numbers say.** The six most-committed files in the entire repository are all process
documents, and the top one — `docs/KNOWN.md`, 658 lines — has been committed to **230 times**,
more than three times the most-committed source file. 224 of those 230 commits are in the last
14 days, so its edit rate is accelerating, not settling. The sprint-13 plan file alone took
107 commits in one week. Every doc in the top ten is a coordination surface (known issues,
current sprint, status, handoff, human tasks, plan) rather than reference material; the
reference docs (`docs/research/`, 24 786 lines) barely appear. `docs/DEVELOPING.md` was
committed 49 times, **all 49 of them in the last 7 days**.

---

## 7. Branch / worktree structure

```sh
git branch -a
git worktree list
git branch --list 'agent/*' | wc -l
git branch --merged sprint-13 --list 'agent/*' | wc -l
git branch --no-merged sprint-13 --list 'agent/*'
git for-each-ref --sort=creatordate --format='%(refname:short)|%(creatordate:short)|%(objecttype)' refs/tags
```

| measure | value |
|---|---:|
| local branches | 102 |
| `agent/*` branches | **66** |
| `agent/*` merged into `sprint-13` | **55 (83.3 %)** |
| `agent/*` not merged into `sprint-13` | **11** |
| `agent/*` merged into `main` | **0** |
| `sprint-N` branches (1–13), all merged into sprint-13 | 13 |
| `upstream-pr-NNN` branches | 17 |
| remote branches | 16 |
| worktrees | 5 |

Unmerged `agent/*`: `agent/pr227`, `pr229`, `pr230`, `pr231`, `pr232`, `pr237`, `pr240`,
`pr241`, `pr243`, `pr246` (10 upstream-PR evaluation branches) and `agent/s13-o2` (1 live
worktree). Only **one** unmerged branch is actual project work.

Worktrees:

| path | head | branch |
|---|---|---|
| `C:/Projects/socom_pc` | `76701f4a` | `sprint-13` |
| `C:/Projects/socom_pc_web` | `4a1cd2e8` | `feat/web-map-viewer` |
| `C:/Projects/wt-cherry` | `f7a7e206` | `agent/picks-keep` |
| `C:/Projects/wt-ci-fix` | `6d6d42fc` | `agent/ci-fix2` |
| `C:/Projects/wt-s13-o2` | `7d8a950d` | `agent/s13-o2` |

Tags — note the split between tag-creation date and the commit each points at:

| tag | tagged | commit date | ancestor of HEAD |
|---|---|---|---|
| `v0.0` … `v0.4` | 2026-02-22 … 2026-04-04 | — | **no** (upstream ps2recomp tags) |
| `v0.5.0` | 2026-09-23 | 2026-09-13 | yes |
| `v0.6.0` | 2026-09-23 | 2026-09-17 | yes |
| `v0.7.0` | 2026-09-23 | 2026-09-18 | yes |
| `v0.8.0` | 2026-09-23 | 2026-09-19 | yes |
| `playtest-1` | 2026-09-20 | 2026-09-20 | yes |
| `v0.9.0` | 2026-09-20 | 2026-09-20 | yes |
| `v0.10.0` | 2026-09-23 | 2026-09-23 | yes |
| `v0.11.0` | **2026-09-25** | 2026-09-25 | yes |
| `v0.12.0` | **2026-09-25** | 2026-09-25 | yes |

**What the numbers say.** 66 agent branches for 112 merges — agent branches are the merge unit,
and 83 % of them have landed. **Zero** agent branches have reached `main`; everything integrates
into the sprint branch, and `main` is 13 sprint-merges behind that pattern. Five worktrees are
live simultaneously, which matches the concurrent-edit pressure seen in section 3.3. Five of the
nine project tags (`v0.5.0`–`v0.8.0`) were **created retroactively on 2026-09-23** against
commits from 09-13 to 09-19 — version history was reconstructed after the fact, not cut at
release time. Two minor versions shipped on the same day (09-25).

---

## 8. Ruling numbers (`R###`)

```sh
git grep -ho -E '\bR[0-9]{1,3}\b' -- 'docs/**' '*.md' | sort -u | wc -l     # distinct ids present
git grep -ho -E '\bR[0-9]{1,3}\b' -- 'docs/**' '*.md' | wc -l               # total mentions
git grep -c -E '\bR[0-9]{2,3}\b' -- 'docs/**' '*.md' | sort -t: -k2 -rn | head
```

| measure | value |
|---|---:|
| distinct `R<1–3 digit>` ids in tracked docs | 299 |
| total `R###` mentions in tracked docs | **2 993** |
| id range observed | R10 – R269 |
| authoritative "next free ruling number" (`docs/HANDOFF.md`, `docs/CURRENT_SPRINT.md`) | **R269** → 268 issued |

The 299 figure over-counts: `R5900` (the PS2 CPU) and a `R1`–`R12` name-rule set in a research
doc both match. The register itself is authoritative and says R269 is next free.

Method for first-appearance dating — approximate, stated plainly: rather than 268 × `git log -S`
(too slow here), one `git log -p` pass over all tracked `*.md` records, for each id, the
**earliest commit date on which that id appears on an added (`+`) line**. This over-attributes
when a ruling is first written in an untracked place and later copied in, and it under-attributes
nothing. Word-boundary guarded so `R5900` does not match.

```sh
git log --date=short --format='D|%ad|%h' -p --no-renames -- 'docs/*.md' '*.md' | awk '
/^D\|/ {split($0,a,"|"); d=a[2]; next}
/^\+/ { s=$0; while (match(s,/R[0-9]+/)) { id=substr(s,RSTART,RLENGTH); rest=substr(s,RSTART+RLENGTH,1);
   n=length(id)-1; if (n>=2 && n<=3 && rest !~ /[0-9A-Za-z_]/) { if (!(id in f) || d<f[id]) f[id]=d }
   s=substr(s,RSTART+RLENGTH) } }
END{for(i in f) print f[i], i}' | sort
```

260 ids (R10–R269) dated. First appearance per day:

| date | rulings first seen | cumulative |
|---|---:|---:|
| 2026-09-08 | 1 | 1 |
| 2026-09-12 | 1 | 2 |
| 2026-09-13 | **61** | 63 |
| 2026-09-14 | 5 | 68 |
| 2026-09-15 | 3 | 71 |
| 2026-09-17 | 14 | 85 |
| 2026-09-18 | 16 | 101 |
| 2026-09-19 | **67** | 168 |
| 2026-09-20 | 7 | 175 |
| 2026-09-21 | **52** | 227 |
| 2026-09-22 | 9 | 236 |
| 2026-09-23 | 9 | 245 |
| 2026-09-24 | 10 | 255 |
| 2026-09-25 | 5 | 260 |

Where rulings are cited most:

| file | `R##`/`R###` matching lines |
|---|---:|
| `docs/CURRENT_SPRINT.md` | 154 |
| `docs/archive/sprints-1-6/2026-09-13-sprint-5-control-readout-and-first-kill.md` | 104 |
| `docs/archive/sprints-7-12/2026-09-20-sprint-9-goal-3-knob-retirement.md` | 102 |
| `docs/archive/CURRENT_SPRINT-sprints-9-to-11.md` | 91 |
| `docs/superpowers/plans/2026-09-24-sprint-12.md` | 67 |
| `docs/KNOWN.md` | 55 |
| `docs/story/timeline.json` | 44 |
| `docs/superpowers/plans/2026-09-25-sprint-13.md` | 42 |

**What the numbers say.** **268 numbered rulings in 30 days** — roughly nine per active day, and
2 993 citations of them across the docs, i.e. each ruling is referenced about eleven times. The
three spike days (09-13: 61, 09-19: 67, 09-21: 52 = 180 of 260, 69 %) are bulk sprint-retro
writes rather than 61 separate decisions made in one day; that is an artefact of the
first-appearance method, which dates a ruling to when its *document* was committed. The counter
has a recorded failure mode: `docs/DOC_MAINTENANCE.md` notes `HANDOFF.md` advertised "next free
R179" while R241 was in use, and that an agent once "numbered from R200, already taken" — the
register lived in two files that disagreed.

---

## 9. Test-count trajectory

The section in `docs/DEVELOPING.md` is not titled "What a green run looks like"; the equivalent
is the five-row table at lines ~632–640 headed by *"The expected lines are the ones to look for;
each count carries the date and the tree it was read on, and the test counts only ever grow, so
more than the number here is fine and fewer is a regression to report."* Rows 3 and 4 carry the
C++ (`ps2x_tests`, `Total Tests: N`) and Python (`Ran N tests`) counts.

```sh
git log --date=short --format='D|%ad|%h' -p --no-renames -- docs/DEVELOPING.md > developing_p.txt
awk '/^D\|/{split($0,a,"|");d=a[2];h=a[3];next} /^\+/{s=$0; while(match(s,/Total Tests: [0-9]+/)){print d,h,substr(s,RSTART+13,RLENGTH-13); s=substr(s,RSTART+RLENGTH)}}' developing_p.txt | sort -u
awk '/^D\|/{split($0,a,"|");d=a[2];h=a[3];next} /^\+/{s=$0; while(match(s,/Ran [0-9]+ tests/)){print d,h,substr(s,RSTART+4,RLENGTH-10); s=substr(s,RSTART+RLENGTH)}}' developing_p.txt | sort -u
```

C++ suite (`ps2x_tests`, `Total Tests:`), as written into `docs/DEVELOPING.md`:

| date | commit | C++ tests |
|---|---|---:|
| 2026-09-20 | `92530267` | 500 |
| 2026-09-21 | `065bdcc9` | 764 |
| 2026-09-24 | `ce8f61e7` | 876 |
| 2026-09-25 | `8612c2d3` | 881 |
| 2026-09-25 | `32c06a0c` / `85941314` / `ad3f16be` | 892 |
| 2026-09-25 | `0669a291` | **940** |

Python suite (`python -m unittest discover -s tools_py/tests`):

| date | commit | Python tests |
|---|---|---:|
| 2026-09-20 | `92530267` | 1 104 |
| 2026-09-21 | `065bdcc9` | 1 723 |
| 2026-09-22 | `c5c01706` | 1 832 |
| 2026-09-25 | `32c06a0c` | 2 553 |
| 2026-09-25 | `0669a291` | 2 795 |
| 2026-09-25 | `0669a291` | **3 164** |

Cross-check from commit subjects (independent source, section 2.3):

```sh
awk -F'|' '{d=$2;s=$3; if (match(s,/ps2x_tests [0-9]+\/[0-9]+/)) print d, substr(s,RSTART,RLENGTH)}' all_subjects.txt | sort
awk -F'|' '{d=$2;s=$3; if (match(s,/Python [0-9]+ OK/))          print d, substr(s,RSTART,RLENGTH)}' all_subjects.txt | sort
```

| date | subject claim |
|---|---|
| 2026-09-21 | `ps2x_tests 707/0`, `709/0`, `716/0` |
| 2026-09-25 | `ps2x_tests 940/0`, `943/0`, `944/0` |
| 2026-09-25 | `Python 3164 OK`, `Python 3176 OK` (×2) |
| 2026-09-25 | `RED 1 / GREEN 944`, `RED 6 / GREEN 947` |

Combined trajectory (C++ + Python):

| date | C++ | Python | total |
|---|---:|---:|---:|
| 2026-09-20 | 500 | 1 104 | 1 604 |
| 2026-09-21 | 764 | 1 723 | 2 487 |
| 2026-09-22 | — | 1 832 | — |
| 2026-09-24 | 876 | — | — |
| 2026-09-25 | **947** | **3 176** | **4 123** |

Current tracked test source: `tools_py/tests/` 44 995 lines, `ps2xTest/` 40 962 lines,
`tests/fixtures/` 333 added lines of history — **85 957 lines of test code** against 219 377
lines of non-test source (0.39 : 1).

**What the numbers say.** The suites grew **2.6×** in five days: 1 604 combined tests on 09-20 →
4 123 on 09-25, with the Python suite nearly tripling (1 104 → 3 176) and the C++ suite almost
doubling (500 → 947). Growth is not smooth — Python jumped 2 553 → 2 795 → 3 164 → 3 176 within
09-25 alone. The documented counts lag the committed reality by a few points (DEVELOPING says
940 C++ where commit subjects that day claim 944 and 947), which is the expected cost of hand-
maintained numbers in prose. Note also that the doc explicitly frames the counts as a floor
("only ever grow… fewer is a regression to report") rather than an assertion.

---

## 10. Issues

```sh
gh issue list --state all --limit 300 --json number,title,state,createdAt,closedAt,labels > issues.json
jq -r '[.[]|select(.state=="OPEN")]|length'   issues.json
jq -r '[.[]|select(.state=="CLOSED")]|length' issues.json
jq -r '.[] | .labels[]?.name' issues.json | sort | uniq -c | sort -rn
```

`gh` 2.100.0 is available and authenticated. **32 issues total** (numbers 25–60; `gh issue list`
excludes pull requests, so the gaps in the number line are PRs).

| state | count |
|---|---:|
| OPEN | **21 (65.6 %)** |
| CLOSED | **11 (34.4 %)** |

By label (labels are not exclusive — every issue carries `known-issue`):

| label | total | open | closed |
|---|---:|---:|---:|
| `known-issue` | 32 | 21 | 11 |
| `recomp` | 13 | 11 | 2 |
| `harness` | 10 | 2 | 8 |
| `carried` | 6 | 4 | 2 |
| `help wanted` | 5 | 2 | 3 |
| `render` | 3 | 2 | 1 |
| `build` | 2 | 2 | 0 |
| `audio` | 2 | 2 | 0 |
| `online` | 1 | 1 | 0 |
| `needs-disc-gate` | 1 | 1 | 0 |
| `linux` | 1 | 1 | 0 |
| `good first issue` | 1 | 0 | 1 |

Time to close:

```sh
jq -r '.[]|select(.state=="CLOSED")|[.number,.createdAt,.closedAt]|@tsv' issues.json | \
 while IFS=$'\t' read n c cl; do echo "$n $(( ($(date -d "$cl" +%s) - $(date -d "$c" +%s))/3600 ))"; done | sort -k2 -n
```

| issue | hours open |
|---:|---:|
| #29 | 0 |
| #45 | 4 |
| #46 | 5 |
| #48 | 16 |
| #30 | 35 |
| #38 | 37 |
| #27 | 46 |
| #39 | 49 |
| #35 | 50 |
| #36 | 50 |
| #37 | 50 |

| stat | value |
|---|---:|
| n closed | 11 |
| **median time to close** | **37 h (1.5 days)** |
| mean | 31.1 h |
| min / max | 0 h / 50 h |

Creation and closure by day:

| date | created | closed |
|---|---:|---:|
| 2026-09-23 | 18 | 1 |
| 2026-09-25 | 13 | 10 |
| 2026-09-26 | 1 | — |

**What the numbers say.** The issue tracker is three days old and holds 32 items: it was opened
in bulk on 2026-09-23 (18 issues in one day) and topped up on 09-25 (13 more). Median time to
close is **37 hours**, and no issue has ever stayed open longer than 50 — but that ceiling is an
artefact of the tracker's age, not of triage discipline. The label distribution separates cleanly
by owner: `harness` issues are 80 % closed (8/10) while `recomp` issues are 85 % open (11/13) —
tooling problems get fixed, recompilation problems accumulate. Every issue carries `known-issue`,
so that label carries no information; the discriminating labels are the seven area tags. The 10
closures on 09-25 coincide with the 302-commit / 51-merge day in section 1.1.

---

## Appendix — commands whose output is cited but not tabled

```sh
# repo scale
git rev-list --count HEAD                                  # 1616
git rev-list --merges --count HEAD                         # 112
git ls-files | wc -l                                       # 2213

# research/ and generated output are invisible to git
grep -n 'research' .gitignore                              # 1:/research/
grep -n -i -E 'recomp|generated|dist' .gitignore           # /recomp/output/, /recomp/build/, …
git ls-files research | wc -l                              # 0
ls -1 research | wc -l                                     # 10 cloned external repos on disk

# docs-only commits
git log --format='@%H' --name-only --no-renames | awk '
 /^@/{if(tot>0){with++; if(tot==md) only++} tot=0; md=0; next}
 NF{tot++; if($0 ~ /\.md$/) md++}
 END{if(tot>0){with++; if(tot==md) only++}; print with, only}'
# → 1503 commits with a diff, 630 of them (41.9 %) touch only .md files

# subject prefix share
git log --format='%s' | grep -c '^docs'                    # 691 / 1616 = 42.8 %
```

| cross-cutting fact | value |
|---|---:|
| commits whose diff touches **only** `.md` files | **630 / 1503 = 41.9 %** |
| commits whose subject starts `docs` | 691 / 1616 = 42.8 % |
| distinct files ever touched | 2097 |
| distinct files touched in the last 7 days | 1005 (47.9 % of the above) |
