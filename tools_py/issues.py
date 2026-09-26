"""The known-issue stack on GitHub issues, held to the live documents.

The conventions are docs/GIT_STRATEGY.md section 7 ("Issues"); the sprint-close review that reads the stack is
docs/DOC_MAINTENANCE.md section 7. This module is the part of both that can be made to fail.

    python -m tools_py.issues skeleton                      # the body every known issue is written into
    python -m tools_py.issues check-body FILE               # the body's shape, before gh ever sees it
    python -m tools_py.issues open --title "..." --body-file FILE --area render [--milestone "Sprint 11"]
    python -m tools_py.issues close 12 --artefact "gate s11_x_gate 3/3, 1a2b3c4"
    python -m tools_py.issues close 12 --not-planned --reason "R260: retracted, KNOWN section 3"
    python -m tools_py.issues audit [--stale-since 2026-09-23] [--json FILE]
    python -m tools_py.issues backlog [--json FILE] [--out docs/BACKLOG.md] [--check [--offline]]
    python -m tools_py.issues carry 25 --comment "not in Sprint 14's plan" [--milestone "Sprint 14"] [--dry-run]
    python -m tools_py.issues milestone close "Sprint 13" --next "Sprint 14" [--dry-run]
    python -m tools_py.issues tally --since 2026-09-25 [--json FILE]
    python -m tools_py.issues labels                        # the label set, read from scripts/github_labels.sh

`open` and `close` call `gh`; `audit` calls it once (`gh issue list --json`) unless `--json FILE` hands it a saved
listing -- the offline path, and the one tools_py/tests/test_issues.py drives end to end. `backlog`, `tally` and
`milestone close` read the same listing (`milestone close` also `--milestones-json`), and `carry` a saved
`gh issue view --json` the same way.

The carry (docs/DOC_MAINTENANCE.md section 7 steps 5 and 7, R267) is `carry` (the `carried` label, a comment that
begins "Carried ", the milestone moved or removed -- refused once the issue has two carry comments, because an issue
carried twice is the owner's question), `milestone close` (refused while an open issue is left in it), `tally` (the
opened/closed/carried sentence) and `backlog`, which writes docs/BACKLOG.md from the open issues and the tracked
list docs/backlog_ruled_out.txt; `backlog --check` exits 1 on a stale file. Nothing here deletes
anything: an issue is closed with a comment that names its artefact, never deleted, because the row that cited it
and the commit that closed it still point at it.

What the audit holds the stack to (exit 1 on any of the first five):
  1. every `issue #N` cited as open in a live document exists, is open, and carries the `known-issue` label;
  2. a citation written as `issue #N (closed)` names an issue that really is closed;
  3. every open `known-issue` is cited by at least one live document -- an orphan has no row that owns it;
  4. every open `known-issue` carries exactly one area label;
  5. every open `known-issue` body still has its four sections (What happens, Evidence, Where it is written,
     Closing bar) -- the closing bar is what the closing comment must answer;
  and reports, without failing: open issues with no milestone (the backlog), issues untouched since `--stale-since`,
  a close marked completed whose last comment is not the tool's own "Closing bar met" line (an owner's close, or a
  close by hand -- the review reads it, never reopens it unasked), and every docs/KNOWN.md section 2 row and every
  live hazard in docs/HAZARDS.md (KNOWN's old section 4; a headline saying HAZARD or Open:) that is neither cited nor settled nor annotated
  `no issue: ...`, for the reviewer to rule on one by one.

The live documents are docs/DOC_MAINTENANCE.md section 3's class-L rows, read through tools_py.docmaint -- never a
list kept here, which would drift the day the registry changes.

A body is also run through the leak check's text rules on the `artifact` surface (tools_py/release/leakrules.py):
an address, a token or a key typed into a public issue is refused with the rule's name, the same way it would be
refused at the commit.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

from tools_py import docmaint
from tools_py.release import leakcheck
from tools_py.release import leakrules

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.environ.get("GITHUB_ISSUES_REPO", "Scotho/socom-unzipped")

STACK_LABEL = "known-issue"
CARRIED_LABEL = "carried"
# One per issue. The names are scripts/github_labels.sh's area block; test_issues.py holds the two together.
AREAS = ("audio", "render", "online", "launcher", "input", "linux", "packaging", "docs",
         "harness", "server", "build", "recomp")

KNOWN = "docs/KNOWN.md"
# R270 (Sprint 14 I5): KNOWN's section 4 moved here, one `## <area>` heading per area; every bullet under any
# heading of this file is read as a section 4 bullet was.
HAZARDS = "docs/HAZARDS.md"
# R267: the carry's one home, generated, and the tracked list of rows ruled not to be issues that it renders.
BACKLOG = "docs/BACKLOG.md"
RULED_OUT_LIST = "docs/backlog_ruled_out.txt"
RULED_OUT_HEADING = "## 2. Ruled not an issue"
RULING_FIELD = re.compile(r"^(R\d+|no issue)$")
# What a carry comment begins with -- `carry` writes "Carried from X to Y: ...", and the hand carries of the
# Sprint 11 close and R266 were written "Carried at the Sprint 11 close ..." and "Carried once into Sprint 13 ...".
CARRY_COMMENT = "Carried "
# DOC_MAINTENANCE section 7 step 5: an issue carried twice is the owner's question, not a third carry.
CARRY_LIMIT = 2
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# `issue #12` is the citation form; `issue #12 (closed)` is what it becomes when the issue closes and the row is
# kept as a record. A bare `#244` is not a citation -- it is how the tree names an upstream pull request.
CITATION = re.compile(r"\bissue #(\d+)(\s*\(closed\))?", re.I)
# A row the review ruled out says so at its end: `no issue: the owner's ears`, `no issue: settled 2026-09-22`.
RULED_OUT = re.compile(r"\bno issue:", re.I)
SETTLED = re.compile(r"\b(SETTLED|FIXED|CLOSED|SUPERSEDED|RETRACTED|WITHDRAWN)\b", re.I)
# A section 4 bullet is asked about only when its headline says it is live; the rest of section 4 is lessons.
LIVE_HAZARD = re.compile(r"^(HAZARD\b|Open:)")          # at the headline's start, upper-case, as KNOWN writes them
# What `close --artefact` writes; a completed close without it was closed by hand and is noted for the review.
CLOSING_COMMENT = "Closing bar met:"

SECTIONS = ("## What happens", "## Evidence", "## Where it is written", "## Closing bar")
BR_ID = re.compile(r"BR-\d{8}-[0-9a-z]{6}", re.I)
BR_SENTENCE = re.compile(r"^Reported through the launcher as BR-\d{8}-[0-9a-z]{6}\.$", re.I | re.M)
HOME_PATH = re.compile(r"(?:[A-Za-z]:\\Users\\|/home/[A-Za-z0-9_.-]+/|/Users/[A-Za-z0-9_.-]+/)", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PLACEHOLDER = re.compile(r"^\s*<[^>]*>\s*$")

SKELETON = """Reported: <where this was first seen -- the docs/KNOWN.md row's date and section, a gate stamp, a log path; or, when it came from a launcher report, the sentence "Reported through the launcher as BR-YYYYMMDD-xxxxxx." and NOTHING else from the report>

