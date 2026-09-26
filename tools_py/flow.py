"""The flow page: how work moves through this repository, measured from git (Sprint 14 Task M1; the review's F8).

Run: python -m tools_py.flow [--since DATE] [--check] [--rev REV] [--queue-log PATH] [--backlog PATH]
                             [--repo PATH] [--out FILE]

Writes `docs/FLOW.md`. The numbers are the ones `docs/audits/2026-09-26-autonomy-structure-review/03-git-forensics.md`
computed once by hand, with its methods; each line of the page names the command that reproduces it. They are
descriptive: no targets (the review's course H: "metrics that get optimized").

What each number is, and where it differs from note 03:
  merges_per_day        the merges `changelog.entries()` lists (Task S1's merge walk, not a second one) whose
                        committer time is on or after --since, counted per UTC calendar day of the committer time.
                        Note 03 section 1.1 counted `git log --merges` per author date in the committer's -0300
                        zone; the page states both merge counts, so a merge the walk does not reach shows.
  fix_rounds_per_merge  a histogram {rounds: merges}: for each such merge, the commits on the merged side (reachable
                        from a second parent, not from the first) whose subject matches FIX_ROUND, note 03 section
                        2.2's `review round|fix round` (case-sensitive, as its grep -E was).
  fix_rounds_per_merge_broad   the same with FIX_ROUND_BROAD, `review round|fix round|fix\\(|review`, the Task M1
                        brief's wider pattern: it also counts every `fix(scope):` commit and every subject naming a
                        review, so it is an upper bound, not a round count.
  again_subjects        the commits since --since whose subject contains " again", case-insensitive (note 03 section
                        3.2, `grep -ci -- " again"`), merges included.
  docs_share_of_churn_7d   lines added + deleted under docs/ over all lines added + deleted, `git log --numstat
                        --no-renames`, in the seven days before the rendered commit's committer time; binary rows
                        and merges (no numstat) left out, as note 03 section 4.1 left them. Note 03's "23.7 %" was the
                        share of lines ADDED, and its 24.0 % roll-up added root *.md files; this is added + deleted,
                        docs/ only.
  median_ticket_wait_s  the median of the `TICKET <id> waited <s>` lines of the lock's queue log (Task W2 writes
                        them into logs/loop_lock.queue.log beside the main tree). A line stamped (the lock's
                        `YYYY-MM-DDTHH:MM:SSZ` prefix) after the rendered commit or before --since is left out, so an
                        appended log does not make an old page stale; an unstamped line is counted. None when the log
                        is missing or holds no such line: the page says "not measured" and why.
  open_issue_age_days   the median age, in days at the rendered commit, of the open issues in `docs/BACKLOG.md` as it
                        stood at that commit, read from an "Opened" column of its open-issues table. None when the
                        table has no such column (it has none on 2026-09-26: the dates live on GitHub, and this page
                        makes no network read).
  sessions              the distinct `Claude-Session:` trailer values in the bodies of the commits since --since
                        (note 03 section 1.3's `grep '^Claude-Session:' | sort -u`).
  commits_per_session   {session: commits}; the page shows the counts, largest first, not the URLs.

"Since" is a UTC calendar day and every commit is placed by its committer time (note 03 used the author date).

Held to the commit it names, the variant Task S1 chose for a page that depends on git history (the changelog's
suite test renders at the commit that last wrote the page). The flow page counts commits, so it can never be a render
of the commit that writes it -- that commit is one more -- and so it names the commit it was rendered at, and
`--check` re-renders there (with the --since the page names) unless --rev is given: `--check` asks "is this file what
the tool says about that commit", and `--check --rev HEAD` asks "is it current". Regenerate at the close. On a shallow
clone the command refuses with exit 2 (`changelog.ShallowHistory`), as the changelog does.
"""
import argparse
import calendar
import datetime
import difflib
import os
import re
import statistics
import subprocess
import sys

