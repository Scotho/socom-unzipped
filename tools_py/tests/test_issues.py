"""tools_py/issues.py: the known-issue stack's shape, without the network.

Every case here runs on planted text or a planted `gh issue list --json` listing; nothing calls gh, because a
test that touched the owner's public repository from a test run would be a write nobody reviewed
(docs/HANDOFF.md rule 13). What is checked is what actually goes wrong with an issue tracker kept beside a
document: a row citing an issue that was closed, a row that says closed while the issue is open, an issue
nobody's row owns, a body that lost the section the closing comment has to answer, a label set that drifted
from the script that creates it, a live-document list that drifted from the registry, and the things that must
never reach a public issue -- a home path, an address, a token, or anything from a bug report but its id.
The `--json` replay is driven end to end through main(), so the offline path a reviewer is told to use is the
path that is tested.
"""
import contextlib
import io
import json
import os
import re
import tempfile
import unittest

from tools_py import docmaint
from tools_py import issues

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GOOD_BODY = """Reported: docs/KNOWN.md section 2, 2026-09-23.

## What happens
The title stage scores the last four menu captures at 60-88 and the gate still passes.

## Evidence
`logs/parity/gate/s9_p7_playtest_gate/summary.txt`, captures s19..s22.

## Where it is written
docs/KNOWN.md section 2, "The title stage quietly lost four captures".

## Closing bar
The four captures score >= 90 again on a gate, or the references are re-recorded with the change written down.
"""


class SkeletonTest(unittest.TestCase):
    def test_the_skeleton_carries_every_required_section(self):
        for heading in issues.SECTIONS:
            self.assertIn(heading, issues.SKELETON)

    def test_the_skeleton_itself_is_refused(self):
        problems = issues.check_body(issues.SKELETON)
        self.assertTrue(problems, "an unfilled skeleton must not reach GitHub")
        self.assertTrue(any("placeholder" in p for p in problems))


class CheckBodyTest(unittest.TestCase):
    def test_a_filled_body_passes(self):
        self.assertEqual(issues.check_body(GOOD_BODY), [])

    def test_a_missing_section_fails(self):
        body = GOOD_BODY.replace("## Closing bar", "## Bar")
        problems = issues.check_body(body)
        self.assertTrue(any("Closing bar" in p for p in problems), problems)

    def test_an_empty_section_fails(self):
        body = re.sub(r"## Evidence\n.*?\n\n", "## Evidence\n\n", GOOD_BODY, flags=re.S)
        problems = issues.check_body(body)
        self.assertTrue(any("Evidence" in p and "empty" in p for p in problems), problems)

    def test_a_home_path_fails(self):
        for path in (r"C:\Users\bob\game.iso", "/home/bob/game.iso", "/Users/bob/game.iso"):
            body = GOOD_BODY + "\n## Notes\nseen at %s\n" % path
            problems = issues.check_body(body)
            self.assertTrue(any("home directory" in p for p in problems), (path, problems))

    def test_an_email_address_fails(self):
        problems = issues.check_body(GOOD_BODY + "\n## Notes\nreporter someone@example.com\n")
        self.assertTrue(any("e-mail" in p for p in problems), problems)

    def test_a_br_id_is_allowed_only_in_the_one_sentence(self):
        ok = "Reported through the launcher as BR-20260919-abc123.\n" + GOOD_BODY.split("\n", 1)[1]
        self.assertEqual(issues.check_body(ok), [])
        bad = GOOD_BODY + "\n## Notes\nthe report BR-20260919-abc123 said the sound was wrong\n"
        problems = issues.check_body(bad)
        self.assertTrue(any("BR-" in p for p in problems), problems)

    def test_the_leak_checks_rules_guard_the_body_too(self):
        # An address the tree would refuse at the commit (a routable IP that is not the hosted box's) and a
        # vendor token shape are refused here with the rule's name, so the writer is not the only check.
        # Built at run time, in pieces, so the tree's own leak check (the pre-commit hook) does not read this
        # file as carrying a real address or token -- the same reason leakcheck's self-test plants its shapes.
        ip = ".".join(("93", "184", "216", "34"))
        token = "ghp_" + "0123456789" + "abcdefghij" + "ABCDEFGHIJ" + "012345"
        for planted, rule in (("seen from %s during the round" % ip, "ip-address"),
                              (token, "vendor-token")):
            problems = issues.check_body(GOOD_BODY + "\n## Notes\n%s\n" % planted)
            self.assertTrue(any("leak check" in p and rule in p for p in problems), (planted, problems))