## What happens
<the defect in one paragraph, in your own words: what is observed, on which build or commit, on which platform>

## Evidence
<the artefact that shows it: a path under logs/, a gate stamp, a test name, a commit hash, a research note. No artefact, no issue>

## Where it is written
<the docs/KNOWN.md row (its section and headline) and any plan, task or ruling that carries it. The row cites this issue back as `issue #N`>

## Closing bar
<the test, measurement or gate result that would show it fixed -- or the experiment that would retract it. The closing comment quotes this>

## Notes
<optional: candidates, what was tried, what is the owner's (docs/HUMAN_TASKS.md), what a contributor without a disc can do>
"""


# ----------------------------------------------------------------------------------------------------- the body

def sections_of(text):
    """{heading: body} for every `## ` heading in a body, in order; text before the first heading is under ''."""
    out = {}
    current = ""
    out[current] = []
    for line in text.splitlines():
        if line.startswith("## "):
            current = line.strip()
            out[current] = []
        else:
            out[current].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def leak_hits(text):
    """(rule, line) for every leak-check text rule that fires on the body, on the artifact surface, minus what
    tools_py/release/leak_allow.txt allows for the path `issue-body`."""
    rules = leakrules.text_rules(surface="artifact")
    hits, stats = [], leakcheck.new_stats()
    leakcheck.scan_text("issue-body", text, rules, hits, stats)
    allow = leakcheck.load_allow()
    return [(h.rule, h.line) for h in hits if not leakcheck.allowed(h, allow)]


def check_body(text):
    """Problems with an issue body, each a sentence; empty means the body may go to GitHub."""
    problems = []
    parts = sections_of(text)
    for heading in SECTIONS:
        if heading not in parts:
            problems.append("missing section %r" % heading)
        elif not parts[heading] or all(PLACEHOLDER.match(l) or not l.strip() for l in parts[heading].splitlines()):
            problems.append("section %r is empty or still the skeleton's placeholder" % heading)
    for i, line in enumerate(text.splitlines(), 1):
        if PLACEHOLDER.match(line):
            problems.append("line %d is a placeholder left from the skeleton" % i)
        if HOME_PATH.search(line):
            problems.append("line %d carries a home directory path -- scrub it to ~" % i)
        if EMAIL.search(line):
            problems.append("line %d carries an e-mail address -- nothing personal goes in a public issue" % i)
    for m in BR_ID.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line = text[line_start:(line_end if line_end != -1 else len(text))]
        if not BR_SENTENCE.match(line.strip()):
            problems.append("a BR- id appears outside the one permitted sentence "
                            "'Reported through the launcher as BR-....' -- nothing else crosses from a report")
    for rule, line in leak_hits(text):
        problems.append("line %d trips the leak check's %r rule -- an issue is public and permanent; if this is a "
                        "reviewed non-secret, record it in tools_py/release/leak_allow.txt for path issue-body"
                        % (line, rule))
    return problems


# ------------------------------------------------------------------------------------------------ the citations

def cited_issues(text):
    """{number: 'open'|'closed'} -- how the text cites each issue. 'open' wins when both forms appear."""
    cited = {}
    for m in CITATION.finditer(text):
        n = int(m.group(1))
        state = "closed" if m.group(2) else "open"
        if cited.get(n) != "open":
            cited[n] = state
    return cited


def _read(relpath):
    with open(os.path.join(ROOT, relpath), encoding="utf-8") as f:
        return f.read()


def live_docs():
    """The class-L documents of docs/DOC_MAINTENANCE.md section 3 -- the only ones that may say an issue is open.
    A plan or a research note is a snapshot and may cite a closed issue forever."""
    return tuple(docmaint.by_class("L"))


def live_citations():
    """{number: {'state': 'open'|'closed', 'where': [docs]}} over the live documents."""
    out = {}
    for doc in live_docs():
        path = os.path.join(ROOT, doc)
        if not os.path.isfile(path):
            continue
        for n, state in cited_issues(_read(doc)).items():
            entry = out.setdefault(n, {"state": "closed", "where": []})
            entry["where"].append(doc)
            if state == "open":
                entry["state"] = "open"
    return out


def _headline(line, opener):
    """The bold headline that starts a row or bullet; the line's remainder if the bold does not close on it."""
    rest = line[len(opener):]
    return rest.split("**", 1)[0].strip()


