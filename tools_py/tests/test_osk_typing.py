"""Sprint 6 (2026-09-15 evening, s6_ladder2 / s6_ladder_oldharness): the on-screen keyboard is READ BACK after
typing through the injected pad (research/28 §5 item 4 -- the harness never read what it typed). Both instances
typed the password at ~32 fps and got 'ocom', an empty field and 'xmfû' (accent mode after a lost toggle).

`osk_typed_count` counts the glyph runs in the keyboard's text row (the cursor block blinks and the font is
proportional, so the cursor position is not a count); the pad path of `Shell.type` types WITHOUT the final ENTER,
reads the count back, clears with BCKSPC and retypes at slower pacing (at most 2 retries) and only presses ENTER on
a match; `osk_normal_mode` re-reads the mode after the toggle.

Fixtures are full-width crops of rows 220..256 of real captures (tools_py/tests/fixtures/lobby/), pasted back into
a black 640x448 frame at the same rows, as test_online_login_lobby.py does; the scripted count frames for the
FakeShell runs are synthesised with the measured geometry (7 px glyph blobs, 11.3 px apart, cursor on or off).
"""
import os
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image

from tools_py.parity import online_login_ours as L
from tools_py.parity.online_login import OSK_START, osk_moves, osk_pos

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "lobby")
OSK_TEXT_BAND = (0, 220, 640, 256)
OSK_ACCENT_BOX = (20, 396, 96, 428)
REF_ACCENT = os.path.join("scripts", "parity", "ref_osk_accent.png")
REF_NORMAL = os.path.join("scripts", "parity", "ref_osk_normal.png")


def frame(*parts):
    """A black 640x448 RGB frame with each (image path, box) pasted at its box."""
    im = Image.new("L", (640, 448), 0)
    for path, box in parts:
        im.paste(Image.open(path).convert("L"), box[:2])
    return im.convert("RGB")


def fixture(name):
    return os.path.join(FIX, name)


def synth_typed(n, cursor=True):
    """A text-row frame with n characters typed: n light-grey glyph blobs and, when `cursor`, the white block after
    them (the live block blinks: a read must not depend on it)."""
    a = np.zeros((448, 640), dtype=np.uint8)
    for k in range(n):
        x = 31 + int(round(11.3 * k))
        a[232:246, x:x + 7] = 160
    if n and cursor:
        x = 30 + int(round(11.3 * n))
        a[230:248, x:x + 5] = 255
    return Image.fromarray(a).convert("RGB")


def gray(im):
    return L.lobby_gray_of(im)


def text_row(name):
    return gray(frame((fixture(name), OSK_TEXT_BAND)))


class TypedCount(unittest.TestCase):
    def test_real_captures(self):
        self.assertEqual(L.osk_typed_count(text_row("osk_text_xmfu_oldharness.png")), 4)     # 'xmfû', cursor on
        self.assertEqual(L.osk_typed_count(text_row("osk_text_testp_cal1.png")), 6)          # "test;p": proportional font
        self.assertEqual(L.osk_typed_count(text_row("osk_text_soc_cursor_match.png")), 3)    # cursor on
        self.assertEqual(L.osk_typed_count(text_row("osk_text_socomc_login.png")), 6)        # cursor blinked off
        self.assertEqual(L.osk_typed_count(text_row("osk_text_empty_s6_lad2.png")), 0)       # nothing typed, no cursor
        self.assertEqual(L.osk_typed_count(text_row("osk_text_empty_s5_lad2.png")), 0)
        self.assertEqual(L.osk_typed_count(text_row("osk_text_empty_cursor_oldharness.png")), 0)   # nothing typed, cursor on

    def test_synthesised_counts_with_and_without_the_cursor(self):
        for n in range(0, 9):
            self.assertEqual(L.osk_typed_count(gray(synth_typed(n))), n, n)
            self.assertEqual(L.osk_typed_count(gray(synth_typed(n, cursor=False))), n, n)

    def test_constants(self):
        self.assertEqual(L.OSK_TEXT_ROWS, (228, 250))
        self.assertEqual(L.OSK_TEXT_COLS, (20, 470))
        self.assertEqual((L.OSK_INK_MIN, L.OSK_CURSOR_MIN, L.OSK_GLYPH_MIN_WIDTH), (60, 200, 2))


class FakeShell(L.Shell):
    """A Shell without the reference images: records logs and pad presses with their pacing."""

    def __init__(self, pad_file="pad.txt"):          # deliberately skips Shell.__init__
        self.hwnd, self.out, self.t0, self.tag, self.pad_file = 1, tempfile.gettempdir(), 0.0, "A_", pad_file
        self.logs, self.presses, self.paced, self.shots = [], [], [], []

    def log(self, m):
        self.logs.append(m)

    def press(self, b, wait=1.0):
        self.check_stage()
        self.presses.append(("key", b))

    def pad_press(self, b, wait=0.35, hold_s=0.09):
        self.check_stage()
        self.presses.append(("pad", b))
        self.paced.append((b, hold_s, wait))

    def shot(self, label, max_age=None):
        self.shots.append(label)


