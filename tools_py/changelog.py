"""The changelog: every merge commit, grouped by release tag, generated from git (Sprint 14 Task S1, R272).

Run: python -m tools_py.changelog [--check] [--repo <path>] [--out <file>] [--rev <commit>]

Writes `docs/CHANGELOG.md`; `--check` exits 1 when the file differs from a fresh render and prints the head of the
diff. Until 2026-09-26 `docs/STATUS.md` carried a hand-written log below its "Current state" block, 260 KB that
nobody read; that log is archived (`docs/archive/STATUS-log-to-2026-09-26.md`) and this page replaces its record of
what landed. The reasoning behind a merge lives in its commit message and in the sprint plan's Log.

What is read (`docs/GIT_STRATEGY.md` section 2: sprint merges, slices and outside PRs reach `main` as merge commits;
agent branches reach a sprint branch as merge commits):
  * every merge on the first-parent line of `--rev` (default HEAD) -- `git log --merges --first-parent`: on a sprint
    branch, the agent-branch merges and the merges of `main` into it, then `main`'s own line (the sprint -> main
    merges, the slices, the reviewed topic PRs);
  * and, for each such merge, the merges on the first-parent line of the branch it brought in, down to where that
    branch left the line it joined (`git log --merges --first-parent <merge>^2 --not <merge>^1`), recursively -- so
    a closed sprint's own agent merges are listed under the merge that took the sprint to `main`. `via` names the
    merge that brought an entry in (None on the first-parent line).
  * A merge of `main` (or `origin/main`) INTO a sprint or topic branch is listed, marked "main merged in": it is how
    a slice's or a filler's work reached the sprint branch, and leaving it out would make the sprint's record skip
    the day main moved under it.

Grouping: the `v*` tags (`git for-each-ref refs/tags/v*`) whose commit is in the history, ordered by their commit's
date; each merge belongs to the oldest tag that contains it, and the merges no tag contains are "Since <newest tag>".
Containment, not dates, decides, because tags were created after the fact (v0.5.0 to v0.8.0 on 2026-09-23).

Each entry: `sha`, `date` (the committer date, the day the merge was made), `branch` (named from the subject, never
from a ref, so the page is the same on every clone; "" when the subject names none), `subject_head`, `body`, `tag`,
`via`, `direction`. The head of a subject: git's own default subjects ("Merge branch ...", "Merge remote-tracking
branch ...", "Merge pull request ...") are kept as they are; otherwise the house prefix "merge <branch>:" or
"merge:" is dropped (and a branch named first, "merge: agent/disc -- <what>", with it), a "Merge <branch> (<what>) into <target>" keeps <what>, and the text is cut at the first " -- ".
Backticks are dropped on the page, so a path a later commit moved is not read as a claim about today's tree
(`docs/DOC_MAINTENANCE.md` section 4, check 6).
"""
import argparse
import difflib
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = "docs/CHANGELOG.md"
SHORT = 8
MAX_HEAD = 160
MAIN_IN = "main merged in"

DEFAULT_SUBJECT = re.compile(r"^Merge (?:branch|remote-tracking branch|pull request|tag|commit) ")
PR_FROM = re.compile(r"^Merge pull request #\d+ from [^/\s]+/(\S+)")
GIT_BRANCH = re.compile(r"^Merge (?:remote-tracking )?branch '([^']+)'")
MAIN_INTO = re.compile(r"^[Mm]erge:\s+((?:origin/)?main)\b")
NAMED = re.compile(r"^[Mm]erge\s+([A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*)(?=[\s:(]|$)")
SPRINT_TO_MAIN = re.compile(r"\bSprint (\d+)\b[^:]*?\bto main\b")
SPRINT_TITLE = re.compile(r"^Sprint (\d+):")
PARENTHESISED = re.compile(r"^Merge (\S+) \((.*)\) into \S+$")
HOUSE_PREFIX = re.compile(r"^[Mm]erge(?:\s+[^\s:(]+)?\s*:\s*(.*)$")
LEAD_BRANCH = re.compile(r"^([A-Za-z0-9._-]+/[A-Za-z0-9._/-]+) -- ")     # "merge: agent/disc -- what it was"


def _git(repo, *args):
    out = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, check=True)
    return out.stdout.decode("utf-8", errors="replace")


