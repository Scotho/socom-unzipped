"""Sprint 13 Task C6: every dependency the build or CI downloads is pinned to bytes, not to a name.

- CMake: each `FetchContent_Declare` / `ExternalProject_Add` in a tracked CMakeLists.txt or *.cmake that fetches
  by git names a full 40-hex commit in `GIT_TAG` (a branch or a tag can move under the same name), and each that
  fetches by `URL` carries a literal `URL_HASH SHA256=<64 hex>`. `GIT_SHALLOW TRUE` next to a commit pin is refused
  too: a shallow clone fetches by ref name, so CMake cannot check a bare commit out of one.
- CI: every `pip install` a workflow runs names `package==version`, directly or through the `-r` requirements file
  it installs; an `apt-get install` is not version-pinned (review round 1: the image upgrades the runtime packages a
  -dev pin would hold back) but carries a reviewed marker, and the FFmpeg family's versions are printed into the log.

The CMake files are read as text (no configure: that needs the toolchain and, for the runtime tree, the build
lock); the parser is tested on synthetic blocks below so a regex drift cannot turn the real check vacuous.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF = os.path.join(ROOT, ".github", "workflows")

HEX40 = re.compile(r"^[0-9a-f]{40}$")
URL_HASH = re.compile(r"\bURL_HASH\s+\"?SHA256=[0-9a-fA-F]{64}\"?(?=\s|\))")


def _strip_comments(text):
    """CMake line comments out (a `#` outside a quoted string), so a pin in a comment does not count."""
    out = []
    for line in text.splitlines():
        buf, quoted = [], False
        for ch in line:
            if ch == '"':
                quoted = not quoted
            if ch == "#" and not quoted:
                break
            buf.append(ch)
        out.append("".join(buf))
    return "\n".join(out)


def fetch_blocks(text):
    """(command, name, body) for each FetchContent_Declare / ExternalProject_Add call, parentheses balanced."""
    text = _strip_comments(text)
    out = []
    for m in re.finditer(r"\b(FetchContent_Declare|ExternalProject_Add)\s*\(", text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            i += 1
        body = text[m.end():i - 1]
        name = body.split(None, 1)[0] if body.split() else ""
        out.append((m.group(1), name, body))
    return out


def _arg(body, key):
    m = re.search(r"\b" + key + r"\s+\"?([^\s\")]+)\"?", body)
    return m.group(1) if m else None


def problems(body):
    """What is wrong with one block's pin; empty when it is pinned to bytes."""
    found = []
    if re.search(r"\bGIT_REPOSITORY\b", body):
        tag = _arg(body, "GIT_TAG")
        if not tag or not HEX40.match(tag):
            found.append(f"GIT_TAG {tag!r} is not a 40-hex commit")
        if re.search(r"\bGIT_SHALLOW\s+\"?(TRUE|ON|YES|1)\"?", body, re.I):
            found.append("GIT_SHALLOW with a commit pin (a shallow clone cannot check out a bare commit)")
    elif re.search(r"\bURL\b", body):
        if not URL_HASH.search(body):
            found.append("URL with no literal URL_HASH SHA256=<64 hex>")
    else:
        found.append("neither GIT_REPOSITORY nor URL (a SOURCE_DIR-only declaration needs no pin; say so here)")
    return found


