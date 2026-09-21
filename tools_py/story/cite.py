"""The citation test for `docs/STORY.md` -- Sprint 11 Goal 6's teeth.

The goal's bar is that "a test fails if an entry cites something that does not exist". Existence is the
weakest check available, so this does four more:

  * the `Cited:` line is PARSED against a grammar, so a malformed citation fails instead of being skipped;
  * a short hash must be unambiguous (`git rev-parse --verify`), because seven characters collide eventually;
  * the subject fragment a reader sees beside each hash must actually occur in that commit's subject, which
    turns the readable half of the citation into a second assertion rather than decoration;
  * the date and subject stored in `docs/story/timeline.json` must agree with git, which is what catches a
    rewritten history -- a hash that resolves to a DIFFERENT commit passes an existence check.

`/logs/` is git-ignored, so a run citation cannot be checked in a fresh clone at all. Those carry a frozen
witness in the tree (spec 4.3) and the test has three levels, never a fourth called "skipped".

Scope, so nobody widens it by accident: this reads `docs/STORY.md` and `docs/story/timeline.json` and
nothing else. `docs/STATUS.md` cites two commits that no longer resolve (`841a6fc`, `60fe75c`, both
predating the move into this repository at `4b0bbf9`); they are annotated in place and are a STATUS hygiene
task, not this test's business. KNOWN_DEAD below exists so that a citation known to be unresolvable can be
declared once, with a reason, instead of being rediscovered every run.

Usage:
    python -m tools_py.story.cite [--story docs/STORY.md] [--timeline docs/story/timeline.json]
Exit 0 when clean, 1 when any problem is found, 2 on a usage error.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A citation that is known not to resolve, declared once with the reason. An UNLISTED dead citation is a
# failure; a listed one is a record. Keys are the exact ref as written.
KNOWN_DEAD = {
    "841a6fc": "pre-4b0bbf9 history (the VU1 register-file build), lost in the move into this repository; "
               "annotated in place at docs/STATUS.md:1180",
    "60fe75c": "pre-4b0bbf9 history (the first-boot flow to the main menu), lost in the same move; "
               "annotated in place at docs/STATUS.md:2317",
}

# Retracted phrasings (docs/KNOWN.md section 3). The story may tell the story of being wrong; it may not
# state any of these as current. Matched case-insensitively against body text only.
RETRACTED = [
    "frozen at round start",
    "frozen at starting round",
    "ghost flag",
    "depth quantisation causes",
    "depth quantization causes",
    "sharpens the hud",
    "+0x204 is health",
]

# Jargon may appear in a `How:` line or a citation, never in a hook or a body: the owner's bar is that a
# stranger follows the story without knowing what a GS or an IOP is.
JARGON = ["GS", "IOP", "VU0", "VU1", "DMAC", "VIF", "GIF", "CLUT", "XGKICK", "sceMpeg", "FMAC", "SPU", "DMAtag"]

# Items on a Cited: line are separated by a middle dot (or a pipe). Not a comma and not a semicolon: commit
# subjects in this project contain both, and the readable fragment beside a hash quotes the subject.
SEPARATORS = "·|"

# The release entry is written from a template whose fields are marked like this; a document that still
# carries one of these was never finished.
PLACEHOLDERS = ["{{", "}}", "TODO(release)", "RELEASE-TAG-HERE"]

# Pictures: an entry may carry one image line, ![caption](docs/story/img/<file>), and every image the story
# shows must be tracked, must exist, must be under the size budget, and must have a row in
# docs/story/PICTURES.md -- the inventory spec 5.3 asks for, which is also the disc-derived decision table's
# input. The line is the owner's; the test only keeps the list honest.
# A video takes the same slot on the same line, with an .mp4 under the same directory: it gets a budget of its
# own and must have a poster frame beside it (<name>.png, tracked), which is the picture the page shows before
# anyone presses play and the picture a browser without the codec shows instead of nothing.
PICTURE_DIR = "docs/story/img/"
PICTURE_MAX_BYTES = 1_000_000
VIDEO_MAX_BYTES = 12_000_000
VIDEO_EXT = ".mp4"
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_ENTRY_RE = re.compile(r"^###\s+(\d{4}-\d{2}-\d{2})\s+[—–-]+\s+(.+?)\s*$")
_CITED_RE = re.compile(r"^`?Cited:`?\s*(.*)$")
# `<sha>` [(YYYY-MM-DD)] <subject fragment>. The optional date marks a deliberate forward or backward
# reference -- a commit cited under an entry dated on a different day -- and the checker verifies it
# against git, so the marker is an assertion rather than a note.
_SHA_RE = re.compile(r"^`([0-9a-f]{7,40})`\s*(?:\((\d{4}-\d{2}-\d{2})\))?\s*(.*)$")
_RUN_RE = re.compile(r"^(run|gate)\s+([A-Za-z0-9_.\-]+)$")
# A tracked path, optionally back-ticked, optionally followed by a parenthesised note for the reader
# ("docs/STATUS.md (2026-09-08 22:30 entry)"). The note is not checked; the path is.
_PATH_RE = re.compile(r"^`?([A-Za-z0-9_./\-]+/[A-Za-z0-9_./\-]+)`?(?:\s*\(([^()]*)\))?$")
_CODE_SPAN_RE = re.compile(r"`[^`]*`")
_WORD_RE = re.compile(r"[a-z0-9]+")


class Problem(object):
    def __init__(self, where, kind, detail):
        self.where = where
        self.kind = kind
        self.detail = detail

    def __repr__(self):
        return "%s: [%s] %s" % (self.where, self.kind, self.detail)

    def __eq__(self, other):
        return (self.where, self.kind, self.detail) == (other.where, other.kind, other.detail)


class Citation(object):
    def __init__(self, kind, ref, fragment=""):
        self.kind = kind          # "commit" | "run" | "gate" | "log" | "path"
        self.ref = ref
        self.fragment = fragment  # the human-readable subject fragment, commits only
        self.date = None          # a "(YYYY-MM-DD)" marker on a commit cited out of its entry's day

    def __repr__(self):
        return "Citation(%r, %r, %r)" % (self.kind, self.ref, self.fragment)

    @property
    def log_path(self):
        """The path under logs/ that a run, gate or log citation names; None for the other kinds."""
        if self.kind == "run":
            return "logs/parity/" + self.ref
        if self.kind == "gate":
            return "logs/parity/gate/" + self.ref
        if self.kind == "log":
            return self.ref
        return None


class Entry(object):
    def __init__(self, date, title, lines):
        self.date = date
        self.title = title
        self.lines = lines

    @property
    def where(self):
        return "%s %s" % (self.date, self.title)

    def cited_line(self):
        for ln in self.lines:
            stripped = ln.strip()
            if stripped.startswith("Cited:") or stripped.startswith("`Cited:"):
                return stripped
        return None

    def prose_lines(self):
        """Hook and body only: not the How line, not the But line, not the citation line."""
        out = []
        for ln in self.lines:
            s = ln.strip()
            if not s or s.startswith("Cited:") or s.startswith("`Cited:"):
                continue
            if s.startswith("*How:*") or s.startswith("_How:_") or s.startswith("*But:*") or s.startswith("_But:_"):
                continue
            out.append(ln)
        return out


def parse_entries(markdown):
    """Split a story document into its `### <date> - <title>` entries."""
    entries = []
    current = None
    for raw in markdown.splitlines():
        m = _ENTRY_RE.match(raw)
        if m:
            current = Entry(m.group(1), m.group(2), [])
            entries.append(current)
        elif current is not None:
            if raw.startswith("## ") or raw.startswith("# "):
                current = None
            else:
                current.lines.append(raw)
    return entries


def parse_cited(line):
    """Parse a `Cited:` line into citations. Raises ValueError on anything the grammar does not allow."""
    m = _CITED_RE.match(line.strip())
    if not m:
        raise ValueError("not a Cited: line")
    body = m.group(1).strip()
    if not body:
        raise ValueError("Cited: line carries no citation")
    out = []
    for chunk in re.split("[" + SEPARATORS + "]", body):
        item = chunk.strip()
        if not item:
            continue
        m2 = _SHA_RE.match(item)
        if m2:
            c = Citation("commit", m2.group(1), m2.group(3).strip())
            c.date = m2.group(2)
            out.append(c)
            continue
        m3 = _RUN_RE.match(item)
        if m3:
            out.append(Citation(m3.group(1), m3.group(2)))
            continue
        m4 = _PATH_RE.match(item)
        if m4:
            path = m4.group(1).rstrip("/")
            out.append(Citation("log" if path.startswith("logs/") else "path", path))
            continue
        raise ValueError("unparseable citation %r" % item)
    if not out:
        raise ValueError("Cited: line carries no citation")
    return out


def normalise(text):
    return re.sub(r"\s+", " ", text.lower()).strip(" .,;:")


_ARTICLES = {"the", "a", "an", "and"}


def words(text):
    """The alphanumeric words of a fragment or a subject, lower-cased; arrows, dashes and articles dropped,
    so a fragment may read as English without inventing anything."""
    return [w for w in _WORD_RE.findall(text.lower().replace("->", " ").replace("→", " "))
            if w not in _ARTICLES]


def fragment_supports(fragment, subject):
    """The readable fragment beside a hash must be drawn from that commit's subject.

    Elision is allowed -- a 200-character subject is quoted in ten words -- so the test is that every word
    of the fragment occurs in the subject, not that the fragment is a substring. A fragment invented for a
    different commit ("the first online login" beside a sprint-5 ladder hash) fails; a fragment that drops
    the middle of a long subject passes.
    """
    have = set(words(subject))
    return all(w in have for w in words(fragment))


def load_witnesses(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k.replace("\\", "/"): v for k, v in data.get("witnesses", {}).items()}


def digest_path(full):
    """What a witness freezes. A file: its bytes. A directory: its sorted listing, one name per line,
    which is the most a witness can say about a run directory without copying it."""
    if os.path.isfile(full):
        h = hashlib.sha256()
        n = 0
        with open(full, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
                n += len(chunk)
        return n, h.hexdigest()
    if os.path.isdir(full):
        listing = "\n".join(sorted(os.listdir(full))).encode("utf-8")
        return len(os.listdir(full)), hashlib.sha256(listing).hexdigest()
    return None


class GitResolver(object):
    """Answers the questions the checker asks of the repository. Swapped for a fake in the tests."""

    def __init__(self, root=ROOT, ref="HEAD", witnesses=None):
        self.root = root
        self.ref = ref
        self._tracked = None
        self._witnesses = witnesses

    def witness(self, path):
        if self._witnesses is None:
            self._witnesses = load_witnesses(os.path.join(self.root, "docs", "story", "witnesses.json"))
        return self._witnesses.get(path.replace("\\", "/"))

    def logs_present(self):
        """Whether the RUN ARCHIVE is here -- not merely a logs/ directory, which the test suite itself creates
        on any machine, CI included (run 35495411398 called 55 witnesses orphaned that way). The archive is
        recognised by its own marker, logs/ARCHIVED_TO_D.txt, which the owner's machine has carried since
        2026-09-13; STORY_VERIFY_LOGS=1 / =0 forces the answer either way."""
        forced = os.environ.get("STORY_VERIFY_LOGS")
        if forced in ("0", "1"):
            return forced == "1"
        return os.path.isfile(os.path.join(self.root, "logs", "ARCHIVED_TO_D.txt"))

    def size(self, path):
        full = os.path.join(self.root, path)
        return os.path.getsize(full) if os.path.isfile(full) else None

    def picture_inventory(self):
        """The file names that have a row in docs/story/PICTURES.md (a markdown table, file name in backticks)."""
        p = os.path.join(self.root, "docs", "story", "PICTURES.md")
        if not os.path.exists(p):
            return set()
        with open(p, encoding="utf-8") as f:
            return set(re.findall(r"`([^`/]+\.(?:png|jpg|jpeg|webp|mp4))`", f.read()))

    def digest(self, path):
        """(bytes, sha256) of a file under logs/, or of a directory's sorted listing; None when absent."""
        return digest_path(os.path.join(self.root, path))

    def _git(self, *a):
        # Bytes, decoded as UTF-8 by hand: commit subjects in this project carry em dashes and section
        # signs, and text=True would decode them in the console's code page on Windows.
        try:
            p = subprocess.run(["git"] + list(a), cwd=self.root, capture_output=True)
        except OSError as e:                                    # pragma: no cover - git absent
            raise RuntimeError("git unavailable: %s" % e)
        return (p.returncode, p.stdout.decode("utf-8", "replace").strip(),
                p.stderr.decode("utf-8", "replace").strip())

    def commit(self, sha):
        """(full_sha, date, subject) or None. Ambiguity is a miss, deliberately."""
        rc, _, _ = self._git("rev-parse", "--verify", "--quiet", sha + "^{commit}")
        if rc != 0:
            return None
        rc, out, _ = self._git("show", "-s", "--format=%H%x00%ad%x00%s", "--date=short", sha)
        if rc != 0 or out.count("\x00") != 2:
            return None
        full, date, subject = out.split("\x00")
        return full, date, subject

    def reachable(self, sha):
        rc, _, _ = self._git("merge-base", "--is-ancestor", sha, self.ref)
        return rc == 0

    def shallow(self):
        """A shallow clone (CI's default checkout is depth 1) holds almost none of the cited commits. The
        checker then falls back to the data file's stored date and subject -- spec 4.4, decision 4 -- and
        says so, rather than calling 208 real commits dead or skipping the check."""
        if not hasattr(self, "_shallow"):
            rc, out, _ = self._git("rev-parse", "--is-shallow-repository")
            self._shallow = (rc == 0 and out.strip() == "true")
        return self._shallow

    def tracked(self, path):
        if self._tracked is None:
            rc, out, _ = self._git("ls-files")
            self._tracked = set(out.replace("\\", "/").splitlines()) if rc == 0 else set()
        return path.replace("\\", "/") in self._tracked

    def exists(self, path):
        return os.path.exists(os.path.join(self.root, path))