def known_rows_without_issue(text, hazards_file=False):
    """(section, headline) of every docs/KNOWN.md section 2 row and every live section 4 hazard (headline
    `HAZARD:` / `Open:`) that is neither citing an issue, nor settled -- in its headline or in a `> Superseded`
    blockquote under it -- nor annotated `no issue: ...`. A nested `  - ` sub-bullet is an entry of its own.
    With `hazards_file` the text is docs/HAZARDS.md: every `## <area>` heading is read as section 4 was, and a
    row's first field is the area instead of the section number."""
    rows = []
    section = None
    entry_lines = None            # the lines of the entry being gathered (a table row is one line; a bullet wraps)
    entry_section = None
    area = None

    def flush():
        if not entry_lines:
            return
        first = entry_lines[0].lstrip()
        whole = "\n".join(entry_lines)
        opener = "| **" if first.startswith("| **") else "- **"
        headline = _headline(first, opener)
        blockquote = "\n".join(l.strip() for l in entry_lines[1:] if l.strip().startswith(">"))
        if CITATION.search(whole) or RULED_OUT.search(whole) or headline.startswith("~~"):
            return
        if SETTLED.search(headline) or SETTLED.search(blockquote):
            return
        if entry_section == "4" and not LIVE_HAZARD.search(headline):
            return
        rows.append((area if hazards_file else entry_section, headline[:110]))

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            entry_lines = None
            if hazards_file:
                section, area = "4", line[3:].strip()
            else:
                section = line[3:].split(".", 1)[0].strip()
            continue
        if section == "2" and line.startswith("| **"):
            flush()
            entry_lines, entry_section = [line], "2"
        elif section == "4" and (line.startswith("- **") or line.startswith("  - **")):
            flush()
            entry_lines, entry_section = [line], "4"
        elif section == "4" and line.startswith("  - "):
            flush()                               # a sub-bullet with no bold headline: not an entry, not the parent's
            entry_lines = None
        elif entry_lines is not None and entry_section == "4" and line.startswith("  "):
            entry_lines.append(line)              # a wrapped bullet, or its `  > Superseded` blockquote
        else:
            flush()
            entry_lines = None
    flush()
    return rows


# ----------------------------------------------------------------------------------------------------- the audit

def normalise(issue):
    """One gh `issue list --json` record -> the flat shape the audit reads."""
    labels = issue.get("labels") or []
    labels = [l["name"] if isinstance(l, dict) else l for l in labels]
    milestone = issue.get("milestone")
    if isinstance(milestone, dict):
        milestone = milestone.get("title")
    comments = [(c.get("createdAt") or "", c.get("body") or "") if isinstance(c, dict) else ("", c or "")
                for c in (issue.get("comments") or [])]
    return {
        "number": int(issue["number"]),
        "state": str(issue.get("state", "")).upper(),
        "stateReason": str(issue.get("stateReason") or "").upper(),
        "title": issue.get("title", ""),
        "labels": labels,
        "milestone": milestone,
        "updatedAt": issue.get("updatedAt", ""),
        "createdAt": issue.get("createdAt") or "",
        "closedAt": issue.get("closedAt") or "",
        "body": issue.get("body") or "",
        "comments": comments,
        "lastComment": comments[-1][1] if comments else "",
    }


# ------------------------------------------------------------------------------------------------- the carry

