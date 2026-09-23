"""Fix wave W10 (2026-09-22): the game's own remember-password, proven on a virgin card in two launches.

R237 said the prefilled login leaves the player path because the supported way in is a persona saved on the card
with SAVE PASSWORD ticked. The reason to doubt that path was the owner's failed save, which was the `..` refusal
fixed the same night (152579a) -- so W10 is re-decided on a proof, not executed: launch one creates the persona
with SAVE PASSWORD = YES (`--save-password`), launch two must log in with nothing typed (`--saved-password`).
Only if the second passes does the prefill leave the player path.

Here: the two pure readers over a 640x448 grey frame (the SAVE PASSWORD tick, the PASSWORD field's glyphs), the
tick-setting step and the two login branches, on test_first_login's synthesised forms and the FakeShell. The one
test on a real capture (logs/parity/blop_c) is skipped when it is not on disk.
"""
import os
import unittest
from unittest import mock

import numpy as np
from PIL import Image

from tools_py.parity import online_login_ours as L
from tools_py.tests import test_first_login as F
from tools_py.tests import test_online_login_lobby as T

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOP_FORM = os.path.join(ROOT, "logs", "parity", "blop_c", "02_persona.png")
BLOP_CONNECT = os.path.join(ROOT, "logs", "parity", "blop_c", "06_connect_focus.png")

ROW_SAVE = (20, 166, 160, 188)
PASSWORD_VALUE = (172, 136, 400, 158)


def tick(im, box, luma=100):
    """The frame with a tick drawn inside one SAVE PASSWORD box: a filled block at the measured tick level."""
    y0, y1, x0, x1 = box
    out = im.copy()
    out.paste(Image.new("RGB", (x1 - x0 - 4, y1 - y0 - 4), (luma, luma, luma)), (x0 + 2, y0 + 2))
    return out


def with_password(im):
    """The form with a 6-glyph value in the PASSWORD strip (the PLAYER NAME fixture, one row down)."""
    out = im.copy()
    out.paste(im.crop(F.NAME_VALUE), PASSWORD_VALUE)
    return out


def lit_row(im, row_box):
    """The form with `row_box` lit and PASSWORD unlit: the lit-fill fixture moved down a row."""
    out = im.copy()
    out.paste(im.crop(F.ROW_PASSWORD), row_box)
    out.paste(im.crop(F.ROW_PLAYER_NAME), F.ROW_PASSWORD)       # the unlit fixture in the row it came from
    return out


FORM_NO = tick(F.FORM_SAVED, L.LOGIN_SAVE_NO_BOX)
FORM_YES = tick(F.FORM_SAVED, L.LOGIN_SAVE_YES_BOX)
FORM_NEITHER = F.FORM_SAVED
FORM_SAVE_ROW_NO = tick(lit_row(F.FORM_SAVED, ROW_SAVE), L.LOGIN_SAVE_NO_BOX)
FORM_SAVE_ROW_YES = tick(lit_row(F.FORM_SAVED, ROW_SAVE), L.LOGIN_SAVE_YES_BOX)
KEY = lambda b: ("key", b)


class TheReaders(unittest.TestCase):
    def test_the_tick_is_read_from_the_box_it_is_in(self):
        self.assertEqual(L.login_save_password(F.gray(FORM_NO)), "no")
        self.assertEqual(L.login_save_password(F.gray(FORM_YES)), "yes")
        self.assertIsNone(L.login_save_password(F.gray(FORM_NEITHER)))
        self.assertIsNone(L.login_save_password(F.gray(tick(FORM_NO, L.LOGIN_SAVE_YES_BOX))))   # both: not a form

    def test_the_password_strip_reads_its_glyphs(self):
        self.assertEqual(L.login_password_glyphs(F.gray(F.FORM_SAVED)), 0)
        self.assertEqual(L.login_password_glyphs(F.gray(with_password(F.FORM_SAVED))), 6)

    def test_the_boxes_sit_inside_the_outlines_and_apart_from_the_labels(self):
        # YES outline x 176-192 / label from 202; NO outline x 240-254 / label from 268 (the measured columns)
        _y0, _y1, x0, x1 = L.LOGIN_SAVE_YES_BOX
        self.assertTrue(176 < x0 and x1 < 192)
        _y0, _y1, x0, x1 = L.LOGIN_SAVE_NO_BOX
        self.assertTrue(240 < x0 and x1 < 254)

    @unittest.skipUnless(os.path.exists(BLOP_FORM), "the blop_c capture is not on disk")
    def test_the_real_form_reads_no_and_its_password_reads_five_asterisks(self):
        g = L.lobby_gray_of(Image.open(BLOP_FORM))
        self.assertEqual(L.login_save_password(g), "no")
        self.assertEqual(L.login_password_glyphs(g), 0)           # 02_persona: "Enter your password." -- empty
        g = L.lobby_gray_of(Image.open(BLOP_CONNECT))
        self.assertEqual(L.login_save_password(g), "no")
        self.assertEqual(L.login_password_glyphs(g), 5)           # 06_connect_focus: "*****"


