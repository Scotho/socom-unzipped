"""The owner's sitting page, generated (Sprint 14 Task D3).

`python -m tools_py.sitting` writes `docs/SITTING.md` from four sources; `--check` exits 1 when the file on disk
differs from a fresh render and prints the head of the diff. The page answers "what do you need from me", in four
sections the owner answers by number, one line each:

  1. the O rows of `docs/HUMAN_TASKS.md`: the hand needed (the bold lead of the row's second column), the default
     the loop is on, first asked, and the days waited to the page's date. A row whose default is struck (`~~`) is
     answered: it is listed apart, never as open.
  2. the active rulings dated on or after `since` -- `rulings.rows()`, the same records `docs/RULINGS.md` shows --
     one line each ending "overturn by number". A ruling whose label carries no date cannot be placed before or
     after the sitting; the page says how many were left out and `docs/RULINGS.md` lists them.
  3. the open issues whose `Carried` column in `docs/BACKLOG.md` reads 2 or more: keep, or close as not planned.
  4. the build `docs/PLAYTEST.md` names: its build block's archive and hashes, or **NOT BUILT**.

`since` defaults to the `last sitting: <date>` line under HUMAN_TASKS' header (`--since` overrides it). The page's
date ("as of") is today when it is written; `--check` renders with the date the page on disk carries, so the page
goes stale when a source changes, not when the calendar does -- the days waited are as of the date the page says.
"""
import argparse
import datetime
import difflib
import os
import re
import sys

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


def active_since(rulings_rows, since):
    """(the active rulings dated on or after `since`, oldest first; the number of active rulings with no date)."""
    active = [r for r in rulings_rows if r["status"] == "active"]
    dated = [r for r in active if r["date"] and r["date"] >= since]
    def key(r):
        sprint, number, suffix = rulings._sort_key(r["number"])
        return (r["date"], -sprint, -number, suffix)
    dated.sort(key=key)
    return dated, sum(1 for r in active if not r["date"])


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
    dated, undated = active_since(rulings_rows, since)
    carried = carried_twice(backlog_md)
    built, shown = build_state(playtest_md)
    counts = "%s (%d answered or struck); %s since %s; %s; the build: %s." % (
        _plural(len(open_rows), "open O row"), len(answered), _plural(len(dated), "active ruling"), since,
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
        "%s dated on or after %s, oldest first. Each stands until you overturn it; an overturn is its number "
        "and the word. Left out: %s in the label, which cannot be placed before or after the sitting "
        "(`docs/RULINGS.md` lists every ruling)." % (
            _plural(len(dated), "active ruling"), since,
            _plural(undated, "active ruling has no date", "active rulings have no date")),
        "",
    ]
    for r in dated:
        out.append("- **%s** (%s) %s -- overturn by number" % (r["number"], r["date"], _cut(r["line"])))
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
        m = AS_OF.search(current)
        as_of = datetime.date.fromisoformat(m.group(1)) if m else None
        fresh = render_tree(root, since=args.since, today=as_of)
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
