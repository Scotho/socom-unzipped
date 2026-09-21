"""Sprint 8: the first login on a server that has no saved persona (the project's hosted Horizon,
3.143.65.100, 2026-09-19 launch s8_hosted_control).

The game keeps personas per server. Against the LAN box the CONNECT TO SOCOM II form arrives with
PLAYER NAME prefilled from the memory card and the cursor on PASSWORD; against a fresh server PLAYER
NAME is empty and lit and the header reads "Choose a different persona or create a new one.". The
harness assumed the first CROSS always opened the password keyboard, so it typed the password into
the name ("socom" in A_05_password.png), left the password blank, and CONNECT stayed unlit
(login:connect-focus; B timed out).

Two pure detectors over a 640x448 grey frame tell the two forms apart:

  `login_name_glyphs` counts the glyph runs of the PLAYER NAME value strip with the same run counter
  the keyboard's text row uses -- 6 for "socomc" (the LAN card's persona), 5 for the "socom" the old
  path mistyped, 0 for the empty field of a fresh server;
  `login_focus_row` names the single lit row of the form (the CONNECT button's lit-fill detector,
  generalised over the six rows) -- "password" on the LAN form, "player_name" on the fresh one.

`osk_title_edge` reads the keyboard panel's title back: "Enter Player Name" ends at column 163,
"Enter Player Password" at 195.

Fixtures are crops of the two reference captures, cut by
tools_py/tests/fixtures/lobby/make_first_login_fixtures.py and pasted into a black 640x448 frame at
their box (12 KB in all).
"""
import unittest
from unittest import mock

from PIL import Image

from tools_py.parity import online_login_ours as L
from tools_py.tests import test_online_login_lobby as T

frame, gray, Grabs = T.frame, T.gray, T.Grabs

ROW_PLAYER_NAME = (20, 106, 160, 128)
ROW_PASSWORD = (20, 136, 160, 158)
NAME_VALUE = (172, 106, 400, 128)
OSK_TITLE = (24, 202, 400, 222)
OSK_PANEL = (20, 200, 475, 432)
PROMPT = (150, 74, 490, 90)

# the LAN form: PLAYER NAME prefilled ("socomc"), cursor on PASSWORD
FORM_SAVED = frame(("osk_panel_form_lad7.png", OSK_PANEL), ("prompt_password_lad2.png", PROMPT),
                   ("row_player_name_unlit_s8lan.png", ROW_PLAYER_NAME),
                   ("row_password_lit_s8lan.png", ROW_PASSWORD),
                   ("name_value_socomc_s8lan.png", NAME_VALUE))
# the hosted form on a first login: PLAYER NAME empty and lit, PASSWORD unlit (and greyed out)
FORM_FRESH = frame(("osk_panel_form_lad7.png", OSK_PANEL), ("prompt_password_lad2.png", PROMPT),
                   ("row_player_name_lit_s8host.png", ROW_PLAYER_NAME),
                   ("row_password_unlit_s8host.png", ROW_PASSWORD),
                   ("name_value_empty_s8host.png", NAME_VALUE))
# the same form once a 5-glyph name is in it, PLAYER NAME still lit (s8_hosted_control A_05_password)
FORM_NAME_TYPED = frame(("osk_panel_form_lad7.png", OSK_PANEL), ("prompt_password_lad2.png", PROMPT),
                        ("row_player_name_lit_s8host.png", ROW_PLAYER_NAME),
                        ("row_password_unlit_s8host.png", ROW_PASSWORD),
                        ("name_value_socom_s8host.png", NAME_VALUE))
# after the DOWN: the name still there, the cursor on PASSWORD
FORM_PASSWORD_LIT = frame(("osk_panel_form_lad7.png", OSK_PANEL), ("prompt_password_lad2.png", PROMPT),
                          ("row_player_name_unlit_s8lan.png", ROW_PLAYER_NAME),
                          ("row_password_lit_s8lan.png", ROW_PASSWORD),
                          ("name_value_socom_s8host.png", NAME_VALUE))
# the two keyboards (the lad7 panel carries the accent key osk_open_of reads; the title is pasted over it)
KBD_NAME = frame(("osk_panel_kbd_lad7.png", OSK_PANEL), ("osk_title_name_s8host.png", OSK_TITLE))
KBD_PASSWORD = frame(("osk_panel_kbd_lad7.png", OSK_PANEL), ("osk_title_password_s8lan.png", OSK_TITLE))
BLACK = Image.new("RGB", (640, 448), 0)