class Grabs:
    """winshot.grab stand-in: hands out frames in order (the last repeats) and records max_age."""

    def __init__(self, *frames):
        self.frames, self.ages = list(frames), []

    def __call__(self, hwnd, max_age=None):
        self.ages.append(max_age)
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]


def walk(cur, label):
    """The pad presses of one key: the d-pad walk from cur to the key, then CROSS. Returns (presses, new cur)."""
    dst = osk_pos(label)
    return [("pad", m.upper()) for m in osk_moves(cur, dst)] + [("pad", "CROSS")], dst


def expected(*legs):
    """Press list for a sequence of key labels typed from OSK_START, dead-reckoned like the harness."""
    cur, out = OSK_START, []
    for label in legs:
        p, cur = walk(cur, label)
        out += p
    return out


def run_typed(text, *frames):
    sh, g = FakeShell(), Grabs(*frames)
    with mock.patch.object(L.winshot, "grab", g):
        sh.osk_type_pad_verified(text)
    return sh, g


class PadTypingVerified(unittest.TestCase):
    def test_first_attempt_matches_one_enter_no_backspace(self):
        sh, g = run_typed("socom", synth_typed(5))
        self.assertEqual(sh.presses, expected(*"socom", "ENTER"))
        self.assertNotIn(("pad", "BCKSPC"), sh.presses)
        self.assertEqual(sh.presses.count(("pad", "CROSS")), 6)
        self.assertEqual([m for m in sh.logs if m.startswith("[osk]")], ["[osk] typed 5 of 5 (attempt 1)"])
        self.assertTrue(all(a is not None and a <= L.LOBBY_FRAME_MAX_AGE_S for a in g.ages), g.ages)
        # normal pacing on the first attempt
        self.assertTrue(all(h == 0.09 for _, h, _ in sh.paced), sh.paced)

    def test_one_lost_character_is_cleared_and_retyped_slowly(self):
        sh, g = run_typed("socom", synth_typed(4), synth_typed(0), synth_typed(5, cursor=False))
        typed1 = expected(*"socom")                       # attempt 1 (dead-reckoned, ends on 'm')
        clear, cur = walk(osk_pos("m"), "BCKSPC")         # walk to BCKSPC, first press
        clear += [("pad", "CROSS")] * 3                   # 4 presses in all: one per counted character
        retype, cur2 = [], osk_pos("BCKSPC")
        for ch in "socom":
            p, cur2 = walk(cur2, ch)
            retype += p
        enter, _ = walk(cur2, "ENTER")
        self.assertEqual(sh.presses, typed1 + clear + retype + enter)
        self.assertEqual(sh.presses.count(("pad", "CROSS")), 5 + 4 + 5 + 1)
        self.assertEqual([m for m in sh.logs if m.startswith("[osk]")],
                         ["[osk] typed 4 of 5 -> retype (attempt 1)",
                          "[osk] cleared: 0 of 5 left",
                          "[osk] typed 5 of 5 (attempt 2)"])
        # the retype (and the ENTER) run at the slow pacing; attempt 1 at the normal one
        n1 = len(typed1)
        self.assertTrue(all(h == 0.09 and w in (0.35, 0.6) for _, h, w in sh.paced[:n1]), sh.paced[:n1])
        slow = sh.paced[n1:]                              # clear, retype and ENTER
        self.assertTrue(all(h == L.OSK_SLOW_HOLD_S and w == (L.OSK_CROSS_WAIT_S if b == "CROSS" else L.OSK_SLOW_WAIT_S)
                            for b, h, w in slow), slow)
        self.assertEqual((L.OSK_SLOW_HOLD_S, L.OSK_SLOW_WAIT_S), (0.18, 0.5))

    def test_three_failures_is_a_classified_failure_with_no_enter(self):
        sh = FakeShell()
        with mock.patch.object(L.winshot, "grab", Grabs(synth_typed(4), synth_typed(0), synth_typed(3), synth_typed(0),
                                                        synth_typed(2))), \
                self.assertRaises(L.LobbyFail) as cm:
            sh.osk_type_pad_verified("socom")
        self.assertEqual(cm.exception.cls, "login:keyboard-typing")
        self.assertEqual(cm.exception.detail, "2 of 5 characters after 3 attempts")
        self.assertEqual(L.CLASS_OSK_TYPING, "login:keyboard-typing")
        self.assertIn("LOBBY class=login:keyboard-typing", sh.logs)
        self.assertEqual(sh.shots, ["lobby_fail_login_keyboard-typing"])
        # ENTER was never walked to: the last key pressed is a character of the third attempt ('m'), not ENTER
        self.assertEqual(sh.presses.count(("pad", "CROSS")), 5 + 4 + 5 + 3 + 5)     # three types, two clears, no ENTER
        self.assertEqual([m for m in sh.logs if m.startswith("[osk] typed")],
                         ["[osk] typed 4 of 5 -> retype (attempt 1)",
                          "[osk] typed 3 of 5 -> retype (attempt 2)",
                          "[osk] typed 2 of 5 (attempt 3)"])
        self.assertEqual(L.OSK_TYPE_ATTEMPTS, 3)

    def test_clear_that_leaves_characters_backspaces_again(self):
        # 4 typed; the first clear leaves 1 (a BCKSPC press dropped), the second clear empties it; then a good retype
        sh, g = run_typed("socom", synth_typed(4), synth_typed(1), synth_typed(0), synth_typed(5))
        self.assertEqual(sh.presses.count(("pad", "CROSS")), 5 + 4 + 1 + 5 + 1)
        self.assertEqual([m for m in sh.logs if m.startswith("[osk] cleared")],
                         ["[osk] cleared: 1 of 5 left -> 1 more BCKSPC", "[osk] cleared: 0 of 5 left"])

    def test_type_routes_the_pad_path_through_the_verified_typer(self):
        kbd = frame((REF_NORMAL, OSK_ACCENT_BOX))
        sh = FakeShell()
        sh.osk_open = lambda: True
        with mock.patch.object(L.winshot, "grab", Grabs(kbd, synth_typed(5), kbd)), mock.patch.object(L.time, "sleep"):
            sh.type("socom")
        self.assertEqual(sh.presses, expected(*"socom", "ENTER"))
        self.assertTrue(any(m.startswith("WARNING: the on-screen keyboard is still up") for m in sh.logs))

    def test_posted_keys_path_is_unchanged(self):
        sh = FakeShell(pad_file=None)
        sh.osk_open = lambda: True
        with mock.patch.object(L, "osk_type") as ot, mock.patch.object(L.winshot, "grab", Grabs(frame((REF_NORMAL, OSK_ACCENT_BOX)))), \
                mock.patch.object(L.time, "sleep"):
            sh.type("socom")
        ot.assert_called_once_with(1, "socom", None, "", target=L.T)
        self.assertEqual(sh.presses, [])


