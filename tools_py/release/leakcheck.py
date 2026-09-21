#!/usr/bin/env python3
"""The gate that decides whether this repository may face outward -- one command, exit non-zero on any hit.

    python -m tools_py.release.leakcheck tree               every tracked file, as it is in the working tree
    python -m tools_py.release.leakcheck staged             what `git commit` is about to take (the pre-commit hook)
    python -m tools_py.release.leakcheck ignored            the paths that hold the real secrets are ignored,
                                                            untracked, and were never committed
    python -m tools_py.release.leakcheck metadata           every commit's author and committer identity
    python -m tools_py.release.leakcheck history [REV..]    every added line of every commit on every ref
    python -m tools_py.release.leakcheck artifact <dir>     an unpacked release archive, or any directory
    python -m tools_py.release.leakcheck all                tree + ignored + metadata + history

Exit codes -- three states, not two: **0** clean, **1** findings, **2** the scanner did not run (a missing
target, a shallow clone in history mode, or the planted control it runs on itself first was missed). A gate
that treats "could not scan" as "nothing found" is worse than no gate, because it reports safety it did not
measure -- so a caller must never read 2 as a pass.

Output is `path:line: rule: <masked excerpt>` on stderr, and `--json` writes one object (`tool`, `target`,
`scanned`, `self_test`, `findings`, `exit`) whose excerpts are masked exactly as the terminal's are: a
machine-readable report is MORE likely to be pasted, logged or attached, not less. `--reveal` prints the
matched text unmasked on the terminal only, for whoever is fixing the hit.

Decisions live in `leak_allow.txt` beside this file (a rule, a path glob, an optional literal, and the reason),
so an allowed hit is a reviewed line in a tracked file and not a comment in the code. Owner-specific literals
live in the git-ignored `leak_extra.txt` (`leakrules.EXTRA_FILE`). Sprint 11 Goal 9 is the design; Sprint 10
pulled it forward the day the repository went public.
"""
import argparse
import fnmatch
import io
import json
import os
import subprocess
import sys

from tools_py.release import leakrules as R

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALLOW_FILE = os.path.join(R.HERE, "leak_allow.txt")
BINARY_SNIFF_BYTES = 8 * 1024 * 1024
TEXT_SNIFF_BYTES = 8 * 1024
MAX_LINE = 4000          # a minified or hex-dump line longer than this is scanned in pieces, never skipped

# The paths that hold the real secrets and the owner's data (HANDOFF §5 rule 2, the Sprint 11 spec Goal 9 item 1).
# "It is git-ignored" is a claim with a shelf life; the gate re-proves it on every run: ignored now, not in the
# index now, and never added by any commit on any ref.
SENSITIVE_IGNORED = (
    "vm/", "vm/keys/", "vm/lightsail/", "logs/", "logs/bug_reports/", "game/", "tools/", "research/",
    "dist/", "dist-release/", "dist-linux/", "dist-linux-release/", "server/config/simulated.db",
    "server/logs/", ".claude/skills/s2u-bug-reports/", "ONBOARDING.md", "ghidra_proj/", "recomp/output/",
    "tools_py/release/leak_extra.txt", "mc0/", "mc1/",
)
# Shapes of file that must never be tracked whatever their path (the .gitignore has the same list; this is
# the proof that it held).
SENSITIVE_NAME_RE = R.KEYNAME_PATH_RE


class Hit:
    __slots__ = ("path", "line", "rule", "text", "context")

    def __init__(self, path, line, rule, text, context=""):
        self.path, self.line, self.rule, self.text, self.context = path, line, rule, text, context

    def where(self):
        if self.line:
            return f"{self.path}:{self.line}"
        return f"{self.path}: (file name)" if self.context == "name" else self.path

    def masked_context(self):
        """The line the hit sits on, with the matched text masked -- the context is what lets a reader find
        the hit, and it must not be the thing that leaks it."""
        if not self.context or self.context == "name":
            return ""
        return self.context.replace(self.text, R.mask(self.text)) if self.text else self.context

    def render(self, reveal=False):
        shown = self.text if reveal else R.mask(self.text)
        ctx = (self.context if reveal else self.masked_context()) if self.context != "name" else ""
        return f"{self.where()}: {self.rule}: {shown}" + (f" [{ctx}]" if ctx else "")

    def as_json(self):
        return {"rule": self.rule, "file": self.path, "line": self.line, "excerpt_masked": R.mask(self.text),
                "severity": R.SEVERITY.get(self.rule, "medium"), "context_masked": self.masked_context()}


