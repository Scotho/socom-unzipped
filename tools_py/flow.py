"""The flow page: how work moves through this repository, measured from git (Sprint 14 Task M1; the review's F8).

Run: python -m tools_py.flow [--since DATE] [--check] [--usage] [--rev REV] [--queue-log PATH]
                             [--backlog PATH] [--repo PATH] [--out FILE]

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
                        2.2's `review round|fix round` (case-sensitive, as its grep -E was). Unlike note 03, a round
                        counts ONCE, at the first merge (committer-time order, the merges before --since included)
                        whose range brings it in: an integration merge (a sprint into main, main into an agent
                        branch) counts only the rounds no earlier merge brought. And only a non-merge commit that is
                        not the controller's plan record (`docs(sprint-N): ...`, PLAN_RECORD) is a round: a merge
                        subject ("review PASS after one fix round") and a plan-Log commit report a round, they are
                        not one (is_round()).
  fix_rounds_per_merge_broad   the same with FIX_ROUND_BROAD, `review round|fix round|fix\\(|review`, the Task M1
                        brief's wider pattern: it also counts every `fix(scope):` commit and every subject naming a
                        review, so it is an upper bound, not a round count. The same once-only rule.
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
                        appended log does not make an old page stale; an unstamped line cannot be placed, so it is
                        treated as after the rendered commit: left out, and counted on the page. None when the log
                        is missing or holds no such line: the page says "not measured" and why.
  open_issue_age_days   the median age, in days at the rendered commit, of the open issues in `docs/BACKLOG.md` as it
                        stood at that commit, read from an "Opened" column of its open-issues table. None when the
                        table has no such column (it has none on 2026-09-26: the dates live on GitHub, and this page
                        makes no network read).
  sessions              the distinct `Claude-Session:` trailer values in the bodies of the commits since --since
                        (note 03 section 1.3's `grep '^Claude-Session:' | sort -u`).
  commits_per_session   {session: commits}; the page shows the counts, largest first, not the URLs.
  tokens                (Task M2) the token spend, local only. When the environment variable SOCOM_CLAUDE_TRANSCRIPTS
                        names a directory, its transcripts are read and the `message.usage` fields summed per session:
                        input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens and a message
                        count, the session's own spend and its agents' apart, and a total. Claude Code's layout, under
                        ~/.claude/projects/<project-key>/: the session's own transcript is `<stem>.jsonl` at the top
                        level; its agents' are `<stem>/subagents/*.jsonl` (every `.jsonl` under `<stem>/` counts as
                        agents', a folder with no top-level file of its name included); a line with `isSidechain:
                        true` counts as agents' wherever it is. A message id written on several lines of a transcript
                        counts once, by its LAST line: Claude Code writes a streamed partial first, and the output count
                        only grows (the M2 review measured a 6x undercount keeping the first). A message whose (last)
                        line is stamped before --since or after the rendered commit is left out, as the queue log's
                        are, and the page states that window, so a transcript still being written does not make the
                        page stale; a usage line with no timestamp cannot be placed and is left out too.
                        A line that is not JSON is skipped and counted. The page holds ONLY the sums, keyed by the
                        transcript's file stem (a transcript id: it need not equal a commit's Claude-Session trailer
                        id, and no mapping is assumed), and the directory's last component, named as such: never a
                        line of content, never a path, never an agent transcript's file name. Unset, the page says
                        "not measured" and why; set to a missing directory or one holding no transcript, it says that.
                        `--usage` prints the token lines alone and writes nothing.

"Since" is a UTC calendar day and every commit is placed by its committer time (note 03 used the author date).

Held to the commit it names, the variant Task S1 chose for a page that depends on git history (the changelog's
suite test renders at the commit that last wrote the page). The flow page counts commits, so it can never be a render
of the commit that writes it -- that commit is one more -- and so it names the commit it was rendered at, and
`--check` re-renders there (with the --since the page names) unless --rev is given: `--check` asks "is this file what
the tool says about that commit", and `--check --rev HEAD` asks "is it current". Regenerate at the close. On a shallow
clone the command refuses with exit 2 (`changelog.ShallowHistory`), as the changelog does. The ticket-wait and token
lines come from files local to one machine, so `--check` holds them only where those files are; the suite's page test
compares held() -- the page without them.
"""
import argparse
import calendar
import datetime
import difflib
import json
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
PLAN_RECORD = re.compile(r"^docs\(sprint-[0-9]+\)")    # [0-9], not \d: the page prints it for grep -E
ROUND_RULE = ("A round counts once, at the first merge whose range brings it in; merge commits and docs(sprint-N) "
              "plan commits are not rounds; rounds committed straight on a sprint branch count at the sprint's merge "
              "into main (Sprint 11's seven at PR #49)")
