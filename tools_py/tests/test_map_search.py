"""Sprint 6, launch s6_ladder3: choose_map pressed DOWN through a frame with no readable highlight (mid-scroll at
35-55 fps, two instances on one host) and walked past FROSTFIRE to THE RUINS. The fix re-reads an unreadable
frame on fresh captures before pressing, and scores ALL six visible rows so a target seen at another row is
walked to, one press at a time, instead of overshot.

Frames are scripted from grayscale crops of real captures (tools_py/tests/fixtures/lobby/make_map_fixtures.py),
pasted into a black 640x448 frame at the MAP_ROW_* geometry.
"""
import os
import tempfile
import unittest
from unittest import mock

from PIL import Image

from tools_py.parity import online_login_ours as L
from tools_py.parity import winshot

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "lobby")
LIST_BOX = L.map_row_box(0)[:2]                   # the six-row region crops start at row 0's corner


def crop(name):
    return Image.open(os.path.join(FIX, name)).convert("L")


def frame_of_rows(**rows):
    """A black frame with fixture rows pasted at the given indices: frame_of_rows(r4="maprow_x.png")."""
    im = Image.new("L", (640, 448), 0)
    for key, name in rows.items():
        im.paste(crop(name), L.map_row_box(int(key[1:]))[:2])
    return im.convert("RGB")


def frame_of_list(name):
    im = Image.new("L", (640, 448), 0)
    im.paste(crop(name), LIST_BOX)
    return im.convert("RGB")


FF_LIT, FF_PALE = "maprow_frostfire_lit_lad2.png", "maprow_frostfire_pale_scan17.png"
OTHER_LIT, OTHER_PALE, EMPTY = "maprow_blizzard_lit_scan14.png", "maprow_requiem_pale_scan14.png", "maprow_empty_scan23.png"

PALE_ROWS = {f"r{i}": OTHER_PALE for i in range(6)}
NO_MATCH_CUR4 = frame_of_rows(**{**PALE_ROWS, "r4": OTHER_LIT})            # cursor at row 4, FROSTFIRE not visible
NO_HILITE = frame_of_rows(**PALE_ROWS)                                     # mid-scroll: no row in the highlight band
FF_LIT_AT4 = frame_of_rows(**{**PALE_ROWS, "r4": FF_LIT})                  # the accepting frame of Sprint 5
FF_AT2_CUR4 = frame_of_rows(**{**PALE_ROWS, "r2": FF_PALE, "r4": OTHER_LIT})
FF_AT2_CUR3 = frame_of_rows(**{**PALE_ROWS, "r2": FF_PALE, "r3": OTHER_LIT})
FF_LIT_AT2 = frame_of_rows(**{**PALE_ROWS, "r2": FF_LIT})
FF_AT5_CUR4 = frame_of_rows(**{**PALE_ROWS, "r5": FF_PALE, "r4": OTHER_LIT})
FF_AT1_CUR4 = frame_of_rows(**{**PALE_ROWS, "r1": FF_PALE, "r4": OTHER_LIT})
FF_AT3_CUR4 = frame_of_rows(**{**PALE_ROWS, "r3": FF_PALE, "r4": OTHER_LIT})
NOT_FOUND_LAD3 = frame_of_list("maplist_s6_lad3_not_found.png")
MEDLEY_LAD2 = frame_of_list("maplist_s5_lad2_medley.png")


class FakeShell(L.Shell):
    """A Shell without the reference images: records logs, presses, shots and sleeps."""

    def __init__(self, pad_file="pad.txt"):          # deliberately skips Shell.__init__
        self.hwnd, self.out, self.t0, self.tag, self.pad_file = 1, tempfile.gettempdir(), 0.0, "A_", pad_file
        self.logs, self.presses, self.shots, self.sleeps = [], [], [], []

    def stage_sleep(self, seconds):
        self.sleeps.append(seconds)
        self.check_stage()

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


DOWN, UP = ("pad", "down"), ("pad", "up")


def run(*frames):
    sh, g = FakeShell(), Grabs(*frames)
    with mock.patch.object(L.winshot, "grab", g), mock.patch.object(L, "press_map_cross_verified") as cross:
        row = L.choose_map(sh, "frostfire")
    return sh, g, row, cross


