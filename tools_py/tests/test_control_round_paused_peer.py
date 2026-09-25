"""Sprint 13 V7 (#34) -- scripts/parity/control_round_paused_peer.sh and tools_py/parity/peer_pause.py.

Textual where a run would launch a game (the script's knobs, its sources, that it never takes the lock), executed
where it refuses before any launch (--before without SOCOM_EXE, --peer console without LAN_IP, an unknown --peer),
and the pause orchestration with its IO faked: the suspend and the resume in order, the resume even when a capture
fails, the byte range of A's log and the frames in pause.json, a driver that ends before the round."""
import json
import os
import re
import subprocess
import tempfile
import unittest

from tools_py.parity import peer_pause as P
from tools_py.tests.shell import BASH

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(ROOT, "scripts", "parity", "control_round_paused_peer.sh")
MIXED2 = os.path.join(ROOT, "scripts", "parity", "mixed_match2.sh")


def text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def code_lines(src):
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


class ScriptText(unittest.TestCase):
    def setUp(self):
        self.src = text(SCRIPT)
        self.code = code_lines(self.src)

    def test_sources_env_and_the_environment_writer(self):
        self.assertRegex(self.code, r'(?m)^\. "\$\(dirname "\$0"\)/env\.sh"$')
        self.assertRegex(self.code, r'(?m)^\. "\$\(dirname "\$0"\)/write_env\.sh"')
        self.assertRegex(self.code, r"(?m)^\s*write_env_ps2x \"\$OUT\"")

    def test_sets_the_rounds_knobs(self):
        for knob in ("PS2X_PC_SAMPLER=0.25", "PS2X_CLOCK_TRACE=1", "PS2X_SOCOM2_NET_TRACE=1", "PS2X_GS_STATS=1",
                     "PS2X_SOCOM2_RSA_KEY_B=b"):
            self.assertRegex(self.code, r"(?m)^export %s(\s|$)" % re.escape(knob))

    def test_never_takes_the_lock(self):
        self.assertNotRegex(self.code, r"loop_lock\.sh|run_detached\.sh")

    def test_pauses_through_peer_pause_and_reads_through_the_readout(self):
        self.assertIn("-m tools_py.parity.peer_pause run", self.code)
        self.assertIn('--stop-file "$OUT/.driver_rc"', self.code)
        self.assertIn("-m tools_py.parity.control_round_readout paused-peer", self.code)
        self.assertIn("-m tools_py.parity.freeze_trace", self.code)

    def test_the_ours_peer_is_a_hold_round_without_watches(self):
        drive = re.search(r"online_match_ours ([^>]*)>", self.code.replace("\\\n", " "))
        self.assertIsNotNone(drive)
        args = drive.group(1)
        self.assertIn("--prefilled", args)
        self.assertIn('--hold "$HOLD"', args)
        for watched in ("--control-round", "--converge", "--until-kill"):
            self.assertNotIn(watched, args, "a watched endgame would end the round on the paused peer")

    def test_writes_under_logs_parity_and_a_done_marker(self):
        self.assertIn("logs/parity/s13_v7_paused_peer_", self.code)
        self.assertIn('> "logs/${NAME}.done"', self.code)
        # the marker carries the DECISIVE outcome and the executor verdict, not the latter alone
        self.assertIn("RESULT PAUSED-PEER [A-Z]* [A-Z]*", self.code)

    def test_the_console_peer_runs_the_mixed_leg_with_a_long_hold(self):
        self.assertIn('MIXED_HOLD="$HOLD" bash scripts/parity/mixed_match2.sh', self.code)
        self.assertIn('--hold "$MIXED_HOLD"', code_lines(text(MIXED2)))
        self.assertIn('MIXED_HOLD="${MIXED_HOLD:-30}"', text(MIXED2), "the leg's own default is unchanged")
        self.assertIn('--foreign-b "${PREFILLED[@]}"', code_lines(text(MIXED2)), "O1: ours logs in prefilled")
        self.assertIn('[ "${MIXED_PREFILLED:-1}" = 0 ] && PREFILLED=()', text(MIXED2))


