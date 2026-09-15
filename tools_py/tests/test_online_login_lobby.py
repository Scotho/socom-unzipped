"""Sprint 6 Task 2 Steps 2-3 (research/28 §4): every fixed press of the CREATE GAME and JOIN GAME flows is
verified against the next expected screen and re-sent on fresh frames before it fails with a class that
names the press; `Shell.wait_for` timeouts and a window that never reaches the main menu carry a class too.

Fixtures are crops of real captures (tools_py/tests/fixtures/lobby/make_screen_fixtures.py), pasted back into a
black 640x448 frame at their box, as test_lobby_resend.py does. FakeShell records logs, presses and shots.
"""
import os
import tempfile
import unittest
from unittest import mock

from PIL import Image

from tools_py.parity import online_login_ours as L

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "lobby")
TITLE = (20, 18, 360, 58)
ROW_CREATE_GAME = (18, 106, 135, 128)
ROW_CHOOSE_GAMES = (18, 386, 170, 406)
ROW_GAMES_LIST = (150, 262, 620, 280)
NOTICE = (150, 152, 490, 265)
OSK_ACCENT_BOX = (20, 396, 96, 428)


def frame(*parts):
    """A black 640x448 RGB frame with each (fixture, box) pasted at its box."""
    im = Image.new("L", (640, 448), 0)
    for name, box in parts:
        im.paste(Image.open(os.path.join(FIX, name)).convert("L"), box[:2])
    return im.convert("RGB")


def gray(im):
    return L.lobby_gray_of(im)


# screens, as the live frame would show them after each press
BRIEFING_JOIN_LIT = frame(("title_lad2_briefing_room.png", TITLE), ("row_create_game_unlit_lad2.png", ROW_CREATE_GAME))
BRIEFING_CREATE_LIT = frame(("title_wtb3_still_briefing.png", TITLE), ("row_create_game_lit_wtb3.png", ROW_CREATE_GAME))
CREATE_GAME = frame(("title_lad2_create_game.png", TITLE), ("row_choose_games_unlit_wtb3.png", ROW_CHOOSE_GAMES))
CREATE_GAME_KBD = frame(("title_lad2_create_game.png", TITLE), ("osk_accent_key_cal1.png", OSK_ACCENT_BOX))
CREATE_GAME_CHOOSE_LIT = frame(("title_lad2_create_game.png", TITLE), ("row_choose_games_lit_lad2.png", ROW_CHOOSE_GAMES))
PLAY_LIST = frame(("title_lad2_play_list.png", TITLE))
PLAY_LIST_KILL4 = frame(("title_kill4_still_play_list.png", TITLE))
CREATE_GAME_NO_LOBBY_KILL4 = frame(("title_kill4_no_lobby.png", TITLE))
GAME_LOBBY_NOTICE = frame(("title_lad2_game_lobby.png", TITLE), ("notice_up_8c.png", NOTICE))
GAME_LOBBY = frame(("title_lad2_game_lobby.png", TITLE), ("notice_gone_8c.png", NOTICE))
GAMES_LIST_ACTIVE = frame(("title_lad2_briefing_room.png", TITLE), ("row_games_list_lit_8c.png", ROW_GAMES_LIST))
GAMES_LIST_NONE = frame(("title_lad2_briefing_room.png", TITLE), ("row_games_list_none_wtb5.png", ROW_GAMES_LIST))
JOIN_NO_LOBBY_LAUNCH1 = frame(("title_launch1_join_no_lobby.png", TITLE), ("row_games_list_lit_8c.png", ROW_GAMES_LIST))


class FakeShell(L.Shell):
    """A Shell without the reference images: records logs, presses and shots (test_lobby_resend pattern)."""

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

    def type(self, text, shots=None, tag=""):
        self.presses.append(("type", text))


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


def press_lines(sh, stage):
    return [m for m in sh.logs if m.startswith(f"[lobby] {stage} ")]