class CitationsTest(unittest.TestCase):
    TEXT = ("| **A row (issue #12).** text | bar |\n"
            "| **A settled row (issue #13 (closed)).** | done |\n"
            "PR #244 upstream is not one of ours; neither is a bare #99 nor R251.\n"
            "Issue #12 again, in another case.\n")

    def test_only_the_issue_form_counts(self):
        cited = issues.cited_issues(self.TEXT)
        self.assertEqual(cited, {12: "open", 13: "closed"})

    def test_open_wins_over_closed_for_the_same_number(self):
        cited = issues.cited_issues("issue #5 (closed) ... issue #5")
        self.assertEqual(cited, {5: "open"})


class LiveDocsTest(unittest.TestCase):
    """The audit reads the registry's class-L rows, not a list of its own: an issue cited only from README or
    STATUS must count, and a document that changes class must change the audit with it."""

    def test_live_docs_are_the_registrys_class_l_rows(self):
        self.assertEqual(issues.live_docs(), tuple(docmaint.by_class("L")))
        for must in ("docs/KNOWN.md", "README.md", "docs/STATUS.md", "docs/CURRENT_SPRINT.md"):
            self.assertIn(must, issues.live_docs())


class KnownRowsTest(unittest.TestCase):
    KNOWN = ("# What we know\n\n## 1. Proven\n\n| **Proven thing.** | x |\n\n"
             "## 2. Believed\n\n| What | What would settle it |\n|---|---|\n"
             "| **Believed with an issue (issue #7).** more | exp |\n"
             "| **Believed with no issue yet.** more | exp |\n"
             "| **Believed, ruled out.** more | exp *No issue: the owner's ears* |\n"
             "| ~~**Struck out.**~~ **SETTLED** | done |\n"
             "| **~~Struck inside the bold~~ -- falsified the same evening** | done |\n"
             "| **Headline that says FIXED 2026-09-15.** | done |\n"
             "| **HAZARD, fixed: lower-case still counts.** | done |\n\n"
             "## 3. Retracted\n\n| **Retracted, no issue.** | y |\n\n"
             "## 4. Standing hazards\n\n"
             "- **HAZARD: a hazard with an issue.** *(issue #8)* text\n"
             "- **HAZARD: a hazard with no issue that wraps onto\n"
             "  a second line.** and its text, which mentions a thing that was fixed elsewhere\n"
             "- **Open: a live question with no issue.** text\n"
             "- **A lesson, not a hazard: nothing to fix.** text\n"
             "- **HAZARD: superseded in its blockquote.** text\n"
             "  > Superseded 2026-09-21: the scrubber does this now\n"
             "- **HAZARD: a hazard ruled out.** text\n"
             "  *no issue: a lesson, nothing left to fix*\n"
             "- **HAZARD: a hazard whose citation is on its second line, wrapped\n"
             "  like this.** *(issue #9)* text\n"
             "- **HAZARD: a parent that cites an issue.** *(issue #10)*\n"
             "  - **HAZARD: a nested sub-bullet with no citation of its own.** text\n"
             "  - a plain sub-bullet with no headline\n\n"
             "## 5. Nothing here\n\n- **HAZARD: not scanned.**\n")

    def test_lists_section_2_rows_and_live_section_4_hazards_without_a_citation(self):
        self.assertEqual(issues.known_rows_without_issue(self.KNOWN),
                         [("2", "Believed with no issue yet."),
                          ("4", "HAZARD: a hazard with no issue that wraps onto"),
                          ("4", "Open: a live question with no issue."),
                          ("4", "HAZARD: a nested sub-bullet with no citation of its own.")])


