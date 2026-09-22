"""Sprint 6, launch s6_ladder9 (2026-09-15, harness d6e417f): the GAME LOBBY showed both players under SEALS
(socomc, socome, both green), TERRORISTS empty, the host's row "NOT READY 3" -- a match cannot start with an
empty team, so both instances sat there until the liveness timeout (RESULT LOBBY-FAIL timeout:launch).

Two harness gaps:
1. B's team read "(288, 0)" (both names on the SEALs side; s6_ladder5/8 read (143, 144)) was logged and not acted
   on: join_game(switch=False) never pressed SWITCH TEAMS. Now the read decides -- one name per column or a
   verified SWITCH TEAMS press, re-read, up to LOBBY_SWITCH_MAX times, else `join:switch-teams`; the host reads
   the same columns on the frame its READY search starts from and fails `host:teams-unbalanced` rather than
   ready up and wait 200 s.
2. Both READY checks read "row-2 label right edges [None, None]" and took the "game lobby gone" branch with the
   lobby still up: after the CROSS the cursor highlight was off the row and the label text was dim (max 110,
   the detector wanted > 110) with a count suffix ("NOT READY 34"). The detector now reads at luma 75 (the teal
   highlight fill peaks at 68, dim text at 83-85), ignores the count columns (>= READY_COUNT_COL), and a None
   read consults the title band: GAME LOBBY still up -> re-read up to READY_REREAD_MAX times; only a gone title
   is "gone".

Frames are the fixtures under tools_py/tests/fixtures/lobby/ (make_teams_fixtures.py) pasted into a black
640x448 frame, the test_online_login_lobby / test_lobby_ready pattern.
"""
import unittest
from unittest import mock

import numpy as np
from PIL import Image

from tools_py.parity import online_login_ours as L
from tools_py.tests import test_online_login_lobby as T

FakeShell, Grabs, frame, gray, TITLE, NOTICE = T.FakeShell, T.Grabs, T.frame, T.gray, T.TITLE, T.NOTICE
READY_BOX = (14, 150, 175, 190)
TEAMS_BOX = (180, 240, 615, 300)
LOBBY = (("title_lad2_game_lobby.png", TITLE), ("notice_gone_8c.png", NOTICE))
CROSS, PAD_CROSS, DOWN, UP = ("key", "cross"), ("pad", "CROSS"), ("key", "down"), ("key", "up")


def with_cursor(im, row):
    """The GAME LOBBY menu highlight (teal fill, mean ~70) drawn on menu row `row` (0 ARMORY, 1 SWITCH TEAMS,
    2 READY); the label text inside the row box is kept."""
    a = np.asarray(im.convert("L"), dtype=np.uint8).copy()
    y0, y1 = L.LOBBY_CURSOR_ROWS[row]
    a[y0:y1, 22:165] = np.maximum(a[y0:y1, 22:165], 68)
    return Image.fromarray(a).convert("RGB")


def without_names(im):
    """The team columns blank: the notice_gone_8c crop (rows 152-265) carries the host's SEALS name (143 px)."""
    a = np.asarray(im.convert("L"), dtype=np.uint8).copy()
    a[240:300, 180:615] = 0
    return Image.fromarray(a).convert("RGB")


def lobby(teams=None, label=None, cursor=None):
    parts = list(LOBBY)
    if teams:
        parts.append((teams, TEAMS_BOX))
    if label:
        parts.append((label, READY_BOX))
    im = frame(*parts)
    if not teams:
        im = without_names(im)
    return with_cursor(im, cursor) if cursor is not None else im


BOTH_SEALS, ONE_EACH, HOST_ALONE = "teams_lad9_both_seals.png", "teams_lad8_one_each.png", "teams_lad8_host_alone.png"
READY_LIT, NOT_READY_34_DIM = "ready_lad8_ready_lit.png", "ready_lad9_not_ready_34_dim.png"
LOBBY_GONE = frame(("title_kill4_no_lobby.png", TITLE), ("ready_8c_A_left_lobby.png", READY_BOX))
BLACK = Image.new("RGB", (640, 448), 0)


def teams_of(name):
    return L.lobby_teams_of(gray(frame((name, TEAMS_BOX))))


def edge_of(name):
    return L.ready_label_edge(gray(frame((name, READY_BOX))))