class ScreenDetectors(unittest.TestCase):
    def test_title_matches_its_own_screen_across_launches(self):
        for name, im in (("briefing_room", BRIEFING_JOIN_LIT), ("create_game", CREATE_GAME),
                         ("play_list", PLAY_LIST), ("game_lobby", GAME_LOBBY)):
            self.assertTrue(L.lobby_title_is(gray(im), name), name)
            for other in L.LOBBY_TITLES:
                if other != name:
                    self.assertFalse(L.lobby_title_is(gray(im), other), (name, other))

    def test_title_distances_have_margin(self):
        self.assertLess(L.lobby_title_dist(gray(CREATE_GAME), "create_game"), 0.05)
        self.assertGreater(L.lobby_title_dist(gray(PLAY_LIST), "create_game"), 2 * L.LOBBY_TITLE_MAX_DIST)
        self.assertGreater(L.lobby_title_dist(gray(CREATE_GAME), "play_list"), 2 * L.LOBBY_TITLE_MAX_DIST)

    def test_failed_launch_screens_read_as_what_they_were(self):
        self.assertTrue(L.lobby_title_is(gray(BRIEFING_CREATE_LIT), "briefing_room"))      # wtb3: CROSS eaten
        self.assertFalse(L.lobby_title_is(gray(BRIEFING_CREATE_LIT), "create_game"))
        self.assertTrue(L.lobby_title_is(gray(PLAY_LIST_KILL4), "play_list"))               # kill4: SQUARE eaten
        self.assertFalse(L.lobby_title_is(gray(CREATE_GAME_NO_LOBBY_KILL4), "game_lobby"))  # kill4: no lobby
        self.assertFalse(L.lobby_title_is(gray(JOIN_NO_LOBBY_LAUNCH1), "game_lobby"))       # launch1: no lobby

    def test_row_lit(self):
        self.assertTrue(L.lobby_row_lit(gray(BRIEFING_CREATE_LIT), "create_game"))
        self.assertFalse(L.lobby_row_lit(gray(BRIEFING_JOIN_LIT), "create_game"))
        self.assertTrue(L.lobby_row_lit(gray(CREATE_GAME_CHOOSE_LIT), "choose_games"))
        self.assertFalse(L.lobby_row_lit(gray(CREATE_GAME), "choose_games"))
        self.assertTrue(L.lobby_row_lit(gray(GAMES_LIST_ACTIVE), "games_list"))
        self.assertFalse(L.lobby_row_lit(gray(GAMES_LIST_NONE), "games_list"))

    def test_notice(self):
        self.assertTrue(L.lobby_notice_up(gray(GAME_LOBBY_NOTICE)))
        self.assertFalse(L.lobby_notice_up(gray(GAME_LOBBY)))

    def test_osk_open_of_frame(self):
        self.assertTrue(L.osk_open_of(gray(CREATE_GAME_KBD)))
        self.assertFalse(L.osk_open_of(gray(CREATE_GAME)))


HOST_HAPPY = (BRIEFING_CREATE_LIT, CREATE_GAME, CREATE_GAME_KBD, CREATE_GAME_CHOOSE_LIT, PLAY_LIST,
              CREATE_GAME_CHOOSE_LIT, GAME_LOBBY_NOTICE, GAME_LOBBY)
HOST_PRESSES = [("key", "up"), ("key", "cross"), ("key", "cross"), ("type", "test"), ("key", "up"), ("key", "cross"),
                ("key", "square"), ("key", "square"), ("key", "cross")]
HOST_STAGES = ("create-game:select", "create-game:enter", "create-game:name-keyboard", "create-game:choose-games-select",
               "create-game:choose-games", "create-game:accept", "create-game:create", "create-game:continue")


def run_host(*frames, pad_file="pad.txt"):
    sh, g = FakeShell(pad_file=pad_file), Grabs(*frames)
    sh.is_screen = lambda name, thresh=None: name == "game_lobby"
    with mock.patch.object(L.winshot, "grab", g), mock.patch.object(L, "choose_map", return_value=0):
        L.host_game(sh)
    return sh, g


