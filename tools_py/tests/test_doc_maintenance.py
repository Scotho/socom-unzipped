"""The documentation registry (docs/DOC_MAINTENANCE.md) held to the tree.

Six checks, each aimed at a rot mechanism that actually bit this project (the reasons are in
docs/DOC_MAINTENANCE.md section 0). No build needed, so this runs in CI. Nothing here fails on a
calendar -- cadence is the sprint-close review, a human step with a stamp.
"""
import os
import shutil
import tempfile
import re
import unittest

from tools_py import docmaint


class RegistryShapeTest(unittest.TestCase):
    def test_the_registry_parses_and_every_class_is_known(self):
        rows = docmaint.registry()
        self.assertGreaterEqual(len(rows), 25, "the registry lost its rows -- check the table's pipe format")
        for r in rows:
            self.assertIn(r["cls"], docmaint.CLASSES, r)

    def test_every_covered_document_has_exactly_one_row(self):
        listed = [r["path"] for r in docmaint.registry()]
        missing = [p for p in docmaint.covered_files() if p not in listed]
        self.assertEqual(missing, [], "unclassified document(s): add a row to docs/DOC_MAINTENANCE.md section 3 "
                                      "giving each a class, or move it somewhere section 2 classifies by location")
        dupes = sorted({p for p in listed if listed.count(p) > 1})
        self.assertEqual(dupes, [], "duplicate registry row(s)")

    def test_every_row_points_at_a_file_that_exists(self):
        gone = [r["path"] for r in docmaint.registry()
                if not os.path.isfile(os.path.join(docmaint.ROOT, r["path"]))]
        self.assertEqual(gone, [], "registry row(s) for files that are not there -- a move left the row behind")

    def test_the_registry_registers_itself(self):
        self.assertIn("docs/DOC_MAINTENANCE.md", [r["path"] for r in docmaint.registry()])


class RulingCounterTest(unittest.TestCase):
    """HANDOFF offered R179 while R241 was in use, and a collision had already happened once."""

    def test_handoff_offers_a_next_free_ruling_number(self):
        self.assertIsNotNone(docmaint.next_free_ruling(),
                             "docs/HANDOFF.md lost its 'Next free ruling number: R<n>' line")

    def test_the_next_free_ruling_is_one_past_the_highest_in_use(self):
        highest, where = docmaint.max_ruling()
        self.assertGreater(highest, 0, "no R<n> found at all -- the scan is broken, not the docs")
        self.assertEqual(
            docmaint.next_free_ruling(), highest + 1,
            "docs/HANDOFF.md offers R%s but R%d is already in use (%s). Take your number from HANDOFF "
            "and bump that line in the same commit." % (docmaint.next_free_ruling(), highest, where))


class SingleSourceCountsTest(unittest.TestCase):
    """686/686 had reached four documents; DEVELOPING.md owns the counts."""

    def test_only_developing_md_states_a_suite_count(self):
        bad = docmaint.count_offenders()
        self.assertEqual(
            bad, [],
            "suite count(s) outside %s: %s -- point at that document instead of repeating the number"
            % (docmaint.COUNT_OWNER, bad))

    def test_the_owner_actually_states_one(self):
        text = docmaint._read(docmaint.COUNT_OWNER)
        self.assertTrue(any(p.search(text) for p in docmaint.COUNT_PATTERNS),
                        "%s is supposed to be the single source for the suite counts and states none"
                        % docmaint.COUNT_OWNER)