def planted(number, state="OPEN", labels=("known-issue", "render"), milestone="Sprint 11",
            updated="2026-09-23T10:00:00Z", body=GOOD_BODY, title="t", reason=None, comments=(),
            created="2026-09-23T09:00:00Z", closed=None):
    return {"number": number, "state": state, "stateReason": reason, "title": title,
            "labels": [{"name": l} for l in labels],
            "milestone": {"title": milestone} if milestone else None,
            "updatedAt": updated, "createdAt": created, "closedAt": closed, "body": body,
            "comments": [{"author": {"login": "someone"}, "body": c} for c in comments]}


def cites(n, state="open"):
    return {n: {"state": state, "where": ["docs/KNOWN.md"]}}


class AuditTest(unittest.TestCase):
    def test_a_consistent_stack_is_clean(self):
        problems, notes = issues.audit(cites(1), [planted(1)])
        self.assertEqual(problems, [])
        self.assertEqual(notes, [])

    def test_a_row_citing_a_closed_issue_fails(self):
        problems, _ = issues.audit(cites(1), [planted(1, state="CLOSED")])
        self.assertEqual(len(problems), 1)
        self.assertIn("CLOSED", problems[0])

    def test_a_row_citing_a_closed_issue_as_closed_is_fine(self):
        problems, _ = issues.audit(cites(1, "closed"), [planted(1, state="CLOSED")])
        self.assertEqual(problems, [])

    def test_a_row_saying_closed_while_the_issue_is_open_fails_with_its_own_sentence(self):
        problems, _ = issues.audit(cites(1, "closed"), [planted(1)])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("cited as closed", problems[0])
        self.assertNotIn("orphan", problems[0])

    def test_a_row_citing_a_missing_issue_fails(self):
        problems, _ = issues.audit(cites(9), [])
        self.assertTrue(any("does not exist" in p for p in problems), problems)

    def test_a_cited_issue_without_the_stack_label_fails(self):
        problems, _ = issues.audit(cites(1), [planted(1, labels=("bug", "render"))])
        self.assertTrue(any("known-issue" in p for p in problems), problems)

    def test_an_orphan_open_issue_fails(self):
        problems, _ = issues.audit({}, [planted(4)])
        self.assertTrue(any("orphan" in p for p in problems), problems)

    def test_a_closed_issue_nobody_cites_is_not_an_orphan(self):
        problems, _ = issues.audit({}, [planted(4, state="CLOSED")])
        self.assertEqual(problems, [])

    def test_area_labels_must_be_exactly_one(self):
        problems, _ = issues.audit(cites(1), [planted(1, labels=("known-issue",))])
        self.assertTrue(any("area" in p for p in problems), problems)
        problems, _ = issues.audit(cites(1), [planted(1, labels=("known-issue", "render", "audio"))])
        self.assertTrue(any("2 area labels" in p for p in problems), problems)

    def test_a_body_that_lost_its_closing_bar_fails(self):
        problems, _ = issues.audit(cites(1), [planted(1, body=GOOD_BODY.replace("## Closing bar", "## Bar"))])
        self.assertTrue(any("Closing bar" in p for p in problems), problems)

    def test_backlog_and_stale_are_notes_not_problems(self):
        problems, notes = issues.audit(cites(1), [planted(1, milestone=None, updated="2026-09-01T00:00:00Z")],
                                       stale_since="2026-09-20")
        self.assertEqual(problems, [])
        self.assertTrue(any("no milestone" in n for n in notes), notes)
        self.assertTrue(any("untouched since 2026-09-01" in n for n in notes), notes)

    def test_a_completed_close_without_the_tools_closing_line_is_noted_never_failed(self):
        # The owner closed #29 by hand with "could not repro": that close stands (DOC_MAINTENANCE section 7
        # step 4), so the audit tells the reviewer and does not fail.
        by_hand = planted(1, state="CLOSED", reason="COMPLETED", comments=("Old issue, could not repro, closing",))
        problems, notes = issues.audit(cites(1, "closed"), [by_hand])
        self.assertEqual(problems, [])
        self.assertTrue(any("closed as completed" in n and "#1" in n for n in notes), notes)
        by_tool = planted(1, state="CLOSED", reason="COMPLETED",
                          comments=("a discussion", "Closing bar met: gate s11_x_gate 3/3, 1a2b3c4"))
        _, notes = issues.audit(cites(1, "closed"), [by_tool])
        self.assertEqual(notes, [])
        dropped = planted(1, state="CLOSED", reason="NOT_PLANNED", comments=("Closed as not planned: R260",))
        _, notes = issues.audit(cites(1, "closed"), [dropped])
        self.assertEqual(notes, [])

    def test_gh_label_and_milestone_shapes_are_read(self):
        # gh emits labels as objects and the milestone as an object or null; a plain-string form is read too.
        flat = {"number": 3, "state": "open", "title": "t", "labels": ["known-issue", "audio"],
                "milestone": "Sprint 11", "updatedAt": "", "body": GOOD_BODY}
        n = issues.normalise(flat)
        self.assertEqual((n["state"], n["labels"], n["milestone"]), ("OPEN", ["known-issue", "audio"], "Sprint 11"))