# --------------------------------------------------------------------------------------------
# the allow list

def load_allow(path=ALLOW_FILE):
    """[(rule, path glob, literal or "", reason)] from `leak_allow.txt`: `rule  glob  [literal]  # reason`.
    A literal with spaces is quoted. A malformed line is a hard error -- an allow list that silently drops a
    line is one that silently allows nothing, or everything."""
    import shlex
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return rows
    for n, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        body, _, reason = line.partition("#")
        parts = shlex.split(body)
        if len(parts) not in (2, 3):
            raise ValueError(f"{path}:{n}: expected `rule glob [literal] # reason`, got {raw!r}")
        rule, glob = parts[0], parts[1]
        lit = parts[2] if len(parts) == 3 else ""
        rows.append((rule, glob, lit, reason.strip()))
    return rows


def allowed(hit, allow):
    for rule, glob, lit, _reason in allow:
        if rule != hit.rule and rule != "*":
            continue
        if not (fnmatch.fnmatchcase(hit.path, glob) or fnmatch.fnmatchcase(hit.path, glob.rstrip("/") + "/*")):
            continue
        if lit and lit.lower() not in (hit.text or "").lower() and lit.lower() not in (hit.context or "").lower():
            continue
        return True
    return False


# --------------------------------------------------------------------------------------------
# scanning one file's bytes

def is_binary(blob):
    head = blob[:TEXT_SNIFF_BYTES]
    return b"\x00" in head


def scan_text(rel, text, trules, hits, stats, line_offset=0):
    for i, line in enumerate(text.splitlines(), 1 + line_offset):
        stats["lines"] += 1
        pieces = [line] if len(line) <= MAX_LINE else [line[j:j + MAX_LINE] for j in range(0, len(line), MAX_LINE)]
        for piece in pieces:
            for rule, fn in trules:
                got = fn(piece)
                if got:
                    hits.append(Hit(rel, i, rule, got, piece.strip()[:200]))


def scan_blob(rel, blob, rules, hits, stats):
    trules, brules, nrules = rules
    for rule, fn in nrules:
        got = fn(rel)
        if got:
            hits.append(Hit(rel, 0, rule, got, "name"))
    stats["files"] += 1
    stats["bytes"] += len(blob)
    if is_binary(blob):
        stats["binary_files"] += 1
        text = blob[:BINARY_SNIFF_BYTES].decode("latin-1")
        for rule, fn in brules:
            got = fn(text)
            if got:
                hits.append(Hit(rel, 0, rule, got, "binary"))
    else:
        stats["text_files"] += 1
        scan_text(rel, blob.decode("utf-8", errors="replace"), trules, hits, stats)


def build_rules(users=None, extras=None, hosted=R.HOSTED_IPS, surface="tree"):
    return (R.text_rules(users, extras, hosted, surface), R.binary_rules(users, extras), R.name_rules(users, extras))


def new_stats():
    return {"files": 0, "text_files": 0, "binary_files": 0, "bytes": 0, "lines": 0, "commits": 0}


# --------------------------------------------------------------------------------------------
# git

def git(args, cwd=ROOT, check=True, binary=False):
    p = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, check=False)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed ({p.returncode}): {p.stderr.decode('utf-8', 'replace').strip()}")
    return p.stdout if binary else p.stdout.decode("utf-8", errors="replace")


def tracked_files(cwd=ROOT):
    out = git(["ls-files", "-z", "--cached", "--full-name"], cwd=cwd, binary=True)
    return [p.decode("utf-8", "replace") for p in out.split(b"\x00") if p]


def staged_files(cwd=ROOT):
    out = git(["diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"], cwd=cwd, binary=True)
    return [p.decode("utf-8", "replace") for p in out.split(b"\x00") if p]


def is_shallow(cwd=ROOT):
    return git(["rev-parse", "--is-shallow-repository"], cwd=cwd).strip() == "true"


# --------------------------------------------------------------------------------------------
# the modes

