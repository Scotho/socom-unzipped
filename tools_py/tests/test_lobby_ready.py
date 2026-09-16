"""Sprint 6, launch s6_ladder4 (docs/research/30-scope-at-spawn.md): after the host readied, B's READY code
could not read the lobby cursor, pressed DOWN/UP eight times a second apart and CROSS "for READY" -- all
delivered to a match that had already started, where D-pad UP/DOWN are the scope zoom cyclers (decomp
FUN_00594cf0), so B spawned scoped 3.0x and the control precondition failed.

The cursor search now reads a fresh frame before every press, stops the moment the title band is no longer
GAME LOBBY, is bounded at LOBBY_CURSOR_PRESSES presses, presses CROSS without a cursor only when the READY
row reads lit, and otherwise fails as `ready:cursor-not-found`. Frames are scripted from the fixtures under
tools_py/tests/fixtures/lobby/ pasted into a black 640x448 frame (the test_online_login_lobby pattern).
"""
import unittest
from unittest import mock

import numpy as np
from PIL import Image

from tools_py.parity import online_login_ours as L
from tools_py.tests import test_online_login_lobby as T

FakeShell, Grabs, frame, gray, TITLE, NOTICE = T.FakeShell, T.Grabs, T.frame, T.gray, T.TITLE, T.NOTICE
READY_BOX = (14, 150, 175, 190)          # the ready_8a_* crops (fixtures README)
LOBBY_TITLE = ("title_lad2_game_lobby.png", TITLE)

# GAME LOBBY with the cursor on READY (8a A: teal fill, row-2 mean 69, median 68): the normal state.
LOBBY_CURSOR_READY = frame(LOBBY_TITLE, ("notice_gone_8c.png", NOTICE), ("ready_8a_A_dropped.png", READY_BOX))
# GAME LOBBY after the CROSS registered: NOT READY on row 2 (8a B).
LOBBY_NOT_READY = frame(LOBBY_TITLE, ("notice_gone_8c.png", NOTICE), ("ready_8a_B_taken.png", READY_BOX))
# GAME LOBBY with no cursor drawn (every *_17_game_lobby_ok capture: the three rows read 29-33, -1).
LOBBY_NO_CURSOR = frame(LOBBY_TITLE, ("notice_gone_8c.png", NOTICE))
# The match started / a loading screen: no GAME LOBBY title, no row-2 label (8c A after launch).
LOBBY_GONE = frame(("title_kill4_no_lobby.png", TITLE), ("ready_8c_A_left_lobby.png", READY_BOX))
BLACK = Image.new("RGB", (640, 448), 0)


def lit_without_cursor():
    """A GAME LOBBY whose READY row reads lit by median (68 > 50) but not by mean (41 <= 50): the
    cursor detector and the row detector disagreeing. Synthetic -- no capture shows this; it pins the
    row-lit fallback branch (item 3) without going through the cursor branch."""
    im = np.asarray(LOBBY_NO_CURSOR.convert("L"), dtype=np.uint8).copy()
    y0, y1, x0, x1 = L.LOBBY_ROWS["ready"]
    band = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    band[:, : int(0.6 * (x1 - x0))] = 68
    im[y0:y1, x0:x1] = band
    return Image.fromarray(im).convert("RGB")


LOBBY_LIT_NO_CURSOR = lit_without_cursor()