def commit_witnesses(timeline):
    """What the data file stores beside every commit hash -- the citation of record when git cannot answer."""
    out = {}
    for row in (timeline or {}).get("entries", []):
        for c in row.get("citations", []):
            if c.get("kind") == "commit" and c.get("date") and c.get("subject"):
                out[c["ref"]] = (c.get("sha") or c["ref"], c["date"], c["subject"])
    return out


def check_citation(cit, resolver, where, problems, witnesses=None):
    if cit.kind == "commit":
        if cit.ref in KNOWN_DEAD:
            return
        info = resolver.commit(cit.ref)
        from_git = info is not None
        if info is None and resolver.shallow():
            info = (witnesses or {}).get(cit.ref)
        if info is None:
            if resolver.shallow():
                problems.append(Problem(where, "dead-commit",
                                        "%s is not in this shallow clone and docs/story/timeline.json stores no "
                                        "date and subject for it, so nothing can vouch for it" % cit.ref))
            else:
                problems.append(Problem(where, "dead-commit",
                                        "%s does not resolve (or is ambiguous). If it is a known casualty of a "
                                        "history rewrite, declare it in KNOWN_DEAD with a reason." % cit.ref))
            return
        _, date, subject = info
        marked = getattr(cit, "date", None)
        if marked and marked != date:
            problems.append(Problem(where, "date-mismatch",
                                    "%s is marked (%s) but %s dates it %s"
                                    % (cit.ref, marked, "git" if from_git else "the data file", date)))
        if cit.fragment and not fragment_supports(cit.fragment, subject):
            problems.append(Problem(where, "fragment-mismatch",
                                    "%s is cited as %r but its subject is %r" % (cit.ref, cit.fragment, subject)))
        if from_git and not resolver.shallow() and not resolver.reachable(cit.ref):
            problems.append(Problem(where, "unreachable",
                                    "%s exists but is not reachable from the published ref" % cit.ref))
    elif cit.kind in ("run", "gate", "log"):
        check_witness(cit, resolver, where, problems)
    elif cit.kind == "path":
        if not resolver.tracked(cit.ref):
            problems.append(Problem(where, "untracked-path",
                                    "%s is not tracked by git, so a reader of the public repository cannot "
                                    "follow it" % cit.ref))


