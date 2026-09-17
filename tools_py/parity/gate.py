"""One command for the three screenshot gates. PASS/FAIL per gate, exit 1 on any FAIL.

  python -m tools_py.parity.gate                     # all three (title ~3 min, transition ~3 min, mission ~11 min)
  python -m tools_py.parity.gate --only title,mission
  python -m tools_py.parity.gate --score-title logs/parity/runs/vr_title     # re-score, no game run
  python -m tools_py.parity.gate --score-mission logs/parity/drive_gameplay_probe5.txt

Runs go to logs/parity/gate/<stamp>/<gate>/ with the drive log beside them and a summary.txt.
Must be run from the repo root (drive.py uses relative paths). Takes scripts/loop_lock.sh.

Refuses to start (exit 3) when C: has less than RUN_MIN_FREE_GB (default 4) free -- Sprint 5 R46/A5:
a launch or a gate run must not be the thing that fills a drive already near capacity. `free_gb()` is
the injectable seam for tests (mock.patch.object(gate, "free_gb", ...)); RUN_FREE_GB_CMD overrides the
query itself with a shell command whose last stdout line is the free space in GB, the same override
scripts/run_detached.sh honours for its own disk refusal. `--score-title`/`--score-mission` (re-score
an existing run, no game launch, nothing large written) are exempt.
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import time

import numpy as np
from PIL import Image

from tools_py.parity import black_rows, compare, console_compare, drive, guest_probe, mission_fail, screen_bands

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_MIN_FREE_GB = 4.0


def free_gb(drive_path="C:\\"):
    """Free space on `drive_path`, in GiB. RUN_FREE_GB_CMD, if set, overrides the query with a shell
    command whose last stdout line is the figure (used by tests, and shared with
    scripts/run_detached.sh's own override of the same name); otherwise shutil.disk_usage. Tests
    normally patch this function directly rather than going through RUN_FREE_GB_CMD."""
    cmd = os.environ.get("RUN_FREE_GB_CMD")
    if cmd:
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True).stdout
        return float(out.strip().splitlines()[-1])
    return shutil.disk_usage(drive_path).free / (1024.0 ** 3)


TITLE_REF = os.path.join("scripts", "parity", "ref_main_menu_ours.png")
# Calibrated 2026-09-10 on the four stored clean title runs (vr_title, rt_title, gl_title,
# xg_title): the 19 menu captures s00..s18 score 93.2..99.4 against the reference, s19 is the
# fade into the attract movie (83.7..85.1) and s20..s22 are the movie itself (49.5..67.8).
# Every clean run scores exactly 19/23 >= 90.0, so 90.0 sits ~3 points under the menu band and
# ~5 points over the fade, and 16 leaves three captures of headroom. A mission run scored as a
# title run gives 1/36 (negative control, logs/parity/runs/gameplay_probe5).
TITLE_MIN_SCORE = 90.0      # compare.score of a capture vs the main-menu reference
TITLE_MIN_MATCHES = 16      # of the 23 captures s00..s22 (19 are at the menu on a clean run, then the attract movie)
HUD_REF_NAME = "ref_hud_ours.png"
MISSION_MIN_HOLDS = 3       # sNN_hold* steps after the HUD: fewer means the probe died on entry
# ... and of their captures (sNN_hold*.png), at least this many must be gameplay by the letterbox-band test
# (screen_bands.gameplay_band). R30, 2026-09-13: from 2026-09-12 14:33 every mission run "reached the HUD"
# with 0 presses on the letterboxed intro cinematic and held W/R1/L/S over it -- s5_task4_dbuff's six hold
# captures are all the cinematic -- and this scorer, which read only the drive log, passed them. Sprint 3's
# s3a (4 presses) has 6/6 gameplay holds, famb 6/6, s3d_2x_host 5/6 (its rejected hold, s36, is a black
# frame); s3b3 2/6 (it held over the "TO ABORT" flyover) FAILs, correctly. False-positive class: the band
# test only says "not the letterbox" -- s3d_2x_host's MISSION FAILURE statistics holds (s38, s40) and dim
# near-black fades (famb s34) read as gameplay.
MISSION_MIN_GAMEPLAY_HOLDS = 3
# Liveness (R34): gameplay on screen is not a live game. s5_gatefix and mission4 passed the band test on
# every hold while the runtime had nearly stopped presenting (latest_frame.png exports after the first
# [guest-fault] line: s5_gatefix 43, mission4 36, native_on 61, against s3a 1393, famb 1529); their holds
# are pixel-identical, so W/R1/L/S never reached a running game. A "live pair" is two consecutive hold
# captures that are both gameplay and differ by a mean absolute RGB difference >= MISSION_LIVE_PAIR_DIFF.
# Measured on the full-size captures (review of 69e2a9d, re-derived here): qualifying pairs s3a 4
# (3.67-22.9), famb 4, native_on 3, s3d_2x_host 2 -> PASS; mission4 1 (3.82), s5_gatefix 0 (max 1.60)
# -> FAIL. Static pairs in live runs read 0.00-0.03 (the player stands still after the last hold), so 3.0
# sits well above a frozen frame and at the bottom of real motion.
MISSION_LIVE_PAIR_DIFF = 3.0
MISSION_MIN_LIVE_PAIRS = 2
# Sprint 6 Task 1 (owner-agreed 2026-09-14): three scorers that look at what the liveness checks cannot.
# 1a mission_fail.detect over every hold capture and final.png FAILS the stage: s5_head_1x_b's holds were
#    gameplay and live while s38/s40/final were the MISSION FAILURE statistics screen.
# 1b console_compare on the spawn capture (mission_spawn_capture) is PRINTED into the detail and does not
#    change the verdict -- R78: the water shards are a known, owned defect, and a gate that fails on them
#    every run teaches nothing; the numbers are on every summary so their trend is visible. It flips to
#    failing in the same commit as the water fix (Task 5a).
# 1c guest_probe over the game's run log (mission_game_log) is SCORED since R80 (2026-09-15): s6_probe on the
#    block-pointer exe read the root node at the console's 5.5039, MoveScale 1.0 and 0 teleports, so a value
#    outside its tolerance fails the stage. NO-DATA fails only a stage the gate launched itself.
GUEST_PROBE_CONSOLE = os.path.join("scripts", "parity", "guest_probe_console.json")
PRISTINE_CARD = os.path.join("game", "disc", "mc0_parity")   # the 2026-09-08 card: no controller config saved, so the boot shows the configuration screens and the save dialog
# What this floor counts: black-screen frames AT OR AFTER the probe script's first `burst` step
# (first_burst_step() below -> black_rows.py --from-step), i.e. frames of the black screen
# between the controller-configuration screens and the mission briefing. It deliberately does not
# count the rest of the run: a boot supplies ten or more black frames of its own before the probe
# has left the memory-card screens, and counting those makes the gate green on a run that never
# reached the briefing at all.
#
# That is not hypothetical -- it is what this gate did between `wcap1` (2026-09-11) and this fix.
# The controller-configuration "save to memory card?" dialog started appearing on boot;
# gameplay_probe.txt guards it with ifref pairs and transition_probe.txt did not, so the probe
# stalled on the dialog. Every run since examined 0 frames at/after its burst step and passed on
# boot black screens alone: wcap1 10 frames / 0 after, wcap2 13 / 0, famb 11 / 0, famc 10 / 0,
# hostdraw_on 11 / 0, hostdraw_fix 9 / 0. Runs from before the dialog did measure the transition
# (gate/first 6 / 5, gate/native_on 4 / 4, runs/gl_transition 8 / 7), which is why the floor of 5
# looked calibrated. All of the stalled runs FAIL under the scorer as it now stands; that is the
# honest record, not a regression.
#
# The same defect came back on 2026-09-12 in its other half. The guards were there, but the burst
# was pinned to step 11 (right after the FIRST guard pair) while the dialog can land on a later
# pair: logs/parity/gate/s4_mb matched it at steps 13/14, so the burst fired on a controller-
# configuration screen and the only frames left of the actual fade were four 1 Hz wait captures --
# FAIL, "4 black-screen frames examined, need 5", three runs running. The burst is now `ifburst`
# (drive.py): one after every guard pair, and only the pair that answered the dialog fires its
# own. score_transition reads the step back off the captures the run wrote (observed_burst_step),
# so the scored frames are the frames after the NO press wherever that press landed. Only bursts at
# a step the script marks `ifburst` count: the probe also ends with an unconditional burst on the
# settled briefing, and a run that answered no dialog but still reached that burst would otherwise
# have it read as "the transition" and pass quietly on it (found in review, 2026-09-12).
#
# transition_probe.txt carries those guards and puts its burst on the NO press, so the fade is
# captured at 5 fps. Calibrated 2026-09-11 on two consecutive clean runs of the fixed probe:
# logs/parity/gate/tfix3 examined 18 frames at/after the burst step and tfix4 17, every frame
# peak 0. Both clear 5 by more than 3x, so the floor stays 5: under it, a run either did not reach
# the fade or lost its captures. black_rows.py exits 0 when it examines nothing, so the exit code
# alone is a vacuous pass and the count is part of the verdict.
# Recalibrated 2026-09-17 (research/34 section 6): with the guest clock on wall time the black screen before
# the briefing lasts about 4 s (s6_clock_gate: 4 wait captures at 1 Hz, all peak 0) where the two-thirds-speed
# clock gave 14 (s6_clutfix_gate). Three keeps the vacuous-pass guard (a stalled run examines 0 or 1).
TRANSITION_MIN_FRAMES = 3

GATES = {
    "title": dict(script="scripts/parity/title_menu.txt", seconds=170, tail=8),
    "transition": dict(script="scripts/parity/transition_probe.txt", seconds=170, tail=8, wait_period=0.2),
    "mission": dict(script="scripts/parity/gameplay_probe.txt", seconds=480, tail=170),
}


def _score_value(golden, ours):
    """compare.score (compare.py:19) takes two PIL images and returns
    {"score": .., "mad": .., "block": ..}; it may also be a float or a (score, mad, block)
    tuple. Open the paths and normalise the result to a float."""
    with Image.open(golden) as g, Image.open(ours) as o:
        r = compare.score(g, o)
    if isinstance(r, dict):
        return float(r["score"])
    return float(r[0] if isinstance(r, (tuple, list)) else r)


def score_title(run_dir):
    caps = sorted(p for p in glob.glob(os.path.join(run_dir, "s[0-9][0-9]_*.png"))
                  if "burst" not in os.path.basename(p))
    if not caps:
        return False, "no captures in %s" % run_dir
    scores = [(os.path.basename(p), _score_value(TITLE_REF, p)) for p in caps]
    good = sum(1 for _, s in scores if s >= TITLE_MIN_SCORE)
    detail = "%d/%d menu captures >= %.1f; scores: %s" % (
        good, len(scores), TITLE_MIN_SCORE, " ".join("%s=%.1f" % (n[:3], s) for n, s in scores))
    return good >= TITLE_MIN_MATCHES, detail


BURST_CAPTURE_RE = re.compile(r"^s(\d+)_burst_")
# The content-scored transition (s6_fade, 2026-09-16). When no ifburst fired -- a saved controller configuration
# on the card, or a boot that showed no configuration screens -- the fade to black happens during the rank
# press's own settle wait, at a step index that drifts with the number of boot screens (s05 in s6_fade, s07
# nominal), so no step-pinned burst catches it. fade_frames finds the FIRST capture whose header band matches
# the briefing reference (rows 6..18, cols 0..80 of the 160x112 thumbnail: "MISSION BRIEFING"; measured 0.0 on
# every briefing frame of s6_fade/s6_gamepad3, 25.4+ on every other screen, 11.9 on the half-drawn fade-in
# frame), skips the briefing's own fade-in (non-black frames within FADE_IN_MAX_S before it) and counts the
# contiguous black-screen run behind that. The boot's black screens sit behind the main menu, a non-black
# frame, so they can never join the run -- the property the burst step was enforcing.
BRIEFING_REF = os.path.join("scripts", "parity", "ref_briefing_ours.png")
BRIEFING_BAND = (6, 18, 0, 80)
BRIEFING_THRESH = 8.0
FADE_IN_MAX_S = 2.0
CAPTURE_RE = re.compile(r"^[sw]\d+_.*\.png$")


def _script_step_modes(script_path=None):
    """The head mode of every step of a drive.py step script, in drive.parse order.

    drive.py numbers steps by their position among the non-blank, non-comment lines of the script
    and names each capture `s<NN>_*` / `w<NN>_*` after that index, so the list index here is the
    step index there."""
    path = script_path or os.path.join(ROOT, GATES["transition"]["script"])
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    modes = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            modes.append(line.split("+", 1)[0].split(":", 1)[0].strip())
    return modes


def first_burst_step(script_path=None):
    """Index of the first `burst`/`ifburst` step of a drive.py step script, or None.

    In transition_probe.txt the first burst-family step is the one that starts on the "save to
    memory card?" NO press, which is what takes the game to the black screen before the briefing.
    This is the *static* answer -- where the earliest burst could fire. The probe's transition
    bursts are `ifburst` (they fire only behind the guard pair that actually answered the dialog),
    so the answer for a given run is observed_burst_step(); this one is used by
    make_gate_fixtures.py to check that a candidate fixture frame is one the gate would examine."""
    for step, mode in enumerate(_script_step_modes(script_path)):
        if mode in ("burst", "ifburst"):
            return step
    return None


def conditional_burst_steps(script_path=None):
    """The step indices a script marks `ifburst`, i.e. the ones that can only fire on a matched
    "save to memory card?" guard pair -- the transition bursts, and nothing else.

    This set is what keeps the probe's TRAILING unconditional `burst` (the settled briefing, step
    22) from being mistaken for a transition. Without it, a run that answered no dialog at all but
    still reached the briefing would have `s22_burst_*` as its only burst captures, observed_burst
    _step would report 22, and the scorer would count whatever is at the end of the run and call it
    the transition -- a quiet pass if that region happened to read black. Found in review,
    2026-09-12; it is the same failure class this whole enforcement exists to remove."""
    return {step for step, mode in enumerate(_script_step_modes(script_path)) if mode == "ifburst"}


def observed_burst_step(run_dir, script_path=None):
    """Step index of the first *transition* burst that actually fired in a captured run, or None.

    drive.py writes a burst's frames as `s<NN>_burst_<k>.png`, so the run directory records where
    the burst happened even though the step script only says where it *may* happen. The transition
    probe's transition bursts are conditional on the guard pair matching (drive.py `ifburst`), and
    that dialog moves with how many controller-configuration screens the boot shows -- 2026-09-12
    it landed on steps 13/14 instead of 9/10, which put the old fixed burst on a screen that was
    not the transition and left the scorer four 1 Hz wait frames to count (logs/parity/gate/s4_mb).
    Reading the index back off the captures is what makes the scored frames "the frames after the
    NO press" wherever that press landed.

    Only bursts at a step the script marks `ifburst` count (conditional_burst_steps). A script that
    marks none -- an older probe whose bursts are all unconditional -- falls back to every burst it
    finds, which is what such a run means. `None` means no transition burst fired: score_transition
    FAILs on that outright rather than picking some other window."""
    conditional = conditional_burst_steps(script_path)
    steps = []
    try:
        names = os.listdir(run_dir)
    except OSError:
        return None
    for name in names:
        m = BURST_CAPTURE_RE.match(name)
        if m and (not conditional or int(m.group(1)) in conditional):
            steps.append(int(m.group(1)))
    return min(steps) if steps else None


def briefing_dist(path, ref=None):
    r0, r1, c0, c1 = BRIEFING_BAND
    if ref is None:
        ref = drive.thumb(Image.open(BRIEFING_REF))
    t = drive.thumb(Image.open(path))
    return float(np.abs(t[r0:r1, c0:c1] - ref[r0:r1, c0:c1]).mean())


def fade_frames(run_dir):
    """([(name, band_peak), ...] in capture order, first_briefing_name): the black-screen run immediately before
    the first briefing frame of the run, capture order by file mtime (step names drift; capture time does not).
    ([], None) when no capture matches the briefing."""
    try:
        names = [n for n in os.listdir(run_dir) if CAPTURE_RE.match(n)]
    except OSError:
        return [], None
    paths = sorted((os.path.join(run_dir, n) for n in names), key=lambda p: (os.path.getmtime(p), p))
    ref = drive.thumb(Image.open(BRIEFING_REF))
    first = next((k for k, p in enumerate(paths) if briefing_dist(p, ref) <= BRIEFING_THRESH), None)
    if first is None:
        return [], None
    t_first = os.path.getmtime(paths[first])
    k = first - 1
    # The briefing fades in from black: step back over its non-black frames, but only within FADE_IN_MAX_S.
    while k >= 0 and t_first - os.path.getmtime(paths[k]) <= FADE_IN_MAX_S and not black_rows.examine(paths[k])[0]:
        k -= 1
    run = []
    while k >= 0:
        black, peak = black_rows.examine(paths[k])
        if not black:
            break
        run.append((os.path.basename(paths[k]), peak))
        k -= 1
    return run[::-1], os.path.basename(paths[first])


def score_transition(run_dir, script_path=None):
    """black_rows.py prints one "<file>  black screen, rows <y0>-<y1>: peak <n>" line per frame it
    actually examines and exits 1 only when one of them is not black. Zero examined frames also
    exits 0, so the count is part of the verdict, not just the exit code.

    Only frames at or after the run's transition burst are examined (--from-step): those are the
    transition, everything before them is the boot. The step is taken from the captures the run
    actually wrote (observed_burst_step), so a probe whose dialog landed late is still scored from
    its NO press. A run that fired no transition burst never saw the dialog (a saved controller
    configuration on the card, s6_gamepad..s6_fade 2026-09-16): its fade happened during the rank
    press's own settle wait at a drifting step index, so it is scored by CONTENT instead
    (score_fade: the black run immediately before the first briefing frame). There is deliberately
    no fallback to a step index: that would let the run's other black frames -- the boot's, or the
    trailing briefing burst's -- stand in for a fade that was never captured."""
    burst = observed_burst_step(run_dir, script_path)
    if burst is None:
        return score_fade(run_dir)
    scope = " at/after the burst step (s%02d, fired)" % burst
    cmd = [sys.executable, "tools_py/parity/black_rows.py", run_dir, "--from-step", str(burst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    examined = [ln for ln in r.stdout.splitlines() if "black screen, rows " in ln]
    bad = [ln for ln in examined if "NOT BLACK" in ln]
    peaks = [int(m.group(1)) for m in (re.search(r"peak\s+(\d+)", ln) for ln in examined) if m]
    # One check, not two: "examined nothing" and "examined fewer than the floor" are the same
    # condition -- a separate `if not examined` above this was unreachable.
    if len(examined) < TRANSITION_MIN_FRAMES:
        return False, ("transition not captured (%d black-screen frames examined%s, need %d)"
                       " in %s" % (len(examined), scope, TRANSITION_MIN_FRAMES, run_dir))
    if bad or r.returncode != 0:
        return False, "%d black-screen frames examined%s; non-black band: %s" % (
            len(examined), scope,
            "; ".join(" ".join(ln.split()) for ln in bad[:5]) or r.stderr.strip()[:200])
    return True, "%d black-screen frames examined%s, rows 396-447 peak %d" % (
        len(examined), scope, max(peaks, default=0))


def score_fade(run_dir):
    """The content-scored transition for a run that fired no ifburst (see fade_frames)."""
    run, first = fade_frames(run_dir)
    if first is None:
        return False, ("transition not captured (0 black-screen frames examined: no transition burst fired and "
                       "no briefing frame was captured, so nothing marks where the fade ends) in %s" % run_dir)
    scope = " before the first briefing frame (%s)" % first
    if len(run) < TRANSITION_MIN_FRAMES:
        return False, ("transition not captured (%d black-screen frames examined%s, need %d) in %s"
                       % (len(run), scope, TRANSITION_MIN_FRAMES, run_dir))
    bad = [(n, p) for n, p in run if p > 8]
    if bad:
        return False, "%d black-screen frames examined%s; non-black band: %s" % (
            len(run), scope, "; ".join("%s rows 396-447 peak %d <-- NOT BLACK" % b for b in bad[:5]))
    return True, "%d black-screen frames examined%s, rows 396-447 peak %d" % (
        len(run), scope, max((p for _, p in run), default=0))


def drive_command(name, out_dir):
    """drive.py's command line for a stage; the transition stage captures its settle waits at 5 fps."""
    cfg = GATES[name]
    cmd = [sys.executable, "-m", "tools_py.parity.drive", "--target", "ours",
           "--script", cfg["script"], "--out", out_dir,
           "--seconds", str(cfg["seconds"]), "--tail", str(cfg["tail"])]
    if cfg.get("wait_period"):
        cmd += ["--wait-period", str(cfg["wait_period"])]
    return cmd


def mission_run_dir(drive_log):
    """run_gate writes <root>/mission.drive.log beside <root>/mission/; anything else has no known captures."""
    suffix = ".drive.log"
    if drive_log.endswith(suffix):
        d = drive_log[:-len(suffix)]
        if os.path.isdir(d):
            return d
    return None


def mission_game_log(drive_log):
    """run_gate copies the game's own run log (the newest logs/run_*.log, where the runtime prints its
    [peek] rows) to <root>/mission.game.log beside <root>/mission.drive.log; None when there is none."""
    suffix = ".drive.log"
    if drive_log.endswith(suffix):
        p = drive_log[:-len(suffix)] + ".game.log"
        if os.path.isfile(p):
            return p
    return None


def mission_spawn_capture(drive_log, run_dir):
    """The spawn-view capture the console reference was taken at: the first `s<NN>_none` step the drive
    log records after the HUD untilref matched (s28 in gameplay_probe.txt: the untilref step itself,
    captured once the HUD is on screen, before the 2 s wait and the first hold). Read off the log rather
    than pinned to 28 so the step moving in the script does not silently score a different frame. None
    when the log names no such step or its capture is missing."""
    try:
        with open(drive_log, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    hud = re.compile(r"untilref\([^)]*%s[^)]*\):.*matched=True" % re.escape(HUD_REF_NAME))
    seen_hud = False
    for line in lines:
        if not seen_hud:
            seen_hud = bool(hud.search(line))
            continue
        m = re.match(r"^(s\d\d_none)\b", line)
        if m:
            p = os.path.join(run_dir, m.group(1) + ".png")
            return p if os.path.isfile(p) else None
    return None


def console_spawn_line(drive_log, run_dir):
    """`CONSOLE spawn score=<s> water flat=<f> dark=<d> -> PASS|FAIL` for the spawn capture, or
    `CONSOLE spawn NO-DATA`. Print-only (R78)."""
    cap = mission_spawn_capture(drive_log, run_dir)
    if cap is None:
        return "CONSOLE spawn NO-DATA (no s??_none capture after the HUD match)"
    # s6_gamepad5 (2026-09-16): the capture after the HUD match was the letterboxed location cinematic (gameplay
    # band 0.56; HUD frames read 0.92) and the water statistics scored it flat=0.071 -- a figure no HUD frame has
    # ever produced. A frame that is not a HUD frame is NO-DATA, never a verdict.
    try:
        with Image.open(cap) as im:
            is_hud, band = screen_bands.gameplay_band(im.convert("RGB"))
    except OSError as e:
        return "CONSOLE spawn NO-DATA (%s: %s)" % (os.path.basename(cap), e)
    if not is_hud:
        return "CONSOLE spawn NO-DATA (%s is not a HUD frame: gameplay band %.2f < %.2f)" % (
            os.path.basename(cap), band, screen_bands.GAMEPLAY_MIN)
    try:
        s = console_compare.score(cap)
        ok, _ = console_compare.water_verdict(cap)
        st = console_compare.water_stats(cap)
    except (OSError, ValueError) as e:
        return "CONSOLE spawn NO-DATA (%s: %s)" % (os.path.basename(cap), e)
    return "CONSOLE spawn score=%.1f water flat=%.3f dark=%.3f -> %s (%s vs %s)" % (
        s, st["flat"], st["dark"], "PASS" if ok else "FAIL", os.path.basename(cap), console_compare.CONSOLE_REF)


def probe_lines(run_log):
    """One `PROBE <name> PASS|FAIL <detail>` per guest_probe result over the game's run log, or a single
    `PROBE NO-DATA` when there is no log to read. Print-only (R78)."""
    if not run_log or not os.path.isfile(run_log):
        return ["PROBE NO-DATA (no game run log beside the drive log)"]
    try:
        results = guest_probe.evaluate(run_log, GUEST_PROBE_CONSOLE)
    except (OSError, ValueError, KeyError) as e:
        return ["PROBE NO-DATA (%s)" % e]
    return ["PROBE %s %s %s" % (r.name, "PASS" if r.ok else "FAIL", r.detail) for r in results]


def score_mission_log(drive_log, run_dir=None, run_log=None, probe_required=False):
    """HUD matched in the drive log, >= MISSION_MIN_HOLDS hold steps, one capture per logged hold,
    >= MISSION_MIN_GAMEPLAY_HOLDS of the hold captures gameplay, and >= MISSION_MIN_LIVE_PAIRS live pairs
    (consecutive gameplay captures that differ: the game was running while the holds were sent). A log alone
    proves the script ran, not what the holds were held over, so missing captures are FAIL with NO-DATA,
    never a PASS.

    Then (Sprint 6 Task 1): no hold capture or final.png may be the MISSION FAILURE screen (FAIL), and the
    console spawn comparison and the guest-value probe are appended to the detail, print-only (R78).
    `run_log` is the game's own run log for the probe; default mission_game_log(drive_log)."""
    try:
        with open(drive_log, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return False, str(e)
    m = re.search(r"untilref\([^)]*%s[^)]*\):.*matched=(True|False)" % re.escape(HUD_REF_NAME), text)
    if not m:
        return False, "no HUD untilref result in %s" % drive_log
    if m.group(1) != "True":
        return False, "HUD never matched (mission not reached)"
    holds = len(re.findall(r"^s\d\d_hold", text, re.M))
    if holds < MISSION_MIN_HOLDS:
        return False, "HUD reached; %d hold steps captured (need %d)" % (holds, MISSION_MIN_HOLDS)
    run_dir = run_dir or mission_run_dir(drive_log)
    caps = sorted(glob.glob(os.path.join(run_dir, "s[0-9][0-9]_hold*.png"))) if run_dir else []
    if len(caps) != holds:
        return False, ("NO-DATA: HUD reached, but %d hold captures for %d logged holds in %s"
                       % (len(caps), holds, run_dir))
    frames = []
    for p in caps:
        with Image.open(p) as im:
            rgb = im.convert("RGB")
            frames.append((os.path.basename(p)[:3], screen_bands.gameplay_band(rgb), rgb))
    good = sum(1 for _, (ok, _), _ in frames if ok)
    diffs = []
    for (_, (ok_a, _), a), (_, (ok_b, _), b) in zip(frames, frames[1:]):
        if b.size != a.size:
            b = b.resize(a.size, Image.BOX)
        d = float(np.abs(np.asarray(a, dtype=np.float32) - np.asarray(b, dtype=np.float32)).mean())
        diffs.append((d, ok_a and ok_b and d >= MISSION_LIVE_PAIR_DIFF))
    live = sum(1 for _, q in diffs if q)
    detail = ("HUD reached; %d hold steps; %d/%d hold captures are gameplay (need %d; bands %s); "
              "%d live hold pairs (need %d; diff >= %.1f: %s)" % (
                  holds, good, len(frames), MISSION_MIN_GAMEPLAY_HOLDS,
                  " ".join("%s=%.2f" % (n, f) for n, (_, f), _ in frames),
                  live, MISSION_MIN_LIVE_PAIRS, MISSION_LIVE_PAIR_DIFF,
                  " ".join("%.2f" % d for d, _ in diffs)))
    if not (good >= MISSION_MIN_GAMEPLAY_HOLDS and live >= MISSION_MIN_LIVE_PAIRS):
        return False, detail
    # 1a: a live game can still have failed the mission. The band and liveness tests read the MISSION
    # FAILURE statistics screen as gameplay (s5_head_1x_b), so every hold capture and the final frame
    # is checked for its banner.
    final = os.path.join(run_dir, "final.png")
    for p in caps + ([final] if os.path.isfile(final) else []):
        failed, reason = mission_fail.detect(p)
        if failed:
            return False, "MISSION FAILED on screen: %s (%s); %s" % (reason, os.path.basename(p), detail)
    # 1b: printed, not scored (R78) until the water is fixed. 1c: scored since R80 (s6_probe read the root node at
    # the console's 5.5039, MoveScale 1.0 and 0 teleports on the block-pointer exe) -- a probe value outside its
    # tolerance fails the stage; NO-DATA fails it only when the gate launched the stage itself (probe_required:
    # run_gate set PS2X_PEEK and the sampler, so rows must exist), never on a --score-mission re-score of an
    # older run that carries no game log.
    lines = [detail, console_spawn_line(drive_log, run_dir)]
    probes = probe_lines(run_log or mission_game_log(drive_log))
    lines += probes
    failed = [l for l in probes if " FAIL " in l and ("NO-DATA" not in l or probe_required)]
    failed += [l for l in probes if l.startswith("PROBE NO-DATA") and probe_required]
    if failed:
        head = failed[0].split(" ", 2)
        name = head[1] if len(head) > 1 else "?"
        return False, "GUEST PROBE FAILED: %s; %s" % (name, "; ".join(lines))
    return True, "; ".join(lines)


def _lock(cmd, owner):
    try:
        return subprocess.run(["bash", "scripts/loop_lock.sh", cmd, owner], capture_output=True, text=True)
    except OSError as e:
        raise SystemExit("gate: cannot run scripts/loop_lock.sh (%s). Run the gate from Git Bash at "
                         "the repo root." % e)


def run_gate(name, out_root):
    cfg = GATES[name]
    out_dir = os.path.join(out_root, name)
    os.makedirs(out_dir, exist_ok=True)
    for p in glob.glob(os.path.join("logs", "parity", "latest_frame.png*")):
        os.remove(p)
    drive_log = os.path.join(out_root, name + ".drive.log")
    # drive.py launches the exe with its own environment, so PS2X_* set here reach the runtime. The
    # mission stage needs the guest-value probe's chains in PS2X_PEEK (Task 1c) for probe_lines to read
    # anything; an operator's own PS2X_PEEK (a wider spec, e.g. the ladder's) is left alone.
    env = dict(os.environ)
    # A gate run is defined as a boot with NO controller: with an Xbox pad plugged in the libpad HLE reported a
    # configured controller and the game skipped its PRECISION SHOOTER CONFIGURATION screens and the 'save to
    # memory card?' dialog the transition stage keys on (s6_gamepad, s6_gamepad2, 2026-09-16).
    env.setdefault("PS2X_HOST_GAMEPAD", "0")
    # ... and from a PRISTINE memory card. The owner's free play (2026-09-16) saved the controller configuration
    # onto game/disc/mc0, the card every gate booted from, and the boot stopped showing the configuration screens
    # and the 'save to memory card?' dialog the transition stage keys on (s6_gamepad .. s6_gamepad3, three gates
    # lost). Each stage now boots from a fresh copy of game/disc/mc0_parity in the stamp directory; an operator's
    # own PS2X_MC_DIR wins. The copy is per stamp (not per stage) -- the game writes SCRATCHPAD.DAT at boot.
    if not env.get("PS2X_MC_DIR"):
        card = os.path.join(out_root, "mc0")
        shutil.copytree(PRISTINE_CARD, card, dirs_exist_ok=True)
        env["PS2X_MC_DIR"] = os.path.abspath(card)
    if name == "mission":
        if not env.get("PS2X_PEEK"):
            env["PS2X_PEEK"] = guest_probe.peek_spec(GUEST_PROBE_CONSOLE)
        # The runtime prints its [peek] rows from the PC sampler's thread, one row per sample
        # (game_overrides_socom2.cpp, PS2X_PC_SAMPLER=<seconds>): without it PS2X_PEEK yields nothing --
        # s6_blockptr's mission stage read "PROBE ... NO-DATA (0 reads of 0 rows)". One row per second
        # is the ladder's cadence and costs nothing measurable.
        env.setdefault("PS2X_PC_SAMPLER", "1")
    with open(drive_log, "w", encoding="utf-8") as log:
        subprocess.run(drive_command(name, out_dir), stdout=log, stderr=subprocess.STDOUT, env=env)
    # The game's own run log (where the runtime prints its [peek] rows) lands beside the drive log as
    # <name>.game.log; score_mission_log's probe reads it back from there (mission_game_log).
    newest = sorted(glob.glob(os.path.join("logs", "run_*.log")), key=os.path.getmtime)
    if newest:
        shutil.copyfile(newest[-1], os.path.join(out_root, name + ".game.log"))
    subprocess.run([sys.executable, "-m", "tools_py.parity.montage", out_dir,
                    os.path.join(out_root, name + "_sheet.png")], capture_output=True)
    if name == "title":
        return score_title(out_dir)
    if name == "transition":
        return score_transition(out_dir)
    return score_mission_log(drive_log, run_log=mission_game_log(drive_log), probe_required=True)


def score_baseline(stamp):
    """Sprint 6 Task 8: score a saved run directory (a stamp name under logs/parity/gate, or a path) without
    launching anything -- each stage it holds through the same scorer the live gate used; nothing written.
    Prints the gate's lines and summary; returns the gate's exit code, 4 when there is nothing to score."""
    out_root = stamp if os.path.isdir(stamp) else os.path.join("logs", "parity", "gate", stamp)
    results = []
    title_dir = os.path.join(out_root, "title")
    if os.path.isdir(title_dir):
        results.append(("title",) + tuple(score_title(title_dir)))
    transition_dir = os.path.join(out_root, "transition")
    if os.path.isdir(transition_dir):
        results.append(("transition",) + tuple(score_transition(transition_dir)))
    drive_log = os.path.join(out_root, "mission.drive.log")
    if os.path.isfile(drive_log):
        results.append(("mission",) + tuple(score_mission_log(drive_log, run_log=mission_game_log(drive_log),
                                                              probe_required=True)))
    if not results:
        print("gate: nothing to score in %s (no title/, transition/ or mission.drive.log)" % out_root)
        return 4
    failed = 0
    for name, ok, detail in results:
        print("%s %s (%s)" % ("PASS" if ok else "FAIL", name, detail), flush=True)
        failed += 0 if ok else 1
    print("GATE %s (%d/%d) [baseline %s]" % ("FAIL" if failed else "PASS", len(results) - failed, len(results), out_root))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="title,transition,mission")
    ap.add_argument("--owner", default="gate")
    ap.add_argument("--stamp", default=time.strftime("%Y%m%d_%H%M%S"))
    ap.add_argument("--score-title")
    ap.add_argument("--score-mission")
    ap.add_argument("--mission-frames", help="capture dir for --score-mission (default: <log minus .drive.log>)")
    ap.add_argument("--baseline", help="re-score a saved stamp (a logs/parity/gate/<stamp> name or a path) without "
                                       "launching: every stage it holds, through the live gate's scorers; writes nothing")
    args = ap.parse_args(argv)

    if args.baseline:
        return score_baseline(args.baseline)

    # --score-title/--score-mission re-score an existing run: no game launch, nothing large written
    # -- exempt from the disk refusal (review round 1 item 3, 2026-09-13), and checked first so
    # free_gb() is never even called on this path.
    if args.score_title:
        ok, detail = score_title(args.score_title)
        print("%s title (%s)" % ("PASS" if ok else "FAIL", detail))
        return 0 if ok else 1
    if args.score_mission:
        ok, detail = score_mission_log(args.score_mission, args.mission_frames)
        print("%s mission (%s)" % ("PASS" if ok else "FAIL", detail))
        return 0 if ok else 1

    min_free = float(os.environ.get("RUN_MIN_FREE_GB", DEFAULT_MIN_FREE_GB))
    free = free_gb()
    if free < min_free:
        print("gate: refusing to start: %.2f GB free on C: < RUN_MIN_FREE_GB=%.2f GB" % (free, min_free))
        return 3

    # Make the output root before taking the lock: a makedirs failure must not leak the lock.
    out_root = os.path.join("logs", "parity", "gate", args.stamp)
    os.makedirs(out_root, exist_ok=True)
    take = _lock("take", args.owner)
    if take.returncode != 0:
        print("gate: lock busy: " + take.stdout.strip())
        return 2
    wanted = [g.strip() for g in args.only.split(",") if g.strip()]
    results = []
    try:
        for name in wanted:
            ok, detail = run_gate(name, out_root)
            line = "%s %s (%s)" % ("PASS" if ok else "FAIL", name, detail)
            print(line, flush=True)
            results.append((ok, line))
    finally:
        # Release the lock and leave a summary even when a gate raises part-way through.
        _lock("release", args.owner)
        for name in wanted[len(results):]:
            results.append((False, "FAIL %s (gate did not run)" % name))
        failed = [line for ok, line in results if not ok]
        with open(os.path.join(out_root, "summary.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(line for _, line in results) + "\n")
        print("GATE %s (%d/%d) -> %s" % ("FAIL" if failed else "PASS",
                                         len(results) - len(failed), len(results), out_root))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
