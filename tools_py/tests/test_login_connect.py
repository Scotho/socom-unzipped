"""Sprint 6, launch s6_ladder6 (2026-09-15, both instances at ~59 fps; research/28 §5-§6): the two blind press
runs left in login() lost one press each. A typed its password (read back 5 of 5), then the four DOWNs to CONNECT
lost one: the cursor sat on GENDER, CROSS opened "Specify your gender." and the stage timed out. B typed 5 of 5
and the walk to ENTER lost a step: "the on-screen keyboard is still up" was a WARNING, and the stage timed out.

Now `press_connect` reads the CONNECT button back after the four DOWNs (median of its fill: 68 lit on all 117
lit captures, 19-31 unlit), presses at most LOGIN_CONNECT_EXTRA_DOWNS more, presses CROSS only when it is lit,
and reads the form back after the CROSS (a still-up form with CONNECT lit is a dropped CROSS; with GENDER lit it
is the gender prompt: TRIANGLE and the search resumes). `Shell.osk_enter_verified` reads the keyboard back after
ENTER and re-presses (BCKSPC first when a stray key was typed), at most OSK_ENTER_RETRIES times.

Fixtures are crops of the s5_t5_ladder2 (lit) and s6_ladder6 (GENDER lit) captures, cut by
tools_py/tests/fixtures/lobby/make_login_fixtures.py and pasted into a black 640x448 frame at their box.
"""
import unittest
from unittest import mock

from PIL import Image

from tools_py.parity import online_login_ours as L
from tools_py.parity.online_login import osk_pos
from tools_py.tests import test_online_login_lobby as T
from tools_py.tests import test_osk_typing as O

frame, gray, Grabs = T.frame, T.gray, T.Grabs
CONNECT = (20, 366, 160, 390)
GENDER = (20, 226, 160, 246)
PROMPT = (150, 74, 490, 90)
OSK_ACCENT_BOX = T.OSK_ACCENT_BOX

# the CONNECT TO SOCOM II form with the cursor on CONNECT ("Connect." in the prompt band; s5_t5_ladder2 A_06)
FORM_CONNECT_LIT = frame(("row_connect_lit_lad2.png", CONNECT), ("row_gender_unlit_lad2.png", GENDER),
                         ("prompt_connect_lad2.png", PROMPT))
# the form with the cursor on GENDER ("Specify your gender."; s6_ladder6 A_06 = A_lobby_fail_timeout_login)
FORM_GENDER_LIT = frame(("row_connect_unlit_lad6.png", CONNECT), ("row_gender_lit_lad6.png", GENDER),
                        ("prompt_gender_lad6.png", PROMPT))
# the form with the cursor on PASSWORD ("Enter your password."; s5 A_05): neither row lit
FORM_PASSWORD = frame(("row_connect_unlit_lad6.png", CONNECT), ("row_gender_unlit_lad2.png", GENDER),
                      ("prompt_password_lad2.png", PROMPT))
AFTER_CONNECT = frame(("prompt_gone_lad2.png", PROMPT))            # s5 A_07: the write-down notice, band dark
EULA = frame(("prompt_eula_lad2.png", PROMPT))                     # s5 A_08: only the panel's edges in the band
KEYBOARD = frame(("osk_accent_key_cal1.png", OSK_ACCENT_BOX))      # an on-screen keyboard (normal mode)
BLACK = Image.new("RGB", (640, 448), 0)

KEY_DOWN, KEY_CROSS = ("key", "down"), ("key", "cross")
PAD_DOWN, PAD_CROSS, PAD_TRIANGLE = ("pad", "DOWN"), ("pad", "CROSS"), ("pad", "TRIANGLE")
FOUR_DOWNS = [KEY_DOWN] * 4


