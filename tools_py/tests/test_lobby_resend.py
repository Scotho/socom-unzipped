"""Sprint 5 R47 / plan Amendment A6: the lobby's screen-verified re-send and per-stage timeouts.

The signature fixtures are crops of the launch 8a/8b/8c captures (tools_py/tests/fixtures/lobby/README.md), pasted
back into a black 640x448 frame at their recorded box so the detectors read them exactly where the live frame has them.
"""
import os
import tempfile
import unittest
from unittest import mock

from PIL import Image

from tools_py.parity import online_login_ours as L
from tools_py.parity import winshot

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "lobby")
PANEL = (335, 110, 625, 380)
READY = (14, 150, 175, 190)


def frame(name, box):
    im = Image.new("L", (640, 448), 0)
    im.paste(Image.open(os.path.join(FIX, name)).convert("L"), box[:2])
    return im.convert("RGB")


MAP_PRE_8B = frame("map_8b_pre.png", PANEL)
MAP_DROPPED_8B = frame("map_8b_post_dropped.png", PANEL)
MAP_PRE_8C = frame("map_8c_pre.png", PANEL)
MAP_TAKEN_8C = frame("map_8c_post_taken.png", PANEL)
READY_DROPPED_8A = frame("ready_8a_A_dropped.png", READY)
READY_TAKEN_8A_B = frame("ready_8a_B_taken.png", READY)
READY_LEFT_8C = frame("ready_8c_A_left_lobby.png", READY)


def gray(im):
    return L.lobby_gray_of(im)


class FakeShell(L.Shell):
    """A Shell without the reference images: records logs, presses and shots."""

    def __init__(self, pad_file="pad.txt"):          # deliberately skips Shell.__init__
        self.hwnd, self.out, self.t0, self.tag, self.pad_file = 1, tempfile.gettempdir(), 0.0, "A_", pad_file
        self.logs, self.presses, self.shots = [], [], []

    def log(self, m):
        self.logs.append(m)

    def press(self, b, wait=1.0):
        self.check_stage()
        self.presses.append(("key", b))

    def pad_press(self, b, wait=0.35, hold_s=0.09):
        self.check_stage()
        self.presses.append(("pad", b))

    def shot(self, label, max_age=None):
        self.shots.append(label)


class Grabs:
    """winshot.grab stand-in: hands out frames in order (the last repeats) and records max_age."""

    def __init__(self, *frames):
        self.frames, self.ages = list(frames), []

    def __call__(self, hwnd, max_age=None):
        self.ages.append(max_age)
        item = self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]
        if isinstance(item, BaseException):
            raise item
        return item


class SignatureDetectors(unittest.TestCase):
    def test_map_cross_dropped_on_8b_taken_on_8c(self):
        self.assertTrue(L.map_cross_dropped(gray(MAP_PRE_8B), gray(MAP_DROPPED_8B)))
        self.assertFalse(L.map_cross_dropped(gray(MAP_PRE_8C), gray(MAP_TAKEN_8C)))

    def test_map_panel_diff_values(self):
        self.assertEqual(L.map_panel_diff(gray(MAP_PRE_8B), gray(MAP_DROPPED_8B)), 0.0)
        self.assertGreater(L.map_panel_diff(gray(MAP_PRE_8C), gray(MAP_TAKEN_8C)), L.MAP_CROSS_DROPPED_MAX_DIFF)

    def test_ready_label_edge_on_real_frames(self):
        self.assertEqual(L.ready_label_edge(gray(READY_DROPPED_8A)), 48)
        self.assertIn(L.ready_label_edge(gray(READY_TAKEN_8A_B)), (82, 83))
        self.assertIsNone(L.ready_label_edge(gray(READY_LEFT_8C)))

    def test_ready_dropped_classification(self):
        self.assertTrue(L.ready_dropped(gray(READY_DROPPED_8A)))
        self.assertFalse(L.ready_dropped(gray(READY_TAKEN_8A_B)))
        # 8c: the match launched within 3 s, so no label -- not retried (a CROSS on NOT READY would un-ready)
        self.assertFalse(L.ready_dropped(gray(READY_LEFT_8C)))