class SnapshotsAndArchivesTest(unittest.TestCase):
    def test_every_snapshot_is_dated(self):
        self.assertEqual(
            docmaint.undated_snapshots(), [],
            "class-S file(s) with no date in the filename and none in the first 15 lines -- a snapshot "
            "that does not say when it was taken reads as current")

    def test_every_archive_says_it_is_one(self):
        self.assertEqual(
            docmaint.silent_archives(), [],
            "class-A file(s) whose first 15 lines do not say 'archived' or 'superseded' -- an archive "
            "that reads as live is the defect archiving was supposed to prevent")

    def test_the_archive_subdirectories_are_classified_by_location(self):
        """docs/archive/<sub>/**.md is class A by location: no row, but a banner is still required."""
        listed = [r["path"] for r in docmaint.registry()]
        for path in docmaint.archived_by_location():
            self.assertNotIn(path, listed,
                             "%s is class A by location (docs/DOC_MAINTENANCE.md section 2) -- it must not "
                             "also carry a registry row" % path)
            self.assertNotIn(path, docmaint.covered_files())


class DanglingLinksTest(unittest.TestCase):
    """A path written in a document is a claim about the tree, and a move falsifies it silently."""

    def test_no_document_cites_a_docs_path_that_is_not_there(self):
        bad = docmaint.dangling_doc_links()
        self.assertEqual(
            bad, [],
            "backticked docs/ path(s) that are not in the tree: %s -- re-point the citation, or, if it "
            "describes a file that does not exist yet, mark the line '%s'"
            % (bad, docmaint.FUTURE_MARK))


class ReportTest(unittest.TestCase):
    def test_the_report_runs_clean_on_this_tree(self):
        r = docmaint.report()
        problems = {k: r[k] for k in ("unregistered", "missing_files", "duplicate_rows",
                                      "count_offenders", "undated_snapshots", "silent_archives",
                                      "dangling_doc_links") if r[k]}
        self.assertEqual(problems, {}, "python -m tools_py.docmaint says: %s" % problems)

    def test_the_review_stamp_parses(self):
        """Not a calendar check -- only that the line a human stamps at sprint close is still there."""
        text = docmaint._read("docs/DOC_MAINTENANCE.md")
        m = re.search(r"\*\*Last full review:\s*(20\d{2}-\d{2}-\d{2})", text)
        self.assertIsNotNone(m, "docs/DOC_MAINTENANCE.md lost its 'Last full review:' stamp")