class Detectors(unittest.TestCase):
    def test_connect_row(self):
        self.assertTrue(L.lobby_row_lit(gray(FORM_CONNECT_LIT), "connect"))
        self.assertFalse(L.lobby_row_lit(gray(FORM_GENDER_LIT), "connect"))
        self.assertFalse(L.lobby_row_lit(gray(FORM_PASSWORD), "connect"))
        self.assertFalse(L.lobby_row_lit(gray(AFTER_CONNECT), "connect"))
        self.assertFalse(L.lobby_row_lit(gray(BLACK), "connect"))
        self.assertEqual(L.lobby_row_median(gray(FORM_CONNECT_LIT), "connect"), 68.0)
        self.assertEqual(L.lobby_row_median(gray(FORM_GENDER_LIT), "connect"), 19.0)
        self.assertEqual(L.LOBBY_ROWS["connect"], (366, 390, 20, 160))
        self.assertEqual(L.LOBBY_ROW_LIT_MEDIAN["connect"], 50.0)

    def test_gender_row(self):
        self.assertTrue(L.lobby_row_lit(gray(FORM_GENDER_LIT), "gender"))
        self.assertFalse(L.lobby_row_lit(gray(FORM_CONNECT_LIT), "gender"))
        self.assertFalse(L.lobby_row_lit(gray(FORM_PASSWORD), "gender"))
        self.assertEqual(L.lobby_row_median(gray(FORM_GENDER_LIT), "gender"), 68.0)
        self.assertEqual(L.lobby_row_median(gray(FORM_CONNECT_LIT), "gender"), 23.0)

    def test_form_prompt_band(self):
        for form in (FORM_CONNECT_LIT, FORM_GENDER_LIT, FORM_PASSWORD):
            self.assertTrue(L.login_form_up(gray(form)))
        for other in (AFTER_CONNECT, EULA, KEYBOARD, BLACK):
            self.assertFalse(L.login_form_up(gray(other)))
        self.assertGreaterEqual(L.login_form_prompt_cols(gray(FORM_CONNECT_LIT)), 50)     # "Connect.": 52 columns
        self.assertGreaterEqual(L.login_form_prompt_cols(gray(FORM_GENDER_LIT)), 95)      # "Specify your gender.": 99
        self.assertEqual(L.login_form_prompt_cols(gray(AFTER_CONNECT)), 0)
        self.assertLess(L.login_form_prompt_cols(gray(EULA)), 10)       # the panel's edge: 7 columns
        self.assertEqual(L.LOGIN_FORM_PROMPT_MIN_COLS, 40)

    def test_bounds_and_classes(self):
        self.assertEqual((L.LOGIN_CONNECT_DOWNS, L.LOGIN_CONNECT_EXTRA_DOWNS, L.LOGIN_GENDER_BACKS), (4, 3, 2))
        self.assertEqual(L.CLASS_CONNECT_FOCUS, "login:connect-focus")
        self.assertEqual(L.CLASS_CONNECT_PRESS, "login:connect-press")
        self.assertEqual(L.CLASS_OSK_ENTER, "login:keyboard-enter")
        self.assertEqual(L.OSK_ENTER_RETRIES, 2)


def run_connect(*frames):
    sh, g = T.FakeShell(), Grabs(*frames)
    with mock.patch.object(L.winshot, "grab", g):
        L.press_connect(sh)
    return sh, g


def focus_lines(sh):
    return [m for m in sh.logs if m.startswith("[login] connect focus:")]