class MapCrossResend(unittest.TestCase):
    def test_taken_first_time_sends_nothing_more(self):
        sh, g = FakeShell(), Grabs(MAP_PRE_8C, MAP_TAKEN_8C)
        with mock.patch.object(L.winshot, "grab", g):
            self.assertEqual(L.press_map_cross_verified(sh), 0)
        self.assertEqual(sh.presses, [("key", "cross")])
        self.assertFalse([m for m in sh.logs if "LOBBY RESEND" in m])
        self.assertTrue(all(a is not None and a <= L.LOBBY_FRAME_MAX_AGE_S for a in g.ages), g.ages)

    def test_dropped_then_taken_on_the_second_attempt(self):
        sh, g = FakeShell(), Grabs(MAP_PRE_8B, MAP_DROPPED_8B, MAP_TAKEN_8C)
        with mock.patch.object(L.winshot, "grab", g):
            self.assertEqual(L.press_map_cross_verified(sh), 1)
        self.assertEqual(sh.presses, [("key", "cross"), ("pad", "CROSS")])
        self.assertIn("LOBBY RESEND map-cross-dropped attempt=1", sh.logs)

    def test_two_drops_then_taken(self):
        sh, g = FakeShell(), Grabs(MAP_PRE_8B, MAP_DROPPED_8B, MAP_DROPPED_8B, MAP_TAKEN_8C)
        with mock.patch.object(L.winshot, "grab", g):
            self.assertEqual(L.press_map_cross_verified(sh), 2)
        self.assertEqual([m for m in sh.logs if "LOBBY RESEND" in m],
                         ["LOBBY RESEND map-cross-dropped attempt=1", "LOBBY RESEND map-cross-dropped attempt=2"])

    def test_lobby_fail_after_three_resends(self):
        sh, g = FakeShell(), Grabs(MAP_PRE_8B, MAP_DROPPED_8B)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.press_map_cross_verified(sh)
        self.assertEqual(cm.exception.cls, "map-cross-dropped")
        self.assertEqual(cm.exception.code, L.LOBBY_FAIL_EXIT)
        self.assertIsInstance(cm.exception, SystemExit)
        self.assertEqual(len([p for p in sh.presses if p[0] == "pad"]), L.LOBBY_RESEND_MAX)
        self.assertEqual(L.LOBBY_RESEND_MAX, 3)
        self.assertTrue(any(m.startswith("RESULT LOBBY-FAIL map-cross-dropped") for m in sh.logs), sh.logs)
        self.assertIn("LOBBY class=map-cross-dropped", sh.logs)

    def test_without_a_pad_file_the_resend_is_a_posted_key(self):
        sh, g = FakeShell(pad_file=None), Grabs(MAP_PRE_8B, MAP_DROPPED_8B, MAP_TAKEN_8C)
        with mock.patch.object(L.winshot, "grab", g):
            L.press_map_cross_verified(sh)
        self.assertEqual(sh.presses, [("key", "cross"), ("key", "cross")])

    def test_a_stale_frame_is_waited_out_not_read_as_dropped(self):
        stale = winshot.StaleFrameError("latest.png", 9.6, L.LOBBY_FRAME_MAX_AGE_S)
        sh, g = FakeShell(), Grabs(MAP_PRE_8C, stale, MAP_TAKEN_8C)
        with mock.patch.object(L.winshot, "grab", g):
            self.assertEqual(L.press_map_cross_verified(sh), 0)
        self.assertEqual(sh.presses, [("key", "cross")])


class ReadyResend(unittest.TestCase):
    def run_ready(self, *frames):
        sh, g = FakeShell(), Grabs(*frames)
        with mock.patch.object(L.winshot, "grab", g), mock.patch.object(L, "lobby_select") as sel:
            try:
                L.ready(sh)
            finally:
                self.sh, self.sel = sh, sel
        return sh, sel

    def test_taken(self):
        sh, sel = self.run_ready(READY_TAKEN_8A_B)
        self.assertEqual(sh.presses, [("key", "cross")])
        self.assertEqual(sel.call_count, 1)
        self.assertIn("19_ready", sh.shots)

    def test_dropped_then_taken_on_the_second_attempt(self):
        sh, sel = self.run_ready(READY_DROPPED_8A, READY_TAKEN_8A_B)
        self.assertEqual(sh.presses, [("key", "cross"), ("pad", "CROSS")])
        self.assertEqual(sel.call_count, 2)                     # the cursor is re-checked before the re-send
        self.assertIn("LOBBY RESEND ready-dropped attempt=1", sh.logs)

    def test_lobby_left_is_not_resent(self):
        sh, _ = self.run_ready(READY_LEFT_8C)
        self.assertEqual(sh.presses, [("key", "cross")])

    def test_lobby_fail_after_three_resends(self):
        with self.assertRaises(L.LobbyFail) as cm:
            self.run_ready(READY_DROPPED_8A)
        self.assertEqual((cm.exception.cls, cm.exception.code), ("ready-dropped", L.LOBBY_FAIL_EXIT))
        self.assertEqual(len([p for p in self.sh.presses if p[0] == "pad"]), 3)