def carry_comments(issue):
    """[(createdAt, body)] of the comments that record a carry: the tool's own and the hand-written ones of the
    Sprint 11 close and R266 all begin with the word `Carried`."""
    return [(when, body) for when, body in issue["comments"] if body.startswith(CARRY_COMMENT)]


def carried_count(issue):
    """How many sprint closes the issue has survived: its carry comments, or one when it bears the label with none
    (a carry recorded by the label alone)."""
    n = len(carry_comments(issue))
    if n == 0 and CARRIED_LABEL in issue["labels"]:
        return 1
    return n


def closing_bar_sentence(body):
    """The closing bar's first sentence, on one line -- what the backlog shows beside the issue."""
    text = " ".join(sections_of(body).get("## Closing bar", "").split())
    if text.startswith("- "):
        text = text[2:]
    # A sentence ends at . ! or ? outside an inline code span, followed by the end or a space and then anything
    # but a lower-case letter -- so `a ... b` in code, "sidecar... then" and "e. g." do not end it. Known edge: a
    # double-backtick span (``a ` b``) is read as three toggles, so a sentence could end inside it; no issue body
    # uses one, and the cost would only be a shorter first sentence.
    in_code = False
    for k, ch in enumerate(text):
        if ch == "`":
            in_code = not in_code
        elif ch in ".!?" and not in_code:
            rest = text[k + 1:]
            if not rest:
                return text
            if rest[0] == " " and not rest.lstrip()[:1].islower():
                return text[:k + 1]
    return text


def _cell(text):
    return (text or "").replace("|", r"\|").strip()


def ruled_out_rows(text=None):
    """The rows of docs/backlog_ruled_out.txt as dicts; ValueError with the line number on a malformed row."""
    if text is None:
        text = _read(RULED_OUT_LIST)
    rows, seen = [], set()
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [p.strip() for p in line.split(" | ")]
        if len(parts) != 4 or not all(parts):
            raise ValueError("%s line %d: want `<slug> | <ruling> | <bar or reason> | <where written>`, four "
                             "non-empty fields split by ' | '" % (RULED_OUT_LIST, i))
        slug, ruling, bar, where = parts
        if not RULING_FIELD.match(ruling):
            raise ValueError("%s line %d: the ruling field is %r -- an R-number (R265) or 'no issue'"
                             % (RULED_OUT_LIST, i, ruling))
        if slug in seen:
            raise ValueError("%s line %d: the slug %r is already a row" % (RULED_OUT_LIST, i, slug))
        seen.add(slug)
        rows.append({"slug": slug, "ruling": ruling, "bar": bar, "where": where})
    return rows


def render_head():
    return ("# Backlog: the carry in one place\n\n"
            "> **Generated -- do not edit.** Written by `python -m tools_py.issues backlog` from the open issues on "
            "GitHub and the tracked list `%s` (ruling R267). Change the issue, or the list, and regenerate; "
            "`python -m tools_py.issues backlog --check` exits 1 when this file is stale (`--offline` checks the "
            "ruled-out half without the network). The conventions are `docs/GIT_STRATEGY.md` section 7; the carry "
            "at a sprint close is `docs/DOC_MAINTENANCE.md` section 7 step 5, and an issue carried twice is the "
            "owner's question.\n" % RULED_OUT_LIST)


def render_issues(issues):
    stack = sorted((normalise(i) for i in issues), key=lambda i: i["number"])
    stack = [i for i in stack if i["state"] == "OPEN"]
    lines = ["", "## 1. Open issues", "",
             "%d open issues. *Carried* counts the sprint closes an issue has survived (its `Carried ...` comments, "
             "or one for the `carried` label alone); at 2 the next close asks the owner." % len(stack), "",
             "| Issue | Title | Area | Milestone | Carried | Closing bar (first sentence) |",
             "|---|---|---|---|---|---|"]
    for i in stack:
        areas = [l for l in i["labels"] if l in AREAS]
        lines.append("| #%d | %s | %s | %s | %d | %s |"
                     % (i["number"], _cell(i["title"]), ", ".join(areas) or "--", _cell(i["milestone"] or "backlog"),
                        carried_count(i), _cell(closing_bar_sentence(i["body"])) or "--"))
    return "\n".join(lines) + "\n"


def render_ruled_out(rows):
    lines = ["", RULED_OUT_HEADING, "",
             "%d rows. Each was ruled not to be an issue -- by a ruling, or `no issue` with its reason -- and keeps "
             "its bar here so the next review does not re-ask. Edit `%s`, never this table." % (len(rows),
                                                                                                 RULED_OUT_LIST), "",
             "| Item | Ruling | Bar or reason | Where it is written |",
             "|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s |" % (_cell(r["slug"]), _cell(r["ruling"]), _cell(r["bar"]),
                                               _cell(r["where"])))
    return "\n".join(lines) + "\n"


def render_backlog(issues, rows):
    return render_head() + render_issues(issues) + render_ruled_out(rows)


