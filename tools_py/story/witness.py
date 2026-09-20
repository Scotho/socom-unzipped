"""Freeze a witness for every run, gate and log citation in `docs/STORY.md` -- spec 4.3.

`/logs/` is git-ignored, so a stranger reading the public repository can never open the run a sentence
cites. The witness is the small, checkable part of that evidence carried in the tree: where it came from,
a few lines of what it says, its size and its sha256. `cite.py` checks the witness exists in any clone and,
on a machine that has `logs/`, re-proves the size and hash against the file itself.

A witness is written by this script, never typed by hand -- a copy of evidence can be wrong in a way the
original is not, and the sha256 re-proof only means something if the text and the hash were captured
together. Existing witnesses are kept unless `--refresh` is given, so a re-run after a log changes is a
loud diff rather than a silent update.

The captured text is scrubbed of the machine's home directory and user name before it is written: the
witness file is a public artefact and the logs were not written to be one.

Usage:
    python -m tools_py.story.witness [--story docs/STORY.md] [--out docs/story/witnesses.json]
                                     [--captured YYYY-MM-DD] [--refresh] [--archived PATH ...]
"""
import argparse
import getpass
import json
import os
import re
import sys

from tools_py.story import cite

ROOT = cite.ROOT
MAX_TEXT = 480


def scrub(text):
    home = os.path.expanduser("~").replace("\\", "/")
    user = getpass.getuser()
    out = text.replace("\\", "/")
    for needle in sorted({home, home.lower(), home.upper()}, key=len, reverse=True):
        if needle:
            out = out.replace(needle, "<home>")
    if user:
        out = re.sub(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(user), "<user>", out)
    return out


def head_text(full):
    """The first few lines of a file, or a directory's first few entries -- enough for a reader to see
    that the witness is about what the sentence says it is about."""
    if os.path.isdir(full):
        names = sorted(os.listdir(full))
        text = "\n".join(names[:12])
        if len(names) > 12:
            text += "\n... (%d entries)" % len(names)
        return text
    try:
        with open(full, "rb") as f:
            raw = f.read(4096)
    except OSError:
        return ""
    if b"\x00" in raw or os.path.splitext(full)[1].lower() in (".wav", ".png", ".jpg", ".gz", ".zip", ".bin"):
        # A picture or a sound cannot be quoted; the size and the hash are the witness.
        return "<binary %s, %d bytes>" % (os.path.splitext(full)[1].lower() or "file", os.path.getsize(full))
    text = raw.decode("utf-8", errors="replace")
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()][:6]
    text = "\n".join(lines)
    return text[:MAX_TEXT]


def freeze(path, captured, archived=False):
    full = os.path.join(ROOT, path)
    d = cite.digest_path(full)
    if d is None:
        return None
    size, digest = d
    return {
        "source": path,
        "text": scrub(head_text(full)),
        "bytes": size,
        "sha256": digest,
        "captured": captured,
        "archived": bool(archived),
        "kind": "directory" if os.path.isdir(full) else "file",
    }


def cited_log_paths(markdown):
    out = []
    for entry in cite.parse_entries(markdown):
        line = entry.cited_line()
        if not line:
            continue
        try:
            cits = cite.parse_cited(line)
        except ValueError:
            continue
        for c in cits:
            p = c.log_path
            if p and p not in out:
                out.append(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Freeze witnesses for the story's run citations.")
    ap.add_argument("--story", default=os.path.join(ROOT, "docs", "STORY.md"))
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "story", "witnesses.json"))
    ap.add_argument("--captured", required=True, help="the date to stamp on new witnesses, YYYY-MM-DD")
    ap.add_argument("--refresh", action="store_true", help="re-freeze witnesses that already exist")
    ap.add_argument("--archived", nargs="*", default=[],
                    help="paths whose file is gone but whose witness is kept, marked archived")
    args = ap.parse_args(argv)
    with open(args.story, encoding="utf-8") as f:
        markdown = f.read()
    existing = cite.load_witnesses(args.out)
    wanted = cited_log_paths(markdown)
    written, kept, missing = [], [], []
    for path in wanted:
        if path in existing and not args.refresh:
            kept.append(path)
            continue
        w = freeze(path, args.captured, archived=path in args.archived)
        if w is None:
            if path in existing:
                kept.append(path)
            else:
                missing.append(path)
            continue
        existing[path] = w
        written.append(path)
    for path in args.archived:
        if path in existing:
            existing[path]["archived"] = True
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    doc = {
        "schema": 1,
        "about": "Frozen witnesses for docs/STORY.md's run, gate and log citations. Written by "
                 "tools_py/story/witness.py, never by hand. logs/ is git-ignored; this is the checkable part.",
        "witnesses": {k: existing[k] for k in sorted(existing)},
    }
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("%d written, %d kept, %d cited paths not on this machine" % (len(written), len(kept), len(missing)))
    for p in missing:
        print("  MISSING %s" % p)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