class TeamDetector(unittest.TestCase):
    def test_pixels_on_the_captures(self):
        self.assertEqual(teams_of(BOTH_SEALS), (288, 0))          # s6_ladder9: both under SEALS
        self.assertEqual(teams_of(ONE_EACH), (143, 144))          # s6_ladder8 B_16
        self.assertEqual(teams_of("teams_lad5_one_each.png"), (143, 144))
        self.assertEqual(teams_of(HOST_ALONE), (143, 0))          # s6_ladder8 A_17: the host before the join
        self.assertEqual(L.lobby_teams_of(gray(BLACK)), (0, 0))

    def test_states(self):
        self.assertEqual(L.lobby_teams_state(143, 144), "ok")
        self.assertEqual(L.lobby_teams_state(288, 0), "one-sided")
        self.assertEqual(L.lobby_teams_state(0, 288), "one-sided")
        self.assertEqual(L.lobby_teams_state(143, 0), "unread")   # the host alone / a half-rendered frame
        self.assertEqual(L.lobby_teams_state(0, 0), "unread")
        self.assertEqual(L.lobby_teams_state(23, 0), "unread")    # an in-game frame's stray pixels
        self.assertEqual(L.lobby_teams_state(*teams_of(BOTH_SEALS)), "one-sided")
        self.assertEqual(L.lobby_teams_state(*teams_of(ONE_EACH)), "ok")
        self.assertEqual(L.lobby_teams_state(*teams_of(HOST_ALONE)), "unread")
        self.assertEqual(L.lobby_teams_state(*L.lobby_teams_of(gray(T.GAME_LOBBY))), "unread")   # (143, 0)

    def test_margins(self):
        self.assertLessEqual(2 * L.LOBBY_TEAM_NAME_MIN_PX, 143)   # a name is at least twice the floor
        self.assertGreaterEqual(L.LOBBY_TEAM_NAME_MIN_PX, 2 * 23)  # twice the in-game stray reading
        self.assertGreater(L.LOBBY_TEAM_TWO_NAMES_MIN_PX, 144 + 60)   # one name plus the name floor
        self.assertLess(L.LOBBY_TEAM_TWO_NAMES_MIN_PX, 288 - 60)      # two names minus it
        self.assertEqual(L.LOBBY_SWITCH_MAX, 3)


class ReadyLabelDetector(unittest.TestCase):
    def test_edges_with_and_without_a_count_suffix(self):
        self.assertEqual(edge_of("ready_lad9_not_ready_3_lit.png"), 82)     # "NOT READY 3", highlighted
        self.assertEqual(edge_of(NOT_READY_34_DIM), 82)                     # "NOT READY 34", dim: was None
        self.assertEqual(edge_of("ready_lad9_not_ready_lit.png"), 82)       # "NOT READY", highlighted
        self.assertEqual(edge_of(READY_LIT), 48)                            # "READY", highlighted
        self.assertEqual(edge_of("ready_lad8_ready_3_dim.png"), 48)         # "READY 3", dim: was None
        self.assertEqual(edge_of("ready_8a_A_dropped.png"), 48)             # the Sprint 5 fixtures read as before
        self.assertEqual(edge_of("ready_8a_B_taken.png"), 83)
        self.assertIsNone(edge_of("ready_8c_A_left_lobby.png"))            # in-game: nothing left of the count
        self.assertIsNone(L.ready_label_edge(gray(BLACK)))

    def test_dropped_verdicts(self):
        for name, dropped in (("ready_lad8_ready_lit.png", True), ("ready_lad8_ready_3_dim.png", True),
                              ("ready_lad9_not_ready_3_lit.png", False), (NOT_READY_34_DIM, False),
                              ("ready_lad9_not_ready_lit.png", False)):
            self.assertEqual(L.ready_dropped(gray(frame((name, READY_BOX)))), dropped, name)

    def test_luma_thresholds(self):
        self.assertEqual(L.READY_LABEL_LUMA, 110)       # the lit read is unchanged (Sprint 5 edges 48 / 83)
        self.assertGreater(L.READY_LABEL_DIM_LUMA, 68)  # the teal highlight fill's brightest pixel
        self.assertLess(L.READY_LABEL_DIM_LUMA, 83)     # dim label text (no cursor on the row) peaks at 83-85
        self.assertGreater(L.READY_COUNT_COL, 84)       # "NOT READY" ends at col 83-84
        self.assertLessEqual(L.READY_COUNT_COL, 98)     # the 8c in-game frame lights col 98; digits start at 117