class PlantedDefectsTest(unittest.TestCase):
    """A gate that has never failed is not known to work (KNOWN section 4).

    Each check is fired once against a tree built to break exactly it, so a future refactor that
    quietly turns a check into a no-op reddens here instead of passing forever.
    """

    def setUp(self):
        self._root = docmaint.ROOT
        self._tmp = tempfile.mkdtemp(prefix="docmaint_")
        docmaint.ROOT = self._tmp
        for sub in ("docs", "docs/archive", "docs/parity", "docs/story"):
            os.makedirs(os.path.join(self._tmp, sub), exist_ok=True)
        self.write("README.md", "# r\n")
        self.write("CONTRIBUTING.md", "# c\n")
        self.write("SECURITY.md", "# s\n")
        self.write("THIRD_PARTY_NOTICES.md", "# t\n")
        self.write("docs/DEVELOPING.md", "# d\n\nTotal Tests: 764\n")
        self.write("docs/HANDOFF.md", "# h\n\nNext free ruling number: R100\n\nR99 was decided earlier.\n")
        self.registry([("README.md", "L"), ("CONTRIBUTING.md", "C"), ("SECURITY.md", "C"),
                       ("THIRD_PARTY_NOTICES.md", "G"), ("docs/DEVELOPING.md", "L"),
                       ("docs/HANDOFF.md", "L"), ("docs/DOC_MAINTENANCE.md", "C")])

    def tearDown(self):
        docmaint.ROOT = self._root
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write(self, rel, text):
        path = os.path.join(self._tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def registry(self, rows, stamp="2026-01-01"):
        body = ["# Doc maintenance", "", "**Last full review: %s.**" % stamp, "",
                "| Path | Class | Owner | Note |", "|---|---|---|---|"]
        body += ["| `%s` | **%s** | x | |" % (p, c) for p, c in rows]
        self.write("docs/DOC_MAINTENANCE.md", "\n".join(body) + "\n")

    def test_the_clean_planted_tree_passes(self):
        """The control for the controls: without a defect, nothing fires."""
        r = docmaint.report()
        self.assertEqual(r["unregistered"], [])
        self.assertEqual(r["missing_files"], [])
        self.assertEqual(r["count_offenders"], [])
        self.assertEqual(r["undated_snapshots"], [])
        self.assertEqual(r["silent_archives"], [])
        self.assertEqual(r["dangling_doc_links"], [])
        self.assertEqual(r["next_free_ruling"], r["max_ruling"] + 1, "the counter check's own control")

    def test_an_unregistered_document_fires_check_1(self):
        self.write("docs/NEWTHING.md", "# new\n")
        self.assertIn("docs/NEWTHING.md", docmaint.report()["unregistered"])

    def test_a_row_for_a_missing_file_fires_check_1(self):
        self.registry([("docs/GONE.md", "N"), ("docs/DOC_MAINTENANCE.md", "C")])
        self.assertIn("docs/GONE.md", docmaint.report()["missing_files"])

    def test_a_colliding_ruling_number_fires_check_2(self):
        self.write("docs/HANDOFF.md", "# h\n\nNext free ruling number: R100\n\nR240 was decided.\n")
        self.assertEqual(docmaint.max_ruling()[0], 240)
        self.assertNotEqual(docmaint.next_free_ruling(), 241)

    def test_two_counter_lines_that_disagree_are_visible(self):
        self.write("docs/HANDOFF.md", "# h\n\nNext free ruling number: R100\n")
        self.write("docs/CURRENT_SPRINT.md", "# cs\n\nnext ruling:  R101\n")
        self.registry([("docs/HANDOFF.md", "L"), ("docs/CURRENT_SPRINT.md", "L"),
                       ("docs/DOC_MAINTENANCE.md", "C")])
        self.assertEqual(sorted(docmaint.ruling_counters().values()), [100, 101])

    def test_an_undated_suite_count_fires_check_3(self):
        self.write("README.md", "# r\n\nbaselines: C++ 686/686 today\n")
        hits = docmaint.report()["count_offenders"]
        self.assertTrue(any(h[0] == "README.md" for h in hits), hits)

    def test_a_dated_suite_count_does_not_fire_check_3(self):
        self.write("README.md", "# r\n\nRun on 2026-09-21: C++ 686/686.\n")
        self.assertEqual(docmaint.report()["count_offenders"], [])

    def test_a_count_under_a_dated_heading_does_not_fire_check_3(self):
        self.write("README.md", "# r\n\n## 2026-09-18 entry\n\nC++ 554/554 that day.\n")
        self.assertEqual(docmaint.report()["count_offenders"], [])

    def test_an_undated_snapshot_fires_check_4(self):
        self.write("docs/parity/THING.md", "# a report\n\nno date anywhere\n")
        self.registry([("docs/parity/THING.md", "S"), ("docs/DOC_MAINTENANCE.md", "C")])
        self.assertIn("docs/parity/THING.md", docmaint.report()["undated_snapshots"])

    def test_a_silent_archive_fires_check_5(self):
        self.write("docs/archive/OLD.md", "# old thing\n\nreads exactly like a live document\n")
        self.registry([("docs/archive/OLD.md", "A"), ("docs/DOC_MAINTENANCE.md", "C")])
        self.assertIn("docs/archive/OLD.md", docmaint.report()["silent_archives"])

    def test_a_capitalised_banner_is_a_banner(self):
        """The house banner is in capitals; [Aa]rchiv did not match it."""
        self.write("docs/archive/OLD.md", "# old thing\n\n> **ARCHIVED 2026-09-23 -- Sprint 1's spec.**\n")
        self.registry([("docs/archive/OLD.md", "A"), ("docs/DOC_MAINTENANCE.md", "C")])
        self.assertEqual(docmaint.report()["silent_archives"], [])

    def test_a_banded_archive_does_not_fire_check_5(self):
        self.write("docs/archive/OLD.md", "# old thing\n\n> **ARCHIVED.** Superseded by X.\n")
        self.registry([("docs/archive/OLD.md", "A"), ("docs/DOC_MAINTENANCE.md", "C")])
        self.assertEqual(docmaint.report()["silent_archives"], [])

    def test_a_silent_file_in_an_archive_subdirectory_fires_check_5(self):
        """Class A by location: no row is owed, but the banner still is."""
        self.write("docs/archive/sprints-1-6/SPEC.md", "# a sprint spec\n\nreads exactly like a live plan\n")
        self.assertEqual(docmaint.report()["unregistered"], [], "a subdirectory file must owe no row")
        self.assertIn("docs/archive/sprints-1-6/SPEC.md", docmaint.report()["silent_archives"])

    def test_a_banded_file_in_an_archive_subdirectory_does_not_fire_check_5(self):
        self.write("docs/archive/sprints-1-6/SPEC.md",
                   "# a sprint spec\n\n> **ARCHIVED 2026-09-23 -- Sprint 1's spec, closed 2026-09-10.**\n")
        self.assertEqual(docmaint.report()["silent_archives"], [])
        self.assertEqual(docmaint.archived_by_location(), ["docs/archive/sprints-1-6/SPEC.md"])

    def test_a_dangling_docs_path_fires_check_6(self):
        self.write("docs/HANDOFF.md",
                   "# h\n\nNext free ruling number: R100\n\nR99 was decided.\n\nSee `docs/superpowers/specs/gone.md`.\n")
        hits = docmaint.report()["dangling_doc_links"]
        self.assertTrue(any(h[2] == "docs/superpowers/specs/gone.md" for h in hits), hits)
        self.assertTrue(any(h[0] == "docs/HANDOFF.md" for h in hits), hits)

    def test_a_docs_path_that_exists_does_not_fire_check_6(self):
        self.write("docs/HANDOFF.md",
                   "# h\n\nNext free ruling number: R100\n\nR99 was decided.\n\nSee `docs/DEVELOPING.md` and "
                   "`docs/DEVELOPING.md#running` and `docs/DOC_MAINTENANCE.md` section 2.\n")
        self.assertEqual(docmaint.report()["dangling_doc_links"], [])

    def test_a_future_marked_docs_path_does_not_fire_check_6(self):
        self.write("docs/HANDOFF.md",
                   "# h\n\nNext free ruling number: R100\n\nR99 was decided.\n\n"
                   "The installer will write `docs/INSTALL-WINDOWS.md`. <!-- docmaint: future -->\n")
        self.assertEqual(docmaint.report()["dangling_doc_links"], [])

    def test_a_root_document_is_scanned_too(self):
        self.write("README.md", "# r\n\nSee `docs/NOPE.md`.\n")
        self.assertTrue(any(h[0] == "README.md" for h in docmaint.report()["dangling_doc_links"]))

    def test_a_struck_through_path_is_a_retraction_and_does_not_fire_check_6(self):
        self.write("README.md", "# r\n\n~~`docs/research/19-old.md`~~ `docs/DEVELOPING.md` (renumbered).\n")
        self.assertEqual(docmaint.report()["dangling_doc_links"], [])

    def test_a_locator_is_not_part_of_the_path(self):
        self.write("README.md", "# r\n\n`docs/DEVELOPING.md:101` and `docs/DEVELOPING.md:318,355,433-435`.\n")
        self.assertEqual(docmaint.report()["dangling_doc_links"], [])

    def test_a_glob_or_a_placeholder_is_not_a_citation(self):
        self.write("README.md", "# r\n\n`docs/research/**` and `docs/audits/*.md` and `docs/research/<n>-x.md`.\n")
        self.assertEqual(docmaint.report()["dangling_doc_links"], [])


if __name__ == "__main__":
    unittest.main()
