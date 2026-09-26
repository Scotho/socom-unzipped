"""The documentation registry (docs/DOC_MAINTENANCE.md) held to the tree.

Eleven checks, each aimed at a rot mechanism that actually bit this project (the reasons are in
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

    def test_exactly_one_counter_line(self):
        """The counter had two homes, HANDOFF's line and CURRENT_SPRINT's `next ruling:` header line, kept in
        step by hand; on 2026-09-22 they said R242 and R241. From Sprint 14 (Task D2, R273) HANDOFF section 2
        is the one home and docs/RULINGS.md is the index, so a second counter line is a defect."""
        hits = []
        for path in docmaint.by_class("L"):
            if not os.path.isfile(os.path.join(docmaint.ROOT, path)):
                continue
            for i, line in enumerate(docmaint._read(path).split("\n"), 1):
                if docmaint.RULING_LINE.search(line):
                    hits.append((path, i))
        self.assertEqual([p for p, _ in hits], ["docs/HANDOFF.md"],
                         "the next free ruling number is stated once, in docs/HANDOFF.md section 2: %s" % hits)
        header = docmaint._read("docs/CURRENT_SPRINT.md").split("```")[1]
        self.assertIsNone(re.search(r"^next ruling\s*:", header, re.M | re.I),
                          "docs/CURRENT_SPRINT.md's header carries a `next ruling:` line again -- point at "
                          "docs/HANDOFF.md section 2 instead")


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
        """Sprint 13 R4 cut HUMAN_TASKS from 702 lines (82,968 B) to one table of the owner's decisions (9,786 B).

        Its ceiling was lowered to that size plus 25 %; a number back near the old 104,000 would let the
        stack of "Start here" blocks grow again unnoticed.
        """
        path, heading, limit = [c for c in docmaint.CEILINGS if c[0] == "docs/HUMAN_TASKS.md"][0]
        self.assertIsNone(heading)
        self.assertLessEqual(limit, 12500, "raise nothing: archive the old rows (docs/DOC_MAINTENANCE.md check 7)")

    def test_every_ceiling_names_a_block_that_exists(self):
        for path, heading, limit in docmaint.CEILINGS:
            self.assertIsNotNone(docmaint.block_bytes(path, heading),
                                 "%s has no %r block -- a renamed heading must not switch its ceiling off"
                                 % (path, heading))


class ReadFirstBudgetTest(unittest.TestCase):
    """Check 11 (Sprint 14 I4): what a new controller reads before acting stays under 160,000 bytes.

    The review of 2026-09-26 (F1) found HANDOFF's read-first list at 975 KB, a quarter-million tokens before the
    first action. The set is HANDOFF itself, the files its section 3 "Read" step names, the plan CURRENT_SPRINT's
    `plans:` line names, and STATUS's "## Current state" block.
    """

    def test_the_real_read_first_set_is_under_the_budget(self):
        members = docmaint.read_first_bytes()
        paths = [p for p, _ in members]
        total = sum(n for _, n in members)
        listing = docmaint.describe_read_first(members)
        self.assertIn("docs/HANDOFF.md", paths, listing)
        self.assertIn("docs/STATUS.md", paths, listing)
        self.assertIn("docs/CURRENT_SPRINT.md", paths, "HANDOFF section 3 no longer names it: %s" % listing)
        self.assertTrue(any(p.startswith("docs/superpowers/plans/") for p in paths),
                        "CURRENT_SPRINT's plans: line named no plan the parser found: %s" % listing)
        self.assertLessEqual(total, docmaint.READ_FIRST_BUDGET,
                             "over the read-first budget -- shrink or archive, never raise the number: %s" % listing)


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
                                      "dangling_doc_links", "over_ceiling", "unknown_tags",
                                      "duplicate_rulings", "undefined_rulings", "read_first_over") if r[k]}
        self.assertEqual(problems, {}, "python -m tools_py.docmaint says: %s" % problems)

    def test_the_review_stamp_parses(self):
        """Not a calendar check -- only that the line a human stamps at sprint close is still there."""
        text = docmaint._read("docs/DOC_MAINTENANCE.md")
        m = re.search(r"\*\*Last full review:\s*(20\d{2}-\d{2}-\d{2})", text)
        self.assertIsNotNone(m, "docs/DOC_MAINTENANCE.md lost its 'Last full review:' stamp")


class GeneratedBacklogTest(unittest.TestCase):
    """docs/BACKLOG.md (R267) is class G: `python -m tools_py.issues backlog` writes it. Its issue table needs
    the network, so this holds the half that does not -- the head and the ruled-out table against the tracked
    docs/backlog_ruled_out.txt -- through the tool's own `--check --offline`."""

    def test_the_backlog_and_its_list_are_registered(self):
        rows = {r["path"]: r["cls"] for r in docmaint.registry()}
        self.assertEqual(rows.get("docs/BACKLOG.md"), "G")
        self.assertIn("docs/backlog_ruled_out.txt", rows)

    def test_the_backlog_is_not_stale_against_its_ruled_out_list(self):
        from tools_py import issues
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = issues.main(["backlog", "--check", "--offline"])
        self.assertEqual(code, 0, out.getvalue())


