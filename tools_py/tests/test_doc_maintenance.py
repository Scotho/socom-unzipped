"""The documentation registry (docs/DOC_MAINTENANCE.md) held to the tree.

Eight checks, each aimed at a rot mechanism that actually bit this project (the reasons are in
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


class CeilingsTest(unittest.TestCase):
    """R268: the four documents that grow by appending get a byte ceiling each.

    The 2026-09-25 audit found CURRENT_SPRINT at 190 KB with 12 % of it live, HANDOFF section 2 holding
    twelve pick-up points, and the STATUS "Current state" block at 30 KB of dated bullets under a heading
    that says "keep it short". Nothing retired a block, so the close review read only the newest one.
    """

    def test_the_appending_documents_are_under_their_ceilings(self):
        bad = docmaint.over_ceiling()
        self.assertEqual(
            bad, [],
            "over the R268 ceiling(s): %s -- archive the oldest blocks (docs/archive/, a banner, a registry "
            "row) rather than raising the number" % "; ".join(docmaint.describe_ceiling(b) for b in bad))

    def test_human_tasks_stays_one_table(self):
        """Sprint 13 R4 cut HUMAN_TASKS from 699 lines (82,968 B) to one table of the owner's decisions (9,288 B).

        Its ceiling was lowered to that size plus 25 %; a number back near the old 104,000 would let the
        stack of "Start here" blocks grow again unnoticed.
        """
        path, heading, limit = [c for c in docmaint.CEILINGS if c[0] == "docs/HUMAN_TASKS.md"][0]
        self.assertIsNone(heading)
        self.assertLessEqual(limit, 12000, "raise nothing: archive the old rows (docs/DOC_MAINTENANCE.md check 7)")

    def test_every_ceiling_names_a_block_that_exists(self):
        for path, heading, limit in docmaint.CEILINGS:
            self.assertIsNotNone(docmaint.block_bytes(path, heading),
                                 "%s has no %r block -- a renamed heading must not switch its ceiling off"
                                 % (path, heading))


class TagClaimsTest(unittest.TestCase):
    """R268: "merged to `main` as `vX`" is a claim about origin, and Sprint 11's was written before its tag."""

    def test_every_merged_as_names_a_tag_on_origin(self):
        tags, why = docmaint.remote_tags()
        if tags is None:
            self.skipTest("the tag check did not run -- origin unreachable: %s" % why)
        self.assertEqual(
            docmaint.unknown_tags(tags), [],
            "a live document says 'merged to main as vX' for a tag origin does not list -- write it after "
            "the tag is pushed, or say 'merges ... as' until then")


class RulingScanTest(unittest.TestCase):
    def test_the_ruling_scan_reads_every_archive_file(self):
        """A ledger archived out of a live file must not let the counter walk backwards."""
        sources = docmaint.ruling_sources()
        for rel in docmaint.linked_docs():
            if rel.startswith("docs/archive/"):
                self.assertIn(rel, sources)
        self.assertIn("docs/archive/CURRENT_SPRINT-sprints-9-to-11.md", sources)


