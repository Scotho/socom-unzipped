"""Sprint 6, launch s6_ladder7 (2026-09-15, harness 31b399c): instance A reached the main menu, the harness pressed
DOWN then CROSS for ONLINE, and the LOGIN screen never came -- A_lobby_fail_pre-login.png shows the main menu with
ONLINE lit: the DOWN registered and the CROSS was dropped (wtb4's and 3b's timeout captures show the same picture).
Instance B passed the whole login with the day's earlier checks. Tonight's three failures each sat on a BLIND press
(one sent with no read-back of the screen it should produce); the drop rate of posted keyboard messages is about one
in twenty, because they reach raylib only when the game's window thread pumps, while the injected pad file is polled
by the guest every frame.

Now (1) `Shell.press` routes every pad button through the pad file when there is one; (2) `press_online` reads
ONLINE back after the DOWN (row medians of the three menu rows' text cores: lit 114-146, dim 15-43 on every capture)
and re-sends the CROSS while the menu still shows ONLINE lit and the login screen has not come; (3) `press_persona`
verifies the two persona CROSSes (the first by the frame changing, the second by the keyboard being open), each
re-sent through the pad at most LOBBY_RESEND_MAX times before login:persona:<stage>.

Fixtures are crops of the s6_ladder7 captures, cut by tools_py/tests/fixtures/lobby/make_login_path_fixtures.py and
pasted into a black 640x448 frame at their box. No capture shows the block-pointer exe's menu with NEW GAME lit
(every pre-login timeout capture has ONLINE lit), so that frame swaps the lit and dim row crops.
"""
import unittest
from unittest import mock

from PIL import Image

from tools_py.parity import online_login_ours as L
from tools_py.tests import test_online_login_lobby as T
from tools_py.tests import test_login_connect as C

frame, gray, Grabs = T.frame, T.gray, T.Grabs
ROW_NEW_GAME, ROW_ONLINE, ROW_LAN = (262, 278, 368, 296), (262, 312, 368, 332), (262, 348, 368, 364)
OSK_PANEL = (20, 200, 475, 432)

# the main menu after the DOWN: ONLINE lit, NEW GAME and LAN dim (s6_ladder7 A_lobby_fail_pre-login)
MENU_ONLINE_LIT = frame(("menu_row_new_game_dim_lad7.png", ROW_NEW_GAME), ("menu_row_online_lit_lad7.png", ROW_ONLINE),
                        ("menu_row_lan_dim_lad7.png", ROW_LAN))
# the menu before the DOWN (or after a dropped one): the lit crop at the top row, a dim one in ONLINE's place
MENU_NEW_GAME_LIT = frame(("menu_row_online_lit_lad7.png", ROW_NEW_GAME), ("menu_row_new_game_dim_lad7.png", ROW_ONLINE),
                          ("menu_row_lan_dim_lad7.png", ROW_LAN))
# a DOWN too many: LAN lit
MENU_LAN_LIT = frame(("menu_row_new_game_dim_lad7.png", ROW_NEW_GAME), ("menu_row_lan_dim_lad7.png", ROW_ONLINE),
                     ("menu_row_online_lit_lad7.png", ROW_LAN))
LOGIN_SCREEN = frame(("menu_row_online_login_screen_lad7.png", ROW_ONLINE))      # B_00_login at the same rows
BLACK = Image.new("RGB", (640, 448), 0)
WHITE = Image.new("RGB", (640, 448), 255)

# the persona stage: the CONNECT TO SOCOM II form (cursor on PASSWORD) and the password keyboard open over it
FORM_PANEL = frame(("osk_panel_form_lad7.png", OSK_PANEL))
KBD_PANEL = frame(("osk_panel_kbd_lad7.png", OSK_PANEL))
CHANGED_NO_KBD = C.FORM_GENDER_LIT                                # a different screen with no keyboard on it

KEY_DOWN, KEY_CROSS = ("key", "down"), ("key", "cross")
PAD_DOWN, PAD_CROSS = ("pad", "DOWN"), ("pad", "CROSS")


