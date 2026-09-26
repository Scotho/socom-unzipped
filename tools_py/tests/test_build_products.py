"""Build products stay out of the source tree (Sprint 13 Task C5; the code audit's F28, F30, F32, F33 and D8).

`./build.sh recomp` rewrote the tracked r0001 function map in place (`fix_ghidra_csv.py recomp/socom2_ghidra.csv ...`
with no `--out`) on every recomp: the defect `scripts/build_revision.sh` step 0 had already fixed for every other
revision, and the reason issue #54's nested rows were written into a tracked file at all. These cases hold the
rule both lanes now share -- a build reads its sources and writes its products under git-ignored paths, so `git
status` after `./build.sh recomp` or an r0004 build is empty:

  - build.sh's recomp step, read as text: every file it writes (a redirection, a `cp` target, the fixed map,
    the merged ELF, ps2_recomp's output directory, the directory it clears) is neither tracked nor un-ignored;
  - the r0001 config's `ghidra_output` names the fixed map that step writes, so the recompiler compiles the rows
    the build fixed and never the raw tracked map;
  - `recomp/socom2.toml` says it is hand-maintained, and what a build may and may not write;
  - `recomp/socom2_ghidra.toml` (Ghidra's side output, carrying one machine's absolute paths) is gone from the
    index, ignored where the export script would write it again, and read by no build;
  - `recomp/socom2_r0004.toml` stays TRACKED -- its per-line provenance (the r0001 address and the method behind
    every moved address, the `[revision.unresolved]` table) is readable without a disc -- and a regeneration
    from `recomp/socom2.toml`, `game/r0004/match.json` and the two images through step 3's own arguments must
    give its bytes (LF-normalised), so an r0004 build rewrites it to the same content. The regeneration needs the
    disc-derived files, which are git-ignored: it skips without them. `SOCOM_DATA_ROOT` names another checkout
    that has them (an agent worktree reads the main tree's), read-only.
"""
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILD_SH = os.path.join(ROOT, "build.sh")
BUILD_REVISION = os.path.join(ROOT, "scripts", "build_revision.sh")
R0001_TOML = os.path.join(ROOT, "recomp", "socom2.toml")
R0004_TOML = os.path.join(ROOT, "recomp", "socom2_r0004.toml")
GHIDRA_TOML = "recomp/socom2_ghidra.toml"


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def git(*args):
    return subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, text=True)


def in_a_checkout():
    return shutil.which("git") is not None and git("rev-parse", "--is-inside-work-tree").stdout.strip() == "true"


def recomp_body():
    """The body of build.sh's recomp() function, comment lines dropped and continuations joined."""
    m = re.search(r"^recomp\(\) \{\n(.*?)^\}", read(BUILD_SH), re.S | re.M)
    assert m, "build.sh has no recomp() function"
    lines, cur = [], ""
    for raw in m.group(1).splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.endswith("\\"):
            cur += s[:-1] + " "
            continue
        lines.append(cur + s)
        cur = ""
    return lines


def repo_path(word, cwd=""):
    """A build.sh word as a repository-relative path: $ROOT/x -> x, $GEN -> recomp/output, a bare name under cwd."""
    w = word.strip('"').replace("${ROOT}", "$ROOT")
    if w == "$GEN":
        return "recomp/output/"     # a directory: the trailing slash is how git's dir-only patterns match it
    if w.startswith("$ROOT/"):
        return w[len("$ROOT/"):]
    assert "$" not in w, "an output path this reader cannot resolve: %r" % word
    return (cwd + "/" + w) if cwd else w


def toml_value(text, key):
    m = re.search(r'^%s\s*=\s*"([^"]*)"' % re.escape(key), text, re.M)
    return m.group(1) if m else None