class HostGameVerified(unittest.TestCase):
    def test_happy_path_issues_the_same_presses_as_before(self):
        sh, g = run_host(*HOST_HAPPY)
        self.assertEqual(sh.presses, HOST_PRESSES)
        self.assertFalse([m for m in sh.logs if "LOBBY RESEND" in m])
        self.assertTrue(all(a is not None and a <= L.LOBBY_FRAME_MAX_AGE_S for a in g.ages), g.ages)
        for stage, btn in zip(HOST_STAGES, ("up", "cross", "cross", "up", "cross", "square", "square", "cross")):
            self.assertEqual(press_lines(sh, stage), [f"[lobby] {stage} press={btn} verified=True attempt=1"])
        self.assertIn("17_game_lobby_ok", sh.shots)

    def test_one_dropped_press_is_resent_through_the_pad(self):
        # wtb3 / kill6: the CROSS that enters CREATE GAME was eaten -- the screen stayed BRIEFING ROOM
        frames = (BRIEFING_CREATE_LIT, BRIEFING_CREATE_LIT, CREATE_GAME, CREATE_GAME_KBD, CREATE_GAME_CHOOSE_LIT,
                  PLAY_LIST, CREATE_GAME_CHOOSE_LIT, GAME_LOBBY_NOTICE, GAME_LOBBY)
        sh, _ = run_host(*frames)
        self.assertEqual(sh.presses, HOST_PRESSES[:2] + [("pad", "CROSS")] + HOST_PRESSES[2:])
        self.assertIn("LOBBY RESEND create-game:enter attempt=1", sh.logs)
        self.assertEqual(press_lines(sh, "create-game:enter"),
                         ["[lobby] create-game:enter press=cross verified=False attempt=1",
                          "[lobby] create-game:enter press=cross verified=True attempt=2"])

    def test_without_a_pad_file_the_resend_is_a_posted_key(self):
        frames = (BRIEFING_JOIN_LIT, BRIEFING_CREATE_LIT) + HOST_HAPPY[1:]
        sh, _ = run_host(*frames, pad_file=None)
        self.assertEqual(sh.presses, [("key", "up"), ("key", "up")] + HOST_PRESSES[1:])

    def check_class(self, frames, cls, btn, n_before):
        sh, g = FakeShell(), Grabs(*frames)
        sh.is_screen = lambda name, thresh=None: name == "game_lobby"
        with mock.patch.object(L.winshot, "grab", g), mock.patch.object(L, "choose_map", return_value=0), \
                self.assertRaises(L.LobbyFail) as cm:
            L.host_game(sh)
        self.assertEqual((cm.exception.cls, cm.exception.code), (cls, L.LOBBY_FAIL_EXIT))
        self.assertTrue(any(m.startswith(f"RESULT LOBBY-FAIL {cls}") for m in sh.logs), sh.logs)
        self.assertIn(f"LOBBY class={cls}", sh.logs)
        pads = [p for p in sh.presses if p[0] == "pad"]
        self.assertEqual(pads, [("pad", btn.upper())] * L.LOBBY_RESEND_MAX)
        self.assertEqual(len(sh.presses), n_before + 1 + L.LOBBY_RESEND_MAX)      # nothing pressed after the failure
        self.assertEqual(press_lines(sh, cls),
                         [f"[lobby] {cls} press={btn} verified=False attempt={k}" for k in range(1, L.LOBBY_RESEND_MAX + 2)])
        return sh

    def test_select_never_lit(self):
        self.check_class((BRIEFING_JOIN_LIT,), "create-game:select", "up", 0)

    def test_enter_never_leaves_the_briefing_room(self):          # wtb3, kill6
        self.check_class((BRIEFING_CREATE_LIT, BRIEFING_CREATE_LIT), "create-game:enter", "cross", 1)

    def test_name_keyboard_never_opens(self):                     # kill6's keyboard
        self.check_class((BRIEFING_CREATE_LIT, CREATE_GAME, CREATE_GAME), "create-game:name-keyboard", "cross", 2)

    def test_choose_games_row_never_lit(self):                    # wtb3's cursor on RANK RESTRICTIONS
        self.check_class((BRIEFING_CREATE_LIT, CREATE_GAME, CREATE_GAME_KBD, CREATE_GAME),
                         "create-game:choose-games-select", "up", 4)

    def test_choose_games_never_opens(self):
        self.check_class((BRIEFING_CREATE_LIT, CREATE_GAME, CREATE_GAME_KBD, CREATE_GAME_CHOOSE_LIT, CREATE_GAME_CHOOSE_LIT),
                         "create-game:choose-games", "cross", 5)

    def test_accept_never_returns_to_create_game(self):           # kill4, kill7, 8b: play list still up
        self.check_class(HOST_HAPPY[:5] + (PLAY_LIST_KILL4,), "create-game:accept", "square", 6)

    def test_create_never_makes_a_lobby(self):                    # kill4's 17_game_lobby_FAILED
        self.check_class(HOST_HAPPY[:6] + (CREATE_GAME_NO_LOBBY_KILL4,), "create-game:create", "square", 7)

    def test_continue_never_dismisses_the_notice(self):
        self.check_class(HOST_HAPPY[:7] + (GAME_LOBBY_NOTICE,), "create-game:continue", "cross", 8)

    def test_classes_are_not_stage_timeouts(self):
        for stage in HOST_STAGES:
            self.assertFalse(stage.startswith("timeout:"))
        self.assertEqual(getattr(L.host_game, "lobby_stage", None), "host")


