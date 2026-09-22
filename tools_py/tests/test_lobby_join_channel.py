"""Fix wave W8, ruling R240 (2026-09-22): the join driver presses REFRESH LIST, takes a `--channel`, and stops
calling an empty games list a failure.

What happened. `python -m tools_py.parity.online_login_ours --join --instance B` logged into the owner's live
lobby and reached the BRIEFING ROOM in 175 s (logs/parity/join_owner_lobby/drive.txt). It then pressed CROSS on
JOIN GAME four times on Channel 1 and ended `RESULT LOBBY-FAIL join:list -- still not registered after 3
re-sends`. The four captures it kept say more than the log did: miss_join_list_1 and _3 still showed the long
"Activate the games list and choose a game to join." prompt (those presses really were eaten), _2 showed
"... choose a game to WATCH." with WATCH GAME highlighted (the cursor had left JOIN GAME between the first and
second press -- nothing in the driver presses DOWN there and the move is still unexplained), and only _4 and
the fail capture read "There are no games to join." Three defects in one line:

1. REFRESH LIST was never pressed, so the only list the driver could ever see was the one the room happened to
   open with. It is the fifth row of the briefing room's left menu (CREATE GAME / JOIN GAME / WATCH GAME /
   PLAYER LIST / REFRESH LIST) and nothing in the driver had ever moved that cursor.
2. No channel was chosen, so the run could only find a game in whichever room the list opened on.
3. "There are no games to join." was scored as OUR failure. It is not one: it is a statement about the lobby.

The frames in this test are built the way test_online_login_lobby and test_lobby_teams build theirs -- the
committed crops under tools_py/tests/fixtures/lobby/ pasted into a 640x448 frame -- with two additions that
have no committed crop and are therefore painted from measurements instead:

  * a lit menu row: a teal fill, which reads as a median of 68 over x 18..135 on every briefing-room capture
    in logs/parity, against 22-25 for an unlit row.
  * the prompt band's sentence: only its LENGTH is read (briefing_banner_span), so a bar of the measured width
    is the same measurement as the text. The widths here are the ones the real captures give:
        419-429 px  "Activate the games list and choose a game to join." / "... to watch."   (266 captures)
        385 px      the same sentence on PCSX2, which draws these screens ~7% narrower        (2 captures)
        207 px      "There are no games to join."      (7: join_owner_lobby's fail capture and its miss_4,
                                                        plus ours_task6_mp, ours_task6_scale, ours_task7_cal1,
                                                        ours_task7_wtb3, ours_task7_wtb5 -- the five runs this
                                                        file's own comment already names as empty-list runs)
        179 px      "Choose game to join."             (104, every one of them with a game in the list)
"""
import unittest
from unittest import mock

import numpy as np
from PIL import Image

from tools_py.parity import lobby_report
from tools_py.parity import online_login_ours as L
from tools_py.tests import test_online_login_lobby as T

FakeShell, Grabs, frame, gray, TITLE = T.FakeShell, T.Grabs, T.frame, T.gray, T.TITLE
ROW_GAMES_LIST = T.ROW_GAMES_LIST
BRIEFING_TITLE = ("title_lad2_briefing_room.png", TITLE)
GAME_LOBBY_TITLE = ("title_lad2_game_lobby.png", TITLE)
LIST_LIT = ("row_games_list_lit_8c.png", ROW_GAMES_LIST)
LIST_NONE = ("row_games_list_none_wtb5.png", ROW_GAMES_LIST)
CROSS, DOWN, UP = ("key", "cross"), ("key", "down"), ("key", "up")
PAD_DOWN, PAD_CROSS = ("pad", "DOWN"), ("pad", "CROSS")

PROMPT_PX, PROMPT_PCSX2_PX, NO_GAMES_PX, CHOOSE_PX = 419, 385, 207, 179


def with_menu_row(im, row):
    """The BRIEFING ROOM menu highlight drawn on `row` (a BRIEFING_MENU name): the teal fill, at the 68 every
    lit row of every capture reads."""
    a = np.asarray(im.convert("L"), dtype=np.uint8).copy()
    y0, y1, x0, x1 = L.LOBBY_ROWS[row]
    a[y0:y1, x0:x1] = np.maximum(a[y0:y1, x0:x1], 68)
    return Image.fromarray(a).convert("RGB")


def with_banner(im, width):
    """`width` px of ink on the prompt band, centred as the game centres its sentences. 0 draws nothing."""
    if width <= 0:
        return im
    a = np.asarray(im.convert("L"), dtype=np.uint8).copy()
    rows, cols = L.BRIEFING_BANNER
    x0 = cols.start + ((cols.stop - cols.start) - width) // 2
    a[rows.start + 2:rows.stop - 5, x0:x0 + width] = 200
    return Image.fromarray(a).convert("RGB")