def recomp_outputs():
    """(what, repo-relative path) for every file or directory build.sh's recomp step writes."""
    outs = []
    for line in recomp_body():
        cwd = "recomp" if re.search(r'cd "\$ROOT/recomp"', line) else ""
        for target in re.findall(r"(?<![0-9&])>\s*(\"[^\"]+\"|[^\s;)|&]+)", line):
            if target not in ("/dev/null",):
                outs.append(("redirection", repo_path(target, cwd)))
        words = shlex.split(line.replace("(", " ").replace(")", " "), posix=True)
        for i, w in enumerate(words):
            base = os.path.basename(w)
            if base == "fix_ghidra_csv.py":
                args = words[i + 1:]
                if "--out" in args:
                    outs.append(("fix_ghidra_csv --out", repo_path(args[args.index("--out") + 1])))
                else:   # no --out: the tool writes over its first argument, the map it read
                    outs.append(("fix_ghidra_csv in place", repo_path(args[0])))
            elif base == "make_overlay_elf.py":
                first = next(a for a in words[i + 1:] if not a.startswith("--"))
                outs.append(("make_overlay_elf", repo_path(first)))
            elif base == "ps2_recomp.exe":
                toml = os.path.join(ROOT, cwd, words[i + 1])
                out = toml_value(read(toml), "output")
                outs.append(("ps2_recomp output", os.path.normpath(os.path.join(cwd, out)).replace("\\", "/") + "/"))
            elif w == "cp" and i == 0:
                outs.append(("cp", repo_path(words[-1])))
            elif w == "rm" and i == 0:
                outs.extend(("rm", repo_path(a)) for a in words[1:] if not a.startswith("-"))
    return outs


@unittest.skipUnless(in_a_checkout(), "needs git and a checkout")
class BuildShRecompWritesNoTrackedFile(unittest.TestCase):
    def test_the_reader_sees_every_writer(self):
        """The census cannot go vacuous: the four writers the step has had since Sprint 1 are all found."""
        kinds = {k.split(" ")[0] for k, _p in recomp_outputs()}
        for kind in ("fix_ghidra_csv", "make_overlay_elf", "ps2_recomp", "cp", "redirection"):
            self.assertIn(kind, kinds, recomp_outputs())

    def test_no_output_is_tracked(self):
        tracked = [(k, p) for k, p in recomp_outputs() if git("ls-files", "--", p).stdout.strip()]
        self.assertEqual(tracked, [], "build.sh recomp writes into tracked files: `git status` is dirty after it")

    def test_every_output_is_ignored(self):
        # An untracked product that is not ignored is a `??` line in git status -- dirty all the same.
        loose = [(k, p) for k, p in recomp_outputs()
                 if git("check-ignore", "-q", "--no-index", "--", p).returncode != 0]
        self.assertEqual(loose, [], "build.sh recomp writes outside the ignored paths")

    def test_the_fixed_map_goes_under_recomp_build(self):
        fixed = [p for k, p in recomp_outputs() if k.startswith("fix_ghidra_csv")]
        self.assertEqual(len(fixed), 1, fixed)
        self.assertTrue(fixed[0].startswith("recomp/build/"), fixed)


class TheR0001ConfigReadsTheFixedMap(unittest.TestCase):
    def test_ghidra_output_is_what_the_recomp_step_writes(self):
        fixed = [p for k, p in recomp_outputs() if k.startswith("fix_ghidra_csv")]
        named = toml_value(read(R0001_TOML), "ghidra_output")
        # ps2_recomp runs in recomp/ (build.sh's `cd "$ROOT/recomp"`), so the key is relative to it.
        self.assertEqual(["recomp/" + named], fixed,
                         "the recompiler must compile the rows the build fixed, not the raw tracked map")

    def test_the_tracked_map_is_not_what_the_recompiler_reads(self):
        self.assertNotEqual(toml_value(read(R0001_TOML), "ghidra_output"), "socom2_ghidra.csv")


class TheR0001ConfigSaysItIsHandMaintained(unittest.TestCase):
    def header(self):
        head = []
        for line in read(R0001_TOML).splitlines():
            if not line.startswith("#"):
                break
            head.append(line)
        return "\n".join(head)

    def test_the_header_says_hand_maintained(self):
        self.assertIn("HAND-MAINTAINED", self.header())

    def test_the_header_no_longer_claims_a_generator(self):
        self.assertNotIn("Generated by ElfAnalyzer", read(R0001_TOML))

    def test_the_header_says_what_a_build_may_write(self):
        head = self.header()
        self.assertIn("recomp/build/", head)            # where the build's products go
        self.assertIn("never", head)                    # and that this file is not one of them


@unittest.skipUnless(in_a_checkout(), "needs git and a checkout")
class TheGhidraSideTomlIsGone(unittest.TestCase):
    def test_not_tracked(self):
        self.assertEqual(git("ls-files", "--", GHIDRA_TOML).stdout.strip(), "")

    def test_a_ghidra_reexport_there_is_ignored(self):
        # scripts/ghidra_export_functions.sh writes <out>.toml beside <out>.csv.
        for path in (GHIDRA_TOML, "recomp/socom2_ghidra_r0004.toml"):
            self.assertEqual(git("check-ignore", "-q", "--no-index", "--", path).returncode, 0, path)

    def test_no_build_reads_it(self):
        p = git("grep", "-l", "socom2_ghidra.toml", "--", "build.sh", "scripts", "third_party/ps2recomp",
                "ghidra_scripts", "tools_py", ":!tools_py/tests", ":!tools_py/research")
        self.assertEqual(p.stdout.split(), [])