class PlantedDefectsTest(unittest.TestCase):
    """A gate that has never failed is not known to work (docs/HAZARDS.md harness).

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
        # ...in a plan, where a ruling is made (HANDOFF section 4 rule 9), so the clean tree cites nothing undefined.
        self.write("docs/superpowers/plans/2026-01-01-plan.md",
                   "# plan\n\n## Rulings made on the owner's behalf\n\n- **R99** (Task 1): the decision.\n")
        self.registry([("README.md", "L"), ("CONTRIBUTING.md", "C"), ("SECURITY.md", "C"),
                       ("THIRD_PARTY_NOTICES.md", "G"), ("docs/DEVELOPING.md", "L"),
                       ("docs/HANDOFF.md", "L"), ("docs/DOC_MAINTENANCE.md", "C")])

    def tearDown(self):
        docmaint.ROOT = self._root
        docmaint.remote_tags = self._tags
        shutil.rmtree(self._tmp, ignore_errors=True)

    def ceiling(self, path, whole=False):
        """The first ceiling on `path` -- or, with whole=True, its whole-file one (HANDOFF has both)."""
        return [c for c in docmaint.CEILINGS if c[0] == path and (not whole or c[1] is None)][0]

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
        self.assertEqual(r["read_first_over"], [])
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

    def test_a_skill_or_an_agent_definition_is_scanned_too(self):
        """Sprint 14 I2: the live procedures are .claude/skills/**/SKILL.md and .claude/agents/*.md."""
        self.write(".claude/skills/some-skill/SKILL.md", "---\nname: some-skill\n---\n\nRead `docs/GONE-SKILL.md`.\n")
        self.write(".claude/agents/some-agent.md", "---\nname: some-agent\n---\n\nRead `docs/GONE-AGENT.md`.\n")
        hits = docmaint.report()["dangling_doc_links"]
        self.assertIn((".claude/skills/some-skill/SKILL.md", 5, "docs/GONE-SKILL.md"), hits)
        self.assertIn((".claude/agents/some-agent.md", 5, "docs/GONE-AGENT.md"), hits)

    def test_a_future_marked_path_in_a_skill_does_not_fire_check_6(self):
        self.write(".claude/skills/some-skill/SKILL.md",
                   "---\nname: some-skill\n---\n\nRead `docs/LATER.md`. <!-- docmaint: future -->\n")
        self.assertEqual(docmaint.report()["dangling_doc_links"], [])

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

    def test_handoff_section_2_ceiling_measures_only_section_2(self):
        """A long section 3 does not fire the section-2 ceiling; the whole-file one (I3) owns the rest."""
        path, heading, limit = self.ceiling("docs/HANDOFF.md")
        self.write(path, "# h\n\nNext free ruling number: R100\n\n## 2. Where it stands\n\n- now\n\n"
                         "## 3. Next\n\n" + "y" * (limit + 100) + "\n")
        self.assertEqual(docmaint.report()["over_ceiling"], [])

    # --- Sprint 14 I3: HANDOFF is transient, and the whole file has a ceiling ---------------------------

    def test_a_handoff_one_byte_over_its_whole_file_ceiling_fires(self):
        """HANDOFF grew to 36 KB doing three jobs (handoff, runbook, postmortem); I3 cut it to the first."""
        path, heading, limit = self.ceiling("docs/HANDOFF.md", whole=True)
        self.assertEqual(limit, 6000)
        head = "# h\n\nNext free ruling number: R100\n\n## 2. Where it stands\n\n- now\n\n## 3. Next\n\n"
        self.write(path, head + "y" * (limit + 1 - len(head) - 1) + "\n")
        self.assertEqual(docmaint.block_bytes(path, None), limit + 1)
        hits = [h for h in docmaint.report()["over_ceiling"] if h[0] == path and h[1] is None]
        self.assertEqual(len(hits), 1, docmaint.report()["over_ceiling"])
        self.assertIn("(whole file)", docmaint.describe_ceiling(hits[0]))
        self.assertIn("6,001", docmaint.describe_ceiling(hits[0]))

    def test_a_handoff_exactly_at_its_whole_file_ceiling_does_not_fire(self):
        """The negative control: 6,000 bytes is inside the ceiling."""
        path, heading, limit = self.ceiling("docs/HANDOFF.md", whole=True)
        head = "# h\n\nNext free ruling number: R100\n\n## 2. Where it stands\n\n- now\n\n## 3. Next\n\n"
        self.write(path, head + "y" * (limit - len(head) - 1) + "\n")
        self.assertEqual(docmaint.block_bytes(path, None), limit)
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

    # --- Sprint 14 I4: check 11, the read-first budget ---------------------------------------------------

    READ_FIRST_HANDOFF = ("# h\n\n## 2. Where it stands\n\nNext free ruling number: R100\n\n"
                          "## 3. Your first hour\n\n1. `bash scripts/install_hooks.sh`.\n"
                          "2. Read `docs/A.md`, then `docs/B.md`, then\n   `CLAUDE.md` (the plans: line names it).\n"
                          "3. Where anything disagrees with `docs/KNOWN.md`, KNOWN wins.\n\n## 4. Rules\n\n- x\n")

    def plant_read_first(self, each):
        self.write("docs/HANDOFF.md", self.READ_FIRST_HANDOFF)
        self.write("docs/A.md", "a" * (each - 1) + "\n")
        self.write("docs/B.md", "b" * (each - 1) + "\n")
        self.write("docs/KNOWN.md", "k" * 300000 + "\n")

    def test_two_90000_byte_members_fire_check_11_with_the_sum_printed(self):
        self.plant_read_first(90000)
        members = docmaint.read_first_bytes()
        self.assertEqual([p for p, _ in members], ["docs/HANDOFF.md", "docs/A.md", "docs/B.md"])
        total = sum(n for _, n in members)
        self.assertGreater(total, 180000)
        over = docmaint.report()["read_first_over"]
        self.assertEqual(len(over), 1, over)
        text = docmaint.describe_read_first(over[0])
        self.assertIn("{:,}".format(total), text)
        self.assertIn("docs/A.md 90,000", text)
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = docmaint.main([])
        self.assertEqual(code, 1, out.getvalue())
        self.assertIn("read_first_over", out.getvalue())
        self.assertIn("{:,}".format(total), out.getvalue())

    def test_a_150000_byte_set_does_not_fire_check_11(self):
        """The negative control; also: a path named outside the Read step (KNOWN here, 300 KB) is not a member."""
        self.plant_read_first(75000)
        self.assertEqual(docmaint.report()["read_first_over"], [])
        self.assertNotIn("docs/KNOWN.md", [p for p, _ in docmaint.read_first_bytes()])
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            docmaint.main([])
        self.assertIn("read-first:", out.getvalue())

    def test_the_plans_line_and_statuss_block_are_members(self):
        self.write("docs/HANDOFF.md", self.READ_FIRST_HANDOFF.replace("`docs/A.md`, then `docs/B.md`",
                                                                      "`docs/CURRENT_SPRINT.md`"))
        self.write("docs/CURRENT_SPRINT.md", "# c\n\n```\nbranch:  x\nplans:   docs/superpowers/plans/2026-01-01-plan.md "
                                             "(the Log), and docs/superpowers/plans/old.md\n```\n")
        self.write("docs/STATUS.md", "# s\n\n## Current state (keep it short)\n\n- now\n\n## Log\n\n" + "z" * 50000 + "\n")
        members = dict(docmaint.read_first_bytes())
        self.assertIn("docs/superpowers/plans/2026-01-01-plan.md", members)
        self.assertNotIn("docs/superpowers/plans/old.md", members)
        self.assertEqual(members["docs/STATUS.md"], docmaint.block_bytes("docs/STATUS.md", "## Current state"))
        self.assertLess(members["docs/STATUS.md"], 100, "the log below STATUS's block must not count")

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

    # --- Sprint 13 R3: one number, one ruling; a cited number has a text ---------------------------------

    def plan(self, rel, body):
        self.write("docs/superpowers/plans/" + rel, "# a plan\n\n## Rulings made on the owner's behalf\n\n" + body)

    def test_a_ruling_defined_twice_fires_with_both_locations(self):
        """R107, R109 and R110 were each issued by two Sprint 8 plans for unrelated decisions (audit D55)."""
        self.plan("a.md", "- **R90** (Task 1): the first decision.\n")
        self.plan("b.md", "intro\n\n- **R90 (2026-09-19).** A different decision.\n")
        hits = docmaint.report()["duplicate_rulings"]
        self.assertEqual(hits, [("R90", [("docs/superpowers/plans/a.md", 5), ("docs/superpowers/plans/b.md", 7)])])

    def test_an_archived_owner_list_restating_a_ruling_is_not_a_second_definition(self):
        """Only a plan, the sprint file and their archives make a ruling (rule 9); the archived HUMAN_TASKS
        restated R246/R247 in the house shape on 2026-09-25 and read as a duplicate until this held."""
        self.plan("a.md", "- **R90** (Task 1): the decision.\n")
        self.write("docs/archive/HUMAN_TASKS-to-2026-09-25.md",
                   "# Archived (2026-09-25): the owner's list, verbatim\n\n- **R90** the decision restated for the owner.\n")
        self.write("docs/archive/CURRENT_SPRINT-sprints-9-to-11.md",
                   "# Archived (2026-09-25): the sprint file's records\n\n- **R91** (2026-09-20): made in the sprint file.\n")
        self.plan("b.md", "- **R91** (2026-09-21): made again.\n")
        hits = docmaint.report()["duplicate_rulings"]
        self.assertEqual([name for name, _ in hits], ["R91"], hits)

    def test_every_house_shape_of_a_definition_is_a_definition(self):
        self.plan("a.md", "- **R90** (Task 1): one.\n"
                          "**R90 -- two.**\n"
                          "- **R90 — three.**\n"
                          "1. **R90, four.**\n"
                          "Mid-line **R90:** five.\n"
                          "  **Ruling R90: six.**\n"
                          "and **R90** (2026-09-25, the controller): seven.\n")
        hits = docmaint.report()["duplicate_rulings"]
        self.assertEqual([len(locs) for _, locs in hits], [7], hits)

    def test_a_citation_is_not_a_definition(self):
        self.plan("a.md", "- **R90** (Task 1): the decision.\n\n"
                          "R90's cost; the stop rule (R90); see **R90** below.\n"
                          "1. **R90 was wrong on its first telling.**\n"
                          "The winner is chosen by **R90**: the smaller wins.\n"
                          "- **R89–R90** (the close): a range restated.\n")
        self.assertEqual(docmaint.report()["duplicate_rulings"], [])

    def test_a_spaced_range_is_not_a_definition(self):
        self.plan("a.md", "- **R90** (Task 1): the decision.\n"
                          "- **R90 – R92** (the close): a range restated.\n"
                          "- **R90 - R92** (the close): again.\n"
                          "**R90 -- R92**: and again.\n")
        self.assertEqual(docmaint.report()["duplicate_rulings"], [])

    def test_a_line_naming_a_number_twice_is_one_location(self):
        self.write("docs/HANDOFF.md", "# h\n\nNext free ruling number: R100\n\nR89 (it corrects R89) and R99.\n")
        self.assertEqual(docmaint.report()["undefined_rulings"], [("R89", [("docs/HANDOFF.md", 5)])])

    def test_a_quote_or_a_code_fence_is_not_a_definition(self):
        self.plan("a.md", "- **R90** (Task 1): the decision.\n\n"
                          "> **R90: the text as it read before it was rewritten.**\n\n"
                          "```\n- **R90** (Task 1): a commit message template\n```\n")
        self.assertEqual(docmaint.report()["duplicate_rulings"], [])

    def test_a_restatement_outside_the_plans_is_not_a_definition(self):
        """HANDOFF section 4 rule 9: a ruling is made in a plan, or in CURRENT_SPRINT when there is none."""
        self.plan("a.md", "- **R90** (Task 1): the decision.\n")
        self.write("docs/HANDOFF.md", "# h\n\nNext free ruling number: R100\n\n- **R90** the decision, restated.\n")
        self.assertEqual(docmaint.report()["duplicate_rulings"], [])

    def test_a_ledger_row_indexes_a_definition_rather_than_repeating_it(self):
        self.plan("a.md", "- **R90** (Task 1): the decision.\n")
        self.write("docs/CURRENT_SPRINT.md", "# cs\n\n#### The rulings ledger\n\n| R | decision | where |\n"
                                             "|---|---|---|\n| R90 | the decision | `plans/a.md` |\n")
        self.assertEqual(docmaint.report()["duplicate_rulings"], [])

    def test_two_ledger_rows_for_one_number_fire(self):
        self.write("docs/CURRENT_SPRINT.md", "# cs\n\n| R90 | one |\n| R90 | two |\n")
        hits = docmaint.report()["duplicate_rulings"]
        self.assertEqual(hits, [("R90", [("docs/CURRENT_SPRINT.md", 3), ("docs/CURRENT_SPRINT.md", 4)])])

    def test_a_second_issue_recorded_as_b_does_not_fire_and_defines_the_b_name(self):
        """Recorded, not renumbered: the second definition carries 'cited as R<n>b' and is counted as R<n>b."""
        self.plan("a.md", "- **R90** (Task 1): the first decision.\n")
        self.plan("b.md", "- **R90** (2026-09-19; *R90 was issued twice; this, the second, is cited as R90b "
                          "from 2026-09-25*): a different decision.\n")
        self.write("docs/HANDOFF.md", "# h\n\nNext free ruling number: R100\n\nR90 and R90b were decided.\n")
        r = docmaint.report()
        self.assertEqual(r["duplicate_rulings"], [])
        self.assertEqual(r["undefined_rulings"], [])

    def test_a_cited_ruling_with_no_definition_fires(self):
        """R114, R116 and R124 were cited for a week with no text anywhere (audit D56)."""
        self.plan("a.md", "- **R90** (Task 1): the decision.\n")
        self.write("docs/HANDOFF.md", "# h\n\nNext free ruling number: R100\n\nR89 was decided (R90).\n")
        hits = docmaint.report()["undefined_rulings"]
        self.assertEqual([h[0] for h in hits], ["R89"])
        self.assertEqual(hits[0][1], [("docs/HANDOFF.md", 5)])

    def test_the_clean_planted_tree_defines_every_ruling_it_cites(self):
        r = docmaint.report()
        self.assertEqual(r["duplicate_rulings"], [])
        self.assertEqual(r["undefined_rulings"], [])

    def test_a_ledger_row_is_a_definition_for_the_undefined_check(self):
        self.write("docs/CURRENT_SPRINT.md", "# cs\n\n| R89 | decided in the ledger itself |\n")
        self.write("docs/HANDOFF.md", "# h\n\nNext free ruling number: R100\n\nR89 and R99 were decided.\n")
        self.assertEqual(docmaint.report()["undefined_rulings"], [])

    def test_a_vacancy_note_in_a_plan_answers_an_undefined_number(self):
        self.plan("a.md", "R89 — vacant: named in a range, never issued.\n")
        self.write("docs/HANDOFF.md", "# h\n\nNext free ruling number: R100\n\nR88, R89 and R99 were decided.\n")
        hits = docmaint.report()["undefined_rulings"]
        self.assertEqual([h[0] for h in hits], ["R88"])

    def test_a_vacancy_note_outside_the_plans_and_ledgers_does_not_count(self):
        self.write("docs/HANDOFF.md", "# h\n\nNext free ruling number: R100\n\nR89 -- vacant: says who? R99.\n")
        self.assertEqual([h[0] for h in docmaint.report()["undefined_rulings"]], ["R89"])

    def test_a_b_citation_needs_its_b_definition(self):
        self.write("docs/HANDOFF.md", "# h\n\nNext free ruling number: R100\n\nR99 and R99b were decided.\n")
        self.assertEqual([h[0] for h in docmaint.report()["undefined_rulings"]], ["R99b"])

    def test_a_sprint_local_name_is_not_a_global_ruling(self):
        """Sprint 12 numbered its own rulings S12-R<n>; S12-R13 is not R13."""
        self.write("docs/HANDOFF.md", "# h\n\nNext free ruling number: R100\n\nR99 amended by S12-R13 and S12-R5.\n")
        self.assertEqual(docmaint.report()["undefined_rulings"], [])

    def test_main_prints_both_locations_of_a_duplicate(self):
        import io
        from contextlib import redirect_stdout
        self.plan("a.md", "- **R90** (Task 1): one.\n")
        self.plan("b.md", "- **R90** (Task 2): two.\n")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(docmaint.main([]), 1)
        self.assertIn("R90 defined 2 times: docs/superpowers/plans/a.md:5; docs/superpowers/plans/b.md:5",
                      out.getvalue())


class ClaudeMdTest(unittest.TestCase):
    """Sprint 14 I1: the root CLAUDE.md the harness loads into every session. It stays short (a line
    ceiling), points at the live documents instead of restating them, names the skills Task I2
    creates (naming them first is the contract), and carries nothing that rots -- no suite count."""

    PATH = os.path.join(docmaint.ROOT, "CLAUDE.md")
    MAX_LINES = 60
    NAMES = ("docs/CURRENT_SPRINT.md", "docs/KNOWN.md", "docs/HUMAN_TASKS.md",
             "loop-iteration", "agent-worktree", "run-gate", "sprint-close")

    def text(self):
        self.assertTrue(os.path.isfile(self.PATH), "CLAUDE.md is missing at the repository root")
        with open(self.PATH, encoding="utf-8") as f:
            return f.read()

    def test_it_exists_and_is_at_most_sixty_lines(self):
        lines = self.text().splitlines()
        self.assertLessEqual(len(lines), self.MAX_LINES,
                             "CLAUDE.md has %d lines; the ceiling is %d -- move detail to docs/DEVELOPING.md"
                             % (len(lines), self.MAX_LINES))

    def test_it_names_the_live_documents_and_the_skills(self):
        text = self.text()
        missing = [n for n in self.NAMES if n not in text]
        self.assertEqual(missing, [], "CLAUDE.md does not name: %s" % missing)

    def test_it_states_no_suite_count(self):
        text = self.text()
        hits = [p.pattern for p in docmaint.COUNT_PATTERNS if p.search(text)]
        self.assertEqual(hits, [], "CLAUDE.md states a suite count (%s); %s owns them"
                         % (hits, docmaint.COUNT_OWNER))

    def test_it_is_registered_as_a_contract(self):
        self.assertIn("CLAUDE.md", docmaint.covered_files())
        rows = {r["path"]: r["cls"] for r in docmaint.registry()}
        self.assertEqual(rows.get("CLAUDE.md"), "C", "CLAUDE.md needs a class C row in docs/DOC_MAINTENANCE.md section 3")


class SkillsTest(unittest.TestCase):
    """Sprint 14 I2: the four procedures are project skills (.claude/skills/<name>/SKILL.md, tracked), each
    with a frontmatter `name:` equal to its directory and a `description:`; docs/LOOP_PROMPT.md is a pointer
    under 2,000 bytes that names the loop's skill; CLAUDE.md's procedure lines point at the SKILL.md files."""

    NAMES = ("loop-iteration", "agent-worktree", "run-gate", "sprint-close")
    LOOP_PROMPT = os.path.join(docmaint.ROOT, "docs", "LOOP_PROMPT.md")
    POINTER_MAX_BYTES = 2000

    def skill_path(self, name):
        return os.path.join(docmaint.ROOT, ".claude", "skills", name, "SKILL.md")

    def frontmatter(self, path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
        self.assertIsNotNone(m, "%s has no YAML frontmatter between --- lines at the top" % path)
        fields = {}
        for line in m.group(1).splitlines():
            k, sep, v = line.partition(":")
            if sep and not line.startswith((" ", "\t")):
                fields[k.strip()] = v.strip()
        return fields

    def test_each_skill_exists_with_its_name_and_a_description(self):
        for name in self.NAMES:
            with self.subTest(skill=name):
                path = self.skill_path(name)
                self.assertTrue(os.path.isfile(path), "missing %s" % path)
                fields = self.frontmatter(path)
                self.assertEqual(fields.get("name"), name, "%s: name: must equal its directory" % path)
                self.assertTrue(fields.get("description"), "%s: description: is empty or missing" % path)

    def test_loop_prompt_is_a_pointer_naming_the_loop_skill(self):
        with open(self.LOOP_PROMPT, "rb") as f:
            data = f.read()
        self.assertLess(len(data), self.POINTER_MAX_BYTES,
                        "docs/LOOP_PROMPT.md is %d bytes; it is a pointer under %d" % (len(data), self.POINTER_MAX_BYTES))
        self.assertIn(b"loop-iteration", data)

    def test_claude_md_points_at_each_skill_file(self):
        with open(os.path.join(docmaint.ROOT, "CLAUDE.md"), encoding="utf-8") as f:
            text = f.read()
        missing = [n for n in self.NAMES if ".claude/skills/%s/SKILL.md" % n not in text]
        self.assertEqual(missing, [], "CLAUDE.md does not point at .claude/skills/<name>/SKILL.md for: %s" % missing)


if __name__ == "__main__":
    unittest.main()