class ReplayTest(unittest.TestCase):
    """`audit --json FILE` end to end through main(): a planted tree with one KNOWN row citing issue #1, and a
    saved listing -- the offline path a reviewer without gh is told to use, so it is the path that is tested."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "docs"))
        with open(os.path.join(self.tmp, "docs", "KNOWN.md"), "w", encoding="utf-8") as f:
            f.write("# K\n\n## 2. Believed\n\n| **A row.** *(issue #1)* | exp |\n\n## 4. Hazards\n\n- **H.** *(issue #1)*\n")
        self.saved_root = issues.ROOT
        issues.ROOT = self.tmp

    def tearDown(self):
        issues.ROOT = self.saved_root

    def run_audit(self, listing):
        path = os.path.join(self.tmp, "listing.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(listing, f)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = issues.main(["audit", "--json", path])
        return code, out.getvalue()

    def test_a_clean_listing_exits_zero(self):
        code, text = self.run_audit([planted(1)])
        self.assertEqual(code, 0, text)
        self.assertIn("audit: OK", text)
        self.assertNotIn("PROBLEM", text)

    def test_a_closed_but_cited_issue_exits_one(self):
        code, text = self.run_audit([planted(1, state="CLOSED")])
        self.assertEqual(code, 1, text)
        self.assertIn("PROBLEM: issue #1 is cited as open", text)

    def test_an_empty_listing_cannot_pass(self):
        code, text = self.run_audit([])
        self.assertEqual(code, 1, text)
        self.assertIn("does not exist", text)


class LabelsAgreeTest(unittest.TestCase):
    """The areas this module accepts are the areas scripts/github_labels.sh creates, and the stack's two labels
    exist there too -- otherwise `open` would apply a label the repository does not have."""

    def test_every_area_and_stack_label_is_created_by_the_script(self):
        with open(os.path.join(ROOT, "scripts", "github_labels.sh"), encoding="utf-8") as f:
            text = f.read()
        block = re.search(r"^LABELS=\(\n(.*?)^\)$", text, re.S | re.M).group(1)
        names = {line.strip()[1:].split("|")[0] for line in block.splitlines() if line.strip().startswith('"')}
        for label in issues.AREAS + (issues.STACK_LABEL, issues.CARRIED_LABEL):
            self.assertIn(label, names, "%s is not created by scripts/github_labels.sh" % label)


RULED_OUT_TEXT = """# slug | ruling | bar or reason | where it is written
soft-double-chain | R265 | Declined until a gate, a control round or a player names a numeric defect that points at it. | audit D14
window-policy | no issue | One gate at `fullscreen`, its three scores against the pinned run's. | audit A13
"""


class PlantedTree(unittest.TestCase):
    """A planted repository root with docs/ and the ruled-out list, and a saved listing to replay."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "docs"))
        self.write("docs/backlog_ruled_out.txt", RULED_OUT_TEXT)
        self.saved_root = issues.ROOT
        issues.ROOT = self.tmp

    def tearDown(self):
        issues.ROOT = self.saved_root

    def write(self, rel, text):
        with open(os.path.join(self.tmp, rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def read(self, rel):
        with open(os.path.join(self.tmp, rel), encoding="utf-8") as f:
            return f.read()

    def listing(self, records, name="listing.json"):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f)
        return path

    def run_main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = issues.main(argv)
        return code, out.getvalue()


def carry_comment(text="Carried at the Sprint 11 close (2026-09-25): not in the plan", when="2026-09-25T10:00:00Z"):
    return {"author": {"login": "someone"}, "body": text, "createdAt": when}


class BacklogTest(PlantedTree):
    """`backlog` writes docs/BACKLOG.md from the open issues plus docs/backlog_ruled_out.txt (R267)."""

    def stack(self):
        carried = planted(25, labels=("known-issue", "linux", "carried"), milestone="Sprint 13",
                          title="The VM suites are not green | on the merged tree")
        carried["comments"] = [carry_comment(), carry_comment("A review note, not a carry"),
                               carry_comment("Carried once into Sprint 13 (R266): the sprint has a task")]
        backlog = planted(27, labels=("known-issue", "recomp"), milestone=None,
                          body=GOOD_BODY.replace("The four captures score >= 90 again on a gate, or the references "
                                                 "are re-recorded with the change written down.",
                                                 "One clean-exit launch. If the password is read back, the row "
                                                 "retracts."))
        hand = planted(28, labels=("known-issue", "audio", "carried"), milestone=None)
        closed = planted(29, state="CLOSED")
        return [closed, hand, backlog, carried]

    def test_the_file_is_written_with_both_tables_and_a_generated_head(self):
        path = self.listing(self.stack())
        code, text = self.run_main(["backlog", "--json", path])
        self.assertEqual(code, 0, text)
        out = self.read("docs/BACKLOG.md")
        head = "\n".join(out.splitlines()[:8])
        self.assertIn("Generated", head)
        self.assertIn("python -m tools_py.issues backlog", head)
        self.assertIn("docs/backlog_ruled_out.txt", head)
        # the open issues, in number order; the closed one is not carry
        self.assertLess(out.index("| #25 |"), out.index("| #27 |"))
        self.assertLess(out.index("| #27 |"), out.index("| #28 |"))
        self.assertNotIn("| #29 |", out)
        row25 = [l for l in out.splitlines() if l.startswith("| #25 |")][0]
        self.assertIn("linux", row25)
        self.assertIn("Sprint 13", row25)
        self.assertIn("| 2 |", row25, "two 'Carried' comments are two carries; a review note is not one")
        self.assertIn(r"The VM suites are not green \| on the merged tree", row25, "a pipe in a title is escaped")
        row27 = [l for l in out.splitlines() if l.startswith("| #27 |")][0]
        self.assertIn("backlog", row27)
        self.assertIn("| 0 |", row27)
        self.assertIn("One clean-exit launch.", row27)
        self.assertNotIn("retracts", row27, "only the closing bar's first sentence")
        row28 = [l for l in out.splitlines() if l.startswith("| #28 |")][0]
        self.assertIn("| 1 |", row28, "the label with no carry comment still counts once (a carry by hand)")
        # the ruled-out rows, rendered as the second table
        self.assertIn("| soft-double-chain | R265 |", out)
        self.assertIn("| window-policy | no issue |", out)
        self.assertIn("3 open issues", out)
        self.assertIn("2 rows", out)

    def test_check_passes_on_a_fresh_file_and_fails_on_a_stale_one(self):
        path = self.listing(self.stack())
        self.run_main(["backlog", "--json", path])
        code, text = self.run_main(["backlog", "--json", path, "--check"])
        self.assertEqual(code, 0, text)
        # an issue closed since the file was written: stale
        code, text = self.run_main(["backlog", "--json", self.listing(self.stack()[1:3], "l2.json"), "--check"])
        self.assertEqual(code, 1, text)
        self.assertIn("stale", text)

    def test_check_never_writes(self):
        path = self.listing(self.stack())
        code, text = self.run_main(["backlog", "--json", path, "--check"])
        self.assertEqual(code, 1, text)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "docs", "BACKLOG.md")))

    def test_the_offline_check_reads_only_the_ruled_out_half(self):
        # The docs test has no network: --offline holds the ruled-out table and the head to the tracked list,
        # and takes the issue table as it stands in the file.
        path = self.listing(self.stack())
        self.run_main(["backlog", "--json", path])
        code, text = self.run_main(["backlog", "--check", "--offline"])
        self.assertEqual(code, 0, text)
        self.write("docs/backlog_ruled_out.txt", RULED_OUT_TEXT + "new-row | no issue | A bar. | audit G3\n")
        code, text = self.run_main(["backlog", "--check", "--offline"])
        self.assertEqual(code, 1, text)
        self.assertIn("stale", text)

    def test_a_malformed_ruled_out_row_is_refused_with_its_line(self):
        self.write("docs/backlog_ruled_out.txt", RULED_OUT_TEXT + "only | three | fields\n")
        code, text = self.run_main(["backlog", "--json", self.listing(self.stack())])
        self.assertEqual(code, 2, text)
        self.assertIn("line 4", text)
        self.write("docs/backlog_ruled_out.txt", RULED_OUT_TEXT + "x | maybe | A bar. | audit A1\n")
        code, text = self.run_main(["backlog", "--json", self.listing(self.stack())])
        self.assertEqual(code, 2, text)
        self.assertIn("ruling", text)
        self.write("docs/backlog_ruled_out.txt", RULED_OUT_TEXT + "window-policy | no issue | Again. | audit A1\n")
        code, text = self.run_main(["backlog", "--json", self.listing(self.stack())])
        self.assertEqual(code, 2, text)
        self.assertIn("window-policy", text)


