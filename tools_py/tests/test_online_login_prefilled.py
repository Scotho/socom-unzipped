"""Sprint 10 Goal 9, Task 6: `--prefilled` -- the harness stops typing on ours.

With the flag, online_login_ours exports PS2X_SOCOM2_LOGIN_NAME / PS2X_SOCOM2_LOGIN_PASS into the game it
launches (the values it would have typed), and at each login keyboard reads the field back and presses ENTER
instead of typing (R180: the runtime prefills, never submits; the harness presses). Without the flag nothing
changes: the typing path runs as before, byte for byte. A name or password the game's keyboard could not hold
(over its MaxChars, 14 / 12 -- research/38; a space, an accent, a `"` in the name) is refused before the launch:
the runtime would cut it and the login would fail 120 s later with no message.

The screen reads are monkeypatched away: the login flow's fakes are test_online_login_lobby's FakeShell and
test_first_login's form frames; the keyboard-level cases feed test_osk_typing's synthesised text rows to the
real Shell.type.
"""
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

from tools_py.parity import online_login_ours as L
from tools_py.parity.online_login import OSK_START
from tools_py.tests import test_first_login as F
from tools_py.tests import test_online_login_lobby as T
from tools_py.tests import test_osk_typing as K

KBD = K.frame((K.REF_NORMAL, K.OSK_ACCENT_BOX))      # the keyboard up, normal mode (the mode read)
GONE = Image.new("RGB", (640, 448), 0)               # after ENTER: the keyboard closed


def typed_open(n):
    """A keyboard frame (normal mode) with n characters in the text row (test_login_connect's)."""
    im = K.synth_typed(n)
    im.paste(Image.open(K.REF_NORMAL).convert("RGB"), K.OSK_ACCENT_BOX[:2])
    return im
ENV_NAME, ENV_PASS = "PS2X_SOCOM2_LOGIN_NAME", "PS2X_SOCOM2_LOGIN_PASS"


class PrefillValues(unittest.TestCase):
    """(d) the caps and the keyboard's character set, refused rather than cut."""

    def test_the_two_variables_carry_the_values_the_harness_would_have_typed(self):
        self.assertEqual(L.prefill_env("socomc", "socom"), {ENV_NAME: "socomc", ENV_PASS: "socom"})

    def test_the_caps_are_the_keyboards_own(self):
        self.assertEqual((L.PREFILL_NAME_CAP, L.PREFILL_PASSWORD_CAP), (14, 12))
        L.prefill_env("a" * 14, "b" * 12)                                   # at the cap: held
        with self.assertRaises(ValueError) as cm:
            L.prefill_env("a" * 15, "socom")
        self.assertIn("15", str(cm.exception))
        self.assertIn("14", str(cm.exception))
        with self.assertRaises(ValueError) as cm:
            L.prefill_env("socomc", "b" * 13)
        self.assertIn("13", str(cm.exception))
        self.assertIn("12", str(cm.exception))

    def test_a_character_the_keyboard_has_not_got_is_refused(self):
        for name in ("so com", "socôm", "so\"com", ""):
            with self.assertRaises(ValueError, msg=repr(name)):
                L.prefill_env(name, "socom")
        for password in ("so com", "", "s\tocom"):
            with self.assertRaises(ValueError, msg=repr(password)):
                L.prefill_env("socomc", password)
        # research/38: the name keyboard refuses `"` (NoDQuote); the password keyboard offers it, and every
        # other printable key (Sgt_Rock, the symbol rows, CAPS) is a key of both
        L.prefill_env("Sgt_Rock", "pa\"ss;/1")
        L.prefill_env("~!@#$%^&*()_+", "`-=[]{}:<>?|")


class LaunchEnvironment(unittest.TestCase):
    """(a) the two variables are in the launched game's environment iff --prefilled."""

    def launch_env(self, prefill):
        with mock.patch.dict(L.os.environ), mock.patch.object(L.subprocess, "Popen") as popen:
            L.os.environ.pop(ENV_NAME, None)
            L.os.environ.pop(ENV_PASS, None)
            L.launch(5, None, prefill)
        return popen.call_args.kwargs["env"]

    def test_with_the_flag_the_game_gets_the_two_variables(self):
        env = self.launch_env(L.prefill_env("socomc", "socom"))
        self.assertEqual((env[ENV_NAME], env[ENV_PASS]), ("socomc", "socom"))
        self.assertEqual(env["PS2X_SOCOM2_PAD"], "1")                        # the rest of the launch as before

    def test_without_it_the_environment_is_what_it_was(self):
        env = self.launch_env(None)
        self.assertNotIn(ENV_NAME, env)
        self.assertNotIn(ENV_PASS, env)
        self.assertEqual(env["PS2X_SOCOM2_PAD"], "1")


