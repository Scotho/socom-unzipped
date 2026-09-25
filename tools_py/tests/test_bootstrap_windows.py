"""scripts/bootstrap_windows.sh: the first command a stranger on Windows types.

It fetches the pinned llvm-mingw, CMake and Ninja into `tools/`, each verified by sha256, and
`--check` says what is there. It had no test until now, and on 2026-09-21 it stopped a fresh clone at
that very first command: the old `extract into <name>.new, then mv into place` was refused by Git
Bash's `mv` for llvm-mingw's 9314 files ("Permission denied", destination absent, no reparse point,
no read-only bit; PowerShell's Rename-Item on the same path succeeded instantly, and ninja's single
file renamed fine). The repair (`67ff2e8`) extracts straight into `tools/<name>` and writes the
version stamp last, so an interrupted extraction leaves no stamp and the next run redoes it.

These cases hold the contracts that survive that repair, with no network and no 190 MB archive:
`--check`'s three answers, through the script's own `SOCOM_TOOLS_DIR` seam and never against the real
`tools/`, and the shape of the pinned table. The last two are text assertions over the script -- a
blunt instrument, used here because the alternative is downloading a quarter of a gigabyte in a unit
test, and because a silent return of the rename is exactly the regression that cost a fresh clone its
first command.

NOT covered here, and covered instead by running the thing for real: the download, the extraction and
the sha256 refusal. Those were exercised end to end from a genuine `git clone` of the public
repository on 2026-09-21 -- bootstrap from an empty `tools/` in 16 s, `--check` exit 0 after it --
in the run recorded in `docs/archive/sprints-7-12/2026-09-21-sprint-10-disc-to-elf.md`.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "bootstrap_windows.sh")


def script_text():
    with open(SCRIPT, "r", encoding="utf-8") as fh:
        return fh.read()


def pinned_entries():
    """[(name, version, url, sha256, top)] out of the script's ENTRIES table, variables resolved."""
    text = script_text()
    versions = dict(re.findall(r"^([A-Z_]+_VERSION)=(\S+)$", text, re.M))
    entries = []
    for line in re.findall(r'^\s*"([a-z0-9-]+\|[^"]+)"\s*$', text, re.M):
        for var, value in versions.items():
            line = line.replace("$" + var, value)
        name, version, url, sha, top = line.split("|")
        entries.append((name, version, url, sha, top))
    return entries


@unittest.skipUnless(BASH, "bash not found")
class BootstrapCheckTest(unittest.TestCase):
    """--check, against a temporary tools directory. It never downloads: the check path exits before
    any fetch, which is what makes these cases safe to run anywhere, CI included."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bootstrap_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.entries = pinned_entries()

    def stamp(self, name, version):
        """What the script writes as the last step of a tool's installation."""
        os.makedirs(os.path.join(self.tmp, name), exist_ok=True)
        with open(os.path.join(self.tmp, name, ".bootstrap-version"), "w", newline="\n") as fh:
            fh.write(version + "\n")

    def stamp_all(self):
        for name, version, _, _, _ in self.entries:
            self.stamp(name, version)

    def check(self):
        env = dict(os.environ)
        env["SOCOM_TOOLS_DIR"] = self.tmp
        done = subprocess.run([BASH, SCRIPT, "--check"], capture_output=True, text=True, env=env, cwd=ROOT)
        return done.returncode, done.stdout + done.stderr

    def test_an_empty_tools_directory_is_reported_tool_by_tool_and_exits_1(self):
        code, out = self.check()
        self.assertEqual(code, 1, out)
        for name, version, _, _, _ in self.entries:
            self.assertIn("bootstrap: %s wanted %s, have -" % (name, version), out)

    def test_a_fully_stamped_tools_directory_exits_0(self):
        self.stamp_all()
        code, out = self.check()
        self.assertEqual(code, 0, out)
        for name, version, _, _, _ in self.entries:
            self.assertIn("bootstrap: %s %s present" % (name, version), out)
        self.assertNotIn("wanted", out)

    def test_one_missing_stamp_is_the_only_one_reported(self):
        # An extraction that died half-way leaves no stamp -- the repair's whole point.
        self.stamp_all()
        missing = self.entries[0][0]
        os.remove(os.path.join(self.tmp, missing, ".bootstrap-version"))
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("bootstrap: %s wanted" % missing, out)
        for name, version, _, _, _ in self.entries[1:]:
            self.assertIn("bootstrap: %s %s present" % (name, version), out)

    def test_a_stamp_from_another_version_is_refused_and_named(self):
        self.stamp_all()
        name = self.entries[-1][0]
        self.stamp(name, "0.0.0-from-last-year")
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("bootstrap: %s wanted %s, have 0.0.0-from-last-year" % (name, self.entries[-1][1]), out)

    def test_the_check_path_touches_nothing(self):
        before = sorted(os.listdir(self.tmp))
        self.check()
        self.assertEqual(sorted(os.listdir(self.tmp)), before, "--check wrote into the tools directory")


class PinnedTableTest(unittest.TestCase):
    """The table is the security boundary: a version, an https URL that carries it, and a digest."""

    def setUp(self):
        self.entries = pinned_entries()

    def test_three_tools_are_pinned(self):
        self.assertEqual([e[0] for e in self.entries], ["llvm-mingw", "cmake", "ninja"])

    def test_every_entry_carries_a_sha256_and_an_https_url_naming_its_version(self):
        for name, version, url, sha, _ in self.entries:
            self.assertRegex(sha, r"^[0-9a-f]{64}$", name)
            self.assertTrue(url.startswith("https://"), name)
            self.assertIn(version, url, "%s: the URL does not name the version it is pinned to" % name)

    def test_the_archive_is_verified_before_it_is_extracted(self):
        text = script_text()
        mismatch = text.index("sha256 mismatch")
        extract = text.index('"$py" - "$archive"')
        self.assertLess(mismatch, extract, "the extraction must not be able to run on unverified bytes")


class NoRenameRegressionTest(unittest.TestCase):
    """2026-09-21: `mv "$TOOLS/$name.new" "$TOOLS/$name"` was refused on this machine for a freshly
    written 9314-file directory and stopped a fresh clone at its first command. If it comes back,
    this fails. See the module docstring for the whole incident."""

    def test_nothing_is_extracted_under_a_temporary_name_and_renamed_into_place(self):
        offenders = ["%d: %s" % (n, line.strip())
                     for n, line in enumerate(script_text().splitlines(), 1) if ".new" in line]
        self.assertEqual(offenders, [],
                         "bootstrap_windows.sh extracts into a temporary directory again -- the rename "
                         "into place is what stopped a fresh clone on 2026-09-21 (67ff2e8)")
        self.assertIn('"$py" - "$archive" "$TOOLS/$name"', script_text(),
                      "the extraction must write the final directory directly")

    def test_the_version_stamp_is_written_after_the_extraction(self):
        # The stamp is what --check reads, so it must be the last thing that happens: a run that dies
        # in the middle of unpacking has to read as "not installed", not as "installed".
        text = script_text()
        extract = text.index('"$py" - "$archive"')
        stamp = text.index('> "$TOOLS/$name/.bootstrap-version"')
        self.assertLess(extract, stamp)

    def test_the_tools_directory_seam_the_tests_depend_on_is_still_there(self):
        self.assertIn('TOOLS="${SOCOM_TOOLS_DIR:-$ROOT/tools}"', script_text())


if __name__ == "__main__":
    unittest.main()