def briefing(row="join_game", banner=PROMPT_PX, listed=False):
    im = frame(BRIEFING_TITLE, *( (LIST_LIT,) if listed else (LIST_NONE,) ))
    return with_menu_row(with_banner(im, banner), row) if row else with_banner(im, banner)


UNPRESSED = briefing()                                     # the banner still asks you to activate the list
NO_GAMES = briefing(banner=NO_GAMES_PX)                    # "There are no games to join."
LISTED = briefing(banner=CHOOSE_PX, listed=True)           # "Choose game to join.", a game highlighted
REFRESH_LIT = briefing(row="refresh_list")
WATCH_LIT = briefing(row="watch_game")
PLAYER_LIST_LIT = briefing(row="player_list")
NO_ROW_LIT = briefing(row=None)
GAME_LOBBY_NOTICE, GAME_LOBBY = T.GAME_LOBBY_NOTICE, T.GAME_LOBBY


def rooms(top=125):
    """A BRIEFING ROOMS frame with the room list's highlight at `top`. 125 is where all 273 real
    `*10_rooms.png` captures in logs/parity put it; None draws no highlight at all."""
    a = np.zeros((448, 640), dtype=np.uint8)
    a[96:120, 190:620] = 36                                # the column-header bar, above the list
    if top is not None:
        a[top:top + 16, 190:620] = 38
    return Image.fromarray(a).convert("RGB")


def press_lines(sh, stage):
    return [m for m in sh.logs if m.startswith(f"[lobby] {stage} ")]


class BannerLength(unittest.TestCase):
    """The measure that tells "the press has not taken" from "the list is empty"."""

    def test_the_measured_sentences_land_on_the_right_side_of_the_threshold(self):
        for width, want in ((PROMPT_PX, "prompt"), (429, "prompt"), (PROMPT_PCSX2_PX, "prompt"),
                            (NO_GAMES_PX, "short"), (CHOOSE_PX, "short"), (0, "dark")):
            g = gray(with_banner(frame(BRIEFING_TITLE), width))
            self.assertEqual(L.briefing_banner_span(g), max(width, 0), width)
            self.assertEqual(L.briefing_banner(g), want, width)

    def test_the_threshold_has_room_on_both_sides(self):
        # 207 px is the widest short sentence, 385 the narrowest long one (PCSX2's rendering).
        self.assertGreater(L.BRIEFING_BANNER_WIDE_PX, NO_GAMES_PX * 1.4)
        self.assertLess(L.BRIEFING_BANNER_WIDE_PX, PROMPT_PCSX2_PX * 0.79)
        self.assertLess(L.BRIEFING_BANNER_MIN_PX, CHOOSE_PX)


class MenuRowGeometry(unittest.TestCase):
    def test_the_five_rows_step_by_the_menus_pitch_and_do_not_overlap(self):
        bands = [L.LOBBY_ROWS[r] for r in L.BRIEFING_MENU]
        self.assertEqual(L.BRIEFING_MENU[0], "create_game")           # row 0 is the band that was already here
        for (y0, _y1, x0, x1), (ny0, _ny1, nx0, nx1) in zip(bands, bands[1:]):
            self.assertEqual(ny0 - y0, 32)                            # the menu's measured pitch
            self.assertEqual((x0, x1), (nx0, nx1))
        for row in L.BRIEFING_MENU:
            self.assertEqual(L.LOBBY_ROW_LIT_MEDIAN[row], L.LOBBY_ROW_LIT_MEDIAN["create_game"])

    def test_focus_names_the_single_lit_row(self):
        for row in L.BRIEFING_MENU:
            self.assertEqual(L.briefing_focus_row(gray(briefing(row=row))), row)
        self.assertIsNone(L.briefing_focus_row(gray(NO_ROW_LIT)))
        two = with_menu_row(briefing(row="join_game"), "refresh_list")
        self.assertIsNone(L.briefing_focus_row(gray(two)))             # a transition lights two: no verdict