JOIN_HAPPY = (GAMES_LIST_ACTIVE, GAME_LOBBY_NOTICE, GAME_LOBBY)
JOIN_PRESSES = [("key", "cross"), ("key", "cross"), ("key", "cross")]


class JoinGameVerified(unittest.TestCase):
    def run_join(self, *frames, expect=None):
        sh, g = FakeShell(), Grabs(*frames)
        sh.is_screen = lambda name, thresh=None: name == "game_lobby"
        with mock.patch.object(L.winshot, "grab", g), mock.patch.object(L, "lobby_teams", return_value=(0, 0)):
            if expect is None:
                L.join_game(sh, switch=False)
                return sh
            with self.assertRaises(L.LobbyFail) as cm:
                L.join_game(sh, switch=False)
        self.assertEqual((cm.exception.cls, cm.exception.code), (expect, L.LOBBY_FAIL_EXIT))
        self.assertIn(f"LOBBY class={expect}", sh.logs)
        self.assertEqual([p for p in sh.presses if p[0] == "pad"], [("pad", "CROSS")] * L.LOBBY_RESEND_MAX)
        return sh

    def test_happy_path_issues_the_same_presses_as_before(self):
        sh = self.run_join(*JOIN_HAPPY)
        self.assertEqual(sh.presses, JOIN_PRESSES)
        for stage in ("join:list", "join:enter", "join:continue"):
            self.assertEqual(press_lines(sh, stage), [f"[lobby] {stage} press=cross verified=True attempt=1"])
        self.assertIn("17_game_lobby_ok", sh.shots)

    def test_no_games_to_join(self):                              # wtb3/wtb5's B: the host never created the world
        sh = self.run_join(GAMES_LIST_NONE, expect="join:list")
        self.assertEqual(len(sh.presses), 1 + L.LOBBY_RESEND_MAX)

    def test_list_activates_late_then_joins(self):
        sh = self.run_join(GAMES_LIST_NONE, GAMES_LIST_ACTIVE, GAME_LOBBY_NOTICE, GAME_LOBBY)
        self.assertEqual(sh.presses, [("key", "cross"), ("pad", "CROSS"), ("key", "cross"), ("key", "cross")])
        self.assertIn("LOBBY RESEND join:list attempt=1", sh.logs)

    def test_enter_never_reaches_the_lobby(self):                 # launch1 / launch1b: games list still up at 0.577
        sh = self.run_join(GAMES_LIST_ACTIVE, JOIN_NO_LOBBY_LAUNCH1, expect="join:enter")
        self.assertEqual(len(sh.presses), 2 + L.LOBBY_RESEND_MAX)

    def test_continue_never_dismisses_the_notice(self):
        sh = self.run_join(GAMES_LIST_ACTIVE, GAME_LOBBY_NOTICE, GAME_LOBBY_NOTICE, expect="join:continue")
        self.assertEqual(len(sh.presses), 3 + L.LOBBY_RESEND_MAX)


