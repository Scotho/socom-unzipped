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
            updated="2026-09-23T10:00:00Z", body=GOOD_BODY, title="t", reason=None, comments=()):
    return {"number": number, "state": state, "stateReason": reason, "title": title,
            "labels": [{"name": l} for l in labels],
            "milestone": {"title": milestone} if milestone else None,
            "updatedAt": updated, "body": body,
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


if __name__ == "__main__":
    unittest.main()