AGAIN = " again"
SESSION = re.compile(r"^Claude-Session:\s*(\S+)", re.M)
TICKET = re.compile(r"^(?:(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s+)?.*?\bTICKET\s+(\S+)\s+waited\s+(\d+)\b")
DATE = re.compile(r"\b(\d{4}-\d\d-\d\d)\b")
HEADER = re.compile(r"^Rendered at commit `([0-9a-f]{40})`.*? since (\d{4}-\d\d-\d\d)\b", re.M)
WEEK = 7 * 86400
TRANSCRIPTS_VAR = "SOCOM_CLAUDE_TRANSCRIPTS"
USAGE_FIELDS = (("input", "input_tokens"), ("output", "output_tokens"), ("cache_read", "cache_read_input_tokens"),
                ("cache_creation", "cache_creation_input_tokens"))
TOKENS_SECTION = "## Tokens per transcript"

NUMBERS = ("merges_per_day", "fix_rounds_per_merge", "fix_rounds_per_merge_broad", "again_subjects",
           "docs_share_of_churn_7d", "median_ticket_wait_s", "open_issue_age_days", "sessions",
           "commits_per_session", "tokens")
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
    "tokens": "token spend",
}
LOCAL_ONLY = ("median_ticket_wait_s", "tokens")    # lines from files on one machine: held() leaves them out


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


def is_round(commit, pattern):
    """A fix round: a non-merge commit whose subject matches `pattern`, not the controller's plan record
    (`docs(sprint-N): ...`). A merge subject ("review PASS after one fix round") and a plan-Log commit report a
    round; they are not one, and counting them would count the round twice."""
    if len(commit["parents"]) > 1 or PLAN_RECORD.match(commit["subject"]):
        return False
    return bool(pattern.search(commit["subject"]))


def ticket_waits(path, since, until_stamp):
    """(waits, unstamped): the waits (seconds) of the queue log's stamped TICKET lines within [since, until_stamp],
    and the count of unstamped TICKET lines, which are left out -- a line with no time cannot be placed before
    the rendered commit, so it is treated as after it. (None, 0) when the log is missing."""
    if not path or not os.path.isfile(path):
        return None, 0
    waits, unstamped = [], 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = TICKET.match(line.strip())
            if not m:
                continue
            stamp = m.group(1)
            if not stamp:
                unstamped += 1
                continue
            if stamp > until_stamp or stamp[:10] < since:
                continue
            waits.append(int(m.group(3)))
    return waits, unstamped


def _zero():
    return dict([("messages", 0)] + [(k, 0) for k, _ in USAGE_FIELDS])


def _transcript_files(directory):
    """{stem: [(path, is_agents_file)]}: each top-level `<stem>.jsonl` (the session's own transcript) and every
    `.jsonl` anywhere under a top-level `<stem>/` folder (its agents': Claude Code writes `<stem>/subagents/*.jsonl`),
    a folder with no top-level file of its name included. Paths stay in this module; the page gets stems."""
    found = {}
    for entry in sorted(os.listdir(directory)):
        path = os.path.join(directory, entry)
        if entry.endswith(".jsonl") and os.path.isfile(path):
            found.setdefault(entry[:-len(".jsonl")], []).append((path, False))
        elif os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs.sort()
                for f in sorted(files):
                    if f.endswith(".jsonl"):
                        found.setdefault(entry, []).append((os.path.join(root, f), True))
    return found