class JoinListState(unittest.TestCase):
    def test_the_four_states(self):
        self.assertEqual(L.join_list_state(gray(LISTED)), "listed")
        self.assertEqual(L.join_list_state(gray(NO_GAMES)), "none")
        self.assertEqual(L.join_list_state(gray(UNPRESSED)), "unpressed")
        self.assertEqual(L.join_list_state(gray(briefing(banner=0))), "unread")     # mid-fade
        self.assertEqual(L.join_list_state(gray(GAME_LOBBY)), "unread")             # not the briefing room

    def test_the_watch_banner_is_a_prompt_too(self):
        # miss_join_list_2.png: the cursor had drifted to WATCH GAME and the banner read "... to watch." at
        # 429 px. Still the long prompt, so still "the press has not taken" -- not an empty list.
        self.assertEqual(L.join_list_state(gray(briefing(row="watch_game", banner=429))), "unpressed")


class BriefingSelect(unittest.TestCase):
    def walk(self, *frames):
        sh, g = FakeShell(), Grabs(*frames)
        with mock.patch.object(L.winshot, "grab", g):
            return sh, L.briefing_select(sh, "join:refresh-select", "refresh_list")

    def test_join_game_to_refresh_list_is_three_verified_downs(self):
        sh, n = self.walk(briefing(), WATCH_LIT, PLAYER_LIST_LIT, REFRESH_LIT)
        self.assertEqual(n, 3)
        self.assertEqual(sh.presses, [DOWN, DOWN, DOWN])
        for row in ("watch-game", "player-list", "refresh-list"):
            self.assertEqual(press_lines(sh, f"join:refresh-select:{row}"),
                             [f"[lobby] join:refresh-select:{row} press=down verified=True attempt=1"])

    def test_a_dropped_down_is_re_sent_on_the_row_it_failed_on(self):
        sh, n = self.walk(briefing(), briefing(), WATCH_LIT, PLAYER_LIST_LIT, REFRESH_LIT)
        self.assertEqual(sh.presses, [DOWN, PAD_DOWN, DOWN, DOWN])
        self.assertIn("LOBBY RESEND join:refresh-select:watch-game attempt=1", sh.logs)

    def test_a_down_that_never_lands_fails_naming_the_row(self):
        sh, g = FakeShell(), Grabs(briefing(), briefing())
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.briefing_select(sh, "join:refresh-select", "refresh_list")
        self.assertEqual((cm.exception.cls, cm.exception.code),
                         ("join:refresh-select:watch-game", L.LOBBY_FAIL_EXIT))

    def test_walking_back_up_presses_up(self):
        sh, g = FakeShell(), Grabs(REFRESH_LIT, PLAYER_LIST_LIT, WATCH_LIT, briefing())
        with mock.patch.object(L.winshot, "grab", g):
            self.assertEqual(L.briefing_select(sh, "join:list-select", "join_game"), 3)
        self.assertEqual(sh.presses, [UP, UP, UP])

    def test_already_there_presses_nothing(self):
        sh, g = FakeShell(), Grabs(REFRESH_LIT)
        with mock.patch.object(L.winshot, "grab", g):
            self.assertEqual(L.briefing_select(sh, "join:refresh-select", "refresh_list"), 0)
        self.assertEqual(sh.presses, [])

    def test_an_unreadable_menu_fails_rather_than_pressing_blind(self):
        for bad, why in ((NO_ROW_LIT, "no single row"), (GAME_LOBBY, "not on screen")):
            sh, g = FakeShell(), Grabs(bad)
            with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
                L.briefing_select(sh, "join:refresh-select", "refresh_list")
            self.assertEqual(cm.exception.cls, "join:refresh-select")
            self.assertIn(why, cm.exception.detail)
            self.assertEqual(sh.presses, [])


# The default join: REFRESH LIST (three DOWNs, CROSS, three UPs) and then the CROSS on JOIN GAME.
REFRESH_WALK = (briefing(), WATCH_LIT, PLAYER_LIST_LIT, REFRESH_LIT,      # down, down, down
                REFRESH_LIT,                                              # the frame read after the CROSS
                REFRESH_LIT, PLAYER_LIST_LIT, WATCH_LIT, briefing())      # up, up, up
REFRESH_PRESSES = [DOWN, DOWN, DOWN, CROSS, UP, UP, UP]