def audit(cited, issues, stale_since=None):
    """(problems, notes) for a stack; problems fail, notes are for the reviewer."""
    problems, notes = [], []
    by_number = {i["number"]: i for i in (normalise(x) for x in issues)}
    for n, entry in sorted(cited.items()):
        where = ", ".join(entry["where"])
        issue = by_number.get(n)
        if entry["state"] != "open":
            if issue is not None and issue["state"] == "OPEN":
                problems.append("issue #%d is cited as closed in %s but the issue is OPEN -- close it with its "
                                "artefact, or restore the citation to 'issue #%d'" % (n, where, n))
            continue
        if issue is None:
            problems.append("issue #%d is cited as open in %s but does not exist on the repository" % (n, where))
        elif issue["state"] != "OPEN":
            problems.append("issue #%d is cited as open in %s but is CLOSED -- settle the row, mark the citation "
                            "'issue #%d (closed)', or reopen the issue" % (n, where, n))
        elif STACK_LABEL not in issue["labels"]:
            problems.append("issue #%d is cited as a known issue in %s but does not carry the '%s' label"
                            % (n, where, STACK_LABEL))
    for n, issue in sorted(by_number.items()):
        if STACK_LABEL not in issue["labels"]:
            continue
        if issue["state"] == "CLOSED":
            if issue["stateReason"] == "COMPLETED" and not issue["lastComment"].startswith(CLOSING_COMMENT):
                notes.append("issue #%d is closed as completed but its last comment is not a '%s' line -- closed "
                             "by hand or by the owner; the review reads it (DOC_MAINTENANCE section 7 step 4): %s"
                             % (n, CLOSING_COMMENT, issue["title"][:60]))
            continue
        if issue["state"] != "OPEN":
            continue
        if n not in cited:
            problems.append("issue #%d (%s) is open on the stack but no live document cites it -- an orphan: "
                            "give it a row or close it with a reason" % (n, issue["title"][:60]))
        areas = [l for l in issue["labels"] if l in AREAS]
        if len(areas) != 1:
            problems.append("issue #%d carries %d area labels (%s); exactly one is the rule"
                            % (n, len(areas), ", ".join(areas) or "none"))
        missing = [h for h in SECTIONS if h not in sections_of(issue["body"])]
        if missing:
            problems.append("issue #%d's body lacks %s -- the skeleton's sections are the contract"
                            % (n, ", ".join(repr(h) for h in missing)))
        if not issue["milestone"]:
            notes.append("issue #%d has no milestone (backlog): %s" % (n, issue["title"][:60]))
        if stale_since and issue["updatedAt"] and issue["updatedAt"][:10] < stale_since:
            notes.append("issue #%d untouched since %s (before %s): %s"
                         % (n, issue["updatedAt"][:10], stale_since, issue["title"][:60]))
    return problems, notes


# ------------------------------------------------------------------------------------------------------- gh

def _gh(cmd):
    """Run one gh command; a missing gh is a sentence, not a traceback."""
    if not shutil.which("gh"):
        raise SystemExit("tools_py.issues: gh is not installed -- see https://cli.github.com "
                         "(the audit can run offline with --json FILE)")
    return subprocess.run(["gh"] + cmd, capture_output=True, text=True, encoding="utf-8")


def fetch_issues(repo=REPO):
    out = _gh(["issue", "list", "--repo", repo, "--state", "all", "--limit", "1000",
               "--json", "number,state,stateReason,title,labels,milestone,updatedAt,createdAt,closedAt,body,"
                         "comments"])
    if out.returncode != 0:
        raise SystemExit("gh issue list failed (exit %d): %s" % (out.returncode, out.stderr.strip()))
    return json.loads(out.stdout)


# ------------------------------------------------------------------------------------------------ the commands

def cmd_skeleton(_args):
    sys.stdout.write(SKELETON)
    return 0


def cmd_check_body(args):
    with open(args.file, encoding="utf-8") as f:
        problems = check_body(f.read())
    for p in problems:
        print("check-body: " + p)
    print("check-body: %s" % ("OK" if not problems else "%d problem(s)" % len(problems)))
    return 1 if problems else 0


def _print_cmd(cmd):
    print(" ".join(repr(c) if " " in c else c for c in cmd))


def cmd_open(args):
    if args.area not in AREAS:
        print("open: --area must be one of %s" % ", ".join(AREAS))
        return 2
    with open(args.body_file, encoding="utf-8") as f:
        body = f.read()
    problems = check_body(body)
    if problems:
        for p in problems:
            print("open: " + p)
        return 1
    labels = [STACK_LABEL, args.area] + list(args.label or [])
    cmd = ["issue", "create", "--repo", args.repo, "--title", args.title, "--body-file", args.body_file]
    for l in labels:
        cmd += ["--label", l]
    if args.milestone:
        cmd += ["--milestone", args.milestone]
    if args.dry_run:
        _print_cmd(["gh"] + cmd)
        return 0
    out = _gh(cmd)
    sys.stdout.write(out.stdout)
    sys.stderr.write(out.stderr)
    return out.returncode


