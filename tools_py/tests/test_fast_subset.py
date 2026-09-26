"""tools_py/tests/fast.py, the lock-free fast subset (Sprint 13 H7): its exclusions name real things, it runs what it
does not exclude, and its command line is not on scripts/loop_lock.sh's busy list."""
import os
import re
import unittest

from tools_py.tests import fast

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Exclusions(unittest.TestCase):
    def test_every_exclusion_names_a_module_class_or_method_that_exists(self):
        loader = unittest.TestLoader()
        stale = []
        for name in fast.EXCLUDED:
            try:
                found = loader.loadTestsFromName("%s.%s" % (fast.PACKAGE, name))
            except (AttributeError, ImportError) as e:
                stale.append("%s (%s)" % (name, e))
                continue
            if found.countTestCases() == 0:
                stale.append("%s (no tests)" % name)
        self.assertEqual(stale, [], "EXCLUDED entries that name nothing: the subset would drift silently")

    def test_every_exclusion_says_why(self):
        self.assertEqual([k for k, v in fast.EXCLUDED.items() if not v.strip()], [])

    def test_what_is_not_excluded_runs(self):
        ids = {t.id() for t in fast._flatten(fast.suite())}
        self.assertIn("tools_py.tests.test_gate.TitleScoring.test_fixture_run_passes", ids)
        self.assertIn("tools_py.tests.test_fast_subset.Exclusions.test_what_is_not_excluded_runs", ids)
        self.assertNotIn("tools_py.tests.test_gate.MissionSeeing.test_mission_stage_launches_with_the_probe_peek_spec",
                         ids)
        self.assertFalse(any(i.startswith("tools_py.tests.test_loop_lock.") for i in ids))
        self.assertGreater(len(ids), 1000)


class OffTheBusyList(unittest.TestCase):
    """loop_lock.sh counts a python whose command line matches its patterns as busy; the fast subset must not."""

    def test_the_command_line_matches_no_busy_pattern(self):
        with open(os.path.join(ROOT, "scripts", "loop_lock.sh"), encoding="utf-8") as f:
            line = next(l for l in f if "name ~ /^python/" in l)
        patterns = re.findall(r"cmd ~ /([^/]+)/", line)
        self.assertEqual(len(patterns), 2, line)
        self.assertTrue(any(re.search(p, "python -m unittest discover -s tools_py/tests -t .") for p in patterns))
        self.assertFalse(any(re.search(p, "python -m tools_py.tests.fast") for p in patterns))


if __name__ == "__main__":
    unittest.main()