class Detectors(unittest.TestCase):
    def test_cursor_of(self):
        self.assertEqual(L.lobby_cursor_of(gray(LOBBY_CURSOR_READY))[0], 2)
        self.assertEqual(L.lobby_cursor_of(gray(LOBBY_NOT_READY))[0], 2)
        self.assertEqual(L.lobby_cursor_of(gray(LOBBY_NO_CURSOR))[0], -1)
        self.assertEqual(L.lobby_cursor_of(gray(LOBBY_GONE))[0], -1)
        self.assertEqual(L.lobby_cursor_of(gray(BLACK))[0], -1)
        self.assertEqual(L.lobby_cursor_of(gray(LOBBY_LIT_NO_CURSOR))[0], -1)
        means = L.lobby_cursor_of(gray(LOBBY_CURSOR_READY))[1]
        self.assertEqual(len(means), 3)
        self.assertGreater(means[2], 60)

    def test_ready_row_lit(self):
        self.assertTrue(L.lobby_row_lit(gray(LOBBY_CURSOR_READY), "ready"))
        self.assertTrue(L.lobby_row_lit(gray(LOBBY_NOT_READY), "ready"))
        self.assertTrue(L.lobby_row_lit(gray(LOBBY_LIT_NO_CURSOR), "ready"))
        self.assertFalse(L.lobby_row_lit(gray(LOBBY_NO_CURSOR), "ready"))
        self.assertFalse(L.lobby_row_lit(gray(LOBBY_GONE), "ready"))
        self.assertFalse(L.lobby_row_lit(gray(BLACK), "ready"))

    def test_titles(self):
        self.assertTrue(L.lobby_title_is(gray(LOBBY_NO_CURSOR), "game_lobby"))
        self.assertTrue(L.lobby_title_is(gray(LOBBY_LIT_NO_CURSOR), "game_lobby"))
        self.assertFalse(L.lobby_title_is(gray(LOBBY_GONE), "game_lobby"))
        self.assertFalse(L.lobby_title_is(gray(BLACK), "game_lobby"))

    def test_bound(self):
        self.assertEqual(L.LOBBY_CURSOR_PRESSES, 4)


DOWN, UP, CROSS, PAD_CROSS = ("key", "down"), ("key", "up"), ("key", "cross"), ("pad", "CROSS")
WIGGLE = [DOWN, UP, DOWN, UP]
GONE_LINE = "[lobby] game lobby gone during READY search -- no more presses"


def run_ready(*frames):
    sh, g = FakeShell(), Grabs(*frames)
    with mock.patch.object(L.winshot, "grab", g):
        L.ready(sh)
    return sh, g


class ReadySearch(unittest.TestCase):
    def test_a_cursor_on_ready_at_first_read_one_cross_no_wiggle(self):
        sh, g = run_ready(LOBBY_CURSOR_READY, LOBBY_NOT_READY)
        self.assertEqual(sh.presses, [CROSS])
        self.assertIn("lobby cursor 2 for READY", sh.logs)
        self.assertIn("19_ready", sh.shots)
        self.assertTrue(all(a is not None and a <= L.LOBBY_FRAME_MAX_AGE_S for a in g.ages), g.ages)

    def test_b_cursor_never_read_lobby_up_ready_row_lit_four_presses_then_cross(self):
        sh, _ = run_ready(*[LOBBY_NO_CURSOR] * 4, LOBBY_LIT_NO_CURSOR, LOBBY_NOT_READY)
        self.assertEqual(sh.presses, WIGGLE + [CROSS])
        self.assertEqual([m for m in sh.logs if m.startswith("lobby cursor -1 ->")],
                         ["lobby cursor -1 -> down", "lobby cursor -1 -> up",
                          "lobby cursor -1 -> down", "lobby cursor -1 -> up"])
        self.assertTrue(any("ready row lit" in m for m in sh.logs), sh.logs)
        self.assertFalse(any("LOBBY-FAIL" in m for m in sh.logs))

    def test_b2_cursor_appears_during_the_search(self):
        sh, _ = run_ready(LOBBY_NO_CURSOR, LOBBY_CURSOR_READY, LOBBY_NOT_READY)
        self.assertEqual(sh.presses, [DOWN, CROSS])

    def test_b3_cursor_appears_on_the_read_after_the_last_press(self):
        sh, _ = run_ready(*[LOBBY_NO_CURSOR] * 4, LOBBY_CURSOR_READY, LOBBY_NOT_READY)
        self.assertEqual(sh.presses, WIGGLE + [CROSS])

    def test_c_title_gone_after_the_first_down_stops_everything(self):
        for gone in (LOBBY_GONE, BLACK):
            sh, _ = run_ready(LOBBY_NO_CURSOR, gone)
            self.assertEqual(sh.presses, [DOWN], gone is BLACK)
            self.assertIn(GONE_LINE, sh.logs)
            self.assertFalse([m for m in sh.logs if "READY check" in m])   # no CROSS, so no check
            self.assertFalse([m for m in sh.logs if "LOBBY-FAIL" in m])

    def test_c2_title_gone_at_the_first_read_presses_nothing(self):
        sh, _ = run_ready(LOBBY_GONE)
        self.assertEqual(sh.presses, [])
        self.assertIn(GONE_LINE, sh.logs)

    def test_c3_s6_ladder4_sequence_is_cut_at_the_first_in_game_frame(self):
        # B at 393 s: the cursor read -1, and every frame after the host's READY was the loading screen /
        # the match. The old code sent DOWN,UP x4 and CROSS to the match (research/30).
        sh, _ = run_ready(LOBBY_NO_CURSOR, BLACK, BLACK, BLACK, BLACK, BLACK, BLACK, BLACK, BLACK)
        self.assertEqual(sh.presses, [DOWN])
        self.assertNotIn(CROSS, sh.presses)

    def test_d_cursor_never_read_ready_row_dark_fails_with_a_class(self):
        sh, g = FakeShell(), Grabs(LOBBY_NO_CURSOR)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.ready(sh)
        self.assertEqual(cm.exception.cls, "ready:cursor-not-found")
        self.assertEqual(cm.exception.code, L.LOBBY_FAIL_EXIT)
        self.assertEqual(sh.presses, WIGGLE)                                   # never a CROSS
        self.assertTrue(any(m.startswith("RESULT LOBBY-FAIL ready:cursor-not-found") for m in sh.logs))
        self.assertIn("LOBBY class=ready:cursor-not-found", sh.logs)
        self.assertIn("row means", cm.exception.detail)                        # why: the luminances it read
        self.assertIn("lobby_fail_ready_cursor-not-found", sh.shots)