def check_witness(cit, resolver, where, problems):
    """Spec 4.3. `/logs/` is git-ignored, so a run citation carries a frozen witness in the tree
    (docs/story/witnesses.json) and the check has three levels and no fourth called "skipped":

      1. always, in any clone: the witness exists and is well formed;
      2. when logs/ is present and the file is there: its size and sha256 still match the witness;
      3. when logs/ is present and the file is gone: fail, unless the witness says it was archived.
    """
    path = cit.log_path
    w = resolver.witness(path)
    if w is None:
        problems.append(Problem(where, "no-witness",
                                "%s has no witness in docs/story/witnesses.json, and logs/ is git-ignored, so "
                                "nothing outside this machine can check it (run tools_py.story.witness)" % path))
        return
    for field in ("text", "sha256", "bytes", "captured"):
        if field not in w:
            problems.append(Problem(where, "bad-witness", "%s's witness has no %r" % (path, field)))
            return
    if not resolver.logs_present():
        return
    actual = resolver.digest(path)
    if actual is None:
        if not w.get("archived"):
            problems.append(Problem(where, "witness-orphaned",
                                    "%s is gone from logs/ and its witness does not say it was archived" % path))
        return
    size, digest = actual
    if digest != w["sha256"] or size != w["bytes"]:
        problems.append(Problem(where, "witness-drift",
                                "%s has changed since its witness was captured (%d bytes %s..., witness says "
                                "%d bytes %s...) -- a changed artefact under a citation is louder than a "
                                "missing one" % (path, size, digest[:8], w["bytes"], w["sha256"][:8])))


