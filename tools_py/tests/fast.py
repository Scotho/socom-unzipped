"""The fast subset of the Python suite: `python -m tools_py.tests.fast` (Sprint 13 H7, harness audit #36).

The whole suite (`python -m unittest discover -s tools_py/tests -t .`, which `./build.sh test` runs first) takes about
eleven minutes on the Windows host, and a python whose command line says `unittest` is on scripts/loop_lock.sh's busy
list, so every full run holds up builds and gates machine-wide. This is the part that needs nothing the lock guards:

  - no case here needs a build product (dist/, dist-release/, dist-linux/, the launcher, the .NET server) or the disc
    (game/: the images, the card, the capsule, the ISO) -- EXCLUDED's second block names every case that does, by
    module, class or method;
  - no module here was measured slow: EXCLUDED's first block is every module that took 10 s or more on its own
    (2026-09-25, the Windows host; the bash-, git- and process-driving suites, together about 95% of its time).

Everything else runs, whatever it is -- a new test file is in the fast subset until it is measured slow or needs a
product, so the subset cannot silently shrink to nothing. `tools_py/tests/test_fast_subset.py` holds EXCLUDED to the
tree (every entry names something that exists) and pins the command line off the lock's busy list.

The full suite stays what it was and is still the bar before a commit that touches an excluded area; this is the
check to run while the lock is held by somebody else. `-v` for the verbose runner, `--list` to print the modules.
Measured: see docs/DEVELOPING.md (the testing section).
"""
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE = "tools_py.tests"

# Dotted names under tools_py.tests: a module, a module.Class or a module.Class.method.
EXCLUDED = {
    # -- measured slow: 10 s or more on its own, the Windows host, 2026-09-25 (the whole suite one module at a time in
    #    one process, 1578 s under load). test_gate (12.5 s there, 7.8 s alone) stays in: its scorers are the gate's.
    "test_story_cite": "309 s; resolves every citation in docs/STORY.md against git",
    "test_build_revision": "264 s; drives scripts/build_revision.sh through bash (and the r0001 image when present)",
    "test_story_timeline": "134 s; resolves the timeline's commits",
    "test_loop_lock": "111 s with the slow half skipped; real lock takes, waits and process lists",
    "test_aim_loop": "110 s; two cases run the aim loop's wall-clock schedule",
    "test_mission_music_fast": "69 s; the mission-music pipeline over generated audio",
    "test_make_portable": "57 s; builds a portable folder through bash and PowerShell",
    "test_closeout_launch": "44 s; launches and kills stand-in games through bash",
    "test_leakcheck": "40 s; scans the repository and its history",
    "test_python_resolution": "37 s; drives every script under a shimmed PATH",
    "test_online_instruments": "34 s; the online harness's scripts through bash",
    "test_ladder_template": "32 s; renders and dry-runs the ladder scripts through bash",
    "test_audio_capture_script": "31 s; runs the capture script through bash with stand-in tools",
    "test_rung0_launch": "30 s; dry-runs the rung-0 launch scripts",
    "test_gate_pins": "28 s; replays archived stamps through the gate's scorers",
    "test_bootstrap_windows": "23 s; runs scripts/bootstrap_windows.sh against a local archive server",
    "test_pin_harness": "23 s; the pin harness through git and bash (and dist/socom2.exe when present)",
    "test_make_portable_linux": "20 s; packages a Linux folder through bash (a built launcher when present)",
    "test_capture_env": "19 s; spawns the capture environment scripts",
    "test_build_linux": "18 s; drives scripts/build_linux.sh's argument and test paths through bash",
    "test_horizon_ctl": "18 s; drives server/linux/horizon-ctl.sh through bash",
    "test_parity_env": "16 s; sources scripts/parity/env.sh in bash",
    "test_gate_accept_pins": "14 s; replays the acceptance pins",
    "test_run_sh_exe": "11 s; run.sh through bash with a stand-in exe",
    "test_server_public_ip": "11 s; the server scripts through PowerShell",
    # -- needs a build product or the disc (they skip without one, and run for real on a machine that has it) --
    "test_data_via_twin": "the two game images and game/r0004/match.json",
    "test_decrypt_card_package.RealCardPackageTest": "game/r0004/card/APACHE00.ZDB",
    "test_diagnostics_zip": "the launcher build",
    "test_disc_and_pacing": "the disc image under game/",
    "test_find_ctor_thunks": "the game images",
    "test_gate.MissionSeeing.test_mission_stage_launches_with_the_probe_peek_spec": "the pristine card save under game/",
    "test_knobs_line": "the runner build (dist/socom2.exe)",
    "test_launcher_bug_report": "the launcher build",
    "test_make_server_zip": "the .NET server build",
    "test_motion_pack_check": "the disc file and the RDRAM dumps",
    "test_music_state_poll.TestDef.test_the_real_disc": "game/disc/RUN/SOUNDS/VAGSTORE.ZAR",
    "test_overlay_repair": "the r0001 image and the r0004 stack",
    "test_pine": "game/disc/socom2_game.elf and a live PCSX2",
    "test_portable_audit": "dist/socom2.exe",
    "test_portable_folder": "a portable folder (scripts/make_portable.sh)",
    "test_r0004_capsule.RealCapsuleTest": "the r0004 capsule",
    "test_runner_exit_codes": "the runner build",
    "test_third_party_notices": "dist-release/",
}


def modules():
    return sorted(f[:-3] for f in os.listdir(HERE) if f.startswith("test_") and f.endswith(".py"))


def _excluded(test_id):
    rel = test_id[len(PACKAGE) + 1:] if test_id.startswith(PACKAGE + ".") else test_id
    return any(rel == e or rel.startswith(e + ".") for e in EXCLUDED)


def _flatten(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from _flatten(t)
        else:
            yield t


def suite():
    loader = unittest.TestLoader()
    keep = unittest.TestSuite()
    for name in modules():
        if name in EXCLUDED:
            continue
        for t in _flatten(loader.loadTestsFromName("%s.%s" % (PACKAGE, name))):
            if not _excluded(t.id()):
                keep.addTest(t)
    return keep


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--list" in argv:
        for name in modules():
            print(("-  " if name in EXCLUDED else "   ") + name)
        return 0
    t0 = time.perf_counter()
    s = suite()
    result = unittest.TextTestRunner(verbosity=2 if "-v" in argv else 1).run(s)
    print("fast subset: %d tests in %.1f s (%d modules or cases excluded; python -m unittest discover -s "
          "tools_py/tests -t . runs them all)" % (result.testsRun, time.perf_counter() - t0, len(EXCLUDED)))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