JOIN_FRAMES = (T.GAMES_LIST_ACTIVE, T.GAME_LOBBY_NOTICE, T.GAME_LOBBY)   # join:list, join:enter, join:continue


def run_join(*frames):
    sh, g = FakeShell(), Grabs(*JOIN_FRAMES, *frames)
    sh.is_screen = lambda name, thresh=None: name == "game_lobby"
    with mock.patch.object(L.winshot, "grab", g):
        L.join_game(sh, switch=False, refresh=False)    # W8's REFRESH LIST is tested in test_lobby_join_channel
    return sh


def teams_lines(sh):
    return [m for m in sh.logs if m.startswith("[lobby] teams:")]


class JoinSwitchTeams(unittest.TestCase):
    JOIN = [CROSS, CROSS, CROSS]                          # join:list, join:enter, join:continue

    def test_a_one_name_each_no_switch_press(self):
        sh = run_join(lobby(ONE_EACH, cursor=1))
        self.assertEqual(sh.presses, self.JOIN)
        self.assertEqual(teams_lines(sh), ["[lobby] teams: seals=143 terrorists=144 -> ok (attempt 1)"])
        self.assertEqual(sh.lobby_role, "joiner")

    def test_b_both_on_seals_switch_registers_on_the_second_press(self):
        # team read 1: both on SEALS; cursor read: on SWITCH TEAMS -> CROSS; team read 2: unchanged (the
        # press was dropped); cursor read -> CROSS; team read 3: one each -> ok. Every press is preceded
        # by its own fresh cursor read, so each attempt consumes two frames.
        both = lobby(BOTH_SEALS, cursor=1)
        sh = run_join(both, both, both, both, lobby(ONE_EACH, cursor=1))
        self.assertEqual(sh.presses, self.JOIN + [CROSS, CROSS])
        self.assertEqual(teams_lines(sh), ["[lobby] teams: seals=288 terrorists=0 -> switch (attempt 1)",
                                           "[lobby] teams: seals=288 terrorists=0 -> switch (attempt 2)",
                                           "[lobby] teams: seals=143 terrorists=144 -> ok (attempt 3)"])
        self.assertEqual([m for m in sh.logs if m == "lobby cursor 1 for SWITCH TEAMS"], ["lobby cursor 1 for SWITCH TEAMS"] * 2)
        self.assertFalse([m for m in sh.logs if "LOBBY-FAIL" in m])

    def test_b2_cursor_moved_onto_switch_teams_first(self):
        # the cursor starts on READY (row 2): team read, cursor read -> UP, cursor read -> CROSS, team read ok
        sh = run_join(lobby(BOTH_SEALS, cursor=2), lobby(BOTH_SEALS, cursor=2), lobby(BOTH_SEALS, cursor=1),
                      lobby(ONE_EACH, cursor=1))
        self.assertEqual(sh.presses, self.JOIN + [UP, CROSS])

    def test_c_never_balanced_fails_join_switch_teams(self):
        sh, g = FakeShell(), Grabs(*JOIN_FRAMES, lobby(BOTH_SEALS, cursor=1))
        sh.is_screen = lambda name, thresh=None: name == "game_lobby"
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.join_game(sh, switch=False, refresh=False)
        self.assertEqual((cm.exception.cls, cm.exception.code), ("join:switch-teams", L.LOBBY_FAIL_EXIT))
        self.assertEqual(sh.presses, self.JOIN + [CROSS] * L.LOBBY_SWITCH_MAX)
        self.assertEqual(len(teams_lines(sh)), L.LOBBY_SWITCH_MAX + 1)
        self.assertIn("seals=288 terrorists=0", cm.exception.detail)
        self.assertIn("LOBBY class=join:switch-teams", sh.logs)
        self.assertIn("lobby_fail_join_switch-teams", sh.shots)

    def test_c2_lobby_gone_before_the_switch_press_fails_not_presses(self):
        sh, g = FakeShell(), Grabs(*JOIN_FRAMES, lobby(BOTH_SEALS), LOBBY_GONE)
        sh.is_screen = lambda name, thresh=None: name == "game_lobby"
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.join_game(sh, switch=False, refresh=False)
        self.assertEqual(cm.exception.cls, "join:switch-teams")
        self.assertEqual(sh.presses, self.JOIN)

    def test_no_names_read_is_not_a_switch(self):
        # the s6_ladder8 A_16 frame (0, 0) and A_17 (143, 0): the names had not rendered / one name only;
        # nothing is pressed on such a frame, it is re-read
        for frames in ((lobby(cursor=1),), (lobby(HOST_ALONE, cursor=1),)):
            sh = run_join(*frames)
            self.assertEqual(sh.presses, self.JOIN)
            self.assertEqual(len(teams_lines(sh)), L.LOBBY_SWITCH_MAX + 1)
            self.assertTrue(all(m.endswith("-> unread (attempt %d)" % (i + 1)) for i, m in enumerate(teams_lines(sh))), teams_lines(sh))
            self.assertEqual(sh.sleeps.count(L.LOBBY_TEAMS_REREAD_S), L.LOBBY_SWITCH_MAX)
            self.assertTrue(any("teams unread" in m for m in sh.logs), sh.logs)
            self.assertFalse([m for m in sh.logs if "LOBBY-FAIL" in m])

    def test_one_name_then_both_render(self):
        sh = run_join(lobby(HOST_ALONE, cursor=1), lobby(ONE_EACH, cursor=1))
        self.assertEqual(sh.presses, self.JOIN)
        self.assertEqual(teams_lines(sh)[-1], "[lobby] teams: seals=143 terrorists=144 -> ok (attempt 2)")

    def test_same_team_flag_is_superseded(self):
        sh, g = FakeShell(), Grabs(*JOIN_FRAMES, lobby(ONE_EACH, cursor=1))
        sh.is_screen = lambda name, thresh=None: name == "game_lobby"
        with mock.patch.object(L.winshot, "grab", g):
            L.join_game(sh, switch=True, refresh=False)
        self.assertEqual(sh.presses, self.JOIN)                    # no blind SWITCH TEAMS on balanced teams
        self.assertTrue(any("same-team" in m for m in sh.logs), sh.logs)