KEY_CROSS, KEY_DOWN = ("key", "cross"), ("key", "down")
PAD_CROSS, PAD_DOWN = ("pad", "CROSS"), ("pad", "DOWN")


class NameStrip(unittest.TestCase):
    def test_glyph_runs_count_the_saved_persona(self):
        self.assertEqual(L.login_name_glyphs(gray(FORM_SAVED)), 6)        # "socomc"
        self.assertEqual(L.login_name_glyphs(gray(FORM_NAME_TYPED)), 5)   # "socom"
        self.assertEqual(L.login_name_glyphs(gray(FORM_FRESH)), 0)
        self.assertEqual(L.login_name_glyphs(gray(BLACK)), 0)

    def test_empty_is_the_first_login(self):
        self.assertTrue(L.login_name_empty(gray(FORM_FRESH)))
        self.assertFalse(L.login_name_empty(gray(FORM_SAVED)))
        self.assertFalse(L.login_name_empty(gray(FORM_NAME_TYPED)))

    def test_strip_is_right_of_the_labels_and_left_of_the_photo(self):
        y0, y1, x0, x1 = L.LOGIN_NAME_VALUE
        self.assertEqual((y0, y1), L.LOBBY_ROWS["player_name"][:2])
        self.assertGreater(x0, L.LOBBY_ROWS["player_name"][3])            # clear of the row label
        self.assertEqual((x0, x1), (172, 400))

    def test_the_counter_is_the_keyboard_text_rows_counter(self):
        # same run rule, another band: the OSK text row still reads its own fixtures
        self.assertEqual(L.osk_typed_count(gray(frame(("osk_text_socomc_login.png", (0, 220, 640, 256))))), 6)


class FocusRow(unittest.TestCase):
    def test_lit_row_of_each_form(self):
        self.assertEqual(L.login_focus_row(gray(FORM_SAVED)), "password")
        self.assertEqual(L.login_focus_row(gray(FORM_FRESH)), "player_name")
        self.assertEqual(L.login_focus_row(gray(FORM_NAME_TYPED)), "player_name")
        self.assertEqual(L.login_focus_row(gray(FORM_PASSWORD_LIT)), "password")
        self.assertIsNone(L.login_focus_row(gray(BLACK)))

    def test_rows_are_the_forms_six_rows_thirty_pixels_apart(self):
        self.assertEqual(L.LOGIN_ROW_ORDER,
                         ("player_name", "password", "save_password", "hometown", "gender", "connect"))
        for row in L.LOGIN_ROW_ORDER:
            self.assertEqual(L.LOBBY_ROW_LIT_MEDIAN[row], 50.0)
        tops = [L.LOBBY_ROWS[r][0] for r in L.LOGIN_ROW_ORDER]
        self.assertEqual(tops, [106, 136, 166, 196, 226, 366])

    def test_row_medians_separate_lit_from_unlit(self):
        self.assertEqual(L.lobby_row_median(gray(FORM_FRESH), "player_name"), 68.0)
        self.assertEqual(L.lobby_row_median(gray(FORM_SAVED), "player_name"), 23.0)
        self.assertEqual(L.lobby_row_median(gray(FORM_SAVED), "password"), 68.0)
        self.assertEqual(L.lobby_row_median(gray(FORM_FRESH), "password"), 24.0)

    def test_the_mode_call_names_the_path(self):
        self.assertEqual(L.login_persona_mode(gray(FORM_FRESH)), "create")
        self.assertEqual(L.login_persona_mode(gray(FORM_SAVED)), "saved")
        self.assertIsNone(L.login_persona_mode(gray(BLACK)))       # no form on screen: caller keeps its hint


class OskTitle(unittest.TestCase):
    def test_which_keyboard_opened(self):
        self.assertEqual(L.osk_title_edge(gray(KBD_NAME)), 163)
        self.assertEqual(L.osk_title_edge(gray(KBD_PASSWORD)), 195)
        self.assertTrue(L.osk_title_is_name(gray(KBD_NAME)))
        self.assertFalse(L.osk_title_is_name(gray(KBD_PASSWORD)))
        self.assertIsNone(L.osk_title_edge(gray(BLACK)))
        self.assertFalse(L.osk_title_is_name(gray(BLACK)))
        self.assertLess(L.OSK_TITLE_NAME_MAX_EDGE, 195)
        self.assertGreater(L.OSK_TITLE_NAME_MAX_EDGE, 163)

    def test_both_frames_read_as_an_open_keyboard(self):
        for f in (KBD_NAME, KBD_PASSWORD):
            self.assertTrue(L.osk_open_of(gray(f)))
        for f in (FORM_FRESH, FORM_SAVED):
            self.assertFalse(L.osk_open_of(gray(f)))


