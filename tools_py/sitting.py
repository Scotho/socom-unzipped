"""The owner's sitting page, generated (Sprint 14 Task D3).

`python -m tools_py.sitting` writes `docs/SITTING.md` from four sources; `--check` exits 1 when the file on disk
differs from a fresh render and prints the head of the diff. The page answers "what do you need from me", in four
sections the owner answers by number, one line each:

  1. the O rows of `docs/HUMAN_TASKS.md`: the hand needed (the bold lead of the row's second column), the default
     the loop is on, first asked, and the days waited to the page's date. A row whose default is struck (`~~`) is
     answered: it is listed apart, never as open.
  2. the active rulings on or after `since` -- `rulings.rows()`, the same records `docs/RULINGS.md` shows -- one
     line each ending "overturn by number": those dated on or after it, and those with no date in the label that
     the global counter places after it (numbered above the highest active ruling dated before it) or whose
     home's filename is dated on or after it. The rest of the undated ones are counted, not listed.
  3. the open issues whose `Carried` column in `docs/BACKLOG.md` reads 2 or more: keep, or close as not planned.
  4. the build `docs/PLAYTEST.md` names: its build block's archive and hashes, or **NOT BUILT**.

`since` defaults to the `last sitting: <date>` line under HUMAN_TASKS' header (`--since` overrides it). The page's
date ("as of") is today when it is written; `--check` renders with the date and the `since` the page on disk
carries, so the page goes stale when a source changes, not when the calendar does -- the days waited are as of the
date the page says. The suite holds the page to its sources AT THE COMMIT THAT LAST WROTE IT (`render_at`,
`page_rev`: tools_py.changelog's contract), so a later ruling or O row does not redden it; `--check` against the
current sources is the close's step and the loop regenerates the page when an O row, a ruling or the backlog changes.
"""
import argparse
import datetime
import difflib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

from tools_py import docmaint, rulings

PAGE = "docs/SITTING.md"
HUMAN_TASKS = "docs/HUMAN_TASKS.md"
BACKLOG = "docs/BACKLOG.md"
PLAYTEST = "docs/PLAYTEST.md"
MAX_CELL = 160

STAMP = re.compile(r"^last sitting:\s*(20\d{2}-\d{2}-\d{2})\b", re.M)
AS_OF = re.compile(r"\bas of (20\d{2}-\d{2}-\d{2})\b")
O_ROW = re.compile(r"^\|\s*(O\d+)\s*\|")
BOLD = re.compile(r"\*\*(.+?)\*\*")
SHA = re.compile(r"\b[0-9a-f]{64}\b")
GLOBAL = re.compile(r"R(\d{2,3})b?$")   # the global counter's names; S13-R<n> and S12-R<n> are not on it
SINCE = re.compile(r"\bfor the sitting after the one of (20\d{2}-\d{2}-\d{2})\b")
# D5 will write the block between these markers; until then the block is the first unquoted fence opening "build:".
BLOCK_MARKS = re.compile(r"<!-- build:begin -->(.*?)<!-- build:end -->", re.S)


def _cut(text, limit=MAX_CELL):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit - 1].rstrip() + "…"
        if text.count("`") % 2:
            text = text[:text.rindex("`")].rstrip() + "…"
    return text


def _plain(text):
    return re.sub(r"<!--.*?-->", "", text).replace("**", "").replace("~~", "").strip()


def _esc(text):
    return re.sub(r"(?<!\\)\|", r"\\|", text)


def stamps(human_tasks_md):
    """Every `last sitting: <date>` stamp, oldest first. D4's circuit breaker counts the stamps a row has stood
    through (the stamps on or after its first-asked date); today there is one."""
    return sorted(STAMP.findall(human_tasks_md))


def last_sitting(human_tasks_md):
    found = stamps(human_tasks_md)
    return found[-1] if found else None