class MenuDetectors(unittest.TestCase):
    def test_online_lit(self):
        self.assertTrue(L.menu_online_lit(gray(MENU_ONLINE_LIT)))
        for other in (MENU_NEW_GAME_LIT, MENU_LAN_LIT, LOGIN_SCREEN, BLACK, WHITE):
            self.assertFalse(L.menu_online_lit(gray(other)))

    def test_row_medians(self):
        g = gray(MENU_ONLINE_LIT)
        self.assertEqual(L.menu_row_median(g, "online"), 141.0)
        self.assertEqual(L.menu_row_median(g, "new_game"), 35.5)
        self.assertEqual(L.menu_row_median(g, "lan"), 24.0)
        self.assertEqual(L.menu_row_median(gray(LOGIN_SCREEN), "online"), 36.0)
        self.assertEqual(L.menu_rows_detail(g), "row medians new game 36, online 141, lan 24")

    def test_boxes_and_bounds(self):
        self.assertEqual(L.MENU_ROWS, {"new_game": (278, 296, 262, 368), "online": (312, 332, 262, 368),
                                       "lan": (348, 364, 262, 368)})
        self.assertEqual(L.MENU_ROW_LIT_MEDIAN, 80.0)
        self.assertEqual((L.ONLINE_EXTRA_DOWNS, L.ONLINE_CROSS_RESENDS), (2, 3))
        self.assertEqual(L.LOGIN_SCREEN_WAIT_S, 40.0)
        self.assertEqual(L.ONLINE_CROSS_RESENDS, L.LOBBY_RESEND_MAX)


class PersonaDetectors(unittest.TestCase):
    def test_frame_diff(self):
        d = L.frame_diff(gray(FORM_PANEL), gray(KBD_PANEL))
        self.assertGreater(d, 9.0)                                 # 9.90: the panel's share of the real 16.5
        self.assertLess(d, 11.0)
        self.assertEqual(L.frame_diff(gray(FORM_PANEL), gray(FORM_PANEL)), 0.0)
        # a cursor moving one row (test_login_connect's forms) stays under the threshold, a keyboard clears it
        self.assertLess(L.frame_diff(gray(C.FORM_CONNECT_LIT), gray(C.FORM_GENDER_LIT)), L.PERSONA_CHANGED_MIN_DIFF)
        self.assertGreater(d, L.PERSONA_CHANGED_MIN_DIFF)
        self.assertEqual(L.PERSONA_CHANGED_MIN_DIFF, 4.0)
        self.assertEqual(L.PERSONA_CROSS_WAIT_S, 4.0)

    def test_keyboard_open(self):
        self.assertTrue(L.osk_open_of(gray(KBD_PANEL)))
        self.assertFalse(L.osk_open_of(gray(FORM_PANEL)))
        self.assertFalse(L.osk_open_of(gray(CHANGED_NO_KBD)))

    def test_classes(self):
        self.assertEqual(L.CLASS_PERSONA, "login:persona")


# ---------------------------------------------------------------------------
# Shell.press: the pad file when there is one
# ---------------------------------------------------------------------------
def real_shell(pad_file):
    sh = L.Shell.__new__(L.Shell)                                 # no reference images
    sh.hwnd, sh.pad_file, sh.stages = 1, pad_file, ()
    return sh


class PressRouting(unittest.TestCase):
    """Shell.press posts the KEY even when a pad file exists. s6_ladder10 (2026-09-16): three DOWN presses
    through the pad file left NEW GAME lit on the main menu (row medians new game 70, online 34, lan 28) --
    the shell menus do not read a 0.09 s pad-file press, while posted arrows moved that cursor in every
    earlier launch. Drops on the keyboard path (~1 in 20) are caught by the verified steps that re-send."""

    def test_pad_button_posts_the_key_even_with_a_pad_file(self):
        sh = real_shell("pad.txt")
        with mock.patch.object(L.keys, "press") as key, mock.patch.object(L, "write_pad_file") as pad, \
                mock.patch.object(L.time, "sleep") as sleep:
            sh.press("cross", 2.0)
        key.assert_called_once_with(1, "cross", L.T, hold_s=0.08)
        pad.assert_not_called()
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2.0])

    def test_lower_and_upper_case_names(self):
        for name in ("down", "DOWN", "Triangle"):
            sh = real_shell("pad.txt")
            with mock.patch.object(L.keys, "press") as key, mock.patch.object(L, "write_pad_file") as pad, \
                    mock.patch.object(L.time, "sleep"):
                sh.press(name)
            key.assert_called_once_with(1, name, L.T, hold_s=0.08)
            pad.assert_not_called()

    def test_no_pad_file_posts_the_key(self):
        sh = real_shell(None)
        with mock.patch.object(L.keys, "press") as key, mock.patch.object(L, "write_pad_file") as pad, \
                mock.patch.object(L.time, "sleep") as sleep:
            sh.press("cross", 2.0)
        key.assert_called_once_with(1, "cross", L.T, hold_s=0.08)
        pad.assert_not_called()
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2.0])

    def test_a_button_the_pad_lacks_posts_the_key(self):
        sh = real_shell("pad.txt")
        with mock.patch.object(L.keys, "press") as key, mock.patch.object(L, "write_pad_file") as pad, \
                mock.patch.object(L.time, "sleep"):
            sh.press("escape", 0.5)
        key.assert_called_once_with(1, "escape", L.T, hold_s=0.08)
        pad.assert_not_called()

    def test_every_harness_button_is_a_pad_button(self):
        import inspect
        import re
        names = set(re.findall(r'\.press\("([a-z_]+)"', inspect.getsource(L)))
        self.assertTrue(names)
        self.assertFalse({n for n in names if n.upper() not in L.PAD_BUTTON})