class GhRecorded(PlantedTree):
    """A planted tree where issues._gh records each command and succeeds -- gh itself is never run."""

    def setUp(self):
        super().setUp()
        self.calls = []
        self.saved_gh = issues._gh

        class Done:
            returncode, stdout, stderr = 0, "", ""

        def record(cmd):
            self.calls.append(cmd)
            return Done()
        issues._gh = record

    def tearDown(self):
        issues._gh = self.saved_gh
        super().tearDown()


class CarryTest(GhRecorded):
    """`carry N --comment ... [--milestone NAME]`: the label, the comment and the milestone in one step, and a
    refusal once the issue has been carried twice -- that is the owner's question (DOC_MAINTENANCE section 7 step
    5). --json replays `gh issue view`."""

    def view(self, **kw):
        return self.listing(planted(33, **kw), "view.json")

    def test_a_first_carry_labels_comments_and_moves_the_milestone(self):
        code, text = self.run_main(["carry", "33", "--comment", "not in Sprint 14's plan", "--milestone",
                                    "Sprint 14", "--json", self.view(milestone="Sprint 13")])
        self.assertEqual(code, 0, text)
        self.assertEqual(len(self.calls), 2, self.calls)
        edit, comment = self.calls
        self.assertEqual(edit[:3], ["issue", "edit", "33"])
        self.assertIn("--add-label", edit)
        self.assertEqual(edit[edit.index("--add-label") + 1], "carried")
        self.assertEqual(edit[edit.index("--milestone") + 1], "Sprint 14")
        self.assertEqual(comment[:3], ["issue", "comment", "33"])
        body = comment[comment.index("--body") + 1]
        self.assertTrue(body.startswith(issues.CARRY_COMMENT), body)
        self.assertIn("Sprint 13", body)
        self.assertIn("Sprint 14", body)
        self.assertIn("not in Sprint 14's plan", body)

    def test_no_milestone_means_the_backlog(self):
        code, text = self.run_main(["carry", "33", "--comment", "no plan names it", "--json", self.view()])
        self.assertEqual(code, 0, text)
        self.assertIn("--remove-milestone", self.calls[0])
        self.assertIn("the backlog", self.calls[1][self.calls[1].index("--body") + 1])

    def test_the_tools_comment_counts_as_a_carry(self):
        # What `carry` writes must be what carried_count counts, or the refusal below could never fire.
        self.run_main(["carry", "33", "--comment", "why", "--json", self.view()])
        body = self.calls[1][self.calls[1].index("--body") + 1]
        issue = issues.normalise(planted(33, comments=(body,)))
        self.assertEqual(issues.carried_count(issue), 1)

    def test_a_second_carry_is_allowed_and_a_third_refused(self):
        once = self.view(labels=("known-issue", "render", "carried"),
                         comments=("Carried at the Sprint 11 close (2026-09-25): not in the plan",))
        code, text = self.run_main(["carry", "33", "--comment", "why", "--json", once])
        self.assertEqual(code, 0, text)
        self.calls[:] = []
        twice = self.view(labels=("known-issue", "render", "carried"),
                          comments=("Carried at the Sprint 11 close (2026-09-25): not in the plan",
                                    "a review note",
                                    "Carried once into Sprint 13 (R266): the sprint has a task"))
        code, text = self.run_main(["carry", "33", "--comment", "why", "--json", twice])
        self.assertEqual(code, 1, text)
        self.assertEqual(self.calls, [], "a refused carry touches nothing")
        self.assertIn("carried twice", text)
        self.assertIn("owner", text)

    def test_a_closed_issue_is_not_carried(self):
        code, text = self.run_main(["carry", "33", "--comment", "why", "--json", self.view(state="CLOSED")])
        self.assertEqual(code, 1, text)
        self.assertEqual(self.calls, [])

    def test_the_comment_is_required_and_is_held_to_the_body_rules(self):
        code, text = self.run_main(["carry", "33", "--comment", "  ", "--json", self.view()])
        self.assertEqual(code, 2, text)
        code, text = self.run_main(["carry", "33", "--comment", r"see C:\Users\bob\log.txt", "--json", self.view()])
        self.assertEqual(code, 1, text)
        self.assertIn("home directory", text)
        self.assertEqual(self.calls, [])

    def test_dry_run_prints_and_runs_nothing(self):
        code, text = self.run_main(["carry", "33", "--comment", "why", "--milestone", "Sprint 14", "--dry-run",
                                    "--json", self.view()])
        self.assertEqual(code, 0, text)
        self.assertEqual(self.calls, [])
        self.assertIn("gh issue edit 33", text)
        self.assertIn("gh issue comment 33", text)