def run_create(*frames, name="socom"):
    sh, g = T.FakeShell(), Grabs(*frames)
    with mock.patch.object(L.winshot, "grab", g):
        L.create_persona(sh, name)
    return sh, g


CREATE_FRAMES = (FORM_FRESH, KBD_NAME, KBD_NAME, KBD_NAME, FORM_NAME_TYPED, FORM_PASSWORD_LIT, KBD_PASSWORD)


class CreatePersona(unittest.TestCase):
    def test_a_the_happy_path(self):
        sh, g = run_create(*CREATE_FRAMES)
        self.assertEqual(sh.presses, [KEY_CROSS, KEY_CROSS, ("type", "socom"), KEY_DOWN, KEY_CROSS])
        self.assertIn("[login] persona: keyboard title edge 163 -> Enter Player Name", sh.logs)
        self.assertIn("[login] persona: PLAYER NAME reads 5 glyphs, expected 5", sh.logs)
        self.assertIn("[lobby] login:persona:password-row press=down verified=True attempt=1", sh.logs)
        self.assertIn("[lobby] login:persona:password-keyboard press=cross verified=True attempt=1", sh.logs)
        self.assertEqual(sh.shots, ["03_name_kbd", "03_name", "04_pw_kbd"])
        self.assertFalse([m for m in sh.logs if "LOBBY-FAIL" in m])
        self.assertTrue(all(a is not None and a <= L.LOBBY_FRAME_MAX_AGE_S for a in g.ages), g.ages)

    def test_b_a_name_that_did_not_land_fails_with_a_class(self):
        # the ENTER committed nothing (or the wrong text): the run stops here, not 120 s later on CONNECT
        sh, g = T.FakeShell(), Grabs(FORM_FRESH, KBD_NAME, KBD_NAME, KBD_NAME, FORM_FRESH)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.create_persona(sh, "socom")
        self.assertEqual(cm.exception.cls, "login:persona:name-value")
        self.assertIn("0 glyphs", cm.exception.detail)
        self.assertIn("LOBBY class=login:persona:name-value", sh.logs)
        self.assertNotIn(KEY_DOWN, sh.presses)

    def test_c_the_down_to_password_is_re_sent_through_the_pad(self):
        sh, _ = run_create(FORM_FRESH, KBD_NAME, KBD_NAME, KBD_NAME, FORM_NAME_TYPED,
                           FORM_NAME_TYPED, FORM_PASSWORD_LIT, KBD_PASSWORD)
        self.assertEqual(sh.presses, [KEY_CROSS, KEY_CROSS, ("type", "socom"), KEY_DOWN, PAD_DOWN, KEY_CROSS])

    def test_d_password_row_never_lit_fails_without_a_cross(self):
        sh = T.FakeShell()
        g = Grabs(FORM_FRESH, KBD_NAME, KBD_NAME, KBD_NAME, FORM_NAME_TYPED)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.create_persona(sh, "socom")
        self.assertEqual(cm.exception.cls, "login:persona:password-row")
        self.assertEqual(sh.presses.count(KEY_CROSS), 2)          # the two persona CROSSes, none after

    def test_e_a_password_keyboard_title_is_only_a_log_line(self):
        # the title is a read-back, not a gate: a wrong edge must not stop a run that is otherwise fine
        sh, _ = run_create(FORM_FRESH, KBD_PASSWORD, KBD_PASSWORD, KBD_PASSWORD, FORM_NAME_TYPED,
                           FORM_PASSWORD_LIT, KBD_PASSWORD)
        self.assertIn("[login] persona: keyboard title edge 195 -> NOT Enter Player Name", sh.logs)
        self.assertEqual(sh.presses, [KEY_CROSS, KEY_CROSS, ("type", "socom"), KEY_DOWN, KEY_CROSS])