class ReportTest(unittest.TestCase):
    def test_the_report_runs_clean_on_this_tree(self):
        r = docmaint.report()
        problems = {k: r[k] for k in ("unregistered", "missing_files", "duplicate_rows",
                                      "count_offenders", "undated_snapshots", "silent_archives",
                                      "dangling_doc_links", "over_ceiling", "unknown_tags") if r[k]}
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
        self._tags = docmaint.remote_tags
        self._tmp = tempfile.mkdtemp(prefix="docmaint_")
        docmaint.ROOT = self._tmp
        # The planted tree is not a clone: origin's tags are planted too, so no test here touches the network.
        docmaint.remote_tags = lambda: ({"v0.10.0", "v0.11.0"}, None)
        for sub in ("docs", "docs/archive", "docs/parity", "docs/story"):
            os.makedirs(os.path.join(self._tmp, sub), exist_ok=True)
        self.write("README.md", "# r\n")
        self.write("CONTRIBUTING.md", "# c\n")
        self.write("SECURITY.md", "# s\n")
        self.write("THIRD_PARTY_NOTICES.md", "# t\n")
        self.write("docs/DEVELOPING.md", "# d\n\nTotal Tests: 764\n")
        self.write("docs/HANDOFF.md", "# h\n\n## 2. Where it stands\n\nNext free ruling number: R100\n\n"
                                     "R99 was decided earlier.\n")
        self.registry([("README.md", "L"), ("CONTRIBUTING.md", "C"), ("SECURITY.md", "C"),
                       ("THIRD_PARTY_NOTICES.md", "G"), ("docs/DEVELOPING.md", "L"),
                       ("docs/HANDOFF.md", "L"), ("docs/DOC_MAINTENANCE.md", "C")])

    def tearDown(self):
        docmaint.ROOT = self._root
        docmaint.remote_tags = self._tags
        shutil.rmtree(self._tmp, ignore_errors=True)

    def ceiling(self, path):
        return [c for c in docmaint.CEILINGS if c[0] == path][0]

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
        self.assertEqual(r["over_ceiling"], [])
        self.assertEqual(r["unknown_tags"], [])
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

    # --- R268: the ceilings -------------------------------------------------------------------------------

    def test_a_sprint_file_over_its_ceiling_fires_and_prints_its_size(self):
        path, _, limit = self.ceiling("docs/CURRENT_SPRINT.md")
        self.write(path, "# cs\n" + "x" * limit + "\n")
        hits = [h for h in docmaint.report()["over_ceiling"] if h[0] == path]
        self.assertEqual(len(hits), 1, docmaint.report()["over_ceiling"])
        self.assertEqual(hits[0][2], limit + 6)
        self.assertIn("{:,}".format(limit + 6), docmaint.describe_ceiling(hits[0]))

    def test_a_sprint_file_under_its_ceiling_does_not_fire(self):
        path, _, limit = self.ceiling("docs/CURRENT_SPRINT.md")
        self.write(path, "# cs\n" + "x" * (limit - 100) + "\n")
        self.assertEqual(docmaint.report()["over_ceiling"], [])

    def test_handoff_section_2_over_its_ceiling_fires(self):
        path, heading, limit = self.ceiling("docs/HANDOFF.md")
        self.write(path, "# h\n\nNext free ruling number: R100\n\n## 1. What\n\nshort\n\n"
                         "## 2. Where it stands\n\n" + "- now\n" * (limit // 6 + 10) + "\n## 3. Next\n\nshort\n")
        self.assertTrue(any(h[0] == path and h[1] == heading for h in docmaint.report()["over_ceiling"]))

    def test_only_handoff_section_2_is_measured(self):
        """The rest of HANDOFF is reference and may be long; only the pick-up block appends."""
        path, heading, limit = self.ceiling("docs/HANDOFF.md")
        self.write(path, "# h\n\nNext free ruling number: R100\n\n## 2. Where it stands\n\n- now\n\n"
                         "## 3. Next\n\n" + "y" * (limit * 2) + "\n")
        self.assertEqual(docmaint.report()["over_ceiling"], [])

    def test_the_status_state_block_over_its_ceiling_fires(self):
        path, heading, limit = self.ceiling("docs/STATUS.md")
        self.write(path, "# s\n\n## Current state (keep it short)\n" + "- 2026-09-25 x\n" * (limit // 15 + 10)
                         + "\n## 2026-09-25 -- the log\n\n" + "z" * (limit * 2) + "\n")
        hits = [h for h in docmaint.report()["over_ceiling"] if h[0] == path]
        self.assertEqual(len(hits), 1)
        self.assertLess(hits[0][2], limit * 2, "the log below the block must not count")

    def test_human_tasks_over_its_ceiling_fires(self):
        path, _, limit = self.ceiling("docs/HUMAN_TASKS.md")
        self.write(path, "# ht\n" + "x" * limit + "\n")
        self.assertTrue(any(h[0] == path for h in docmaint.report()["over_ceiling"]))

    def test_a_renamed_heading_fires_rather_than_switching_the_ceiling_off(self):
        path, heading, limit = self.ceiling("docs/STATUS.md")
        self.write(path, "# s\n\n## State of things\n\n- short\n")
        hits = [h for h in docmaint.report()["over_ceiling"] if h[0] == path]
        self.assertEqual(len(hits), 1)
        self.assertIsNone(hits[0][2])
        self.assertIn("not found", docmaint.describe_ceiling(hits[0]))

    # --- R268: "merged to main as vX" names a tag origin has ---------------------------------------------

    def test_a_merged_as_for_a_missing_tag_fires(self):
        self.write("README.md", "# r\n\nSprint 12 is merged to `main` as `v0.12.0`.\n")
        self.assertIn(("README.md", 3, "v0.12.0"), docmaint.report()["unknown_tags"])

    def test_a_merged_as_for_a_tag_origin_has_does_not_fire(self):
        self.write("README.md", "# r\n\nSprint 11 CLOSED and merged to `main` as `v0.11.0`; also merged to main as v0.10.0.\n")
        self.assertEqual(docmaint.report()["unknown_tags"], [])

    def test_the_merged_as_check_ignores_case(self):
        self.write("README.md", "# r\n\nSprint 12 is Merged to MAIN as V0.12.0.\n")
        self.assertIn(("README.md", 3, "v0.12.0"), docmaint.report()["unknown_tags"])

    def test_a_crlf_checkout_measures_the_same_as_lf(self):
        """A Windows checkout carries CRLF; CI carries LF. The ceiling must not depend on which."""
        path, _, limit = self.ceiling("docs/HUMAN_TASKS.md")
        body = "# ht\n" + ("x" * 99 + "\n") * 10
        with open(os.path.join(self._tmp, "docs", "HUMAN_TASKS.md"), "wb") as fh:
            fh.write(body.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(docmaint.block_bytes(path, None), len(body.encode("utf-8")))
        self.write("docs/HUMAN_TASKS.md", body)
        self.assertEqual(docmaint.block_bytes(path, None), len(body.encode("utf-8")))

    def test_a_struck_through_merged_as_is_a_retraction(self):
        self.write("README.md", "# r\n\n~~Sprint 12 is merged to `main` as `v0.12.0`~~ -- not yet.\n")
        self.assertEqual(docmaint.report()["unknown_tags"], [])

    def test_an_unreachable_origin_skips_the_tag_check_out_loud(self):
        import io
        from contextlib import redirect_stdout
        docmaint.remote_tags = lambda: (None, "could not resolve host")
        self.write("README.md", "# r\n\nSprint 12 is merged to `main` as `v0.12.0`.\n")
        r = docmaint.report()
        self.assertEqual(r["unknown_tags"], [])
        self.assertIn("could not resolve host", r["tag_check_skipped"])
        out = io.StringIO()
        with redirect_stdout(out):
            docmaint.main([])
        self.assertIn("SKIPPED", out.getvalue())

    # --- the ruling scan reads the archive --------------------------------------------------------------

    def test_a_ruling_that_lives_only_in_an_archive_file_still_counts(self):
        self.write("docs/archive/CURRENT_SPRINT-old.md", "# old\n\n> ARCHIVED.\n\n| R250 | a ruling |\n")
        self.assertEqual(docmaint.max_ruling(), (250, "docs/archive/CURRENT_SPRINT-old.md"))

    def test_a_ruling_in_an_archive_subdirectory_still_counts(self):
        self.write("docs/archive/sprints-7-12/plan.md", "# p\n\n> ARCHIVED.\n\nR251 was ruled here.\n")
        self.assertEqual(docmaint.max_ruling()[0], 251)


if __name__ == "__main__":
    unittest.main()
