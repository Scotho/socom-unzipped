"""Rebuild `docs/story/timeline.json` from `docs/STORY.md` -- the machine-readable twin (spec 6.1).

`cite.py` asserts that the document and the data file agree in both directions and that every commit row's
stored date and subject match git; until this script existed the file was kept in step by hand, which is
how a data file drifts. This reads the document the way the citation test does (`cite.parse_entries`,
`cite.parse_cited`), asks git for each cited commit's full hash, author date and subject, and writes one row
per entry: `id` (`<date>-<slug>`, the site's anchor), `date`, `title`, `era`, `hook`, `citations`, and
`picture` when the entry shows one. Nothing is invented: a hash that does not resolve stops the run.

Usage:
    python -m tools_py.story.timeline [--story docs/STORY.md] [--out docs/story/timeline.json]
                                      [--generated YYYY-MM-DD] [--check]

`--check` writes nothing and exits 1 if the tracked file differs from what the document says.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

from tools_py.story import cite

ROOT = cite.ROOT
ABOUT = ("Machine-readable form of docs/STORY.md. Built by reading the document; the citation test asserts "
         "the two agree.")
_ERA_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s+\.\.\s+(\d{4}-\d{2}-\d{2})\s+-\s+(.+?)\s*$")


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def build(markdown, resolver, generated, head):
    """The timeline document for `markdown`. Raises ValueError on a commit the resolver cannot find."""
    eras = {}
    era = None
    for raw in markdown.splitlines():
        m = _ERA_RE.match(raw)
        if m:
            era = raw[3:].strip()
        m2 = cite._ENTRY_RE.match(raw)
        if m2:
            eras[(m2.group(1), m2.group(2))] = era
    rows = []
    for e in cite.parse_entries(markdown):
        hook, picture = "", None
        for ln in e.lines:
            s = ln.strip()
            if not hook and s.startswith("**") and s.endswith("**"):
                hook = s.strip("*")
            mi = cite._IMG_RE.search(s)
            if mi and picture is None:
                picture = {"path": mi.group(2), "caption": mi.group(1)}
        cits = []
        cited = e.cited_line()
        for c in (cite.parse_cited(cited) if cited else []):
            if c.kind == "commit":
                info = resolver.commit(c.ref)
                if info is None:
                    raise ValueError("%s: commit %s does not resolve" % (e.where, c.ref))
                sha, date, subject = info
                cits.append({"kind": "commit", "ref": c.ref, "sha": sha, "date": date, "subject": subject})
            elif c.kind in ("run", "gate", "log"):
                cits.append({"kind": c.kind, "ref": c.ref, "path": c.log_path})
            else:
                cits.append({"kind": "path", "ref": c.ref})
        row = {"id": "%s-%s" % (e.date, slug(e.title)), "date": e.date, "title": e.title,
               "era": eras.get((e.date, e.title)), "hook": hook, "citations": cits}
        if picture:
            row["picture"] = picture
        rows.append(row)
    return {"schema": 1, "generated": generated, "head": head, "about": ABOUT, "entries": rows}


def head_short(root):
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=root).decode().strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rebuild the story's timeline.json from the document.")
    ap.add_argument("--story", default=os.path.join(ROOT, "docs", "STORY.md"))
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "story", "timeline.json"))
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--generated", default=datetime.date.today().isoformat())
    ap.add_argument("--check", action="store_true", help="compare with the tracked file; write nothing")
    args = ap.parse_args(argv)
    with open(args.story, encoding="utf-8") as f:
        markdown = f.read()
    doc = build(markdown, cite.GitResolver(root=args.root), args.generated, head_short(args.root))
    if args.check:
        with open(args.out, encoding="utf-8") as f:
            old = json.load(f)
        same = old.get("entries") == doc["entries"]
        print("%s: %s" % (args.out, "in step with the document" if same else "DIFFERS from the document"))
        return 0 if same else 1
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("%s: %d entries at %s" % (args.out, len(doc["entries"]), doc["head"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