def check_pictures(entries, resolver, problems):
    inventory = resolver.picture_inventory()
    for entry in entries:
        imgs = _IMG_RE.findall("\n".join(entry.lines))
        if len(imgs) > 1:
            problems.append(Problem(entry.where, "too-many-pictures", "one picture per entry (spec 5.3)"))
        for caption, path in imgs:
            if not path.startswith(PICTURE_DIR):
                problems.append(Problem(entry.where, "picture-outside-dir",
                                        "%s is not under %s, the one published path" % (path, PICTURE_DIR)))
                continue
            if not caption.strip():
                problems.append(Problem(entry.where, "picture-uncaptioned", "%s has no caption" % path))
            if not resolver.tracked(path):
                problems.append(Problem(entry.where, "picture-untracked", "%s is not tracked by git" % path))
            size = resolver.size(path)
            video = path.endswith(VIDEO_EXT)
            budget = VIDEO_MAX_BYTES if video else PICTURE_MAX_BYTES
            if size is None:
                problems.append(Problem(entry.where, "picture-missing", "%s does not exist" % path))
            elif size > budget:
                problems.append(Problem(entry.where, "picture-too-large",
                                        "%s is %d bytes; the budget is %d" % (path, size, budget)))
            if video:
                poster = path[:-len(VIDEO_EXT)] + ".png"
                if resolver.size(poster) is None or not resolver.tracked(poster):
                    problems.append(Problem(entry.where, "video-no-poster",
                                            "%s needs its poster frame %s beside it, tracked" % (path, poster)))
            if os.path.basename(path) not in inventory:
                problems.append(Problem(entry.where, "picture-not-inventoried",
                                        "%s has no row in docs/story/PICTURES.md" % path))