def _read_usage(path):
    """(entries, malformed): the usage lines of one transcript as [(timestamp or None, is_sidechain, counts)], one
    per message id -- the LAST line of that id, since Claude Code writes a streamed partial first and the output
    count only grows -- and the count of lines that are not a JSON object or carry a non-numeric usage."""
    by_id, entries, malformed = {}, [], 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    raise ValueError("not an object")
                msg = obj.get("message")
                usage = msg.get("usage") if isinstance(msg, dict) else None
                if not isinstance(usage, dict):
                    continue
                counts = [(k, int(usage.get(field) or 0)) for k, field in USAGE_FIELDS]
            except (ValueError, TypeError, AttributeError):
                malformed += 1
                continue
            stamp = obj.get("timestamp")
            entry = (stamp if isinstance(stamp, str) and len(stamp) >= 19 else None, bool(obj.get("isSidechain")),
                     counts)
            mid = msg.get("id")
            if mid is None:
                entries.append(entry)
            elif mid in by_id:
                entries[by_id[mid]] = entry
            else:
                by_id[mid] = len(entries)
                entries.append(entry)
    return entries, malformed


def transcript_usage(directory, since, until_stamp):
    """The token sums of the transcripts in `directory` (_transcript_files()), their messages stamped within
    [since, until_stamp] (the module docstring's "tokens"). Only numbers leave this function, and the directory's
    last component: {"state": "unset"|"missing"|"empty"|"measured", "name", "until", "sessions": {stem: {"main":
    sums, "agents": sums}}, "total", "agents", "files", "agent_files", "malformed", "outside", "unplaced"}."""
    if not directory:
        return {"state": "unset"}
    name = os.path.basename(os.path.normpath(directory))
    if not os.path.isdir(directory):
        return {"state": "missing", "name": name}
    found = _transcript_files(directory)
    if not found:
        return {"state": "empty", "name": name}
    sessions, total, agents = {}, _zero(), _zero()
    files = agent_files = malformed = outside = unplaced = 0
    for stem, paths in sorted(found.items()):
        sums = {"main": _zero(), "agents": _zero()}
        for path, agents_file in paths:
            files += 1
            agent_files += agents_file
            entries, bad = _read_usage(path)
            malformed += bad
            for stamp, sidechain, counts in entries:
                if stamp is None:
                    unplaced += 1
                    continue
                stamp = stamp[:19] + "Z"
                if stamp > until_stamp or stamp[:10] < since:
                    outside += 1
                    continue
                who = "agents" if agents_file or sidechain else "main"
                for bucket in (sums[who], total) + ((agents,) if who == "agents" else ()):
                    bucket["messages"] += 1
                    for k, n in counts:
                        bucket[k] += n
        sessions[stem] = sums
    return {"state": "measured", "name": name, "since": since, "until": until_stamp, "sessions": sessions,
            "total": total, "agents": agents, "files": files, "agent_files": agent_files, "malformed": malformed,
            "outside": outside, "unplaced": unplaced}


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


def measure(repo, since, queue_log, backlog_md, rev="HEAD", transcripts=None):
    """The numbers of the page, measured at `rev` since the UTC day `since` (the module docstring defines each).

    `queue_log`: the lock's queue log, or None. `backlog_md`: a BACKLOG file to read, or None to read
    docs/BACKLOG.md as it stood at `rev`. `transcripts`: the directory SOCOM_CLAUDE_TRANSCRIPTS names, or None
    (unset: the tokens are not measured). Raises changelog.ShallowHistory on a shallow clone."""
    rows = changelog.entries(repo, rev)
    g = changelog._Graph(repo, rev)
    head = g.head
    end = g.commits[head]["ct"]
    start = _day_epoch(since)
    recent = {s: c for s, c in g.commits.items() if c["ct"] >= start}

    # Oldest first, the merges before --since included, so a round an earlier merge brought in is never
    # counted again by a later (integration) merge whose range holds it too.
    ordered = sorted((r["sha"] for r in rows), key=lambda s: (g.commits[s]["ct"], s))
    merges = [s for s in ordered if g.commits[s]["ct"] >= start]
    per_day, narrow, broad = {}, [], []
    counted = {FIX_ROUND: set(), FIX_ROUND_BROAD: set()}
    for sha in ordered:
        c = g.commits[sha]
        first = g.ancestors(c["parents"][0])
        side = set()
        for other in c["parents"][1:]:
            side |= g.ancestors(other)
        side -= first
        found = {}
        for pat, seen in counted.items():
            new = set(s for s in side if s not in seen and is_round(g.commits[s], pat))
            seen |= new
            found[pat] = len(new)
        if c["ct"] < start:
            continue
        day = _utc(c["ct"])
        per_day[day] = per_day.get(day, 0) + 1
        narrow.append(found[FIX_ROUND])
        broad.append(found[FIX_ROUND_BROAD])

    per_session = {}
    for c in recent.values():
        for url in SESSION.findall(c["body"]):
            per_session[url] = per_session.get(url, 0) + 1

    docs, total = _numstat(repo, head, end - WEEK, end)
    until = _utc(end, "%Y-%m-%dT%H:%M:%SZ")
    waits, unstamped = ticket_waits(queue_log, since, until)
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
        "tickets_unstamped": unstamped,
        "median_ticket_wait_s": _median(waits or []),
        "open_issues_dated": len(ages or []),
        "open_issue_age_days": _median(ages or []),
        "sessions": len(per_session),
        "commits_per_session": dict(sorted(per_session.items(), key=lambda kv: (-kv[1], kv[0]))),
        "tokens": transcript_usage(transcripts, since, until),
    }