from tools_py import changelog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = "docs/FLOW.md"
BACKLOG = "docs/BACKLOG.md"
NOTE03 = "docs/audits/2026-09-26-autonomy-structure-review/03-git-forensics.md"
DEFAULT_SINCE = "2026-09-01"
FIX_ROUND = re.compile(r"review round|fix round")
FIX_ROUND_BROAD = re.compile(r"review round|fix round|fix\(|review")
AGAIN = " again"
SESSION = re.compile(r"^Claude-Session:\s*(\S+)", re.M)
TICKET = re.compile(r"^(?:(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s+)?.*?\bTICKET\s+(\S+)\s+waited\s+(\d+)\b")
DATE = re.compile(r"\b(\d{4}-\d\d-\d\d)\b")
HEADER = re.compile(r"^Rendered at commit `([0-9a-f]{40})`.*? since (\d{4}-\d\d-\d\d)\b", re.M)
WEEK = 7 * 86400

NUMBERS = ("merges_per_day", "fix_rounds_per_merge", "fix_rounds_per_merge_broad", "again_subjects",
           "docs_share_of_churn_7d", "median_ticket_wait_s", "open_issue_age_days", "sessions",
           "commits_per_session")
LABELS = {
    "merges_per_day": "merges per day",
    "fix_rounds_per_merge": "fix rounds per merge",
    "fix_rounds_per_merge_broad": "fix rounds per merge, broad pattern",
    "again_subjects": "subjects saying \" again\"",
    "docs_share_of_churn_7d": "docs share of churn, seven days",
    "median_ticket_wait_s": "ticket wait",
    "open_issue_age_days": "open-issue age",
    "sessions": "sessions",
    "commits_per_session": "commits per session",
}


def _git(repo, *args):
    return changelog._git(repo, *args)


def _day_epoch(day):
    return calendar.timegm(datetime.datetime.strptime(day, "%Y-%m-%d").timetuple())


def _utc(ct, fmt="%Y-%m-%d"):
    return datetime.datetime.fromtimestamp(ct, datetime.timezone.utc).strftime(fmt)


def _median(values):
    if not values:
        return None
    m = statistics.median(values)
    return int(m) if float(m).is_integer() else m


def _histogram(counts):
    out = {}
    for n in counts:
        out[n] = out.get(n, 0) + 1
    return dict(sorted(out.items()))


def ticket_waits(path, since, until_stamp):
    """The waits (seconds) of the queue log's TICKET lines, within [since, until_stamp] where a line is stamped."""
    if not path or not os.path.isfile(path):
        return None
    waits = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = TICKET.match(line.strip())
            if not m:
                continue
            stamp = m.group(1)
            if stamp and (stamp > until_stamp or stamp[:10] < since):
                continue
            waits.append(int(m.group(3)))
    return waits