class Fixtures(unittest.TestCase):
    def test_row_luminance_classes(self):
        peak = lambda name: float(L.map_rows(frame_of_rows(r0=name))[0].max())
        self.assertTrue(L.MAP_HILITE_LO <= peak(FF_LIT) <= L.MAP_HILITE_HI)
        self.assertTrue(L.MAP_HILITE_LO <= peak(OTHER_LIT) <= L.MAP_HILITE_HI)
        self.assertGreater(peak(FF_PALE), L.MAP_HILITE_HI)
        self.assertGreater(peak(OTHER_PALE), L.MAP_HILITE_HI)
        self.assertLess(peak(EMPTY), L.MAP_HILITE_LO)

    def test_pale_frostfire_matches_the_reference_and_the_others_do_not(self):
        d = L.map_row_distances(frame_of_rows(r0=FF_LIT, r1=FF_PALE, r2=OTHER_LIT, r3=OTHER_PALE, r4=EMPTY), L.map_ref("frostfire"))
        self.assertLessEqual(d[0], L.MAP_MATCH_THRESH)
        self.assertLessEqual(d[1], L.MAP_MATCH_THRESH)
        for j in (2, 3, 4, 5):
            self.assertGreater(d[j], L.MAP_MATCH_THRESH, j)

    def test_scripted_frames_read_as_intended(self):
        self.assertEqual(L.map_cursor(None, NO_MATCH_CUR4), 4)
        self.assertEqual(L.map_cursor(None, NO_HILITE), -1)
        self.assertEqual(L.map_cursor(None, FF_LIT_AT4), 4)
        self.assertEqual(L.map_cursor(None, FF_AT2_CUR4), 4)
        self.assertEqual(L.map_cursor(None, FF_AT2_CUR3), 3)


class RealCaptures(unittest.TestCase):
    """The two captures the failure was diagnosed on."""

    def test_s6_ladder3_last_frame_cursor_4_no_frostfire(self):
        self.assertEqual(L.map_cursor(None, NOT_FOUND_LAD3), 4)
        d = L.map_row_distances(NOT_FOUND_LAD3, L.map_ref("frostfire"))
        self.assertTrue(all(x > L.MAP_MATCH_THRESH for x in d), d)

    def test_s5_ladder2_choose_games_cursor_0_medley(self):
        self.assertEqual(L.map_cursor(None, MEDLEY_LAD2), 0)
        d = L.map_row_distances(MEDLEY_LAD2, L.map_ref("medley"))
        self.assertLessEqual(d[0], L.MAP_MATCH_THRESH)
        self.assertTrue(all(x > L.MAP_MATCH_THRESH for x in d[1:]), d)
        self.assertTrue(all(x > L.MAP_MATCH_THRESH for x in L.map_row_distances(MEDLEY_LAD2, L.map_ref("frostfire"))))