def cmd_close(args):
    if args.not_planned:
        if not args.reason:
            print("close: --not-planned needs --reason (a ruling number, 'duplicate of #N', or the retraction)")
            return 2
        comment = "Closed as not planned: %s" % args.reason
        cmd = ["issue", "close", str(args.number), "--repo", args.repo, "--reason", "not planned",
               "--comment", comment]
    else:
        if not args.artefact:
            print("close: --artefact is required (the gate stamp, test name or commit that meets the closing bar)")
            return 2
        comment = "Closing bar met: %s" % args.artefact
        cmd = ["issue", "close", str(args.number), "--repo", args.repo, "--reason", "completed",
               "--comment", comment]
    if args.dry_run:
        _print_cmd(["gh"] + cmd)
        return 0
    out = _gh(cmd)
    sys.stdout.write(out.stdout)
    sys.stderr.write(out.stderr)
    return out.returncode


def check_comment(text):
    """Problems with a comment bound for a public issue: the body's line rules without its sections."""
    problems = []
    for i, line in enumerate(text.splitlines(), 1):
        if HOME_PATH.search(line):
            problems.append("line %d carries a home directory path -- scrub it to ~" % i)
        if EMAIL.search(line):
            problems.append("line %d carries an e-mail address -- nothing personal goes in a public issue" % i)
    for rule, line in leak_hits(text):
        problems.append("line %d trips the leak check's %r rule -- an issue comment is public and permanent"
                        % (line, rule))
    return problems


def fetch_issue(number, repo=REPO):
    out = _gh(["issue", "view", str(number), "--repo", repo, "--json",
               "number,state,title,labels,milestone,comments"])
    if out.returncode != 0:
        raise SystemExit("gh issue view %d failed (exit %d): %s" % (number, out.returncode, out.stderr.strip()))
    return json.loads(out.stdout)


def _one_issue(args):
    """The issue `carry` acts on: a saved `gh issue view --json` (or a listing holding it), else one gh call."""
    if not args.json:
        return normalise(fetch_issue(args.number, args.repo))
    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)
    for record in (data if isinstance(data, list) else [data]):
        if int(record["number"]) == args.number:
            return normalise(record)
    raise SystemExit("carry: issue #%d is not in %s" % (args.number, args.json))


def _run_all(cmds, dry_run):
    """Run gh commands in order, stopping at the first failure; with dry_run, print them."""
    for cmd in cmds:
        if dry_run:
            _print_cmd(["gh"] + cmd)
            continue
        out = _gh(cmd)
        sys.stdout.write(out.stdout)
        sys.stderr.write(out.stderr)
        if out.returncode != 0:
            return out.returncode
    return 0


def cmd_carry(args):
    comment = (args.comment or "").strip()
    if not comment:
        print("carry: --comment is required -- one sentence saying why it did not close")
        return 2
    problems = check_comment(comment)
    if problems:
        for p in problems:
            print("carry: " + p)
        return 1
    issue = _one_issue(args)
    if issue["state"] != "OPEN":
        print("carry: issue #%d is %s -- only an open issue is carried" % (args.number, issue["state"]))
        return 1
    if CARRIED_LABEL in issue["labels"] and not carry_comments(issue):
        # The label alone counts as one carry (carried_count), but once this tool added its comment the count
        # would read 1 again and a third carry could slip through. The earlier carry is written down first.
        print("carry: issue #%d bears the '%s' label alone, with no comment starting %r -- that earlier carry is "
              "recorded by the label alone and would be lost from the count. Write it down first (gh issue comment "
              "%d --body \"Carried at the Sprint N close: <why>\"), then carry again."
              % (args.number, CARRIED_LABEL, CARRY_COMMENT, args.number))
        return 1
    count = carried_count(issue)
    if count >= CARRY_LIMIT:
        print("carry: issue #%d has been carried twice already (%d carry comments) -- a third carry is not the "
              "loop's to make: it is the owner's question (docs/DOC_MAINTENANCE.md section 7 step 5), keep it or "
              "close it as not planned under a ruling. Put it in docs/HUMAN_TASKS.md." % (args.number, count))
        return 1
    source = issue["milestone"] or "the backlog"
    target = args.milestone or "the backlog"
    edit = ["issue", "edit", str(args.number), "--repo", args.repo, "--add-label", CARRIED_LABEL]
    edit += ["--milestone", args.milestone] if args.milestone else ["--remove-milestone"]
    body = "%sfrom %s to %s: %s" % (CARRY_COMMENT, source, target, comment)
    note = ["issue", "comment", str(args.number), "--repo", args.repo, "--body", body]
    # The comment first: if it fails, nothing is half-carried (no label and no moved milestone without a reason).
    code = _run_all([note, edit], args.dry_run)
    if code == 0 and not args.dry_run:
        print("carry: issue #%d carried from %s to %s (carry %d of %d)"
              % (args.number, source, target, count + 1, CARRY_LIMIT))
    return code


