"""remap.py's three paths (spec 4.4): a mapped rewrite, an unmapped rewrite with unique subjects, and an
unmapped rewrite with a duplicate subject that must be reported and never auto-resolved. Hermetic: a fake
new history stands in for git."""
import json
import unittest

from tools_py.story import remap

OLD_A = "811b886" + "0" * 33
OLD_B = "5f1de26" + "0" * 33
NEW_A = "aaaaaaa" + "1" * 33
NEW_B = "bbbbbbb" + "1" * 33
NEW_B2 = "bbbbbbb" + "2" * 33

STORY = """### 2026-09-13 - The first kill

**Hook.**

Body.

`Cited:` `811b886` THE ACCEPTANCE TEST PASSED · `5f1de26` first online kill · run s5_t5_ladder2
"""


def timeline():
    return {"schema": 1, "entries": [{"date": "2026-09-13", "title": "The first kill", "citations": [
        {"kind": "commit", "ref": "811b886", "sha": OLD_A, "date": "2026-09-13", "subject": "THE ACCEPTANCE TEST PASSED -- Sprint 5"},
        {"kind": "commit", "ref": "5f1de26", "sha": OLD_B, "date": "2026-09-13", "subject": "first online kill -- ladder launch 2"},
        {"kind": "run", "ref": "s5_t5_ladder2"},
    ]}]}


class FakeHistory(object):
    def __init__(self, commits):
        self.commits = commits   # full sha -> (date, subject)

    def by_date_subject(self, date, subject):
        return [s for s, (d, subj) in self.commits.items() if d == date and remap.cite.normalise(subj) == remap.cite.normalise(subject)]

    def describe(self, sha):
        hit = [s for s in self.commits if s.startswith(sha)]
        if len(hit) != 1:
            return None
        d, subj = self.commits[hit[0]]
        return hit[0], d, subj


class TestMappedRewrite(unittest.TestCase):
    def test_every_hash_moves_through_the_map_and_the_prose_is_untouched(self):
        hist = FakeHistory({NEW_A: ("2026-09-13", "THE ACCEPTANCE TEST PASSED -- Sprint 5 (rewritten)"),
                            NEW_B: ("2026-09-13", "first online kill -- ladder launch 2 (rewritten)")})
        tl, story, resolved, unresolved = remap.remap(timeline(), STORY, [(OLD_A, NEW_A), (OLD_B, NEW_B)], hist)
        self.assertEqual(unresolved, [])
        self.assertEqual([r[1] for r in resolved], ["aaaaaaa", "bbbbbbb"])
        cits = tl["entries"][0]["citations"]
        self.assertEqual(cits[0]["ref"], "aaaaaaa")
        self.assertEqual(cits[0]["subject"], "THE ACCEPTANCE TEST PASSED -- Sprint 5 (rewritten)")
        self.assertIn("`aaaaaaa` THE ACCEPTANCE TEST PASSED", story)
        self.assertIn("`bbbbbbb` first online kill", story)
        self.assertIn("**Hook.**\n\nBody.", story)       # a sentence is never edited
        self.assertEqual(cits[2], {"kind": "run", "ref": "s5_t5_ladder2"})


class TestUnmappedRewriteWithUniqueSubjects(unittest.TestCase):
    def test_falls_back_to_date_and_subject(self):
        hist = FakeHistory({NEW_A: ("2026-09-13", "THE ACCEPTANCE TEST PASSED -- Sprint 5"),
                            NEW_B: ("2026-09-13", "first online kill -- ladder launch 2")})
        tl, story, resolved, unresolved = remap.remap(timeline(), STORY, [], hist)
        self.assertEqual(unresolved, [])
        self.assertTrue(all("(date, subject)" in r[2] for r in resolved))
        self.assertIn("`aaaaaaa`", story)


class TestUnmappedRewriteWithADuplicateSubject(unittest.TestCase):
    def test_a_duplicate_is_reported_and_never_guessed(self):
        hist = FakeHistory({NEW_A: ("2026-09-13", "THE ACCEPTANCE TEST PASSED -- Sprint 5"),
                            NEW_B: ("2026-09-13", "first online kill -- ladder launch 2"),
                            NEW_B2: ("2026-09-13", "first online kill -- ladder launch 2")})
        tl, story, resolved, unresolved = remap.remap(timeline(), STORY, [], hist)
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0][1], "5f1de26")
        self.assertIn("2 commits share", unresolved[0][2])
        self.assertIn("`5f1de26`", story)                # left exactly as it was
        self.assertEqual(tl["entries"][0]["citations"][1]["ref"], "5f1de26")
        self.assertEqual(tl["entries"][0]["citations"][0]["ref"], "aaaaaaa")   # the other one still moves

    def test_a_missing_commit_is_reported(self):
        hist = FakeHistory({NEW_A: ("2026-09-13", "THE ACCEPTANCE TEST PASSED -- Sprint 5")})
        _, _, _, unresolved = remap.remap(timeline(), STORY, [], hist)
        self.assertEqual([u[1] for u in unresolved], ["5f1de26"])
        self.assertIn("no commit", unresolved[0][2])


class TestKnownDeadIsLeftAlone(unittest.TestCase):
    def test_a_declared_dead_hash_is_not_remapped_or_reported(self):
        tl = timeline()
        tl["entries"][0]["citations"][0]["ref"] = "841a6fc"
        hist = FakeHistory({NEW_B: ("2026-09-13", "first online kill -- ladder launch 2")})
        _, _, resolved, unresolved = remap.remap(tl, STORY.replace("811b886", "841a6fc"), [], hist)
        self.assertEqual(unresolved, [])
        self.assertEqual([r[0] for r in resolved], ["5f1de26"])


class TestMapLoading(unittest.TestCase):
    def test_prefix_lookup_is_unambiguous_or_nothing(self):
        pairs = [(OLD_A, NEW_A), ("811b886" + "f" * 33, NEW_B)]
        self.assertIsNone(remap.lookup_in_map(pairs, "811b886"))
        self.assertEqual(remap.lookup_in_map(pairs, "811b8860"), NEW_A)


if __name__ == "__main__":
    unittest.main()
