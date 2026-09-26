"""build.sh consults the loop lock (Sprint 14 G5).

`./build.sh recomp|runtime|release|test|all` refuses (exit 3, run_detached's refusal code) while another holder has
the loop lock, unless it runs as that holder's child (LOOP_LOCK_HELD, exported by `loop_lock.sh run` and
run_detached.sh). `tools` never consults the lock. The consult runs for `--dry-run` too, so these tests exercise it
without building anything: `--dry-run` prints the plan and exits before the toolchain check.

Never the real lock: LOOP_LOCK_PATH points at a temp dir and LOOP_LOCK_PS_CMD at a fake process list, as in
test_loop_lock.py; a lock taken here is released in tearDown.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILD_SH = os.path.join(ROOT, "build.sh").replace("\\", "/")
LOCK_SH = os.path.join(ROOT, "scripts", "loop_lock.sh").replace("\\", "/")
IDLE = ["4|0||System|", "900|4||explorer.exe|C:\\Windows\\explorer.exe", "901|900||bash.exe|bash"]


def fwd(path):
    return path.replace("\\", "/")


@unittest.skipUnless(BASH, "bash not found")
class TestBuildShLockConsult(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="build_sh_lock_test_")
        self.lock = os.path.join(self.tmp, "lk")
        self.procs = os.path.join(self.tmp, "procs.txt")
        with open(self.procs, "w", newline="\n") as f:
            f.write("\n".join(IDLE) + "\n")
        self.taken = False

    def tearDown(self):
        if self.taken:
            subprocess.run([BASH, LOCK_SH, "release", "other-holder"], capture_output=True, text=True,
                           env=self.env(), timeout=60)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def env(self, **extra):
        env = dict(os.environ)
        for k in ("LOOP_LOCK_HELD", "LOOP_LOCK_SELF_WINPID"):
            env.pop(k, None)     # this suite may itself run under `loop_lock.sh run`
        env["LOOP_LOCK_PATH"] = fwd(self.lock)
        env["LOOP_LOCK_PS_CMD"] = "cat '%s'" % fwd(self.procs)
        env.update({k: str(v) for k, v in extra.items()})
        return env

    def hold(self):
        p = subprocess.run([BASH, LOCK_SH, "take", "other-holder", "--purpose", "build_sh_lock test"],
                           capture_output=True, text=True, env=self.env(), timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.taken = True
        check = subprocess.run([BASH, LOCK_SH, "check"], capture_output=True, text=True, env=self.env(), timeout=60)
        self.assertTrue(check.stdout.startswith("HELD: other-holder"), check.stdout)

    def build(self, *args, env=None):
        p = subprocess.run([BASH, BUILD_SH] + list(args), capture_output=True, text=True, cwd=ROOT,
                           env=env or self.env(), timeout=120)
        return p.returncode, p.stdout + p.stderr

    def test_held_by_another_refuses_every_locked_step(self):
        self.hold()
        for step in ("runtime", "recomp", "release", "test", "all"):
            rc, out = self.build(step, "--dry-run")
            self.assertEqual(rc, 3, "%s: %s" % (step, out))
            self.assertIn("lock held by other-holder", out)
            self.assertIn("build refused", out)
            self.assertIn("scripts/loop_lock.sh run", out)
            self.assertNotIn("would run", out, "a refused build prints no plan")

    def test_default_step_is_all_and_is_refused_too(self):
        self.hold()
        rc, out = self.build("--dry-run")
        self.assertEqual(rc, 3, out)
        self.assertIn("lock held by", out)

    def holder_id(self):
        p = subprocess.run([BASH, LOCK_SH, "id"], capture_output=True, text=True, env=self.env(), timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(p.stdout.startswith("other-holder "), p.stdout)
        return p.stdout.strip()

    def test_the_holders_child_proceeds(self):
        self.hold()
        rc, out = self.build("runtime", "--dry-run", env=self.env(LOOP_LOCK_HELD=self.holder_id()))
        self.assertEqual(rc, 0, out)
        self.assertNotIn("lock held by", out)
        self.assertNotIn("stale", out)
        self.assertIn("would run", out)

    def test_a_stale_holder_value_is_refused(self):
        self.hold()
        live = self.holder_id()
        rc, out = self.build("runtime", "--dry-run", env=self.env(LOOP_LOCK_HELD="bogus 1"))
        self.assertEqual(rc, 3, out)
        self.assertIn("LOOP_LOCK_HELD is stale: 'bogus 1' vs holder '%s'" % live, out)
        self.assertNotIn("would run", out)

    def test_a_set_holder_value_on_a_free_lock_proceeds(self):
        rc, out = self.build("runtime", "--dry-run", env=self.env(LOOP_LOCK_HELD="bogus 1"))
        self.assertEqual(rc, 0, out)
        self.assertIn("would run", out)

    def test_free_lock_proceeds_and_prints_the_plan(self):
        rc, out = self.build("runtime", "--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertIn("would run", out)
        self.assertIn("runtime", out)
        self.assertNotIn("lock held by", out)

    def test_tools_never_consults_the_lock(self):
        self.hold()
        rc, out = self.build("tools", "--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("lock held by", out)
        self.assertIn("would run", out)

    def test_dry_run_is_parsed_before_the_toolchain_check(self):
        # Static: a machine with no toolchain must still get the plan, so the dry-run exit precedes the check.
        with open(os.path.join(ROOT, "build.sh")) as f:
            text = f.read()
        self.assertLess(text.index('if [ "$DRY_RUN" = 1 ]'), text.index("no toolchain under tools/"))


if __name__ == "__main__":
    unittest.main()