class MilestoneTest(GhRecorded):
    """`milestone close NAME --next NEXT`: one milestone closed and the next created, refused while an open issue
    remains in it. --json replays the issue listing, --milestones-json the `gh api .../milestones` reply."""

    MILESTONES = [{"number": 2, "title": "Sprint 12", "state": "closed"},
                  {"number": 3, "title": "Sprint 13", "state": "open"}]

    def close(self, stack, milestones=None, *extra):
        return self.run_main(["milestone", "close", "Sprint 13", "--next", "Sprint 14",
                              "--json", self.listing(stack),
                              "--milestones-json", self.listing(milestones or self.MILESTONES, "ms.json")]
                             + list(extra))

    def test_an_emptied_milestone_is_closed_and_the_next_created(self):
        stack = [planted(25, milestone="Sprint 14"), planted(38, state="CLOSED", milestone="Sprint 13")]
        code, text = self.close(stack)
        self.assertEqual(code, 0, text)
        self.assertEqual(len(self.calls), 2, self.calls)
        shut, create = self.calls
        self.assertIn("repos/%s/milestones/3" % issues.REPO, shut)
        self.assertIn("PATCH", shut)
        self.assertIn("state=closed", shut)
        self.assertIn("repos/%s/milestones" % issues.REPO, create)
        self.assertIn("POST", create)
        self.assertIn("title=Sprint 14", create)

    def test_open_issues_left_in_it_refuse_the_close(self):
        stack = [planted(25, milestone="Sprint 13"), planted(26, milestone="Sprint 13"), planted(27, milestone=None)]
        code, text = self.close(stack)
        self.assertEqual(code, 1, text)
        self.assertEqual(self.calls, [])
        self.assertIn("#25", text)
        self.assertIn("#26", text)
        self.assertNotIn("#27", text)
        self.assertIn("carry", text)

    def test_a_next_milestone_that_exists_is_not_created_twice(self):
        ms = self.MILESTONES + [{"number": 4, "title": "Sprint 14", "state": "open"}]
        code, text = self.close([], ms)
        self.assertEqual(code, 0, text)
        self.assertEqual(len(self.calls), 1, self.calls)
        self.assertIn("already exists", text)

    def test_an_unknown_or_closed_milestone_is_said_not_guessed(self):
        code, text = self.run_main(["milestone", "close", "Sprint 99", "--next", "Sprint 100",
                                    "--json", self.listing([]), "--milestones-json", self.listing(self.MILESTONES,
                                                                                                  "ms.json")])
        self.assertEqual(code, 1, text)
        self.assertIn("no milestone", text)
        self.assertEqual(self.calls, [])
        code, text = self.run_main(["milestone", "close", "Sprint 12", "--next", "Sprint 13",
                                    "--json", self.listing([]), "--milestones-json", self.listing(self.MILESTONES,
                                                                                                  "ms.json")])
        self.assertEqual(code, 0, text)
        self.assertEqual(self.calls, [], "closed already and the next exists: nothing to do")
        self.assertIn("already closed", text)

    def test_dry_run_prints_and_runs_nothing(self):
        code, text = self.close([], None, "--dry-run")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.calls, [])
        self.assertIn("gh api", text)