class RefreshBeforeJoin(unittest.TestCase):
    def join(self, *after, expect=None):
        sh, g = FakeShell(), Grabs(*REFRESH_WALK, *after)
        sh.is_screen = lambda name, thresh=None: name == "game_lobby"
        with mock.patch.object(L.winshot, "grab", g), mock.patch.object(L, "lobby_teams", return_value=(0, 0)):
            if expect is None:
                L.join_game(sh, switch=False, channel=1)
                return sh
            with self.assertRaises(expect) as cm:
                L.join_game(sh, switch=False, channel=1)
        self.cm = cm
        return sh

    def test_refresh_list_is_pressed_before_join_game(self):
        sh = self.join(LISTED, GAME_LOBBY_NOTICE, GAME_LOBBY)
        self.assertEqual(sh.presses, REFRESH_PRESSES + [CROSS, CROSS, CROSS])
        self.assertIn("[lobby] join:refresh press=cross verified=True attempt=1 (row refresh_list, "
                      f"banner {PROMPT_PX} px, after 3 select presses)", sh.logs)
        self.assertIn("11b_refresh_list", sh.shots)
        # and the cursor is back on JOIN GAME before the join CROSS, read rather than assumed
        self.assertEqual(press_lines(sh, "join:list-select:join-game"),
                         ["[lobby] join:list-select:join-game press=up verified=True attempt=1"])
        self.assertIn("17_game_lobby_ok", sh.shots)

    def test_no_refresh_is_the_pre_r240_path(self):
        sh, g = FakeShell(), Grabs(LISTED, GAME_LOBBY_NOTICE, GAME_LOBBY)
        sh.is_screen = lambda name, thresh=None: name == "game_lobby"
        with mock.patch.object(L.winshot, "grab", g), mock.patch.object(L, "lobby_teams", return_value=(0, 0)):
            L.join_game(sh, switch=False, refresh=False)
        self.assertEqual(sh.presses, [CROSS, CROSS, CROSS])

    def test_a_press_that_still_has_not_taken_is_re_sent(self):
        # the banner still the long prompt after the join CROSS: exactly R240's first three presses
        sh = self.join(UNPRESSED, LISTED, GAME_LOBBY_NOTICE, GAME_LOBBY)
        self.assertEqual(sh.presses, REFRESH_PRESSES + [CROSS, PAD_CROSS, CROSS, CROSS])
        self.assertIn("LOBBY RESEND join:list attempt=1", sh.logs)
        self.assertIn("[lobby] join:list-read -> unpressed "
                      f"(row join_game, banner {PROMPT_PX} px, first row median 15)", sh.logs)

    def test_a_cursor_that_has_left_join_game_is_not_pressed_at_again(self):
        # R240's miss_join_list_2: between press 1 and press 2 the highlight was on WATCH GAME and the banner
        # read "... choose a game to watch." A re-send there opens the WATCH list.
        sh = self.join(briefing(row="watch_game", banner=429), expect=L.LobbyFail)
        self.assertEqual(self.cm.exception.cls, L.CLASS_CURSOR_DRIFT)
        self.assertIn("WATCH GAME", self.cm.exception.detail)
        self.assertEqual(sh.presses, REFRESH_PRESSES + [CROSS])      # the one press, then the verdict
        self.assertFalse([m for m in sh.logs if m.startswith("LOBBY RESEND join:list ")])


class RefreshLeavesTheRoom(unittest.TestCase):
    def test_it_is_join_refresh_and_nothing_is_pressed_after_it(self):
        walk = (briefing(), WATCH_LIT, PLAYER_LIST_LIT, REFRESH_LIT, GAME_LOBBY)
        sh, g = FakeShell(), Grabs(*walk)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.join_game(sh, switch=False)
        self.assertEqual((cm.exception.cls, cm.exception.code), ("join:refresh", L.LOBBY_FAIL_EXIT))
        self.assertEqual(sh.presses, [DOWN, DOWN, DOWN, CROSS])       # no re-send into an unknown screen
        self.assertIn("LOBBY class=join:refresh", sh.logs)