def o_rows(human_tasks_md, today=None):
    """[{number, hand, default, first_asked, days, struck, answer}] in table order."""
    today = today or datetime.date.today()
    out = []
    for line in human_tasks_md.split("\n"):
        if not O_ROW.match(line):
            continue
        cells = rulings._cells(line)
        if len(cells) < 5:
            continue
        number, what, default, first = cells[0], cells[1], cells[2], cells[-1]
        struck = "~~" in default
        m = BOLD.search(what)
        hand = _plain(m.group(1)) if m else _plain(what)
        hand = hand.rstrip(":;,. ")
        answer = ""
        if struck:
            # The answer is what follows the struck part of the second column: "~~...~~ **Answered ... .**".
            tail = what.rsplit("~~", 1)[-1] if what.count("~~") >= 2 else ""
            answer = _plain(tail)
        d = docmaint.DATE.search(first)
        first_asked = d.group(0) if d else None
        days = None
        if not struck and first_asked:
            days = (today - datetime.date.fromisoformat(first_asked)).days
        out.append({"number": number, "hand": hand, "default": _plain(default), "first_asked": first_asked,
                    "days": days, "struck": struck, "answer": answer})
    return out


def _global_number(name):
    m = GLOBAL.match(name)
    return int(m.group(1)) if m else None


def _home_date(row):
    m = docmaint.DATE.search(os.path.basename((row.get("home") or "").split(" ", 1)[0]))
    return m.group(0) if m else None


def active_since(rulings_rows, since):
    """The active rulings on or after `since`: ([{..., placed}] in order, n dated, n placed, n unplaceable).

    A dated ruling is listed when its date is on or after `since` (placed = None). An undated one is placed after
    the sitting by either of two signals (placed names which): the global counter -- its number is above the
    highest-numbered active ruling dated before `since` ("number") -- or its home's filename carries a date on or
    after `since` ("home"). An undated ruling neither signal places is counted, not listed. The list runs in the
    global counter's order, then the sprint-local names by date."""
    active = [r for r in rulings_rows if r["status"] == "active"]
    before = [_global_number(r["number"]) for r in active if r["date"] and r["date"] < since]
    ceiling = max([n for n in before if n is not None], default=None)
    listed, n_dated, n_placed, n_unplaceable = [], 0, 0, 0
    for r in active:
        if r["date"]:
            if r["date"] >= since:
                listed.append(dict(r, placed=None))
                n_dated += 1
            continue
        n = _global_number(r["number"])
        home = _home_date(r)
        if n is not None and ceiling is not None and n > ceiling:
            listed.append(dict(r, placed="number"))
            n_placed += 1
        elif home and home >= since:
            listed.append(dict(r, placed="home"))
            n_placed += 1
        else:
            n_unplaceable += 1

    def key(r):
        n = _global_number(r["number"])
        suffix = r["number"][-1:] == "b"
        if n is not None:
            return (0, n, suffix, "", "")
        return (1, 0, False, r["date"] or _home_date(r) or "", r["number"])
    listed.sort(key=key)
    return listed, n_dated, n_placed, n_unplaceable


def carried_twice(backlog_md):
    """[{issue, title, area, carried}]: the open-issue table's rows whose Carried column reads 2 or more."""
    out, cols = [], None
    for line in backlog_md.split("\n"):
        if line.startswith("## ") and cols is not None:
            break   # the table of open issues ends at the next section
        if not line.startswith("|"):
            continue
        cells = rulings._cells(line)
        if cols is None:
            if "Carried" in cells and "Issue" in cells:
                cols = {name: i for i, name in enumerate(cells)}
            continue
        if not cells[0].startswith("#"):
            continue
        try:
            carried = int(cells[cols["Carried"]])
        except (ValueError, IndexError):
            continue
        if carried >= 2:
            out.append({"issue": cells[cols["Issue"]], "title": cells[cols.get("Title", 1)],
                        "area": cells[cols["Area"]] if "Area" in cols else "", "carried": carried})
    return out


def build_block(playtest_md):
    """The build block's lines: between D5's markers, else the first unquoted fenced block opening `build:`."""
    m = BLOCK_MARKS.search(playtest_md)
    if m:
        return [l for l in m.group(1).strip("\n").split("\n") if not l.strip().startswith("```")]
    lines = playtest_md.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("```") and i + 1 < len(lines) and lines[i + 1].startswith("build:"):
            block = []
            for body in lines[i + 1:]:
                if body.startswith("```"):
                    return block
                block.append(body)
            return block
    return None