class ChooseMap(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(L.MAP_REREADS, 4)
        self.assertEqual(L.MAP_REREAD_WAIT_S, 0.5)
        self.assertEqual(L.choose_map.lobby_stage, "map_select")

    # 2026-09-16, launch ours_control_crossroads: the target was seen at row 1 with the cursor pinned at row 4 (a
    # scrolled list moves the CONTENT under the cursor), one UP was pressed, the next read did not show the target
    # (a mid-scroll frame) and the walk fell back to DOWN -- the two presses cancelled and the target was never
    # reached in 30 presses. Once a target has been seen the walk keeps that direction through reads that do not
    # show it, for up to MAP_STICKY_PRESSES presses, before falling back to DOWN.
    def test_target_above_the_cursor_keeps_pressing_up_through_an_unreadable_read(self):
        sh, g, row, cross = run(FF_AT1_CUR4, NO_MATCH_CUR4, FF_AT2_CUR4, FF_AT3_CUR4, FF_LIT_AT4)
        self.assertEqual(row, 4)
        self.assertEqual(sh.presses, [UP, UP, UP, UP])
        self.assertIn("map 'frostfire' visible at row 1, cursor at 4 -> up", sh.logs)
        cross.assert_called_once()

    def test_sticky_direction_falls_back_to_down_after_its_budget(self):
        self.assertEqual(L.MAP_STICKY_PRESSES, 6)
        sh, g, row, cross = run(FF_AT1_CUR4, *([NO_MATCH_CUR4] * 7), FF_LIT_AT4)
        self.assertEqual(row, 4)
        self.assertEqual(sh.presses, [UP] * 7 + [DOWN])

    def test_a_highlighted_at_row_4_after_15_down(self):
        sh, g, row, cross = run(*([NO_MATCH_CUR4] * 15), FF_LIT_AT4)
        self.assertEqual(row, 4)
        self.assertEqual(sh.presses, [DOWN] * 15)
        self.assertEqual(sh.sleeps, [])
        self.assertIn("map 'frostfire' highlighted at row 4 after 15 DOWN (text-mask distance 0.005 <= 0.3) -- accepting", sh.logs)
        self.assertIn("map search 00: row 4 is not 'frostfire' (distance 0.694)", sh.logs)
        self.assertEqual(sh.shots, ["14b_map_frostfire"])
        cross.assert_called_once()
        self.assertTrue(all(a == L.LOBBY_FRAME_MAX_AGE_S for a in g.ages), g.ages)   # every read is a fresh frame

    def test_b_unreadable_frame_at_press_15_is_reread_not_pressed_through(self):
        sh, g, row, cross = run(*([NO_MATCH_CUR4] * 15), NO_HILITE, FF_LIT_AT4)
        self.assertEqual(row, 4)
        self.assertEqual(sh.presses, [DOWN] * 15)                 # the re-read absorbed the blank frame
        self.assertEqual(sh.sleeps, [L.MAP_REREAD_WAIT_S])
        self.assertIn("map search 15: no highlighted row (re-read 1)", sh.logs)
        self.assertIn("map 'frostfire' highlighted at row 4 after 15 DOWN (text-mask distance 0.005 <= 0.3) -- accepting", sh.logs)
        self.assertEqual(sum("no highlighted row" in m for m in sh.logs), 1)

    def test_b2_after_max_rereads_it_presses_on(self):
        sh, g, row, cross = run(*([NO_HILITE] * (L.MAP_REREADS + 1)), FF_LIT_AT4)
        self.assertEqual(row, 4)
        self.assertEqual(sh.presses, [DOWN])
        self.assertEqual(sh.sleeps, [L.MAP_REREAD_WAIT_S] * L.MAP_REREADS)
        for n in range(1, L.MAP_REREADS + 1):
            self.assertIn(f"map search 00: no highlighted row (re-read {n})", sh.logs)
        self.assertIn(f"map search 00: no highlighted row after {L.MAP_REREADS} re-reads -- pressing on", sh.logs)
        self.assertIn("map 'frostfire' highlighted at row 4 after 1 DOWN (text-mask distance 0.005 <= 0.3) -- accepting", sh.logs)

    def test_b3_a_stale_frame_is_waited_out(self):
        stale = winshot.StaleFrameError("latest.png", 9.6, L.LOBBY_FRAME_MAX_AGE_S)
        sh, g, row, cross = run(stale, FF_LIT_AT4)
        self.assertEqual(row, 4)
        self.assertEqual(sh.presses, [])
        self.assertEqual(sh.sleeps, [L.MAP_REREAD_WAIT_S])
        self.assertTrue(any("waiting for a fresh frame" in m for m in sh.logs), sh.logs)

    def test_c_visible_at_row_2_cursor_at_4_walks_up_twice(self):
        sh, g, row, cross = run(FF_AT2_CUR4, FF_AT2_CUR3, FF_LIT_AT2)
        self.assertEqual(row, 2)
        self.assertEqual(sh.presses, [UP, UP])
        self.assertIn("map 'frostfire' visible at row 2, cursor at 4 -> up", sh.logs)
        self.assertIn("map 'frostfire' visible at row 2, cursor at 3 -> up", sh.logs)
        self.assertIn("map 'frostfire' highlighted at row 2 after 0 DOWN (text-mask distance 0.005 <= 0.3) -- accepting", sh.logs)
        cross.assert_called_once()

    def test_c2_visible_below_the_cursor_walks_down_once(self):
        sh, g, row, cross = run(FF_AT5_CUR4, FF_LIT_AT4)
        self.assertEqual(row, 4)
        self.assertEqual(sh.presses, [DOWN])
        self.assertIn("map 'frostfire' visible at row 5, cursor at 4 -> down", sh.logs)

    def test_c3_a_pale_target_row_is_not_accepted_only_the_highlighted_one(self):
        # FROSTFIRE visible at row 2 forever with the cursor stuck at 4: never accepted, the walk ends in the fail
        sh = FakeShell()
        with mock.patch.object(L.winshot, "grab", Grabs(FF_AT2_CUR4)), mock.patch.object(L, "press_map_cross_verified") as cross, \
                self.assertRaises(L.LobbyFail) as cm:
            L.choose_map(sh, "frostfire")
        self.assertEqual(cm.exception.cls, L.CLASS_MAP_SEARCH)
        self.assertEqual(sh.presses, [UP] * 30)
        cross.assert_not_called()

    def test_d_never_visible_lobby_fail_after_30(self):
        sh = FakeShell()
        with mock.patch.object(L.winshot, "grab", Grabs(NOT_FOUND_LAD3)), mock.patch.object(L, "press_map_cross_verified") as cross, \
                self.assertRaises(L.LobbyFail) as cm:
            L.choose_map(sh, "frostfire")
        self.assertEqual(cm.exception.cls, L.CLASS_MAP_SEARCH)
        self.assertEqual(sh.presses, [DOWN] * 30)
        self.assertEqual(sh.shots, ["14_map_frostfire_NOT_FOUND", "lobby_fail_map-list-search"])
        self.assertIn("map search 30: row 4 is not 'frostfire' (distance 0.575)", sh.logs)
        self.assertTrue(any(m.startswith("RESULT LOBBY-FAIL map-list-search -- map 'frostfire' was never highlighted in 30 presses of DOWN")
                            for m in sh.logs), sh.logs)
        self.assertIn("LOBBY class=map-list-search", sh.logs)
        cross.assert_not_called()

    def test_missing_reference_aborts(self):
        with self.assertRaises(SystemExit):
            L.choose_map(FakeShell(), "no-such-map")


if __name__ == "__main__":
    unittest.main()