class NoGamesIsNotAFailure(unittest.TestCase):
    def run_join(self, channel=1):
        sh, g = FakeShell(), Grabs(*REFRESH_WALK, NO_GAMES)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyNoGames) as cm:
            L.join_game(sh, switch=False, channel=channel)
        return sh, cm.exception

    def test_the_empty_list_is_its_own_outcome(self):
        sh, exc = self.run_join()
        self.assertEqual(exc.code, L.LOBBY_NO_GAMES_EXIT)
        self.assertNotEqual(L.LOBBY_NO_GAMES_EXIT, L.LOBBY_FAIL_EXIT)
        self.assertNotIsInstance(exc, L.LobbyFail)
        self.assertIn('RESULT NO-GAMES channel=1 -- the briefing room answered "There are no games to join."',
                      sh.logs)
        self.assertIn(f"LOBBY class={L.CLASS_NO_GAMES}", sh.logs)
        self.assertIn("lobby_no_games", sh.shots)
        self.assertFalse([m for m in sh.logs if m.startswith("RESULT LOBBY-FAIL")])

    def test_the_channel_is_named(self):
        # so a run that found nothing says WHERE it found nothing -- the whole point of taking a --channel
        sh, exc = self.run_join(channel=3)
        self.assertEqual(exc.channel, 3)
        self.assertTrue([m for m in sh.logs if m.startswith("RESULT NO-GAMES channel=3 -- ")], sh.logs)

    def test_an_empty_list_is_not_pressed_at_again(self):
        # R240 pressed CROSS four times at "There are no games to join.", and the second of those four landed
        # the cursor on WATCH GAME (miss_join_list_2.png). One press, then the verdict.
        sh, _ = self.run_join()
        self.assertEqual(sh.presses, REFRESH_PRESSES + [CROSS])
        self.assertFalse([m for m in sh.logs if m.startswith("LOBBY RESEND join:list ")])

    def test_lobby_report_does_not_read_it_as_a_lobby_failure(self):
        sh, _ = self.run_join()
        summary = lobby_report.summarise([f"  12.0s A_{m}" for m in sh.logs])
        self.assertEqual(summary["outcome"], lobby_report.OUTCOME_RESULT)
        self.assertEqual(summary["cls"], "NO-GAMES")
        self.assertNotEqual(summary["outcome"], lobby_report.OUTCOME_LOBBY_FAIL)


class SelectRoom(unittest.TestCase):
    def select(self, channel, *frames):
        sh, g = FakeShell(), Grabs(*frames)
        with mock.patch.object(L.winshot, "grab", g):
            return sh, L.select_room(sh, channel)

    def test_the_highlight_is_found_where_every_capture_puts_it(self):
        self.assertEqual(L.rooms_fill_top(gray(rooms())), 125)
        self.assertEqual(L.rooms_fill_top(gray(rooms(top=147))), 147)
        self.assertIsNone(L.rooms_fill_top(gray(rooms(top=None))))     # the header bar alone is not a row

    def test_channel_one_presses_nothing(self):
        for channel in (1, None):
            sh, n = self.select(channel, rooms())
            self.assertEqual((n, sh.presses), (0, []))

    def test_channel_two_presses_down_and_requires_the_highlight_to_move(self):
        sh, n = self.select(2, rooms(125), rooms(147))
        self.assertEqual((n, sh.presses), (1, [DOWN]))
        self.assertIn("[lobby] briefing rooms: DOWN 1 for channel 2 -- highlight y 125 -> 147", sh.logs)
        self.assertIn("10_rooms_channel_2", sh.shots)

    def test_a_highlight_that_does_not_move_is_login_channel_not_a_wrong_room(self):
        # every one of the 306 room-list captures in logs/parity shows ONE room: this is what a --channel 2
        # against such a server does, instead of entering room 1 and reporting it as room 2.
        sh, g = FakeShell(), Grabs(rooms(125))
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.select_room(sh, 2)
        self.assertEqual((cm.exception.cls, cm.exception.code), (L.CLASS_CHANNEL, L.LOBBY_FAIL_EXIT))
        self.assertIn("fewer rooms", cm.exception.detail)
        self.assertIn("10_rooms_channel_2", sh.shots)

    def test_channel_zero_is_refused(self):
        sh, g = FakeShell(), Grabs(rooms())
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.select_room(sh, 0)
        self.assertEqual(cm.exception.cls, L.CLASS_CHANNEL)
        self.assertEqual(sh.presses, [])

    def test_to_briefing_room_takes_the_channel_through(self):
        sh, g = FakeShell(), Grabs(rooms())
        sh.is_screen = lambda name, thresh=None: False
        seen = []
        with mock.patch.object(L.winshot, "grab", g), mock.patch.object(L, "select_room", lambda s, c: seen.append(c)), \
                mock.patch.object(L.Shell, "wait_for", lambda *a, **k: True), \
                mock.patch.object(L.Shell, "press_until_gone", lambda *a, **k: True):
            L.to_briefing_room(sh, 4)
        self.assertEqual(seen, [4])


class CliSurface(unittest.TestCase):
    """The two flags R240 asked for exist on the command line the controller will type. `--help` exits inside
    argparse, so nothing is launched."""

    def test_channel_and_no_refresh_are_arguments(self):
        import os
        import subprocess
        import sys
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        out = subprocess.run([sys.executable, "-m", "tools_py.parity.online_login_ours", "--help"],
                             cwd=root, capture_output=True, text=True, check=True).stdout
        self.assertIn("--channel", out)
        self.assertIn("--no-refresh", out)
        self.assertIn("--join", out)


if __name__ == "__main__":
    unittest.main()