def check_prose(entry, problems):
    prose = "\n".join(entry.prose_lines())
    low = prose.lower()
    for phrase in RETRACTED:
        if phrase in low:
            problems.append(Problem(entry.where, "retracted-claim",
                                    "states %r, which docs/KNOWN.md section 3 retracted" % phrase))
    stripped = _CODE_SPAN_RE.sub(" ", prose)
    for word in JARGON:
        if re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(word), stripped):
            problems.append(Problem(entry.where, "jargon-in-body",
                                    "%r appears outside a How: line or a citation" % word))


def check_timeline(entries, timeline, resolver, problems):
    """The data file and the prose must agree, in both directions, and the data file must agree with git."""
    if timeline is None:
        return
    rows = timeline.get("entries", [])
    by_key = {}
    for row in rows:
        by_key[(row.get("date", ""), normalise(row.get("title", "")))] = row
    for entry in entries:
        key = (entry.date, normalise(entry.title))
        if key not in by_key:
            problems.append(Problem(entry.where, "not-in-timeline",
                                    "the story has this entry and docs/story/timeline.json does not"))
    prose_keys = set((e.date, normalise(e.title)) for e in entries)
    for key, row in by_key.items():
        if key not in prose_keys:
            problems.append(Problem("%s %s" % key, "not-in-story",
                                    "timeline.json has this entry and docs/STORY.md does not"))
        for c in row.get("citations", []):
            if c.get("kind") != "commit":
                continue
            ref = c.get("ref", "")
            if ref in KNOWN_DEAD:
                continue
            info = resolver.commit(ref)
            if info is None:
                if resolver.shallow():
                    continue          # the stored date and subject ARE the witness here; nothing to compare against
                problems.append(Problem("%s %s" % key, "dead-commit", "%s (in timeline.json) does not resolve" % ref))
                continue
            _, date, subject = info
            if c.get("date") and c["date"] != date:
                problems.append(Problem("%s %s" % key, "date-drift",
                                        "%s is recorded as %s and git says %s -- a hash that resolves to a "
                                        "different commit is what a rewritten history produces"
                                        % (ref, c["date"], date)))
            if c.get("subject") and normalise(c["subject"]) != normalise(subject):
                problems.append(Problem("%s %s" % key, "subject-drift",
                                        "%s is recorded as %r and git says %r" % (ref, c["subject"], subject)))


