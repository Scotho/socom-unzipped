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
request waiting forever. On a pull request the `changes` job compares the pull request's base...head (from the merge base), and this test
pins that the expression is chosen by the event's name, so a pull_request run can never fall back to a push's
`before`.

These are text-level checks with an optional PyYAML layer: the `docs` workflow runs this file with no packages
installed, and it must run (not skip) there. The build runners install requirements.txt since Sprint 13 H7, which
carries PyYAML, so the parsed layer runs there too.
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
            # Three dots: from the merge base, so main's own movement since the fork is not "code changed".
            self.assertIn('git diff --name-only "$BASE...$HEAD"', changes, name)
            self.assertNotIn('git diff --name-only "$BASE" "$HEAD"', changes, name)
            # No merge base (a forced push onto unrelated history) builds rather than reading as docs-only.
            self.assertIn('git merge-base "$BASE" "$HEAD"', changes, name)


class DocsWorkflowChecksDocsOnlyPushes(unittest.TestCase):
    """Fix round 1: the doc tests read the real docs/ tree and ran only inside the builds a docs push skips."""

    def test_docs_workflow_runs_the_doc_checks_on_docs_pushes(self):
        self.assertTrue(os.path.exists(os.path.join(WF, "docs.yml")), "no .github/workflows/docs.yml")
        text = _text("docs.yml")
        _, on = _block(text, "on", 0)
        _, push = _block(on, "push", 2)
        self.assertRegex(push or "", r"paths:\s*\n(\s*- .*\n)*?\s*- '?docs/\*\*'?", "docs.yml: push must name docs/**")
        self.assertIsNotNone(_block(on, "pull_request", 2)[0], "docs.yml: no pull_request trigger")
        self.assertIn("python -m tools_py.docmaint", text)
        for mod in ("test_doc_maintenance", "test_tools_py_inventory", "test_workflows"):
            self.assertIn("tools_py.tests." + mod, text, mod)

    def test_docs_job_is_not_a_required_check(self):
        jobs = _jobs(_text("docs.yml"))
        self.assertEqual(list(jobs), ["docs"])
        self.assertNotIn("docs", REQUIRED_CHECKS)


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


SYNTHETIC = os.path.join(ROOT, "tests", "fixtures", "synthetic_recomp")
SYNTHETIC_SCRIPT = "scripts/build_synthetic_runner.sh"
# The job's own tree, built a step earlier with no generated code: only the runner's sources compile on top.
SYNTHETIC_TREE = {"linux.yml": "third_party/ps2recomp/build-linux", "windows.yml": "third_party/ps2recomp/build-clang"}
# The files only the runner compiles, the reason the step exists (the 2026-09-25 audit, code-runtime.md F7).
RUNNER_ONLY = ("game_overrides_socom2.cpp", "socom2_crypto.cpp")
GAME_TEXT_START = 0x180000  # the game's text starts at 0x180008; the synthetic program lives below it


def _steps(job_body):
    """A job body's steps as text blocks, each starting at its `      - ` line."""
    steps, cur = [], None
    for line in job_body.splitlines():
        if line.startswith("      - "):
            cur = [line]
            steps.append(cur)
        elif cur is not None and (line.startswith("        ") or not line.strip()):
            cur.append(line)
        elif line.startswith("      #"):
            continue
        else:
            cur = None
    return ["\n".join(s) for s in steps]


class RunnerLinksAgainstASyntheticSet(unittest.TestCase):
    """Sprint 13 Task C1: every code push compiles the game's own files and links the runner (audit F7, F41)."""

    def _step(self, name):
        body = _jobs(_text(name))[BUILD_WORKFLOWS[name]]
        steps = _steps(body)
        hits = [i for i, s in enumerate(steps) if SYNTHETIC_SCRIPT in s]
        self.assertEqual(len(hits), 1, f"{name}: the build job must run {SYNTHETIC_SCRIPT} exactly once")
        return steps, hits[0]

    def test_each_build_job_runs_the_synthetic_link(self):
        for name in BUILD_WORKFLOWS:
            steps, i = self._step(name)
            step = steps[i]
            first = step.splitlines()[0]
            for f in RUNNER_ONLY:
                self.assertIn(f, first, f"{name}: the step's name must say it compiles {f}")
            self.assertIn(f"--build-dir {SYNTHETIC_TREE[name]}", step,
                          f"{name}: reuse the job's own tree ({SYNTHETIC_TREE[name]}), not a second cold build")
            # After the no-runner build (`id: build`): the tree it reuses has the library already.
            build = [j for j, s in enumerate(steps) if re.search(r"(?m)^        id: build\s*$", s)]
            self.assertEqual(len(build), 1, f"{name}: the no-runner build step needs `id: build`")
            self.assertIn("--no-runner", steps[build[0]], name)
            self.assertLess(build[0], i, f"{name}: the synthetic link must follow the no-runner build")
            # It runs even when the suite failed (both verdicts), never when the build itself failed or was cancelled.
            self.assertRegex(step, r"if: \$\{\{ !cancelled\(\) && steps\.build\.outcome == 'success' \}\}", name)

    def test_the_runner_target_compiles_the_two_files(self):
        with open(os.path.join(ROOT, "third_party", "ps2recomp", "ps2xRuntime", "CMakeLists.txt"),
                  encoding="utf-8") as f:
            cmake = f.read()
        for name in RUNNER_ONLY:
            self.assertIn(f"target_sources(ps2EntryRunner PRIVATE src/lib/{name})", cmake, name)

    def test_the_script_points_the_runner_at_the_synthetic_set(self):
        with open(os.path.join(ROOT, SYNTHETIC_SCRIPT), encoding="utf-8") as f:
            script = f.read()
        self.assertIn('SYN="$ROOT/tests/fixtures/synthetic_recomp"', script)
        self.assertIn('-DPS2X_RUNNER_GENERATED_DIR="$SYN"', script)
        self.assertIn("--target ps2EntryRunner", script)
        self.assertIn('"$rc" -ne 68', script, "the smoke must require the preflight's elf-missing exit")
        code = "\n".join(l for l in script.splitlines() if not l.lstrip().startswith("#"))
        self.assertNotRegex(code, r"\bdist(-linux)?\b", "the synthetic runner is not a game; never into dist/")