def branch_of(subject):
    """The branch a merge subject says it merged, or "" when it names none."""
    for pat in (PR_FROM, GIT_BRANCH, MAIN_INTO):
        m = pat.match(subject)
        if m:
            return m.group(1)
    m = HOUSE_PREFIX.match(subject)
    lead = LEAD_BRANCH.match(m.group(1)) if m else None
    if lead:
        return lead.group(1)
    m = NAMED.match(subject)
    if m and re.search(r"[/_-]", m.group(1)):
        return m.group(1)
    m = SPRINT_TO_MAIN.search(subject) or SPRINT_TITLE.match(subject)
    if m:
        return "sprint-%s" % m.group(1)
    return ""


def subject_head(subject):
    """The head of a merge subject (the module docstring has the rule)."""
    if DEFAULT_SUBJECT.match(subject):
        return subject
    m = PARENTHESISED.match(subject) or HOUSE_PREFIX.match(subject)
    text = m.group(m.lastindex) if m else subject
    lead = LEAD_BRANCH.match(text)
    if lead:
        text = text[lead.end():]
    return text.split(" -- ", 1)[0].strip()


def direction_of(branch):
    return MAIN_IN if branch in ("main", "origin/main") else None


def _history(repo, rev):
    """{sha: {parents, date, ct, subject, body}} for every commit reachable from rev."""
    raw = _git(repo, "log", "--format=%H%x1f%P%x1f%cs%x1f%ct%x1f%s%x1f%b%x1e", rev)
    commits = {}
    for rec in raw.split("\x1e"):
        rec = rec.lstrip("\n")
        if not rec:
            continue
        sha, parents, date, ct, subject, body = rec.split("\x1f", 5)
        commits[sha] = {"parents": parents.split(), "date": date, "ct": int(ct), "subject": subject,
                        "body": body.strip()}
    return commits


class _Graph(object):
    def __init__(self, repo, rev):
        self.commits = _history(repo, rev)
        self.head = _git(repo, "rev-parse", "--verify", rev + "^{commit}").strip()
        self._anc = {}

    def ancestors(self, sha):
        """sha and everything reachable from it, within the history read."""
        if sha not in self._anc:
            seen, stack = set(), [sha]
            while stack:
                s = stack.pop()
                if s in seen or s not in self.commits:
                    continue
                seen.add(s)
                stack.extend(self.commits[s]["parents"])
            self._anc[sha] = seen
        return self._anc[sha]


def tags(repo, rev="HEAD", graph=None):
    """The v* tags whose commit is in rev's history, oldest first: [{name, date, sha}]."""
    g = graph or _Graph(repo, rev)
    raw = _git(repo, "for-each-ref", "--format=%(refname:lstrip=2)%1f%(creatordate:short)%1f%(objectname)"
               "%1f%(*objectname)", "refs/tags/v*")
    reach = g.ancestors(g.head)
    out = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        name, date, obj, peeled = line.split("\x1f")
        target = peeled or obj
        if target in reach:
            out.append({"name": name, "date": date, "sha": target})
    out.sort(key=lambda t: (g.commits[t["sha"]]["ct"], t["date"], t["name"]))
    return out


def entries(repo, rev="HEAD"):
    """Every merge in rev's history as the module docstring defines it, newest first, each with its tag."""
    g = _Graph(repo, rev)
    rows, seen = [], set()

    def walk(tip, excluded, via):
        sha = tip
        while sha in g.commits and not any(sha in ex for ex in excluded):
            c = g.commits[sha]
            if len(c["parents"]) > 1 and sha not in seen:
                seen.add(sha)
                branch = branch_of(c["subject"])
                rows.append({"sha": sha, "date": c["date"], "branch": branch,
                             "subject_head": subject_head(c["subject"]), "body": c["body"], "tag": None,
                             "via": via, "direction": direction_of(branch)})
                first = g.ancestors(c["parents"][0])
                for other in c["parents"][1:]:
                    walk(other, excluded + [first], sha)
            if not c["parents"]:
                break
            sha = c["parents"][0]

    walk(g.head, [], None)
    for t in tags(repo, rev, graph=g):
        contained = g.ancestors(t["sha"])
        for r in rows:
            if r["tag"] is None and r["sha"] in contained:
                r["tag"] = t["name"]
    return rows


