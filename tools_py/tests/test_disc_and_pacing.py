"""Sprint 8 Task 10 follow-up: the explicit disc path, and the reference-paced untilref presses.

Two harness items the VM's marginal title stage asked for, both Python, both tested on both
platforms from this Windows host:

(a) `hostplatform.iso_path()` -- one resolver for the disc image, exported to the launched game as
    PS2X_CD_IMAGE so the runtime's own directory scan (`configureCdImage`) stops being a second,
    different answer. A run with no disc fails at the launch, naming the three places it looked,
    instead of booting black (two VM title runs did exactly that).

(b) `drive.paced_press_times()` -- untilref's press budget as wall-clock time rather than a count
    of 12. `press_pacing()` is the branch: Windows keeps the fixed count (the daily instrument),
    everything else -- and Windows with SOCOM_DRIVE_SLOW_HOST=1, which is how these tests reach it
    here -- takes the paced loop.
"""
import itertools
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from tools_py.parity import drive
from tools_py.parity import hostplatform as hp

WIN, LIN = "Windows", "Linux"


class IsoPath(unittest.TestCase):
    """The three resolution orders, against real files in a temp tree and a fake environment."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.repo_iso = os.path.join(self.root, "game", hp.ISO_NAME)
        os.makedirs(os.path.dirname(self.repo_iso))
        self.env_iso = os.path.join(self.root, "elsewhere.iso")
        self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def touch(path):
        with open(path, "wb") as f:
            f.write(b"\0")

    def test_socom_iso_wins_when_it_is_set_and_exists(self):
        self.touch(self.env_iso)
        self.touch(self.repo_iso)
        for system in (WIN, LIN):
            self.assertEqual(hp.iso_path({"SOCOM_ISO": self.env_iso}, self.root, system),
                             os.path.abspath(self.env_iso))

    def test_a_set_but_missing_socom_iso_falls_through_to_the_repo(self):
        self.touch(self.repo_iso)
        self.assertEqual(hp.iso_path({"SOCOM_ISO": os.path.join(self.root, "gone.iso")},
                                     self.root, LIN),
                         os.path.abspath(self.repo_iso))

    def test_the_repo_disc_is_the_default(self):
        self.touch(self.repo_iso)
        for system in (WIN, LIN):
            self.assertEqual(hp.iso_path({}, self.root, system), os.path.abspath(self.repo_iso))

    def fake_home(self):
        """A home directory holding a socom2.iso, the way the VM's does (vm_sync.sh iso puts it
        there and the synced tree carries no image under game/ -- vm_sync excludes *.iso)."""
        home = os.path.join(self.root, "home")
        os.makedirs(home, exist_ok=True)
        self.touch(os.path.join(home, "socom2.iso"))
        return mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}), home

    def test_the_home_image_is_the_linux_fallback(self):
        patch, home = self.fake_home()
        with patch:
            self.assertEqual(hp.iso_path({}, self.root, LIN),
                             os.path.abspath(os.path.join(home, "socom2.iso")))

    def test_windows_does_not_take_the_home_image_even_when_it_is_there(self):
        # The platform switch: a stray ~/socom2.iso must never become the disc the daily Windows
        # gate drives.
        patch, _home = self.fake_home()
        with patch, self.assertRaises(FileNotFoundError):
            hp.iso_path({}, self.root, WIN)

    def test_the_repo_disc_beats_the_home_image(self):
        patch, _home = self.fake_home()
        self.touch(self.repo_iso)
        with patch:
            self.assertEqual(hp.iso_path({}, self.root, LIN), os.path.abspath(self.repo_iso))

    def test_windows_never_consults_the_home_image(self):
        names = {where: consulted for where, _p, consulted in hp.iso_candidates({}, self.root, WIN)}
        self.assertFalse(names[hp.LINUX_HOME_ISO])
        self.assertTrue({where: c for where, _p, c in
                         hp.iso_candidates({}, self.root, LIN)}[hp.LINUX_HOME_ISO])

    def test_the_order_is_env_then_repo_then_home(self):
        self.assertEqual([where for where, _p, _c in hp.iso_candidates({}, self.root, LIN)],
                         ["SOCOM_ISO", "the repo's game/", hp.LINUX_HOME_ISO])

    def empty_home(self):
        """A home directory with no disc in it. Without this the case trusted the machine: in the
        socom-linux VM `~/socom2.iso` is real (vm_sync.sh iso puts it there), the resolver found it and
        nothing was raised. A "nothing found" test must point every place it names at an empty tree."""
        home = os.path.join(self.root, "emptyhome")
        os.makedirs(home, exist_ok=True)
        return mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home})

    def test_no_disc_anywhere_raises_naming_all_three_places(self):
        # all three places are empty here: SOCOM_ISO unset, the repo's game/ empty (setUp makes the
        # directory and no image), and a home with nothing in it.
        with self.empty_home():
            with self.assertRaises(FileNotFoundError) as cm:
                hp.iso_path({}, self.root, LIN)
            text = str(cm.exception)
            self.assertIn(os.path.expanduser(hp.LINUX_HOME_ISO), text)
        self.assertIn("SOCOM_ISO", text)
        self.assertIn("not set", text)                 # unset is said, not silently skipped
        self.assertIn(self.repo_iso, text)

    def test_the_error_still_names_the_home_image_on_windows(self):
        with self.assertRaises(FileNotFoundError) as cm:
            hp.iso_path({"SOCOM_ISO": os.path.join(self.root, "gone.iso")}, self.root, WIN)
        text = str(cm.exception)
        self.assertIn("gone.iso", text)
        self.assertIn(self.repo_iso, text)
        self.assertIn("socom2.iso", text)
        self.assertIn("Linux only", text)

    def test_this_host_resolves_its_own_disc(self):
        # Not a fixture: the repo Windows drives every day. Its answer must be the file the
        # runtime's scan would find, i.e. the one image under game/.
        try:
            found = hp.iso_path()
        except FileNotFoundError:
            self.skipTest("no disc image on this host")
        self.assertEqual(found, os.path.abspath(os.path.join(hp.ROOT, "game", hp.ISO_NAME)))


class CdImageExport(unittest.TestCase):
    """The export rule: every platform, and only when the variable is not already set."""

    def test_exported_when_unset(self):
        env = drive.cd_image_env({"PS2X_SOCOM2_PAD": "1"}, resolve=lambda: "/discs/socom2.iso")
        self.assertEqual(env["PS2X_CD_IMAGE"], "/discs/socom2.iso")
        self.assertEqual(env["PS2X_SOCOM2_PAD"], "1")

    def test_an_operators_own_value_is_left_alone_and_no_disc_is_needed(self):
        def boom():
            raise AssertionError("the resolver must not even be called")

        env = drive.cd_image_env({"PS2X_CD_IMAGE": "/discs/other.iso"}, resolve=boom)
        self.assertEqual(env["PS2X_CD_IMAGE"], "/discs/other.iso")

    def test_an_empty_value_counts_as_unset(self):
        env = drive.cd_image_env({"PS2X_CD_IMAGE": ""}, resolve=lambda: "/discs/socom2.iso")
        self.assertEqual(env["PS2X_CD_IMAGE"], "/discs/socom2.iso")

    def test_a_missing_disc_is_raised_at_the_launch(self):
        def missing():
            raise FileNotFoundError("no SOCOM II disc image; looked at: ...")

        with self.assertRaises(FileNotFoundError):
            drive.cd_image_env({}, resolve=missing)


class PressPacingBranch(unittest.TestCase):
    def test_windows_keeps_the_fixed_count(self):
        self.assertEqual(drive.press_pacing({}, WIN), "fixed-count")

    def test_off_windows_is_paced(self):
        self.assertEqual(drive.press_pacing({}, LIN), "paced")

    def test_slow_host_asks_for_paced_on_windows_too(self):
        self.assertEqual(drive.press_pacing({"SOCOM_DRIVE_SLOW_HOST": "1"}, WIN), "paced")

    def test_any_other_value_is_not_the_opt_in(self):
        self.assertEqual(drive.press_pacing({"SOCOM_DRIVE_SLOW_HOST": "0"}, WIN), "fixed-count")

    def test_this_host_takes_the_old_path_by_default(self):
        # The gate on this Windows host must be the same instrument it was yesterday.
        self.assertEqual(drive.press_pacing({}), "fixed-count" if os.name == "nt" else "paced")


class UntilrefBudget(unittest.TestCase):
    TITLE = [("untilref(ref.png)", 1.0, ["CROSS"])] + [("wait", 6.0, [])] * 22

    def test_the_rest_of_the_script_keeps_its_time(self):
        # The VM's title stage: 170 s x 3 (gate.stage_seconds), 8 s tail, 22 x 6 s of waits.
        self.assertEqual(drive.untilref_budget(510, 8, self.TITLE, 0), 510 - 8 - 132)

    def test_a_last_step_may_spend_what_is_left(self):
        self.assertEqual(drive.untilref_budget(170, 8, self.TITLE[:1], 0), 162)

    def test_never_negative(self):
        self.assertEqual(drive.untilref_budget(10, 8, self.TITLE, 0), 0.0)


class PacedPressTimes(unittest.TestCase):
    """The paced loop as a pure function over (t, distance-to-previous, distance-to-reference)."""

    @staticmethod
    def presses_for(observations, **kw):
        pressed = []
        result = drive.paced_press_times(observations, pressed.append, **kw)
        return pressed, result

    @staticmethod
    def transition(start, seconds, d_ref=99.0, step=1.0):
        """A screen in motion: every capture far from the one before it."""
        t = start
        while t < start + seconds:
            yield (t, 50.0, d_ref)
            t += step

    def test_a_slow_transition_is_pressed_once_not_once_per_tick(self):
        # Eight seconds of unstable frames after each press, then a settled screen. The old
        # fixed-count loop paced by wall time alone would press on every one of those ticks.
        obs = []
        t = 0.0
        for _ in range(3):
            obs.append((t, 0.2, 99.0))                       # settled, still not the reference
            t += 1.0
            obs += list(self.transition(t, 8.0))             # the press lands: the screen moves
            t += 8.0
        pressed, result = self.presses_for(obs, per_press_timeout=12.0, wall_budget=100.0)
        self.assertEqual(pressed, [0.0, 9.0, 18.0])
        self.assertFalse(result.matched)

    def test_a_press_is_not_repeated_on_the_frame_right_after_it(self):
        # The overshoot: the capture that follows a press is still the old, settled screen --
        # the game has not reacted yet. Pressing on it is how the VM walked through the menu.
        obs = [(0.0, 0.2, 99.0), (1.0, 0.2, 99.0), (2.0, 0.2, 99.0)]
        pressed, _ = self.presses_for(obs, per_press_timeout=12.0, wall_budget=100.0)
        self.assertEqual(pressed, [0.0])

    def test_a_settled_screen_that_swallows_the_press_is_asked_once_more_then_left_alone(self):
        # s8_vm_title_paced1: 120 s of one settled boot screen, 15 presses, and the last of them was
        # latched through the load and spent on the main menu (SELECT RANK at s01). A screen that
        # does not react is a guest that is loading, not a screen that needs pressing harder.
        obs = [(float(t), 0.2, 99.0) for t in range(0, 121)]
        pressed, result = self.presses_for(obs, per_press_timeout=12.0, wall_budget=400.0)
        self.assertEqual(pressed, [0.0, 36.0])           # the settle, and one backstop at 3x
        self.assertFalse(result.matched)

    def test_the_backstop_limit_is_per_screen_not_per_run(self):
        # ... but a screen that DOES move has earned its press again.
        obs = ([(float(t), 0.2, 99.0) for t in range(0, 40)]
               + [(40.0, 50.0, 99.0)]                    # the screen changes
               + [(float(t), 0.2, 99.0) for t in range(41, 90)])
        pressed, _ = self.presses_for(obs, per_press_timeout=12.0, wall_budget=400.0)
        self.assertEqual(pressed, [0.0, 36.0, 41.0, 77.0])

    def test_the_backstop_waits_three_timeouts(self):
        obs = [(float(t), 0.2, 99.0) for t in range(0, 40)]
        pressed, _ = self.presses_for(obs, per_press_timeout=4.0, idle_timeout=20.0,
                                      wall_budget=400.0)
        self.assertEqual(pressed, [0.0, 20.0])

    def test_a_reference_match_stops_immediately(self):
        obs = [(0.0, 0.2, 99.0)] + list(self.transition(1.0, 5.0)) + [(6.0, 0.2, 3.0),
                                                                     (7.0, 0.2, 3.0)]
        pressed, result = self.presses_for(obs, ref_dist=14.0, per_press_timeout=12.0, wall_budget=100.0)
        self.assertTrue(result.matched)
        self.assertEqual(pressed, [0.0])                     # no press on the matching screen

    def test_a_black_screen_that_never_settles_is_pressed_on_the_timeout(self):
        # The VM's 119 s boot: the loading screen never holds still, so only the per-press timeout
        # carries the loop. The budget is time, so the presses reach the far side of the boot.
        obs = list(self.transition(0.0, 120.0))
        pressed, result = self.presses_for(obs, per_press_timeout=12.0, wall_budget=400.0)
        # The first press waits too: the boot screen never holds still, so the timeout is the only
        # clock. Ten presses in the old count were spent in the first 30 s; these span the boot.
        self.assertEqual(pressed, [12.0, 24.0, 36.0, 48.0, 60.0, 72.0, 84.0, 96.0, 108.0])
        self.assertFalse(result.matched)

    def test_the_wall_budget_ends_the_loop(self):
        pressed, result = self.presses_for(self.transition(0.0, 10000.0),  # infinite-ish
                                   per_press_timeout=12.0, wall_budget=30.0)
        self.assertFalse(result.matched)
        self.assertLessEqual(max(pressed), 30.0)
        self.assertEqual(pressed, [12.0, 24.0])

    def test_the_budget_is_counted_from_the_first_observation_not_from_zero(self):
        pressed, result = self.presses_for(self.transition(1000.0, 10000.0),
                                   per_press_timeout=12.0, wall_budget=30.0)
        self.assertEqual(pressed, [1012.0, 1024.0])
        self.assertFalse(result.matched)

    def test_a_reference_already_on_screen_presses_nothing(self):
        pressed, result = self.presses_for([(0.0, float("inf"), 1.0)], wall_budget=100.0)
        self.assertEqual(pressed, [])
        self.assertTrue(result.matched)

    def test_an_exhausted_observation_stream_ends_the_loop_unmatched(self):
        pressed, result = self.presses_for([(0.0, 0.2, 99.0)], wall_budget=100.0)
        self.assertEqual(pressed, [0.0])
        self.assertFalse(result.matched)


class RefObservations(unittest.TestCase):
    """The live feed the paced loop consumes, with a fake clock and fake captures."""

    def test_distances_and_cadence(self):
        frames = [(np.zeros((4, 4), dtype=np.float32), float("inf")),
                  (np.zeros((4, 4), dtype=np.float32), float("inf")),
                  (np.full((4, 4), 10.0, dtype=np.float32), 3.0)]
        clock = [100.0]
        slept = []

        def sample():
            return frames.pop(0)

        def sleep(s):
            slept.append(s)
            clock[0] += s

        # The feed is endless by design (the loop, not the feed, decides when to stop).
        got = list(itertools.islice(
            drive.ref_observations(sample, poll_s=2.0, now=lambda: clock[0], sleep=sleep), 3))
        self.assertEqual([t for t, _d, _r in got], [100.0, 102.0, 104.0])
        self.assertEqual(got[0][1], float("inf"))            # no predecessor
        self.assertEqual(got[1][1], 0.0)                     # identical capture: stable
        self.assertEqual(got[2][1], 10.0)                    # the screen moved
        self.assertEqual([r for _t, _d, r in got], [float("inf"), float("inf"), 3.0])
        self.assertEqual(slept, [2.0, 2.0])   # islice stops at the third yield


if __name__ == "__main__":
    unittest.main()