def run_ready(*frames, role=None):
    sh, g = FakeShell(), Grabs(*frames)
    if role:
        sh.lobby_role = role
    with mock.patch.object(L.winshot, "grab", g):
        L.ready(sh)
    return sh, g


class HostTeamsBeforeReady(unittest.TestCase):
    def test_d_both_on_one_side_fails_host_teams_unbalanced_without_a_press(self):
        sh, g = FakeShell(), Grabs(lobby(BOTH_SEALS, READY_LIT, cursor=2))
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.ready(sh)
        self.assertEqual((cm.exception.cls, cm.exception.code), ("host:teams-unbalanced", L.LOBBY_FAIL_EXIT))
        self.assertEqual(sh.presses, [])
        self.assertIn("seals=288 terrorists=0", cm.exception.detail)
        self.assertIn("LOBBY class=host:teams-unbalanced", sh.logs)
        self.assertIn("lobby_fail_host_teams-unbalanced", sh.shots)
        self.assertEqual(L.Shell.lobby_role, "host")                # the default: only join_game makes a joiner

    def test_d2_joiner_role_names_its_own_class(self):
        sh, g = FakeShell(), Grabs(lobby(BOTH_SEALS, READY_LIT, cursor=2))
        sh.lobby_role = "joiner"
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.ready(sh)
        self.assertEqual(cm.exception.cls, "joiner:teams-unbalanced")

    def test_one_each_readies_up(self):
        sh, _ = run_ready(lobby(ONE_EACH, READY_LIT, cursor=2), lobby(ONE_EACH, "ready_lad9_not_ready_3_lit.png", cursor=2))
        self.assertEqual(sh.presses, [CROSS])
        self.assertIn("[lobby] teams before READY: seals=143 terrorists=144 -> ok", sh.logs)

    def test_no_names_read_still_readies_up(self):
        # no names, or one name (every test_lobby_ready frame reads (143, 0) through its notice crop): not a verdict
        for teams in (None, HOST_ALONE):
            sh, _ = run_ready(lobby(teams, READY_LIT, cursor=2), lobby(teams, "ready_lad9_not_ready_lit.png", cursor=2))
            self.assertEqual(sh.presses, [CROSS])
            self.assertTrue(any(m.endswith("-> unread") for m in sh.logs if "teams before READY" in m), sh.logs)

    def test_teams_are_read_on_the_search_frame_not_an_extra_grab(self):
        sh, g = run_ready(lobby(ONE_EACH, READY_LIT, cursor=2), lobby(ONE_EACH, "ready_lad9_not_ready_3_lit.png", cursor=2))
        self.assertEqual(len(g.ages), 3)                        # cursor read, then the two check frames

    def test_title_gone_at_the_first_read_no_teams_verdict(self):
        sh, _ = run_ready(LOBBY_GONE)
        self.assertEqual(sh.presses, [])
        self.assertFalse([m for m in sh.logs if "teams before READY" in m])