class ConnectFocus(unittest.TestCase):
    def test_a_lit_after_four_downs_one_cross(self):
        sh, g = run_connect(FORM_CONNECT_LIT, AFTER_CONNECT)
        self.assertEqual(sh.presses, FOUR_DOWNS + [KEY_CROSS])
        self.assertEqual(focus_lines(sh), ["[login] connect focus: lit (median 68) attempt 1"])
        self.assertEqual(sh.shots, ["06_connect_focus", "07_after_connect"])
        self.assertFalse([m for m in sh.logs if "LOBBY-FAIL" in m])
        self.assertTrue(all(a is not None and a <= L.LOBBY_FRAME_MAX_AGE_S for a in g.ages), g.ages)

    def test_b_one_down_dropped_fifth_down_then_cross(self):
        # s6_ladder6 A: the cursor on GENDER after the four DOWNs
        sh, _ = run_connect(FORM_GENDER_LIT, FORM_CONNECT_LIT, AFTER_CONNECT)
        self.assertEqual(sh.presses, FOUR_DOWNS + [PAD_DOWN, KEY_CROSS])
        self.assertEqual(focus_lines(sh), ["[login] connect focus: not lit (median 19) attempt 1",
                                           "[login] connect focus: lit (median 68) attempt 2"])

    def test_b2_two_dropped_downs(self):
        sh, _ = run_connect(FORM_PASSWORD, FORM_GENDER_LIT, FORM_CONNECT_LIT, AFTER_CONNECT)
        self.assertEqual(sh.presses, FOUR_DOWNS + [PAD_DOWN, PAD_DOWN, KEY_CROSS])
        self.assertEqual(len(focus_lines(sh)), 3)

    def test_b3_extra_downs_are_posted_keys_without_a_pad(self):
        sh, g = T.FakeShell(pad_file=None), Grabs(FORM_GENDER_LIT, FORM_CONNECT_LIT, AFTER_CONNECT)
        with mock.patch.object(L.winshot, "grab", g):
            L.press_connect(sh)
        self.assertEqual(sh.presses, FOUR_DOWNS + [KEY_DOWN, KEY_CROSS])

    def test_c_never_lit_fails_with_a_class_and_no_cross(self):
        sh, g = T.FakeShell(), Grabs(FORM_GENDER_LIT)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.press_connect(sh)
        self.assertEqual(cm.exception.cls, "login:connect-focus")
        self.assertEqual(sh.presses, FOUR_DOWNS + [PAD_DOWN] * 3)
        self.assertNotIn(KEY_CROSS, sh.presses)
        self.assertNotIn(PAD_CROSS, sh.presses)
        self.assertEqual(len(focus_lines(sh)), 4)
        self.assertIn("LOBBY class=login:connect-focus", sh.logs)
        self.assertIn("3 more", cm.exception.detail)
        self.assertEqual(sh.shots, ["lobby_fail_login_connect-focus"])

    def test_c2_form_not_on_screen_presses_nothing_more(self):
        # the read after the DOWNs shows neither the form nor CONNECT: nothing to search (a keyboard, a black frame)
        for other in (KEYBOARD, BLACK):
            sh, g = T.FakeShell(), Grabs(other)
            with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
                L.press_connect(sh)
            self.assertEqual(cm.exception.cls, "login:connect-focus")
            self.assertEqual(sh.presses, FOUR_DOWNS, other is BLACK)
            self.assertIn("not on screen", cm.exception.detail)

    def test_d_gender_prompt_after_the_cross_is_backed_out_and_the_search_resumes(self):
        # frames: after the 4 DOWNs (lit), after CROSS (the gender prompt), after TRIANGLE (form, cursor on
        # GENDER), after the DOWN (lit), after the second CROSS (gone)
        sh, _ = run_connect(FORM_CONNECT_LIT, FORM_GENDER_LIT, FORM_GENDER_LIT, FORM_CONNECT_LIT, AFTER_CONNECT)
        self.assertEqual(sh.presses, FOUR_DOWNS + [KEY_CROSS, PAD_TRIANGLE, PAD_DOWN, PAD_CROSS])
        self.assertTrue(any(m.startswith("[login] connect press: form still up, GENDER lit") and "TRIANGLE" in m
                            for m in sh.logs), sh.logs)
        self.assertEqual(len(focus_lines(sh)), 3)
        self.assertEqual(sh.shots, ["06_connect_focus", "07_gender_prompt", "06_connect_focus", "07_after_connect"])

    def test_d2_gender_prompt_twice_fails(self):
        sh, g = T.FakeShell(), Grabs(FORM_CONNECT_LIT, FORM_GENDER_LIT, FORM_GENDER_LIT, FORM_CONNECT_LIT,
                                     FORM_GENDER_LIT, FORM_GENDER_LIT, FORM_CONNECT_LIT, FORM_GENDER_LIT)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.press_connect(sh)
        self.assertEqual(cm.exception.cls, "login:connect-focus")
        self.assertEqual(sh.presses.count(PAD_TRIANGLE), 2)
        self.assertEqual(sh.presses.count(PAD_CROSS) + sh.presses.count(KEY_CROSS), 3)

    def test_e_dropped_cross_on_a_lit_connect_is_resent(self):
        # after CROSS the form is still up with CONNECT still lit: the CROSS was dropped (127 of 127 launches that
        # connected had the form gone 5 s after the CROSS)
        sh, _ = run_connect(FORM_CONNECT_LIT, FORM_CONNECT_LIT, FORM_CONNECT_LIT, AFTER_CONNECT)
        self.assertEqual(sh.presses, FOUR_DOWNS + [KEY_CROSS, PAD_CROSS])
        self.assertTrue(any(m.startswith("[login] connect press: form still up, CONNECT lit -> re-send CROSS (attempt 1)")
                            for m in sh.logs), sh.logs)

    def test_e2_cross_never_registers_fails_as_connect_press(self):
        sh, g = T.FakeShell(), Grabs(FORM_CONNECT_LIT)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.press_connect(sh)
        self.assertEqual(cm.exception.cls, "login:connect-press")
        self.assertEqual(sh.presses, FOUR_DOWNS + [KEY_CROSS] + [PAD_CROSS] * L.LOBBY_RESEND_MAX)

    def test_f_a_keyboard_after_the_cross_is_backed_out(self):
        # the CROSS landed on a text row (a keyboard opened): TRIANGLE closes it and the search resumes
        sh, _ = run_connect(FORM_CONNECT_LIT, KEYBOARD, FORM_PASSWORD, FORM_GENDER_LIT, FORM_CONNECT_LIT, AFTER_CONNECT)
        self.assertEqual(sh.presses, FOUR_DOWNS + [KEY_CROSS, PAD_TRIANGLE, PAD_DOWN, PAD_DOWN, PAD_CROSS])


# ---------------------------------------------------------------------------
# The ENTER that closes the keyboard
# ---------------------------------------------------------------------------
def typed_open(n):
    """A keyboard frame (normal mode) with n characters in the text row."""
    im = O.synth_typed(n)
    im.paste(Image.open(O.REF_NORMAL).convert("RGB"), OSK_ACCENT_BOX[:2])
    return im


