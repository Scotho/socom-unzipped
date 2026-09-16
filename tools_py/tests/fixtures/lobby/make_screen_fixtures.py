"""Sprint 6 Task 2 (research/28 §4): the reference crops and test fixtures for the verified CREATE GAME /
JOIN GAME presses in tools_py/parity/online_login_ours.py.

Two outputs, both cut from real 640x448 captures under git-ignored logs/parity/:

1. PRODUCTION references -> scripts/parity/refs/lobby/title_<screen>.png: the title band (x 20-360,
   y 18-58) of the four screens the fixed presses move between, cut from launch 8c (the first launch that
   reached gameplay with the R47 checks). `lobby_title_is` compares the live band's text mask against
   these. Measured over every A/B stage capture of the 30 launches in research/28 §1 (128 captures):
   the right screen scores 0.000-0.011, the nearest wrong one 0.385 (CREATE GAME vs CREATE GAME PLAY
   LIST, a prefix pair) and every other pair >= 0.658.

2. TEST fixtures -> this folder: region crops that tools_py/tests/test_online_login_lobby.py pastes back
   into a black 640x448 frame at the same box, so the detectors read the pixels where a live frame has
   them. The screen crops come from a DIFFERENT launch than the references (ladder2) so the tests
   exercise a cross-launch match, and the "wrong screen" crops come from the launch whose failure they
   reproduce (research/28 §3).

Run from the repo root:  python tools_py/tests/fixtures/lobby/make_screen_fixtures.py
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.join("scripts", "parity", "refs", "lobby")

TITLE = (20, 18, 360, 58)          # title band: BRIEFING ROOM / CREATE GAME / CREATE GAME PLAY LIST / GAME LOBBY
ROW_CREATE_GAME = (18, 106, 135, 128)   # briefing room menu row 0 (CREATE GAME); JOIN GAME is (18, 140, 135, 162)
ROW_CHOOSE_GAMES = (18, 386, 170, 406)  # CREATE GAME menu's last row (CHOOSE GAMES)
ROW_GAMES_LIST = (150, 262, 620, 280)   # first row of the briefing room's games list
NOTICE = (150, 152, 490, 265)           # "The READY button will be available in 30 seconds" panel
OSK_ACCENT_BOX = (20, 396, 96, 428)     # the on-screen keyboard's accent-toggle key (Shell.osk_refs)
OSK_TEXT_BAND = (0, 220, 640, 256)      # the keyboard's text row (228..250) with margin: typed glyphs + cursor block (osk_typed_count)

L8C = "logs/parity/s5_t1_launch8c_medley"
LAD2 = "logs/parity/s5_t5_ladder2"

REFERENCES = {
    "title_briefing_room.png": (f"{L8C}/A_11_briefing_room.png", TITLE),
    "title_create_game.png": (f"{L8C}/A_12_create_game.png", TITLE),
    "title_play_list.png": (f"{L8C}/A_14_choose_games.png", TITLE),
    "title_game_lobby.png": (f"{L8C}/A_17_game_lobby_ok.png", TITLE),
}

FIXTURES = {
    # title bands from a launch other than the references' (cross-launch match)
    "title_lad2_briefing_room.png": (f"{LAD2}/A_11_briefing_room.png", TITLE),
    "title_lad2_create_game.png": (f"{LAD2}/A_12_create_game.png", TITLE),
    "title_lad2_play_list.png": (f"{LAD2}/A_14_choose_games.png", TITLE),
    "title_lad2_game_lobby.png": (f"{LAD2}/A_17_game_lobby_ok.png", TITLE),
    # the screens the failed launches were actually on (research/28 §3)
    "title_wtb3_still_briefing.png": (f"logs/parity/ours_task7_wtb3/A_12_create_game.png", TITLE),   # CREATE GAME CROSS eaten
    "title_kill4_still_play_list.png": (f"logs/parity/ours_task8_kill4/A_15_play_list.png", TITLE),  # ACCEPT SQUARE eaten
    "title_kill4_no_lobby.png": (f"logs/parity/ours_task8_kill4/A_17_game_lobby_FAILED.png", TITLE),  # CREATE never made a lobby
    "title_launch1_join_no_lobby.png": (f"logs/parity/s5_t1_launch1/B_17_game_lobby_FAILED.png", TITLE),  # JOIN never entered
    # cursor rows: lit (teal fill, median 62-68) vs unlit (<= 34)
    "row_create_game_lit_wtb3.png": (f"logs/parity/ours_task7_wtb3/A_12_create_game.png", ROW_CREATE_GAME),
    "row_create_game_unlit_lad2.png": (f"{LAD2}/A_11_briefing_room.png", ROW_CREATE_GAME),          # JOIN GAME lit instead
    "row_choose_games_lit_lad2.png": (f"{LAD2}/A_15_play_list.png", ROW_CHOOSE_GAMES),
    "row_choose_games_unlit_wtb3.png": (f"logs/parity/ours_task7_wtb3/A_19_ready.png", ROW_CHOOSE_GAMES),  # RANK RESTRICTIONS lit
    "row_games_list_lit_8c.png": (f"{L8C}/B_12_games_list.png", ROW_GAMES_LIST),
    "row_games_list_none_wtb5.png": (f"logs/parity/ours_task7_wtb5/B_19_ready.png", ROW_GAMES_LIST),   # "There are no games to join."
    # the 30 s READY notice, up and dismissed
    "notice_up_8c.png": (f"{L8C}/A_16_game_lobby.png", NOTICE),
    "notice_gone_8c.png": (f"{L8C}/A_17_game_lobby_ok.png", NOTICE),
    # the game-name keyboard's accent key (cal1 left the keyboard open with "test;p" typed)
    "osk_accent_key_cal1.png": (f"logs/parity/ours_task7_cal1/A_19_ready.png", OSK_ACCENT_BOX),
    # the keyboard's text row (Sprint 6, 2026-09-15 evening; osk_typed_count counts glyph runs): the old harness
    # typed "xmfû" in accent mode (4 glyphs, cols 31..66), cal1 left "test;p" on the game-name keyboard (6, the
    # proportional font: cursor at col 79, not 30 + 6 x 11.3), the pw_kbd captures show the field just opened (0;
    # the old-harness one with its cursor block on at cols 30..34, the s6_ladder2 one with it blinked off), and
    # two per-key captures from the runs where typing worked (3 with the cursor on, 6 with it off)
    "osk_text_xmfu_oldharness.png": ("logs/parity/s6_ladder_oldharness/A_lobby_fail_timeout_login.png", OSK_TEXT_BAND),
    "osk_text_testp_cal1.png": ("logs/parity/ours_task7_cal1/A_19_ready.png", OSK_TEXT_BAND),
    "osk_text_empty_s6_lad2.png": ("logs/parity/s6_ladder2/A_04_pw_kbd.png", OSK_TEXT_BAND),
    "osk_text_empty_s5_lad2.png": (f"{LAD2}/A_04_pw_kbd.png", OSK_TEXT_BAND),
    "osk_text_empty_cursor_oldharness.png": ("logs/parity/s6_ladder_oldharness/A_04_pw_kbd.png", OSK_TEXT_BAND),
    "osk_text_soc_cursor_match.png": ("logs/parity/ours_match/B_name_key2_c.png", OSK_TEXT_BAND),
    "osk_text_socomc_login.png": ("logs/parity/ours_login/name_key5_c.png", OSK_TEXT_BAND),
}

if __name__ == "__main__":
    os.makedirs(REF_DIR, exist_ok=True)
    for dest, table in ((REF_DIR, REFERENCES), (HERE, FIXTURES)):
        for name, (src, box) in table.items():
            im = Image.open(src).convert("L")
            assert im.size == (640, 448), (src, im.size)
            out = os.path.join(dest, name)
            im.crop(box).save(out, optimize=True)
            print(out, os.path.getsize(out), "bytes")