def tracked_cmake_files():
    out = subprocess.run(["git", "ls-files", "--", "*CMakeLists.txt", "*.cmake"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split()
    return sorted(out)


class TheParserSeesWhatItMust(unittest.TestCase):
    def test_a_tag_a_branch_and_a_short_hash_are_refused(self):
        for tag in ("v1.2.3", "main", "Raylib_5_5", "5c3e2a1"):
            with self.subTest(tag=tag):
                body = f"x\n  GIT_REPOSITORY https://example.invalid/x.git\n  GIT_TAG {tag}\n"
                self.assertTrue(problems(body))

    def test_a_commit_passes_and_shallow_beside_it_is_refused(self):
        sha = "0123456789abcdef0123456789abcdef01234567"
        body = f"x\n  GIT_REPOSITORY https://example.invalid/x.git\n  GIT_TAG {sha} # v1.0\n"
        self.assertEqual(problems(_strip_comments(body)), [])
        self.assertTrue(problems(body + "  GIT_SHALLOW TRUE\n"))

    def test_a_url_needs_a_literal_sha256(self):
        url = 'x\n URL "https://example.invalid/a.zip"\n'
        self.assertTrue(problems(url))
        self.assertTrue(problems(url + " URL_HASH SHA256=" + "a" * 63 + "\n"))
        commented = 'ExternalProject_Add(' + url + ' # URL_HASH SHA256=' + "a" * 64 + '\n)'
        self.assertTrue(problems(fetch_blocks(commented)[0][2]))
        self.assertEqual(problems(url + " URL_HASH SHA256=" + "a" * 64 + "\n"), [])

    def test_blocks_are_found_with_nested_parentheses(self):
        text = 'FetchContent_Declare(\n  a\n  GIT_REPOSITORY "u"\n  GIT_TAG "$(x)"\n)\nExternalProject_Add(b URL "v")\n'
        self.assertEqual([(c, n) for c, n, _ in fetch_blocks(text)],
                         [("FetchContent_Declare", "a"), ("ExternalProject_Add", "b")])


class EveryFetchIsPinnedToBytes(unittest.TestCase):
    def test_every_fetch_content_and_external_project_is_pinned(self):
        seen = 0
        for rel in tracked_cmake_files():
            with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            for command, name, body in fetch_blocks(text):
                seen += 1
                with self.subTest(file=rel, dependency=name):
                    self.assertEqual(problems(body), [], f"{rel}: {command}({name})")
        self.assertGreater(seen, 8, "the scan found too few fetches to be looking at the real tree")


def _workflow_run_lines(name):
    with open(os.path.join(WF, name), encoding="utf-8") as fh:
        return fh.read()


def _install_args(text, pattern):
    """The package arguments of each install command matching pattern (backslash continuations joined)."""
    joined = re.sub(r"\\\n\s*", " ", text)
    out = []
    for m in re.finditer(pattern, joined):
        args = [a for a in m.group(1).split() if not a.startswith("-")]
        out.append(args)
    return out


class CiInstallsArePinned(unittest.TestCase):
    """pip: every package a workflow installs is `==`-pinned, on its own line or in the requirements file it names
    with `-r` (H7's root requirements.txt). apt is NOT pinned by version (review round 1): a -dev package depends on
    its runtime package at exactly its own version and the runner image upgrades the runtime packages itself, so a
    pin becomes a downgrade conflict; instead each install is marked reviewed and the FFmpeg family's installed
    versions are printed into the run's log."""
    WORKFLOWS = sorted(f for f in os.listdir(WF) if f.endswith((".yml", ".yaml")))

    @staticmethod
    def _requirement_rows(path):
        rows = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if line:
                    rows.append(line.split(";", 1)[0].strip())   # an environment marker follows the pin
        return rows

    def test_every_pip_install_names_exact_versions(self):
        if not os.path.isfile(os.path.join(ROOT, "requirements.txt")):
            self.skipTest("no requirements.txt yet (Sprint 13 H7 brings it and the workflows' `pip install -r`)")
        pin = r"^[A-Za-z0-9_.\-\[\]]+==[0-9][A-Za-z0-9.+!-]*$"
        seen = 0
        for wf in self.WORKFLOWS:
            for args in _install_args(_workflow_run_lines(wf), r"pip install ([^\n]+)"):
                words = [w for w in args]
                for i, a in enumerate(words):
                    if a.endswith(".txt"):
                        rows = self._requirement_rows(os.path.join(ROOT, a))
                        self.assertTrue(rows, f"{wf}: {a} has no rows")
                        for row in rows:
                            seen += 1
                            with self.subTest(workflow=wf, requirements=a, row=row):
                                self.assertRegex(row, pin)
                        continue
                    seen += 1
                    with self.subTest(workflow=wf, package=a):
                        self.assertRegex(a, pin)
        self.assertGreater(seen, 0)

    def test_every_apt_install_is_reviewed_and_the_ffmpeg_versions_are_logged(self):
        seen = 0
        for wf in self.WORKFLOWS:
            text = _workflow_run_lines(wf)
            installs = _install_args(text, r"apt-get install ([^\n]+)")
            if not installs:
                continue
            seen += len(installs)
            with self.subTest(workflow=wf):
                self.assertEqual(len(re.findall(r"#\s*apt-unpinned \(reviewed\):", text)), len(installs),
                                 f"{wf}: each apt-get install carries an `# apt-unpinned (reviewed):` line saying why")
                if any(a.startswith("libavcodec") for args in installs for a in args):
                    self.assertRegex(text, r"dpkg-query -W 'libavcodec\*'",
                                     f"{wf} installs FFmpeg and must print the versions it built against")
        self.assertGreater(seen, 0)


if __name__ == "__main__":
    unittest.main()