def _pct(n, d):
    return "%.1f %%" % (100.0 * n / d) if d else "n/a"


def _rounds(hist, n):
    parts = ["%d: %d (%s)" % (k, v, _pct(v, n)) for k, v in hist.items()]
    at_most_one = sum(v for k, v in hist.items() if k <= 1)
    return "%s; none: %s, at most one: %s" % ("; ".join(parts) or "no merges", _pct(hist.get(0, 0), n),
                                              _pct(at_most_one, n))


def _sums(b):
    return "input %d, output %d, cache-read %d, cache-creation %d tokens over %s" % (
        b["input"], b["output"], b["cache_read"], b["cache_creation"], _plural(b["messages"], "message"))


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def token_lines(t):
    """(value, command, table lines) of the tokens number, from transcript_usage()'s dict: sums only."""
    cmd = ("`%s=<the transcripts directory> python -m tools_py.flow --usage` (Claude Code's are under "
           "~/.claude/projects/<project-key>/), the `message.usage` fields of each `.jsonl` summed" % TRANSCRIPTS_VAR)
    if t["state"] == "unset":
        return ("not measured: %s is not set. The transcripts are local to the machine that ran the sessions, so "
                "the page sums them only when the controller names their directory" % TRANSCRIPTS_VAR), cmd, []
    if t["state"] == "missing":
        return "not measured: %s names `%s`, which is not a directory" % (TRANSCRIPTS_VAR, t["name"]), cmd, []
    if t["state"] == "empty":
        return ("not measured: %s names `%s`, which holds no .jsonl transcript" % (TRANSCRIPTS_VAR, t["name"]),
                cmd, [])
    left = ["messages stamped before %s or after %s left out (%d)" % (t["since"], t["until"], t["outside"])]
    if t["unplaced"]:
        left.append("%s with no timestamp left out" % _plural(t["unplaced"], "message"))
    if t["malformed"]:
        left.append("%s skipped" % _plural(t["malformed"], "malformed line"))
    value = ("sums over %s (%s, %d of them agents') in the directory `%s` (the directory's name only, its last "
             "component; the directory is read only by name: neither its path nor a line of content reaches the "
             "page, only these sums) -- total: %s; of which agents (subagent transcripts and sidechain lines): %s; "
             "%s. A repeated message id counts its last line. Per session below; the ids are transcript ids (file "
             "stems), not Claude-Session trailer ids" % (
                 _plural(len(t["sessions"]), "session"), _plural(t["files"], "transcript file"), t["agent_files"],
                 t["name"], _sums(t["total"]), _sums(t["agents"]), ", ".join(left)))
    table = ["", TOKENS_SECTION, "",
             "Sums of `message.usage` per transcript id; \"session\" is the session's own transcript, \"agents\" "
             "the transcripts in its folder and its sidechain lines.", "",
             "| transcript id | whose | messages | input | output | cache-read | cache-creation |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for stem, sums in sorted(t["sessions"].items()):
        for who, label in (("main", "session"), ("agents", "agents")):
            b = sums[who]
            if who == "agents" and not b["messages"]:
                continue
            table.append("| %s | %s | %d | %d | %d | %d | %d |" % (
                stem, label, b["messages"], b["input"], b["output"], b["cache_read"], b["cache_creation"]))
    return value, cmd, table


def held(text):
    """The page less the lines read from files local to one machine (LOCAL_ONLY's numbers and the tokens table):
    what the suite can hold on any clone."""
    out = []
    for line in (text or "").splitlines():
        if line == TOKENS_SECTION:
            break
        if any(line.startswith("- **%s**" % LABELS[k]) for k in LOCAL_ONLY):
            continue
        out.append(line)
    while out and not out[-1]:
        out.pop()
    return out


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
    if m.get("tickets_unstamped"):
        ticket += " (%d unstamped TICKET lines left out: no time, so not placed before the commit)" % (
            m["tickets_unstamped"])
    if m["open_issue_age_days"] is None:
        age = ("not measured: the open-issues table of %s at `%s` has no Opened column; the dates live on GitHub "
               "(`gh issue list --state open --json number,createdAt`), a network read this page does not make"
               % (BACKLOG, short))
    else:
        age = "median %s days over %d open issues" % (m["open_issue_age_days"], m["open_issues_dated"])
    tokens = token_lines(m["tokens"])

    lines = {
        "merges_per_day": (
            "%d merges on %d days (mean %.1f a merge day); `git log --merges` counts %d. Per day below"
            % (n, len(days), (float(n) / len(days)) if days else 0.0, m["git_merges"]),
            "`python -m tools_py.changelog --rev %s` (its merges, changelog.entries()), by UTC committer day; "
            "cross-check: `TZ=UTC git log --merges %s --date=format-local:%%F --format=%%cd %s | sort | uniq -c`"
            % (short, s, short)),
        "fix_rounds_per_merge": (
            "rounds: merges -- %s. %s" % (_rounds(m["fix_rounds_per_merge"], n), ROUND_RULE),
            "`git log --no-merges --format=%%s P1..P2 | grep -v -E '%s' | grep -c -E '%s'` per merge with parents "
            "P1 P2, oldest first, less the commits an earlier merge counted (note 03 section 2.2, deduplicated)"
            % (PLAN_RECORD.pattern, FIX_ROUND.pattern)),
        "fix_rounds_per_merge_broad": (
            "matches: merges -- %s (an upper bound: every fix(scope) commit counts). The same rule"
            % _rounds(m["fix_rounds_per_merge_broad"], n),
            "`git log --no-merges --format=%%s P1..P2 | grep -v -E '%s' | grep -c -E '%s'` per merge, oldest first, "
            "less the commits an earlier merge counted" % (PLAN_RECORD.pattern, FIX_ROUND_BROAD.pattern)),
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
            "last field, unstamped lines and lines stamped after %s or before %s left out" % (m["rev_time"], since)),
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
        "tokens": tokens[:2],
    }

    out = [
        "# Flow: how work moves through this repository",
        "",
        "> **Generated -- do not edit.** Written by `python -m tools_py.flow --since %s` (Sprint 14 M1, the review's "
        "F8; tokens M2) from the git history at the commit named below, the lock's queue log, `%s` and, when "
        "%s names a directory, the sums of its transcripts' usage fields. The methods are note 03's (`%s`); each "
        "number names the command that reproduces it, and where the method differs from the note's the module "
        "docstring says how. Descriptive, not targets. `python -m tools_py.flow --check` exits 1 "
        "when this file is not a render of the commit it names; regenerate at the close." % (
            since, BACKLOG, TRANSCRIPTS_VAR, NOTE03),
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
    out += tokens[2]                                    # last, so held() can cut the page there
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
    ap.add_argument("--usage", action="store_true", help="print the token lines alone (from $%s) and write nothing"
                    % TRANSCRIPTS_VAR)
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
        m = measure(args.repo, since, queue, args.backlog, rev=rev,
                    transcripts=os.environ.get(TRANSCRIPTS_VAR) or None)
    except changelog.ShallowHistory as exc:
        print("flow: refused -- %s" % exc)
        return 2
    except subprocess.CalledProcessError as exc:
        print("flow: git failed on %s (%s); run python -m tools_py.flow" % (rev, exc))
        return 1
    if args.usage:
        value, cmd, table = token_lines(m["tokens"])
        print("\n".join(["- **%s**: %s -- command: %s" % (LABELS["tokens"], value, cmd)] + table))
        return 0
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