# ---------------------------------------------------------------------------
# press_online: DOWN read back, CROSS verified by the login screen
# ---------------------------------------------------------------------------
class ScriptedScreen:
    """Shell.screen_within stand-in: hands out the scripted results (the last repeats), records the calls."""

    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def __call__(self, name, timeout, thresh=None):
        self.calls.append((name, timeout))
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


def run_online(screens, *frames):
    sh, g = T.FakeShell(), Grabs(*frames)
    sh.screen_within = ScriptedScreen(*screens)
    with mock.patch.object(L.winshot, "grab", g):
        L.press_online(sh)
    return sh, g


def online_lines(sh):
    return [m for m in sh.logs if m.startswith("[login] online")]


class OnlineStep(unittest.TestCase):
    def test_a_lit_after_the_down_one_cross(self):
        sh, g = run_online([True], MENU_ONLINE_LIT)
        self.assertEqual(sh.presses, [KEY_DOWN, KEY_CROSS])
        self.assertEqual(online_lines(sh), ["[login] online: lit attempt 1",
                                            "[login] online cross: login screen after 1 press"])
        self.assertEqual(sh.screen_within.calls, [("login", L.LOGIN_SCREEN_WAIT_S)])
        self.assertFalse([m for m in sh.logs if "LOBBY" in m])
        self.assertTrue(all(a is not None and a <= L.LOBBY_FRAME_MAX_AGE_S for a in g.ages), g.ages)

    def test_b_dropped_down_is_re_sent_once(self):
        sh, _ = run_online([True], MENU_NEW_GAME_LIT, MENU_ONLINE_LIT)
        self.assertEqual(sh.presses, [KEY_DOWN, PAD_DOWN, KEY_CROSS])
        self.assertEqual(online_lines(sh)[:2], ["[login] online: not lit attempt 1", "[login] online: lit attempt 2"])

    def test_b2_online_never_lit_fails_pre_login_with_no_cross(self):
        sh, g = T.FakeShell(), Grabs(MENU_NEW_GAME_LIT)
        sh.screen_within = ScriptedScreen(True)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.press_online(sh)
        self.assertEqual(cm.exception.cls, "pre-login")
        self.assertEqual(sh.presses, [KEY_DOWN, PAD_DOWN, PAD_DOWN])
        self.assertEqual(len(online_lines(sh)), 3)
        self.assertIn("ONLINE not lit after 1 DOWN and 2 more", cm.exception.detail)
        self.assertIn("row medians new game 148, online 33, lan 24", cm.exception.detail)
        self.assertEqual(sh.screen_within.calls, [])
        self.assertIn("LOBBY class=pre-login", sh.logs)
        self.assertEqual(sh.shots, ["lobby_fail_pre-login"])

    def test_c_dropped_cross_is_re_sent_while_online_stays_lit(self):
        # s6_ladder7 A: the DOWN registered, the CROSS was dropped, the menu still showed ONLINE lit 40 s later
        sh, _ = run_online([False, True], MENU_ONLINE_LIT)
        self.assertEqual(sh.presses, [KEY_DOWN, KEY_CROSS, PAD_CROSS])
        self.assertEqual(online_lines(sh), ["[login] online: lit attempt 1",
                                            "[login] online cross: no login screen, the menu still shows ONLINE lit"
                                            " -> re-send CROSS (attempt 1)",
                                            "[login] online cross: login screen after 2 presses"])
        self.assertEqual(sh.screen_within.calls, [("login", L.LOGIN_SCREEN_WAIT_S)] * 2)

    def test_c2_cross_never_registers_fails_pre_login_after_three_re_sends(self):
        sh, g = T.FakeShell(), Grabs(MENU_ONLINE_LIT)
        sh.screen_within = ScriptedScreen(False)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.press_online(sh)
        self.assertEqual(cm.exception.cls, "pre-login")
        self.assertEqual(sh.presses, [KEY_DOWN, KEY_CROSS] + [PAD_CROSS] * 3)
        self.assertEqual(len(sh.screen_within.calls), 4)
        self.assertIn("3 re-sends", cm.exception.detail)
        self.assertIn("LOBBY class=pre-login", sh.logs)

    def test_c3_menu_gone_without_the_login_screen_is_not_re_sent(self):
        # the CROSS registered but the login screen never came (a hang, another screen): no blind re-send
        sh, g = T.FakeShell(), Grabs(MENU_ONLINE_LIT, BLACK)
        sh.screen_within = ScriptedScreen(False)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.press_online(sh)
        self.assertEqual(cm.exception.cls, "pre-login")
        self.assertEqual(sh.presses, [KEY_DOWN, KEY_CROSS])
        self.assertIn("no longer shows ONLINE lit", cm.exception.detail)

    def test_d_boot_to_online_reaches_the_login_shot(self):
        sh = T.FakeShell()
        sh.last = None
        sh.is_screen = lambda name, thresh=None: name == "main_menu"
        sh.screen_within = ScriptedScreen(True)
        with mock.patch.object(L.drive, "wait_stable"), mock.patch.object(L.drive, "frame", return_value=None), \
                mock.patch.object(L.time, "sleep"), mock.patch.object(L.winshot, "grab", Grabs(MENU_ONLINE_LIT)):
            L.boot_to_online(sh)
        self.assertEqual(sh.presses, [KEY_DOWN, KEY_CROSS])
        self.assertEqual(sh.shots, ["00_login"])

    def test_screen_within_is_the_wait_without_a_class(self):
        sh = T.FakeShell()
        now = [0.0]
        sh.clock = lambda: now[0]
        sh.is_screen = lambda name, thresh=None: False

        def tick(s):
            now[0] += s

        with mock.patch.object(L.time, "sleep", tick):
            self.assertFalse(sh.screen_within("login", 5))
        self.assertIn("TIMEOUT waiting for login", sh.logs)
        self.assertEqual(sh.shots, ["timeout_login"])
        self.assertFalse([m for m in sh.logs if "LOBBY" in m])
        sh.is_screen = lambda name, thresh=None: name == "login"
        with mock.patch.object(L.time, "sleep", tick):
            self.assertTrue(sh.screen_within("login", 5))
            self.assertTrue(sh.wait_for("login", 5))
        with mock.patch.object(L.time, "sleep", tick), self.assertRaises(L.LobbyFail) as cm:
            sh.wait_for("eula", 5, cls="pre-login")
        self.assertEqual(cm.exception.cls, "pre-login")