def fetch_milestones(repo=REPO):
    out = _gh(["api", "repos/%s/milestones?state=all&per_page=100" % repo])
    if out.returncode != 0:
        raise SystemExit("gh api milestones failed (exit %d): %s" % (out.returncode, out.stderr.strip()))
    return json.loads(out.stdout)


def cmd_milestone_close(args):
    if args.milestones_json:
        with open(args.milestones_json, encoding="utf-8") as f:
            milestones = json.load(f)
    else:
        milestones = fetch_milestones(args.repo)
    by_title = {m["title"]: m for m in milestones}
    closing = by_title.get(args.name)
    if closing is None:
        print("milestone: no milestone is titled %r on %s (there are: %s)"
              % (args.name, args.repo, ", ".join(sorted(by_title)) or "none"))
        return 1
    left = sorted(i["number"] for i in (normalise(x) for x in _listing(args))
                  if i["state"] == "OPEN" and i["milestone"] == args.name)
    if left:
        print("milestone: %r still holds %d open issue(s): %s -- carry each first (python -m tools_py.issues carry N "
              "--comment ... [--milestone %r]) or close it; a milestone is closed empty"
              % (args.name, len(left), ", ".join("#%d" % n for n in left), args.next))
        return 1
    cmds = []
    if str(closing.get("state", "")).lower() == "closed":
        print("milestone: %r is already closed" % args.name)
    else:
        cmds.append(["api", "-X", "PATCH", "repos/%s/milestones/%d" % (args.repo, closing["number"]),
                     "-f", "state=closed"])
    if args.next in by_title:
        print("milestone: %r already exists (%s)" % (args.next, by_title[args.next].get("state")))
    else:
        cmds.append(["api", "-X", "POST", "repos/%s/milestones" % args.repo, "-f", "title=%s" % args.next])
    code = _run_all(cmds, args.dry_run)
    if code == 0 and cmds and not args.dry_run:
        print("milestone: %r closed, %r open" % (args.name, args.next))
    return code


def tally(issues, since):
    """{'opened': [n], 'closed': [n], 'carried': [n], 'highest': n} from `since` (YYYY-MM-DD) on. An issue carried
    more than once in the window counts once."""
    stack = [normalise(i) for i in issues]
    return {
        "opened": sorted(i["number"] for i in stack if i["createdAt"][:10] >= since),
        "closed": sorted(i["number"] for i in stack if i["closedAt"] and i["closedAt"][:10] >= since),
        "carried": sorted(i["number"] for i in stack
                          if any(when[:10] >= since for when, _ in carry_comments(i))),
        "highest": max([i["number"] for i in stack] or [0]),
    }


def cmd_tally(args):
    if not DATE.match(args.since):
        print("tally: --since wants a date, YYYY-MM-DD (the day the sprint opened)")
        return 2
    t = tally(_listing(args), args.since)
    print("Since %s: opened %d, closed %d, carried %d; the highest issue number is #%d."
          % (args.since, len(t["opened"]), len(t["closed"]), len(t["carried"]), t["highest"]))
    for kind in ("opened", "closed", "carried"):
        print("  %s: %s" % (kind, ", ".join("#%d" % n for n in t[kind]) or "none"))
    return 0


LABELS_SCRIPT = "scripts/github_labels.sh"
LABELS_BLOCK = re.compile(r"^LABELS=\(\n(.*?)^\)$", re.S | re.M)
# GitHub's own default labels, which exist on every repository and which the script deliberately does not create
# (its header says why: their names carry spaces, and DOC_MAINTENANCE section 7 step 6 hands them out). They are
# on real issues (#33 #39 #40 #46 #48), so a triager is shown them too.
GITHUB_DEFAULT_LABELS = (
    ("help wanted", "A contributor without a disc could take it."),
    ("good first issue", "Only where the closing bar is a test a newcomer can run themselves."),
)


def script_labels():
    """[(name, description)] in the order scripts/github_labels.sh creates them -- the repository's label set."""
    block = LABELS_BLOCK.search(_read(LABELS_SCRIPT)).group(1)
    out = []
    for line in block.splitlines():
        line = line.strip()
        if line.startswith('"'):
            name, _colour, description = line.strip('"').split("|", 2)
            out.append((name, description))
    return out


def cmd_labels(_args):
    labels = script_labels()
    print("The repository's labels, as %s creates them (add one there and run it, never in the web page):"
          % LABELS_SCRIPT)
    print("areas, exactly one per issue: %s" % " ".join(n for n, _ in labels if n in AREAS))
    for name, description in labels:
        if name not in AREAS:
            print("  %-16s %s" % (name, description))
    for name, description in GITHUB_DEFAULT_LABELS:
        print("  %-16s %s (GitHub default, not created here)" % (name, description))
    return 0