@unittest.skipIf(BASH is None, "no bash")
class ScriptRefusesBeforeAnyLaunch(unittest.TestCase):
    def run_script(self, args, env_extra=None, drop=()):
        name = "test_paused_peer_refusal_%d" % os.getpid()
        out = os.path.join("logs", "parity", name)
        env = dict(os.environ)
        for k in ("SOCOM_EXE", "LAN_IP", "SOCOM_SERVER_IP", "PS2X_SOCOM2_SERVER", "SOCOM_GAME_ELF") + tuple(drop):
            env.pop(k, None)
        env.update(env_extra or {})
        try:
            p = subprocess.run([BASH, SCRIPT] + args + [out], cwd=ROOT, env=env, capture_output=True, text=True,
                               timeout=120)
            done = os.path.join(ROOT, "logs", name + ".done")
            marker = text(done) if os.path.exists(done) else ""
            return p, marker
        finally:
            for rel in (os.path.join("logs", name + ".done"),):
                try:
                    os.remove(os.path.join(ROOT, rel))
                except OSError:
                    pass
            import shutil
            shutil.rmtree(os.path.join(ROOT, out), ignore_errors=True)

    def test_before_needs_the_exe_named(self):
        p, marker = self.run_script(["--before"])
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("--before needs SOCOM_EXE", p.stderr)
        self.assertTrue(marker.startswith("done 2 refused-before-without-exe"), marker)

    def test_console_needs_a_lan_address(self):
        p, marker = self.run_script(["--peer", "console"])
        self.assertEqual(p.returncode, 9, p.stderr)
        self.assertIn("LAN_IP", p.stderr)
        self.assertTrue(marker.startswith("done 9 refused-lan-ip"), marker)

    def test_an_unknown_peer_is_refused(self):
        p, _ = self.run_script(["--peer", "pcsx"])
        self.assertEqual(p.returncode, 2)
        self.assertIn("--peer is ours or console", p.stderr)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.now += s