def check_tree(cwd=ROOT, rules=None, allow=None):
    """Every tracked file, read from the working tree (a tracked file deleted from the tree is skipped: it is
    not going anywhere). Returns (hits, stats)."""
    rules = rules or build_rules()
    hits, stats = [], new_stats()
    for rel in tracked_files(cwd):
        full = os.path.join(cwd, rel)
        if os.path.isdir(full):
            continue                                   # a submodule gitlink: no bytes of ours to scan
        try:
            with open(full, "rb") as fh:
                blob = fh.read()
        except FileNotFoundError:
            continue
        except OSError as e:
            hits.append(Hit(rel, 0, "unreadable", str(e)))
            continue
        scan_blob(rel, blob, rules, hits, stats)
    return _filter(hits, allow), stats


def check_dir(root, rules=None, allow=None):
    """Any directory: an unpacked release archive, a build output, a fixture tree."""
    rules = rules or build_rules()
    hits, stats = [], new_stats()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            try:
                with open(full, "rb") as fh:
                    blob = fh.read()
            except OSError as e:
                hits.append(Hit(rel, 0, "unreadable", str(e)))
                continue
            scan_blob(rel, blob, rules, hits, stats)
    return _filter(hits, allow), stats


def check_staged(cwd=ROOT, rules=None, allow=None):
    """What the index holds for the next commit: each staged file's staged CONTENT (`git show :path`, not the
    working tree's, which may differ), plus two things no content rule sees -- a staged path that the
    .gitignore says is ignored (someone ran `git add -f`), and a staged path shaped like key material."""
    rules = rules or build_rules()
    hits, stats = [], new_stats()
    files = staged_files(cwd)
    for rel in files:
        # `--no-index`, because a path that is in the index is never reported as ignored without it -- and
        # the whole point is that it was just put there over the .gitignore's objection.
        p = subprocess.run(["git", "check-ignore", "--no-index", "-q", "--", rel], cwd=cwd, capture_output=True)
        if p.returncode == 0:
            hits.append(Hit(rel, 0, "forced-ignored-file", rel, "staged although .gitignore ignores it"))
        blob = git(["show", f":{rel}"], cwd=cwd, binary=True)
        scan_blob(rel, blob, rules, hits, stats)
    return _filter(hits, allow), stats


def check_ignored(cwd=ROOT, paths=SENSITIVE_IGNORED, allow=None):
    """The paths that hold the real secrets: ignored by the .gitignore, absent from the index, and never
    added by any commit on any ref. The third needs full history, so a shallow clone makes this mode exit 2."""
    hits, stats = [], new_stats()
    if is_shallow(cwd):
        raise ScanNotRun("history is shallow: `git fetch --unshallow` before the ignored-path check")
    index = set(tracked_files(cwd))
    for path in paths:
        stats["files"] += 1
        # the trailing slash stays: `/dist-linux/` in the .gitignore matches only a directory, and a directory
        # that is not on this disk today is still one the gate must prove ignored
        p = subprocess.run(["git", "check-ignore", "--no-index", "-q", "--", path], cwd=cwd, capture_output=True)
        if p.returncode != 0:
            hits.append(Hit(path, 0, "ignored-path-not-ignored", path, ".gitignore does not match it"))
        bare = path.rstrip("/")
        tracked_now = [t for t in index if t == bare or t.startswith(bare + "/")]
        if tracked_now:
            hits.append(Hit(path, 0, "ignored-path-tracked", tracked_now[0],
                            f"{len(tracked_now)} tracked file(s) under an ignored path"))
        ever = git(["log", "--all", "--format=%h", "--diff-filter=A", "--", bare], cwd=cwd).split()
        if ever:
            hits.append(Hit(path, 0, "ignored-path-in-history", bare, f"added in {len(ever)} commit(s), e.g. {ever[-1]}"))
    # and nothing key-shaped anywhere in the index, whatever its directory
    for rel in sorted(index):
        if SENSITIVE_NAME_RE.search(rel):
            hits.append(Hit(rel, 0, "key-file-name", rel, "name"))
    return _filter(hits, allow), stats