UNREAD = lobby(ONE_EACH, None, cursor=None)                     # GAME LOBBY up, row 2 black: an unread label
READY_FRAME = lobby(ONE_EACH, READY_LIT, cursor=2)
TAKEN_DIM = lobby(ONE_EACH, NOT_READY_34_DIM)                   # s6_ladder9 A_19_ready: no cursor, "NOT READY 34"
TAKEN_LIT = lobby(ONE_EACH, "ready_lad9_not_ready_3_lit.png", cursor=2)


class ReadyCheckReread(unittest.TestCase):
    def test_e_s6_ladder9_dim_label_with_a_count_reads_taken(self):
        # the failing launch's frames: the label read None at luma 110; at 75 it is NOT READY (edge 82)
        sh, _ = run_ready(READY_FRAME, TAKEN_DIM)
        self.assertEqual(sh.presses, [CROSS])
        self.assertIn("READY check: row-2 label right edges [82, 82] (READY ~48, NOT READY ~82)", sh.logs)
        self.assertNotIn("[lobby] game lobby gone during READY check -- no more presses", sh.logs)

    def test_e2_unread_frames_with_the_title_up_are_re_read_then_the_label_decides(self):
        sh, _ = run_ready(READY_FRAME, UNREAD, UNREAD, TAKEN_LIT)
        self.assertEqual(sh.presses, [CROSS])
        self.assertEqual([m for m in sh.logs if m.startswith("READY check: no row-2 label")],
                         [f"READY check: no row-2 label but GAME LOBBY still up -- re-read {k}/{L.READY_REREAD_MAX}" for k in (1, 2)])
        self.assertIn("READY check: row-2 label right edges [82, 82] (READY ~48, NOT READY ~82)", sh.logs)
        self.assertEqual(sh.sleeps.count(L.READY_REREAD_GAP_S), 2)
        self.assertNotIn("[lobby] game lobby gone during READY check -- no more presses", sh.logs)

    def test_e3_re_read_then_still_ready_is_a_dropped_press_and_resent(self):
        sh, _ = run_ready(READY_FRAME, UNREAD, READY_FRAME, READY_FRAME, READY_FRAME, TAKEN_LIT)
        self.assertEqual(sh.presses, [CROSS, PAD_CROSS])
        self.assertIn("LOBBY RESEND ready-dropped attempt=1", sh.logs)

    def test_e4_never_readable_with_the_title_up_fails_without_a_press(self):
        sh, g = FakeShell(), Grabs(READY_FRAME, UNREAD)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.ready(sh)
        self.assertEqual(cm.exception.cls, "ready:label-unread")
        self.assertEqual(sh.presses, [CROSS])
        self.assertEqual(len([m for m in sh.logs if m.startswith("READY check: no row-2 label")]), 2 * L.READY_REREAD_MAX)
        self.assertNotIn("[lobby] game lobby gone during READY check -- no more presses", sh.logs)

    def test_f_title_gone_is_the_gone_branch_without_a_re_read(self):
        for gone in (LOBBY_GONE, BLACK):
            sh, _ = run_ready(READY_FRAME, gone)
            self.assertEqual(sh.presses, [CROSS], gone is BLACK)
            self.assertIn("READY check: row-2 label right edges [None, None] (READY ~48, NOT READY ~82)", sh.logs)
            self.assertIn("[lobby] game lobby gone during READY check -- no more presses", sh.logs)
            self.assertFalse([m for m in sh.logs if m.startswith("READY check: no row-2 label")])
            self.assertNotIn(L.READY_REREAD_GAP_S, sh.sleeps)

    def test_f2_title_gone_during_the_re_reads(self):
        sh, _ = run_ready(READY_FRAME, UNREAD, LOBBY_GONE)
        self.assertEqual(sh.presses, [CROSS])
        self.assertIn("[lobby] game lobby gone during READY check -- no more presses", sh.logs)

    def test_bounds(self):
        self.assertEqual(L.READY_REREAD_MAX, 4)
        self.assertEqual(L.READY_REREAD_GAP_S, 0.5)


if __name__ == "__main__":
    unittest.main()
