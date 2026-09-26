"""Sprint 14 E2: the fourth leg of the gate is named only in the gate.

The leg scores twelve frozen scene references that no agent's brief may name (the spec's D6: captures the agents
never see). So the name is kept out of every file an agent reads to write or to review code: no file in the tree
may mention it except tools_py/parity/gate.py, which is the leg, and scripts/parity/merged_chain.sh, the
merged-chain template that runs it. The template lives on another branch until Sprint 14 W2 merges, so its ABSENCE
is accepted: the rule is "nothing else names it", never "the template must".

Excluded from the search, deliberately:
  - docs/ as a whole. The Sprint 14 plan and spec define the leg by name, and two generated pages (the rulings and
    the sitting) carry the word because they quote those; a document describing the rule is not a brief, and the
    generated pages cannot be edited by hand. A skill under .claude/ or a test is NOT excluded.
  - the leg's own reference directory (scripts/parity/refs/<name>/): its pins.json names its own files.
This module never writes the name as one literal (it is built from parts below), or it would be the stray mention.

Three spellings are searched, any case: the joined word anywhere, and the hyphenated and spaced forms when "leg"
follows them. The bare hyphenated and spaced phrase is ordinary English with thirteen unrelated users in the tree (the
symbol-matching tools' hold-out validation, a build.sh comment, a third_party test), so it is matched only when it
names this leg.

One stray is known and listed in KNOWN_STRAYS: .claude/skills/loop-iteration/SKILL.md names the leg in its hyphenated
form in the merged-chain paragraph, and Sprint 14 W2's branch rewrites that paragraph and keeps the word, so the fix
belongs at W2's merge, not in this branch. The list must equal what the search finds: removing the word without
removing the entry fails too.

Also here, because the leg must say so rather than fail obscurely: before the controller's captures exist, the leg
refuses with gate.REFUSE_NO_REFS and says "no references captured yet"; once they exist, it scores. This deviates from
the plan's "fails until the directory exists": a test that stays red until a night capture would keep CI red all day,
so the missing directory is asserted as a refusal (exit 6 and its message) instead.
"""
import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tools_py.parity import gate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEG = "held" + "out"
# The joined word anywhere; the hyphenated and spaced forms only when they name the leg (the docstring says why).
PATTERN = "held" + "(out|[- ]out[[:space:]]+leg)"
KNOWN_STRAYS = [".claude/skills/loop-iteration/SKILL.md"]
ALLOWED = ("tools_py/parity/gate.py", "scripts/parity/merged_chain.sh")
EXCLUDED_PREFIXES = ("docs/", "scripts/parity/refs/" + LEG + "/")


def stray_mentions(paths):
    """Of the repo-relative paths whose content mentions the leg, the ones that may not."""
    out = []
    for p in paths:
        p = p.replace("\\", "/")
        if p in ALLOWED or p.startswith(EXCLUDED_PREFIXES):
            continue
        out.append(p)
    return sorted(out)


def mentioning_files(root=ROOT):
    """Tracked and untracked-but-not-ignored text files under `root` whose content mentions the leg, any case."""
    r = subprocess.run(["git", "grep", "-l", "-I", "-i", "-E", "--untracked", "-e", PATTERN],
                       cwd=root, capture_output=True, text=True)
    if r.returncode not in (0, 1):          # 1: no match
        raise RuntimeError("git grep failed: %s" % r.stderr.strip())
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


class NothingElseNamesTheLeg(unittest.TestCase):
    def test_no_file_outside_the_gate_and_the_template_mentions_it(self):
        self.assertEqual(stray_mentions(mentioning_files()), KNOWN_STRAYS,
                         "the leg is named only in gate.py and the merged-chain template (KNOWN_STRAYS aside; "
                         "a fixed stray leaves the list)")

    def test_the_gate_is_where_it_lives(self):
        with open(os.path.join(ROOT, "tools_py", "parity", "gate.py"), encoding="utf-8") as f:
            self.assertIn(LEG, f.read())


class TheCheckerOnPlantedPaths(unittest.TestCase):
    def test_a_skill_a_test_and_developing_are_stray(self):
        self.assertEqual(stray_mentions([".claude/skills/run-gate/SKILL.md", "tools_py/tests/test_x.py",
                                         "CLAUDE.md"]),
                         [".claude/skills/run-gate/SKILL.md", "CLAUDE.md", "tools_py/tests/test_x.py"])

    def test_the_gate_the_template_the_docs_and_the_references_are_not(self):
        self.assertEqual(stray_mentions(["tools_py/parity/gate.py", "scripts/parity/merged_chain.sh",
                                         "docs/DEVELOPING.md", "docs/superpowers/plans/p.md",
                                         "scripts/parity/refs/%s/pins.json" % LEG]), [])

    def test_the_template_may_be_absent(self):
        self.assertEqual(stray_mentions(["tools_py/parity/gate.py"]), [])

    def test_the_search_finds_a_planted_mention(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        subprocess.run(["git", "init", "-q", tmp], check=True, capture_output=True)
        os.makedirs(os.path.join(tmp, "tools_py", "parity"))
        with open(os.path.join(tmp, "tools_py", "parity", "gate.py"), "w") as f:
            f.write("LEG = '%s'\n" % LEG.upper())
        with open(os.path.join(tmp, "brief.md"), "w") as f:
            f.write("run the %s leg\n" % LEG)
        with open(os.path.join(tmp, "skill.md"), "w") as f:
            f.write("gate -> %s-%s leg -> archive\n" % ("Held", "Out"))       # the hyphenated spelling
        with open(os.path.join(tmp, "note.txt"), "w") as f:
            f.write("then the %s %s  leg of the chain\n" % ("held", "out"))   # the spaced spelling
        with open(os.path.join(tmp, "symbols.py"), "w") as f:                 # the phrase, not the leg
            f.write("# pairs %s-%s in 3 folds; a %s %s pair\n" % ("held", "out", "held", "out"))
        self.assertEqual(stray_mentions(mentioning_files(tmp)), ["brief.md", "note.txt", "skill.md"])


def _leg(run_dir):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = gate.main(["--leg", LEG, run_dir])
    return rc, out.getvalue()


class BeforeTheCaptures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run_dir = os.path.join(self.tmp, "stamp")
        os.makedirs(os.path.join(self.run_dir, "title"))

    def test_no_references_refuses_with_its_own_code_and_says_why(self):
        with mock.patch.object(gate, "LEG_REFS_DIR", os.path.join(self.tmp, "absent")):
            rc, out = _leg(self.run_dir)
        self.assertEqual(rc, gate.REFUSE_NO_REFS)
        self.assertNotIn(rc, (0, 1, 2, 3, 4, 5, 7, 8))
        self.assertIn("no references captured yet", out)

    def test_the_real_tree_refuses_until_the_captures_and_scores_after(self):
        rc, out = _leg(self.run_dir)
        if os.path.isdir(os.path.join(gate.ROOT, gate.LEG_REFS_DIR)):
            self.assertEqual(rc, 1, out)               # nothing captured in the planted run: 0/12, a FAIL
            self.assertIn("%s 0/12" % LEG.upper(), out)
        else:
            self.assertEqual(rc, gate.REFUSE_NO_REFS, out)
            self.assertIn("no references captured yet", out)


if __name__ == "__main__":
    unittest.main()