class KeyboardEnter(unittest.TestCase):
    """(b)/(c) at the keyboard: Shell.type with `prefilled` reads the field back and walks to ENTER; without it
    the typing path runs as before (posted keys with no pad file, the verified pad typer with one)."""

    def type_prefilled(self, text, *frames, pad_file=None):
        sh = K.FakeShell(pad_file=pad_file)
        sh.osk_open = lambda: True
        with mock.patch.object(L.winshot, "grab", K.Grabs(*frames)), mock.patch.object(L.time, "sleep"), \
                mock.patch.object(L, "osk_type") as posted, \
                mock.patch.object(L.Shell, "osk_type_pad_verified") as pad_typer, \
                mock.patch.object(L.Shell, "osk_type_pad") as pad_walk:
            try:
                sh.type(text, prefilled=True)
            finally:
                posted.assert_not_called()
                pad_typer.assert_not_called()
                pad_walk.assert_not_called()
        return sh

    def test_a_the_field_reads_full_and_enter_is_pressed_from_the_opening_cursor(self):
        # frames: the mode read (keyboard up), the count read (6 already there), the read after ENTER (closed)
        for pad_file in (None, "pad.txt"):
            sh = self.type_prefilled("socomc", KBD, K.synth_typed(6), GONE, pad_file=pad_file)
            self.assertEqual(sh.presses, K.expected("ENTER"), pad_file)          # the walk from OSK_START, one CROSS
            self.assertIn("[osk] prefilled: 6 of 6 in the field -> ENTER", sh.logs)
            self.assertIn("[osk] enter: keyboard closed", sh.logs)
            self.assertFalse([m for m in sh.logs if "LOBBY-FAIL" in m], sh.logs)

    def test_b_a_field_that_is_not_prefilled_fails_with_a_class_and_no_press(self):
        # the exe predates the prefill, or the variable never reached it: typing on top would double the text and
        # ENTER on an empty field puts CONNECT 120 s from a timeout -- stop here, with the count
        for n in (0, 5):
            with self.assertRaises(L.LobbyFail) as cm:
                self.type_prefilled("socomc", KBD, K.synth_typed(n), GONE)
            self.assertEqual(cm.exception.cls, L.CLASS_OSK_PREFILL)
            self.assertEqual(L.CLASS_OSK_PREFILL, "login:prefill-missing")
            self.assertIn(f"{n} of 6", cm.exception.detail)

    def test_c_a_keyboard_still_up_after_enter_is_re_pressed_like_a_typed_one(self):
        # frames: the mode read, the count read, the read after ENTER (still up, 6 in the field), the read after
        # the re-press (closed)
        sh = self.type_prefilled("socomc", KBD, K.synth_typed(6), typed_open(6), GONE)
        self.assertEqual(sh.presses, K.expected("ENTER", "ENTER"))
        self.assertIn("[osk] enter: keyboard still up -> re-press (attempt 1)", sh.logs)

    def test_d_without_the_flag_the_typing_path_is_what_it_was(self):
        sh = K.FakeShell(pad_file=None)
        sh.osk_open = lambda: True
        with mock.patch.object(L, "osk_type") as posted, mock.patch.object(L.winshot, "grab", K.Grabs(KBD)), \
                mock.patch.object(L.time, "sleep"):
            sh.type("socom")
        posted.assert_called_once_with(1, "socom", None, "", target=L.T)
        self.assertEqual(sh.presses, [])
        sh = K.FakeShell()
        sh.osk_open = lambda: True
        with mock.patch.object(L.winshot, "grab", K.Grabs(KBD, K.synth_typed(5), GONE)), mock.patch.object(L.time, "sleep"):
            sh.type("socom")
        self.assertEqual(sh.presses, K.expected(*"socom", "ENTER"))