class WaitForRaises(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.sh = FakeShell()
        self.sh.clock = lambda: self.now[0]
        self.sh.is_screen = lambda name, thresh=None: False

    def tick(self, s):
        self.now[0] += s

    def test_timeout_is_a_classified_failure(self):
        with mock.patch.object(L.time, "sleep", self.tick), self.assertRaises(L.LobbyFail) as cm:
            self.sh.wait_for("universe", 10)
        self.assertEqual((cm.exception.cls, cm.exception.code), ("screen:universe", L.LOBBY_FAIL_EXIT))
        self.assertIn("TIMEOUT waiting for universe", self.sh.logs)
        self.assertIn("timeout_universe", self.sh.shots)
        self.assertIn("LOBBY class=screen:universe", self.sh.logs)

    def test_a_caller_does_not_press_on(self):
        # wtb4 / 3b: after `TIMEOUT waiting for universe` the old login pressed CROSS into whatever was on screen
        with mock.patch.object(L.time, "sleep", self.tick), self.assertRaises(L.LobbyFail) as cm:
            L.login(self.sh, "socomc", "socom", existing=True)
        self.assertEqual(cm.exception.cls, "screen:universe")
        self.assertEqual(self.sh.presses, [])
        self.assertNotIn("01_universe", self.sh.shots)

    def test_class_override_and_explicit_opt_out(self):
        with mock.patch.object(L.time, "sleep", self.tick), self.assertRaises(L.LobbyFail) as cm:
            self.sh.wait_for("login", 5, cls="pre-login")
        self.assertEqual(cm.exception.cls, "pre-login")
        self.sh.logs.clear()
        with mock.patch.object(L.time, "sleep", self.tick):
            self.assertFalse(self.sh.wait_for("persona", 5, required=False))
        self.assertIn("TIMEOUT waiting for persona", self.sh.logs)
        self.assertFalse([m for m in self.sh.logs if "LOBBY" in m])

    def test_found_returns_true(self):
        self.sh.is_screen = lambda name, thresh=None: name == "eula"
        with mock.patch.object(L.time, "sleep", self.tick):
            self.assertTrue(self.sh.wait_for("eula", 5))

    def test_persona_is_the_only_opt_out(self):
        # research/28 + drive logs: `TIMEOUT waiting for persona` occurred in 11 launches that reached gameplay;
        # every other screen's timeout occurred only in failed launches
        import inspect
        import re
        calls = re.findall(r'wait_for\(([^)]*)required=False', inspect.getsource(L))
        self.assertEqual(calls, ['"persona", 60, '])


class PreLogin(unittest.TestCase):
    def setUp(self):
        self.sh = FakeShell()
        self.sh.last = None

    def test_main_menu_never_reached(self):
        self.sh.is_screen = lambda name, thresh=None: False
        with mock.patch.object(L.drive, "wait_stable"), mock.patch.object(L.drive, "frame", return_value=None), \
                mock.patch.object(L.time, "sleep"), self.assertRaises(L.LobbyFail) as cm:
            L.boot_to_online(self.sh)
        self.assertEqual((cm.exception.cls, cm.exception.code), ("pre-login", L.LOBBY_FAIL_EXIT))
        self.assertEqual(self.sh.presses, [("key", "cross")] * 9)
        self.assertIn("LOBBY class=pre-login", self.sh.logs)
        self.assertNotIsInstance(cm.exception.code, str)

    def test_login_screen_never_shown_after_the_menu(self):       # wtb4 / 3b root: `TIMEOUT waiting for login`
        now = [0.0]
        self.sh.clock = lambda: now[0]
        self.sh.is_screen = lambda name, thresh=None: name == "main_menu"

        def tick(s):
            now[0] += s

        with mock.patch.object(L.drive, "wait_stable"), mock.patch.object(L.drive, "frame", return_value=None), \
                mock.patch.object(L.time, "sleep", tick), self.assertRaises(L.LobbyFail) as cm:
            L.boot_to_online(self.sh)
        self.assertEqual(cm.exception.cls, "pre-login")
        self.assertEqual(self.sh.presses, [("key", "down"), ("key", "cross")])
        self.assertIn("TIMEOUT waiting for login", self.sh.logs)


class ClassNames(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(L.CLASS_PRE_LOGIN, "pre-login")
        self.assertEqual(L.LOBBY_TITLES, ("briefing_room", "create_game", "play_list", "game_lobby"))
        self.assertLessEqual(L.LOBBY_TITLE_MAX_DIST, 0.20)
        for name in L.LOBBY_TITLES:
            self.assertTrue(os.path.exists(os.path.join(L.LOBBY_REF_DIR, f"title_{name}.png")), name)


if __name__ == "__main__":
    unittest.main()