def check_metadata(cwd=ROOT, allow=None):
    """Author and committer identities across all history. A private repository's `user.email` is often a
    personal one; the public one should be deliberate. Every identity is a finding until `leak_allow.txt`
    names it -- the allow list is the record of that decision."""
    hits, stats = [], new_stats()
    out = git(["log", "--all", "--format=%an%x09%ae%x09%cn%x09%ce"], cwd=cwd)
    seen = {}
    for line in out.splitlines():
        stats["commits"] += 1
        an, ae, cn, ce = (line.split("\t") + ["", "", "", ""])[:4]
        seen.setdefault(("commit-author", f"{an} <{ae}>"), 0)
        seen[("commit-author", f"{an} <{ae}>")] += 1
        seen.setdefault(("commit-committer", f"{cn} <{ce}>"), 0)
        seen[("commit-committer", f"{cn} <{ce}>")] += 1
    for (rule, ident), n in sorted(seen.items()):
        hits.append(Hit("<git metadata>", 0, rule, ident, f"{n} commit(s)"))
    return _filter(hits, allow), stats


def check_history(cwd=ROOT, revs=None, rules=None, allow=None):
    """Every ADDED line of every commit reachable from every ref (or from `revs`, a `git log` range), and the
    path of every file each commit adds. Binary diffs are not expanded; their paths are still checked by name.
    Needs full history: a shallow clone exits 2 rather than reporting a clean scan of half the past."""
    rules = rules or build_rules()
    trules, _brules, nrules = rules
    hits, stats = [], new_stats()
    if not revs and is_shallow(cwd):
        raise ScanNotRun("history is shallow: `git fetch --unshallow` before the history scan")
    # `--cc`: a merge shows only what differs from EVERY parent -- the lines a conflict resolution wrote, which no
    # parent's diff carries. `--no-renames`: a moved file is an add, so its content is read again.
    args = ["log", "-p", "--cc", "--no-color", "--no-renames", "--format=%x01commit %H", "--diff-filter=AM"]
    args += list(revs) if revs else ["--all"]
    p = subprocess.Popen(["git"] + args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    commit, path, lineno = "", "", 0
    reader = io.TextIOWrapper(p.stdout, encoding="utf-8", errors="replace", newline="\n")
    for raw in reader:
        line = raw.rstrip("\n")
        if line.startswith("\x01commit "):
            commit = line[8:20]
            stats["commits"] += 1
            path = ""
            continue
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else ""
            lineno = 0
            if path:
                stats["files"] += 1
                for rule, fn in nrules:
                    got = fn(path)
                    if got:
                        hits.append(Hit(path, 0, rule, got, f"name @{commit}"))
            continue
        if line.startswith("@@"):
            try:
                lineno = int(line.split("+", 1)[1].split(",")[0].split(" ")[0]) - 1
            except (IndexError, ValueError):
                lineno = 0
            continue
        if not path or not line.startswith("+") or line.startswith("+++"):
            if line.startswith(" ") or line.startswith("+"):
                lineno += 1
            continue
        lineno += 1
        stats["lines"] += 1
        body = line[1:]
        pieces = [body] if len(body) <= MAX_LINE else [body[j:j + MAX_LINE] for j in range(0, len(body), MAX_LINE)]
        for piece in pieces:
            for rule, fn in trules:
                got = fn(piece)
                if got:
                    hits.append(Hit(path, lineno, rule, got, f"@{commit} {piece.strip()[:160]}"))
    p.wait()
    if p.returncode != 0:
        raise ScanNotRun("git log failed: " + p.stderr.read().decode("utf-8", "replace").strip())
    return _filter(hits, allow), stats


class ScanNotRun(Exception):
    """The scanner could not do its job. Exit 2, never 0."""


def _filter(hits, allow):
    if allow is None:
        allow = load_allow()
    return [h for h in hits if not allowed(h, allow)]


# --------------------------------------------------------------------------------------------
# the control: a scanner that finds nothing is indistinguishable from a broken one

PLANTED = [
    ("private-key-block", "-----BEGIN OPENSSH PRIVATE KEY-----"),
    ("vendor-token", "const k = \"AKIAIOSFODNN7EXAMPLE\";"),
    ("vendor-token", "GITHUB_TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"),
    ("jwt", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27u"),
    ("cf-access-client-id", "CF-Access-Client-Id: 0123456789abcdef0123456789abcdef.access.example"),
    ("cf-access-client-secret", "CF-Access-Client-Secret: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"),
    ("bearer-token", "Authorization: Bearer QWxhZGRpbjpvcGVuIHNlc2FtZQ12345678"),
    ("secret-assignment", "accessToken=hunter2hunter2"),
    ("opaque-secret", "key Zk8Qw2ePlRt7YuIoAs3DfGhJkL9xCvBnMq4Zz here"),
    ("aws-account-id", "arn:aws:iam::123456789012:role/monitor"),
    ("key-file-name", "ssh -i socom_linux.pem ubuntu@host"),
    ("key-file-name", "copied vm/keys/id_rsa to the box"),
    ("home-directory-path", "the disc is at C:\\Users\\craigs\\iso\\socom.iso"),
    ("home-directory-path", "the disc is at /c/Users/craigs/iso/socom.iso"),
    ("home-directory-path", "the disc is at /home/craigs/iso/socom.iso"),
    ("private-ip", "client 192.168.1.50 joined"),
    ("ip-address", "home 86.21.44.190 reached"),
    ("street-address", "delivered to 12 Mulberry Lane, Reading"),
    ("postcode", "posted to SW1A 2AA"),
    ("email", "mail some.person@somewhere-else.org for the key"),
    ("ssh-public-key-body", "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx me@box"),
]
PLANTED_NAMES = [
    ("key-file-name", "vm/keys/id_ed25519"),
    ("key-file-name", "deploy/.secrets/socom_linux.pem"),
    ("key-file-name", "server/.env.production"),
    ("key-file-name", "site/credentials.json"),
]
PLANTED_USER = "Testowner"
PLANTED_EXTRA = "Chateau Griffondor"


def self_test():
    """Run every planted secret through the rules it must trip. Returns {"planted", "caught", "missed": [...]}.
    The rules run with a synthetic owner name and literal so the control does not depend on whose machine it is."""
    # the artifact surface carries every rule the tree surface does, plus private-ip; the control runs on it and
    # then checks the tree surface still catches everything but that one
    trules = R.text_rules(users=[PLANTED_USER], extras=[PLANTED_EXTRA], surface="artifact")
    tree_rules = R.text_rules(users=[PLANTED_USER], extras=[PLANTED_EXTRA], surface="tree")
    nrules = R.name_rules(users=[PLANTED_USER], extras=[PLANTED_EXTRA])
    cases = list(PLANTED) + [("owner-user-name", f"built by {PLANTED_USER} on the PC"),
                             ("owner-literal", f"the place is called {PLANTED_EXTRA}")]
    missed = []
    for rule, body in cases:
        fired = {r for r, fn in trules if fn(body)}
        if rule not in fired:
            missed.append(f"text {rule}: {R.mask(body)}")
        if rule != "private-ip" and rule not in {r for r, fn in tree_rules if fn(body)}:
            missed.append(f"text(tree) {rule}: {R.mask(body)}")
    for rule, name in PLANTED_NAMES:
        fired = {r for r, fn in nrules if fn(name)}
        if rule not in fired:
            missed.append(f"name {rule}: {name}")
    # and the negative half: the project's own identifiers must NOT fire, or the gate gets switched off
    clean = ("harness=dc6a625571d778883146da3911413fe22a69a7f8 "
             "sha256=d6e30021123456789012ababababababababababababababababababababab "
             "hosted 3.143.65.100 / socom.scotho.com, exit 65, 1.2.3.400, mpexit=0, 127.0.0.1:8775 "
             "img/run-s8_voice_open/A_03_name_and_more_here.png best=864.288313900726 "
             "Co-Authored-By: Claude <noreply@anthropic.com> C:\\Users\\<you>\\socom.iso %USERPROFILE%\\x "
             "password: <your password> token=[redacted] PS2X_SOCOM2_LOGIN_PASS=${PASS}")
    false_alarm = [r for r, fn in trules if fn(clean)]
    if false_alarm:
        missed.append("false alarm on the project's own identifiers: " + ", ".join(sorted(set(false_alarm))))
    total = len(cases) + len(PLANTED_NAMES) + 1
    return {"planted": total, "caught": total - len(missed), "missed": missed}


# --------------------------------------------------------------------------------------------
# main

MODES = ("tree", "staged", "ignored", "metadata", "history", "artifact", "all")


def run_mode(mode, args, cwd, rules, allow):
    if mode == "tree":
        return check_tree(cwd, rules, allow)
    if mode == "staged":
        return check_staged(cwd, rules, allow)
    if mode == "ignored":
        return check_ignored(cwd, allow=allow)
    if mode == "metadata":
        return check_metadata(cwd, allow)
    if mode == "history":
        return check_history(cwd, args, rules, allow)
    if mode == "artifact":
        if len(args) != 1 or not os.path.isdir(args[0]):
            raise ScanNotRun("artifact: give one directory that exists")
        return check_dir(args[0], build_rules(surface="artifact"), allow)
    raise ScanNotRun(f"unknown mode {mode}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=MODES)
    ap.add_argument("args", nargs="*", help="history: a rev range; artifact: the directory")
    ap.add_argument("--json", metavar="FILE", help="write the report as JSON (excerpts masked); `-` for stdout")
    ap.add_argument("--reveal", action="store_true", help="print matched text unmasked on the terminal")
    ap.add_argument("--max-report", type=int, default=80, help="how many hits to print (all are counted)")
    ap.add_argument("--allow", default=ALLOW_FILE, help="the allow list (default: leak_allow.txt beside the tool)")
    ap.add_argument("--repo", default=ROOT, help="the repository to scan (default: this one)")
    ap.add_argument("--no-self-test", action="store_true", help="skip the planted control (tests only)")
    a = ap.parse_args(argv)
    err = sys.stderr

    report = {"tool": "leakcheck", "target": a.mode, "scanned": {}, "self_test": {}, "findings": [], "exit": 2}

    def finish(code):
        report["exit"] = code
        if a.json:
            text = json.dumps(report, indent=2)
            if a.json == "-":
                print(text)
            else:
                with open(a.json, "w", encoding="utf-8") as fh:
                    fh.write(text + "\n")
        return code

    if not a.no_self_test:
        st = self_test()
        report["self_test"] = {"planted": st["planted"], "caught": st["caught"], "missed": st["missed"]}
        if st["missed"]:
            print(f"leakcheck: SELF-TEST FAILED -- {len(st['missed'])} of {st['planted']} planted controls missed:", file=err)
            for m in st["missed"]:
                print("  " + m, file=err)
            print("leakcheck: the scanner is broken; this is NOT a clean result.", file=err)
            return finish(2)
    try:
        allow = load_allow(a.allow)
    except ValueError as e:
        print(f"leakcheck: {e}", file=err)
        return finish(2)
    rules = build_rules()
    modes = ["tree", "ignored", "metadata", "history"] if a.mode == "all" else [a.mode]
    hits, totals = [], new_stats()
    try:
        for mode in modes:
            mh, ms = run_mode(mode, a.args, a.repo, rules, allow)
            hits += mh
            for k, v in ms.items():
                totals[k] += v
            print(f"leakcheck[{mode}]: {ms['files']} files ({ms['text_files']} text, {ms['binary_files']} binary), "
                  f"{ms['lines']} lines, {ms['bytes']} bytes, {ms['commits']} commits; {len(mh)} hit(s)")
    except ScanNotRun as e:
        print(f"leakcheck: did not run -- {e}", file=err)
        return finish(2)
    except RuntimeError as e:
        print(f"leakcheck: did not run -- {e}", file=err)
        return finish(2)
    report["scanned"] = totals
    report["findings"] = [h.as_json() for h in hits]
    if not hits:
        print(f"leakcheck: 0 hits -- clean ({', '.join(modes)}; self-test {report['self_test'].get('caught', '-')}/"
              f"{report['self_test'].get('planted', '-')})")
        return finish(0)
    by_rule = {}
    for h in hits:
        by_rule[h.rule] = by_rule.get(h.rule, 0) + 1
    for h in hits[:a.max_report]:
        print(h.render(a.reveal), file=err)
    if len(hits) > a.max_report:
        print(f"... and {len(hits) - a.max_report} more", file=err)
    print("leakcheck: " + ", ".join(f"{k}={v}" for k, v in sorted(by_rule.items())), file=err)
    print(f"leakcheck: FAILED -- {len(hits)} hit(s) in {len({h.path for h in hits})} file(s). Do not publish.", file=err)
    return finish(1)


if __name__ == "__main__":
    sys.exit(main())