class SettingTheTick(unittest.TestCase):
    def run_set(self, *frames):
        sh, g = T.FakeShell(), F.Grabs(*frames)
        with mock.patch.object(L.winshot, "grab", g):
            L.set_save_password(sh)
        return sh

    def test_left_moves_the_tick_to_yes(self):
        sh = self.run_set(FORM_SAVE_ROW_NO, FORM_SAVE_ROW_NO, FORM_SAVE_ROW_YES)
        self.assertEqual(sh.presses, [KEY("down"), KEY("left")])
        self.assertIn("[login] save password: reads yes after left", sh.logs)
        self.assertEqual(sh.shots, ["05_save_password"])

    def test_cross_is_tried_when_left_did_nothing(self):
        sh = self.run_set(FORM_SAVE_ROW_NO, FORM_SAVE_ROW_NO, FORM_SAVE_ROW_NO, FORM_SAVE_ROW_YES)
        self.assertEqual(sh.presses, [KEY("down"), KEY("left"), KEY("cross")])

    def test_already_yes_presses_nothing_more(self):
        sh = self.run_set(FORM_SAVE_ROW_YES, FORM_SAVE_ROW_YES)
        self.assertEqual(sh.presses, [KEY("down")])

    def test_a_tick_that_never_moves_fails_with_a_class(self):
        sh, g = T.FakeShell(), F.Grabs(FORM_SAVE_ROW_NO)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.set_save_password(sh)
        self.assertEqual(cm.exception.cls, "login:save-password:tick")
        self.assertEqual(sh.presses, [KEY("down"), KEY("left"), KEY("cross")])

    def test_the_row_never_lit_fails_before_any_toggle(self):
        sh, g = T.FakeShell(), F.Grabs(F.FORM_PASSWORD_LIT)
        with mock.patch.object(L.winshot, "grab", g), self.assertRaises(L.LobbyFail) as cm:
            L.set_save_password(sh)
        self.assertEqual(cm.exception.cls, "login:save-password:row")
        self.assertNotIn(KEY("left"), sh.presses)


class TheTwoLaunches(unittest.TestCase):
    """login() with the two flags, the stage functions stubbed as test_first_login.LoginBranch stubs them."""

    def setUp(self):
        self.calls = []

    def run_login(self, form, **flags):
        sh, g = T.FakeShell(), F.Grabs(form)
        stub = mock.patch.multiple(
            L, create_persona=mock.Mock(side_effect=lambda s, n, li, pf=False: (self.calls.append(("create", n)))),
            press_persona=mock.Mock(side_effect=lambda s, e, li: self.calls.append(("persona", e))),
            press_persona_list=mock.Mock(side_effect=lambda s: s.presses.append(("key", "cross"))),
            set_save_password=mock.Mock(side_effect=lambda s: self.calls.append(("save",))),
            press_connect=mock.Mock(side_effect=lambda s, downs=L.LOGIN_CONNECT_DOWNS: self.calls.append(("connect", downs))),
            login_prompts=mock.Mock(side_effect=lambda s: self.calls.append(("prompts",))),
            login_to_lobby=mock.Mock(side_effect=lambda s: self.calls.append(("lobby",))))
        with mock.patch.object(L.winshot, "grab", g), stub, \
                mock.patch.object(T.FakeShell, "press_until_gone", lambda *a, **k: True), \
                mock.patch.object(T.FakeShell, "wait_for", lambda *a, **k: True):
            L.login(sh, "w10test", "socom", False, **flags)
        return sh

    def test_launch_one_creates_ticks_yes_and_walks_one_down_fewer(self):
        sh = self.run_login(F.FORM_FRESH, save_password=True)
        self.assertEqual(self.calls, [("create", "w10test"), ("save",), ("connect", 3), ("prompts",), ("lobby",)])
        self.assertIn(("type", "socom"), sh.presses)

    def test_without_the_flag_nothing_changes(self):
        sh = self.run_login(F.FORM_FRESH)
        self.assertEqual(self.calls, [("create", "w10test"), ("connect", 4), ("prompts",), ("lobby",)])

    def test_launch_two_types_nothing_when_the_card_brought_the_password(self):
        sh = self.run_login(with_password(FORM_YES), saved_password=True)
        self.assertEqual(self.calls, [("connect", 4), ("prompts",), ("lobby",)])
        self.assertNotIn(("type", "socom"), sh.presses)
        self.assertIn("[login] saved password: PASSWORD reads 6 glyphs, SAVE PASSWORD reads yes; typing nothing", sh.logs)
        self.assertEqual(sh.presses, [("key", "cross")])            # the persona-list CROSS only

    def test_launch_two_fails_on_an_empty_password_field(self):
        with self.assertRaises(L.LobbyFail) as cm:
            self.run_login(FORM_NO, saved_password=True)
        self.assertEqual(cm.exception.cls, "login:saved-password:empty")
        self.assertIn("reads no", cm.exception.detail)
        self.assertEqual(self.calls, [])

    def test_launch_two_fails_when_the_persona_itself_is_gone(self):
        with self.assertRaises(L.LobbyFail) as cm:
            self.run_login(F.FORM_FRESH, saved_password=True)
        self.assertEqual(cm.exception.cls, "login:saved-password:no-persona")
        self.assertEqual(self.calls, [])


class TheCardFolder(unittest.TestCase):
    def test_mc_dir_reaches_the_game_as_an_absolute_path_and_exists(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "virgin", "mc0")
            seen = {}

            def fake_popen(args, env=None, **kw):
                seen["env"] = env
                return mock.Mock()
            with mock.patch.object(L.subprocess, "Popen", fake_popen):
                L.launch(10, None, None, target)
            self.assertEqual(seen["env"]["PS2X_MC_DIR"], os.path.abspath(target))
            self.assertTrue(os.path.isdir(target))

    def test_the_two_flags_are_refused_together(self):
        import subprocess
        import sys
        p = subprocess.run([sys.executable, "-m", "tools_py.parity.online_login_ours", "--save-password", "--saved-password"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("two launches of one proof", p.stderr)


if __name__ == "__main__":
    unittest.main()