class PauserOrchestration(unittest.TestCase):
    def make(self, out, clocks, stop_file=None, copy=None, sizes=None, image="socom2.exe", **kw):
        clk = FakeClock()
        calls = []
        sizes = iter(sizes or [5000, 9000])

        def size_of(path):
            got = next(sizes)
            if isinstance(got, Exception):
                raise got
            return got

        def suspend(pid):
            with open(os.path.join(out, "pause.json"), encoding="utf-8") as f:
                calls.append(("on-disk-before-suspend", json.load(f).get("pid"), clk()))
            calls.append(("suspend", pid, clk()))
        it = iter(clocks)
        last = [None]

        def round_clock(_path):
            try:
                last[0] = next(it)
            except StopIteration:
                pass
            return last[0]

        p = P.Pauser(out, "ours", pause_s=6, at_clock=30, pre_s=4, post_s=4, every_s=2, timeout_s=60,
                     stop_file=stop_file, clock=clk, sleep=clk.sleep, find_log=lambda: "logs/run_A_x.log",
                     round_clock=round_clock, pid_of=lambda: 4242,
                     do_suspend=suspend,
                     do_resume=lambda pid: calls.append(("resume", pid, clk())),
                     size_of=size_of, copy=copy or (lambda s, d: None),
                     mtime_of=lambda path: clk(), image_of=lambda pid: image, **kw)
        return p, calls

    @staticmethod
    def kinds(calls):
        return [c[0] for c in calls if c[0] != "on-disk-before-suspend"]

    def test_waits_for_the_round_then_suspends_captures_and_resumes(self):
        with tempfile.TemporaryDirectory() as d:
            p, calls = self.make(d, [None, 0.0, 12.0, 31.0])
            rec = p.run()
            self.assertIsNone(rec["error"])
            self.assertEqual(self.kinds(calls), ["suspend", "resume"])
            self.assertEqual(calls[0], ("on-disk-before-suspend", 4242, calls[1][2]), "the pid is written first")
            self.assertEqual(calls[1][1], 4242)
            self.assertGreaterEqual(calls[2][2] - calls[1][2], 6)
            self.assertEqual((rec["a_log_bytes_at_suspend"], rec["a_log_bytes_at_resume"]), (5000, 9000))
            phases = [f["phase"] for f in rec["frames"]]
            self.assertEqual(phases.count("pause"), 4)          # 0, 2, 4, 6 s
            self.assertEqual(phases[0], "pre")
            self.assertEqual(phases[-1], "post")
            with open(os.path.join(d, "pause.json"), encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["pid"], 4242)
            self.assertEqual(saved["round_clock_at_start"], 31.0)

    def test_the_peer_is_resumed_even_when_a_capture_fails(self):
        with tempfile.TemporaryDirectory() as d:
            state = {"n": 0}

            def copy(src, dst):
                state["n"] += 1
                if dst.endswith("_pause.png"):
                    raise RuntimeError("disk full")
            p, calls = self.make(d, [40.0], copy=copy)
            rec = p.run()
            self.assertEqual(self.kinds(calls), ["suspend", "resume"])
            self.assertIn("disk full", rec["error"])
            self.assertEqual(rec["a_log_bytes_at_resume"], 9000)

    def test_a_failing_size_read_never_skips_the_resume(self):
        with tempfile.TemporaryDirectory() as d:
            p, calls = self.make(d, [40.0], sizes=[5000, OSError("log gone")])
            rec = p.run()
            self.assertEqual(self.kinds(calls), ["suspend", "resume"])
            self.assertIn("log gone", rec["error"])
            self.assertFalse(rec["suspended"])

    def test_a_pid_that_is_not_the_peers_image_is_never_suspended(self):
        with tempfile.TemporaryDirectory() as d:
            p, calls = self.make(d, [40.0], image="explorer.exe")
            rec = p.run()
            self.assertEqual(calls, [])
            self.assertIn("not the ours peer's image", rec["error"])
            self.assertTrue(P.image_matches("console", "pcsx2-qt.exe"))
            self.assertFalse(P.image_matches("ours", None))

    def test_a_driver_that_ends_first_is_recorded_and_nothing_is_suspended(self):
        with tempfile.TemporaryDirectory() as d:
            stop = os.path.join(d, ".driver_rc")
            with open(stop, "w") as f:
                f.write("4\n")
            p, calls = self.make(d, [0.0], stop_file=stop)
            rec = p.run()
            self.assertEqual(calls, [])
            self.assertIn("the driver ended", rec["error"])
            self.assertNotIn("a_log_bytes_at_suspend", rec)


class PeerPid(unittest.TestCase):
    def test_console_peer_from_pcsx2_ctl_state(self):
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "s4_instances.json")
            with open(state, "w") as f:
                json.dump({"B": {"pid": 777, "t0": 1.0}}, f)
            self.assertEqual(P.peer_pid("console", state_path=state), 777)

    def test_ours_peer_by_its_window_title(self):
        class Shot:
            @staticmethod
            def find_window(title):
                return 99 if title == P.PEER_TITLE else None

            @staticmethod
            def window_pid(hwnd):
                return 1234 if hwnd == 99 else 0
        self.assertEqual(P.peer_pid("ours", shot=Shot), 1234)

    def test_posix_suspend_is_a_stop_signal(self):
        sent = []
        orig = P.os.kill
        P.os.kill = lambda pid, sig: sent.append((pid, sig))
        try:
            P.suspend(5, platform="linux")
            P.resume(5, platform="linux")
        finally:
            P.os.kill = orig
        self.assertEqual([s for _, s in sent], [P.SIGSTOP, P.SIGCONT])


if __name__ == "__main__":
    unittest.main()
