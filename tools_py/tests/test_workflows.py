""".github/workflows: what a run's conclusion means, and which checks the `main` ruleset requires (Sprint 13 H1).

GitHub computes a workflow run's conclusion from its jobs: any job that ran and passed makes the run `success`;
the run reads `skipped` only when EVERY job was skipped (read on 2026-09-25 from public runs: cli/cli's "PR
Triaging" is `skipped` when all seven jobs skip and `success` when one of them runs). The `linux` and `windows`
workflows' `changes` job always runs, so a docs-only push used to read `success` with the build skipped -- and a
final status job that is itself skipped cannot change that, because `changes` still succeeded. The only place the
decision can be made before any job exists is the trigger: `on.push.paths-ignore: docs/**`. A docs-only push now
starts no `linux` or `windows` run at all; a push that touches anything else builds.

The pull_request trigger keeps no path filter: `build`, `build-windows` and `leakcheck` are the `main` ruleset's
required checks (docs/GIT_STRATEGY.md section 6), and a required check whose workflow never starts leaves the pull
request waiting forever. On a pull request the `changes` job compares the pull request's base..head, and this test
pins that the expression is chosen by the event's name, so a pull_request run can never fall back to a push's
`before`.

These are text-level checks with an optional PyYAML layer: the Windows and Linux runners install numpy, pillow and
zstandard only, and this test must run (not skip) there.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF = os.path.join(ROOT, ".github", "workflows")

# The workflow whose build is skipped on docs-only changes -> its build job (a required check on `main`).
BUILD_WORKFLOWS = {"linux.yml": "build", "windows.yml": "build-windows"}
# Every required check on `main` (docs/GIT_STRATEGY.md section 6, the ruleset as read 2026-09-25) -> its workflow.
REQUIRED_CHECKS = {"build": "linux.yml", "build-windows": "windows.yml", "leakcheck": "secrets.yml"}

PR_BASE = "github.event_name == 'pull_request' && github.event.pull_request.base.sha || github.event.before"
PR_HEAD = "github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha"


def _text(name):
    with open(os.path.join(WF, name), encoding="utf-8") as f:
        return f.read()


def _block(text, key, indent):
    """The lines under `<indent>key:` up to the next line at that indent or shallower."""
    lines = text.splitlines()
    pad = " " * indent
    for i, line in enumerate(lines):
        if line.rstrip() == pad + key + ":" or line.startswith(pad + key + ": "):
            out = []
            for nxt in lines[i + 1:]:
                if nxt.strip() and not nxt.startswith(" " * (indent + 1)) and not nxt.lstrip().startswith("#"):
                    break
                out.append(nxt)
            return line, "\n".join(out)
    return None, None


def _jobs(text):
    """Job ids (two-space keys under `jobs:`) -> their bodies."""
    _, body = _block(text, "jobs", 0)
    jobs, cur = {}, None
    for line in (body or "").splitlines():
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            cur = m.group(1)
            jobs[cur] = []
        elif cur:
            jobs[cur].append(line)
    return {k: "\n".join(v) for k, v in jobs.items()}


class DocsOnlyPushStartsNoBuildRun(unittest.TestCase):
    def test_push_ignores_docs_and_pull_request_is_unfiltered(self):
        for name in BUILD_WORKFLOWS:
            text = _text(name)
            _, on = _block(text, "on", 0)
            self.assertIsNotNone(on, name)
            _, push = _block(on, "push", 2)
            self.assertIsNotNone(push, f"{name}: no push trigger")
            self.assertRegex(push, r"paths-ignore:\s*\n\s*- '?docs/\*\*'?",
                             f"{name}: a docs-only push must start no run (on.push.paths-ignore: docs/**)")
            head, pr = _block(on, "pull_request", 2)
            self.assertIsNotNone(head, f"{name}: no pull_request trigger")
            self.assertNotIn("paths", pr or "",
                             f"{name}: a path filter on pull_request would leave a required check waiting forever")

    def test_secrets_runs_on_every_push(self):
        text = _text("secrets.yml")
        self.assertNotIn("paths", _block(text, "on", 0)[1], "a secret in a document is still a secret")


class PullRequestComparesBaseToHead(unittest.TestCase):
    def test_changes_filter_names_the_pull_request_base(self):
        for name in BUILD_WORKFLOWS:
            changes = _jobs(_text(name)).get("changes")
            self.assertIsNotNone(changes, f"{name}: no changes job")
            self.assertIn("BASE: ${{ " + PR_BASE + " }}", changes, name)
            self.assertIn("HEAD: ${{ " + PR_HEAD + " }}", changes, name)
            self.assertIn('git diff --name-only "$BASE" "$HEAD"', changes, name)


class RequiredChecksKeepTheirNames(unittest.TestCase):
    def test_each_required_check_is_a_job_with_no_renaming_name(self):
        for check, wf in REQUIRED_CHECKS.items():
            jobs = _jobs(_text(wf))
            self.assertIn(check, jobs, f"{wf}: the required check `{check}` is gone")
            # A job-level `name:` (four spaces) would become the check-run name and break the ruleset.
            self.assertNotRegex(jobs[check], r"(?m)^    name:", f"{wf}: `{check}` renamed by a job-level name:")

    def test_build_jobs_still_gate_on_changes(self):
        for name, build in BUILD_WORKFLOWS.items():
            body = _jobs(_text(name))[build]
            self.assertRegex(body, r"(?m)^    needs: changes\s*$", name)
            self.assertRegex(body, r"(?m)^    if: needs\.changes\.outputs\.code == 'true'\s*$", name)


class WithPyYAML(unittest.TestCase):
    """The same facts through a real parser, where one is installed (the owner's machine has 6.0.3)."""

    def setUp(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML not installed; the text-level classes above carry the checks")

    def test_parsed(self):
        import yaml
        for name, build in BUILD_WORKFLOWS.items():
            doc = yaml.safe_load(_text(name))
            on = doc.get("on", doc.get(True))  # PyYAML reads a bare `on:` key as True
            self.assertEqual((on["push"] or {}).get("paths-ignore"), ["docs/**"], name)
            self.assertFalse(on.get("pull_request") and {"paths", "paths-ignore"} & set(on["pull_request"]), name)
            env = doc["jobs"]["changes"]["steps"][1]["env"]
            self.assertEqual(env["BASE"], "${{ " + PR_BASE + " }}", name)
            self.assertEqual(env["HEAD"], "${{ " + PR_HEAD + " }}", name)
            self.assertEqual(doc["jobs"][build]["needs"], "changes", name)
            self.assertNotIn("name", doc["jobs"][build], name)
        for check, wf in REQUIRED_CHECKS.items():
            jobs = yaml.safe_load(_text(wf))["jobs"]
            self.assertIn(check, jobs, wf)
            self.assertNotIn("name", jobs[check], wf)


if __name__ == "__main__":
    unittest.main()