class PersonaFormMode(unittest.TestCase):
    """The path is read off the form; the persona-list CROSS is spent first when the form is not up yet."""

    def mode(self, *frames, existing=True):
        sh, g = T.FakeShell(), Grabs(*frames)
        with mock.patch.object(L.winshot, "grab", g), \
                mock.patch.object(L, "press_persona_list",
                                  mock.Mock(side_effect=lambda s: s.presses.append(("key", "cross")))):
            return sh, L.persona_form_mode(sh, existing)

    def test_a_the_form_is_up_and_decides_with_no_press(self):
        sh, out = self.mode(FORM_FRESH)
        self.assertEqual(out, ("create", False))
        self.assertEqual(sh.presses, [])
        self.assertIn("[login] persona: PLAYER NAME 0 glyphs, focus player_name -> create", sh.logs)
        sh, out = self.mode(FORM_SAVED)
        self.assertEqual(out, ("saved", False))
        self.assertIn("[login] persona: PLAYER NAME 6 glyphs, focus password -> saved", sh.logs)

    def test_b_a_lingering_universe_is_read_after_the_list_cross(self):
        # s8_lan_login_recheck: SELECT UNIVERSE was still up at 02_persona, 60 s after the CROSS that
        # should have left it -- the list CROSS is common to both paths, so it is spent here
        sh, out = self.mode(BLACK, FORM_FRESH)
        self.assertEqual(out, ("create", True))
        self.assertEqual(sh.presses, [KEY_CROSS])
        self.assertIn("[login] persona: the form is not on screen -> reading it after the persona-list CROSS",
                      sh.logs)
        sh, out = self.mode(BLACK, FORM_SAVED)
        self.assertEqual(out, ("saved", True))

    def test_c_a_keyboard_the_list_cross_opened_is_read_by_its_title(self):
        sh, out = self.mode(BLACK, KBD_NAME)
        self.assertEqual(out, ("create", True))
        self.assertIn("[login] persona: no form, keyboard title edge 163 -> create", sh.logs)
        sh, out = self.mode(BLACK, KBD_PASSWORD)
        self.assertEqual(out, ("saved", True))

    def test_d_nothing_readable_falls_back_to_the_flag(self):
        sh, out = self.mode(BLACK, BLACK, existing=True)
        self.assertEqual(out, ("saved", True))
        self.assertIn("[login] persona: form unread and no keyboard -> --existing=True", sh.logs)
        sh, out = self.mode(BLACK, BLACK, existing=False)
        self.assertEqual(out, ("create", True))


class LoginBranch(unittest.TestCase):
    """login() picks the path from what persona_form_mode read, not from --existing."""

    def setUp(self):
        self.calls = []

    def run_login(self, form, existing):
        sh, g = T.FakeShell(), Grabs(form)
        stub = mock.patch.multiple(
            L, create_persona=mock.Mock(side_effect=lambda s, n, li, pf=False: self.calls.append(("create", n, li, pf))),
            press_persona=mock.Mock(side_effect=lambda s, e, li: self.calls.append(("persona", e, li))),
            press_persona_list=mock.Mock(side_effect=lambda s: s.presses.append(("key", "cross"))),
            press_connect=mock.Mock(side_effect=lambda s: self.calls.append(("connect",))),
            login_prompts=mock.Mock(side_effect=lambda s: self.calls.append(("prompts",))),
            login_to_lobby=mock.Mock(side_effect=lambda s: self.calls.append(("lobby",))))
        with mock.patch.object(L.winshot, "grab", g), stub, \
                mock.patch.object(T.FakeShell, "press_until_gone", lambda *a, **k: True), \
                mock.patch.object(T.FakeShell, "wait_for", lambda *a, **k: True):
            L.login(sh, "socomc", "socom", existing)
        return sh

    def test_a_empty_name_takes_the_create_path_whatever_existing_says(self):
        for existing in (True, False):
            self.calls = []
            sh = self.run_login(FORM_FRESH, existing)
            self.assertEqual(self.calls[0], ("create", "socomc", False, False))   # False: not --prefilled (Goal 9)
            self.assertIn("[login] persona: none saved -> creating socomc", sh.logs)
            self.assertEqual(self.calls[1:], [("connect",), ("prompts",), ("lobby",)])

    def test_b_a_prefilled_name_takes_the_saved_path_whatever_existing_says(self):
        for existing in (True, False):
            self.calls = []
            sh = self.run_login(FORM_SAVED, existing)
            self.assertEqual(self.calls[0], ("persona", True, False))
            self.assertIn("[login] persona: prefilled -> the saved-persona path", sh.logs)
            self.assertEqual(sh.shots, ["01_universe", "02_persona", "03_name", "04_pw_kbd", "05_password"])
            self.assertEqual(sh.presses, [("type", "socom")])


if __name__ == "__main__":
    unittest.main()