# ---------------------------------------------------------------------------
# press_persona: the two CROSSes after the universe
# ---------------------------------------------------------------------------
def run_persona(existing, *frames):
    sh, g = T.FakeShell(), Grabs(*frames)
    with mock.patch.object(L.winshot, "grab", g):
        L.press_persona(sh, existing)
    return sh, g


def persona_lines(sh):
    return [m for m in sh.logs if m.startswith("[lobby] login:persona")]


class PersonaPresses(unittest.TestCase):
    def test_a_saved_persona_two_presses(self):
        # frames: before the first CROSS (the form), after it (the keyboard), after the second (the keyboard)
        sh, g = run_persona(True, FORM_PANEL, KBD_PANEL, KBD_PANEL)
        self.assertEqual(sh.presses, [KEY_CROSS, KEY_CROSS])
        self.assertEqual(persona_lines(sh), ["[lobby] login:persona:list press=cross verified=True attempt=1",
                                             "[lobby] login:persona:password-keyboard press=cross verified=True attempt=1"])
        self.assertTrue(any(m.startswith("[login] persona list: frame diff 9.9") for m in sh.logs), sh.logs)
        self.assertFalse([m for m in sh.logs if "LOBBY" in m])
        self.assertTrue(all(a is not None and a <= L.LOBBY_FRAME_MAX_AGE_S for a in g.ages), g.ages)

    def test_a2_new_persona_two_presses(self):
        sh, _ = run_persona(False, FORM_PANEL, KBD_PANEL, KBD_PANEL)
        self.assertEqual(sh.presses, [KEY_CROSS, KEY_CROSS])
        self.assertEqual(persona_lines(sh)[1], "[lobby] login:persona:name-keyboard press=cross verified=True attempt=1")

    def test_b_dropped_list_press_is_re_sent_once(self):
        sh, _ = run_persona(True, FORM_PANEL, FORM_PANEL, KBD_PANEL, KBD_PANEL)
        self.assertEqual(sh.presses, [KEY_CROSS, PAD_CROSS, KEY_CROSS])
        self.assertEqual(persona_lines(sh)[:2], ["[lobby] login:persona:list press=cross verified=False attempt=1",
                                                 "[lobby] login:persona:list press=cross verified=True attempt=2"])
        self.assertIn("LOBBY RESEND login:persona:list attempt=1", sh.logs)

    def test_b2_list_press_never_registers(self):
        sh, g = T.FakeShell(), Grabs(FORM_PANEL)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.press_persona(sh, True)
        self.assertEqual(cm.exception.cls, "login:persona:list")
        self.assertEqual(sh.presses, [KEY_CROSS] + [PAD_CROSS] * L.LOBBY_RESEND_MAX)
        self.assertEqual(cm.exception.detail, "a changed screen never showed after CROSS and 3 re-sends -- see the capture")
        self.assertIn("LOBBY class=login:persona:list", sh.logs)
        self.assertEqual(sh.shots, ["lobby_fail_login_persona_list"])

    def test_c_dropped_keyboard_press_is_re_sent_once(self):
        # the first CROSS changed the screen without a keyboard; the second was dropped, its re-send opened one
        sh, _ = run_persona(True, FORM_PANEL, CHANGED_NO_KBD, CHANGED_NO_KBD, KBD_PANEL)
        self.assertEqual(sh.presses, [KEY_CROSS, KEY_CROSS, PAD_CROSS])
        self.assertEqual(persona_lines(sh)[1:], ["[lobby] login:persona:password-keyboard press=cross verified=False attempt=1",
                                                 "[lobby] login:persona:password-keyboard press=cross verified=True attempt=2"])

    def test_c2_keyboard_never_opens(self):
        for existing, cls in ((True, "login:persona:password-keyboard"), (False, "login:persona:name-keyboard")):
            sh, g = T.FakeShell(), Grabs(FORM_PANEL, CHANGED_NO_KBD)
            with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
                L.press_persona(sh, existing)
            self.assertEqual(cm.exception.cls, cls)
            self.assertEqual(sh.presses, [KEY_CROSS, KEY_CROSS] + [PAD_CROSS] * L.LOBBY_RESEND_MAX)
            self.assertIn("keyboard never showed", cm.exception.detail)


class LoginFlow(unittest.TestCase):
    def test_login_verifies_the_persona_presses(self):
        # the saved-persona login has no fixed press left before CONNECT: press_until_gone (screens), press_persona,
        # press_connect (the new-persona branch's DOWN and CROSS to the password field, and the prompt loop's
        # CROSSes after CONNECT, are still fixed presses)
        sh = T.FakeShell()
        sh.press_until_gone = lambda *a, **k: True
        sh.wait_for = lambda *a, **k: True
        sh.is_screen = lambda name, thresh=None: name == "eula"
        with mock.patch.object(L, "press_persona") as persona, mock.patch.object(L, "press_connect") as connect, \
                mock.patch.object(L.time, "sleep"):
            L.login(sh, "socomc", "socom", True)
        persona.assert_called_once_with(sh, True)
        connect.assert_called_once_with(sh)
        self.assertEqual(sh.presses, [("type", "socom")])
        self.assertEqual(sh.shots, ["01_universe", "02_persona", "03_name", "04_pw_kbd", "05_password", "08_eula",
                                    "09_lobby", "09_lobby_no_news"])


if __name__ == "__main__":
    unittest.main()