class ReadyCheckGone(unittest.TestCase):
    def test_both_labels_absent_after_the_cross_is_not_resent(self):
        # 8c: the match launched inside the 3 s wait -- [None, None] is "the lobby is gone", not "dropped"
        sh, _ = run_ready(LOBBY_CURSOR_READY, LOBBY_GONE)
        self.assertEqual(sh.presses, [CROSS])
        self.assertTrue(any(m.startswith("READY check: row-2 label right edges [None, None]") for m in sh.logs))
        self.assertIn("[lobby] game lobby gone during READY check -- no more presses", sh.logs)
        self.assertIn("19_ready", sh.shots)

    def test_lobby_gone_before_a_resend_sends_nothing_more(self):
        # both check frames still READY -> a re-send is due; its cursor search finds the lobby gone
        sh, _ = run_ready(LOBBY_CURSOR_READY, LOBBY_CURSOR_READY, LOBBY_CURSOR_READY, LOBBY_GONE)
        self.assertEqual(sh.presses, [CROSS])
        self.assertIn("LOBBY RESEND ready-dropped attempt=1", sh.logs)
        self.assertIn(GONE_LINE, sh.logs)
        self.assertNotIn(PAD_CROSS, sh.presses)

    def test_resend_still_goes_through_the_pad_when_the_lobby_is_up(self):
        sh, _ = run_ready(LOBBY_CURSOR_READY, LOBBY_CURSOR_READY, LOBBY_CURSOR_READY,
                          LOBBY_CURSOR_READY, LOBBY_NOT_READY)
        self.assertEqual(sh.presses, [CROSS, PAD_CROSS])


class SwitchTeamsKeepsTheSameContract(unittest.TestCase):
    def test_switch_teams_cursor_never_on_the_row_fails_with_its_own_class(self):
        sh, g = FakeShell(), Grabs(LOBBY_CURSOR_READY, LOBBY_CURSOR_READY, LOBBY_NO_CURSOR)
        # row 1 is never lit in these frames: the search runs out and, with no lit_row, fails
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.lobby_select(sh, 1, "SWITCH TEAMS")
        self.assertEqual(cm.exception.cls, "switch-teams:cursor-not-found")
        self.assertEqual(len(sh.presses), L.LOBBY_CURSOR_PRESSES)

    def test_lobby_gone_returns_false(self):
        sh, g = FakeShell(), Grabs(LOBBY_GONE)
        with mock.patch.object(L.winshot, "grab", g):
            self.assertFalse(L.lobby_select(sh, 1, "SWITCH TEAMS"))
        self.assertEqual(sh.presses, [])
        self.assertIn("[lobby] game lobby gone during SWITCH TEAMS search -- no more presses", sh.logs)


if __name__ == "__main__":
    unittest.main()