class SyntheticGeneratedSetShape(unittest.TestCase):
    """tests/fixtures/synthetic_recomp: three hand-written functions and the tables, in the recompiler's shape."""

    def _read(self, name):
        with open(os.path.join(SYNTHETIC, name), encoding="utf-8") as f:
            return f.read()

    def test_three_functions_and_the_tables(self):
        self.assertEqual(sorted(os.listdir(SYNTHETIC)), sorted([
            "entry_0x100000.cpp", "sub_00100020_0x100020.cpp", "rand_0x100030.cpp", "register_functions.cpp",
            "ps2_recompiled_functions.h", "ps2_recompiled_stubs.h"]))

    def test_declared_defined_and_tabled_agree(self):
        decl = re.compile(r"(?m)^void (\w+_0x([0-9a-f]+))\(uint8_t\* rdram, R5900Context\* ctx, PS2Runtime ?\* ?runtime\);")
        declared = {}
        for h in ("ps2_recompiled_functions.h", "ps2_recompiled_stubs.h"):
            for m in decl.finditer(self._read(h)):
                declared[m.group(1)] = int(m.group(2), 16)
        self.assertEqual(len(declared), 3, declared)
        for fn in declared:
            body = self._read(fn + ".cpp")
            self.assertRegex(body, r"(?m)^void " + fn + r"\(uint8_t\* rdram, R5900Context\* ctx, PS2Runtime \*runtime\) \{")
        reg = self._read("register_functions.cpp")
        base = int(re.search(r"g_ps2RecompiledFunctionTableBase = 0x([0-9a-f]+)u;", reg).group(1), 16)
        end = int(re.search(r"g_ps2RecompiledFunctionTableEnd = 0x([0-9a-f]+)u;", reg).group(1), 16)
        count = int(re.search(r"g_ps2RecompiledFunctionTableSlotCount = (\d+)u;", reg).group(1))
        self.assertEqual(count, (end - base) >> 2)
        self.assertIn(f"g_ps2RecompiledFunctionTable[{count}u] = {{}};", reg)
        rows = re.findall(r"g_ps2RecompiledFunctionTable\[(\d+)\] = (\w+); // 0x([0-9a-f]+)", reg)
        self.assertTrue(rows)
        self.assertEqual({fn for _, fn, _ in rows}, set(declared), "every function tabled, nothing else")
        for slot, fn, addr in rows:
            self.assertLess(int(slot), count)
            self.assertEqual(int(addr, 16), base + 4 * int(slot), f"slot {slot}'s comment")
            self.assertGreaterEqual(int(addr, 16), declared[fn], f"{fn} owns 0x{addr} only from its own start")
        for fn, start in declared.items():
            self.assertEqual(dict((f, a) for _, f, a in rows if int(a, 16) == start).get(fn), f"{start:x}",
                             f"{fn}'s own address is its slot")

    def test_nothing_at_the_games_addresses(self):
        # Hand-written, never copied from recomp/output: nothing at or above the game's text (0x180008 up).
        for name in os.listdir(SYNTHETIC):
            # Every address, not the instruction words the comments print after one (`// 0x100000: 0x27bdfff0`).
            for m in re.finditer(r"(?<!: )0x([0-9a-fA-F]{5,8})", self._read(name)):
                self.assertLess(int(m.group(1), 16), GAME_TEXT_START, f"{name}: {m.group(0)} is in the game's range")


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
            runs = [s for s in doc["jobs"][build]["steps"] if SYNTHETIC_SCRIPT in (s.get("run") or "")]
            self.assertEqual(len(runs), 1, name)
            self.assertIn(f"--build-dir {SYNTHETIC_TREE[name]}", runs[0]["run"], name)
            self.assertEqual(runs[0]["if"], "${{ !cancelled() && steps.build.outcome == 'success' }}", name)
        for check, wf in REQUIRED_CHECKS.items():
            jobs = yaml.safe_load(_text(wf))["jobs"]
            self.assertIn(check, jobs, wf)
            self.assertNotIn("name", jobs[check], wf)


if __name__ == "__main__":
    unittest.main()