def page_rev(repo):
    """The commit the page on disk should be a render of: the last commit that wrote it, or HEAD while it has
    uncommitted changes or was never committed."""
    if _git(repo, "status", "--porcelain", "--", PAGE).strip():
        return "HEAD"
    last = _git(repo, "log", "-1", "--format=%H", "--", PAGE).strip()
    return last or "HEAD"


def _line(e, nested):
    head = e["subject_head"].replace("`", "")
    if len(head) > MAX_HEAD:
        head = head[:MAX_HEAD - 3].rstrip() + "..."
    label = e["branch"] or "branch not named"
    if e["direction"]:
        label = "%s, %s" % (label, e["direction"])
    text = "%s `%s` %s [%s]" % (e["date"], e["sha"][:SHORT], head, label)
    if e["via"] and not nested:
        text += " (via `%s`)" % e["via"][:SHORT]
    return ("  - " if nested else "- ") + text


def render(rows, tag_list):
    """The page. Sections newest first: the merges since the newest tag, then one per tag."""
    newest = tag_list[-1]["name"] if tag_list else None
    sections = [(None, "Since %s" % newest if newest else "Untagged", None)]
    for t in reversed(tag_list):
        sections.append((t["name"], t["name"], "Tagged %s on `%s`." % (t["date"], t["sha"][:SHORT])))
    top = sum(1 for r in rows if r["via"] is None)
    out = [
        "# Changelog: the merges, by release tag",
        "",
        "> **Generated -- do not edit.** Written by `python -m tools_py.changelog` from `git log` (R272): every merge "
        "commit on the first-parent line of the history it was rendered from, and on the first-parent line of each "
        "branch those merges brought in, grouped by the oldest `v*` tag that contains it. `python -m "
        "tools_py.changelog --check` exits 1 when this file is stale; regenerate at every merge to a sprint branch "
        "(in the merge's follow-up commit) and at the close. The rules are the module's docstring. The reasoning "
        "behind a merge is its commit message and the sprint plan's Log; the hand-written log this page replaced is "
        "`docs/archive/STATUS-log-to-2026-09-26.md`.",
        "",
        "%d merges (%d on the first-parent line, %d from the branches they merged) in %d sections: %d tag%s and the "
        "merges since the newest. Each line: the date, the merge commit, the head of its subject, [the branch it "
        "merged]. An indented line came in on the branch the line above it merged." % (
            len(rows), top, len(rows) - top, len(sections), len(tag_list), "" if len(tag_list) == 1 else "s"),
    ]
    for key, title, note in sections:
        members = [r for r in rows if r["tag"] == key]
        shas = set(r["sha"] for r in members)
        out += ["", "## " + title, ""]
        if note:
            out += [note, ""]
        out.append("%d merge%s." % (len(members), "" if len(members) == 1 else "s"))
        if members:
            out.append("")
        for r in members:
            out.append(_line(r, nested=r["via"] in shas))
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m tools_py.changelog", description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 when the page differs from a fresh render")
    ap.add_argument("--repo", default=ROOT, help="the repository to read (default: this one)")
    ap.add_argument("--out", default=None, help="the page to write or check (default: <repo>/%s)" % PAGE)
    ap.add_argument("--rev", default="HEAD", help="the commit whose history is rendered (default: HEAD)")
    args = ap.parse_args(argv)
    target = args.out or os.path.join(args.repo, PAGE)
    rows = entries(args.repo, args.rev)
    tag_list = tags(args.repo, args.rev)
    fresh = render(rows, tag_list)
    if args.check:
        try:
            with open(target, "r", encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            print("changelog: %s is missing; run python -m tools_py.changelog" % target)
            return 1
        if current == fresh:
            print("changelog: %s is current" % target)
            return 0
        diff = list(difflib.unified_diff(current.split("\n"), fresh.split("\n"), "on disk", "fresh render",
                                         lineterm=""))
        sys.stdout.write("\n".join(diff[:40]) + "\n")
        if len(diff) > 40:
            print("... %d more diff lines" % (len(diff) - 40))
        print("changelog: %s is stale; run python -m tools_py.changelog" % target)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(fresh)
    per = ["%s %d" % (t["name"], sum(1 for r in rows if r["tag"] == t["name"])) for t in reversed(tag_list)]
    print("changelog: wrote %s (%d merges; since the newest tag %d; %s)" % (
        target, len(rows), sum(1 for r in rows if r["tag"] is None), ", ".join(per)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