def run_enter(text, *frames):
    sh, g = O.FakeShell(), Grabs(*frames)
    with mock.patch.object(L.winshot, "grab", g), mock.patch.object(L.time, "sleep"):
        sh.osk_type_pad_verified(text)
    return sh, g


def enter_lines(sh):
    return [m for m in sh.logs if m.startswith("[osk] enter:")]


TYPED = O.expected(*"socom", "ENTER")
ENTER = osk_pos("ENTER")


class EnterVerified(unittest.TestCase):
    def test_e_keyboard_gone_after_enter_one_cross(self):
        # frames: the count read (5 typed, keyboard up), then the read after ENTER (gone)
        sh, g = run_enter("socom", typed_open(5), BLACK)
        self.assertEqual(sh.presses, TYPED)
        self.assertEqual(enter_lines(sh), ["[osk] enter: keyboard closed"])
        self.assertTrue(all(a is not None and a <= L.LOBBY_FRAME_MAX_AGE_S for a in g.ages), g.ages)

    def test_f_still_up_once_then_gone_second_cross(self):
        # B on s6_ladder6: the count read 5 of 5, the keyboard stayed up after the walk to ENTER
        sh, _ = run_enter("socom", typed_open(5), typed_open(5), BLACK)
        repress, _ = O.walk(ENTER, "ENTER")                        # from the dead-reckoned cursor: no moves, CROSS
        self.assertEqual(sh.presses, TYPED + repress)
        self.assertEqual(sh.presses.count(PAD_CROSS), 7)
        self.assertEqual(enter_lines(sh), ["[osk] enter: keyboard still up -> re-press (attempt 1)",
                                           "[osk] enter: keyboard closed after 1 re-press"])
        # the re-press runs at the slow pacing
        self.assertEqual(sh.paced[-1], ("CROSS", L.OSK_SLOW_HOLD_S, L.OSK_CROSS_WAIT_S))

    def test_g_stray_character_is_backspaced_before_the_re_press(self):
        # a dropped RIGHT left the cursor on the key beside ENTER and the CROSS typed it: 6 of 5
        sh, _ = run_enter("socom", typed_open(5), typed_open(6), BLACK)
        back, cur = O.walk(ENTER, "BCKSPC")
        enter, _ = O.walk(cur, "ENTER")
        self.assertEqual(sh.presses, TYPED + back + enter)
        self.assertEqual(enter_lines(sh), ["[osk] enter: keyboard still up, 6 of 5 characters -> BCKSPC, re-press (attempt 1)",
                                           "[osk] enter: keyboard closed after 1 re-press"])

    def test_g2_stray_then_still_up_then_gone(self):
        sh, _ = run_enter("socom", typed_open(5), typed_open(6), typed_open(5), BLACK)
        back, cur = O.walk(ENTER, "BCKSPC")
        enter, cur = O.walk(cur, "ENTER")
        again, _ = O.walk(cur, "ENTER")
        self.assertEqual(sh.presses, TYPED + back + enter + again)
        self.assertEqual(enter_lines(sh)[-1], "[osk] enter: keyboard closed after 2 re-presses")

    def test_h_still_up_after_the_retries_fails_with_a_class(self):
        sh = O.FakeShell()
        with mock.patch.object(L.winshot, "grab", Grabs(typed_open(5))), mock.patch.object(L.time, "sleep"), \
                self.assertRaises(L.LobbyFail) as cm:
            sh.osk_type_pad_verified("socom")
        self.assertEqual(cm.exception.cls, "login:keyboard-enter")
        self.assertEqual(cm.exception.detail, "keyboard still up after ENTER and 2 re-presses (5 of 5 characters)")
        self.assertEqual(sh.presses.count(PAD_CROSS), 6 + 2)
        self.assertEqual(enter_lines(sh), ["[osk] enter: keyboard still up -> re-press (attempt 1)",
                                           "[osk] enter: keyboard still up -> re-press (attempt 2)"])
        self.assertIn("LOBBY class=login:keyboard-enter", sh.logs)
        self.assertEqual(sh.shots, ["lobby_fail_login_keyboard-enter"])

    def test_type_pad_path_has_no_warning(self):
        sh = O.FakeShell()
        sh.osk_open = lambda: True
        with mock.patch.object(L.winshot, "grab", Grabs(KEYBOARD, typed_open(5), BLACK)), mock.patch.object(L.time, "sleep"):
            sh.type("socom")
        self.assertEqual(sh.presses, TYPED)
        self.assertFalse([m for m in sh.logs if m.startswith("WARNING")], sh.logs)
        self.assertIn("[osk] enter: keyboard closed", sh.logs)


if __name__ == "__main__":
    unittest.main()