class TallyTest(PlantedTree):
    """`tally --since DATE`: the sentence DOC_MAINTENANCE section 7 step 7 wants -- opened, closed and carried
    since the day the sprint opened, and the highest issue number."""

    def test_the_sentence_counts_each_kind_from_the_date(self):
        old = planted(20, created="2026-09-20T09:00:00Z")
        opened = planted(49, created="2026-09-25T09:00:00Z")
        opened_and_closed = planted(50, state="CLOSED", created="2026-09-25T10:00:00Z",
                                    closed="2026-09-25T12:00:00Z")
        closed_old = planted(38, state="CLOSED", created="2026-09-23T10:00:00Z", closed="2026-09-25T08:00:00Z")
        closed_before = planted(30, state="CLOSED", created="2026-09-22T10:00:00Z", closed="2026-09-24T08:00:00Z")
        carried = planted(25, labels=("known-issue", "linux", "carried"))
        carried["comments"] = [carry_comment(when="2026-09-24T10:00:00Z"),
                               carry_comment("Carried once into Sprint 13 (R266)", when="2026-09-25T10:00:00Z"),
                               carry_comment("Carried from Sprint 13 to Sprint 14: again", when="2026-09-25T11:00:00Z")]
        carried_before = planted(26, labels=("known-issue", "harness", "carried"))
        carried_before["comments"] = [carry_comment(when="2026-09-24T10:00:00Z")]
        path = self.listing([old, opened, opened_and_closed, closed_old, closed_before, carried, carried_before])
        code, text = self.run_main(["tally", "--since", "2026-09-25", "--json", path])
        self.assertEqual(code, 0, text)
        first = text.splitlines()[0]
        self.assertIn("opened 2", first)
        self.assertIn("closed 2", first)
        self.assertIn("carried 1", first, "an issue carried twice on the day is one issue carried")
        self.assertIn("#50", first)
        self.assertIn("2026-09-25", first)
        self.assertIn("#49, #50", text)
        self.assertIn("#38, #50", text)

    def test_an_empty_listing_says_zero(self):
        code, text = self.run_main(["tally", "--since", "2026-09-25", "--json", self.listing([])])
        self.assertEqual(code, 0, text)
        self.assertIn("opened 0, closed 0, carried 0", text)

    def test_a_malformed_date_is_refused(self):
        code, text = self.run_main(["tally", "--since", "25/09/2026", "--json", self.listing([])])
        self.assertEqual(code, 2, text)


class RuledOutListTest(unittest.TestCase):
    """The tracked list on this tree parses, and every row the audit marked `backlog` has a place in it."""

    def test_the_tracked_list_parses(self):
        rows = issues.ruled_out_rows()
        self.assertGreaterEqual(len(rows), 10)
        for r in rows:
            self.assertTrue(r["ruling"] == "no issue" or re.match(r"^R\d+$", r["ruling"]), r)

    def test_every_backlog_row_of_the_audit_is_seeded(self):
        wheres = " ".join(r["where"] for r in issues.ruled_out_rows())
        for audit_row in ("A13", "C17", "D12", "D13", "D14", "D15", "G2", "G3", "H4", "I5"):
            self.assertRegex(wheres, r"\baudit %s\b" % audit_row, audit_row)
        self.assertIn("Sprint 12 Outcome", wheres)


if __name__ == "__main__":
    unittest.main()