class NormalMode(unittest.TestCase):
    ACCENT = frame((REF_ACCENT, OSK_ACCENT_BOX))
    NORMAL = frame((REF_NORMAL, OSK_ACCENT_BOX))

    def test_already_normal_no_press(self):
        sh = FakeShell()
        with mock.patch.object(L.winshot, "grab", Grabs(self.NORMAL)):
            sh.osk_normal_mode()
        self.assertEqual(sh.presses, [])
        self.assertEqual(sh.logs, ["[osk] mode normal (0.0 vs 6.3)"])

    def test_accent_toggles_once_when_the_re_read_is_normal(self):
        sh = FakeShell()
        with mock.patch.object(L.winshot, "grab", Grabs(self.ACCENT, self.NORMAL)):
            sh.osk_normal_mode()
        self.assertEqual(sh.presses, [("pad", "CROSS")])
        self.assertEqual(sh.logs, ["[osk] mode accent (6.3 vs 0.0) -> toggling", "[osk] mode normal (0.0 vs 6.3)"])

    def test_accent_still_accent_toggles_again(self):
        sh = FakeShell()
        g = Grabs(self.ACCENT, self.ACCENT, self.NORMAL)
        with mock.patch.object(L.winshot, "grab", g):
            sh.osk_normal_mode()
        self.assertEqual(sh.presses, [("pad", "CROSS"), ("pad", "CROSS")])
        self.assertEqual(sh.logs, ["[osk] mode accent (6.3 vs 0.0) -> toggling",
                                   "[osk] mode accent (6.3 vs 0.0) -> toggling again",
                                   "[osk] mode normal (0.0 vs 6.3)"])
        self.assertEqual(g.ages[1:], [L.LOBBY_FRAME_MAX_AGE_S, L.LOBBY_FRAME_MAX_AGE_S])   # re-reads are fresh frames

    def test_stuck_in_accent_after_two_toggles_is_logged(self):
        sh = FakeShell()
        with mock.patch.object(L.winshot, "grab", Grabs(self.ACCENT)):
            sh.osk_normal_mode()
        self.assertEqual(sh.presses, [("pad", "CROSS"), ("pad", "CROSS")])
        self.assertEqual(sh.logs[-1], "[osk] mode accent (6.3 vs 0.0) after 2 toggles -- typing anyway")

    def test_posted_keys_toggle(self):
        sh = FakeShell(pad_file=None)
        with mock.patch.object(L.winshot, "grab", Grabs(self.ACCENT, self.NORMAL)):
            sh.osk_normal_mode()
        self.assertEqual(sh.presses, [("key", "cross")])


if __name__ == "__main__":
    unittest.main()