def cmd_audit(args):
    if args.json:
        with open(args.json, encoding="utf-8") as f:
            issues = json.load(f)
    else:
        issues = fetch_issues(args.repo)
    cited = live_citations()
    problems, notes = audit(cited, issues, stale_since=args.stale_since)
    open_stack = [normalise(i) for i in issues]
    open_stack = [i for i in open_stack if i["state"] == "OPEN" and STACK_LABEL in i["labels"]]
    print("issues: %d on the repository, %d open on the stack, %d cited by the live documents (%s)"
          % (len(issues), len(open_stack), len(cited), ", ".join(live_docs())))
    for p in problems:
        print("PROBLEM: " + p)
    for n in notes:
        print("note: " + n)
    rows = []
    if os.path.isfile(os.path.join(ROOT, KNOWN)):
        rows += [("section " + section, headline) for section, headline in known_rows_without_issue(_read(KNOWN))]
    if os.path.isfile(os.path.join(ROOT, HAZARDS)):
        rows += [("%s: %s" % (HAZARDS, area), headline)
                 for area, headline in known_rows_without_issue(_read(HAZARDS), hazards_file=True)]
    if rows:
        print("KNOWN rows and hazards neither cited, settled nor ruled out (%d) -- each is the review's to rule on:"
              % len(rows))
        for where, headline in rows:
            print("  - [%s] %s" % (where, headline))
    print("audit: %s" % ("OK" if not problems else "%d problem(s)" % len(problems)))
    return 1 if problems else 0


def _listing(args):
    """The issue listing: a saved `gh issue list --json` file when --json names one, else one gh call."""
    if args.json:
        with open(args.json, encoding="utf-8") as f:
            return json.load(f)
    return fetch_issues(args.repo)


def cmd_backlog(args):
    out_path = os.path.join(ROOT, args.out)
    try:
        rows = ruled_out_rows()
    except ValueError as e:
        print("backlog: %s" % e)
        return 2
    if args.offline:
        if not args.check:
            print("backlog: --offline only checks (the issue table needs the listing)")
            return 2
        if not os.path.isfile(out_path):
            print("backlog: %s does not exist -- python -m tools_py.issues backlog" % args.out)
            return 1
        with open(out_path, encoding="utf-8") as f:
            current = f.read()
        fresh = current.startswith(render_head()) and current.endswith(render_ruled_out(rows))
        print("backlog: %s (offline: the head and the ruled-out table against %s)"
              % ("OK" if fresh else "%s is stale -- python -m tools_py.issues backlog" % args.out, RULED_OUT_LIST))
        return 0 if fresh else 1
    text = render_backlog(_listing(args), rows)
    if args.check:
        current = None
        if os.path.isfile(out_path):
            with open(out_path, encoding="utf-8") as f:
                current = f.read()
        if current != text:
            print("backlog: %s is stale -- python -m tools_py.issues backlog" % args.out)
            return 1
        print("backlog: OK (%s matches the listing and %s)" % (args.out, RULED_OUT_LIST))
        return 0
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    n_open = text.split(RULED_OUT_HEADING)[0].count("\n| #")
    print("backlog: wrote %s -- %d open issues, %d ruled-out rows" % (args.out, n_open, len(rows)))
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")      # a KNOWN headline's dash must not crash a cp1252 console
    ap = argparse.ArgumentParser(prog="python -m tools_py.issues", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=REPO)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("skeleton").set_defaults(fn=cmd_skeleton)
    p = sub.add_parser("check-body")
    p.add_argument("file")
    p.set_defaults(fn=cmd_check_body)
    p = sub.add_parser("open")
    p.add_argument("--title", required=True)
    p.add_argument("--body-file", required=True)
    p.add_argument("--area", required=True)
    p.add_argument("--label", action="append")
    p.add_argument("--milestone")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_open)
    p = sub.add_parser("close")
    p.add_argument("number", type=int)
    p.add_argument("--artefact")
    p.add_argument("--not-planned", action="store_true")
    p.add_argument("--reason")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_close)
    p = sub.add_parser("audit")
    p.add_argument("--json")
    p.add_argument("--stale-since")
    p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("backlog")
    p.add_argument("--json")
    p.add_argument("--out", default=BACKLOG)
    p.add_argument("--check", action="store_true")
    p.add_argument("--offline", action="store_true")
    p.set_defaults(fn=cmd_backlog)
    p = sub.add_parser("carry")
    p.add_argument("number", type=int)
    p.add_argument("--comment", required=True)
    p.add_argument("--milestone")
    p.add_argument("--json")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_carry)
    p = sub.add_parser("milestone")
    msub = p.add_subparsers(dest="action", required=True)
    p = msub.add_parser("close")
    p.add_argument("name")
    p.add_argument("--next", required=True)
    p.add_argument("--json")
    p.add_argument("--milestones-json")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_milestone_close)
    p = sub.add_parser("tally")
    p.add_argument("--since", required=True)
    p.add_argument("--json")
    p.set_defaults(fn=cmd_tally)
    sub.add_parser("labels").set_defaults(fn=cmd_labels)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