def build_state(playtest_md):
    """(built: bool, the lines the page shows)."""
    block = build_block(playtest_md)
    if not block or "NOT BUILT" in "\n".join(block):
        return False, []
    shown = [l.strip() for l in block if re.match(r"\s*(?:build|archive):", l) or SHA.search(l)]
    return True, shown


def _plural(n, one, many=None):
    return "%d %s" % (n, one if n == 1 else (many or one + "s"))


def build(human_tasks_md, rulings_rows, backlog_md, playtest_md, since, today=None):
    """The page, as markdown."""
    today = today or datetime.date.today()
    rows = o_rows(human_tasks_md, today=today)
    open_rows = [r for r in rows if not r["struck"]]
    answered = [r for r in rows if r["struck"]]
    listed, n_dated, n_placed, n_unplaceable = active_since(rulings_rows, since)
    carried = carried_twice(backlog_md)
    built, shown = build_state(playtest_md)
    ruling_counts = "%d dated, %d placed by number or home, %d undated and unplaceable, not listed" % (
        n_dated, n_placed, n_unplaceable)
    counts = "%s (%d answered or struck); %s since %s (%s); %s; the build: %s." % (
        _plural(len(open_rows), "open O row"), len(answered), _plural(len(listed), "active ruling"), since,
        ruling_counts,
        _plural(len(carried), "issue carried twice", "issues carried twice"),
        "built" if built else "**NOT BUILT**")
    out = [
        "# The owner's sitting",
        "",
        "> **Generated -- do not edit.** Written by `python -m tools_py.sitting` from `%s` (the O rows and the "
        "`last sitting:` stamp), the rulings `docs/RULINGS.md` shows (`tools_py.rulings.rows()`), `%s` (the "
        "`Carried` column) and `%s` (its build block). Change a source and regenerate; "
        "`python -m tools_py.sitting --check` exits 1 when this file is stale." % (HUMAN_TASKS, BACKLOG, PLAYTEST),
        "",
        "The page as of %s, for the sitting after the one of %s: %s" % (today.isoformat(), since, counts),
        "",
        "**How to answer.** One line per item, by number -- \"O5: acceptable for v1\", \"R271: overturn\", "
        "\"#25: close\" -- in the next session's prompt or as a note in `docs/STATUS.md`.",
        "",
        "## 1. The O rows",
        "",
        "%d open, %d answered or struck. Each stands on its default until you answer; days waited are to %s." % (
            len(open_rows), len(answered), today.isoformat()),
        "",
        "| O | the hand needed | the default the loop is on | first asked | days waited |",
        "|---|---|---|---|---|",
    ]
    for r in open_rows:
        out.append("| %s | %s | %s | %s | %s |" % (
            r["number"], _esc(_cut(r["hand"])), _esc(_cut(r["default"])), r["first_asked"] or "--",
            "--" if r["days"] is None else r["days"]))
    out += ["", "Answered or struck (the row stays in HUMAN_TASKS as the record):", ""]
    for r in answered:
        out.append("- %s: %s -- %s" % (r["number"], _cut(r["hand"]), _cut(r["answer"]) or "struck"))
    if not answered:
        out.append("- none")
    out += [
        "",
        "## 2. The rulings since the last sitting",
        "",
        "%s on or after %s, in the counter's order (the sprint-local names last, by date): %s dated on or "
        "after it, and %s with no date in the label but *placed by number* -- above the highest-numbered active "
        "ruling dated before %s -- or *placed by home*, its file dated on or after it. Each stands until you "
        "overturn it; an overturn is its number and the word. Left out: %s, which neither signal places "
        "(`docs/RULINGS.md` lists every ruling)." % (
            _plural(len(listed), "active ruling"), since, n_dated, n_placed, since,
            _plural(n_unplaceable, "active ruling with no date", "active rulings with no date")),
        "",
    ]
    for r in listed:
        when = r["date"] if r["placed"] is None else "placed by %s" % r["placed"]
        out.append("- **%s** (%s) %s -- overturn by number" % (r["number"], when, _cut(r["line"])))
    out += [
        "",
        "## 3. The issues carried twice",
        "",
        "%s at `Carried` 2 or more in `%s`: keep each on the backlog, or close it as not planned under a ruling." % (
            _plural(len(carried), "issue carried twice", "issues carried twice"), BACKLOG),
        "",
    ]
    for c in carried:
        out.append("- %s (%s, carried %d) %s" % (c["issue"], c["area"], c["carried"], _cut(c["title"])))
    if not carried:
        out.append("- none")
    out += ["", "## 4. The build", ""]
    if built:
        out.append("The build `%s` names, to play and to check against:" % PLAYTEST)
        out += ["", "```"] + shown + ["```"]
    else:
        out.append("**NOT BUILT**: `%s` names no archive for the current tree; there is nothing to play yet." %
                   PLAYTEST)
    return "\n".join(out) + "\n"