def issue_ages(text, day):
    """The ages in days at `day` of the open issues in a BACKLOG text's open-issues table, from its Opened column;
    None when there is no such column."""
    if not text:
        return None
    section = re.search(r"^## [^\n]*Open issues[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not section:
        return None
    rows = [l for l in section.group(1).splitlines() if l.startswith("|")]
    if not rows:
        return None
    cells = [c.strip() for c in rows[0].strip().strip("|").split("|")]
    col = next((i for i, c in enumerate(cells) if c.lower().startswith("opened")), None)
    if col is None:
        return None
    ref = datetime.datetime.strptime(day, "%Y-%m-%d").date()
    ages = []
    for row in rows[2:]:
        parts = [c.strip() for c in row.strip().strip("|").split("|")]
        m = DATE.search(parts[col]) if col < len(parts) else None
        if m:
            ages.append((ref - datetime.datetime.strptime(m.group(1), "%Y-%m-%d").date()).days)
    return ages


def _backlog_at(repo, rev):
    try:
        return _git(repo, "show", "%s:%s" % (rev, BACKLOG))
    except subprocess.CalledProcessError:
        return None


def _numstat(repo, rev, start, end):
    """(docs lines, all lines) added + deleted by the commits with committer time in [start, end]."""
    raw = _git(repo, "log", "--numstat", "--no-renames", "--format=C\x1f%ct",
               "--since=%s" % _utc(start - 86400, "%Y-%m-%dT%H:%M:%SZ"), rev)
    docs = total = 0
    inside = False
    for line in raw.splitlines():
        if line.startswith("C\x1f"):
            ct = int(line.split("\x1f")[1])
            inside = start <= ct <= end
            continue
        if not inside or not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue                                         # a binary row ("-\t-\tpath")
        n = int(parts[0]) + int(parts[1])
        total += n
        if parts[2].startswith("docs/"):
            docs += n
    return docs, total


def measure(repo, since, queue_log, backlog_md, rev="HEAD"):
    """The numbers of the page, measured at `rev` since the UTC day `since` (the module docstring defines each).

    `queue_log`: the lock's queue log, or None. `backlog_md`: a BACKLOG file to read, or None to read
    docs/BACKLOG.md as it stood at `rev`. Raises changelog.ShallowHistory on a shallow clone."""
    rows = changelog.entries(repo, rev)
    g = changelog._Graph(repo, rev)
    head = g.head
    end = g.commits[head]["ct"]
    start = _day_epoch(since)
    recent = {s: c for s, c in g.commits.items() if c["ct"] >= start}

    merges = [r["sha"] for r in rows if g.commits[r["sha"]]["ct"] >= start]
    per_day, narrow, broad = {}, [], []
    for sha in merges:
        c = g.commits[sha]
        day = _utc(c["ct"])
        per_day[day] = per_day.get(day, 0) + 1
        first = g.ancestors(c["parents"][0])
        side = set()
        for other in c["parents"][1:]:
            side |= g.ancestors(other)
        side -= first
        subjects = [g.commits[s]["subject"] for s in side]
        narrow.append(sum(1 for s in subjects if FIX_ROUND.search(s)))
        broad.append(sum(1 for s in subjects if FIX_ROUND_BROAD.search(s)))

    per_session = {}
    for c in recent.values():
        for url in SESSION.findall(c["body"]):
            per_session[url] = per_session.get(url, 0) + 1

    docs, total = _numstat(repo, head, end - WEEK, end)
    until = _utc(end, "%Y-%m-%dT%H:%M:%SZ")
    waits = ticket_waits(queue_log, since, until)
    if backlog_md is None:
        text = _backlog_at(repo, head)
    else:
        with open(backlog_md, "r", encoding="utf-8") as fh:
            text = fh.read()
    ages = issue_ages(text, _utc(end))

    return {
        "rev": head,
        "rev_time": until,
        "since": since,
        "commits": len(recent),
        "merges": len(merges),
        "git_merges": sum(1 for c in recent.values() if len(c["parents"]) > 1),
        "merges_per_day": dict(sorted(per_day.items())),
        "fix_rounds_per_merge": _histogram(narrow),
        "fix_rounds_per_merge_broad": _histogram(broad),
        "again_subjects": sum(1 for c in recent.values() if AGAIN in c["subject"].lower()),
        "churn_7d_docs": docs,
        "churn_7d_all": total,
        "window_7d": _utc(end - WEEK, "%Y-%m-%dT%H:%M:%SZ"),
        "docs_share_of_churn_7d": (docs / total) if total else None,
        "queue_log_found": waits is not None,
        "tickets": len(waits or []),
        "median_ticket_wait_s": _median(waits or []),
        "open_issues_dated": len(ages or []),
        "open_issue_age_days": _median(ages or []),
        "sessions": len(per_session),
        "commits_per_session": dict(sorted(per_session.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def _pct(n, d):
    return "%.1f %%" % (100.0 * n / d) if d else "n/a"


def _rounds(hist, n):
    parts = ["%d: %d (%s)" % (k, v, _pct(v, n)) for k, v in hist.items()]
    at_most_one = sum(v for k, v in hist.items() if k <= 1)
    return "%s; none: %s, at most one: %s" % ("; ".join(parts) or "no merges", _pct(hist.get(0, 0), n),
                                              _pct(at_most_one, n))


def render(m):
    """The page, from measure()'s dict alone."""
    rev, short, since = m["rev"], m["rev"][:8], m["since"]
    s = "--since=%sT00:00:00Z" % since
    n = m["merges"]
    days = m["merges_per_day"]
    share = m["docs_share_of_churn_7d"]
    counts = sorted(m["commits_per_session"].values(), reverse=True)

    if m["median_ticket_wait_s"] is None:
        why = ("the queue log was not found" if not m["queue_log_found"] else
               "the queue log holds no TICKET line in the window")
        ticket = ("not measured: %s. Task W2 makes the lock write a `TICKET <id> waited <s>` line into "
                  "logs/loop_lock.queue.log at each grant; until then there is nothing to read" % why)
    else:
        ticket = "median %s s over %d tickets" % (m["median_ticket_wait_s"], m["tickets"])
    if m["open_issue_age_days"] is None:
        age = ("not measured: the open-issues table of %s at `%s` has no Opened column; the dates live on GitHub "
               "(`gh issue list --state open --json number,createdAt`), a network read this page does not make"
               % (BACKLOG, short))
    else:
        age = "median %s days over %d open issues" % (m["open_issue_age_days"], m["open_issues_dated"])

    lines = {
        "merges_per_day": (
            "%d merges on %d days (mean %.1f a merge day); `git log --merges` counts %d. Per day below"
            % (n, len(days), (float(n) / len(days)) if days else 0.0, m["git_merges"]),
            "`python -m tools_py.changelog --rev %s` (its merges, changelog.entries()), by UTC committer day; "
            "cross-check: `TZ=UTC git log --merges %s --date=format-local:%%F --format=%%cd %s | sort | uniq -c`"
            % (short, s, short)),
        "fix_rounds_per_merge": (
            "rounds: merges -- %s" % _rounds(m["fix_rounds_per_merge"], n),
            "`git log --format=%%s P1..P2 | grep -c -E '%s'` per merge with parents P1 P2 (note 03 section 2.2)"
            % FIX_ROUND.pattern),
        "fix_rounds_per_merge_broad": (
            "matches: merges -- %s (an upper bound: every fix(scope) commit counts)"
            % _rounds(m["fix_rounds_per_merge_broad"], n),
            "`git log --format=%%s P1..P2 | grep -c -E '%s'` per merge" % FIX_ROUND_BROAD.pattern),
        "again_subjects": (
            "%d of %d commits" % (m["again_subjects"], m["commits"]),
            "`git log %s --format=%%s %s | grep -ci -- ' again'`" % (s, short)),
        "docs_share_of_churn_7d": (
            ("%s: %d of %d lines added + deleted, %s to %s" % (
                _pct(m["churn_7d_docs"], m["churn_7d_all"]), m["churn_7d_docs"], m["churn_7d_all"],
                m["window_7d"], m["rev_time"])) if share is not None else "no lines changed in the window",
            "`git log --numstat --no-renames --since=%s --until=%s --format= %s | awk '$1 ~ /^[0-9]+$/ "
            "{t += $1 + $2} $3 ~ /^docs\\// {d += $1 + $2} END {print d, t}'`" % (m["window_7d"], m["rev_time"], short)),
        "median_ticket_wait_s": (
            ticket,
            "`grep -E 'TICKET [^ ]+ waited [0-9]+' logs/loop_lock.queue.log` (the main tree's), the median of the "
            "last field, lines stamped after %s or before %s left out" % (m["rev_time"], since)),
        "open_issue_age_days": (
            age,
            "`git show %s:%s`, the Opened column of section 1's table, days to %s" % (short, BACKLOG, m["rev_time"][:10])),
        "sessions": (
            "%d distinct Claude-Session trailers" % m["sessions"],
            "`git log %s --format=%%B %s | grep '^Claude-Session:' | sort -u | wc -l`" % (s, short)),
        "commits_per_session": (
            ("largest first: %s; median %s" % (", ".join(str(c) for c in counts), _median(counts)))
            if counts else "no session trailers",
            "`git log %s --format=%%B %s | grep '^Claude-Session:' | sort | uniq -c | sort -rn`" % (s, short)),
    }

    out = [
        "# Flow: how work moves through this repository",
        "",
        "> **Generated -- do not edit.** Written by `python -m tools_py.flow --since %s` (Sprint 14 M1, the review's "
        "F8) from the git history at the commit named below, the lock's queue log and `%s`. The methods are note "
        "03's (`%s`); each number names the command that reproduces it, and where the method differs from the "
        "note's the module docstring says how. Descriptive, not targets. `python -m tools_py.flow --check` exits 1 "
        "when this file is not a render of the commit it names; regenerate at the close." % (since, BACKLOG, NOTE03),
        "",
        "Rendered at commit `%s` (committer time %s), since %s (UTC days): %d commits, %d merges."
        % (rev, m["rev_time"], since, m["commits"], n),
        "",
        "## The numbers",
        "",
    ]
    for key in NUMBERS:
        value, cmd = lines[key]
        out.append("- **%s**: %s -- command: %s" % (LABELS[key], value, cmd))
    out += ["", "## Merges per UTC day", "", "| day | merges |", "|---|---:|"]
    for day, count in days.items():
        out.append("| %s | %d |" % (day, count))
    return "\n".join(out) + "\n"


def page_header(text):
    """(rev, since) the page names, or None."""
    m = HEADER.search(text or "")
    return (m.group(1), m.group(2)) if m else None


def default_queue_log(repo):
    """logs/loop_lock.queue.log in the main tree (the lock lives there; an agent worktree has no logs/)."""
    try:
        common = _git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
        return os.path.join(os.path.dirname(common), "logs", "loop_lock.queue.log")
    except subprocess.CalledProcessError:
        return os.path.join(repo, "logs", "loop_lock.queue.log")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m tools_py.flow", description=__doc__.split("\n")[0])
    ap.add_argument("--since", default=None, help="the first UTC day counted (default: the page's, else %s)"
                    % DEFAULT_SINCE)
    ap.add_argument("--check", action="store_true", help="exit 1 when the page is not a render of the commit it names")
    ap.add_argument("--rev", default=None, help="the commit measured (default: HEAD; with --check, the page's)")
    ap.add_argument("--queue-log", default=None, help="the lock's queue log (default: the main tree's logs/)")
    ap.add_argument("--backlog", default=None, help="a BACKLOG file (default: docs/BACKLOG.md at the commit)")
    ap.add_argument("--repo", default=ROOT, help="the repository to read (default: this one)")
    ap.add_argument("--out", default=None, help="the page to write or check (default: <repo>/%s)" % PAGE)
    args = ap.parse_args(argv)
    target = args.out or os.path.join(args.repo, PAGE)
    current = None
    if os.path.isfile(target):
        with open(target, "r", encoding="utf-8") as fh:
            current = fh.read()
    named = page_header(current)
    if args.check and current is None:
        print("flow: %s is missing; run python -m tools_py.flow" % target)
        return 1
    if args.check and named is None and not (args.rev and args.since):
        print("flow: %s is stale (it names no commit); run python -m tools_py.flow" % target)
        return 1
    since = args.since or (named[1] if named else DEFAULT_SINCE)
    rev = args.rev or (named[0] if args.check else "HEAD")
    queue = args.queue_log or default_queue_log(args.repo)
    try:
        m = measure(args.repo, since, queue, args.backlog, rev=rev)
    except changelog.ShallowHistory as exc:
        print("flow: refused -- %s" % exc)
        return 2
    except subprocess.CalledProcessError as exc:
        print("flow: git failed on %s (%s); run python -m tools_py.flow" % (rev, exc))
        return 1
    fresh = render(m)
    if args.check:
        if current == fresh:
            ahead = _git(args.repo, "rev-list", "--count", "%s..HEAD" % m["rev"]).strip()
            print("flow: %s is current for %s (HEAD is %s commits past it; the close regenerates)"
                  % (target, m["rev"][:8], ahead))
            return 0
        diff = list(difflib.unified_diff(current.split("\n"), fresh.split("\n"), "on disk", "fresh render",
                                         lineterm=""))
        sys.stdout.write("\n".join(diff[:40]) + "\n")
        print("flow: %s is stale; run python -m tools_py.flow" % target)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(fresh)
    print("flow: wrote %s (%s since %s: %d merges, %d sessions)" % (target, m["rev"][:8], since, m["merges"],
                                                                     m["sessions"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
