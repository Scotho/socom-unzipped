"""Carry the story's commit citations across a history rewrite -- spec 4.4, decision D1.

A `git filter-repo` rewrite re-hashes every descendant of the first affected commit, so in practice every
hash in `docs/STORY.md` and `docs/story/timeline.json` changes at once, and the citation test goes red. That
is the test working. This script is what makes clearing it mechanical instead of editorial:

  * With a map (`.git/filter-repo/commit-map`: `old new` per line), every hash is rewritten through it and
    the stored date and subject are refreshed from the new history.
  * Without a map (a fresh import), each citation is looked up by `(author date, subject)` in the new
    history. Anything that is not a UNIQUE match is reported for a person to settle, never guessed.
  * Nothing is written unless every citation resolved, or `--partial` is given -- and even then the
    unresolved ones are left exactly as they were and listed.

The prose is never touched: the story keeps hashes out of sentences for exactly this reason (spec 4.4,
decision 1), so a rewrite edits the `Cited:` lines and the data file and nothing else.

Usage:
    python -m tools_py.story.remap [--map .git/filter-repo/commit-map] [--story docs/STORY.md]
                                   [--timeline docs/story/timeline.json] [--dry-run] [--partial]
Exit 0 when everything resolved, 1 when something needs a person, 2 on a usage error.
"""
import argparse
import json
import os
import re
import subprocess
import sys

from tools_py.story import cite

ROOT = cite.ROOT
_HASH_IN_CITED = re.compile(r"`([0-9a-f]{7,40})`")


def load_map(path):
    """`old new` pairs, keyed by every unambiguous prefix a citation might have used."""
    pairs = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            parts = ln.split()
            if len(parts) >= 2 and re.fullmatch(r"[0-9a-f]{40}", parts[0]) and re.fullmatch(r"[0-9a-f]{40}", parts[1]):
                pairs.append((parts[0], parts[1]))
    return pairs


def lookup_in_map(pairs, short):
    hits = {new for old, new in pairs if old.startswith(short)}
    return hits.pop() if len(hits) == 1 else None


class NewHistory(object):
    """The rewritten repository, as (date, subject) -> [full sha]."""

    def __init__(self, root=ROOT, ref="HEAD"):
        self.root = root
        self.ref = ref
        self._index = None

    def _git(self, *a):
        p = subprocess.run(["git"] + list(a), cwd=self.root, capture_output=True)
        return p.returncode, p.stdout.decode("utf-8", "replace")

    def index(self):
        if self._index is None:
            rc, out = self._git("log", self.ref, "--format=%H%x00%ad%x00%s", "--date=short")
            idx = {}
            if rc == 0:
                for ln in out.splitlines():
                    if ln.count("\x00") == 2:
                        sha, date, subject = ln.split("\x00")
                        idx.setdefault((date, cite.normalise(subject)), []).append(sha)
            self._index = idx
        return self._index

    def by_date_subject(self, date, subject):
        return list(self.index().get((date, cite.normalise(subject)), []))

    def describe(self, sha):
        rc, out = self._git("show", "-s", "--format=%H%x00%ad%x00%s", "--date=short", sha)
        if rc != 0 or out.strip().count("\x00") != 2:
            return None
        full, date, subject = out.strip().split("\x00")
        return full, date, subject


def resolve(citation, pairs, history):
    """(new_full_sha, reason) or (None, reason). Never guesses: a non-unique match is a None."""
    old = citation.get("ref", "")
    if pairs:
        new = lookup_in_map(pairs, old)
        if new:
            return new, "mapped"
    date, subject = citation.get("date"), citation.get("subject")
    if not (date and subject):
        return None, "no stored date/subject to fall back on"
    hits = history.by_date_subject(date, subject)
    if len(hits) == 1:
        return hits[0], "matched by (date, subject)"
    if not hits:
        return None, "no commit in the new history has that date and subject"
    return None, "%d commits share that date and subject: %s" % (len(hits), ", ".join(h[:7] for h in hits))


def remap(timeline, story_text, pairs, history, short=7):
    """Returns (new_timeline, new_story_text, resolved, unresolved)."""
    resolved, unresolved = [], []
    rewrite = {}
    for entry in timeline.get("entries", []):
        for c in entry.get("citations", []):
            if c.get("kind") != "commit":
                continue
            old = c.get("ref", "")
            if old in cite.KNOWN_DEAD:
                continue
            new, why = resolve(c, pairs, history)
            if new is None:
                unresolved.append((entry.get("title", ""), old, why))
                continue
            info = history.describe(new)
            if info is None:
                unresolved.append((entry.get("title", ""), old, "mapped to %s, which the new history does not have" % new[:7]))
                continue
            full, date, subject = info
            rewrite[old] = full[:short]
            c.update({"ref": full[:short], "sha": full, "date": date, "subject": subject})
            resolved.append((old, full[:short], why))
    # the story's Cited: lines only -- never a sentence
    out_lines = []
    for ln in story_text.splitlines(keepends=True):
        if ln.lstrip().startswith("`Cited:`"):
            ln = _HASH_IN_CITED.sub(lambda m: "`%s`" % rewrite.get(m.group(1), m.group(1)), ln)
        out_lines.append(ln)
    return timeline, "".join(out_lines), resolved, unresolved


def main(argv=None):
    ap = argparse.ArgumentParser(description="Carry the story's citations across a history rewrite.")
    ap.add_argument("--map", default=None, help=".git/filter-repo/commit-map; omit for a fresh import")
    ap.add_argument("--story", default=os.path.join(ROOT, "docs", "STORY.md"))
    ap.add_argument("--timeline", default=os.path.join(ROOT, "docs", "story", "timeline.json"))
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--partial", action="store_true", help="write what resolved even if some did not")
    args = ap.parse_args(argv)
    pairs = load_map(args.map) if args.map else []
    with open(args.timeline, encoding="utf-8") as f:
        timeline = json.load(f)
    with open(args.story, encoding="utf-8") as f:
        story = f.read()
    timeline, story, resolved, unresolved = remap(timeline, story, pairs, NewHistory(root=args.root))
    for old, new, why in resolved:
        print("%s -> %s  (%s)" % (old, new, why))
    for title, old, why in unresolved:
        print("UNRESOLVED %s in %r: %s" % (old, title, why))
    print("\n%d resolved, %d need a person." % (len(resolved), len(unresolved)))
    if unresolved and not args.partial:
        print("Nothing written. Settle the unresolved ones, or pass --partial to write the rest.")
        return 1
    if not args.dry_run:
        with open(args.timeline, "w", encoding="utf-8", newline="\n") as f:
            json.dump(timeline, f, indent=1, ensure_ascii=False)
            f.write("\n")
        with open(args.story, "w", encoding="utf-8", newline="\n") as f:
            f.write(story)
        print("Written. Now run: python -m tools_py.story.cite")
    return 1 if unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
