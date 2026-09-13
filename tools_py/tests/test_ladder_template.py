"""Sprint 5 Task 5 fix round, slice 3 -- the ladder launch template (review of finish (vi), I4; R47):

  * the launch's ROUTE resolves inside the pinned snapshot, and `--dry-run --pinned` exercises exactly that snapshot
    (the DRY-RUN line prints harness=<sha>, not <sha>-live, and a route under <out>/harness);
  * pin_harness's exit status and its import check are checked: a failing pin is PIN-FAIL (exit 7), never a silent
    fall back to the live tree;
  * R47: the done marker records a harness exit 4 as `LOBBY-FAIL <class>`;
  * minor: the template's knob comment names SECONDS_RUN.

unittest only; no game (the pinned dry run archives HEAD into a temp dir).
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE = os.path.join(ROOT, "scripts", "parity", "ladder_frostfire.sh")
BASH = shutil.which("bash")
if os.name == "nt":
    for cand in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if os.path.exists(cand):
            BASH = cand
            break


def fwd(p):
    return p.replace("\\", "/")


@unittest.skipUnless(BASH, "bash not found")
class LadderTemplateTest(unittest.TestCase):
    def run_t(self, args, env_extra=None, timeout=300):
        env = dict(os.environ, **(env_extra or {}))
        return subprocess.run([BASH, fwd(TEMPLATE)] + args, capture_output=True, text=True, cwd=ROOT, env=env,
                              timeout=timeout)

    def tmp(self):
        d = tempfile.mkdtemp(prefix="ladder_tpl_")
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def test_the_done_marker_records_exit_4_as_lobby_fail(self):
        d = self.tmp()
        log = os.path.join(d, "drive.txt")
        with open(log, "w") as f:
            f.write("[A] LOBBY RESEND ready-dropped attempt=3\n[A] RESULT LOBBY-FAIL ready-dropped -- READY never "
                    "registered\n[A] LOBBY class=ready-dropped\n")
        p = self.run_t(["--outcome", "4", fwd(log)])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stdout.strip(), "done 4 mpexit=4 LOBBY-FAIL ready-dropped")
        self.assertEqual(self.run_t(["--outcome", "0", fwd(log)]).stdout.strip(), "done 0 mpexit=0 KILL")
        with open(TEMPLATE) as f:
            text = f.read()
        self.assertIn('echo "done $rc mpexit=$rc $(outcome "$rc" "logs/parity/drive_${NAME}.txt") $ident" > '
                      '"logs/${NAME}.done"', text)

    def test_the_pinned_dry_run_exercises_the_snapshot(self):
        d = fwd(self.tmp())
        p = self.run_t(["--dry-run", "--pinned", d])
        out = p.stdout + p.stderr
        self.assertEqual(p.returncode, 0, out)
        line = next((ln for ln in out.splitlines() if ln.startswith("DRY-RUN OK")), "")
        self.assertRegex(line, r" harness=[0-9a-f]{12} ", out)
        self.assertNotIn("-live", line)
        m = re.search(r" route=(\S+)", line)
        self.assertTrue(m and fwd(m.group(1)).startswith(d + "/harness/tools_py/parity/routes/"), line)
        self.assertTrue(os.path.exists(os.path.join(d, "harness", "HARNESS_COMMIT")))

    def test_the_pinned_dry_run_takes_a_relative_out_dir(self):
        # the launch default is relative (logs/parity/...): pin_harness.sh's own prefix check WARNs on it, the
        # template's python real-path check must not
        rel = "logs/parity/test_pinned_%d" % os.getpid()
        self.addCleanup(shutil.rmtree, os.path.join(ROOT, rel), True)
        p = self.run_t(["--dry-run", "--pinned", rel])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(" route=" + rel + "/harness/tools_py/parity/routes/frostfire_v2.json ", p.stdout)

    def test_a_failing_pin_fails_loudly(self):
        d = fwd(self.tmp())
        for body in ("echo 'pin_harness: cannot resolve HEAD'; exit 2",
                     "mkdir -p \"$1/harness\"; echo 'pin_harness: WARNING -- pinned import check did not resolve' >&2; "
                     "echo \"$1/harness\"; exit 0"):
            fake = os.path.join(d, "fake_pin.sh")
            with open(fake, "w", newline="\n") as f:
                f.write("#!/usr/bin/env bash\n" + body + "\n")
            p = self.run_t(["--dry-run", "--pinned", d + "/out"], env_extra={"PIN_HARNESS_SH": fwd(fake)})
            self.assertEqual(p.returncode, 7, p.stdout + p.stderr)
            self.assertIn("PIN-FAIL", p.stderr)
            self.assertNotIn("DRY-RUN OK", p.stdout)

    def test_the_launch_route_is_the_snapshots_and_the_comment_names_seconds_run(self):
        with open(TEMPLATE) as f:
            text = f.read()
        self.assertIn('ROUTE="${ROUTE:-$HARNESS/tools_py/parity/routes/frostfire_v2.json}"', text)
        self.assertIn("SECONDS_RUN (2400", text)
        self.assertNotIn("SECONDS (2400", text)


if __name__ == "__main__":
    unittest.main()