class LoginFlow(unittest.TestCase):
    """(b)/(c) across the flow: both keyboards of a first login, and the one of a saved persona, get the flag."""

    def run_login(self, form, prefilled, existing=False):
        sh = T.FakeShell()
        sh.press_until_gone = lambda *a, **k: True
        sh.wait_for = lambda *a, **k: True
        stub = mock.patch.multiple(
            L, press_persona=mock.Mock(), press_verified=mock.Mock(),
            press_connect=mock.Mock(), login_prompts=mock.Mock(), login_to_lobby=mock.Mock())
        # a first login: the fresh form, the name keyboard (its title read), then the form with the six glyphs
        # the ENTER committed (create_persona's read-back; the DOWN and CROSS to the password keyboard are the
        # mocked press_verified); a saved persona: the LAN form, PLAYER NAME already "socomc"
        frames = (F.FORM_FRESH, F.KBD_NAME, F.FORM_SAVED) if form is F.FORM_FRESH else (form,)
        with mock.patch.object(L.winshot, "grab", F.Grabs(*frames)), stub, mock.patch.object(L.time, "sleep"):
            L.login(sh, "socomc", "socom", existing, prefilled)
        return sh

    def test_a_prefilled_first_login_presses_enter_on_both_keyboards_and_types_nothing(self):
        sh = self.run_login(F.FORM_FRESH, prefilled=True)
        self.assertEqual(sh.presses, [("enter", "socomc"), ("enter", "socom")])
        self.assertNotIn(("type", "socomc"), sh.presses)
        self.assertNotIn(("type", "socom"), sh.presses)
        self.assertIn("[login] persona: none saved -> creating socomc (prefilled)", sh.logs)

    def test_b_prefilled_saved_persona_presses_enter_on_the_password_keyboard(self):
        sh = self.run_login(F.FORM_SAVED, prefilled=True, existing=True)
        self.assertEqual(sh.presses, [("enter", "socom")])

    def test_c_without_the_flag_both_keyboards_are_typed_as_before(self):
        sh = self.run_login(F.FORM_FRESH, prefilled=False)
        self.assertEqual(sh.presses, [("type", "socomc"), ("type", "socom")])
        self.assertIn("[login] persona: none saved -> creating socomc", sh.logs)
        sh = self.run_login(F.FORM_SAVED, prefilled=False, existing=True)
        self.assertEqual(sh.presses, [("type", "socom")])

    def test_d_the_flag_is_optional_and_off_by_default(self):
        sh = T.FakeShell()
        sh.press_until_gone = lambda *a, **k: True
        sh.wait_for = lambda *a, **k: True
        stub = mock.patch.multiple(L, press_persona=mock.Mock(), press_connect=mock.Mock(),
                                   login_prompts=mock.Mock(), login_to_lobby=mock.Mock())
        with mock.patch.object(L.winshot, "grab", F.Grabs(F.FORM_SAVED)), stub, mock.patch.object(L.time, "sleep"):
            L.login(sh, "socomc", "socom", True)                              # today's four arguments
        self.assertEqual(sh.presses, [("type", "socom")])


class CommandLine(unittest.TestCase):
    """main(): the flag reaches launch (the environment) and login (the presses); a value the keyboard could not
    hold stops the run before the launch."""

    def run_main(self, *argv):
        calls = self.calls = {}
        sh = T.FakeShell()
        out = tempfile.mkdtemp()

        def launch(seconds, instance=None, prefill=None):
            calls["launch"] = (seconds, instance, prefill)
            return mock.Mock(), "SOCOM"

        def login(s, name, password, existing, prefilled=False):
            calls["login"] = (name, password, existing, prefilled)

        with mock.patch.object(sys, "argv", ["online_login_ours", "--out", out, "--hold", "0", *argv]), \
                mock.patch.multiple(L, launch=launch, attach=lambda *a, **k: sh, boot_to_online=mock.Mock(),
                                    login=login), \
                mock.patch.object(L.hostplatform, "process_running", lambda name: False), \
                mock.patch.object(L.hostplatform, "kill_process_by_name", mock.Mock()):
            L.main()
        return calls, sh

    def test_a_prefilled_exports_the_variables_and_presses_enter(self):
        calls, sh = self.run_main("--existing", "--prefilled", "--name", "socomc", "--password", "socom")
        self.assertEqual(calls["launch"], (500, None, {ENV_NAME: "socomc", ENV_PASS: "socom"}))
        self.assertEqual(calls["login"], ("socomc", "socom", True, True))
        self.assertIn("LOBBY class=ok", sh.logs)

    def test_b_without_the_flag_nothing_is_exported_and_the_flow_types(self):
        calls, _ = self.run_main("--existing", "--name", "socomc", "--password", "socom")
        self.assertEqual(calls["launch"], (500, None, None))
        self.assertEqual(calls["login"], ("socomc", "socom", True, False))

    def test_c_a_value_the_keyboard_could_not_hold_stops_before_the_launch(self):
        for argv in (("--name", "a" * 15), ("--password", "b" * 13), ("--name", "so com")):
            with self.assertRaises(SystemExit, msg=argv) as cm:
                self.run_main("--prefilled", *argv)
            self.assertNotEqual(cm.exception.code, 0)
            self.assertNotIn("launch", self.calls)                            # refused before any game starts

    def test_d_the_usage_line_names_the_flag(self):
        self.assertIn("[--prefilled]", L.__doc__)


if __name__ == "__main__":
    unittest.main()