class StageTimeouts(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.sh = FakeShell()
        self.sh.clock = lambda: self.now[0]

    def test_constants(self):
        self.assertEqual(L.LOBBY_STAGES, ("login", "host", "join", "map_select", "ready", "launch"))
        self.assertLessEqual(L.LOBBY_STAGE_TIMEOUT_S, 180.0)
        self.assertNotIn(L.LOBBY_FAIL_EXIT, (0, 1, 2, 3))     # go, FAIL, NO-DATA, NO-CONTROL

    def test_lobby_functions_are_staged(self):
        for fn, stage in ((L.login, "login"), (L.to_briefing_room, "login"), (L.host_game, "host"),
                          (L.choose_map, "map_select"), (L.join_game, "join"), (L.ready, "ready")):
            self.assertEqual(getattr(fn, "lobby_stage", None), stage, fn.__name__)

    def test_unknown_stage_is_refused(self):
        with self.assertRaises(ValueError):
            with L.lobby_stage(self.sh, "armory"):
                pass

    def test_timeout_fires_after_the_budget(self):
        with self.assertRaises(L.LobbyFail) as cm:
            with L.lobby_stage(self.sh, "login"):
                self.now[0] += L.LOBBY_STAGE_TIMEOUT_S - 1
                self.sh.press("cross")                          # inside the budget: fine
                self.now[0] += 2
                self.sh.press("cross")
        self.assertEqual((cm.exception.cls, cm.exception.code), ("timeout:login", L.LOBBY_FAIL_EXIT))
        self.assertEqual(len(self.sh.presses), 1)
        self.assertTrue(any(m.startswith("RESULT LOBBY-FAIL timeout:login") for m in self.sh.logs))
        self.assertIn("LOBBY class=timeout:login", self.sh.logs)

    def test_no_stage_no_timeout_and_the_stage_is_cleared(self):
        with L.lobby_stage(self.sh, "join"):
            pass
        self.now[0] += 10000
        self.sh.check_stage()                                   # gameplay presses are never lobby timeouts

    def test_nested_stage_reports_the_expired_outer_stage(self):
        with self.assertRaises(L.LobbyFail) as cm:
            with L.lobby_stage(self.sh, "host"):
                self.now[0] += 170
                with L.lobby_stage(self.sh, "map_select"):
                    self.now[0] += 20
                    self.sh.check_stage()
        self.assertEqual(cm.exception.cls, "timeout:host")

    def test_real_press_sleep_is_cut_at_the_deadline(self):
        sh = L.Shell.__new__(L.Shell)
        sh.hwnd, sh.t0, sh.tag, sh.pad_file = 1, 0.0, "B_", None
        sh.log, sh.shot = (lambda m: None), (lambda *a, **k: None)
        sh.clock = lambda: self.now[0]
        slept = []

        def sleep(s):
            slept.append(s)
            self.now[0] += s

        with mock.patch.object(L.keys, "press"), mock.patch.object(L.time, "sleep", sleep):
            with self.assertRaises(L.LobbyFail) as cm:
                with L.lobby_stage(sh, "join"):
                    self.now[0] += L.LOBBY_STAGE_TIMEOUT_S - 5
                    sh.press("cross", 25.0)
        self.assertEqual(cm.exception.cls, "timeout:join")
        self.assertEqual(slept, [5.0])

    def test_launch_wait_budget_is_shared(self):
        self.assertEqual(L.lobby_launch_budget(self.now[0], clock=lambda: self.now[0] + 30.0),
                         L.LOBBY_STAGE_TIMEOUT_S - 30.0)
        self.assertEqual(L.lobby_launch_budget(self.now[0], clock=lambda: self.now[0] + 500.0), 1.0)


if __name__ == "__main__":
    unittest.main()