def _read(root, rel):
    with open(os.path.join(root, rel), "r", encoding="utf-8") as fh:
        return fh.read()


def render_tree(root, since=None, today=None):
    human = _read(root, HUMAN_TASKS)
    since = since or last_sitting(human)
    if not since:
        raise SystemExit("sitting: no `last sitting: <date>` line in %s and no --since" % HUMAN_TASKS)
    return build(human, rulings.rows(root=root), _read(root, BACKLOG), _read(root, PLAYTEST), since, today=today)


def page_stamps(page_md):
    """(today, since) the page on disk was rendered with, each None when the page does not say."""
    m, s = AS_OF.search(page_md), SINCE.search(page_md)
    return (datetime.date.fromisoformat(m.group(1)) if m else None), (s.group(1) if s else None)


def _git(repo, *args):
    return subprocess.run(["git"] + list(args), cwd=repo, capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout


def shallow_reason(repo):
    """A sentence when `repo` is a shallow clone (CI's depth-1 checkout), else None: the commit that last wrote
    the page may be missing there (tools_py.changelog's precedent)."""
    if _git(repo, "rev-parse", "--is-shallow-repository").strip() == "true":
        return "%s is a shallow clone: the commit that last wrote %s may be missing" % (repo, PAGE)
    return None


def page_rev(repo):
    """The commit the page on disk should be a render of: the last commit that wrote it, or None (the working
    tree) while it has uncommitted changes or was never committed."""
    if _git(repo, "status", "--porcelain", "--", PAGE).strip():
        return None
    return _git(repo, "log", "-1", "--format=%H", "--", PAGE).strip() or None


def render_at(repo, rev, since=None, today=None):
    """The page rendered from the sources as they stood at `rev` (None: the working tree). Every tracked markdown
    file at `rev` is unpacked into a scratch tree, because the rulings are read from many documents."""
    if rev is None:
        return render_tree(repo, since=since, today=today)
    tmp = tempfile.mkdtemp(prefix="sitting_at_")
    try:
        data = subprocess.run(["git", "archive", "--format=tar", rev, "--", "*.md"], cwd=repo,
                              capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(tmp, filter="data")
            else:
                tar.extractall(tmp)
        return render_tree(tmp, since=since, today=today)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m tools_py.sitting", description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 when %s differs from a fresh render" % PAGE)
    ap.add_argument("--since", default=None, help="the last sitting's date (default: HUMAN_TASKS' stamp)")
    ap.add_argument("--root", default=None, help="the tree to read and write (default: this repository)")
    args = ap.parse_args(argv)
    root = args.root or docmaint.ROOT
    target = os.path.join(root, PAGE)
    if args.check:
        try:
            current = _read(root, PAGE)
        except OSError:
            print("sitting: %s is missing; run python -m tools_py.sitting" % PAGE)
            return 1
        as_of, page_since = page_stamps(current)
        fresh = render_tree(root, since=args.since or page_since, today=as_of)
        if current == fresh:
            print("sitting: %s is current" % PAGE)
            return 0
        diff = list(difflib.unified_diff(current.split("\n"), fresh.split("\n"),
                                         "%s (on disk)" % PAGE, "%s (fresh render)" % PAGE, lineterm=""))
        sys.stdout.write("\n".join(diff[:40]) + "\n")
        if len(diff) > 40:
            print("... %d more diff lines" % (len(diff) - 40))
        print("sitting: %s is stale; run python -m tools_py.sitting" % PAGE)
        return 1
    fresh = render_tree(root, since=args.since)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(fresh)
    print("sitting: wrote %s (%s)" % (PAGE, fresh.split("\n")[4].split(": ", 1)[-1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