@unittest.skipUnless(in_a_checkout(), "needs git and a checkout")
class OtherRevisionsConfigsAreProducts(unittest.TestCase):
    def test_a_check_build_config_is_ignored(self):
        # build_revision r0001check writes recomp/socom2_r0001check.toml; only r0004's is a tracked record.
        self.assertEqual(git("check-ignore", "-q", "--no-index", "--", "recomp/socom2_r0001check.toml").returncode, 0)

    def test_the_r0004_config_stays_tracked(self):
        self.assertEqual(git("ls-files", "--", "recomp/socom2_r0004.toml").stdout.strip(), "recomp/socom2_r0004.toml")


# ---- the r0004 config is held to what step 3 writes ---------------------------------------------------------

STEP3 = {   # build_revision.sh's in-tree values for REV=r0004, as the lines below assert they are written there
    "--set-input": "../game/overlays_r0004/socom2_game_r0004.elf",
    "--set-output": "./output_r0004/",
    "--set-ghidra-output": "build/socom2_ghidra_r0004.fixed.csv",
    "--set-names": "socom2_names_r0004.csv",
}


class Step3ArgumentsAreTheOnesRegeneratedHere(unittest.TestCase):
    def test_build_revision_writes_these_values(self):
        text = read(BUILD_REVISION)
        for needle in ('TOML_INPUT="../game/overlays_$REV/socom2_game_$REV.elf"; TOML_OUTPUT="./output_$REV/"',
                       'TOML_GHIDRA="build/socom2_ghidra_$REV.fixed.csv"',
                       '--set-ghidra-output "$TOML_GHIDRA" --set-names "$TOML_NAMES" --out "$TOML"',
                       'NAMES_SRC="$ROOT/recomp/socom2_names_$REV.csv"',   # r0004's: TOML_NAMES is its basename
                       '--set-input "$TOML_INPUT" --set-output "$TOML_OUTPUT"',
                       '"$py" -m tools_py.revision_toml "$ROOT/recomp/socom2.toml" "$MATCH"',
                       '--elf-b "$ELF"'):
            self.assertIn(needle, text)


DATA_ROOT = os.path.abspath(os.environ.get("SOCOM_DATA_ROOT") or ROOT)
MATCH = os.path.join(DATA_ROOT, "game", "r0004", "match.json")
ELF_A = os.path.join(DATA_ROOT, "dist", "socom2_game.elf")                          # the report's a.elf
ELF_B = os.path.join(DATA_ROOT, "game", "overlays_r0004", "socom2_game_r0004.elf")  # step 3's --elf-b


@unittest.skipUnless(all(os.path.isfile(p) for p in (MATCH, ELF_A, ELF_B)),
                     "no r0004 match report and images under %s (git-ignored, disc-derived; SOCOM_DATA_ROOT names a "
                     "checkout that has them)" % DATA_ROOT)
class TheTrackedR0004ConfigIsWhatStep3Writes(unittest.TestCase):
    def test_regenerated_equals_tracked(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "socom2_r0004.toml")
            args = [sys.executable, "-m", "tools_py.revision_toml", R0001_TOML, MATCH,
                    "--elf-a", ELF_A, "--elf-b", ELF_B,
                    "--csv-a", os.path.join(ROOT, "recomp", "socom2_ghidra.csv")]
            for flag, value in STEP3.items():
                args += [flag, value]
            p = subprocess.run(args + ["--out", out], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout[-2000:] + p.stderr[-2000:])
            got = read(out)
        if DATA_ROOT != ROOT:   # a report outside this checkout is named as it came (revision_toml.repo_relative)
            got = got.replace(MATCH.replace("\\", "/"), "game/r0004/match.json")
        want = read(R0004_TOML).replace("\r\n", "\n")
        if got != want:
            import difflib
            diff = "".join(list(difflib.unified_diff(want.splitlines(True), got.splitlines(True),
                                                     "tracked", "regenerated"))[:80])
            self.fail("recomp/socom2_r0004.toml is not what step 3 writes -- an r0004 build would leave it "
                      "modified. Regenerate it (this case's command, --out recomp/socom2_r0004.toml) and commit:\n"
                      + diff)


if __name__ == "__main__":
    unittest.main()