def check(markdown, timeline=None, resolver=None):
    """The whole check. Returns a list of Problem; empty means clean."""
    resolver = resolver or GitResolver()
    problems = []
    witnesses = commit_witnesses(timeline)
    entries = parse_entries(markdown)
    if not entries:
        problems.append(Problem("(document)", "no-entries", "no `### <date> - <title>` entries found"))
    seen = set()
    for entry in entries:
        key = (entry.date, normalise(entry.title))
        if key in seen:
            problems.append(Problem(entry.where, "duplicate-entry", "two entries share a date and a title"))
        seen.add(key)
        line = entry.cited_line()
        if line is None:
            problems.append(Problem(entry.where, "uncited", "no Cited: line -- every dated claim carries one"))
            continue
        try:
            citations = parse_cited(line)
        except ValueError as e:
            problems.append(Problem(entry.where, "unparseable", str(e)))
            continue
        for cit in citations:
            check_citation(cit, resolver, entry.where, problems, witnesses)
        check_prose(entry, problems)
    dates = [e.date for e in entries]
    if dates != sorted(dates):
        problems.append(Problem("(document)", "out-of-order", "entries are not in date order"))
    for token in PLACEHOLDERS:
        if token in markdown:
            problems.append(Problem("(document)", "placeholder",
                                    "%r is in the document -- the release entry's template was pasted in and not "
                                    "filled (docs/story/release-entry.template.md)" % token))
    check_pictures(entries, resolver, problems)
    check_timeline(entries, timeline, resolver, problems)
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check every citation in the progress story.")
    ap.add_argument("--story", default=os.path.join(ROOT, "docs", "STORY.md"))
    ap.add_argument("--timeline", default=os.path.join(ROOT, "docs", "story", "timeline.json"))
    ap.add_argument("--witnesses", default=None, help="default: <root>/docs/story/witnesses.json")
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args(argv)
    if not os.path.exists(args.story):
        sys.stderr.write("no story at %s\n" % args.story)
        return 2
    with open(args.story, encoding="utf-8") as f:
        markdown = f.read()
    timeline = None
    if os.path.exists(args.timeline):
        with open(args.timeline, encoding="utf-8") as f:
            timeline = json.load(f)
    witnesses = load_witnesses(args.witnesses) if args.witnesses else None
    problems = check(markdown, timeline, GitResolver(root=args.root, witnesses=witnesses))
    for p in problems:
        print(p)
    if problems:
        print("\n%d problem(s). A citation that cannot be followed is not a citation." % len(problems))
        return 1
    n = len(parse_entries(markdown))
    resolver = GitResolver(root=args.root)
    if resolver.shallow():
        print("%d entries, every citation resolves -- in a SHALLOW clone: commits were vouched for by the date and "
              "subject stored in docs/story/timeline.json, not by git. Run on a full clone to check against git." % n)
    else:
        print("%d entries, every citation resolves." % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
