"""Two instances of OUR exe play a match on the local Horizon stack: A logs in and hosts a game
(--map, default Frostfire; the choice is verified), B logs in, joins it and switches team, both
press READY -> the match launches (mirrors online_match.py, the PCSX2 two-client reference).
Screens land in --out as A_*/B_*.

Instance B runs with its own window title, memory card dir (game/disc/mc0_b) and UDP port shift
(see online_login_ours.INSTANCES). Personas: A = --name-a (default socomc, saved on mc0),
B = --name-b (default socome; created on first use unless --existing-b).

Gameplay phases: --play / --probe / --sweep drive open-loop bursts. --calibrate and --walk-to-b
are CLOSED loop: each instance's run log is tailed live (RunLogTail), so the driver reads the
`[peek] @416054` position rows and the `MoveScale` f12 rows while the match is running and can
measure what an injected hold actually did.

Usage: python -m tools_py.parity.online_match_ours [--hold 120] [--out logs/parity/ours_match]
"""
import argparse
import bisect
import json
import math
import os
import re
import struct
import subprocess
import threading
import time

import numpy as np

from . import online_ladder
from . import online_login_ours as L
from . import verdict_core as vc
from . import winshot

# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------
# `PS2X_PEEK=0x416054:3` + `PS2X_PC_SAMPLER=<s>` prints the local player's ORBITING CAMERA record
# (x, y, z) every sample; the camera sits CAMERA_ORBIT_RADIUS units behind the player along its
# facing (STATUS 2026-09-10 20:10), so the player is at camera + R * facing. The rows are the only
# trustworthy movement signal this harness has: screenshots go stale and are written whether or not
# the match ever launched (research/18 §3.5, §3.10).
POSITION_ADDR = 0x416054
# `PS2X_CALL_TRACE="0x553dc0:MoveScale"` logs FUN_00553dc0's f12 -- the multiplayer movement scale
# actor+0x1368. It is 1.0 while the network has been active within 5500 ms and decays to 0.0 at
# 6500 ms of idle (research/18 §3.12). A hold measured while it is not 1.0 measures the lag freeze,
# not the controls, so every calibration hold is discarded unless the scale held at 1.0 across it.
MOVE_SCALE_TRACE_NAME = "MoveScale"
MOVE_SCALE_LIVE = 1.0

# ---------------------------------------------------------------------------
# Stick keys (online_login_ours.PAD_AXIS). The game runs the Precision Shooter preset, so the
# right stick looks (and the body follows the look) and the left stick translates.
# ---------------------------------------------------------------------------
LOOK_RIGHT_KEY, LOOK_LEFT_KEY = "L", "J"        # right stick right / left  (rx)
LOOK_UP_KEY, LOOK_DOWN_KEY = "I", "K"           # right stick up / down     (ry) -- PITCH. Which of
                                                # the two raises the muzzle is NOT established, so
                                                # the engagement sweeps both ways rather than
                                                # assuming a sign. Pitch is the one look axis the
                                                # movement-scale bug never touched (research/18
                                                # §3.12: it is not among the three scaled axes)
LATERAL_RIGHT_KEY, LATERAL_LEFT_KEY = "D", "A"  # left stick right / left   (lx)
WALK_FORWARD_KEY, WALK_BACK_KEY = "W", "S"      # left stick up / down      (ly)

# ---------------------------------------------------------------------------
# MEASURED CONSTANTS -- docs/research/18-online-round-start.md §3.13 has the method, the three
# repeats and the spread. Measured on logs/parity/ours_task7_cal3 (map mp51, the default Medley
# first round, A's SEAL spawn); every hold below held the movement scale at 1.0.
#
# Angles are in the (x, z) ground plane with the sign of atan2(dz, dx). Both hold responses are
# AFFINE, not proportional: a hold delivers rate * (seconds - lead), because the record is the
# camera TRAILING the player and it takes that long to take up the slack. Measured from the three
# 2 s repeats against the one 4 s hold; the lead is what makes a short corrective hold land at all.
# ---------------------------------------------------------------------------
LOOK_DEG_PER_S = 104.9           # steady-state deg/s of a look hold. Least squares over the 19
                                 # clean turn holds of ours_task7_cal3 + ours_task7_wtb1 (0.71 s to
                                 # 4.0 s): |sweep| = 104.86*t - 46.45, RMS 18.1 deg. A proportional
                                 # fit is worse (80.4 deg/s, RMS 26.5). The RMS is why the loop
                                 # re-measures the sweep it actually got instead of trusting this.
TURN_HOLD_LEAD_S = 0.44          # dead time of a look hold before the facing moves (46.45/104.86)
LOOK_RIGHT_SIGN = 1.0            # MEASURED: LOOK_RIGHT_KEY sweeps POSITIVE (L +171/+155/+168 deg
                                 # over 2 s, LOOK_LEFT_KEY -173 over 2 s: symmetric)
# NOT a speed, and deliberately named so nobody can use it as one: the three 2 s forward repeats
# came out 8.01 / 27.55 / 29.14 units/s (ptp 21.1 on a mean of 21.6) because the record is the
# trailing camera and two of the three holds ran into something. Kept only so the failure is on the
# record next to the number that replaced it. No call site reads it. See research/18 §3.13.
WALK_2S_HOLD_OBSERVED_NOT_A_SPEED = 21.6
WALK_UNITS_PER_S_LONG = 40.0     # units/s of the 4 s forward hold, corroborated by 20 unobstructed
                                 # bursts in the proving runs at 33..46. THIS is the forward rate:
                                 # burst sizing and the progress test both use it
WALK_BACK_UNITS_PER_S = 25.3     # units/s of a 2 s backward hold (25.0..25.6 -- tight)
LATERAL_UNITS_PER_S = 42.5       # units/s of a 2 s strafe hold (39.6..45.6). MEASURED: the left
                                 # stick STRAFES on this preset, it does not turn -- the three A
                                 # holds all travelled at facing-90 deg with the facing unchanged
CAMERA_ORBIT_RADIUS = 24.9       # units from the 0x416054 record to the player. The three circle
                                 # fits with a zero residual (pure rotation) all give 24.91; fits
                                 # with translation mixed in bias it down to 22.2

# ---------------------------------------------------------------------------
# Calibration schedule
# ---------------------------------------------------------------------------
CAL_REPEATS = 3                  # the brief asks for three repeats and their spread
CAL_TURN_HOLD_S = 2.0
CAL_LONG_HOLD_S = 4.0            # one longer hold per key: linearity check
CAL_WALK_HOLD_S = 2.0
CAL_HEADING_PROBE_S = 1.5        # forward tap whose displacement direction IS the facing
CAL_RETURN_HOLD_S = 3.0          # walk back so the repeats start from roughly one place
HOLD_SETTLE_S = 1.5              # the record keeps moving briefly after release (research/18 §3.5)
HOLD_REST_S = 0.8
PEEK_LEAD_S = 0.25               # a peek row is written up to one sample after the state it reports
ROTATION_MAX_RADIUS = 250.0      # a fitted circle bigger than this is a straight line, not a turn
ROTATION_MAX_RESIDUAL = 6.0      # mean |r_i - r| of the fit, in units
MIN_ROTATION_POINTS = 4

# ---------------------------------------------------------------------------
# --walk-to-b
# ---------------------------------------------------------------------------
ARRIVE_UNITS = 120.0             # "within a set distance": ~5x the camera orbit radius, and under
                                 # 8% of the 1526-unit gap between the two spawns on this map
WALK_STEP_MIN_S = 0.8
WALK_STEP_MAX_S = 6.0            # an unobstructed 6 s burst covers ~230 units; a blocked one only
                                 # costs the difference, and ours_task7_wtb2 ran out of clock, not
                                 # of steps -- 25 steps at ~12 s each covered 55% of the gap
WALK_STEP_FRACTION = 0.8         # aim each burst at 80% of the remaining gap: undershooting costs
                                 # a step, overshooting makes the loop oscillate around B
WALK_SETTLE_S = 0.6              # the loop settles less than the calibration: it re-measures anyway
WALK_REST_S = 0.3                # ... and rests less between holds, for the same reason
TURN_SETTLE_S = 1.0
WALK_TO_B_MAX_STEPS = 40         # HARD cap: a mis-calibration cannot run the match forever
WALK_TO_B_MAX_SECONDS = 290.0    # HARD cap: a round is ~6 minutes and respawns at the end of it
TURN_DEADBAND_DEG = 12.0         # inside this the bearing error is not worth a turn hold
TURN_MAX_HOLD_S = 4.0            # a single turn hold never exceeds this
FACING_PROBE_S = 1.5
FACING_MIN_UNITS = 4.0           # below this a forward tap did not move: the heading is unusable
# MEASURED in ours_task8_kill3: instance B entered the approach while its player was still not
# controllable -- 161 in-game rows, the movement scale at 1.0, and the record moving EXACTLY 0.00
# units across a 1.5 s forward hold, a 1.3 s turn and another 1.5 s hold. Two probes in ten seconds
# was not enough patience and the whole side aborted, which cost the run: A walked alone and
# stopped 587 units short. The liveness rule counts non-zero rows, not DISTINCT ones, so it cannot
# catch this; the probe has to.
FACING_PROBE_TRIES = 6
FACING_PROBE_REST_S = 4.0
# A burst's heading is believed only when the burst actually went somewhere, in a straight line.
# ours_task7_wtb1 failed exactly here: bursts that slid along the spawn wall reported headings up to
# 86 deg off the direction the player was pointed, the loop adopted them, and every bearing after
# that was nonsense. A blocked burst now leaves the dead-reckoned facing alone.
WALK_PROGRESS_FRACTION = 0.25    # of the distance the measured rate predicts for that hold length
WALK_STRAIGHT_MIN = 0.70         # net displacement / path length along the sampled rows
DETOUR_DEG = 65.0                # on a block, aim this far off the bearing to get round whatever
DETOUR_STEPS = 2                 # ... and hold that offset for this many steps (wall following)
UNSTICK_LATERAL_UNITS = 40.0     # how far to sidestep out of whatever the burst walked into
UNSTICK_BACK_S = 0.6


# ---------------------------------------------------------------------------
# Task 8 (S3) -- two movers, a mined corridor, and the kill readout
# ---------------------------------------------------------------------------
# ONE player walking to the other cannot finish inside a round: ours_task7_wtb2 closed 757.8 units
# for 1960.7 walked (38.6 %) at ~12 s a step, so the 1382-unit gap needs ~450 s against a ~360 s
# round (KNOWN.md, research/18 §3.13). BOTH players moving halves each side's share to ~700 units
# -- and it also removes the starvation trap, because the movement scale is fed by RECEIVED bytes
# and a parked opponent sends nothing.
# The corridor below was mined on ONE map. `online_match_ours` must never steer along it anywhere
# else: a corridor that does not exist is worse than no corridor, because the loop believes it.
MINED_ROUTE_MAP = "medley"             # mp51, the Medley first round
MP51_SEAL_SPAWN = (542.3, 1479.9)      # A's spawn, camera record (x, z)
MP51_TERROR_SPAWN = (1144.8, 77.5)     # B's spawn, camera record (x, z)

# MINED, NOT PLANNED. Every point below is a place instance A's camera record actually WAS during
# ours_task7_wtb2 (logs/run_A_20260912_211009.log, 1441 in-game rows), so the corridor is
# proven-walkable rather than a guess at the map. Kept when a row is >= 70 units from the last kept
# point AND closer to MP51_TERROR_SPAWN than any row before it, which makes the chain
# progress-monotone: 1167.5 units of path to close 851.4 units of gap (73 %), against the 38.6 %
# the straight-line-plus-detour policy managed over the same ground. The y of these rows falls
# 184.8 -> -4.5, i.e. the route is a descent, which is why a straight line out of the SEAL spawn
# does not work. Re-mine with the same rule if the map or the spawn ever changes.
MP51_SEAL_ROUTE = [
    (542.16, 1479.83), (529.78, 1407.15), (619.33, 1378.23), (693.20, 1348.87),
    (748.09, 1297.83), (795.44, 1232.73), (737.63, 1192.23), (746.69, 1119.70),
    (742.73, 1044.52), (720.58, 977.14), (755.66, 912.12), (843.41, 903.91),
    (911.55, 879.02), (950.25, 814.12), (1033.83, 800.50), (1096.40, 750.61),
]
WAYPOINT_ARRIVE = 90.0           # a waypoint is "reached" this close; it is a corridor, not a rail
WAYPOINT_DROP_UNITS = 420.0      # once the other player is this close, chase the player, not the
                                 # corridor -- the corridor only exists to leave the spawn bowl

# The efficiency fix, and it is a fix to THIS loop rather than to the map. Over ours_task7_wtb2's
# 24 step transitions 10 lost ground, and the four biggest losses were 150-185 unit bursts at
# straightness 0.93-0.97 -- clean open-ground walking in the wrong direction, because the loop
# committed a FULL burst to a facing it had just dead-reckoned through an open-loop turn. Turns are
# the unreliable part (research/18 §3.13: RMS 18 deg, and wtb2's step 15 commanded -72 deg and
# delivered -16), so a burst that follows a turn is now a SHORT PROBE whose only job is to measure
# the facing; a full-length burst is spent only when the facing was measured by a believed burst
# and the bearing error is already inside the deadband.
WALK_PROBE_S = 2.0               # ~62 units: enough rows to measure a heading, cheap to throw away
TURN_GAIN_MIN, TURN_GAIN_MAX = 0.35, 2.5
TURN_GAIN_ALPHA = 0.3            # EMA over delivered/commanded, per side, measured turn by turn.
                                 # 0.5 chased the noise in kill1: the gain swung 0.88 -> 1.63 ->
                                 # 1.24 -> 0.57 -> 1.45 in nine steps and the loop turned past the
                                 # bearing every other step
TURN_GAIN_MIN_CMD = 25.0         # below this a turn is too small to estimate a gain from
# The approach deadband is NOT the 12 deg the calibration used to classify a hold as a rotation.
# No single open-loop aim is better than about +-20 deg (research/18 §3.13), so insisting on 12 deg
# means every step turns, every step that turns walks a probe, and a full burst is never spent:
# kill1 took 14 steps and 80 s to close 190 of 1392 units for exactly that reason. Walking 30 deg
# off the bearing still closes cos(30) = 87 % of the distance, which beats turning again.
APPROACH_DEADBAND_DEG = 30.0
# ... but only while there is room for the error to be cheap. 30 deg off at 400 units still closes
# 87 % of the gap; 30 deg off at 40 units walks straight past. The deadband therefore tightens back
# to the calibration's 12 deg inside APPROACH_TIGHT_UNITS, which is what stops the endgame
# oscillating around the target (the simulated converge took 39 steps with one flat deadband).
APPROACH_TIGHT_UNITS = 150.0
APPROACH_TIGHT_DEADBAND_DEG = 12.0


def approach_deadband(dist):
    return APPROACH_TIGHT_DEADBAND_DEG if dist <= APPROACH_TIGHT_UNITS else APPROACH_DEADBAND_DEG


# Contact range. PAD_AXIS injects only full stick deflection, so the shortest usable turn hold
# already sweeps 35-40 deg and no single open-loop aim is better than about +-20 deg (research/18
# §3.13). A body subtends 20 deg only at about 15 units, so the engagement has to start at contact
# range and the sweep has to cover the angle space rather than aim at it.
ENGAGE_UNITS = 45.0
ENGAGE_SWEEP_HOLD_S = 0.55       # the shortest hold that turns at all
ENGAGE_FIRE_S = 0.45
ENGAGE_STEP_FORWARD_S = 0.8
# MEASURED in ours_task8_kill2, and it is the reason that run's 24 bursts hit nothing: the two
# players closed to **10.1 units horizontally** and stayed **35-55 units apart VERTICALLY** for the
# whole engagement (mean dy -44.8 over the last 400 rows, minimum 3-D camera-to-camera separation
# 34.9). At 10 units of ground range a 45-unit height difference is 77 deg of elevation, and the
# engagement only swept yaw. So the sweep now covers pitch as well -- both ways, because which of
# I/K raises the muzzle has never been measured.
# RETIRED before it was ever used in a landed engagement, on arithmetic rather than on a run.
# The look response has a 0.44 s dead time, so a 0.5 s hold delivers ~0.06 s of deflection -- of
# the order of 6 deg -- while research/18's own probe table records a 2 s RUP hold pitching "to the
# sky", i.e. saturation. Full-deflection-only injection therefore leaves almost nothing usable
# between ~6 deg and the clamp, and the level-again loop COUNTS holds, so the first clamp
# desynchronises the pitch from the facing probe and the forward tap that follow it. Meeting at the
# same height is the cheaper and calibrated fix, and it is what ENGAGE_DY_UNITS enforces.
# The offline readout that would settle pitch properly, when someone wants it: the camera record
# minus the actor position IS a pitch measurement (kill2: ground radius 20.65, height 19.73, i.e.
# the camera sits ~44 deg above the player), so one timed I hold and one K hold in ANY
# single-instance run give both the sign and the deg/s without spending a match.
ENGAGE_SWEEP_PITCH = False
ENGAGE_PITCH_HOLD_S = 0.5
ENGAGE_PITCH_STEPS = 2           # how far up and down the sweep goes, in holds
# ... but the pitch sweep is the SECOND fix, not the first, and the rows say why. Sweeping 77 deg
# of elevation is beyond any plausible in-game pitch clamp and the ry hold response has never been
# measured at all (§3.13 calibrated yaw only), so no hold length is known to reach it. Meeting at
# the SAME elevation costs no new capability and makes the yaw sweep sufficient: at the 206-247
# unit range where kill2's two players were last within 20-27 units of each other's height, the
# elevation angle is 12 deg, not 77.
# MEASURED on kill2's ACTOR rows (1056 paired), which is the honest version of that run: the
# minimum true 3-D separation the two players ever reached was **50.0 units**, and over the last
# 400 rows the 3-D separation had a median of 67.9 (min 50.0, max 112.4) with a median elevation of
# 43.3 deg. **Zero per cent** of those rows were inside 45 units in 3-D, inside 25, or within 10 of
# each other's height. So range and elevation are CO-EQUAL causes and the 77 deg figure was the
# single worst row, not the condition. Contact is therefore a 3-D test with a height gate, and the
# engagement keeps closing rather than only sweeping.
ENGAGE_3D_UNITS = 22.0           # true actor-to-actor 3-D range at which a burst can be expected
                                 # to matter: a body subtends 15-20 deg only inside about this
ENGAGE_DY_UNITS = 10.0           # ... and the heights have to match, or the sweep has to solve an
                                 # elevation it has no calibrated way to solve
STACK_WATCH_UNITS = 140.0        # inside this ground range, a height mismatch is a STACK and the
                                 # loop stops converging into it
LEVEL_TARGET_MAX_RANGE = 600.0   # how far back along its own trail a player will go to find the
                                 # other's elevation
LEVEL_TARGET_MIN_RANGE = 40.0    # ... and how close a breadcrumb has to be to be worth walking to

# Kill / round-end readout.
TELEPORT_UNITS = 250.0           # a jump this big between consecutive 4 Hz position rows is not
                                 # walking (a 0.25 s sample at 40 units/s moves 10 units): it is a
                                 # respawn, which on a one-life round means the round ENDED
RESPAWN_RADIUS = 60.0            # ... and landing this close to the spawn it left says so twice
MOVED_AWAY_UNITS = 250.0         # only after the player got this far from its spawn in the first
                                 # place, so the first steps out of the spawn cannot fire it
SERVER_LOG = os.path.join("server", "logs", "console-Medius.log")
SERVER_ROUND_MARK = "MediusPlayerReport"
# The player actor's class vtable. PS2X_PEEK SKIPS an item whose pointer chain does not resolve,
# so the items after it shift DOWN by one and an index alone names the wrong block: in kill1's log
# item 1 was the raw `0x408c58:4` static for 1698 rows and the actor block for 804. Word 0 of the
# actor block is the vtable, so the health watch checks it before reading anything.
ACTOR_VTABLE = 0x006691A0
# The actor carries its own x/y/z at +0x1c/+0x20/+0x24 (words 7/8/9 of the block). MEASURED over
# ours_task8_kill2's 1172 paired rows: the 0x416054 camera record orbits it at a ground radius of
# 20.65 (sd 5.17) and sits 19.73 above it, i.e. the camera looks down on the player from about 44
# deg. Reading the actor directly removes the whole camera->player reconstruction, and with it the
# error that made "contact at 33 units" meaningless: reconstructing from camera + facing is wrong
# by up to two orbit radii (~50 units) when the facing estimate is wrong, and it needs the OTHER
# side's facing, which is what ours_task8_kill3 never obtained.
ACTOR_POS_WORDS = (7, 8, 9)


# ---------------------------------------------------------------------------
# Live log tail
# ---------------------------------------------------------------------------
class RunLogTail(threading.Thread):
    """Follow one instance's run log and host-timestamp the rows the driver has to act on.

    The exe prints `[peek]` with std::endl (flushed per line) and does not timestamp it, so the
    arrival time recorded here is the clock the driver uses; it lags the guest state by at most one
    sampler period plus the poll interval.
    """

    _ITEM = re.compile(r"@([0-9a-fA-F]+):((?:\s+[0-9a-fA-F]{8}\([^)]*\))+)")
    _WORD = re.compile(r"([0-9a-fA-F]{8})\(")

    POLL_S = 0.05
    _BP = re.compile(r"^\[gs-gl stats\] backpressure .*?\bwaits=(\d+) wait_ms=([\d.]+) timeouts=(\d+)")

    def __init__(self, path, addr=POSITION_ADDR, clock=time.time):
        super().__init__(daemon=True)
        self.path, self.addr, self.clock = path, addr, clock
        self.rows = []          # (t, x, y, z) -- every peek row, all-zero pre-gameplay rows included
        self.scales = []        # (t, f12)
        self.lines = 0
        # Task 8: every OTHER PS2X_PEEK item of the same row, by its index in the PS2X_PEEK spec.
        # `items[i] = (t, addr, [word, ...])` is the most recent block; `item_rows` counts them so
        # "the chain never resolved" is distinguishable from "the chain resolved and nothing moved"
        # -- an item whose pointer chain is bad is SKIPPED by the exe, not printed as zeros.
        self.items = {}
        self.item_rows = {}
        # The ACTOR's own position rows, (t, x, y, z), read out of whichever peeked item carries
        # the actor block -- identified by its vtable, never by an index, because PS2X_PEEK SKIPS
        # an item whose chain does not resolve and the ones after it shift down.
        self.actor_rows = []
        self.actor_addr = None
        # Sprint 5 Task 5: the actor-matrix heading (t, facing deg, x, z) -- research/22 §4, valid at rest only
        self.heading_rows = []
        # A health watch is an OFFSET IN BYTES FROM THE ACTOR BASE, not an item/word pair: the
        # item index is not stable and an index-based guard checked the wrong block entirely.
        self.watch_offset = None
        # How many sampler rows the watch actually READ a value from. Without this, "health never
        # moved" and "the watch never read anything" are the same observation -- the zero-rows
        # hazard, re-entering at exactly the point the kill readout depends on.
        self.watch_reads = 0
        self.watch_misses = 0
        # (t, value, actor_addr) of that word, appended only when the value OR the actor changes.
        # The actor address travels with every read: a death is only a death on the actor that was
        # alive a moment ago, and the actor block can be re-pointed (respawn, a different player).
        self.watch_hist = []
        # Sprint 5 Task 3: the state the verdicts need, read by CONTENT through verdict_core.
        #   calls[name] = [(t, #n, f12)] for every `[call]` slot (count calls from #n, never lines);
        #   rets[name]  = [(t, #n, v0)];
        #   alive_rows  = [(t, actor+0xF7A byte)];
        #   round_rows  = [(t, {mp_round_count, mp_game_over, aiteam_00, aiteam_08, clock})], each a
        #                 value or vc.NoData -- valves identified by their NAME BYTES, never by pointer;
        #   valve_counts[name] = [rows identified, rows seen, last NO-DATA reason];
        #   latest_items = the newest row's items (the R6 context of a move-path stall line).
        self.calls = {}
        self.rets = {}
        self.alive_rows = []
        # Which actor byte is the alive byte (--alive-offset; research/19 F1, confirmed single-player in
        # Sprint 5 Task 2), and (t, byte, actor_addr) appended when the byte OR the actor changes -- the
        # alive-leaves-1 observation KillWatch records beside a health death.
        self.alive_offset = vc.ACTOR_ALIVE_OFFSET
        self.alive_hist = []
        self.round_rows = []
        self.round_valid_t = None
        self.valve_counts = {}
        self.latest_items = None
        # Sprint 5 Task 5: ng+0xde (t, byte) from the CZNetGame block, found by content (vc.ng_lagflag_rows); and the
        # round clock DAT_004365c0 (t, float), which stands still while an instance's guest is frozen (launch 8c).
        self.lag_rows = []
        self.round_time_rows = []
        # Sprint 5 Amendment A4 (rung 0): `[gs-gl stats] backpressure ... waits= wait_ms= timeouts=` rows (PS2X_GS_STATS=1,
        # one per ~60 GL calls) as (t, waits, wait_ms, timeouts), and the `[gs-gl] back-pressure:` cap-hit lines (t)
        self.bp_rows = []
        self.bp_caps = []
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # -- reading -------------------------------------------------------------
    def run(self):
        f, buf = None, ""
        while not self._stop.is_set():
            if f is None:
                try:
                    f = open(self.path, "r", errors="replace")
                except OSError:
                    time.sleep(0.2)
                    continue
            chunk = f.read(65536)
            if not chunk:
                time.sleep(self.POLL_S)
                continue
            buf += chunk
            while True:
                nl = buf.find("\n")
                if nl < 0:
                    break
                self._line(buf[:nl])
                buf = buf[nl + 1:]
        if f:
            f.close()

    def _line(self, line):
        self.lines += 1
        t = self.clock()
        if line.startswith("[peek]"):
            blocks = []
            all_items = []
            for idx, (addr, words) in enumerate(self._ITEM.findall(line)):
                raw = [int(w, 16) for w in self._WORD.findall(words)]
                a = int(addr, 16)
                all_items.append((a, raw))
                if a == self.addr:
                    vals = [struct.unpack("<f", struct.pack("<I", w))[0] for w in raw[:3]]
                    if len(vals) >= 3:
                        with self._lock:
                            self.rows.append((t, vals[0], vals[1], vals[2]))
                    continue
                blocks.append((idx, a, raw))
            self._state_row(t, all_items)
            if not blocks:
                return
            # Which block is the actor? The one whose word 0 is the class vtable. Everything else
            # -- its position, and where a health offset lives -- is addressed off that block's
            # own address, so an unresolved chain can shift the indices without breaking anything.
            actor = next((b for b in blocks if b[2] and b[2][0] == ACTOR_VTABLE), None)
            with self._lock:
                for idx, a, raw in blocks:
                    self.items[idx] = (t, a, raw)
                    self.item_rows[idx] = self.item_rows.get(idx, 0) + 1
                if actor is not None:
                    self.actor_addr = actor[1]
                    wi, wj, wk = ACTOR_POS_WORDS
                    if len(actor[2]) > wk:
                        xyz = [struct.unpack("<f", struct.pack("<I", actor[2][w]))[0]
                               for w in (wi, wj, wk)]
                        self.actor_rows.append((t, xyz[0], xyz[1], xyz[2], actor[1]))
                        h = heading_from_matrix(actor[2])
                        if h is not None and (xyz[0] or xyz[1] or xyz[2]):
                            self.heading_rows.append((t, h, xyz[0], xyz[2]))
                    if self.watch_offset is not None:
                        want = self.actor_addr + self.watch_offset
                        hit = False
                        for _, a, raw in blocks:
                            if a <= want < a + 4 * len(raw):
                                v = raw[(want - a) // 4]
                                self.watch_reads += 1
                                hit = True
                                if (not self.watch_hist
                                        or self.watch_hist[-1][1:] != (v, self.actor_addr)):
                                    self.watch_hist.append((t, v, self.actor_addr))
                                break
                        if not hit:
                            # The offset is armed but no peeked block covers it -- the PS2X_PEEK
                            # spec is too narrow. Counted, so the run can say so instead of
                            # reporting silence as stability.
                            self.watch_misses += 1
            return
        if line.startswith("[call]"):
            m = vc._CALL.match(line)
            if m:
                name, n, rest = m.group(2), int(m.group(3)), m.group(4)
                fm = vc._F12.search(rest)
                f12 = float(fm.group(1)) if fm else None
                with self._lock:
                    self.calls.setdefault(name, []).append((t, n, f12))
                    if name == MOVE_SCALE_TRACE_NAME and f12 is not None:
                        self.scales.append((t, f12))
            return
        if line.startswith("[ret]"):
            m = vc._RET.match(line)
            if m:
                with self._lock:
                    self.rets.setdefault(m.group(1), []).append((t, int(m.group(2)), int(m.group(3), 16)))
            return
        if line.startswith("[gs-gl"):
            m = self._BP.search(line)
            if m:
                with self._lock:
                    self.bp_rows.append((t, int(m.group(1)), float(m.group(2)), int(m.group(3))))
            elif "back-pressure:" in line:
                with self._lock:
                    self.bp_caps.append(t)

    def _state_row(self, t, items):
        """Alive byte, round valves + clock string and per-valve identification counts, from one
        `[peek]` row's items (all of them, the camera record included)."""
        alive = vc.row_actor_field(items, self.alive_offset, "u8")
        actor = next((a for a, w in items if w and w[0] == ACTOR_VTABLE), None)
        valves = {name: vc.row_valve(items, name) for name in vc.VALVES}
        state = {name: valves[name] for name in vc.ROUND_VALVES}
        state["clock"] = vc.row_clock_string(items)
        lag = vc.ng_lagflag_rows([(t, items)])
        rt_word = vc.row_static(items, vc.ROUND_TIME_ADDR)
        with self._lock:
            self.latest_items = items
            if lag:
                self.lag_rows.append(lag[0])
            if rt_word is not None:
                self.round_time_rows.append((t, vc.f32(rt_word)))
            if not isinstance(alive, vc.NoData):
                self.alive_rows.append((t, alive))
                if not self.alive_hist or self.alive_hist[-1][1:] != (alive, actor):
                    self.alive_hist.append((t, alive, actor))
            self.round_rows.append((t, state))
            if not any(isinstance(state[k], vc.NoData) for k in ("mp_round_count", "mp_game_over")):
                self.round_valid_t = t
            for name, v in valves.items():
                c = self.valve_counts.setdefault(name, [0, 0, None])
                c[1] += 1
                if isinstance(v, vc.NoData):
                    c[2] = v.reason
                else:
                    c[0] += 1

    def stop(self):
        self._stop.set()

    # -- queries -------------------------------------------------------------
    def _snapshot(self):
        with self._lock:
            return list(self.rows)

    def ingame(self):
        """Rows that are not the all-zero pre-gameplay record (research/18 §3.10 step 0)."""
        return [r for r in self._snapshot() if r[1] or r[2] or r[3]]

    def actor_ingame(self):
        with self._lock:
            rows = list(self.actor_rows)
        return [r for r in rows if r[1] or r[2] or r[3]]

    def actor_latest(self, max_age=4.0):
        """The player's OWN (t, x, y, z), or None. Preferred over `latest()` everywhere: it needs
        no facing, no orbit radius and no reconstruction."""
        rows = self.actor_ingame()
        if rows and self.clock() - rows[-1][0] <= max_age:
            return rows[-1]
        return None

    def latest(self, max_age=4.0):
        rows = self.ingame()
        if rows and self.clock() - rows[-1][0] <= max_age:
            return rows[-1]
        return None

    def last_before(self, t):
        rows = [r for r in self.ingame() if r[0] <= t]
        return rows[-1] if rows else None

    def window(self, t0, t1):
        return [r for r in self.ingame() if t0 <= r[0] <= t1]

    def scale_window(self, t0, t1):
        with self._lock:
            return [s for s in self.scales if t0 <= s[0] <= t1]

    def scale_ok(self, t0, t1, pad=2.5):
        """(ok, n, lo, hi) for the movement scale across a hold. No samples at all is NOT ok --
        an instrument that emits zero rows is a failed measurement, not a quiet one (§3.10 rule 3).
        """
        s = [v for _, v in self.scale_window(t0 - pad, t1 + pad)]
        if not s:
            return False, 0, None, None
        return (min(s) == MOVE_SCALE_LIVE == max(s)), len(s), min(s), max(s)


# ---------------------------------------------------------------------------
# Geometry, all in the (x, z) ground plane
# ---------------------------------------------------------------------------
def circle_fit(pts):
    """Algebraic (Kasa) circle fit; returns (cx, cz, r, mean residual)."""
    P = np.asarray(pts, dtype=float)
    if len(P) < 3:
        return None
    A = np.column_stack([2.0 * P[:, 0], 2.0 * P[:, 1], np.ones(len(P))])
    b = (P ** 2).sum(axis=1)
    try:
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    cx, cz, c = (float(v) for v in sol)
    rr = c + cx * cx + cz * cz
    if not (rr > 0.0) or not np.isfinite(rr):
        return None
    r = math.sqrt(rr)
    resid = float(np.mean(np.abs(np.hypot(P[:, 0] - cx, P[:, 1] - cz) - r)))
    return cx, cz, r, resid


def sweep_deg(pts, cx, cz):
    """Signed angle swept about (cx, cz), accumulated so a sweep past +-180 deg still adds up."""
    total, prev = 0.0, None
    for x, z in pts:
        a = math.degrees(math.atan2(z - cz, x - cx))
        if prev is not None:
            total += (a - prev + 180.0) % 360.0 - 180.0
        prev = a
    return total


def wrap_deg(a):
    return (a + 180.0) % 360.0 - 180.0


def spread(values):
    """(n, mean, min, max, peak-to-peak, stdev) -- a calibration without its spread is not one."""
    v = [x for x in values if x is not None]
    if not v:
        return {"n": 0}
    m = sum(v) / len(v)
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / len(v)) if len(v) > 1 else 0.0
    return {"n": len(v), "mean": m, "min": min(v), "max": max(v), "ptp": max(v) - min(v), "sd": sd}


# ---------------------------------------------------------------------------
# One measured hold
# ---------------------------------------------------------------------------
def _wait(abort, seconds):
    """Sleep, unless `abort` is set -- in which case return at once (or as soon as it is set)."""
    if abort is None:
        time.sleep(seconds)
    else:
        abort.wait(seconds)


def measure_hold(sh, tail, key, seconds, settle=HOLD_SETTLE_S, rest=HOLD_REST_S, label="",
                 abort=None):
    """Inject one stick hold and measure what the 0x416054 record did over hold + settle.

    Returns both readings, because which one is meaningful depends on the key: a look hold rotates
    the record about the player (fit a circle, take the swept angle) and a walk/strafe hold
    translates it (take the displacement). `kind` says which the data supports.
    """
    t0 = time.time()
    if abort is None:
        sh.pad(seconds, sticks=[key])
    else:
        sh.pad(seconds, sticks=[key], abort=abort)
    t1 = time.time()
    _wait(abort, settle)
    t2 = time.time()
    _wait(abort, rest)

    before = tail.last_before(t0 + PEEK_LEAD_S)
    pts = tail.window(t0, t2 + PEEK_LEAD_S)
    ok, n_scale, lo, hi = tail.scale_ok(t0, t2)
    out = {"label": label, "key": key, "hold_s": round(t1 - t0, 3), "rows": len(pts),
           "scale_ok": ok, "scale_n": n_scale, "scale_lo": lo, "scale_hi": hi,
           "kind": "no-data", "dist": None, "heading": None, "rate_units_s": None,
           "sweep_deg": None, "rate_deg_s": None, "radius": None, "residual": None,
           "centre": None, "start": None, "end": None, "path": None, "straight": None}
    if before is None or not pts:
        return out
    end = pts[-1]
    out["start"] = [before[1], before[2], before[3]]
    out["end"] = [end[1], end[2], end[3]]
    dx, dz = end[1] - before[1], end[3] - before[3]
    out["dist"] = math.hypot(dx, dz)
    out["rate_units_s"] = out["dist"] / max(out["hold_s"], 1e-6)
    if out["dist"] > 1e-6:
        out["heading"] = math.degrees(math.atan2(dz, dx))

    track = [(before[1], before[3])] + [(r[1], r[3]) for r in pts]
    # Path length along the sampled rows: net/path is 1.0 for a straight line and falls away as the
    # record curves -- which is what sliding along a wall looks like from these rows.
    out["path"] = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(track, track[1:]))
    out["straight"] = out["dist"] / out["path"] if out["path"] > 1e-6 else 0.0
    fit = circle_fit(track)
    if fit:
        cx, cz, r, resid = fit
        sw = sweep_deg(track, cx, cz)
        out.update(radius=r, residual=resid, centre=[cx, cz], sweep_deg=sw,
                   rate_deg_s=sw / max(out["hold_s"], 1e-6))
        if (len(track) >= MIN_ROTATION_POINTS and r <= ROTATION_MAX_RADIUS
                and resid <= ROTATION_MAX_RESIDUAL and abs(sw) >= TURN_DEADBAND_DEG):
            out["kind"] = "rotation"
        else:
            out["kind"] = "translation"
    else:
        out["kind"] = "translation"
    return out


def fmt_hold(m):
    scale = "1.0" if m["scale_ok"] else "BAD"
    rng = "" if m["scale_lo"] is None else f",{m['scale_lo']}..{m['scale_hi']}"
    s = (f"[cal] {m['label']:<22} key={m['key']} hold={m['hold_s']:.2f}s rows={m['rows']:2d} "
         f"kind={m['kind']:<11} scale={scale}({m['scale_n']}{rng})")
    if m["dist"] is not None:
        s += f" d={m['dist']:7.2f} ({m['rate_units_s']:6.2f} u/s) str={m['straight']:4.2f}"
    if m["heading"] is not None:
        s += f" hdg={m['heading']:7.2f}"
    if m["sweep_deg"] is not None:
        s += (f" sweep={m['sweep_deg']:8.2f} ({m['rate_deg_s']:7.2f} deg/s)"
              f" r={m['radius']:7.2f} res={m['residual']:5.2f}")
    return s


def wait_ingame(tail, sh, timeout=180.0, need=8):
    """research/18 §3.10 step 0, enforced in-process: no gameplay rows, no measurement."""
    t = time.time()
    while time.time() - t < timeout:
        if len(tail.ingame()) >= need:
            sh.log(f"liveness OK: {len(tail.ingame())} in-game peek rows, {tail.lines} log lines")
            return True
        time.sleep(1.0)
    sh.log(f"LIVENESS FAILED: {len(tail.ingame())} in-game peek rows of {len(tail.rows)} "
           f"({tail.lines} log lines) -- this run never reached gameplay")
    return False


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
def calibrate(sh, tail, out_dir, shots=True):
    """Measure look deg/s, lateral units/s, walk units/s and the camera orbit radius.

    Every turn repeat is bracketed by a short forward tap, so the rotation is measured twice by
    independent means: the circle fit through the camera arc, and the change in the direction the
    player actually walks. The second is what --walk-to-b consumes.
    """
    res = {"look": [], "lateral": [], "walk": [], "back": [], "heading_delta": [],
           "radius": [], "long": [], "left": [], "orbit_check": []}
    sh.log("calibration start")

    # --- look (right stick), bracketed by heading probes -------------------
    for rep in range(CAL_REPEATS):
        w0 = measure_hold(sh, tail, WALK_FORWARD_KEY, CAL_HEADING_PROBE_S, label=f"look{rep}_hdg_before")
        sh.log(fmt_hold(w0))
        t = measure_hold(sh, tail, LOOK_RIGHT_KEY, CAL_TURN_HOLD_S, label=f"look{rep}_turn")
        sh.log(fmt_hold(t))
        w1 = measure_hold(sh, tail, WALK_FORWARD_KEY, CAL_HEADING_PROBE_S, label=f"look{rep}_hdg_after")
        sh.log(fmt_hold(w1))
        if t["scale_ok"] and t["kind"] == "rotation":
            res["look"].append(t["rate_deg_s"])
            res["radius"].append(t["radius"])
        if (w0["heading"] is not None and w1["heading"] is not None and t["scale_ok"]
                and w0["dist"] > FACING_MIN_UNITS and w1["dist"] > FACING_MIN_UNITS):
            d = wrap_deg(w1["heading"] - w0["heading"])
            res["heading_delta"].append(d / max(t["hold_s"], 1e-6))
            sh.log(f"[cal] look{rep}_walk_heading_delta {d:.2f} deg over {t['hold_s']:.2f}s "
                   f"= {d / t['hold_s']:.2f} deg/s (circle fit said {t['rate_deg_s']})")
        # The camera sits behind the player: the direction from the record to the fitted circle
        # centre should be the walk heading, and the radius the offset. Check both.
        if t["kind"] == "rotation" and w1["heading"] is not None and t["centre"]:
            cx, cz = t["centre"]
            ex, ez = t["end"][0], t["end"][2]
            to_centre = math.degrees(math.atan2(cz - ez, cx - ex))
            res["orbit_check"].append(wrap_deg(to_centre - w1["heading"]))
            sh.log(f"[cal] look{rep}_orbit_check record->centre {to_centre:.2f} vs walk heading "
                   f"{w1['heading']:.2f} (delta {wrap_deg(to_centre - w1['heading']):.2f}), "
                   f"r={t['radius']:.2f}")
        b = measure_hold(sh, tail, WALK_BACK_KEY, CAL_RETURN_HOLD_S, label=f"look{rep}_return")
        sh.log(fmt_hold(b))
        if shots:
            sh.shot(f"cal_look{rep}")

    lng = measure_hold(sh, tail, LOOK_RIGHT_KEY, CAL_LONG_HOLD_S, label="look_long")
    sh.log(fmt_hold(lng))
    res["long"].append({"key": LOOK_RIGHT_KEY, "hold_s": lng["hold_s"], "rate_deg_s": lng["rate_deg_s"],
                        "kind": lng["kind"], "scale_ok": lng["scale_ok"]})
    lft = measure_hold(sh, tail, LOOK_LEFT_KEY, CAL_TURN_HOLD_S, label="look_left")
    sh.log(fmt_hold(lft))
    if lft["scale_ok"] and lft["kind"] == "rotation":
        res["left"].append(lft["rate_deg_s"])

    # --- lateral (left stick left/right) -----------------------------------
    for rep in range(CAL_REPEATS):
        r = measure_hold(sh, tail, LATERAL_RIGHT_KEY, CAL_TURN_HOLD_S, label=f"lateral{rep}_right")
        sh.log(fmt_hold(r))
        if r["scale_ok"]:
            res["lateral"].append({"rate_units_s": r["rate_units_s"], "rate_deg_s": r["rate_deg_s"],
                                   "kind": r["kind"], "dist": r["dist"]})
        lt = measure_hold(sh, tail, LATERAL_LEFT_KEY, CAL_TURN_HOLD_S, label=f"lateral{rep}_left")
        sh.log(fmt_hold(lt))
        if shots:
            sh.shot(f"cal_lateral{rep}")

    # --- walk --------------------------------------------------------------
    for rep in range(CAL_REPEATS):
        f = measure_hold(sh, tail, WALK_FORWARD_KEY, CAL_WALK_HOLD_S, label=f"walk{rep}_fwd")
        sh.log(fmt_hold(f))
        if f["scale_ok"]:
            res["walk"].append(f["rate_units_s"])
        b = measure_hold(sh, tail, WALK_BACK_KEY, CAL_WALK_HOLD_S, label=f"walk{rep}_back")
        sh.log(fmt_hold(b))
        if b["scale_ok"]:
            res["back"].append(b["rate_units_s"])
        if shots:
            sh.shot(f"cal_walk{rep}")
    wl = measure_hold(sh, tail, WALK_FORWARD_KEY, CAL_LONG_HOLD_S, label="walk_long")
    sh.log(fmt_hold(wl))
    res["long"].append({"key": WALK_FORWARD_KEY, "hold_s": wl["hold_s"], "rate_units_s": wl["rate_units_s"],
                        "kind": wl["kind"], "scale_ok": wl["scale_ok"]})
    sh.log(fmt_hold(measure_hold(sh, tail, WALK_BACK_KEY, CAL_LONG_HOLD_S, label="walk_long_return")))

    summary = {
        "look_deg_per_s": spread(res["look"]),
        "look_deg_per_s_from_walk_heading": spread(res["heading_delta"]),
        "look_left_deg_per_s": spread(res["left"]),
        "camera_orbit_radius": spread(res["radius"]),
        "orbit_direction_error_deg": spread(res["orbit_check"]),
        "walk_units_per_s": spread(res["walk"]),
        "walk_back_units_per_s": spread(res["back"]),
        "lateral": res["lateral"],
        "linearity": res["long"],
    }
    sh.log("[cal] SUMMARY " + json.dumps(summary, default=float))
    if out_dir:
        with open(os.path.join(out_dir, f"calibration_{sh.tag or 'A'}.json"), "w") as fh:
            json.dump({"raw": res, "summary": summary}, fh, indent=1, default=float)
    return summary


# ---------------------------------------------------------------------------
# --walk-to-b
# ---------------------------------------------------------------------------
def player_pos(record, heading_deg):
    """The player, from its orbiting-camera record: the camera is CAMERA_ORBIT_RADIUS behind."""
    h = math.radians(heading_deg)
    return record[1] + CAMERA_ORBIT_RADIUS * math.cos(h), record[3] + CAMERA_ORBIT_RADIUS * math.sin(h)


def turn_hold_seconds(error_deg):
    """Hold length for a turn of |error_deg|, from the affine response: the first TURN_HOLD_LEAD_S
    of a hold delivers nothing, so a short correction that ignores the lead delivers nothing."""
    return min(abs(error_deg) / LOOK_DEG_PER_S + TURN_HOLD_LEAD_S, TURN_MAX_HOLD_S)


def turn_by(sh, tail, error_deg, abort=None):
    """Turn the facing by `error_deg` with one timed hold at the measured look rate."""
    key = LOOK_RIGHT_KEY if error_deg * LOOK_RIGHT_SIGN >= 0 else LOOK_LEFT_KEY
    secs = turn_hold_seconds(error_deg)
    m = measure_hold(sh, tail, key, secs, settle=TURN_SETTLE_S, rest=WALK_REST_S,
                     label=f"turn{error_deg:+.0f}", abort=abort)
    sh.log(fmt_hold(m))
    return m


def facing_probe(sh, tail, seconds=FACING_PROBE_S, label="facing", abort=None):
    """A short forward tap; the direction the record travels IS the player's facing."""
    m = measure_hold(sh, tail, WALK_FORWARD_KEY, seconds, label=label, abort=abort)
    sh.log(fmt_hold(m))
    if m["heading"] is None or m["dist"] < FACING_MIN_UNITS or not m["scale_ok"]:
        return None, m
    return m["heading"], m


def walk_to_b(A, B, tailA, tailB, arrive, max_steps, max_seconds, shots=True):
    """Task 7's one-directional approach: A walks to a PARKED B, capped by steps and wall clock.

    It is now the single-mover entry point into the one loop -- `approach()` with no corridor, no
    engagement and a partner that is not walking back. Task 8 generalised the loop rather than
    forking it, so `sim_walk_to_b.py` exercises the code the match actually runs.

    A parked opponent starves a STUCK mover (the movement scale is fed by received bytes, KNOWN.md),
    so this mode is the calibration/proving one: --converge is what a match should use.
    """
    duel = Duel()
    me, other = Side("A", A.sh, tailA), Side("B", B.sh, tailB)
    fb, _ = facing_probe(B.sh, tailB, label="B_facing")
    if fb is None:
        A.sh.log("walk-to-b: B's facing probe moved nothing -- falling back to the raw record "
                 "(B is then known only to within the orbit radius)")
    else:
        duel.set_facing("B", fb)
    r = approach(me, other, duel, arrive, max_steps, max_seconds, shots=shots, shot_every=1,
                 engage=-1.0)
    return r


# ---------------------------------------------------------------------------
# Task 8 (S3): two movers converging, and the kill / round-end readout
# ---------------------------------------------------------------------------
class Duel:
    """What the two approach threads have to agree on: each side's measured facing, each side's
    view of the gap, and a single contact flag, so that when one side reaches contact the other
    stops walking instead of running past it."""

    def __init__(self):
        self._lock = threading.Lock()
        self.facing = {}
        self.dist = {}
        self.contact = threading.Event()
        self.stop = threading.Event()
        # Sprint 5 Task 5: the PAIRED actor range over the whole run (PairedRange), from the tails each side
        # registers with observe(). best_dist() used to be min(each side's LATEST set_dist), which is
        # neither the run minimum nor the current gap: launch 3c printed closest_3d=166.76 against a true
        # 52.42 (dy 42), and the pre-engagement `near` gate read that number.
        self.tails = {}
        self.pairs = PairedRange()
        self._pair_lock = threading.Lock()

    def set_facing(self, tag, f):
        with self._lock:
            self.facing[tag] = f

    def get_facing(self, tag):
        with self._lock:
            return self.facing.get(tag)

    def set_dist(self, tag, d):
        with self._lock:
            self.dist[tag] = d

    def observe(self, tag, tail):
        with self._lock:
            self.tails[tag] = tail

    def update_pairs(self):
        with self._lock:
            ta, tb = self.tails.get("A"), self.tails.get("B")
        if ta is None or tb is None:
            return
        with self._pair_lock:
            self.pairs.update(ta.actor_ingame(), tb.actor_ingame())

    def best_dist(self):
        """The TRUE run minimum of the paired actor-to-actor 3-D distance (verdict_core.score_contact's
        pairing). Only a run with no paired actor rows at all (camera reconstruction) falls back to the
        smallest distance a side published, and that fallback is not a run minimum."""
        self.update_pairs()
        if self.pairs.closest is not None:
            return self.pairs.closest
        with self._lock:
            v = [d for d in self.dist.values() if d is not None]
        return min(v) if v else None

    def best_dy(self):
        """|dy| at the run minimum (None without paired rows)."""
        self.update_pairs()
        return self.pairs.closest_dy

    def current_d3(self, now=None, max_age=None):
        """The CURRENT paired 3-D distance -- the newest pair, if it is at most `max_age` old -- or None.
        This, not the run minimum, is what a gate that decides what to do next may read."""
        max_age = CURRENT_PAIR_MAX_AGE_S if max_age is None else max_age
        self.update_pairs()
        cur = self.pairs.current
        now = time.time() if now is None else now
        if cur is None or now - cur[0] > max_age:
            return None
        return cur[1]


class Side:
    """One instance as the approach loop sees it."""

    def __init__(self, tag, sh, tail, route=None):
        self.tag, self.sh, self.tail, self.route = tag, sh, tail, route
        self.turn_gain = 1.0
        self.r1_times = []           # Sprint 5 Task 5: host times of the R1 injections (the damage verdict)
        self.best_3d = None          # the 2-D best flatters a stack; keep the honest one too
        self.spawn = None
        self.result = None
        # Sprint 5 Task 5: partial-deflection aim state (aim_yaw)
        self.yaw_gain = 1.0
        self.aims = []
        self.aim_teleports = 0


def true_pos(tail, facing=None):
    """(x, y, z, source) for a player: the ACTOR's own position when the actor block is being
    peeked, and the camera reconstruction only as a fallback.

    The reconstruction is `camera + CAMERA_ORBIT_RADIUS * facing`, so a facing that is wrong by
    tens of degrees misplaces the player by up to two orbit radii -- about 50 units, which is
    larger than the whole engagement range. It also needs the OTHER side's facing to place the
    other player, which is a dependency the actor read does not have.
    """
    a = tail.actor_latest()
    if a is not None:
        return a[1], a[2], a[3], "actor"
    r = tail.latest()
    if r is None:
        return None
    if facing is None:
        return r[1], r[2], r[3], "camera-raw"
    x, z = player_pos(r, facing)
    return x, r[2], z, "camera-reconstructed"


def level_target(tail, target_y, me_xz, tol=None,
                 max_range=LEVEL_TARGET_MAX_RANGE, min_range=LEVEL_TARGET_MIN_RANGE):
    """The nearest place THIS player has actually stood whose height matches `target_y`.

    The player's own position rows are a breadcrumb trail: every one of them is somewhere it
    provably was, at a height it provably was at. When the two players are close on the ground and
    far apart vertically, walking to a breadcrumb at the other's height is a proven-walkable way
    out of the stack, and it needs no map, no route planner and no new calibration.

    ours_task8_kill2 is why this exists: A's own rows span y 8.0-189.3 and B's 23.5-88.1, so A
    walked THROUGH B's elevation band and kept descending. The closest the two ever came while
    within 15 units of each other's height was 321.6 units; by the time they were 12.3 units apart
    on the ground they were 36.0 apart vertically.
    """
    tol = ENGAGE_DY_UNITS if tol is None else tol     # read at CALL time, not at import time
    best = None
    trail = tail.actor_ingame() or tail.ingame()
    for r in trail:                              # (t, x, y, z)
        if abs(r[2] - target_y) > tol:
            continue
        d = math.hypot(r[1] - me_xz[0], r[3] - me_xz[1])
        if d > max_range or d < min_range:
            continue
        if best is None or d < best[0]:
            best = (d, (r[1], r[3]), r[2])
    return best


def other_player_pos(tail, facing):
    """The other side's player position from its camera record. Without its facing the record is
    only good to within CAMERA_ORBIT_RADIUS, which is why both sides publish theirs."""
    r = tail.latest()
    if r is None:
        return None, None
    if facing is None:
        return (r[1], r[3]), r
    return player_pos(r, facing), r


def approach(me, other, duel, arrive, max_steps, max_seconds, shots=True, shot_every=3,
             engage=ENGAGE_UNITS):
    """Walk `me` toward `other` until the gap closes, following `me.route` out of the spawn while
    the other player is still far away.

    Generalised from Task 7's one-directional --walk-to-b: it runs on either instance, both at
    once, and the other player is READ LIVE rather than assumed parked.
    """
    sh, tail = me.sh, me.tail
    t_start = time.time()
    # Every hold this side makes is released the moment EITHER side calls contact. Without it the
    # side that did not call contact finished its in-flight burst -- up to WALK_STEP_MAX_S, ~240
    # units -- and walked straight through the engagement: the simulated `converge` once reported
    # a best of 11.2 while the two players ended 87.4 apart.
    abort = duel.contact
    sh.log(f"approach[{me.tag}]: arrive<={arrive} engage<={engage} <={max_steps} steps, "
           f"<={max_seconds}s, route={len(me.route or [])} waypoints")
    duel.observe(me.tag, tail)
    duel.observe(other.tag, other.tail)
    facing = None
    for attempt in range(FACING_PROBE_TRIES):
        facing, _ = facing_probe(sh, tail, label=f"{me.tag}_facing{attempt}", abort=abort)
        if facing is not None:
            break
        sh.log(f"approach[{me.tag}]: facing probe {attempt} moved nothing -- the player may not be "
               f"controllable yet; turning 90 deg, waiting {FACING_PROBE_REST_S}s and retrying")
        turn_by(sh, tail, 90.0, abort=abort)
        _wait(abort, FACING_PROBE_REST_S)
    if facing is None:
        # NOT an abort. A side that cannot measure its heading can still walk: every burst is
        # scored and a believed one replaces the facing, so the loop finds it within a step or two.
        # Aborting here cost ours_task8_kill3 its second mover and, with it, the whole run.
        facing, confident0 = 0.0, False
        sh.log(f"approach[{me.tag}]: no heading after {FACING_PROBE_TRIES} probes -- starting at "
               f"0 deg with the facing UNTRUSTED; the first believed burst will measure it")
    else:
        confident0 = True
    duel.set_facing(me.tag, facing)
    r0 = tail.latest()
    if r0 is not None and me.spawn is None:
        me.spawn = (r0[1], r0[3])

    best, track = None, []
    wp, detour_left, detour_sign, blocks, confident = 0, 0, 1.0, 0, confident0
    pending_turn = None              # (facing before the turn, commanded degrees)
    for step in range(max_steps):
        if duel.contact.is_set():
            sh.log(f"[app {me.tag}] STOP -- the other side reached contact after {step} steps")
            return {"ok": True, "reason": "contact-other", "steps": step, "best": best,
                    "best_3d": me.best_3d, "track": track}
        if duel.stop.is_set():
            sh.log(f"[app {me.tag}] STOP -- the run was ended (kill signal or timeout) after "
                   f"{step} steps")
            return {"ok": False, "reason": "run-ended", "steps": step, "best": best,
                    "best_3d": me.best_3d, "track": track}
        if time.time() - t_start > max_seconds:
            sh.log(f"[app {me.tag}] STOP -- wall-clock cap {max_seconds}s")
            return {"ok": False, "reason": "time-cap", "steps": step, "best": best,
                    "best_3d": me.best_3d, "track": track}
        pme = true_pos(tail, facing)
        poth = true_pos(other.tail, duel.get_facing(other.tag))
        if pme is None or poth is None:
            sh.log(f"[app {me.tag}] STOP -- stale position rows "
                   f"(me={pme is not None} other={poth is not None})")
            return {"ok": False, "reason": "stale-rows", "steps": step, "best": best,
                    "best_3d": me.best_3d, "track": track}
        mx, my, mz, src_me = pme
        opos = (poth[0], poth[2])
        src = f"{src_me}/{poth[3]}"
        dist = math.hypot(opos[0] - mx, opos[1] - mz)
        # HEIGHT and TRUE RANGE. Ground distance alone cannot see a floor between the two
        # players; kill2 reported 33 units of ground gap while the true 3-D separation never got
        # below 50 and the median elevation was 43 deg.
        dy = poth[1] - my
        d3 = math.hypot(dist, dy)
        level = abs(dy) <= ENGAGE_DY_UNITS
        best = dist if best is None else min(best, dist)
        duel.set_dist(me.tag, d3)                    # the DUEL tracks the honest 3-D range
        me.best_3d = d3 if me.best_3d is None else min(me.best_3d, d3)
        # The corridor exists to leave the spawn bowl, not to reach the player: as soon as the
        # other side is within WAYPOINT_DROP_UNITS the chain is dropped and the target is the
        # player itself.
        target, tname = opos, "player"
        # Do not converge into a stack. Inside STACK_WATCH_UNITS of ground range with the heights
        # mismatched, the target becomes the nearest breadcrumb on this player's OWN trail at the
        # other player's height -- somewhere it has provably stood, at the height it needs.
        if not level and dist <= STACK_WATCH_UNITS:
            lt = level_target(tail, poth[1], (mx, mz))
            if lt:
                target, tname = lt[1], "level"
                sh.log(f"[app {me.tag}] STACKED: {dist:.1f} units apart on the ground, {dy:+.1f} "
                       f"apart vertically -- backing off {lt[0]:.0f} units to a breadcrumb at "
                       f"y={lt[2]:.1f} instead of closing")
            else:
                sh.log(f"[app {me.tag}] STACKED: {dist:.1f} on the ground, {dy:+.1f} vertically, "
                       f"and no breadcrumb of mine is at the other player's height -- closing "
                       f"anyway, the engagement will have to sweep pitch")
        # The corridor is a DESCENT (y 184.8 -> -4.5). Once this player is already at the other's
        # height there is nothing to gain by following it further down.
        elif me.route and level and wp < len(me.route):
            sh.log(f"[app {me.tag}] heights match ({dy:+.1f}) -- dropping the corridor at wp{wp} "
                   f"rather than descending past the other player")
            me.route = None
        if me.route and dist > WAYPOINT_DROP_UNITS:
            while wp < len(me.route) and math.hypot(me.route[wp][0] - mx,
                                                    me.route[wp][1] - mz) <= WAYPOINT_ARRIVE:
                wp += 1
            # ... and skip ahead whenever the NEXT point is already the nearer one, so a waypoint
            # the player cannot quite reach cannot pin the chain. The corridor is monotone in path
            # length, so the nearest point is the local one and this only ever advances.
            while (wp + 1 < len(me.route)
                   and math.hypot(me.route[wp + 1][0] - mx, me.route[wp + 1][1] - mz)
                   < math.hypot(me.route[wp][0] - mx, me.route[wp][1] - mz)):
                wp += 1
            if wp < len(me.route):
                target, tname = me.route[wp], f"wp{wp}"
        bearing = math.degrees(math.atan2(target[1] - mz, target[0] - mx))
        aim = wrap_deg(bearing + detour_sign * DETOUR_DEG) if detour_left > 0 else bearing
        err = wrap_deg(aim - facing)
        track.append({"step": step, "tag": me.tag, "me": [mx, my, mz],
                      "player_me": [mx, mz], "player_other": list(opos), "dist": dist,
                      "target": list(target), "target_name": tname, "facing": facing,
                      "bearing": bearing, "aim": aim, "err": err, "detour": detour_left,
                      "confident": confident, "turn_gain": me.turn_gain, "t": time.time(),
                      "dy": dy, "d3": d3, "level": level, "src": src,
                      "me_y": my, "other_y": poth[1]})
        sh.log(f"[app {me.tag}] step {step:2d} me=({mx:8.2f},{mz:8.2f}) other=({opos[0]:8.2f},"
               f"{opos[1]:8.2f}) d2={dist:8.2f} d3={d3:8.2f} dy={dy:+7.2f} tgt={tname:>6} "
               f"face={facing:7.2f} bear={bearing:7.2f} err={err:+7.2f} det={detour_left} "
               f"conf={int(confident)} gain={me.turn_gain:4.2f} src={src}")
        if shots and (step % shot_every == 0):
            sh.shot(f"app{step:02d}")
        if d3 <= engage and level:
            sh.log(f"[app {me.tag}] CONTACT: TRUE 3-D range {d3:.2f} <= {engage} AND heights "
                   f"{dy:+.2f} within {ENGAGE_DY_UNITS}, after {step} steps (src {src})")
            duel.contact.set()
            return {"ok": True, "reason": "contact", "steps": step, "dist": dist, "d3": d3,
                    "dy": dy, "best": best, "best_3d": me.best_3d, "track": track}
        if d3 <= arrive and level:
            sh.log(f"[app {me.tag}] ARRIVED: {dist:.2f} <= {arrive} units after {step} steps")
            return {"ok": True, "reason": "arrived", "steps": step, "dist": dist,
                    "best": best, "best_3d": me.best_3d, "track": track}
        deadband = approach_deadband(d3)
        if abs(err) > deadband:
            # The open-loop turn is the unreliable link (research/18 3.13: RMS 18 deg, and wtb2's
            # step 15 asked -72 and delivered -16). Ask for err/gain and let the next believed
            # burst say what was actually delivered.
            cmd = max(-179.0, min(179.0, err / max(me.turn_gain, 0.2)))
            mt = turn_by(sh, tail, cmd, abort=abort)
            applied = (mt["sweep_deg"] if (mt["kind"] == "rotation" and mt["sweep_deg"] is not None)
                       else cmd)
            pending_turn = (facing, err)
            facing = wrap_deg(facing + applied)
            confident = False
            track[-1]["turn_cmd"] = cmd
            track[-1]["turn_applied"] = applied
            if duel.contact.is_set():
                sh.log(f"[app {me.tag}] turn released -- the other side called contact")
                return {"ok": True, "reason": "contact-other", "steps": step, "best": best,
                        "best_3d": me.best_3d, "aborted_hold": "turn", "track": track}
        # A FULL burst is spent only on a facing that was measured by a believed burst and already
        # points at the target; everything else gets a probe whose only job is to measure the
        # facing again. This is the fix for wtb2's 38.6 % efficiency: its four biggest losses were
        # 150-185 unit bursts at straightness 0.93-0.97 walked on a dead-reckoned facing.
        if confident and abs(err) <= deadband and detour_left == 0:
            want = (math.hypot(target[0] - mx, target[1] - mz)
                    * WALK_STEP_FRACTION / WALK_UNITS_PER_S_LONG)
            secs = max(WALK_STEP_MIN_S, min(WALK_STEP_MAX_S, want))
            probe = False
        else:
            secs, probe = WALK_PROBE_S, True
        m = measure_hold(sh, tail, WALK_FORWARD_KEY, secs, settle=WALK_SETTLE_S,
                         rest=WALK_REST_S, label=f"{me.tag}app{step:02d}_walk", abort=abort)
        sh.log(fmt_hold(m))
        if duel.contact.is_set():
            # Do not score a burst that was cut short on purpose, and do not unstick from it.
            sh.log(f"[app {me.tag}] burst released after {m['hold_s']:.2f} of {secs:.2f} s -- "
                   f"the other side called contact")
            return {"ok": True, "reason": "contact-other", "steps": step, "best": best,
                    "best_3d": me.best_3d, "aborted_hold": "walk", "track": track}
        expect = WALK_UNITS_PER_S_LONG * max(m["hold_s"] - TURN_HOLD_LEAD_S, 0.0)
        good = (m["scale_ok"] and m["heading"] is not None
                and m["dist"] >= WALK_PROGRESS_FRACTION * expect
                and m["straight"] >= WALK_STRAIGHT_MIN)
        track[-1]["walk"] = {"hold_s": m["hold_s"], "dist": m["dist"], "straight": m["straight"],
                             "expect": expect, "scale_ok": m["scale_ok"], "believed": good,
                             "probe": probe}
        if good:
            if pending_turn is not None:
                f0, cmd_deg = pending_turn
                delivered = wrap_deg(m["heading"] - f0)
                if abs(cmd_deg) >= TURN_GAIN_MIN_CMD and delivered * cmd_deg > 0:
                    g = min(TURN_GAIN_MAX, max(TURN_GAIN_MIN, abs(delivered) / abs(cmd_deg)))
                    me.turn_gain = (1.0 - TURN_GAIN_ALPHA) * me.turn_gain + TURN_GAIN_ALPHA * g
                    sh.log(f"[app {me.tag}] turn gain: asked {cmd_deg:+.1f} deg, delivered "
                           f"{delivered:+.1f} -> gain {me.turn_gain:.2f}")
                pending_turn = None
            facing = m["heading"]                        # measured truth beats dead reckoning
            duel.set_facing(me.tag, facing)
            confident = True
            detour_left = 0                              # a believed burst ENDS the detour; wtb2
            blocks = 0                                   # decremented it and kept walking off-line
        else:
            why = ("scale" if not m["scale_ok"] else
                   "short" if m["dist"] is not None and m["dist"] < WALK_PROGRESS_FRACTION * expect
                   else "curved")
            sh.log(f"[app {me.tag}] step {step} burst not believed ({why}): moved {m['dist']} of "
                   f"{expect:.0f}, straightness {m['straight']} -- facing kept, detouring")
            confident = False
            blocks += 1
            if blocks % (DETOUR_STEPS + 1) == 0:
                detour_sign = -detour_sign
                sh.log(f"[app {me.tag}] {blocks} blocked bursts in a row -- detour the other way")
            detour_left = DETOUR_STEPS
            measure_hold(sh, tail, WALK_BACK_KEY, UNSTICK_BACK_S, settle=WALK_SETTLE_S,
                         rest=WALK_REST_S, label=f"{me.tag}app{step:02d}_unstick_back",
                         abort=abort)
            side = LATERAL_RIGHT_KEY if detour_sign > 0 else LATERAL_LEFT_KEY
            measure_hold(sh, tail, side, UNSTICK_LATERAL_UNITS / LATERAL_UNITS_PER_S,
                         settle=WALK_SETTLE_S, rest=WALK_REST_S,
                         label=f"{me.tag}app{step:02d}_unstick_side", abort=abort)
        if detour_left > 0 and not good:
            detour_left -= 1
    sh.log(f"[app {me.tag}] STOP -- step cap {max_steps} reached, best distance {best}")
    return {"ok": False, "reason": "step-cap", "steps": max_steps, "best": best,
            "best_3d": me.best_3d, "track": track}


def engage_fight(me, other, duel, seconds, shots=True):
    """Contact range: face the other player and sweep-fire.

    No open-loop aim is better than about +-20 deg and the shortest usable turn hold already
    sweeps 35-40 deg (research/18 3.13), so this COVERS the angle space with the shortest holds
    that turn at all rather than aiming at the target, and closes a little every cycle.
    """
    sh, tail = me.sh, me.tail
    t0 = time.time()
    cycle = 0
    while time.time() - t0 < seconds and not duel.stop.is_set():
        facing = duel.get_facing(me.tag)
        pme, poth = true_pos(tail, facing), true_pos(other.tail, duel.get_facing(other.tag))
        dist = d3 = None
        if pme is not None and poth is not None and facing is not None:
            mx, my, mz, src_me = pme
            opos = (poth[0], poth[2])
            dist = math.hypot(opos[0] - mx, opos[1] - mz)
            dy = poth[1] - my
            d3 = math.hypot(dist, dy)
            bearing = math.degrees(math.atan2(opos[1] - mz, opos[0] - mx))
            err = wrap_deg(bearing - facing)
            elev = math.degrees(math.atan2(dy, max(dist, 1e-6)))
            duel.set_dist(me.tag, d3)
            me.best_3d = d3 if me.best_3d is None else min(me.best_3d, d3)
            sh.log(f"[fight {me.tag}] cycle {cycle:2d} d2={dist:8.2f} d3={d3:8.2f} dy={dy:+7.2f} "
                   f"elev={elev:+6.1f}deg face={facing:7.2f} bear={bearing:7.2f} err={err:+7.2f} "
                   f"src={src_me}/{poth[3]}")
            # The approach refuses to converge into a stack; the ENGAGEMENT has to refuse too,
            # or `near = closest <= engage * 2.5` walks straight back into the kill2 condition --
            # stacked, out of range, sweeping at a floor. Same mechanism: steer to a breadcrumb on
            # this player's own trail at the other player's height, and do not fire this cycle.
            if abs(dy) > ENGAGE_DY_UNITS:
                lt = level_target(tail, poth[1], (mx, mz))
                sh.log(f"[fight {me.tag}] STACKED at contact: {dist:.1f} on the ground, {dy:+.1f} "
                       f"vertically ({elev:+.0f} deg) -- "
                       + (f"climbing {lt[0]:.0f} units to a breadcrumb at y={lt[2]:.1f} instead of "
                          f"firing at a floor" if lt else
                          "no breadcrumb of mine is at that height; holding fire this cycle"))
                if lt:
                    bx, bz = lt[1]
                    e = wrap_deg(math.degrees(math.atan2(bz - mz, bx - mx)) - facing)
                    if abs(e) > TURN_DEADBAND_DEG:
                        turn_by(sh, tail, e / max(me.turn_gain, 0.2))
                    m = measure_hold(sh, tail, WALK_FORWARD_KEY,
                                     max(WALK_STEP_MIN_S,
                                         min(WALK_STEP_MAX_S,
                                             lt[0] * 0.8 / WALK_UNITS_PER_S_LONG)),
                                     settle=WALK_SETTLE_S, rest=WALK_REST_S,
                                     label=f"{me.tag}fight{cycle:02d}_level")
                    if m["heading"] is not None and m["scale_ok"]:
                        duel.set_facing(me.tag, m["heading"])
                cycle += 1
                continue
            if abs(err) > TURN_DEADBAND_DEG:
                mt = turn_by(sh, tail, err / max(me.turn_gain, 0.2))
                if mt["kind"] == "rotation" and mt["sweep_deg"] is not None:
                    duel.set_facing(me.tag, wrap_deg(facing + mt["sweep_deg"]))
        # Cover the angle space in BOTH axes. Yaw: the bearing and one shortest-hold step either
        # side. Pitch: level, then ENGAGE_PITCH_STEPS holds one way and the same number back plus
        # the same again the other way, so neither the sign of I/K nor the sign of the height
        # difference has to be known. Every position gets two bursts.
        pitch_plan = [(None, 0)]
        if ENGAGE_SWEEP_PITCH:
            pitch_plan += ([(LOOK_UP_KEY, 1)] * ENGAGE_PITCH_STEPS
                           + [(LOOK_DOWN_KEY, -1)] * (2 * ENGAGE_PITCH_STEPS))
        pitch_at = 0
        for pkey, pstep in pitch_plan:
            if duel.stop.is_set():
                break
            if pkey:
                sh.pad(ENGAGE_PITCH_HOLD_S, sticks=[pkey])
                pitch_at += pstep
                time.sleep(0.15)
            for key in (None, LOOK_RIGHT_KEY, LOOK_LEFT_KEY):
                if duel.stop.is_set():
                    break
                if key:
                    sh.pad(ENGAGE_SWEEP_HOLD_S, sticks=[key])
                    time.sleep(0.15)
                for _ in range(2):
                    me.r1_times.append(time.time())
                    sh.pad(ENGAGE_FIRE_S, buttons=["R1"])
                    time.sleep(0.12)
            # the yaw sweep above nets one step left; put it back before the next pitch position
            sh.pad(ENGAGE_SWEEP_HOLD_S, sticks=[LOOK_RIGHT_KEY])
            time.sleep(0.15)
        # ... and level the pitch again, or the forward tap below measures a heading through a
        # camera that is looking at the sky.
        while pitch_at and not duel.stop.is_set():
            sh.pad(ENGAGE_PITCH_HOLD_S,
                   sticks=[LOOK_DOWN_KEY if pitch_at > 0 else LOOK_UP_KEY])
            pitch_at += -1 if pitch_at > 0 else 1
            time.sleep(0.15)
        if shots:
            sh.shot(f"fight{cycle:02d}")
        # KEEP CLOSING. kill2's engagement swept from a median 3-D range of 67.9 units and
        # never once came inside 45; sweeping from out of range is not an aim problem. The forward
        # burst doubles as the facing measurement.
        secs = ENGAGE_STEP_FORWARD_S
        if d3 is not None and d3 > ENGAGE_3D_UNITS:
            want = (d3 - ENGAGE_3D_UNITS) * 0.7 / WALK_UNITS_PER_S_LONG + TURN_HOLD_LEAD_S
            secs = max(ENGAGE_STEP_FORWARD_S, min(WALK_STEP_MAX_S, want))
        f, _ = facing_probe(sh, tail, seconds=secs, label=f"{me.tag}_fight_close")
        if f is not None:
            duel.set_facing(me.tag, f)
        cycle += 1
    return {"cycles": cycle}


# ---------------------------------------------------------------------------
# Sprint 5 Task 5 (b): the actor-matrix heading, partial-deflection aim, the teleport detector
# ---------------------------------------------------------------------------
# --- the actor-matrix heading and partial-deflection yaw (research/22 §3-§4) ----------------------------
ACTOR_MATRIX_ROW2_WORDS = (0xA0 // 4, 0xA8 // 4)   # actor +0xa0 / +0xa8 = matrix row 2 x / z (= -sin t, cos t)
AIM_TOL_DEG = 6.0                # the brief's closed-loop bar; a body subtends 15-20 deg at contact range
AIM_MAX_ITER = 6                 # rx holds per aim_yaw call, hard cap
# research/22 §3.1, single player, 1.0 s holds from rest: peak omega per |rx - 0x80|. <= 48 is dead (+48 read
# axis 0.000, -48 read 0.004); 64 read 8.21 / 9.22 deg/s (mean 8.7); 96 read 100.74 on both runs; 127 read
# 128.11 (the rate law omega = 2.0 rad/s x axis, confirmed). Linear between the points is an ASSUMPTION --
# the response is steep between 64 and 96 and was sampled at no level in between -- which is why aim_yaw
# re-measures what each hold delivered and never trusts the table open loop. Blind: SP vs online frame rate.
YAW_DEAD_ZONE = 48
YAW_TABLE = ((48, 0.0), (64, 8.7), (96, 100.7), (127, 128.1))
AIM_MIN_DEFLECTION = 64          # the smallest measured level that turns (49..63 were never sampled)
AIM_DEFLECTION_STEP = 4
# research/22 §3.1: +96 held 1.0 s swept 53.1-53.3 deg at a peak 100.7 deg/s, +127 swept 79.0 at 128.1 -- a
# dead time of ~0.4-0.47 s before the rate is reached (the same shape as TURN_HOLD_LEAD_S online, 0.44 s).
AIM_LEAD_S = 0.40
AIM_HOLD_MAX_S = 1.0             # one hold never exceeds this: the shooter's standing budget (~2 s) needs
                                 # the rest reads on either side of it to fit, so big turns take several holds
AIM_REST_ROWS = 2                # "wait for 2 rows with unchanged heading after any rx": the matrix is not valid
AIM_REST_TOL_DEG = 0.05          # within ~2.5 s of an rx hold (KNOWN §1) and drifted 0.000 deg at rest
AIM_REST_POS_UNITS = 0.5         # ... and the player itself not moving: heading while walking reads p90 ~54 deg
AIM_REST_TIMEOUT_S = 4.0         # no at-rest heading inside this -> NO-DATA, never a guess
AIM_POLL_S = 0.25                # one 4 Hz peek row
# The owner-requested review's default aim: SHORT pulses, the heading read AIM_PULSE_READ_S after each (research/22:
# at rest the matrix changed only on rx holds). aim_yaw(read="pulse").
AIM_PULSE_READ_S = 0.5
AIM_PULSE_MAX_S = 0.6            # a pulse for a small error never exceeds this (lead 0.4 s + 0.2 s of turn) ...
AIM_PULSE_LONG_ERR_DEG = 25.0    # ... but an error whose turn (err / gain) is larger than this gets a LONGER pulse,
AIM_PULSE_LONG_MAX_S = 1.6       # up to this (1.2 s of turn at 127 = ~153 deg), still read 0.5 s after it ends: at
                                 # <= 0.6 s a 179 deg error took 11 pulses (slice (b) review, lead 0.47 s)
AIM_PULSE_MAX_ITER = 6           # Amendment A3's bar: tolerance in <= 6 iterations on >= 80 % of aim cycles
AIM_DEAD_DELIVERED_DEG = 0.5     # a pulse that turned less than this (predicted >= AIM_GAIN_MIN_CMD_DEG) was DEAD ...
AIM_ESCALATE_DEFLECTION = 16     # ... so the side's deflection floor steps up by this (and the next hold by
AIM_ESCALATE_HOLD_S = 0.15       # this longer than the dead one) -- never the identical pulse again (slice (b) review
                                 # I2: a dead rx band, or a lead longer than AIM_LEAD_S)
# I7 (fix round, rv5f1/plant4.py: dead zone 90 + lead 0.47 + ramp 0.15 at 45 units never converged): one escalation per
# dead pulse -- the deflection floor first; the side's LEAD (and with it the hold) when the dead pulse's turn beyond
# its lead was shorter than AIM_DEAD_SHORT_TURN_S right after a deflection escalation; every delivered pulse decays the
# floor by AIM_DEFLECTION_STEP and the lead by AIM_LEAD_DECAY_S; a hold never plans a sweep beyond AIM_SWEEP_CAP x |err|
AIM_DEAD_SHORT_TURN_S = 0.15
AIM_LEAD_MAX_S = 0.85
AIM_LEAD_DECAY_S = 0.05
AIM_SWEEP_CAP = 1.5
AIM_GAIN_ALPHA = 0.5             # EMA of delivered/predicted sweep; the sim's world turns at 0.6-0.7x the table
AIM_GAIN_MIN, AIM_GAIN_MAX = 0.2, 3.0
AIM_GAIN_MIN_CMD_DEG = 2.0       # a predicted sweep below this is too small to estimate a gain from


def heading_from_matrix(words):
    """The walk facing, atan2(dz, dx) degrees, from an actor block's matrix: (-m[+0xa0], -m[+0xa8]) (research/22
    §4). None when the block is too short or row 2 is not a unit vector (an unfilled matrix)."""
    i, k = ACTOR_MATRIX_ROW2_WORDS
    if len(words) <= k:
        return None
    a, c = vc.f32(words[i]), vc.f32(words[k])
    if not (math.isfinite(a) and math.isfinite(c)) or abs(math.hypot(a, c) - 1.0) > 0.05:
        return None
    return math.degrees(math.atan2(-c, -a))


def yaw_rate_deg_s(deflection):
    """Table yaw rate (deg/s) for |rx - 0x80| = `deflection`: 0 inside the dead zone, piecewise linear and
    strictly increasing above it."""
    d = min(abs(deflection), 127)
    if d <= YAW_DEAD_ZONE:
        return 0.0
    for (d0, r0), (d1, r1) in zip(YAW_TABLE, YAW_TABLE[1:]):
        if d <= d1:
            return r0 + (r1 - r0) * (d - d0) / (d1 - d0)
    return YAW_TABLE[-1][1]


def aim_plan(err_deg, gain, hold_max=None, min_deflection=None, min_hold=0.0, lead=None, max_sweep=None):
    """-> (rx, seconds, predicted_deg): the rx value and hold length for a yaw error of `err_deg` given the
    side's measured gain (delivered / table). The smallest deflection >= `min_deflection` (AIM_MIN_DEFLECTION, or
    a side's escalated floor) whose turn fits in the hold cap; the hold is `lead` (AIM_LEAD_S, or a side's escalated
    lead) + the turn, at least `min_hold`; `predicted_deg` is what the TABLE says that hold sweeps (|err| / gain when
    it fits). `max_sweep` caps the table sweep a `min_hold` may add (I7, fix round: an escalated hold never plans more
    than that). Positive error -> rx right (LOOK_RIGHT_SIGN: rx right sweeps positive)."""
    lead = AIM_LEAD_S if lead is None else lead
    want = abs(err_deg) / min(max(gain, AIM_GAIN_MIN), AIM_GAIN_MAX)
    turn_max = max((AIM_HOLD_MAX_S if hold_max is None else hold_max) - lead, 0.05)
    floor = min(127, AIM_MIN_DEFLECTION if min_deflection is None else max(AIM_MIN_DEFLECTION, min_deflection))
    levels = [lv for lv in range(AIM_MIN_DEFLECTION, 127, AIM_DEFLECTION_STEP) if lv >= floor] + [127]
    d = levels[-1]
    for lv in levels:
        if want / yaw_rate_deg_s(lv) <= turn_max:
            d = lv
            break
    turn = min(max(want / yaw_rate_deg_s(d), min_hold - lead, 0.0), max(turn_max, min_hold - lead))
    if max_sweep is not None:
        turn = min(turn, max(want, max_sweep) / yaw_rate_deg_s(d))
    sign = 1 if err_deg * LOOK_RIGHT_SIGN > 0 else -1
    rx = max(0, min(255, vc.PAD_NEUTRAL + sign * d))
    return rx, lead + turn, yaw_rate_deg_s(d) * turn


def pulse_hold_max(err_deg, gain):
    """The pulse cap for this error: AIM_PULSE_MAX_S, or up to AIM_PULSE_LONG_MAX_S when the turn is large."""
    want = abs(err_deg) / min(max(gain, AIM_GAIN_MIN), AIM_GAIN_MAX)
    if want <= AIM_PULSE_LONG_ERR_DEG:
        return AIM_PULSE_MAX_S
    return min(AIM_PULSE_LONG_MAX_S, max(AIM_PULSE_MAX_S, AIM_LEAD_S + want / yaw_rate_deg_s(127)))


def _rest_heading(rows, since):
    """The newest heading row if the last AIM_REST_ROWS rows each repeat their predecessor (heading and position)
    and both began after `since` + one peek period; else None."""
    last = rows[-(AIM_REST_ROWS + 1):]
    if len(last) < AIM_REST_ROWS + 1:
        return None
    if since is not None and any(r[0] < since + PEEK_LEAD_S for r in last[1:]):
        return None
    for p, q in zip(last, last[1:]):
        if (abs(wrap_deg(q[1] - p[1])) > AIM_REST_TOL_DEG
                or math.hypot(q[2] - p[2], q[3] - p[3]) > AIM_REST_POS_UNITS):
            return None
    return last[-1]


def wait_rest_heading(tail, since, clock=time.time, wait=time.sleep, timeout=AIM_REST_TIMEOUT_S, on_poll=None):
    """Poll `tail.heading_rows` until an at-rest heading exists (see _rest_heading) -> (t, heading, x, z) | None.
    `on_poll()` runs at every poll; a True return means the player moved, so the rest wait starts over (the
    two-sided rule must not wait for a matrix to settle)."""
    t_end = clock() + timeout
    while True:
        with tail._lock:                                # noqa: SLF001 - same module
            rows = tail.heading_rows[-(AIM_REST_ROWS + 1):]
        r = _rest_heading(rows, since)
        if r is not None:
            return r
        if clock() >= t_end:
            return None
        if on_poll is not None and on_poll():
            since = clock()
            t_end = since + timeout
            continue
        wait(AIM_POLL_S)


def wait_pulse_heading(tail, since, clock=time.time, wait=time.sleep, timeout=AIM_REST_TIMEOUT_S, on_poll=None):
    """The newest heading row sampled at least AIM_PULSE_READ_S after `since` (the end of the last pulse or move)
    -> (t, heading, x, z) | None. `on_poll()` as in wait_rest_heading."""
    t_end = clock() + AIM_PULSE_READ_S + timeout
    while True:
        with tail._lock:                                # noqa: SLF001 - same module
            rows = tail.heading_rows[-1:]
        if rows and rows[-1][0] >= since + AIM_PULSE_READ_S:
            return rows[-1]
        if clock() >= t_end:
            return None
        if on_poll is not None and on_poll():
            since = clock()
            t_end = since + AIM_PULSE_READ_S + timeout
            continue
        wait(min(AIM_POLL_S, max(0.01, since + AIM_PULSE_READ_S - clock())) if clock() < since + AIM_PULSE_READ_S
             else AIM_POLL_S)


# --- the teleport detector -----------------------------------------------------------------------------------
# research/22 §3.1: in single player 45 of 47 row steps > 30 units fell inside rx holds (up to 380 units per 4 Hz row)
# and one 86-unit step came with the pad neutral; online partial deflection has never been run. Any attempt (an aim
# pulse, a walk leg) during which the actor's rows step further than this ABORTS with a teleport RESULT.
TELEPORT_STEP_UNITS = 30.0       # ground (x, z) step between consecutive rows of one actor
TELEPORT_SPEED_FACTOR = 2.0      # ... and more than twice what walking covers in that row gap: under load kill2 B ran
                                 # 1.08 s/row, i.e. a walking 43 units between two rows


class TeleportAbort(RuntimeError):
    def __init__(self, tag, during, step, t):
        super().__init__(f"teleport side={tag} during={during} step={step:.1f}u t={t:.2f}")
        self.tag, self.during, self.step, self.t = tag, during, step, t


def teleport_step(rows, t0, t1, limit=TELEPORT_STEP_UNITS, walking=True):
    """The first row in [t0, t1 + one peek period] whose ground step from the previous row of the SAME actor exceeds
    `limit` and, when `walking`, TELEPORT_SPEED_FACTOR x walking speed over the gap -> (t, step) | None. A STATIONARY
    window (an aim, a burst) gets no walking credit: on a 1.08 s/row sampler the credit hid a 43-unit jump (slice (b)
    review I3). Blind: a jump that lands within 30 units; a respawn onto a new actor block (the kill readout's)."""
    prev = None
    for r in sorted(r for r in rows if r[1] or r[2] or r[3]):
        if r[0] > t1 + PEEK_LEAD_S:
            break
        if prev is not None and r[0] >= t0 and prev[4] == r[4]:
            step = math.hypot(r[1] - prev[1], r[3] - prev[3])
            if step > limit and (not walking or step > TELEPORT_SPEED_FACTOR * WALK_UNITS_PER_S_LONG * (r[0] - prev[0])):
                return r[0], step
        prev = r
    return None


def aim_yaw(me, target_xz, tail, sh, clock=time.time, wait=time.sleep, fidget=None, on_poll=None, read="pulse",
            tol=None, max_iter=None):
    """Closed-loop yaw onto `target_xz` -> (err_before, err_after), degrees (None when no heading could be read).

    Each iteration reads the heading from the ACTOR MATRIX (never the camera: KNOWN §4) -- `read="pulse"` (the
    Amendment A default): AIM_PULSE_READ_S after each pulse and after the call starts (wait_pulse_heading);
    `read="rest"`: 2 unchanged rows after any rx (wait_rest_heading) -- computes the bearing from the actor's own x/z,
    and stops inside `tol` (default: spec §5.1's min(AIM_TOL_DEG, 0.8 atan(3.4 / d)) at the read's ground range d);
    otherwise it offers `fidget()` a chance to move first (a True return re-reads), then holds rx at a partial
    deflection from aim_plan and learns the side's gain from what the next read says the hold delivered. Pulses are
    capped at pulse_hold_max (a longer pulse for a large turn). A pulse that delivered nothing raises the side's
    deflection floor (`me.aim_floor`, kept across calls) and the next hold, so a dead pulse is never repeated
    identically. At most `max_iter` holds (AIM_PULSE_MAX_ITER = 6 / AIM_MAX_ITER). An actor row step >
    TELEPORT_STEP_UNITS between two reads raises TeleportAbort (counted on `me.aim_teleports`) -- with walking credit
    only if the player was moved in between (fidget / on_poll). Every read is recorded on `me.aims`. `on_poll()` is
    polled while waiting to read: a True return means it moved the player."""
    pulse = read == "pulse"
    max_iter = (AIM_PULSE_MAX_ITER if pulse else AIM_MAX_ITER) if max_iter is None else max_iter
    rec = {"tag": me.tag, "t0": clock(), "target": list(target_xz), "reads": [], "holds": [],
           "err_before": None, "err_after": None, "teleports": 0, "read": read, "tol": tol, "dead": 0}
    me.aims.append(rec)
    moved = [False]

    def poll():
        m = on_poll() if on_poll is not None else False
        if m:
            moved[0] = True
        return m
    since, rx_end, holds, fidgets = (clock() if pulse else None), None, 0, 0
    last_read_t = rec["t0"]
    pending = None                                      # (heading before, predicted deg, sign, (rx, secs)) of the last hold
    last_dead = None
    while True:
        r = (wait_pulse_heading(tail, since, clock, wait, on_poll=poll) if pulse
             else wait_rest_heading(tail, since, clock, wait, on_poll=poll))
        if r is None:
            sh.log(f"AIM {me.tag} NO-DATA: no {'post-pulse' if pulse else 'at-rest'} actor-matrix heading within "
                   f"{AIM_REST_TIMEOUT_S:g}s ({len(rec['reads'])} reads, {holds} holds) -- not aiming from a guess")
            rec["err_after"] = None
            return rec["err_before"], None
        t_r, h, x, z = r
        rec["reads"].append({"t": t_r, "heading": h, "x": x, "z": z, "after_rx": rx_end})
        hit = teleport_step(tail.actor_ingame(), last_read_t, t_r, walking=moved[0])
        if hit is not None:
            me.aim_teleports += 1
            rec["teleports"] += 1
            sh.log(f"AIM {me.tag} TELEPORT: an actor row stepped {hit[1]:.1f} units during the aim "
                   f"({'moved' if moved[0] else 'stationary: no walking credit'}; research/22 §3.1) -- the attempt "
                   f"is aborted")
            raise TeleportAbort(me.tag, "aim", hit[1], hit[0])
        last_read_t, moved[0] = t_r, False
        if pending is not None:
            h0, predicted, sign, plan = pending
            pending = None
            delivered = wrap_deg(h - h0)
            if predicted >= AIM_GAIN_MIN_CMD_DEG and abs(delivered) < AIM_DEAD_DELIVERED_DEG:
                # I7 (fix round): ONE escalation per dead pulse, never both at once -- the deflection first (a dead rx
                # band), the lead-and-hold when the dead pulse's turn was short or the last escalation was already the
                # deflection (a lead longer than planned), and the deflection again after a lead escalation
                rec["dead"] += 1
                last_dead = plan
                dev, lead_used = abs(plan[0] - vc.PAD_NEUTRAL), plan[2]
                floor0 = getattr(me, "aim_floor", AIM_MIN_DEFLECTION)
                short = plan[1] - lead_used < AIM_DEAD_SHORT_TURN_S
                if not short:                          # a long turn that delivered nothing: dead-band evidence
                    me.aim_dead_band = max(getattr(me, "aim_dead_band", 0), dev)
                if dev < 127 and (rec.get("escalated") != "deflection" or not short):
                    me.aim_floor = min(127, max(floor0, dev) + AIM_ESCALATE_DEFLECTION)
                    rec["escalated"] = "deflection"
                else:
                    me.aim_lead = min(AIM_LEAD_MAX_S, max(getattr(me, "aim_lead", AIM_LEAD_S), lead_used)
                                      + AIM_ESCALATE_HOLD_S)
                    rec["escalated"] = "lead"
                sh.log(f"AIM {me.tag} dead pulse rx={plan[0]} {plan[1]:.2f}s (turned {delivered:+.2f} deg of "
                       f"{predicted:.1f}) -- escalated the {rec['escalated']}: deflection floor "
                       f"{getattr(me, 'aim_floor', AIM_MIN_DEFLECTION)}, lead {getattr(me, 'aim_lead', AIM_LEAD_S):.2f}s")
            elif predicted >= AIM_GAIN_MIN_CMD_DEG:
                # a delivered pulse: the escalations decay (I7) -- the floor by one deflection step (never back into a
                # band a LONG pulse proved dead), the lead toward AIM_LEAD_S -- so a short-lived dead read never pins
                # every later aim at full deflection
                me.aim_floor = max(AIM_MIN_DEFLECTION, getattr(me, "aim_dead_band", 0) + AIM_ESCALATE_DEFLECTION,
                                   getattr(me, "aim_floor", AIM_MIN_DEFLECTION) - AIM_DEFLECTION_STEP)
                me.aim_lead = max(AIM_LEAD_S, getattr(me, "aim_lead", AIM_LEAD_S) - AIM_LEAD_DECAY_S)
                rec["escalated"] = None
                if delivered * sign > 0:
                    g = min(AIM_GAIN_MAX, max(AIM_GAIN_MIN, abs(delivered) / predicted))
                    me.yaw_gain = (1.0 - AIM_GAIN_ALPHA) * me.yaw_gain + AIM_GAIN_ALPHA * g
        d = math.hypot(target_xz[0] - x, target_xz[1] - z)
        tol_r = aim_tol_deg(d) if tol is None else tol
        err = wrap_deg(math.degrees(math.atan2(target_xz[1] - z, target_xz[0] - x)) - h)
        if rec["err_before"] is None:
            rec["err_before"] = err
        rec["err_after"], rec["tol"] = err, tol_r
        if abs(err) <= tol_r or holds >= max_iter:
            break
        if fidget is not None and fidgets < 2 * max_iter and fidget():
            fidgets += 1
            moved[0] = True
            since = clock()
            continue
        cap = pulse_hold_max(err, me.yaw_gain) if pulse else None
        floor = getattr(me, "aim_floor", AIM_MIN_DEFLECTION)
        lead = getattr(me, "aim_lead", AIM_LEAD_S)
        # I7: the hold is capped so the planned sweep stays <= AIM_SWEEP_CAP x |err| (in delivered degrees)
        sweep_cap = AIM_SWEEP_CAP * abs(err) / min(max(me.yaw_gain, AIM_GAIN_MIN), AIM_GAIN_MAX)
        rx, secs, predicted = aim_plan(err, me.yaw_gain, hold_max=None if cap is None else cap + lead - AIM_LEAD_S,
                                       min_deflection=floor, lead=lead, max_sweep=sweep_cap)
        if last_dead is not None and (rx, round(secs, 3)) == (last_dead[0], round(last_dead[1], 3)):
            me.aim_floor = min(127, floor + AIM_ESCALATE_DEFLECTION)       # never the identical dead pulse again
            rx, secs, predicted = aim_plan(err, me.yaw_gain, hold_max=None if cap is None else cap + lead - AIM_LEAD_S,
                                           min_deflection=me.aim_floor, lead=lead, max_sweep=sweep_cap)
        t_hold = clock()
        sh.pad(secs, axes={"rx": rx})
        rx_end = since = clock()
        holds += 1
        rec["holds"].append({"t": rx_end, "t_start": t_hold, "rx": rx, "s": round(secs, 3), "err": err,
                             "predicted": predicted, "gain": me.yaw_gain})
        pending = (h, predicted, 1 if err > 0 else -1, (rx, secs, lead))
    sh.log(f"AIM {me.tag} err {rec['err_before']:+.1f} -> {rec['err_after']:+.1f} deg in {holds} "
           f"{'pulses' if pulse else 'holds'} gain={me.yaw_gain:.2f} "
           f"({'ok' if abs(rec['err_after']) <= rec['tol'] else 'NOT within'} {rec['tol']:.2f})")
    return rec["err_before"], rec["err_after"]


class KillWatch(threading.Thread):
    """Decide, live, whether a death or a round end has happened -- and say WHICH signal fired.

    Three independent signals, because no single one of them is trustworthy on its own:

    1. `health` -- a word of the peeked player-actor block crossing into a range. Armed only when
       --health-offset names an ACTOR-RELATIVE byte offset confirmed across two kills (never an
       item index: PS2X_PEEK skips unresolved items and the ones after them shift down, so an
       index-based guard read the wrong block entirely); the brief forbids
       believing a candidate before that, so by default this signal is OFF and says so. It fires
       only on a TRANSITION -- an alive read then a dead read on the same actor address (see
       `_check_health`; tools_py/tests/test_kill_watch.py holds it to that).
    2. `respawn` -- the position record of either instance TELEPORTING (a jump no walk can make
       between two 4 Hz samples), or landing back within RESPAWN_RADIUS of the spawn it left. On a
       one-life round that is the round ending, which is what a kill causes.
    3. `server` -- a new MediusPlayerReport in the Horizon Medius log. This one is recorded and
       NEVER fires, and the reason is measured rather than assumed: in `ours_task8_kill1` exactly
       one MediusPlayerReport arrived, at T+156.7 s, with the two players 603 units apart, both
       still walking, and no respawn in either position record. It is a periodic client stats
       report, not a round boundary. Firing on it made that run print PASS for a round that had
       not ended -- which is the flattering positive this sprint keeps warning about. The DME TCP
       log is worse still: research/18 §1 measured a playing match and a frozen one as
       byte-identical there.

    The first FIRING signal wins and is named in the result; the observations keep being
    collected, so the run can say whether they agreed.
    """

    #: signals that may end a run. `server` is deliberately not among them (see above).
    #: Sprint 5 Task 3: `round` -- the round-state valves read by name bytes (mp_round_count steps,
    #: mp_game_over leaves 0, the clock string reaches 00:00) -- is the round-end signal, and
    #: `respawn` is DEMOTED to a fallback: it fires only while that instance's valves are NO-DATA,
    #: and is otherwise recorded as a non-firing observation. Neither is ever a PASS (result_verdict).
    FIRING = ("health", "round", "respawn")

    POLL_S = 0.25

    def __init__(self, tails, spawns, server_log=SERVER_LOG, health=None,
                 health_range=(-1e9, 0.0), clock=time.time, alive=None):
        super().__init__(daemon=True)
        self.tails, self.spawns, self.clock = tails, spawns, clock
        self.server_log, self.health, self.health_range = server_log, health, health_range
        # --alive-offset: the alive byte leaving ALIVE_VALUE on the actor that read alive is recorded as a
        # NON-firing `alive` observation (spec �5 Goal 2: it leaves 1 within 2 s of the health death).
        # It never ends a run on its own: a byte that also changes on a revive or a spectator switch is
        # corroboration, not attribution.
        self.alive = alive
        self._alive_state = {}
        self.events = []
        self.fired = None
        self._stop = threading.Event()
        self._seen = {t: 0 for t in tails}
        self._away = {t: False for t in tails}
        # Which row source each tag is being read from. The actor's own position is the truth; the
        # camera record is a fallback, and switching between them resets the cursor rather than
        # silently re-indexing one series against the other.
        self._src = {t: None for t in tails}
        # Per-instance health transition state: {tag: {seen, actor, alive}} (see _check_health).
        self._health_state = {}
        # Round state: rows already seen before the watch started seed the last values, so history
        # (the lobby, a previous round) is never replayed as a transition.
        self._round_seen, self._round_prev = {}, {}
        for tag, tail in tails.items():
            with tail._lock:                         # noqa: SLF001 - same module
                rows = list(getattr(tail, "round_rows", []))
            prev = {}
            for _, st in rows:
                for k, v in st.items():
                    if not isinstance(v, vc.NoData):
                        prev[k] = v
            self._round_seen[tag], self._round_prev[tag] = len(rows), prev
        try:
            self._server_pos = os.path.getsize(server_log)
        except OSError:
            self._server_pos = None

    def stop(self):
        self._stop.set()

    def rearm(self, t=None):
        """A new round (Amendment A2): the next firing signal may end it. Events are kept; a signal whose ROW is older
        than this moment (`t`, default now) never fires the new round -- even when this watch first polls it after the
        rearm (I1, fix round: wait_next_round sees the step row before KillWatch's poll does). The health state is kept
        per actor: the respawned actor reads alive again first."""
        self.rearmed_at = self.clock() if t is None else t
        self.fired = None

    def _add(self, kind, tag, detail, firing=None):
        ev = {"kind": kind, "tag": tag, "t": self.clock(), "detail": detail,
              "firing": (kind in self.FIRING) if firing is None else firing}
        row_t = detail.get("at") if isinstance(detail, dict) else None
        if (ev["t"] if row_t is None else row_t) < getattr(self, "rearmed_at", float("-inf")):
            ev["firing"] = False
        self.events.append(ev)
        if self.fired is None and ev["firing"]:
            self.fired = ev
        return ev

    def _check_positions(self):
        for tag, tail in self.tails.items():
            rows = tail.actor_ingame()
            src = "actor"
            if not rows:
                rows, src = tail.ingame(), "camera"
            if self._src[tag] != src:
                self._src[tag] = src
                self._seen[tag] = 0
                self._away[tag] = False
                if rows:
                    self.spawns[tag] = (rows[0][1], rows[0][3])
            spawn = self.spawns.get(tag)
            i = self._seen[tag]
            for j in range(max(i, 1), len(rows)):
                a, b = rows[j - 1], rows[j]
                d = math.hypot(b[1] - a[1], b[3] - a[3])
                far = (spawn is not None
                       and math.hypot(b[1] - spawn[0], b[3] - spawn[1]) > MOVED_AWAY_UNITS)
                if far:
                    self._away[tag] = True
                if d >= TELEPORT_UNITS:
                    fallback = not self.round_live(tag)
                    self._add("respawn", tag, {"jump": d, "from": [a[1], a[3]],
                                               "to": [b[1], b[3]], "fallback": fallback, "at": b[0]},
                              firing=fallback)
                elif (self._away[tag] and spawn is not None
                      and math.hypot(b[1] - spawn[0], b[3] - spawn[1]) <= RESPAWN_RADIUS):
                    self._away[tag] = False
                    fallback = not self.round_live(tag)
                    self._add("respawn", tag, {"back_at_spawn": [b[1], b[3]],
                                               "spawn": list(spawn), "fallback": fallback, "at": b[0]},
                              firing=fallback)
            self._seen[tag] = len(rows)

    #: an ALIVE read is a health float strictly above zero and at most full (1.0). Anything else --
    #: 0.0, NaN/inf, a heap fill such as 0xAFAFAFAF (~ -3.2e-10) or 0xD9D9D9D9, a huge value from a
    #: word that is not health at all -- is never evidence the actor was alive.
    ALIVE_RANGE = (0.0, 1.0)

    def _check_health(self):
        """A death counts only as a TRANSITION: the same actor address must first give an alive read
        (0 < v <= 1) and then a read inside `health_range`. State is per instance and per actor
        address; a change of address resets it. A first read of 0.0 or of uninitialised heap is
        therefore not a kill -- which is what this guard printed PASS for before."""
        if self.health is None:                      # 0 is a valid actor offset
            return
        lo, hi = self.health_range
        alive_lo, alive_hi = self.ALIVE_RANGE
        for tag, tail in self.tails.items():
            with tail._lock:                         # noqa: SLF001 - same module
                hist = list(tail.watch_hist)
            state = self._health_state.setdefault(tag, {"seen": 0, "actor": None, "alive": None})
            for t, raw, actor in hist[state["seen"]:]:
                if actor != state["actor"]:
                    state["actor"], state["alive"] = actor, None
                v = struct.unpack("<f", struct.pack("<I", raw))[0]
                if math.isfinite(v) and alive_lo < v <= alive_hi:
                    state["alive"] = (t, raw, v)
                elif not (math.isfinite(v) and lo <= v <= hi):
                    # Neither alive nor dead (NaN, inf, 5000.0, a word that is not health): the
                    # actor's last alive read no longer describes it, so it cannot be the "before".
                    state["alive"] = None
                elif state["alive"] is not None:
                    prev_t, prev_raw, prev_v = state["alive"]
                    self._add("health", tag, {"raw": raw, "value": v, "at": t,
                                              "offset": self.health, "actor": actor,
                                              "alive_raw": prev_raw, "alive_value": prev_v,
                                              "alive_at": prev_t})
                    state["alive"] = None            # one death per alive stretch
            state["seen"] = len(hist)

    def _check_alive(self):
        if self.alive is None:
            return
        for tag, tail in self.tails.items():
            with tail._lock:                         # noqa: SLF001 - same module
                hist = list(getattr(tail, "alive_hist", []))
            state = self._alive_state.setdefault(tag, {"seen": 0, "alive": None})
            for t, v, actor in hist[state["seen"]:]:
                if v == vc.ALIVE_VALUE:
                    state["alive"] = (t, actor)
                elif state["alive"] is not None and state["alive"][1] == actor:
                    self._add("alive", tag, {"value": v, "at": t, "actor": actor, "offset": self.alive,
                                             "alive_at": state["alive"][0]}, firing=False)
                    state["alive"] = None
                else:
                    state["alive"] = None
            state["seen"] = len(hist)

    def round_live(self, tag):
        """This instance's round valves (mp_round_count and mp_game_over, by name bytes) were read
        within ROUND_LIVE_MAX_AGE_S. While they are, `respawn` does not fire."""
        tail = self.tails[tag]
        t = getattr(tail, "round_valid_t", None)
        return t is not None and self.clock() - t <= ROUND_LIVE_MAX_AGE_S

    def _check_round(self):
        """`round` on a valve transition between two identified reads: mp_round_count changes,
        mp_game_over leaves 0, or the clock string becomes 00:00. `aiteam` (non-firing) when an
        aiteam_* count drops -- kill attribution is Task 6's, not this watch's. Blind: the valves'
        semantics are inference (research/19 F2); the clock's 00:00 is also a round end with no kill."""
        for tag, tail in self.tails.items():
            with tail._lock:                         # noqa: SLF001 - same module
                rows = list(tail.round_rows[self._round_seen[tag]:])
            self._round_seen[tag] += len(rows)
            prev = self._round_prev[tag]
            for t, st in rows:
                for name, v in st.items():
                    if isinstance(v, vc.NoData):
                        continue
                    p = prev.get(name)
                    if p is not None and v != p:
                        if name == "mp_round_count":
                            self._add("round", tag, {"valve": name, "from": p, "to": v, "at": t})
                        elif name == "mp_game_over" and p == 0:
                            self._add("round", tag, {"valve": name, "from": p, "to": v, "at": t})
                        elif name == "clock" and v == "00:00":
                            self._add("round", tag, {"valve": name, "from": p, "to": v, "at": t})
                        elif name.startswith("aiteam_") and v < p:
                            self._add("aiteam", tag, {"valve": name, "from": p, "to": v, "at": t},
                                      firing=False)
                    prev[name] = v

    def _check_server(self):
        if self._server_pos is None:
            return
        try:
            size = os.path.getsize(self.server_log)
        except OSError:
            return
        if size <= self._server_pos:
            self._server_pos = min(self._server_pos, size)
            return
        with open(self.server_log, "r", errors="replace") as f:
            f.seek(self._server_pos)
            chunk = f.read(size - self._server_pos)
        self._server_pos = size
        n = chunk.count(SERVER_ROUND_MARK)
        if n:
            self._add("server", "-", {"marks": n, "mark": SERVER_ROUND_MARK})

    def run(self):
        while not self._stop.is_set():
            try:
                self._check_health()
                self._check_alive()
                self._check_round()
                self._check_positions()
                self._check_server()
            except Exception as e:              # noqa: BLE001 - a watcher must not kill the run
                self.events.append({"kind": "watch-error", "tag": "-", "t": time.time(),
                                    "detail": repr(e)})
            self._stop.wait(self.POLL_S)


# ---------------------------------------------------------------------------
# Sprint 5 Task 3: a harness that cannot spend a match proving nothing
# ---------------------------------------------------------------------------
# Every verdict below is decided by the PURE scorers in verdict_core (one control bar, one move-path
# rule, valves by name bytes); this section only drives the pad, reads the tails and prints.

# --- the controllable precondition ------------------------------------------
PRECONDITION_HOLD_S = 2.0        # the spec's 2 s forward hold (spec §5 Goal 1)
# The drift clause needs the pad FULLY neutral (buttons included) over the 10 s before the hold, the
# window ending at the last actor row before the press. 10 s + kill2 B's worst row gap under load
# (1.08 s) + one 4 Hz row of arrival lag. Shorter, and every hold after the first is drift NO-DATA,
# because the turn between holds lands inside the window (frost1's probes were 9 s apart).
PRECONDITION_NEUTRAL_S = 11.5
# Score only once release + 2 s (the snap-back window) has rows: + one row of arrival lag (0.25 s)
# + the poll (0.05 s), rounded up.
PRECONDITION_SETTLE_S = 2.5
PRECONDITION_TURN_DEG = 90.0     # the heading is varied between holds: a controllable player whose
                                 # hold ran into geometry (kill2 A's Aapp00_walk: 2.00 s -> 21.72
                                 # units) gets a different wall, or none, on the next hold
PRECONDITION_MAX_ATTEMPTS = 6    # up to 4 DECISIVE holds (vc.PRECONDITION_MAX_HOLDS); NO-DATA holds
                                 # are retried, but never more than this many in total

# --- the move-path watch ----------------------------------------------------
MOVE_PATH_MAX_EVERY = 20         # at ~17-27 MoveScale calls/s, EVERY <= 20 logs >= ~1 line/s, so a
                                 # 10 s stall is ~10 missing lines; at the default 500 it is one line
                                 # per ~26 s and a healthy path looks stalled (plan instrument notes)
MOVE_PATH_POLL_S = 1.0
DEFAULT_HEALTH_OFFSET = 0x1044   # research/19 F1; Sprint 5 Task 2 read damage steps live in SP, no death (research/22)
DEFAULT_ALIVE_OFFSET = vc.ACTOR_ALIVE_OFFSET   # 0xF7A, same sources
ALIVE_PEEK_BASE = 0x408C58       # *0x408c58 = the player actor
ROUND_LIVE_MAX_AGE_S = 5.0       # valves read within this long count as live (20 rows at 4 Hz,
                                 # ~8 at kill2 B's 0.6 s/row under load)
FRAME_MAX_AGE_S = 2.0            # evidence screens (kill, final) must be fresher than this (spec Goal 6)


def _pad_event(t, sticks=()):
    """The pad state the harness itself wrote at host time t (PAD_AXIS full deflection, no buttons)."""
    axes = {"rx": vc.PAD_NEUTRAL, "ry": vc.PAD_NEUTRAL, "lx": vc.PAD_NEUTRAL, "ly": vc.PAD_NEUTRAL}
    for k in sticks:
        name, value = L.PAD_AXIS[k.upper()]
        axes[name] = value
    return vc.PadEvent(t, 0, axes["rx"], axes["ry"], axes["lx"], axes["ly"])


def _row_period(rows, t0, t1):
    win = [r[0] for r in rows if t0 <= r[0] <= t1]
    return (win[-1] - win[0]) / (len(win) - 1) if len(win) > 1 else None


def peer_freeze_label(peer, t0, t1):
    """'freeze(<tag>)' when the peer's round clock paused (freeze or round boundary) inside (t0, t1), else ''."""
    if peer is None:
        return ""
    tag, ptail = peer
    rt, steps, _, _ = tail_clock_state(ptail)
    p = pause_overlaps(vc.clock_pauses(rt, steps), t0, t1)
    return "" if p is None else f"{p[3]}({tag})"


def assert_controllable(side, tail, sh, clock=time.time, wait=time.sleep,
                        max_holds=vc.PRECONDITION_MAX_HOLDS, max_attempts=PRECONDITION_MAX_ATTEMPTS, peer=None):
    """Up to `max_holds` decisive 2 s forward holds on ACTOR rows, each preceded by 10+ s of fully
    neutral pad and, after the first, a 90 deg turn; each scored by vc.score_control (the spec's one
    bar). The side is CONTROLLABLE as soon as ANY hold passes, NO-CONTROL when every decisive hold
    failed, NO-DATA when none was decisive. Returns vc.SideControl.

    Pad timing is the harness's own write times (host clock); actor rows are host-timestamped on
    arrival by RunLogTail, i.e. up to one sampler period + the poll late. Blind: a half-decayed
    movement scale that still covers 40 units; motion in the wrong direction; a neutral-window drift
    that stays under 5 units because the player is frozen (hence the 40). The camera record
    0x416054 is never read here (kill3 B: it froze while the actor walked 67 units). `peer` = (tag, tail) of the
    other instance: a starved hold's retry reason says freeze(<tag>) when the peer's round clock stood still in the
    idle window behind it (R24; a frozen peer sends nothing, so the scale falls)."""
    events = [_pad_event(clock())]
    sh.pad(0.0)                                   # the file says neutral from here on
    verdicts, decisive = [], 0
    for attempt in range(max_attempts):
        if attempt:
            secs = turn_hold_seconds(PRECONDITION_TURN_DEG)
            events.append(_pad_event(clock(), [LOOK_RIGHT_KEY]))
            sh.pad(secs, sticks=[LOOK_RIGHT_KEY])
            events.append(_pad_event(clock()))
        wait(PRECONDITION_NEUTRAL_S)
        t0 = clock()
        events.append(_pad_event(t0, [WALK_FORWARD_KEY]))
        sh.pad(PRECONDITION_HOLD_S, sticks=[WALK_FORWARD_KEY])
        t1 = clock()
        events.append(_pad_event(t1))
        wait(PRECONDITION_SETTLE_S)
        rows = tail.actor_ingame()
        v = vc.score_control(rows, events, vc.Hold(t0, t1))
        starved = False
        if hasattr(tail, "scale_ok"):
            ok_s, n_s, lo_s, _ = tail.scale_ok(t0, t1)
            # Fix round 1 (I-2): MoveScale logged with f12 < 1.0 around the hold means the hold
            # measured the lag freeze, not the controls -> NO-DATA, retried. Zero MoveScale lines
            # (the silent move path, Frostfire) is not starvation evidence: the FAIL stands.
            starved = n_s > 0 and not ok_s and v.status == "FAIL"
            if starved:
                fz = peer_freeze_label(peer, t0 - SCALE_ALARM_IDLE_MS / 1000.0, t1 + PRECONDITION_SETTLE_S)
                v = vc.ControlVerdict(False, v.net_units, v.snapback_units, v.drift_units, vc.NO_DATA,
                                      f"scale {lo_s} < 1.0 around the hold (starved"
                                      f"{', ' + fz if fz else ''}, not a control verdict); was FAIL: {v.reason}",
                                      v.hold)
        verdicts.append(v)
        period = _row_period(rows, t0 - vc.CONTROL_DRIFT_WINDOW_S, t1 + vc.CONTROL_SNAPBACK_AFTER_RELEASE_S)
        scale = ""
        if hasattr(tail, "scale_ok"):
            ok, n, lo, hi = tail.scale_ok(t0, t1)
            if n == 0:
                scale = " scale=NO-DATA(0 MoveScale lines around the hold: the move path is silent)"
            else:
                scale = f" scale={'1.0' if ok else 'NOT-1.0'}({n},{lo}..{hi})"
                if starved:
                    scale += " [starved: retried as NO-DATA]"
        fmt = lambda x: "n/a" if x is None else f"{x:.2f}"
        sh.log(f"CONTROL {side} hold {attempt} {t1 - t0:.2f}s net={fmt(v.net_units)} "
               f"snap={fmt(v.snapback_units)} drift={fmt(v.drift_units)} rows={len(rows)} "
               f"period={fmt(period)}{scale} -> {v.status}{' (' + v.reason + ')' if v.reason else ''}")
        if v.status == "PASS":
            break
        if v.status == "FAIL":
            decisive += 1
            if decisive >= max_holds:
                break
    if any(v.status == "PASS" for v in verdicts):
        status = vc.CONTROLLABLE
    elif decisive:
        status = vc.NO_CONTROL
    else:
        status = vc.NO_DATA
    sh.log(f"CONTROL {side} side {status} ({len(verdicts)} hold(s), {decisive} decisive)")
    return vc.SideControl(status, verdicts)


def control_exit_code(result):
    """RESULT of the precondition -> process exit: 0 go, 3 NO-CONTROL (either form), 2 NO-DATA."""
    if result == vc.CONTROLLABLE:
        return 0
    if result.startswith(vc.NO_CONTROL):
        return 3
    return 2


def run_precondition(clients):
    """assert_controllable on every client at once (each on its own instance). -> (result, sides)."""
    sides, threads = {}, []
    for tag, c in clients.items():
        peer = next(((pt, pc.tail) for pt, pc in clients.items() if pt != tag), None)
        t = threading.Thread(target=lambda tg=tag, cl=c, pr=peer: sides.__setitem__(
            tg, assert_controllable(tg, cl.tail, cl.sh, peer=pr)))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    missing = [tag for tag in clients if tag not in sides]
    for tag in missing:                         # a thread that raised is a side with no verdict
        sides[tag] = vc.SideControl(vc.NO_DATA, [])
    return vc.control_result(sides), sides


# --- instrument specs -------------------------------------------------------
def _canon_chain(chain):
    return re.sub(r"0x[0-9a-f]+|\d+", lambda m: hex(int(m.group(0), 0)), chain.strip().lower())


def parse_peek_spec(spec):
    """PS2X_PEEK -> [(canonical chain, words, raw item)] (numbers normalised, e.g. `+0x0c` == `+0xc`)."""
    out = []
    for raw in (spec or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        chain, _, w = raw.partition(":")
        try:
            words = int(w, 0) if w else 1
        except ValueError:
            words = 0
        out.append((_canon_chain(chain), words, raw))
    return out


def _has_item(items, item, min_words):
    chain, _, w = item.partition(":")
    c = _canon_chain(chain)
    return any(ch == c and words >= min_words for ch, words, _ in items)


def move_path_preconditions(env, alive_offset=vc.ACTOR_ALIVE_OFFSET):
    """Why a MovePathWatch would attest to nothing under this environment ([] = it may start):
    MoveScale traced at PS2X_CALL_TRACE_EVERY <= 20, and the two disarm inputs peeked -- the actor
    block (vtable), a peek item covering actor+0xF7A, and mp_round_count's value AND name-bytes items.
    Without the disarm inputs verdict_core answers every stall NO-DATA, so the watch would be blind."""
    problems = []
    names = {e.split(":", 1)[1].strip() for e in env.get("PS2X_CALL_TRACE", "").split(",") if ":" in e}
    if MOVE_SCALE_TRACE_NAME not in names:
        problems.append(f"PS2X_CALL_TRACE has no {MOVE_SCALE_TRACE_NAME} slot (0x553dc0:{MOVE_SCALE_TRACE_NAME})")
    every = env.get("PS2X_CALL_TRACE_EVERY")
    try:
        every_n = int(every, 0) if every is not None else None
    except ValueError:
        every_n = None
    if every_n is None or not 1 <= every_n <= MOVE_PATH_MAX_EVERY:
        problems.append(f"PS2X_CALL_TRACE_EVERY={every if every is not None else 'unset (default 500)'} "
                        f"-- the watch needs 1..{MOVE_PATH_MAX_EVERY}")
    items = parse_peek_spec(env.get("PS2X_PEEK", ""))
    base = _canon_chain(f"*{ALIVE_PEEK_BASE:#x}")
    if not any(ch == base and words > max(vc.ACTOR_POS_WORDS) for ch, words, _ in items):
        problems.append(f"PS2X_PEEK has no actor block (*{ALIVE_PEEK_BASE:#x}:10 or wider)")
    covered = False
    for ch, words, _ in items:
        m = re.fullmatch(re.escape(base) + r"(?:\+(0x[0-9a-f]+))?", ch)
        if m:
            off = int(m.group(1), 16) if m.group(1) else 0
            if off <= alive_offset < off + 4 * min(words, 64):
                covered = True
    if not covered:
        problems.append(f"PS2X_PEEK covers no actor+{alive_offset:#x} (alive byte), e.g. "
                        f"*{ALIVE_PEEK_BASE:#x}+0xF78:1")
    rc = vc.VALVES["mp_round_count"]
    if not (_has_item(items, rc.value_item, 2) and _has_item(items, rc.name_item, 3)):
        problems.append(f"PS2X_PEEK lacks mp_round_count's {rc.value_item} and/or {rc.name_item}")
    return problems


def parse_offset(text):
    """--health-offset / --alive-offset: an int (0 is valid), or None for 'none'/'off'/''."""
    if text is None or str(text).strip().lower() in ("", "none", "off"):
        return None
    return int(str(text), 0)


def health_peek_problems(spec, health_offset):
    """Why an ARMED health watch would read nothing under this PS2X_PEEK ([] = covered). The watch reads
    actor+offset from whichever item covers it (RunLogTail), so an item chained off the actor static must
    span it; an armed watch with zero reads is a FAIL after the match, so refuse before it."""
    if health_offset is None:
        return []
    base = _canon_chain(f"*{ALIVE_PEEK_BASE:#x}")
    for ch, words, _ in parse_peek_spec(spec):
        m = re.fullmatch(re.escape(base) + r"(?:\+(0x[0-9a-f]+))?", ch)
        if m:
            off = int(m.group(1), 16) if m.group(1) else 0
            if off <= health_offset < off + 4 * min(words, 64):
                return []
    return [f"health watch armed at actor+{health_offset:#x} but PS2X_PEEK covers no actor+{health_offset:#x}, "
            f"e.g. *{ALIVE_PEEK_BASE:#x}+{health_offset:#x}:1 (or pass --health-offset none)"]


def launch_refusal_lines(env, alive_offset, health_offset):
    """The pre-launch refusal of a --converge run -> (lines to print, exit code); ([], 0) = launch.
    Each instrument refuses under its own label: the move-path watch's preconditions and the armed health
    watch's peek coverage are different failures and are named apart."""
    lines = []
    mp = move_path_preconditions(env, alive_offset=alive_offset if alive_offset is not None
                                 else vc.ACTOR_ALIVE_OFFSET)
    hp = health_peek_problems(env.get("PS2X_PEEK", ""), health_offset)
    lines += [f"MOVE-PATH WATCH REFUSES: {p}" for p in mp]
    lines += [f"HEALTH WATCH REFUSES: {p}" for p in hp]
    if mp:
        lines.append("RESULT NO-DATA move-path watch (not launched)")
    if hp:
        lines.append("RESULT NO-DATA health watch (not launched)")
    return lines, (2 if lines else 0)


def peek_spec_problems(spec):
    """Lint a PS2X_PEEK spec for the ways it has produced nothing before (non-fatal; printed)."""
    items = parse_peek_spec(spec)
    problems = []
    for ch, words, raw in items:
        if words > 64:
            problems.append(f"`{raw}` asks {words} words; PS2X_PEEK caps every item at 64 silently -- split it")
        if ch == _canon_chain("*0x43668c**"):
            problems.append("mission_abort: `*0x43668c**:3` dereferences the name bytes themselves "
                            "(@7373696d, research/21 §6.2) -- use `*0x43668c*:3`")
    for name, v in vc.VALVES.items():
        if _has_item(items, v.value_item, 2) and not _has_item(items, v.name_item, 3):
            problems.append(f"{name}: {v.value_item} without its name-bytes item {v.name_item} -- "
                            f"it will read NO-DATA {name}")
    return problems


def requested_valves(spec):
    items = parse_peek_spec(spec)
    return [name for name, v in vc.VALVES.items() if _has_item(items, v.value_item, 2)]


def valve_report(tag, tail, requested):
    """One line per requested valve: `VALVE <name> side=<tag> ok <n>/<rows>` or `NO-DATA <name>
    side=<tag> (<reason>)` when no row identified it by its name bytes."""
    lines = []
    with tail._lock:                                  # noqa: SLF001 - same module
        counts = {k: list(v) for k, v in tail.valve_counts.items()}
    for name in requested:
        ok, total, reason = counts.get(name, [0, 0, None])
        if ok == 0:
            lines.append(f"NO-DATA {name} side={tag} ({reason or 'never seen'}; {total} rows)")
        elif ok < total:
            lines.append(f"VALVE {name} side={tag} ok {ok}/{total} rows (NO-DATA on {total - ok}, last: {reason})")
        else:
            lines.append(f"VALVE {name} side={tag} ok {ok}/{total} rows")
    return lines


class MovePathWatchRefused(RuntimeError):
    """The environment would make the move-path watch attest to nothing (see move_path_preconditions)."""


class MovePathWatch(threading.Thread):
    """MoveScale liveness on every instance, live: vc.score_move_path over each tail's MoveScale #n,
    alive byte and mp_round_count (by name bytes). Logs every change of verdict; a stall line carries
    the R6 snap-back inputs (actor+0x420, DAT_004365c0, DAT_0045a0c1) when they are peeked, so the
    stall names its gap. `stalled` is the first (tag, verdict, now) that stalled.

    Refuses to START (raises MovePathWatchRefused at construction) unless MoveScale is traced at
    PS2X_CALL_TRACE_EVERY <= 20 and the disarm inputs are peeked. Blind: a stall under 10 s; a path
    that ticks but ignores the stick (assert_controllable's job); a tail call into MoveScale (the call
    trace misses `J` tail calls -- KNOWN §4; its callers are `jal`, research/21 §6.2)."""

    def __init__(self, tails, log, env=None, clock=time.time, name=MOVE_SCALE_TRACE_NAME):
        super().__init__(daemon=True)
        env = os.environ if env is None else env
        problems = move_path_preconditions(env)
        if problems:
            raise MovePathWatchRefused("; ".join(problems))
        self.tails, self.log, self.clock, self.name = tails, log, clock, name
        self.t0 = clock()                             # times in the lines are seconds since the watch started
        self.verdicts = {}
        self.history = []
        self.stalled = None
        # Task 5 finish (review I2): a freeze longer than FREEZE_MAX_S is NO-DATA, not an endless disarm -- the first
        # (tag, verdict, host now) that went NO-DATA that way; the run ends on it like on a stall
        self.freeze_nodata = None
        self.disarm_until = None
        self._noted = set()
        self._stop_ev = threading.Event()

    def rearm(self, t):
        """A round transition (Amendment A2): the move path is legitimately silent from the round end to the reset --
        disarm every side for ROUND_STEP_DISARM_S from host time `t`, whether or not the mp_round_count step was read."""
        self.disarm_until = t + vc.ROUND_STEP_DISARM_S
        self.log(f"MOVE-PATH re-armed for a new round: disarmed until +{vc.ROUND_STEP_DISARM_S:g}s")

    def check(self, now=None):
        t0 = self.t0
        now = (self.clock() if now is None else now) - t0
        out = {}
        for tag, tail in self.tails.items():
            with tail._lock:                          # noqa: SLF001 - same module
                calls = [(t - t0, n) for t, n, _ in tail.calls.get(self.name, [])]
                alive = [(t - t0, v) for t, v in tail.alive_rows]
                rounds = [(t - t0, st["mp_round_count"]) for t, st in tail.round_rows
                          if not isinstance(st["mp_round_count"], vc.NoData)]
                items = tail.latest_items
                round_time = [(t - t0, v) for t, v in getattr(tail, "round_time_rows", [])
                              if t - t0 >= now - PAUSE_LOOKBACK_S]
                n_rows = len(tail.round_rows)
            note_clock_missing(tag, n_rows, round_time, self._noted, self.log)
            v = vc.score_move_path(calls, alive, rounds, now)
            if v.status == "stalled" and self.disarm_until is not None:
                start = self.disarm_until - t0
                if now < start or now - max(start, v.since or start) < vc.MOVE_STALL_S:
                    v = vc.MovePathVerdict("disarmed", v.since, v.detail + f"; round transition: re-armed at "
                                                                          f"{start:.1f}")
            if v.status == "stalled":
                # Sprint 5 Task 5 freeze tolerance (launch 8c): while this instance's round clock 0x4365c0 stands
                # still the guest is frozen, not stalled -- and the stall clock restarts when the freeze ends. A
                # freeze longer than FREEZE_MAX_S is NO-DATA (nothing after it is evidence either).
                eps = freeze_episodes(round_time, now, round_steps=vc.round_steps(rounds))
                fe = eps[-1][1] if eps else None
                if eps and eps[-1][2] and now - eps[-1][0] > FREEZE_MAX_S:
                    v = vc.MovePathVerdict(vc.NO_DATA, v.since,
                                           v.detail + f"; freeze: round clock 0x4365c0 still since {eps[-1][0]:.1f}, "
                                           f"{now - eps[-1][0]:.1f}s > FREEZE_MAX_S {FREEZE_MAX_S:g}s")
                    if self.freeze_nodata is None:
                        self.freeze_nodata = (tag, v, now + t0)
                elif fe is not None and now - fe < vc.MOVE_STALL_S:
                    frozen = eps[-1][2]
                    v = vc.MovePathVerdict("disarmed", v.since,
                                           v.detail + (f"; freeze: round clock 0x4365c0 still since "
                                                       f"{eps[-1][0]:.1f}" if frozen else
                                                       f"; freeze: round clock 0x4365c0 ran again at {fe:.1f}, "
                                                       f"re-armed {vc.MOVE_STALL_S:g}s after"))
            prev = self.verdicts.get(tag)
            if prev is None or prev.status != v.status:
                since = "-" if v.since is None else f"{v.since:.1f}"
                ctx = f"; {vc.stall_context(items or [])}" if v.status == "stalled" else ""
                line = f"MOVE-PATH {tag} {v.status} since={since} -- {v.detail}{ctx}"
                self.log(line)
                self.history.append({"t": now, "tag": tag, "status": v.status, "line": line})
            if v.status == "stalled" and self.stalled is None:
                self.stalled = (tag, v, now + t0)       # host time of the first stall
            self.verdicts[tag] = v
            out[tag] = v
        return out

    def run(self):
        while not self._stop_ev.is_set():
            try:
                self.check()
            except Exception as e:                    # noqa: BLE001 - a watcher must not kill the run
                self.log(f"MOVE-PATH watch error {e!r}")
            self._stop_ev.wait(MOVE_PATH_POLL_S)

    def stop(self):
        self._stop_ev.set()


# ---------------------------------------------------------------------------
# Sprint 5 Task 5 (a): the run's paired closest approach, freeze tolerance, the two-sided starvation watch
# ---------------------------------------------------------------------------
# --- the paired 3-D range (Duel.best_dist / current_d3) ------------------------------------------------------
CURRENT_PAIR_MAX_AGE_S = 3.0     # a paired distance older than this is not "current"


class PairedRange:
    """Incremental verdict_core.score_contact pairing: each A actor row with the B row nearest in time within
    CONTACT_PAIR_MAX_S. `closest` / `closest_dy` are the TRUE run minimum and |dy| there; `current` is the
    newest pair (t, d3, |dy|). An A row is paired once a B row at or after its time exists, so no later B row
    can be nearer."""

    def __init__(self):
        self.closest = self.closest_dy = self.closest_t = self.current = None
        self.pairs = 0
        self._ia = 0

    def update(self, rowsA, rowsB):
        if not rowsB:
            return
        tb = [r[0] for r in rowsB]
        while self._ia < len(rowsA) and rowsA[self._ia][0] <= tb[-1]:
            a = rowsA[self._ia]
            self._ia += 1
            k = bisect.bisect_left(tb, a[0])
            cand = [j for j in (k - 1, k) if 0 <= j < len(rowsB) and abs(tb[j] - a[0]) <= vc.CONTACT_PAIR_MAX_S]
            if not cand:
                continue
            b = rowsB[min(cand, key=lambda j: abs(tb[j] - a[0]))]
            d3, dy = math.dist(a[1:4], b[1:4]), abs(a[2] - b[2])
            self.pairs += 1
            self.current = (a[0], d3, dy)
            if self.closest is None or d3 < self.closest:
                self.closest, self.closest_dy, self.closest_t = d3, dy, a[0]


# --- freeze tolerance (launch 8c, research/21 §9.8) ----------------------------------------------------------
# An instance whose guest stalls keeps writing peek rows while its round clock DAT_004365c0 stands still (8c:
# 3.3-17.3 s, main thread parked at 0x3b00a4). Its move path is silent (the live 10 s rule fired three times)
# and it sends nothing, so the OTHER instance's NetIdle alarms (peaks 8217 / 10338 ms). Neither is a defect of
# the side that reports it.
# Task 5 finish (slice (a) review): the definition is spec §5.1.1's, in verdict_core.clock_pauses -- a stall >= 1.0 s
# after merging stalls around one advancing row, or a clock rate < 25 % over a window; the pause from an mp_round_count
# step to the clock restart is a ROUND boundary, not a freeze.
FREEZE_CLOCK_STILL_S = vc.FREEZE_STALL_S
FREEZE_MAX_S = 20.0              # the longest freeze tolerated before it counts as NO-DATA (8c's worst: 17.3 s)
PAUSE_LOOKBACK_S = 120.0         # the live watches judge pauses over this much recent clock history (bounded work)
LAG_FLAG_IDLE_MS = 4501          # ng+0xde is set at idle >= 4501 ms: a flag alarm's idle window is at least this long
SCALE_ALARM_IDLE_MS = 5500       # f12 < 1.0 needs idle > 5500 ms


def freeze_episodes(rows, now=None, still_s=None, round_steps=()):
    """rows: [(t, round clock)] -> [(t_first, t_last, ongoing)] of the FREEZES (vc.clock_pauses kind 'freeze'; round
    boundaries excluded when `round_steps` are given). `now` is accepted for symmetry and not used. No rows -> []."""
    return [(a, b, g) for a, b, g, k in vc.clock_pauses(rows, round_steps, still_s or FREEZE_CLOCK_STILL_S)
            if k == "freeze"]


def frozen_now(rows, now, round_steps=()):
    eps = freeze_episodes(rows, now, round_steps=round_steps)
    return bool(eps and eps[-1][2])


def last_freeze_end(rows, now, round_steps=()):
    """The last row time of the newest freeze episode (ongoing or not), or None."""
    eps = freeze_episodes(rows, now, round_steps=round_steps)
    return eps[-1][1] if eps else None


def tail_clock_state(tail, since=None):
    """(round clock rows, mp_round_count step times, alive rows, peek rows seen) of a tail, clock rows from `since`."""
    with tail._lock:                                    # noqa: SLF001 - same module
        rt = [r for r in getattr(tail, "round_time_rows", []) if since is None or r[0] >= since]
        rounds = [(t, st["mp_round_count"]) for t, st in getattr(tail, "round_rows", [])
                  if not isinstance(st.get("mp_round_count"), vc.NoData)]
        alive = list(getattr(tail, "alive_rows", [])[-8:])
        n_rows = len(getattr(tail, "round_rows", []))
    return rt, vc.round_steps(rounds), alive, n_rows


CLOCK_MISSING_ROWS = 8           # peek rows seen with no 0x4365c0 in any of them before the watches say they are blind


def note_clock_missing(tag, n_rows, rt, noted, log):
    """Log ONCE per side that 0x4365c0 is absent from its peek rows (freezes then read as stalls or starvation)."""
    if rt or n_rows < CLOCK_MISSING_ROWS or tag in noted:
        return
    noted.add(tag)
    log(f"FREEZE-DETECTION {tag} blind: 0x4365c0 is not in {n_rows} peek rows -- a guest freeze cannot be told from "
        f"a stall or from starvation on this side (add 0x4365c0:1 to PS2X_PEEK)")


def pause_overlaps(pauses, t0, t1):
    """The newest pause strictly overlapping (t0, t1) -> (t_first, t_last, ongoing, kind) | None."""
    hit = [p for p in pauses if p[0] < t1 and p[1] > t0]
    return hit[-1] if hit else None


# --- the starvation watch (spec §5 Goal 5(c), both instances) -----------------------------------------------
STARVATION_POLL_S = 0.25
STARVATION_NODATA_S = 3.0        # no NetIdle row newer than this -> NO-DATA (EVERY=10 logs one per ~0.5 s at 20
                                 # calls/s, ~0.9 s at 8c's 11.5/s)
STARVATION_GRACE_S = 3.0         # rows may not exist yet when the watch starts
ALARM_CLEAR_S = 3.0              # spec §5(c): every alarm clears within 3 s of the other side moving


class StarvationWatch(threading.Thread):
    """verdict_core.score_starvation on both instances, live, over each side's NEWEST NetIdle `[ret] v0` and
    ng+0xde rows (primary ng+0xde, secondary NetIdle >= 4000 ms, verdict_core's own rules -- zero lag rows
    with a quiet NetIdle is NO-DATA, ruling R23), plus MoveScale f12 < 0.99 (Amendment A).

    * Guest-clock pauses are verdict_core.clock_pauses over each side's 0x4365c0 (spec §5.1.1): FREEZES, and the
      ROUND boundary from an mp_round_count step to the clock restart.
    * An alarm on side X opens an episode. Its idle window is [t - idle, t] (at least 4501 ms for an ng+0xde alarm,
      5500 ms for f12). If that window overlaps a pause of either instance, the cause is `freeze(Y)` / `round(Y)`:
      reported, not counted, nobody asked to move. An open starvation alarm whose window later overlaps a pause
      is re-attributed the same way. Otherwise the cause is starvation and it is counted; the other side is asked
      to move (take_request / request_event) only when BOTH round clocks are advancing -- a reaction, never a
      schedule. The mover reports moved().
    * An alarm still open ALARM_CLEAR_S after its mover moved sets `stop_reason`.
    * No fresh NetIdle row on a side (NetIdle stops with the move path) is NO-DATA and sets `stop_reason` -- except
      during that side's own pause (a freeze for at most FREEZE_MAX_S), while its alive byte reads != 1, within
      ROUND_STEP_DISARM_S of its round step, or within STARVATION_NODATA_S of max(its last NetIdle row, the end of
      its last pause) -- NetIdle resumes up to 2.6 s after the clock (launch 8c).
    Blind: idle peaks between NetIdle samples (0.5-0.9 s); a frozen instance whose clock still ticks."""

    def __init__(self, tails, log, clock=time.time):
        super().__init__(daemon=True)
        self.tails, self.log, self.clock = tails, log, clock
        self.tags = sorted(tails)
        self.t0 = clock()
        self.status = {tag: None for tag in self.tags}
        self.alarms = []
        self.stop_reason = None
        self.pauses = {tag: [] for tag in self.tags}
        self._noted = set()
        self._requests = {tag: threading.Event() for tag in self.tags}
        self._stop_ev = threading.Event()
        self._lock = threading.Lock()

    def _other(self, tag):
        return next(t for t in self.tags if t != tag)

    def _rows(self, tag, now=None):
        tail = self.tails[tag]
        since = None if now is None else now - PAUSE_LOOKBACK_S
        rt, steps, alive, n_rows = tail_clock_state(tail, since)
        with tail._lock:                                # noqa: SLF001 - same module
            idle = [(t, v) for name in vc.NET_IDLE_NAMES for t, _, v in tail.rets.get(name, [])]
            lag = list(getattr(tail, "lag_rows", []))
            f12 = [(t, f) for t, _, f in tail.calls.get(MOVE_SCALE_TRACE_NAME, []) if f is not None]
        idle = sorted(r for r in idle if r[0] >= self.t0)
        return {"idle": idle, "lag": [r for r in lag if r[0] >= self.t0], "rt": rt, "steps": steps, "alive": alive,
                "n_rows": n_rows, "f12": [r for r in f12 if r[0] >= self.t0]}

    def _advancing(self, rows, pauses, now):
        """This instance's round clock has rows within STARVATION_NODATA_S and is not paused now."""
        rt = rows["rt"]
        if not rt or now - rt[-1][0] > STARVATION_NODATA_S:
            return False
        return not (pauses and pauses[-1][2])

    def _stop(self, reason):
        if self.stop_reason is None:
            self.stop_reason = reason
            self.log(f"STARVATION-WATCH STOP: {reason}")

    @staticmethod
    def _window_s(signal, idle_ms):
        ms = idle_ms or 0
        if signal == "ng+0xde":
            ms = max(ms, LAG_FLAG_IDLE_MS)
        elif signal == "f12":
            ms = max(ms, SCALE_ALARM_IDLE_MS)
        return ms / 1000.0

    def _attribute(self, tag, t_from, t_to, pauses):
        """The pause (other side first) overlapping (t_from, t_to) -> 'freeze(Y)' / 'round(Y)' | None."""
        for side in (self._other(tag), tag):
            p = pause_overlaps(pauses[side], t_from, t_to)
            if p is not None:
                return f"{p[3]}({side})"
        return None

    def _no_netidle_status(self, tag, rows, pauses, now):
        """(status, detail) for a side with no NetIdle row in the last STARVATION_NODATA_S."""
        own = pauses[-1] if pauses and pauses[-1][2] else None
        if own is not None:
            if own[3] == "freeze" and now - own[0] > FREEZE_MAX_S:
                return vc.NO_DATA, (f"no NetIdle row in the last {STARVATION_NODATA_S:g}s; frozen "
                                    f"{now - own[0]:.1f}s > {FREEZE_MAX_S:g}s")
            return f"{own[3]}({tag})", ""
        alive = [r for r in rows["alive"] if now - r[0] <= vc.ALIVE_MAX_AGE_S]
        if alive and alive[-1][1] != vc.ALIVE_VALUE:
            return "disarmed", "+0xF7A != 1 (NetIdle stops with the move path on death)"
        if rows["steps"] and now - rows["steps"][-1] < vc.ROUND_STEP_DISARM_S:
            return "disarmed", f"mp_round_count stepped {now - rows['steps'][-1]:.1f}s ago"
        ref = max([self.t0 + STARVATION_GRACE_S - STARVATION_NODATA_S]
                  + [r[0] for r in rows["idle"][-1:]] + [p[1] for p in pauses])
        if now - ref <= STARVATION_NODATA_S:
            return self.status[tag], ""                  # a freeze just ended: NetIdle resumes up to 2.6 s later
        return vc.NO_DATA, (f"no NetIdle row in the last {STARVATION_NODATA_S:g}s (NetIdle stops with the move path)"
                            + (f"; last pause ended {now - pauses[-1][1]:.1f}s ago" if pauses else ""))

    def check(self, now=None):
        now = self.clock() if now is None else now
        with self._lock:
            rows = {tag: self._rows(tag, now) for tag in self.tags}
            pauses = {tag: vc.clock_pauses(rows[tag]["rt"], rows[tag]["steps"]) for tag in self.tags}
            self.pauses = pauses
            for tag in self.tags:
                note_clock_missing(tag, rows[tag]["n_rows"], rows[tag]["rt"], self._noted, self.log)
            for tag in self.tags:
                other = self._other(tag)
                r = rows[tag]
                fresh_idle = [x for x in r["idle"] if now - x[0] <= STARVATION_NODATA_S]
                fresh_lag = [x for x in r["lag"] if now - x[0] <= STARVATION_NODATA_S]
                signal, detail = None, ""
                if not fresh_idle:
                    status, detail = self._no_netidle_status(tag, r, pauses[tag], now)
                else:
                    v = vc.score_starvation(fresh_idle[-1:], fresh_lag[-1:], side=tag)
                    status, signal, detail = v.status, v.signal, v.detail
                    fresh_f12 = [x for x in r["f12"] if now - x[0] <= STARVATION_NODATA_S]
                    if status == "ok" and fresh_f12 and fresh_f12[-1][1] < vc.CONTACT_SCALE_MIN:
                        # Amendment A: a scale already below 0.99 is starvation too (the ng block may be unread)
                        status, signal = "alarm", "f12"
                        detail = f"MoveScale f12 {fresh_f12[-1][1]:g} < {vc.CONTACT_SCALE_MIN:g}; " + detail
                    if status == vc.NO_DATA and now - self.t0 < STARVATION_GRACE_S:
                        status = None
                if status == vc.NO_DATA:
                    self._stop(f"NO-DATA starvation side={tag}: {detail}")
                if status != self.status[tag]:
                    self.log(f"STARVATION side={tag} {status} -- {detail or signal or ''}".rstrip(" -"))
                self.status[tag] = status
                open_alarm = next((a for a in self.alarms if a["side"] == tag and a["t_clear"] is None), None)
                if status == "alarm" and open_alarm is None:
                    idle_ms = fresh_idle[-1][1] if fresh_idle else None
                    win = self._window_s(signal, idle_ms)
                    cause = self._attribute(tag, now - win, now, pauses) or "starvation"
                    a = {"side": tag, "t": now, "signal": signal, "cause": cause, "mover": other, "t_move": None,
                         "t_clear": None, "idle_ms": idle_ms, "window_s": win, "asked": False, "t_ask": None,
                         "clocks_ok": False}
                    self.alarms.append(a)
                    if cause == "starvation" and self._advancing(r, pauses[tag], now) and \
                            self._advancing(rows[other], pauses[other], now):
                        a["asked"], a["t_ask"], a["clocks_ok"] = True, now, True
                        self._requests[other].set()
                        self.log(f"STARVATION alarm side={tag} signal={signal} idle={idle_ms}ms -- "
                                 f"{other} must move (two-sided rule)")
                    elif cause == "starvation":
                        self.log(f"STARVATION alarm side={tag} signal={signal} idle={idle_ms}ms -- round clocks "
                                 f"not both advancing (0x4365c0 unread or still): counted, nobody asked to move")
                    else:
                        self.log(f"STARVATION alarm side={tag} signal={signal} idle={idle_ms}ms cause={cause} -- its "
                                 f"idle window [{now - win:.1f}, {now:.1f}] overlaps that pause: reported, not "
                                 f"counted, nobody asked to move")
                elif status == "ok" and open_alarm is not None:
                    open_alarm["t_clear"] = now
                    self._requests[other].clear()
                    ref = open_alarm["t_move"] if open_alarm["t_move"] is not None else open_alarm["t"]
                    self.log(f"STARVATION alarm side={tag} cleared {now - open_alarm['t']:.1f}s after it opened, "
                             f"{now - ref:.1f}s after " + ("the move" if open_alarm["t_move"] else "the alarm"))
                elif open_alarm is not None and open_alarm["cause"] == "starvation":
                    cause = self._attribute(tag, open_alarm["t"] - open_alarm["window_s"], now, pauses)
                    both = self._advancing(r, pauses[tag], now) and self._advancing(rows[other], pauses[other], now)
                    if cause is not None:
                        open_alarm["cause"] = cause
                        self._requests[other].clear()
                        self.log(f"STARVATION alarm side={tag} re-attributed to {cause}")
                    elif not open_alarm["asked"] and both:
                        # opened while a clock was unconfirmed: ask now, and judge the stop rule from here
                        open_alarm["asked"], open_alarm["t_ask"], open_alarm["clocks_ok"] = True, now, True
                        self._requests[other].set()
                        self.log(f"STARVATION alarm side={tag} re-asked: both round clocks confirmed "
                                 f"{now - open_alarm['t']:.1f}s after it opened -- {other} must move")
                    elif open_alarm["asked"] and not both and open_alarm["clocks_ok"]:
                        open_alarm["clocks_ok"] = False
                        self.log(f"STARVATION alarm side={tag}: a round clock stopped running during the alarm -- it "
                                 f"can no longer stop the engagement (spec §5.1: both clocks for its whole duration)")
                if (open_alarm is not None and open_alarm["cause"] == "starvation" and open_alarm["clocks_ok"]
                        and open_alarm["t_move"] is not None and now - open_alarm["t_move"] > ALARM_CLEAR_S):
                    self._stop(f"STARVATION alarm side={tag} not cleared within {ALARM_CLEAR_S:g}s of "
                               f"{other} moving")

    def new_round(self, t):
        """A new round (Amendment A2): the stop reason and open alarms belong to the round that ended; the NO-DATA grace
        restarts at `t`."""
        with self._lock:
            for a in self.alarms:
                if a["t_clear"] is None:
                    a["t_clear"] = t
                    a["closed_by"] = "round end"
            for ev in self._requests.values():
                ev.clear()
            self.stop_reason = None
            self.t0 = t
            self.status = {tag: None for tag in self.tags}

    def round_alarms(self, t0, t1=None):
        """The alarms opened in [t0, t1]."""
        return [a for a in self.alarms if a["t"] >= t0 and (t1 is None or a["t"] <= t1)]

    def take_request(self, tag):
        """True once per request for `tag` to move -- and only while the alarm that asked is still open: an alarm
        that cleared on its own (the side walked anyway) leaves no stale request behind."""
        ev = self._requests[tag]
        if not ev.is_set():
            return False
        ev.clear()
        with self._lock:
            return any(a["mover"] == tag and a["cause"] == "starvation" and a["t_clear"] is None and a["asked"]
                       for a in self.alarms)

    def request_event(self, tag):
        return self._requests[tag]

    def moved(self, tag, t):
        with self._lock:
            for a in self.alarms:
                if a["mover"] == tag and a["cause"] == "starvation" and a["t_clear"] is None and a["t_move"] is None:
                    a["t_move"] = t

    def starvation_alarms(self):
        return sum(1 for a in self.alarms if a["cause"] == "starvation")

    def alarms_cleared(self):
        return sum(1 for a in self.alarms if a["cause"] == "starvation" and a["t_clear"] is not None
                   and a["t_clear"] - (a["t_move"] if a["t_move"] is not None else a["t"]) <= ALARM_CLEAR_S)

    def freeze_alarms(self, kind="freeze"):
        """{side: n} of the alarms attributed to that side's `kind` pause ('freeze' or 'round')."""
        out = {}
        for a in self.alarms:
            if a["cause"].startswith(kind + "("):
                side = a["cause"][len(kind) + 1:-1]
                out[side] = out.get(side, 0) + 1
        return out

    def max_idle_ms(self):
        return {tag: max((v for _, v in self._rows(tag)["idle"]), default=None) for tag in self.tags}

    def lag_rows_read(self):
        return {tag: len(self._rows(tag)["lag"]) for tag in self.tags}

    def summary_line(self):
        fz = self.freeze_alarms()
        rd = self.freeze_alarms("round")
        return (f"STARVATION-WATCH alarms={self.starvation_alarms()} cleared={self.alarms_cleared()} "
                f"freeze_alarms={','.join(f'freeze({k})={v}' for k, v in sorted(fz.items())) or 0} "
                f"round_alarms={','.join(f'round({k})={v}' for k, v in sorted(rd.items())) or 0} "
                f"max_idle_ms={self.max_idle_ms()} lag_rows={self.lag_rows_read()} stop={self.stop_reason}")

    def run(self):
        while not self._stop_ev.is_set():
            try:
                self.check()
            except Exception as e:                      # noqa: BLE001 - a watcher must not kill the run
                self.log(f"STARVATION-WATCH error {e!r}")
            self._stop_ev.wait(STARVATION_POLL_S)

    def stop(self):
        self._stop_ev.set()


def result_verdict(fired, events, health_armed, watch_reads, stale_shots=(), stalled=None,
                   missing_shots=()):
    """The one RESULT word of a --converge run -> (verdict, is_kill). PASS is reserved for a health
    transition, and even then not from an instrument that read nothing on a side or from a kill
    screen older than FRAME_MAX_AGE_S. `round` (valves) and `respawn` (the fallback, used only while
    the valves are NO-DATA) end a round, which the clock does too: never a PASS."""
    if health_armed and (not watch_reads or min(watch_reads.values()) == 0):
        return (f"FAIL health watch armed with zero reads {watch_reads} -- 'health never moved' from an "
                f"instrument that never looked", False)
    kinds = {e["kind"] for e in events}
    if fired is not None and (fired["kind"] == "health" or "health" in kinds):
        base = "PASS" if fired["kind"] == "health" else "PASS (round end corroborated by a health transition)"
        if missing_shots:
            return (f"FAIL evidence-missing ({', '.join(missing_shots)}) -- no readable evidence frame", False)
        if stale_shots:
            return (f"FAIL kill screen stale ({', '.join(stale_shots)}) -- the frame file is older than "
                    f"{FRAME_MAX_AGE_S:g}s, so it is a picture of the past", False)
        return base, True
    if stalled is not None:
        tag, v = stalled[0], stalled[1]
        return f"FAIL move-path stalled side={tag} -- {v.detail}", False
    if fired is None:
        return "FAIL no kill or round-end signal", False
    if fired["kind"] == "respawn":
        return "ROUND-END (respawn fallback, the valves were NO-DATA; unattributed -- NOT a kill)", False
    return f"ROUND-END ({fired['kind']}; unattributed -- NOT a kill)", False


def evidence_shot(c, label, stale, log, missing=None):
    """A screen that is evidence (kill, final): a stale frame file goes to `stale`, a missing or
    unreadable one to `missing`; either blocks a PASS (result_verdict)."""
    try:
        c.sh.shot(label, max_age=FRAME_MAX_AGE_S)
    except winshot.StaleFrameError as e:
        stale.append(f"{c.tag}_{label}")
        log(f"STALE FRAME {c.tag}_{label}: {e}")
    except Exception as e:                            # noqa: BLE001
        if missing is not None:
            missing.append(f"{c.tag}_{label}")
        log(f"EVIDENCE MISSING {c.tag}_{label}: {e!r}")


# --- the clock round-end negative control (Sprint 5 Task 1 Step 5b; Task 6's free fixture) -----------
# After the precondition nobody fires: both sides alternate small strafe legs (each side's traffic feeds
# the OTHER side's idle counter, KNOWN §2 two-sided starvation) until the round ends on its clock. The run
# records that total_mp_kills, aiteam_* and actor+0x1044 do not step while mp_round_count does.
CONTROL_ROUND_CAP_S = 420.0
CONTROL_ROUND_LEG_S = (0.5, 0.8, 0.6, 0.9)   # cycled; inside the brief's 0.4-1.0 s lx legs
CONTROL_ROUND_AFTER_S = 15.0                  # rows kept after the round-end signal (reported, never scored)
CONTROL_ROUND_POLL_S = 0.25
CONTROL_ROUND_VALVES = ("mp_round_count", "mp_game_over", "total_mp_kills", "aiteam_00", "aiteam_08",
                        "player_team", "mp_major_game_state", "mp_minor_game_state")
CONTROL_ROUND_STEP_VALVES = ("total_mp_kills", "aiteam_00", "aiteam_08")


def control_round_state(items, health_offset=DEFAULT_HEALTH_OFFSET, alive_offset=DEFAULT_ALIVE_OFFSET):
    """One peek row's items -> {valve: value | NoData, 'clock', 'health', 'alive'}; valves by name bytes,
    actor fields through the vtable block."""
    st = {name: vc.row_valve(items, name) for name in CONTROL_ROUND_VALVES}
    st["clock"] = vc.row_clock_string(items)
    st["health"] = (vc.row_actor_field(items, health_offset, "f32") if health_offset is not None
                    else vc.NoData("health disarmed"))
    st["alive"] = (vc.row_actor_field(items, alive_offset, "u8") if alive_offset is not None
                   else vc.NoData("alive disarmed"))
    return st


def _known(v):
    return v is not None and not isinstance(v, vc.NoData)


def control_round_end(series):
    """series: {tag: [(t, state)]} -> (t, tag, detail) of the FIRST round-end signal on any side, or None.
    Signals (KillWatch._check_round's): mp_round_count changes, mp_game_over leaves 0, the clock string
    becomes 00:00 -- each a transition between two identified reads, so history is never a signal."""
    best = None
    for tag, rows in series.items():
        prev = {}
        for t, st in rows:
            hit = None
            for name in ("mp_round_count", "mp_game_over", "clock"):
                v, p = st.get(name), prev.get(name)
                if not _known(v):
                    continue
                if _known(p) and v != p and (name == "mp_round_count"
                                             or (name == "mp_game_over" and p == 0)
                                             or (name == "clock" and v == "00:00")):
                    hit = hit or f"{name} {p}->{v}"
                prev[name] = v
            if hit:
                if best is None or t < best[0]:
                    best = (t, tag, hit)
                break
    return best


def score_control_round(series, end_t=None):
    """-> dict: per side, the steps of total_mp_kills / aiteam_* (value changes between identified reads)
    and the health minimum and changes, counted strictly BEFORE the round-end time `end_t` (after it the
    round resets its counters, which is not a kill); the same step counts after `end_t` are reported apart."""
    out = {"round_ended": end_t is not None, "sides": {}}
    for tag, rows in series.items():
        side = {"steps": {}, "steps_after_end": {}, "values": {}, "health_min": None,
                "health_changes": 0, "alive_values": [], "alive_changes": 0}
        prev = {}
        for t, st in rows:
            before = end_t is None or t < end_t
            for name in CONTROL_ROUND_STEP_VALVES:
                v = st.get(name)
                if not _known(v):
                    continue
                seen = side["values"].setdefault(name, [])
                if not seen or seen[-1] != v:
                    seen.append(v)
                if name in prev and prev[name] != v:
                    key = "steps" if before else "steps_after_end"
                    side[key][name] = side[key].get(name, 0) + 1
                prev[name] = v
            h = st.get("health")
            if _known(h) and before:
                if side["health_min"] is None or h < side["health_min"]:
                    side["health_min"] = h
                if "health" in prev and prev["health"] != h:
                    side["health_changes"] += 1
                prev["health"] = h
            al = st.get("alive")
            if _known(al) and before:
                if al not in side["alive_values"]:
                    side["alive_values"].append(al)
                if "alive" in prev and prev["alive"] != al:
                    side["alive_changes"] += 1          # a death need not move the counters or the health word
                prev["alive"] = al
        for name in CONTROL_ROUND_STEP_VALVES:
            side["steps"].setdefault(name, 0)
        out["sides"][tag] = side
    return out


def control_round_result_line(score, end):
    sides = sorted(score["sides"])
    kills = sum(score["sides"][s]["steps"]["total_mp_kills"] for s in sides)
    ai = ",".join(f"{s}:{n}={score['sides'][s]['steps'][n]}" for s in sides for n in ("aiteam_00", "aiteam_08"))
    hmin = ",".join("n/a" if score["sides"][s]["health_min"] is None
                    else f"{score['sides'][s]['health_min']:g}" for s in sides)
    hch = ",".join(str(score["sides"][s]["health_changes"]) for s in sides)
    ach = ",".join(str(score["sides"][s]["alive_changes"]) for s in sides)
    sig = f" signal={end[2].replace(' ', '')} on={end[1]}" if end else ""
    return (f"RESULT CONTROL-ROUND round_ended={'yes' if end else 'no'} kills_stepped={kills} "
            f"aiteam_stepped={ai} health_min={hmin} health_changes={hch} alive_changed={ach}{sig}")


def control_round_arg_problem(a):
    """-> the refusal text when --control-round is combined with a mode that fires (R1), else None.
    --until-kill engages, --play fires bursts, --sweep fires at every step: any of them turns the
    negative control into a run that can kill."""
    if not getattr(a, "control_round", False):
        return None
    firing = [flag for flag, on in (("--until-kill", getattr(a, "until_kill", False)),
                                    ("--play", getattr(a, "play", 0)),
                                    ("--sweep", getattr(a, "sweep", 0))) if on]
    if firing:
        return (f"--control-round cannot run with {', '.join(firing)}: those press R1, and the negative "
                f"control requires that nobody fires")
    return None


def control_round_ok(score, end):
    """The negative control holds: the round ended, and nothing a kill moves stepped before it."""
    if end is None:
        return False
    for side in score["sides"].values():
        if any(side["steps"][n] for n in CONTROL_ROUND_STEP_VALVES) or side["health_changes"] or side["alive_changes"]:
            return False
    return True


def control_round(clients, log, clock=time.time, wait=time.sleep, cap_s=CONTROL_ROUND_CAP_S,
                  health_offset=DEFAULT_HEALTH_OFFSET, alive_offset=DEFAULT_ALIVE_OFFSET,
                  after_s=CONTROL_ROUND_AFTER_S):
    """Alternate lx strafe legs A, B, A, B (left, left, right, right, ...) with NO button ever pressed,
    sampling each tail's newest peek row, until the first round-end signal (then `after_s` of neutral
    observation) or `cap_s`. -> (series, end, score)."""
    tags = sorted(clients)
    series = {tag: [] for tag in tags}
    last = {tag: None for tag in tags}

    def collect():
        for tg in tags:
            tail = clients[tg].tail
            with tail._lock:                              # noqa: SLF001 - same module
                items = tail.latest_items
            if items is not None and items is not last[tg]:
                last[tg] = items
                series[tg].append((clock(), control_round_state(items, health_offset, alive_offset)))

    t0 = clock()
    collect()
    i, end = 0, None
    log(f"CONTROL-ROUND start: strafe legs {CONTROL_ROUND_LEG_S}s alternating {'/'.join(tags)}, "
        f"no buttons, cap {cap_s:g}s")
    while clock() - t0 < cap_s:
        tag = tags[i % len(tags)]
        key = LATERAL_LEFT_KEY if (i // len(tags)) % 2 == 0 else LATERAL_RIGHT_KEY
        clients[tag].sh.pad(CONTROL_ROUND_LEG_S[i % len(CONTROL_ROUND_LEG_S)], sticks=[key])
        i += 1
        collect()
        end = control_round_end(series)
        if end is not None:
            break
        if i % 80 == 0:
            parts = []
            for tg in tags:
                st = series[tg][-1][1] if series[tg] else {}
                parts.append(f"{tg}:clock={st.get('clock')} rc={st.get('mp_round_count')} "
                             f"kills={st.get('total_mp_kills')} health={st.get('health')}")
            log(f"CONTROL-ROUND T+{clock() - t0:.0f}s legs={i} " + " ".join(parts))
    if end is not None:
        log(f"CONTROL-ROUND round-end signal {end[2]} on {end[1]} at T+{end[0] - t0:.1f}s after {i} legs; "
            f"observing {after_s:g}s more, pad neutral")
        stop = clock() + after_s
        while clock() < stop:
            wait(CONTROL_ROUND_POLL_S)
            collect()
    else:
        log(f"CONTROL-ROUND cap {cap_s:g}s reached after {i} legs with no round-end signal")
    score = score_control_round(series, end[0] if end else None)
    return series, end, score


# ---------------------------------------------------------------------------
# Sprint 5 Task 5 (c): the engagement -- the recorded route, the endgame modes, the LADDER line
# ---------------------------------------------------------------------------
# Every piece below is driven by the pad and read from the tails; verdicts that already have a pure scorer
# (starvation, contact) are decided by verdict_core, so the live harness and the offline replay agree.

def endgame_preconditions(env):
    """Why the StarvationWatch / freeze tolerance would attest to nothing under this environment ([] = launch)."""
    problems = []
    names = {e.split(":", 1)[1].strip() for e in env.get("PS2X_CALL_TRACE", "").split(",") if ":" in e}
    if not names & set(vc.NET_IDLE_NAMES):
        problems.append("PS2X_CALL_TRACE has no NetIdle slot (0x30cd80:NetIdle) -- the starvation watch would be "
                        "NO-DATA from its first poll")
    items = parse_peek_spec(env.get("PS2X_PEEK", ""))
    if not (_has_item(items, "*0x437ce8:64", 64) and _has_item(items, "*0x437ce8+0x100:21", 7)):
        problems.append("PS2X_PEEK lacks the CZNetGame block *0x437ce8:64 + *0x437ce8+0x100:21 (ng+0xde, the "
                        "primary starvation signal)")
    if not _has_item(items, "0x4365c0:1", 1):
        problems.append("PS2X_PEEK lacks the round clock 0x4365c0:1 -- a frozen instance could not be told from "
                        "a starving one")
    return problems


def endgame_arg_problem(a):
    if getattr(a, "endgame", None) and getattr(a, "control_round", False):
        return (f"--endgame {a.endgame} cannot run with --control-round: every engagement mode (route, cooperative, "
                f"converge) fires, and the negative control requires that nobody does")
    return None


# --- the LADDER line and the damage verdict ------------------------------------------------------------------
def ladder_rung(controllable, contact_ok, damage):
    """0 not controllable on both; 1 no contact (spec §5.1: vc.score_contact(...).ok -- the band for >= 5.0 s over
    >= 10 rows; None = NO-DATA); 2 contact; 3 contact and damage."""
    if tuple(controllable) != ("yes", "yes"):
        return 0
    if not contact_ok:
        return 1
    return 3 if damage == "yes" else 2


def aim_iters_field(aims, t0=None, t1=None):
    """Amendment A3's reported aim bar, one token: `<ok>/<cycles>:<n>,<n>!,...` -- per aim cycle (an aim_yaw call that
    started in [t0, t1]) its iteration count, `!` when it ended outside its tolerance; `ok` counts cycles inside
    tolerance in <= AIM_PULSE_MAX_ITER. NO-DATA without cycles."""
    cyc = [a for a in aims if (t0 is None or a["t0"] >= t0) and (t1 is None or a["t0"] <= t1)]
    if not cyc:
        return vc.NO_DATA
    marks, ok = [], 0
    for a in cyc:
        good = a["err_after"] is not None and a.get("tol") is not None and abs(a["err_after"]) <= a["tol"]
        ok += good and len(a["holds"]) <= AIM_PULSE_MAX_ITER
        marks.append(f"{len(a['holds'])}{'' if good else '!'}")
    return f"{ok}/{len(cyc)}:{','.join(marks)}"


def record_lobby_fail(out_dir, n_rounds, exc, log, ident=""):
    """R47: a LobbyFail (exit 4) ends a ladder launch before any round -> the LADDER-SUMMARY line (0 rounds, 0 usable,
    stop=LOBBY-FAIL <class>) and converge.json {"lobby_fail": <class>, "rounds": [], ...}. Returns the class."""
    cls = getattr(exc, "cls", None) or "unclassified"
    log(online_ladder.lobby_fail_summary(n_rounds, cls, ident))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "converge.json"), "w") as fh:
        json.dump({"lobby_fail": cls, "detail": getattr(exc, "detail", ""), "rounds": [], "usable_rounds": 0,
                   "ladder_stop": f"{online_ladder.LOBBY_FAIL} {cls}"}, fh, indent=1)
    return cls


def rounds_arg_problem(a):
    """--rounds needs a watched engagement (route / cooperative); converge and the control round play one."""
    n = getattr(a, "rounds", 1)
    if not isinstance(n, int) or n < 1:
        return f"--rounds {n}: at least 1"
    if n > 1 and (getattr(a, "control_round", False) or getattr(a, "endgame", None) == "converge"):
        return "--rounds > 1 needs --endgame route or cooperative (converge and --control-round play one round)"
    return None


def harness_identity(root=None):
    """(commit, exe sha256 prefix) of the code and binary a launch runs: HARNESS_COMMIT / EXE_BUILD of a pinned snapshot
    (scripts/pin_harness.sh writes them at the snapshot root, which is this package's grandparent) when present;
    otherwise the live tree's HEAD marked `-live` and dist/socom2.exe hashed here. NO-DATA when unreadable."""
    root = root or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    commit = exe = vc.NO_DATA
    pinned = os.path.join(root, "HARNESS_COMMIT")
    if os.path.exists(pinned):
        with open(pinned) as f:
            commit = (f.read().strip() or vc.NO_DATA)[:12]
        build = os.path.join(root, "EXE_BUILD")
        if os.path.exists(build):
            with open(build) as f:
                m = re.search(r"sha256=([0-9a-fA-F]{16})", f.read())
            exe = m.group(1).lower() if m else vc.NO_DATA
        return commit, exe
    try:
        head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20)
        if head.returncode == 0 and head.stdout.strip():
            commit = head.stdout.strip()[:12] + "-live"
    except (OSError, subprocess.SubprocessError):
        pass
    binary = os.path.join("dist", "socom2.exe")
    if os.path.exists(binary):
        import hashlib
        h = hashlib.sha256()
        with open(binary, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        exe = h.hexdigest()[:16]
    return commit, exe


def identity_tokens(root=None):
    commit, exe = harness_identity(root)
    return f"harness={commit} exe={exe}"


def rx_pulse_table(me, clock=time.time, wait=time.sleep, table=None, seconds=None):
    """Amendment A3/A4's REPORTED rung-0 table: rx pulses of +-64/+-80/+-96 for 0.3 s each from rest, the actor-matrix
    heading read AIM_PULSE_READ_S after each -> [{"dev", "deg"}] (deg None when no heading or a row jumped). Logged
    one line per pulse; never a gate."""
    table = online_ladder.RUNG0_PULSE_TABLE if table is None else table
    seconds = online_ladder.RUNG0_PULSE_S if seconds is None else seconds
    out = []
    r0 = wait_pulse_heading(me.tail, clock() - AIM_PULSE_READ_S, clock, wait)
    for dev in table:
        t_p = clock()
        me.sh.pad(seconds, axes={"rx": vc.PAD_NEUTRAL + dev})
        r1 = wait_pulse_heading(me.tail, clock(), clock, wait)
        jump = teleport_step(me.tail.actor_ingame(), t_p, clock(), walking=False)
        deg = None if (r0 is None or r1 is None or jump is not None) else wrap_deg(r1[1] - r0[1])
        out.append({"dev": dev, "deg": deg})
        me.sh.log(f"RUNG0 rx-table {me.tag} rx={dev:+d} {seconds:g}s -> "
                  + ("NO-DATA" + (f" (a {jump[1]:.1f}u row jump)" if jump else "") if deg is None else f"{deg:+.2f} deg"))
        r0 = r1
    return out


def ladder_line(rung, controllable, contact_rows, rows_read, damage, kill, starvation_alarms, alarms_cleared,
                max_idle_ms, lagflag_rows, aim_iters=None, contact_s=None, sampler_s=None, round_n=None, mover=None,
                bp_waits=None, rung0=None):
    """The brief's one-line ladder result, with spec §5.1's contact time and the sampler period beside the contact
    rows. A field whose rows were zero reads NO-DATA (None, or 0 for a row count), never 0. `aim_iters`
    (aim_iters_field) is appended when given; `rung0` (round 1, online_ladder.rung0_report's token) LAST, as
    `RUNG0 <PASS | FAIL reason | NO-DATA reason>` (R68)."""
    nd = lambda v: vc.NO_DATA if v is None else str(v)
    rows = lambda v: vc.NO_DATA if not v else str(v)
    secs = lambda v: vc.NO_DATA if v is None else f"{v:.2f}"
    return (f"LADDER {'' if round_n is None else f'round={round_n} '}rung={rung} controllable={','.join(controllable)} "
            f"contact_s={secs(contact_s)} "
            f"contact_rows={nd(contact_rows)} sampler_s={secs(sampler_s)} "
            f"rows_read={rows(rows_read)} damage={damage} kill={kill} starvation_alarms={nd(starvation_alarms)} "
            f"alarms_cleared={nd(alarms_cleared)} max_idle_ms={','.join(nd(v) for v in max_idle_ms)} "
            f"lagflag_rows={','.join(rows(v) for v in lagflag_rows)}"
            + ("" if aim_iters is None else f" aim_iters={aim_iters}")
            + ("" if bp_waits is None else f" bp_waits={','.join(nd(v) for v in bp_waits)}")
            + ("" if mover is None else f" mover={mover}")
            + ("" if rung0 is None else f" RUNG0 {rung0}"))


def ladder_contact(tailA, tailB, t0=None, t1=None):
    """verdict_core.score_contact (spec §5.1: the band, >= 5.0 s, guest-clock pauses of either instance pausing the
    count) over the two live tails (one host clock: no alignment needed), actor rows limited to [t0, t1]."""
    inside = lambda t: (t0 is None or t >= t0) and (t1 is None or t <= t1)

    def take(tail):
        with tail._lock:                                # noqa: SLF001 - same module
            calls = list(tail.calls.get(MOVE_SCALE_TRACE_NAME, []))
            clock = [(t, st["clock"]) for t, st in tail.round_rows if not isinstance(st.get("clock"), vc.NoData)]
        rt, steps, _, _ = tail_clock_state(tail)
        return ([(t, n) for t, n, _ in calls], [(t, f) for t, _, f in calls if f is not None], clock, rt, steps)
    ca, sa, clk, rta, sta = take(tailA)
    cb, sb, clkb, rtb, stb = take(tailB)
    return vc.score_contact([r for r in tailA.actor_ingame() if inside(r[0])],
                            [r for r in tailB.actor_ingame() if inside(r[0])], ca, cb, clk or clkb, (sa, sb),
                            round_time_rows=(rta, rtb), round_steps=(sta, stb))


def _row_at(rows, t, max_age=vc.CONTACT_ROW_MAX_GAP_S):
    k = bisect.bisect_right([r[0] for r in rows], t) - 1
    return rows[k] if k >= 0 and t - rows[k][0] <= max_age else None


def damage_verdict(victim_hist, victim_rows, shooter_rows, r1_times):
    """Spec §5 Goal 5(d) -> 'yes' | 'no' | 'unarmed' (no watch) | NO-DATA (armed, zero reads). victim_hist:
    RunLogTail.watch_hist of +0x1044 [(t, raw word, actor)]. A drop is a read below the previous alive read
    (0 < v <= 1) on the same actor; it is damage when the pair is inside the engagement band (spec §5.1: |dy| <= 10,
    3-D <= 45) at that time, an R1
    was injected in the preceding 3 s, and the victim's y did not drop > 20 units in the preceding 2 s.
    Blind: an environmental damage source coinciding with a burst at a stationary target."""
    if victim_hist is None:
        return "unarmed"
    if not victim_hist:
        return vc.NO_DATA
    prev = None
    for t, raw, actor in victim_hist:
        v = vc.f32(raw)
        if (prev is not None and prev[1] == actor and 0.0 < prev[0] <= 1.0 and math.isfinite(v)
                and v < prev[0]):
            vr, sr = _row_at(victim_rows, t), _row_at(shooter_rows, t)
            fired = any(t - 3.0 <= r <= t for r in r1_times)
            ys = [r[2] for r in victim_rows if t - 2.0 <= r[0] <= t]
            fell = vr is not None and ys and max(ys) - vr[2] > 20.0
            contact = (vr is not None and sr is not None and math.dist(vr[1:4], sr[1:4]) <= vc.CONTACT_3D_MAX_UNITS
                       and abs(vr[2] - sr[2]) <= vc.CONTACT_DY_MAX_UNITS)
            if fired and contact and not fell:
                return "yes"
        prev = (v, actor)
    return "no"


# --- the default engagement: a recorded route, then close, aim with pulses, fire (--endgame route) -----------------
# Amendment A (A3, R44), from the owner-requested broad review: in launch 3c both sides stood ~48 s still at f12 = 1.0
# (NetIdle <= 1547 ms) and every recorded alarm fell inside a peer freeze or a stuck-mover window. So the default
# engagement is simple: the stander (B, the joiner) stands at its spawn; the mover (A, the host) follows a recorded
# waypoint route (tools_py/parity/routes/<map>.json, source rows cited) to the stander's floor, closes into the
# engagement band, stops, aims with short partial-rx pulses closed-loop on the actor matrix (read 0.5 s after each)
# and fires. Nobody oscillates; a side moves for the other only as a StarvationWatch reaction.
ROUTES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "routes")
ENGAGE_BAND_3D_UNITS = 45.0      # spec §5.1 (Amendment A): the engagement band -- same floor |dy| <= 10 and 3-D <= 45
ENGAGE_BAND_STOP_UNITS = 35.0    # close_to stops inside this: the band less a margin for drift while aiming
ENGAGE_BAND_STANDOFF_UNITS = 25.0  # ... with its walk legs sized to end this far off (the tolerance is 6 deg there)
ENGAGE_TOO_CLOSE_UNITS = 8.0     # inside this the mover backs off a leg first
ENDGAME_FIGHT_S = 150.0
OSC_DEFLECTION = 64              # |lx - 0x80| of every small strafe leg (reactions, the cooperative oscillation): meant
                                 # as "the smallest deflection that moves" -- NOT MEASURED ONLINE
RULE_LEG_S = 1.0                 # a reaction: one 1.0 s strafe leg by the side that was NOT starved
RULE_LEG_DEFLECTION = OSC_DEFLECTION   # traffic is what feeds the counter; a full-deflection second (~42 units) would walk
                                       # the shooter out of the band
ENDGAME_BURST_S = ENGAGE_FIRE_S
ENDGAME_BURST_GAP_S = 0.12
ROUTE_MAX_SPACING_UNITS = 100.0  # no two consecutive waypoints further apart (a longer leg is an unwalked guess)
ROUTE_ARRIVE_UNITS = 20.0        # a waypoint is reached this close (ground)
ROUTE_AIM_TOL_DEG = 12.0         # a leg is walked once the facing is this close to the bearing (12 deg over a 60-unit
                                 # leg is 12 units off the line; the next leg re-aims)
ROUTE_LEG_MIN_S, ROUTE_LEG_MAX_S = 0.3, 1.5   # one walk leg: at most ~60 units, then re-read the position
ROUTE_SETTLE_S = 2 * PEEK_LEAD_S # rows of the leg's end arrive before progress is scored
ROUTE_PROGRESS_UNITS = 6.0       # a leg that gained less than this toward its waypoint is blocked ...
ROUTE_STUCK_LEGS = 3             # ... and this many in a row fail the route (--mover swaps who walks)
ROUTE_MAX_LEGS = 120             # hard cap over a whole route or close


def aim_tol_deg(d3):
    """spec §5.1 (Amendment A): the aim tolerance at 3-D range d3 -- min(AIM_TOL_DEG, 0.8 * atan(3.4 / d3))."""
    return min(AIM_TOL_DEG, 0.8 * math.degrees(math.atan2(3.4, max(d3, 1e-6))))


# Task 5 finish (slice (c) review, controller rulings): the route FILE is an option of its own (--route), separate from
# the in-game --map; for --map frostfire it defaults to routes/frostfire_v2.json (rw24, derived from collision geometry)
# and the 3c-derived routes/frostfire.json stays loadable. v2 legs carry `expected_floor_y` (ramp legs rise 100 -> 142)
# and `clearance`: arrival and the off-floor check use each leg's floor y, and a narrow leg arrives closer.
ROUTE_DEFAULT_FILES = {"frostfire": "frostfire_v2.json"}
ROUTE_V2_MAX_SPACING_UNITS = 60.0
ROUTE_ARRIVE_NARROW_UNITS = 8.0  # a leg whose clearance is under ROUTE_NARROW_CLEARANCE (the 25-wide ramp mouth) arrives
ROUTE_NARROW_CLEARANCE = 15.0    # within this; a 0.3 s minimum leg is 12 units, so an overshoot lands within 8 again
ROUTE_FLOOR_TOL_Y = 6.0          # arrival: the actor's y within this of the leg's expected_floor_y
ROUTE_OFF_FLOOR_Y = 12.0         # en route: y outside [prev floor, this floor] by more than this is off the route
ROUTE_NO_PROGRESS_S = 12.0       # the best distance to the current waypoint (or the close target) must improve by
                                 # ROUTE_PROGRESS_UNITS within this: oscillating or sliding legs trip it (review I3)
ROUTE_TIME_FACTOR = 3.0          # a route's whole time budget: slack + this x its length at walking speed
ROUTE_TIME_SLACK_S = 20.0
CLOSE_MAX_S = 60.0               # a close's whole time budget (it starts <= ~45 units from the band)
SPAWN_MISMATCH_UNITS = 20.0      # a live spawn further than this from the route file's is NO-DATA spawn-mismatch
ROUND_RESET_SPAWN_UNITS = 20.0   # a jump landing this close to the side's spawn ...
ROUND_RESET_STEP_S = 15.0        # ... within this of an mp_round_count step is the round-end reset (8c: 5.5 s after)
ENDGAME_UNITS = 150.0            # the cooperative victim oscillates only while the shooter is this close (3-D)


def default_route_path(map_name, routes_dir=None):
    """The route file for `map_name`: ROUTE_DEFAULT_FILES, else routes/<map>.json when it exists, else None."""
    d = routes_dir or ROUTES_DIR
    name = (map_name or "").lower()
    path = os.path.join(d, ROUTE_DEFAULT_FILES.get(name, f"{name}.json"))
    return path if name and os.path.exists(path) else None


def load_route_table(map_name=None, routes_dir=None, path=None):
    """The parsed route file (`path`, else default_route_path(map_name)), or None when there is none."""
    path = path or default_route_path(map_name, routes_dir)
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def route_waypoints(table, mover):
    """-> [{x, z, y, floor_y, arrive, ramp, clearance}] of the mover's route (None without one). floor_y is the leg's
    expected_floor_y (the leg INTO this waypoint), falling back to the waypoint's own y; arrive is
    ROUTE_ARRIVE_NARROW_UNITS on a leg with clearance < ROUTE_NARROW_CLEARANCE."""
    if not table or mover not in table.get("routes", {}):
        return None
    out = []
    for w in table["routes"][mover]["waypoints"]:
        leg = w.get("leg_from_prev") or {}
        fy = leg.get("expected_floor_y", w.get("y"))
        clr = min(v for v in (w.get("clearance"), leg.get("min_clearance"), 1e9) if v is not None)
        out.append({"x": float(w["x"]), "z": float(w["z"]), "y": None if w.get("y") is None else float(w["y"]),
                    "floor_y": None if fy is None else float(fy), "ramp": bool(leg.get("ramp")), "clearance": clr,
                    "arrive": ROUTE_ARRIVE_NARROW_UNITS if clr < ROUTE_NARROW_CLEARANCE else ROUTE_ARRIVE_UNITS})
    return out


def route_for(map_name=None, mover="A", routes_dir=None, path=None):
    """The mover's waypoints (dicts, route_waypoints) toward the other side's floor, or None."""
    return route_waypoints(load_route_table(map_name, routes_dir, path), mover)


def map_spawn(map_name=None, tag="A", routes_dir=None, path=None):
    table = load_route_table(map_name, routes_dir, path)
    if not table or tag not in table.get("spawns", {}):
        return None
    s = table["spawns"][tag]
    return s["x"], s["y"], s["z"]


def problems_route_file(path):
    """Why a route file would walk nothing sound ([] = usable): missing file, a spawn or route missing, a waypoint
    spacing over the limit (60 for a version >= 2 file, else ROUTE_MAX_SPACING_UNITS), a leg without a numeric
    expected_floor_y (version >= 2 files, or any file whose legs carry one)."""
    if not path or not os.path.exists(path):
        return [f"route file {path} does not exist"]
    try:
        with open(path, encoding="utf-8") as f:
            table = json.load(f)
    except (OSError, ValueError) as e:
        return [f"route file {path} unreadable: {e}"]
    probs = []
    v2 = (table.get("version") or 0) >= 2
    limit = ROUTE_V2_MAX_SPACING_UNITS if v2 else ROUTE_MAX_SPACING_UNITS
    for tag in ("A", "B"):
        if tag not in table.get("spawns", {}):
            probs.append(f"{os.path.basename(path)}: no spawn {tag}")
        wps = table.get("routes", {}).get(tag, {}).get("waypoints")
        if not wps:
            probs.append(f"{os.path.basename(path)}: no route {tag}")
            continue
        for i, (p, q) in enumerate(zip(wps, wps[1:]), 1):
            d = math.dist((p["x"], p["z"]), (q["x"], q["z"]))
            if d > limit:
                probs.append(f"{os.path.basename(path)}: route {tag} wp{i - 1}->wp{i} spacing {d:.1f} > {limit:g}")
            fy = (q.get("leg_from_prev") or {}).get("expected_floor_y")
            if v2 and not isinstance(fy, (int, float)):
                probs.append(f"{os.path.basename(path)}: route {tag} leg into wp{i} has no numeric expected_floor_y")
            elif not v2 and not isinstance(q.get("y"), (int, float)):
                probs.append(f"{os.path.basename(path)}: route {tag} wp{i} has no y (a version-1 file's floor)")
    return probs


def _wp(w):
    if isinstance(w, dict):
        return w
    return {"x": float(w[0]), "z": float(w[1]), "y": None, "floor_y": None, "arrive": ROUTE_ARRIVE_UNITS,
            "ramp": False, "clearance": None}


def _walk_leg(me, target_xz, clock, wait, log, on_poll=None, back=False, stand_off=0.0):
    """Aim (pulses, ROUTE_AIM_TOL_DEG) at `target_xz`, then walk one leg toward it (or, `back`, away from a target that
    is too close) sized to the remaining ground distance less `stand_off`. -> (distance before, distance after) | None
    when a position or heading could not be read. Raises TeleportAbort when a row steps > TELEPORT_STEP_UNITS."""
    a = me.tail.actor_latest()
    if a is None:
        return None
    d0 = math.hypot(target_xz[0] - a[1], target_xz[1] - a[3])
    _, err = aim_yaw(me, target_xz, me.tail, me.sh, clock=clock, wait=wait, on_poll=on_poll, read="pulse",
                     tol=ROUTE_AIM_TOL_DEG)
    if err is None:
        return None
    t0 = clock()
    if back:
        secs = max(ROUTE_LEG_MIN_S, min(ROUTE_LEG_MAX_S, (stand_off - d0) / WALK_BACK_UNITS_PER_S))
        me.sh.pad(secs, sticks=[WALK_BACK_KEY])
    else:
        secs = max(ROUTE_LEG_MIN_S, min(ROUTE_LEG_MAX_S, (d0 - stand_off) / WALK_UNITS_PER_S_LONG))
        me.sh.pad(secs, sticks=[WALK_FORWARD_KEY])
    wait(ROUTE_SETTLE_S)
    hit = teleport_step(me.tail.actor_ingame(), t0, clock())
    if hit is not None:
        log(f"ROUTE {me.tag} TELEPORT: an actor row stepped {hit[1]:.1f} units during a walk leg -- attempt aborted")
        raise TeleportAbort(me.tag, "walk", hit[1], hit[0])
    b = me.tail.actor_latest()
    if b is None:
        return None
    return d0, math.hypot(target_xz[0] - b[1], target_xz[1] - b[3])


class Progress:
    """The no-progress budget: `best` must improve by ROUTE_PROGRESS_UNITS within ROUTE_NO_PROGRESS_S."""

    def __init__(self, clock):
        self.clock, self.best, self.t = clock, None, clock()

    def reset(self):
        self.best, self.t = None, self.clock()

    def stalled(self, d):
        if self.best is None or d < self.best - ROUTE_PROGRESS_UNITS:
            self.best, self.t = d, self.clock()
            return None
        idle = self.clock() - self.t
        return idle if idle > ROUTE_NO_PROGRESS_S else None


def follow_route(me, route, clock=time.time, wait=time.sleep, log=None, stop=None, on_poll=None):
    """Walk `route` (route_waypoints dicts, or (x, z) tuples) with aimed legs -> {"ok", "reason", "wp", "legs"}. A
    waypoint is reached inside its `arrive` distance with the actor's y within ROUTE_FLOOR_TOL_Y of the leg's floor y;
    the follower skips ahead whenever the next waypoint is already the nearer one (a corridor, not a rail). It fails on:
    ROUTE_STUCK_LEGS legs in a row gaining < ROUTE_PROGRESS_UNITS ("stuck at wpN"); no ROUTE_PROGRESS_UNITS gain on
    the best distance for ROUTE_NO_PROGRESS_S ("no progress"); the route's time budget; standing at a waypoint on the
    wrong floor, or leaving the legs' floor band en route ("floor"). TeleportAbort propagates. Reads only actor rows and
    the actor matrix."""
    log = log or me.sh.log
    route = [_wp(w) for w in route]
    wp, legs, stuck = 0, 0, 0
    a = me.tail.actor_latest()
    here0 = (a[1], a[3]) if a else (route[0]["x"], route[0]["z"])
    length = sum(math.dist((p["x"], p["z"]), (q["x"], q["z"])) for p, q in zip(route, route[1:]))
    length += math.dist(here0, (route[0]["x"], route[0]["z"])) if route else 0.0
    budget = ROUTE_TIME_SLACK_S + ROUTE_TIME_FACTOR * length / WALK_UNITS_PER_S_LONG
    t0, prog = clock(), Progress(clock)
    log(f"ROUTE {me.tag} start: {len(route)} waypoints, {length:.0f} units, time budget {budget:.0f}s")
    fail = lambda reason: {"ok": False, "reason": reason, "wp": wp, "legs": legs}
    while wp < len(route):
        if stop is not None and stop.is_set():
            return fail("stopped")
        if legs >= ROUTE_MAX_LEGS:
            return fail(f"leg cap {ROUTE_MAX_LEGS} at wp{wp}")
        if clock() - t0 > budget:
            return fail(f"time budget {budget:.0f}s exceeded at wp{wp}")
        a = me.tail.actor_latest()
        if a is None:
            return fail("stale actor rows")
        here = (a[1], a[3])
        pos = lambda w: (w["x"], w["z"])
        while wp + 1 < len(route) and math.dist(here, pos(route[wp + 1])) < math.dist(here, pos(route[wp])):
            wp += 1
            prog.reset()
        w = route[wp]
        d = math.dist(here, pos(w))
        if w["floor_y"] is not None and wp > 0 and route[wp - 1]["floor_y"] is not None:
            lo = min(route[wp - 1]["floor_y"], w["floor_y"]) - ROUTE_OFF_FLOOR_Y
            hi = max(route[wp - 1]["floor_y"], w["floor_y"]) + ROUTE_OFF_FLOOR_Y
            if not lo <= a[2] <= hi:
                return fail(f"off the route's floor before wp{wp} (y {a[2]:.1f} outside {lo:.0f}..{hi:.0f})")
        if d <= w["arrive"]:
            if w["floor_y"] is not None and abs(a[2] - w["floor_y"]) > ROUTE_FLOOR_TOL_Y:
                return fail(f"wrong floor at wp{wp} (y {a[2]:.1f}, the leg's floor {w['floor_y']:.1f})")
            log(f"ROUTE {me.tag} wp{wp} reached at ({here[0]:.1f},{a[2]:.1f},{here[1]:.1f})")
            wp, stuck = wp + 1, 0
            prog.reset()
            continue
        idle = prog.stalled(d)
        if idle is not None:
            return fail(f"no progress toward wp{wp} for {idle:.1f}s (best {prog.best:.1f} units)")
        leg = _walk_leg(me, pos(w), clock, wait, log, on_poll=on_poll)
        legs += 1
        if leg is None:
            return fail("NO-DATA heading or position")
        if leg[0] - leg[1] < ROUTE_PROGRESS_UNITS:
            stuck += 1
            log(f"ROUTE {me.tag} wp{wp}: leg gained {leg[0] - leg[1]:.1f} units ({stuck}/{ROUTE_STUCK_LEGS})")
            if stuck >= ROUTE_STUCK_LEGS:
                return fail(f"stuck at wp{wp}")
        else:
            stuck = 0
    return {"ok": True, "reason": "arrived", "wp": wp, "legs": legs}


def close_to(me, other, clock=time.time, wait=time.sleep, log=None, stop=None, on_poll=None,
             stop_d3=None, stand_off=None):
    """Walk aimed legs toward the OTHER actor's live position until it is on this floor (|dy| <= ENGAGE_DY_UNITS) and
    inside `stop_d3` (ENGAGE_BAND_STOP_UNITS), legs sized to end `stand_off` (ENGAGE_BAND_STANDOFF_UNITS) short ->
    {"ok", "reason", "legs", "d3"}. Off the floor is a failure: the route's job was to get there. Stuck, no-progress
    (on the best 3-D distance) and CLOSE_MAX_S budgets as in follow_route."""
    log = log or me.sh.log
    stop_d3 = ENGAGE_BAND_STOP_UNITS if stop_d3 is None else stop_d3
    stand_off = ENGAGE_BAND_STANDOFF_UNITS if stand_off is None else stand_off
    legs, stuck, t0, prog = 0, 0, clock(), Progress(clock)
    while True:
        if stop is not None and stop.is_set():
            return {"ok": False, "reason": "stopped", "legs": legs}
        a, b = me.tail.actor_latest(), other.tail.actor_latest()
        if a is None or b is None:
            return {"ok": False, "reason": "stale actor rows", "legs": legs}
        dy, d3 = b[2] - a[2], math.dist(a[1:4], b[1:4])
        if abs(dy) > ENGAGE_DY_UNITS:
            return {"ok": False, "reason": f"off the target's floor (dy {dy:+.1f})", "legs": legs, "d3": d3}
        if d3 <= stop_d3:
            return {"ok": True, "reason": "closed", "legs": legs, "d3": d3}
        if legs >= ROUTE_MAX_LEGS:
            return {"ok": False, "reason": f"leg cap {ROUTE_MAX_LEGS}", "legs": legs, "d3": d3}
        if clock() - t0 > CLOSE_MAX_S:
            return {"ok": False, "reason": f"time budget {CLOSE_MAX_S:g}s exceeded closing", "legs": legs, "d3": d3}
        idle = prog.stalled(d3)
        if idle is not None:
            return {"ok": False, "reason": f"no progress closing for {idle:.1f}s (best {prog.best:.1f})", "legs": legs,
                    "d3": d3}
        leg = _walk_leg(me, (b[1], b[3]), clock, wait, log, on_poll=on_poll, stand_off=stand_off)
        legs += 1
        if leg is None:
            return {"ok": False, "reason": "NO-DATA heading or position", "legs": legs}
        stuck = stuck + 1 if leg[0] - leg[1] < ROUTE_PROGRESS_UNITS else 0
        if stuck >= ROUTE_STUCK_LEGS:
            return {"ok": False, "reason": "stuck closing", "legs": legs, "d3": d3}


def is_round_reset(hit, rows, spawn, round_steps):
    """A teleport `hit` (t, step) that lands within ROUND_RESET_SPAWN_UNITS of `spawn` (x, y, z) within
    ROUND_RESET_STEP_S of an mp_round_count step is the round-end reset to spawn (KNOWN §4; 8c: at the clock restart,
    5.5 s after the step) -- a round boundary, not a FAIL teleport."""
    if hit is None or spawn is None:
        return False
    land = next((r for r in reversed(rows) if r[0] == hit[0]), None)
    if land is None or math.hypot(land[1] - spawn[0], land[3] - spawn[2]) > ROUND_RESET_SPAWN_UNITS:
        return False
    return any(abs(hit[0] - s) <= ROUND_RESET_STEP_S for s in round_steps)


def round_reset_classifier(spawns=None):
    """-> classify(side, hit): True when the jump `hit` is the round-end reset to the side's spawn (`spawns` {tag: xyz},
    else the side's first in-game actor row) near an mp_round_count step (is_round_reset)."""
    def classify(side, hit):
        spawn = (spawns or {}).get(side.tag)
        if spawn is None:
            rows = side.tail.actor_ingame()
            spawn = rows[0][1:4] if rows else None
        return is_round_reset(hit, side.tail.actor_ingame(), spawn, tail_clock_state(side.tail)[1])
    return classify


def fire_window_teleport(out, sides, t0, t1, log, classify=None):
    """Amendment A3: a teleport of either player inside a fire window [t0, t1] (the burst and its gap, no walking
    credit -- both stand) makes the round NO-DATA. Sets out['fire_teleport'] / out['stop_reason'] -> True on a hit.
    `classify(side, hit)` True marks the jump a round-end reset instead (out['round_end'])."""
    for side in sides:
        hit = teleport_step(side.tail.actor_ingame(), t0, t1, walking=False)
        if hit is not None:
            if classify is not None and classify(side, hit):
                out["round_end"] = {"tag": side.tag, "t": hit[0], "step": hit[1]}
                out["stop_reason"] = f"ROUND-END reset to spawn side={side.tag}"
                log(f"ENDGAME {out['stop_reason']} (a jump of {hit[1]:.1f}u within {ROUND_RESET_STEP_S:g}s of a round step)")
                return True
            out["fire_teleport"] = {"tag": side.tag, "step": hit[1], "t": hit[0], "window": [t0, t1]}
            out["stop_reason"] = (f"NO-DATA teleport in a fire window side={side.tag} step={hit[1]:.1f}u -- the round "
                                  f"is not scored (Amendment A3)")
            log(f"ENDGAME {out['stop_reason']}")
            return True
    return False


FIRE_WINDOW_RECHECK_S = 10.0     # a freeze is only visible >= 1 s after it starts: recent fire windows are re-checked
FIRE_WINDOW_SETTLE_S = 1.25      # I3/I6 (fix round): a window's own rows (a jump in its last row, a stall >= 1 s that
                                 # began in it) have all arrived this long after it ends -- then it is re-checked


def settle_fire_windows(out, sides, watch, log, clock, wait=None, classify=None, final=False, teleport_sides=None,
                        next_window=False):
    """Re-check the fire windows whose rows have settled: each window whose end is FIRE_WINDOW_SETTLE_S old gets its
    teleport check again (once), and the freeze check runs over the recent windows. `next_window` (a burst is about to
    open the next window): every earlier window whose rows up to PEEK_LEAD_S after its end have arrived is due now.
    `final` (the fight loop has exited): first wait until the LAST window is settled, then check everything. -> True when a window made the round NO-DATA
    (out['fire_teleport'] / out['fire_freeze'] / out['round_end'] set by the checks)."""
    windows = out.get("fire_windows") or []
    if not windows:
        return False
    if final and wait is not None:
        rest = windows[-1][1] + FIRE_WINDOW_SETTLE_S - clock()
        if rest > 0:
            wait(rest)
    now = clock()
    k = out.get("fire_settled", 0)
    while k < len(windows) and windows[k][1] + (PEEK_LEAD_S if next_window else FIRE_WINDOW_SETTLE_S) <= now + 1e-9:
        out["fire_settled"] = k + 1
        if fire_window_teleport(out, teleport_sides or sides, windows[k][0], windows[k][1], log, classify=classify):
            return True
        k += 1
    return fire_window_freeze(out, sides, windows, watch, log, now)


def fire_window_freeze(out, sides, windows, watch, log, now):
    """spec §5.1: a guest-clock freeze of either instance overlapping a fire window, or a freeze-attributed starvation
    alarm whose idle window overlaps one, makes the round NO-DATA. Sets out['fire_freeze'] / out['stop_reason']."""
    recent = [w for w in windows if now - w[1] <= FIRE_WINDOW_RECHECK_S]
    for side in sides:
        rt, steps, _, _ = tail_clock_state(side.tail, now - PAUSE_LOOKBACK_S)
        for p in vc.clock_pauses(rt, steps):
            if p[3] != "freeze":
                continue
            w = next((w for w in recent if p[0] < w[1] and p[1] > w[0]), None)
            if w is not None:
                out["fire_freeze"] = {"tag": side.tag, "pause": list(p[:2]), "window": list(w)}
                out["stop_reason"] = (f"NO-DATA freeze in a fire window side={side.tag} ({p[0]:.1f}-{p[1]:.1f}) -- the "
                                      f"round is not scored (spec §5.1)")
                log(f"ENDGAME {out['stop_reason']}")
                return True
    for a in (watch.alarms if watch is not None else []):
        if not a["cause"].startswith("freeze("):
            continue
        w = next((w for w in recent if a["t"] - a.get("window_s", 0.0) < w[1] and a["t"] > w[0]), None)
        if w is not None:
            out["fire_freeze"] = {"alarm": a["side"], "cause": a["cause"], "window": list(w)}
            out["stop_reason"] = (f"NO-DATA freeze-attributed alarm side={a['side']} ({a['cause']}) overlaps a fire "
                                  f"window -- the round is not scored (spec §5.1)")
            log(f"ENDGAME {out['stop_reason']}")
            return True
    return False


def spawn_mismatch(sides, spawns, live=None):
    """spawns: {tag: (x, y, z)} from the route file; live: {tag: (x, y, z)} (default: each tail's first actor row).
    -> 'side=<tag> ...' for the first side whose live spawn is > SPAWN_MISMATCH_UNITS (3-D) off, else None."""
    for tag, side in sorted(sides.items()):
        want = (spawns or {}).get(tag)
        if want is None:
            continue
        got = (live or {}).get(tag)
        if got is None:
            rows = side.tail.actor_ingame()
            got = rows[0][1:4] if rows else None
        if got is None:
            return f"side={tag} no actor row to compare with the route file's spawn"
        d = math.dist(got, want)
        if d > SPAWN_MISMATCH_UNITS:
            return (f"side={tag} live spawn ({got[0]:.1f},{got[1]:.1f},{got[2]:.1f}) is {d:.1f} units from the route "
                    f"file's ({want[0]:.1f},{want[1]:.1f},{want[2]:.1f})")
    return None


ROUTE_JOIN_MAX_UNITS = 60.0      # R65: after the precondition the mover joins the nearest same-floor waypoint this close
ROUTE_JOIN_DY_UNITS = 10.0       # ... "same floor": |actor y - the waypoint's leg floor y| <= this


def route_join_index(route, pos):
    """R65: the index of the nearest waypoint (ground distance) within ROUTE_JOIN_MAX_UNITS of `pos` (x, y, z) whose leg
    floor y is within ROUTE_JOIN_DY_UNITS of pos's y (a waypoint without a floor y matches any floor), or None."""
    best = None
    for i, w in enumerate(_wp(w) for w in route):
        d = math.hypot(w["x"] - pos[0], w["z"] - pos[2])
        if d > ROUTE_JOIN_MAX_UNITS or (w["floor_y"] is not None and abs(pos[1] - w["floor_y"]) > ROUTE_JOIN_DY_UNITS):
            continue
        if best is None or d < best[0]:
            best = (d, i)
    return None if best is None else best[1]


def victim_should_oscillate(d3):
    """The cooperative victim strafe-oscillates only while the shooter is inside ENDGAME_UNITS (3-D)."""
    return d3 is not None and d3 <= ENDGAME_UNITS


def endgame_route(sides, duel, watch, log, map_name, mover="A", route=None, fight_s=None, clock=time.time,
                  wait=time.sleep, spawns=None, live_spawns=None, route_path=None, route_join="start"):
    """The default engagement -> result dict. The stander stands (it moves only when the StarvationWatch asks it: one
    RULE_LEG_S strafe leg); the mover follows `route` (default: routes/<map>.json for `mover`) to the stander's floor,
    close_to()s it into the engagement band, then cycles aim_yaw(read="pulse", tol=aim_tol_deg(d3)) -> one R1 burst
    while inside the tolerance, re-closing when the band is left and reacting to StarvationWatch requests with a
    strafe leg. A TeleportAbort ends the attempt with `teleport` set (the RESULT line says so) -- unless it is the
    round-end reset to spawn (is_round_reset: `round_end`); a failed route or close ends it with the hint to swap the
    mover. `spawns` ({tag: (x, y, z)}, the route file's): a live spawn (`live_spawns`, default each tail's first actor
    row) further than SPAWN_MISMATCH_UNITS is `NO-DATA spawn-mismatch` before anybody walks. A teleport, or a guest
    freeze / freeze-attributed alarm, inside a fire window makes the round NO-DATA."""
    shooter = sides[mover]
    stander = sides["B" if mover == "A" else "A"]
    fight_s = ENDGAME_FIGHT_S if fight_s is None else fight_s
    route = route if route is not None else route_for(map_name, mover, path=route_path)
    out = {"mode": "route", "mover": shooter.tag, "stander": stander.tag, "route": None, "close": None,
           "rule_moves": [], "bursts": 0, "stop_reason": None, "teleport": None, "fire_teleport": None,
           "fire_freeze": None, "round_end": None, "t_fight": None, "t_end": None, "fire_windows": [],
           "route_join": None}
    duel.observe(shooter.tag, shooter.tail)
    duel.observe(stander.tag, stander.tail)
    log(f"ENDGAME BANNER mode=route mover={shooter.tag} stander={stander.tag} (stands at its spawn) "
        f"route={'%d waypoints (%s)' % (len(route), map_name) if route else 'NONE -- closing directly'} "
        f"band=|dy|<={ENGAGE_DY_UNITS:g},3-D<={ENGAGE_BAND_3D_UNITS:g} (stop at {ENGAGE_BAND_STOP_UNITS:g}) "
        f"aim=pulses(read {AIM_PULSE_READ_S:g}s after each, <= {AIM_PULSE_MAX_S:g}s) tol=min({AIM_TOL_DEG:g},0.8*atan(3.4/d)) "
        f"oscillation=OFF micro-strafe=OFF reaction=other-side-moves {RULE_LEG_S:g}s only when starved with both "
        f"round clocks running; teleport abort > {TELEPORT_STEP_UNITS:g}u per row")
    stop = duel.stop
    sign, sign_lock = {"s": 1}, threading.Lock()        # both side threads react: flip under a lock
    mismatch = spawn_mismatch({shooter.tag: shooter, stander.tag: stander}, spawns, live_spawns) if spawns else None
    if mismatch:
        out["stop_reason"] = f"NO-DATA spawn-mismatch {mismatch} -- nobody walks a route that starts elsewhere"
        out["t_end"] = clock()
        log(f"ENDGAME STOP: {out['stop_reason']}")
        return out

    classify = round_reset_classifier(spawns)

    def react(side):
        if watch is None or not watch.take_request(side.tag):
            return False
        with sign_lock:
            sign["s"] = -sign["s"]
            s = sign["s"]
        t = clock()
        side.sh.pad(RULE_LEG_S, axes={"lx": vc.PAD_NEUTRAL + s * RULE_LEG_DEFLECTION})
        watch.moved(side.tag, t)
        out["rule_moves"].append({"tag": side.tag, "t": t})
        log(f"ENDGAME reaction: {side.tag} strafed {RULE_LEG_S:g}s for the starved other side")
        return True

    def stander_loop():
        while not stop.is_set():
            if not react(stander):
                wait(STARVATION_POLL_S)

    def mover_run():
        on_poll = lambda: react(shooter)
        if route:
            # R65: after the precondition (route_join="nearest") join at the nearest same-floor waypoint within 60 units,
            # never an unrouted walk; after a round reset ("start") the players are at spawn: waypoint 0
            here = shooter.tail.actor_latest()
            k = 0 if route_join == "start" else (None if here is None else route_join_index(route, here[1:4]))
            if k is None:
                out["stop_reason"] = (f"NO-DATA route-start: no waypoint on {shooter.tag}'s floor within "
                                      f"{ROUTE_JOIN_MAX_UNITS:g} units of "
                                      + ("an unread position" if here is None else
                                         f"({here[1]:.1f},{here[2]:.1f},{here[3]:.1f})") + " -- nobody walks unrouted")
                return
            out["route_join"] = k
            log(f"ROUTE {shooter.tag} joins at wp{k} of {len(route)}")
            r = follow_route(shooter, route[k:], clock=clock, wait=wait, log=log, stop=stop, on_poll=on_poll)
            out["route"] = r
            if not r["ok"]:
                out["stop_reason"] = f"route failed: {r['reason']} -- --mover {stander.tag} swaps which side walks"
                return
        r = close_to(shooter, stander, clock=clock, wait=wait, log=log, stop=stop, on_poll=on_poll)
        out["close"] = r
        if not r["ok"]:
            out["stop_reason"] = f"close failed: {r['reason']} -- --mover {stander.tag} swaps which side walks"
            return
        out["t_fight"] = clock()
        log(f"ENDGAME band reached: {shooter.tag} at 3-D {r['d3']:.1f} from {stander.tag}")
        while clock() - out["t_fight"] < fight_s and not stop.is_set():
            if watch is not None and watch.stop_reason:
                out["stop_reason"] = watch.stop_reason
                return
            if settle_fire_windows(out, (shooter, stander), watch, log, clock, classify=classify):
                return                                   # I6: an earlier window's late rows made the round NO-DATA
            if react(shooter):
                continue
            a, b = shooter.tail.actor_latest(), stander.tail.actor_latest()
            if a is None or b is None:
                out["stop_reason"] = "stale actor rows in the engagement"
                return
            d3, dy = math.dist(a[1:4], b[1:4]), b[2] - a[2]
            if abs(dy) > ENGAGE_DY_UNITS or d3 > ENGAGE_BAND_3D_UNITS:
                r = close_to(shooter, stander, clock=clock, wait=wait, log=log, stop=stop, on_poll=on_poll)
                if not r["ok"]:
                    out["stop_reason"] = (f"re-close failed: {r['reason']} -- --mover {stander.tag} swaps which "
                                          f"side walks")
                    return
                continue
            if d3 < ENGAGE_TOO_CLOSE_UNITS:
                if _walk_leg(shooter, (b[1], b[3]), clock, wait, log, on_poll=on_poll, back=True,
                             stand_off=ENGAGE_BAND_STANDOFF_UNITS) is None:
                    out["stop_reason"] = "aim NO-DATA"
                    return
                continue
            tol = aim_tol_deg(d3)
            _, err = aim_yaw(shooter, (b[1], b[3]), shooter.tail, shooter.sh, clock=clock, wait=wait,
                             on_poll=on_poll, read="pulse", tol=tol)
            if err is None:
                out["stop_reason"] = "aim NO-DATA"
                return
            if abs(err) <= tol and not stop.is_set():
                if settle_fire_windows(out, (shooter, stander), watch, log, clock, classify=classify,
                                       next_window=True):
                    return                               # I6: the previous window, re-checked at the next one
                t_b = clock()
                shooter.r1_times.append(t_b)
                shooter.sh.pad(ENDGAME_BURST_S, buttons=["R1"])
                out["bursts"] += 1
                wait(ENDGAME_BURST_GAP_S)
                out["fire_windows"].append((t_b, clock()))
                if fire_window_teleport(out, (shooter, stander), t_b, clock(), log, classify=classify):
                    return
            if out["fire_windows"] and fire_window_freeze(out, (shooter, stander), out["fire_windows"], watch, log,
                                                          clock()):
                return

    ts = threading.Thread(target=stander_loop, daemon=True)
    ts.start()
    try:
        mover_run()
        if not (out["fire_teleport"] or out["fire_freeze"] or out["round_end"]):
            # I3: the last window's rows (a late jump, a stall that began in it) arrive after the loop has exited
            settle_fire_windows(out, (shooter, stander), watch, log, clock, wait, classify=classify, final=True)
    except TeleportAbort as e:
        if classify(sides[e.tag], (e.t, e.step)):
            out["round_end"] = {"tag": e.tag, "t": e.t, "step": e.step, "during": e.during}
            out["stop_reason"] = f"ROUND-END reset to spawn side={e.tag} (a {e.step:.1f}u jump near a round step)"
        else:
            out["teleport"] = {"tag": e.tag, "during": e.during, "step": e.step, "t": e.t}
            out["stop_reason"] = str(e)
    finally:
        stop.set()
        ts.join(timeout=RULE_LEG_S + 2.0)
        out["t_end"] = clock()
    if out["stop_reason"]:
        log(f"ENDGAME STOP: {out['stop_reason']}")
    log(f"ENDGAME done: mode=route bursts={out['bursts']} reactions={len(out['rule_moves'])} "
        f"route={out['route'] and out['route']['reason']} close={out['close'] and out['close']['reason']}")
    return out


# --- --endgame cooperative (opt-in; Amendment A: flags, default off) -----------------------------------------------
# The first Task 5 brief's two-sided engagement, kept as an opt-in mode: the victim strafe-oscillates from the start
# (feeding the shooter's counter) and the shooter micro-strafes between bursts (feeding the victim's). It reaches the
# victim the same way the default does (the recorded route, then close_to) and then fights at contact range.
ENDGAME_CLOSE_UNITS = 16.0       # the shooter stands this far off: the 22-unit gate minus the victim's excursion
ENDGAME_CLOSE_SLACK = 3.0        # ... re-closing only beyond CLOSE + SLACK
ENDGAME_TOO_CLOSE_UNITS = 12.0   # ... and backing off inside this (at 6 units a 1-unit centre error is 10 deg)
ENDGAME_REAPPROACH_UNITS = 80.0  # beyond this (or off the floor) close_to runs again
ENDGAME_WALK_MIN_S, ENDGAME_WALK_MAX_S = 0.15, 1.5
VICTIM_OSC_LEG_S = 0.4           # the brief: 0.4 s per leg, excursion <= ~8 units
SHOOTER_STRAFE_S = 0.3           # the brief: one 0.3 s lx leg between bursts, alternating
SHOOTER_WAIT_STAND_MAX_S = 3.5   # a wait for the matrix to settle is broken by a micro-strafe past this (under the
                                 # 4000 ms alarm). A micro-strafe INSIDE an aim moves the shooter 13 deg of bearing at
                                 # 15 units (3.5 units in the sim) and, offered at 1.5 s, stopped every aim converging:
                                 # the sim's endgame fired 0 bursts. So the cycle is aim -> burst -> micro-strafe.
ENDGAME_WALK_AIM_MAX_DEG = 45.0  # a range correction walks along the current facing only when it is this close
OSC_CENTRE_WINDOW_S = 1.6        # two full victim oscillation cycles: aim at the centre, not the swing


def target_centre(tail, now, window=OSC_CENTRE_WINDOW_S):
    """Mean actor position over the last `window` s (the oscillation centre) -> (x, y, z) | None."""
    rows = [r for r in tail.actor_ingame() if now - r[0] <= window]
    if not rows:
        a = tail.actor_latest()
        return None if a is None else (a[1], a[2], a[3])
    n = float(len(rows))
    return (sum(r[1] for r in rows) / n, sum(r[2] for r in rows) / n, sum(r[3] for r in rows) / n)


def toward_axes(me, other_xz, deflection=RULE_LEG_DEFLECTION):
    """Left-stick axes that walk `me` toward `other_xz` from its newest matrix heading, the larger component at
    `deflection`; ly forward when the heading is unknown. Right-strafe = facing - 90 deg (research/18 §3.13)."""
    with me.tail._lock:                                 # noqa: SLF001 - same module
        rows = list(me.tail.heading_rows[-1:])
    if not rows:
        return {"ly": vc.PAD_NEUTRAL - deflection}
    _, h, x, z = rows[-1]
    rel = math.radians(wrap_deg(math.degrees(math.atan2(other_xz[1] - z, other_xz[0] - x)) - h))
    fwd, right = math.cos(rel), -math.sin(rel)
    k = deflection / max(abs(fwd), abs(right), 1e-6)
    return {"ly": max(0, min(255, vc.PAD_NEUTRAL - round(k * fwd))),
            "lx": max(0, min(255, vc.PAD_NEUTRAL + round(k * right)))}


def endgame_cooperative(sides, duel, watch, log, map_name=None, route=None, fight_s=None, micro_strafe=True,
                        rule=True, clock=time.time, wait=time.sleep, mover="A", route_path=None):
    """The two-sided engagement (the first Task 5 brief): EACH side's scale is restored only by the OTHER side moving.

    Victim (the stander): strafe-oscillates continuously from the start (lx +-OSC_DEFLECTION, VICTIM_OSC_LEG_S legs)
    -- feeding the shooter's counter. Shooter (`mover`): follow_route + close_to (to ENDGAME_CLOSE_UNITS), then
    cycles of range correction -> aim_yaw (at rest) on the victim's oscillation centre -> one R1 burst -> one
    SHOOTER_STRAFE_S micro-strafe (alternating) -- feeding the victim's counter; inside an aim only a rule move, or a
    micro-strafe once a wait for the matrix to settle has stood SHOOTER_WAIT_STAND_MAX_S, interrupts it. `watch`
    (StarvationWatch): victim alarms -> the shooter suspends firing and walks a RULE_LEG_S strafe leg; shooter alarms
    -> the victim walks a RULE_LEG_S leg toward the shooter; its stop_reason ends the engagement. `micro_strafe` /
    `rule` exist so the simulation can show that removing both starves the victim. OPT-IN (--endgame cooperative).
    -> result dict."""
    shooter, victim = sides[mover], sides["B" if mover == "A" else "A"]
    fight_s = ENDGAME_FIGHT_S if fight_s is None else fight_s
    route = route if route is not None else route_for(map_name, mover, path=route_path)
    out = {"mode": "cooperative", "shooter": shooter.tag, "victim": victim.tag, "standing": [], "rule_moves": [],
           "micro_strafes": 0, "victim_legs": 0, "stop_reason": None, "t_fight": None, "t_end": None,
           "route": None, "close": None, "bursts": 0, "reapproaches": 0, "teleport": None, "fire_teleport": None,
           "fire_freeze": None, "round_end": None, "fire_windows": []}
    classify = round_reset_classifier()
    duel.observe(shooter.tag, shooter.tail)
    duel.observe(victim.tag, victim.tail)
    log(f"ENDGAME BANNER mode=cooperative shooter={shooter.tag} victim={victim.tag} "
        f"victim_osc=lx+-{OSC_DEFLECTION} {VICTIM_OSC_LEG_S:g}s legs (feeds {shooter.tag}) "
        f"shooter_micro_strafe={'lx+-%d %gs after each burst' % (OSC_DEFLECTION, SHOOTER_STRAFE_S) if micro_strafe else 'OFF'} "
        f"(feeds {victim.tag}) alarm_source=ng+0xde(primary),NetIdle>={vc.NETIDLE_ALARM_MS}ms(secondary) "
        f"rule={'other-side-moves %gs' % RULE_LEG_S if rule else 'OFF'} "
        f"route={'%d waypoints' % len(route) if route else 'NONE'}")
    stop = duel.stop

    def rule_request(tag):
        return rule and watch is not None and watch.take_request(tag)

    def victim_loop():
        sign = 1
        while not stop.is_set():
            if rule_request(victim.tag):
                centre = target_centre(shooter.tail, clock())
                t = clock()
                axes = toward_axes(victim, (centre[0], centre[2])) if centre else {"ly": 0}
                victim.sh.pad(RULE_LEG_S, axes=axes)
                watch.moved(victim.tag, t)
                out["rule_moves"].append({"tag": victim.tag, "t": t, "axes": axes})
                log(f"ENDGAME rule: {victim.tag} walked {RULE_LEG_S:g}s toward {shooter.tag} {axes}")
                continue
            a, b = shooter.tail.actor_latest(), victim.tail.actor_latest()
            if not victim_should_oscillate(None if a is None or b is None else math.dist(a[1:4], b[1:4])):
                wait(STARVATION_POLL_S)                 # the oscillation feeds a shooter inside ENDGAME_UNITS only
                continue
            sign = -sign
            victim.sh.pad(VICTIM_OSC_LEG_S, axes={"lx": vc.PAD_NEUTRAL + sign * OSC_DEFLECTION})
            out["victim_legs"] += 1

    last_move = [clock()]
    strafe_sign = [1]

    def strafe(seconds, deflection):
        strafe_sign[0] = -strafe_sign[0]
        t = clock()
        out["standing"].append(t - last_move[0])
        shooter.sh.pad(seconds, axes={"lx": vc.PAD_NEUTRAL + strafe_sign[0] * deflection})
        last_move[0] = clock()
        return t

    def rule_move():
        if rule_request(shooter.tag):
            t = strafe(RULE_LEG_S, RULE_LEG_DEFLECTION)
            watch.moved(shooter.tag, t)
            out["rule_moves"].append({"tag": shooter.tag, "t": t})
            log(f"ENDGAME rule: {shooter.tag} suspended firing and strafed {RULE_LEG_S:g}s")
            return True
        return False

    def on_poll():
        if rule_move():
            return True
        if micro_strafe and clock() - last_move[0] >= SHOOTER_WAIT_STAND_MAX_S:
            strafe(SHOOTER_STRAFE_S, OSC_DEFLECTION)
            out["micro_strafes"] += 1
            return True
        return False

    def aim(centre):
        return aim_yaw(shooter, (centre[0], centre[2]), shooter.tail, shooter.sh, clock=clock, wait=wait,
                       fidget=rule_move, on_poll=on_poll, read="rest", tol=AIM_TOL_DEG)

    def walk(key_axes, seconds):
        t = clock()
        out["standing"].append(t - last_move[0])
        shooter.sh.pad(seconds, axes=key_axes)
        last_move[0] = clock()

    def reach():
        r = close_to(shooter, victim, clock=clock, wait=wait, log=log, stop=stop, on_poll=rule_move,
                     stop_d3=ENDGAME_CLOSE_UNITS + ENDGAME_CLOSE_SLACK, stand_off=ENDGAME_CLOSE_UNITS)
        last_move[0] = clock()
        return r

    def shooter_loop():
        if route:
            out["route"] = follow_route(shooter, route, clock=clock, wait=wait, log=log, stop=stop,
                                        on_poll=rule_move)
            last_move[0] = clock()
            if not out["route"]["ok"]:
                out["stop_reason"] = f"route failed: {out['route']['reason']}"
                return
        out["close"] = reach()
        if not out["close"]["ok"]:
            out["stop_reason"] = f"close failed: {out['close']['reason']}"
            return
        out["t_fight"] = clock()
        out["standing"], last_move[0] = [], clock()     # standing windows are counted in the fight only
        log(f"ENDGAME contact: shooter {shooter.tag} engages (paired d3={duel.current_d3()})")
        while clock() - out["t_fight"] < fight_s and not stop.is_set():
            if watch is not None and watch.stop_reason:
                out["stop_reason"] = watch.stop_reason
                return
            if rule_move():
                continue
            now = clock()
            me = shooter.tail.actor_latest()
            centre = target_centre(victim.tail, now)
            if me is None or centre is None:
                out["stop_reason"] = "stale actor rows in the engagement"
                return
            d3, dy = math.dist(me[1:4], centre), centre[1] - me[2]
            log(f"ENDGAME cycle T+{now - out['t_fight']:.1f}s d3={d3:.1f} dy={dy:+.1f} "
                f"standing={now - last_move[0]:.1f}s gain={shooter.yaw_gain:.2f}")
            if abs(dy) > ENGAGE_DY_UNITS or d3 > ENDGAME_REAPPROACH_UNITS:
                out["reapproaches"] += 1
                r = reach()
                if not r["ok"]:
                    out["stop_reason"] = f"re-close failed: {r['reason']}"
                    return
                continue
            if d3 > ENDGAME_CLOSE_UNITS + ENDGAME_CLOSE_SLACK or d3 < ENDGAME_TOO_CLOSE_UNITS:
                # Range correction along the CURRENT facing (a walk changes range, not bearing, when the facing
                # points at the target) -- it is also traffic for the victim. Aim first only when the newest
                # heading row is far off the bearing.
                with shooter.tail._lock:                # noqa: SLF001 - same module
                    hrow = list(shooter.tail.heading_rows[-1:])
                off = (abs(wrap_deg(math.degrees(math.atan2(centre[2] - hrow[0][3], centre[0] - hrow[0][2]))
                                    - hrow[0][1])) if hrow else 180.0)
                if off > ENDGAME_WALK_AIM_MAX_DEG:
                    if aim(centre)[1] is None:
                        out["stop_reason"] = "aim NO-DATA"
                        return
                    continue
                if d3 > ENDGAME_CLOSE_UNITS:
                    secs = (d3 - ENDGAME_CLOSE_UNITS) / WALK_UNITS_PER_S_LONG
                    walk({"ly": 0}, max(ENDGAME_WALK_MIN_S, min(ENDGAME_WALK_MAX_S, secs)))
                else:
                    secs = (ENDGAME_CLOSE_UNITS - d3) / WALK_BACK_UNITS_PER_S
                    walk({"ly": 255}, max(ENDGAME_WALK_MIN_S, min(ENDGAME_WALK_MAX_S, secs)))
                continue
            _, err = aim(centre)
            if err is None:
                out["stop_reason"] = "aim NO-DATA"
                return
            if abs(err) <= AIM_TOL_DEG and not stop.is_set() and not (
                    rule and watch is not None and watch.request_event(shooter.tag).is_set()):
                if settle_fire_windows(out, (shooter, victim), watch, log, clock, classify=classify,
                                       teleport_sides=(shooter,), next_window=True):
                    return
                t_b = clock()
                shooter.r1_times.append(t_b)
                shooter.sh.pad(ENDGAME_BURST_S, buttons=["R1"])
                out["bursts"] += 1
                wait(ENDGAME_BURST_GAP_S)
                out["fire_windows"].append((t_b, clock()))
                if fire_window_teleport(out, (shooter,), t_b, clock(), log, classify=classify):
                    return
            if settle_fire_windows(out, (shooter, victim), watch, log, clock, classify=classify,
                                   teleport_sides=(shooter,)):
                return
            if micro_strafe:
                strafe(SHOOTER_STRAFE_S, OSC_DEFLECTION)
                out["micro_strafes"] += 1
        if micro_strafe or rule:
            strafe(SHOOTER_STRAFE_S, OSC_DEFLECTION)    # leave the victim fed: no alarm opens as the fight ends
        else:
            out["standing"].append(clock() - last_move[0])

    def shooter_guarded():
        try:
            shooter_loop()
            if not (out["fire_teleport"] or out["fire_freeze"] or out["round_end"]):
                settle_fire_windows(out, (shooter, victim), watch, log, clock, wait, classify=classify, final=True,
                                    teleport_sides=(shooter,))
        except TeleportAbort as e:
            if classify(sides[e.tag], (e.t, e.step)):
                out["round_end"] = {"tag": e.tag, "t": e.t, "step": e.step, "during": e.during}
                out["stop_reason"] = f"ROUND-END reset to spawn side={e.tag} (a {e.step:.1f}u jump near a round step)"
            else:
                out["teleport"] = {"tag": e.tag, "during": e.during, "step": e.step, "t": e.t}
                out["stop_reason"] = str(e)

    tv = threading.Thread(target=victim_loop, daemon=True)
    ts = threading.Thread(target=shooter_guarded, daemon=True)
    tv.start()
    ts.start()
    ts.join()
    stop.set()
    tv.join(timeout=RULE_LEG_S + 5.0)
    out["t_end"] = clock()
    if out["stop_reason"]:
        log(f"ENDGAME STOP: {out['stop_reason']}")
    st = [s for s in out["standing"] if s is not None]
    log(f"ENDGAME done: mode=cooperative bursts={out['bursts']} micro_strafes={out['micro_strafes']} "
        f"victim_legs={out['victim_legs']} rule_moves={len(out['rule_moves'])} standing_total={sum(st):.1f}s "
        f"max_window={max(st, default=0):.1f}s aims={len(shooter.aims)} teleports={shooter.aim_teleports}")
    return out


class Client:
    def __init__(self, tag, out, name, existing, seconds):
        self.tag, self.out, self.name, self.existing, self.seconds = tag, out, name, existing, seconds
        self.proc = self.sh = None
        self.error = None
        self.run_log = os.path.abspath(os.path.join(
            "logs", f"run_{tag}_{time.strftime('%Y%m%d_%H%M%S')}.log"))
        self.tail = None

    def launch(self):
        # run.sh honours PS2X_RUN_LOG, so the driver knows which file carries this instance's
        # [peek] rows and can follow them live instead of guessing by modification time.
        os.environ["PS2X_RUN_LOG"] = self.run_log
        self.proc, self.title = L.launch(self.seconds, self.tag)
        self.tail = RunLogTail(self.run_log)
        self.tail.start()

    def login(self):
        try:
            self.sh = L.attach(self.proc, self.title, self.out, self.tag + "_", L.INSTANCES[self.tag]["PS2X_SOCOM2_INPUT_FILE"])
            L.boot_to_online(self.sh)
            L.login(self.sh, self.name, "socom", self.existing)
            L.to_briefing_room(self.sh)
        except BaseException as e:      # noqa: BLE001 - surfaced by the caller
            self.error = e

    def kill(self):
        if self.tail:
            self.tail.stop()
        if self.proc:
            self.proc.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold", type=int, default=120)
    ap.add_argument("--out", default="logs/parity/ours_match")
    ap.add_argument("--seconds", type=int, default=700)
    ap.add_argument("--name-a", default="socomc")
    ap.add_argument("--name-b", default="socome")
    ap.add_argument("--existing-b", action="store_true")
    ap.add_argument("--only", default="", help="A or B: run one instance's login only (setup check)")
    ap.add_argument("--play", type=int, default=0, help="gameplay bursts after the hold (A walks + fires, B turns)")
    ap.add_argument("--same-team", action="store_true", help="B switches to SEALs (the joiner is auto-assigned to TERRORISTS); teammates spawn together")
    ap.add_argument("--sweep", type=int, default=0, help="gameplay: A turns in place in <N> steps of --sweep-hold s firing a burst at each; B stands")
    ap.add_argument("--sweep-hold", type=float, default=0.5)
    ap.add_argument("--host-switch", action="store_true", help="A (host) switches team after B joined (the joiner is auto-assigned opposite the host; the joiner's lobby cursor does not move)")
    ap.add_argument("--probe", action="store_true", help="gameplay: A tries every stick direction and the stance buttons with screens after each (input probe)")
    ap.add_argument("--probe-both", action="store_true", help="with --probe: drive the same stick sequence on B as well, so local control is proven on both sides")
    ap.add_argument("--turn-key", default="L", help="L = right stick right, the only key that turns on this preset. D (left stick right) was believed to be a 'Sure Shot turn' but MEASURES as a strafe: constant world bearing, facing unchanged (research/18 §3.13)")
    ap.add_argument("--calibrate", action="store_true", help="gameplay: measure look deg/s, lateral units/s, walk units/s and the camera orbit radius on A (three repeats each, with the spread)")
    ap.add_argument("--walk-to-b", action="store_true", help="gameplay: A reads both positions, turns toward B and walks until within --arrive units")
    ap.add_argument("--arrive", type=float, default=ARRIVE_UNITS)
    ap.add_argument("--max-steps", type=int, default=WALK_TO_B_MAX_STEPS)
    ap.add_argument("--max-walk-seconds", type=float, default=WALK_TO_B_MAX_SECONDS)
    # -- Task 8 (S3) --------------------------------------------------------
    ap.add_argument("--converge", action="store_true",
                    help="gameplay: BOTH instances walk toward each other (one mover cannot close "
                         "1382 units inside a round -- 38.6%% measured closure efficiency needs "
                         "~450 s against a ~360 s round), A following the mined mp51 corridor")
    ap.add_argument("--until-kill", action="store_true",
                    help="implies --converge: run until a death or round end is observed, capture "
                         "both screens at that moment and print which signal fired; exit 1 on the "
                         "timeout so a failed match is a clean FAIL rather than a hang")
    ap.add_argument("--engage", type=float, default=ENGAGE_3D_UNITS,
                    help="TRUE 3-D actor-to-actor range at which the approach stops and the "
                         "engagement starts. Contact also requires the two heights to be within "
                         "--engage-dy; kill2 reported a 33-unit ground gap while the real 3-D "
                         "separation never got below 50")
    ap.add_argument("--engage-dy", type=float, default=ENGAGE_DY_UNITS)
    ap.add_argument("--fight-seconds", type=float, default=150.0)
    ap.add_argument("--kill-timeout", type=float, default=420.0,
                    help="wall-clock budget from the liveness check to the kill; on expiry the run "
                         "ends FAIL with both screens captured")
    ap.add_argument("--control-round", action="store_true",
                    help="implies --converge: after the control precondition NOBODY FIRES; both sides "
                         "alternate 0.5-0.9 s strafe legs (each feeds the other's idle counter) until "
                         "the round ends on its clock (mp_round_count step, mp_game_over, clock 00:00) "
                         "or --control-round-cap. Prints RESULT CONTROL-ROUND; exit 1 unless the round "
                         "ended with total_mp_kills, aiteam_* and the health word unchanged (Task 6's "
                         "negative control)")
    ap.add_argument("--control-round-cap", type=float, default=CONTROL_ROUND_CAP_S)
    ap.add_argument("--mover", choices=["A", "B"], default="A",
                    help="which side walks and shoots in --endgame route/cooperative (default A, the host); the other "
                         "stands at its spawn. Swap it when the route fails")
    ap.add_argument("--endgame", choices=["route", "cooperative", "converge"], default=None,
                    help="the engagement of a --converge/--until-kill run. route (DEFAULT, Amendment A): the stander "
                         "stands at its spawn; the mover follows tools_py/parity/routes/<map>.json to its floor, closes "
                         "into the engagement band (|dy| <= 10, 3-D <= 45), aims with short partial-rx pulses read "
                         "0.5 s after each from the actor matrix, and fires; a side moves for the other only as a "
                         "StarvationWatch reaction (starved, both round clocks running); an actor row step > 30 units "
                         "in a pulse or walk leg ends the attempt with RESULT FAIL teleport. cooperative (opt-in): the "
                         "same route and close, then the victim strafe-oscillates and the shooter micro-strafes "
                         "between bursts. converge: Sprint 4's both-approach + sweep-fire. route and cooperative need "
                         "NetIdle traced and *0x437ce8:64, *0x437ce8+0x100:21, 0x4365c0:1 peeked (refuse otherwise)")
    ap.add_argument("--no-route", action="store_true",
                    help="ignore the mined corridor and walk the straight line (the Task 7 policy)")
    ap.add_argument("--rounds", type=int, default=online_ladder.LADDER_ROUNDS_DEFAULT,
                    help="Amendment A2: rounds played on one lobby success (default 4). After a round end or kill the "
                         "actor is re-found by its vtable, the move-path disarm window re-armed and per-round state "
                         "reset; round 1 carries the precondition, rounds 2.. engage only. One LADDER round=<n> line "
                         "each and a LADDER-SUMMARY. Stop rules (A1): 3 usable rounds at rung 1 without rung 2 -> "
                         "SWAP-MOVER; 2 usable rounds at rung 2 without rung 3 -> DAMAGE-PATH-DECISION")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate the arguments, the route file, the peek/trace spec and PS2X_GS_STATS, print "
                         "DRY-RUN OK (exit 0) or DRY-RUN REFUSED lines (exit 2), and launch nothing")
    ap.add_argument("--auto-swap", action="store_true",
                    help="on SWAP-MOVER, swap --mover for the next rounds (once) instead of stopping")
    ap.add_argument("--route", default=None,
                    help="the route FILE of --endgame route/cooperative, separate from --map (which picks the in-game "
                         "map). Default: tools_py/parity/routes/frostfire_v2.json for --map frostfire (rw24, from "
                         "collision geometry), else routes/<map>.json; routes/frostfire.json is the old 3c-derived "
                         "route. Its spawns are checked against the live spawns before anybody walks")
    ap.add_argument("--map", default="frostfire",
                    help="map to select in CHOOSE GAMES. The selection is VERIFIED against a "
                         "reference crop of the highlighted row before CROSS is pressed; a map "
                         "with no reference aborts rather than accepting whatever is highlighted")
    ap.add_argument("--map-scan", type=int, default=0,
                    help="with --only A: walk the AVAILABLE MAPS list this many DOWN presses, "
                         "capturing every screen, and stop. No match is created. This is how the "
                         "reference crop for a new map is obtained")
    ap.add_argument("--health-offset", default=f"{DEFAULT_HEALTH_OFFSET:#x}",
                    help="BYTE OFFSET FROM THE ACTOR BASE of the health float to watch (default "
                         f"{DEFAULT_HEALTH_OFFSET:#x}; 'none' disarms). Not an item index: PS2X_PEEK skips "
                         "items whose chain does not resolve, so indices shift. research/19 F1: 1.0 = full, "
                         "<= 0.0 = dead. ARMED BY DEFAULT since Sprint 5 Task 2. That task's single-player runs "
                         "read it step 1.0 -> 0.978 -> 0.721 and 1.0 -> 0.392 on damage, but saw NO death "
                         "(docs/research/22-kill-readout.md): the `<= 0` half is still sourced, not read "
                         "live, and the first online death is its confirmation. "
                         "PS2X_PEEK must cover it (e.g. *0x408c58+0x1044:1): a --converge run refuses to "
                         "launch otherwise, rather than failing later with reads=0. The +0x204/+0x208 "
                         "pair this help used to name is RETRACTED.")
    ap.add_argument("--alive-offset", default=f"{DEFAULT_ALIVE_OFFSET:#x}",
                    help=f"BYTE OFFSET FROM THE ACTOR BASE of the alive byte (default {DEFAULT_ALIVE_OFFSET:#x}, "
                         "1 = alive; 'none' disarms the observation). Read for the move-path disarm and "
                         "recorded by KillWatch as a non-firing `alive` observation when it leaves 1 on the "
                         "actor that read alive. Sourced (research/19 F1); Task 2 saw it stay 1 through damage and "
                         "a MISSION FAILURE, and saw no death.")
    ap.add_argument("--health-range", default="-1e9:0.0",
                    help="lo:hi -- the float range that counts as DEAD for --health-offset. The "
                         "default matches research/19's `<= 0.0 = dead`. It used to be -0.5:0.5, "
                         "which on a 1.0-full health float would have called a player at 40 %% "
                         "health dead and printed PASS for a kill that never happened. A read in "
                         "this range counts ONLY as a transition: the same actor address must "
                         "first read alive (0 < v <= 1), so a first read of 0.0 or of "
                         "uninitialised heap (0xAFAFAFAF) is not a kill")
    a = ap.parse_args()
    a.health_offset = parse_offset(a.health_offset)
    a.alive_offset = parse_offset(a.alive_offset)
    if a.until_kill:
        a.converge = True
    if a.control_round:
        problem = control_round_arg_problem(a)
        if problem:
            raise SystemExit(problem)
        a.converge = True
    if a.endgame:
        problem = endgame_arg_problem(a)
        if problem:
            raise SystemExit(problem)
        a.converge = True
    if a.endgame is None:
        a.endgame = "route"                     # the default engagement (owner-requested review)
    problem = rounds_arg_problem(a)
    if problem:
        raise SystemExit(problem)
    watched_endgame = a.endgame in ("route", "cooperative") and not a.control_round
    route_path = a.route or default_route_path(a.map)
    ident = identity_tokens()
    if a.dry_run:
        lines, _ = launch_refusal_lines(os.environ, a.alive_offset, a.health_offset) if a.converge else ([], 0)
        lines = [ln for ln in lines if not ln.startswith("RESULT")]
        lines += [f"PEEK SPEC: {p}" for p in peek_spec_problems(os.environ.get("PS2X_PEEK", ""))] if a.converge else []
        if watched_endgame:
            lines += [f"ENDGAME REFUSES: {p}" for p in endgame_preconditions(os.environ)]
            lines += [f"ROUTE REFUSES: {p}" for p in problems_route_file(route_path)] if route_path else \
                [f"ROUTE REFUSES: no route file for --map {a.map} (pass --route)"]
            if os.environ.get("PS2X_GS_STATS") != "1":
                lines.append("RUNG0 REFUSES: PS2X_GS_STATS is not 1 -- rung 0's back-pressure waits would be NO-DATA")
        for ln in lines:
            print(f"DRY-RUN REFUSED {ln}", flush=True)
        if lines:
            raise SystemExit(2)
        print(f"DRY-RUN OK map={a.map} endgame={a.endgame} route={route_path} rounds={a.rounds} mover={a.mover} "
              f"auto_swap={a.auto_swap} until_kill={a.until_kill} {ident}", flush=True)
        return
    # Both of these were quietly inert: only --engage-dy was pushed into the module global, and
    # `level_target`'s `tol` default bound at IMPORT time, so a --engage-dy on the command line
    # never reached the anti-stack search. A flag that does nothing is worse than no flag.
    globals()["ENGAGE_DY_UNITS"] = a.engage_dy
    globals()["ENGAGE_3D_UNITS"] = a.engage
    os.makedirs(a.out, exist_ok=True)
    if subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower().count("socom2.exe"):
        raise SystemExit("socom2.exe is already running")
    if a.converge and not a.only:
        # Refuse BEFORE a launch, not after: a match whose move-path watch cannot see a stall, or
        # whose round valves cannot be identified, is a match spent proving nothing.
        for prob in peek_spec_problems(os.environ.get("PS2X_PEEK", "")):
            print(f"PEEK SPEC: {prob}", flush=True)
        lines, code = launch_refusal_lines(os.environ, a.alive_offset, a.health_offset)
        if watched_endgame:
            eg = endgame_preconditions(os.environ)
            lines += [f"ENDGAME REFUSES: {p}" for p in eg]
            if eg:
                lines.append(f"RESULT NO-DATA starvation watch (not launched) {ident}")
                code = 2
        if lines:
            for line in lines:
                print(line, flush=True)
            raise SystemExit(code)
    A = Client("A", a.out, a.name_a, True, a.seconds)
    B = Client("B", a.out, a.name_b, a.existing_b, a.seconds)
    failed = False
    if a.only:
        if a.until_kill:
            raise SystemExit("--only drives ONE instance and cannot observe a kill; --until-kill "
                             "needs both. Drop one of the two rather than getting an exit 0 and "
                             "no RESULT line.")
        c = A if a.only == "A" else B
        try:
            c.launch()
            c.login()
            if c.error:
                raise c.error
            if a.map_scan:
                L.open_choose_games(c.sh)
                rows = L.map_scan(c.sh, a.map_scan)
                c.sh.log(f"map scan done: highlighted rows {rows}")
            c.sh.shot("done")
        finally:
            c.kill()
        return
    try:
        A.launch()
        time.sleep(6)
        B.launch()
        tA = threading.Thread(target=A.login)
        tB = threading.Thread(target=B.login)
        tA.start()
        time.sleep(5)
        tB.start()
        tA.join()
        tB.join()
        for c in (A, B):
            if c.error:
                raise c.error
        L.host_game(A.sh, game_map=a.map)
        L.join_game(B.sh, switch=a.same_team and not a.host_switch)   # the joiner is auto-assigned to the other team
        if a.host_switch:
            A.sh.log(f"teams before host switch {L.lobby_teams(A.sh)}")
            L.lobby_select(A.sh, 1, "SWITCH TEAMS")
            A.sh.press("cross", 4.0)
            A.sh.shot("18_host_switched")
            A.sh.log(f"teams after host switch {L.lobby_teams(A.sh)}")
        time.sleep(35)                                           # READY becomes available
        L.ready(A.sh)
        L.ready(B.sh)
        for i in range(a.hold // 10):
            time.sleep(10)
            A.sh.shot(f"hold{i:02d}")
            B.sh.shot(f"hold{i:02d}")
        if a.play:
            # Gameplay phase (the user's acceptance test): A hunts, B stands. A walks forward in
            # bursts and fires; B turns slowly so both sides render each other. Screens every
            # burst on both sides; the kill/round end is read from the HUD captures and the DME log.
            for i in range(a.play):
                A.sh.hold("W", 3.0)
                A.sh.hold("R1", 0.3)
                A.sh.hold("R1", 0.3)
                B.sh.hold("L", 0.6)
                A.sh.shot(f"play{i:02d}")
                B.sh.shot(f"play{i:02d}")
        if a.probe:
            # Each stick direction for 3 s with 2 s of rest, twice (posted keys are sometimes
            # dropped); the position rows ([peek] @416054, 1/s) give the displacement per key.
            for i, (key, secs) in enumerate([("K", 3.0), ("I", 3.0), ("J", 3.0), ("L", 3.0), ("W", 3.0), ("S", 3.0), ("A", 3.0), ("D", 3.0)] * 2):
                A.sh.hold(key, secs)
                if a.probe_both:
                    B.sh.hold(key, secs)
                A.sh.log(f"probe {i:02d} {key} {secs}s")
                time.sleep(2.0)
                A.sh.shot(f"probe{i:02d}_{key}")
                B.sh.shot(f"probe{i:02d}_{key}")
        if a.calibrate or a.walk_to_b or a.converge:
            # research/18 §3.10 step 0, in-process: no gameplay rows, no measurement. Four of
            # eleven runs in the previous task never reached gameplay and their screenshots did
            # not say so.
            t_launch = time.time()                               # R47: one launch-stage budget for both
            liveA = wait_ingame(A.tail, A.sh, timeout=L.LOBBY_STAGE_TIMEOUT_S)
            liveB = wait_ingame(B.tail, B.sh, timeout=L.lobby_launch_budget(t_launch))
            A.sh.log(f"in-game peek rows A={len(A.tail.ingame())} B={len(B.tail.ingame())} "
                     f"(log lines A={A.tail.lines} B={B.tail.lines})")
            if not (liveA and liveB):
                raise L.lobby_fail(A.sh, "timeout:launch", "liveness check failed: the run never reached gameplay")
            A.sh.log(f"LOBBY class={L.CLASS_OK}")
        if a.calibrate:
            calibrate(A.sh, A.tail, a.out)
        if a.walk_to_b:
            r = walk_to_b(A, B, A.tail, B.tail, a.arrive, a.max_steps, a.max_walk_seconds)
            with open(os.path.join(a.out, "walk_to_b.json"), "w") as fh:
                json.dump(r, fh, indent=1, default=float)
            A.sh.log(f"[wtb] result {r['ok']} {r['reason']} steps={r['steps']} best={r.get('best')}")
            A.sh.shot("wtb_final")
            B.sh.shot("wtb_final")
        if a.converge:
            # Sprint 5 Task 3: the move path is watched from here to the end, the valves are
            # checked by name bytes, and nobody walks until BOTH players are proven controllable.
            mpw = MovePathWatch({"A": A.tail, "B": B.tail}, A.sh.log)
            mpw.start()
            valves_wanted = requested_valves(os.environ.get("PS2X_PEEK", ""))
            for c in (A, B):
                for line in valve_report(c.tag, c.tail, valves_wanted):
                    A.sh.log(line)
            control, control_sides = run_precondition({"A": A, "B": B})
            A.sh.log("PRECONDITION controllable: " + " ".join(
                f"{tag}={sd.status}({len(sd.holds)} holds)" for tag, sd in sorted(control_sides.items())))
            if control != vc.CONTROLLABLE:
                mpw.stop()
                code = control_exit_code(control)
                why = ("a side that cannot move cannot be engaged, and a parked side starves its partner"
                       if code == 3 else "no hold on some side was decisive (actor rows missing?)")
                A.sh.log(f"RESULT {control if code == 3 else 'NO-DATA control'} {ident} -- the match is not "
                         f"spent: {why}")
                with open(os.path.join(a.out, "control.json"), "w") as fh:
                    json.dump({"result": control,
                               "sides": {tag: {"status": sd.status,
                                               "holds": [vars(v) for v in sd.holds]}
                                         for tag, sd in control_sides.items()},
                               "move_path": mpw.history}, fh, indent=1, default=str)
                raise SystemExit(code)
        if a.converge and a.control_round:
            # Sprint 5 Task 1 Step 5b: the clock round-end negative control. Nobody fires.
            series, end, score = control_round({"A": A, "B": B}, A.sh.log, cap_s=a.control_round_cap,
                                               health_offset=a.health_offset, alive_offset=a.alive_offset)
            mpw.stop()
            for c in (A, B):
                evidence_shot(c, "final", [], A.sh.log, [])
                for line in valve_report(c.tag, c.tail, valves_wanted):
                    A.sh.log(line)
            with open(os.path.join(a.out, "control_round.json"), "w") as fh:
                json.dump({"control": {tag: sd.status for tag, sd in control_sides.items()},
                           "move_path": mpw.history, "end": end, "score": score,
                           "series": series}, fh, indent=1, default=str)
            A.sh.log(control_round_result_line(score, end) + f" {ident}")
            if not control_round_ok(score, end):
                failed = True
        if a.converge and not a.control_round:
            # Task 8 (S3): BOTH sides close, then fight, and a KillWatch decides when it is over. Sprint 5 Amendment A2:
            # a watched engagement plays up to --rounds rounds on one lobby success (online_ladder.run_ladder).
            # The mined corridor is map-specific (research/18 §4.5). On any other map it would
            # steer along a route that does not exist, so it is dropped and the banner says so.
            mined_ok = (not a.no_route) and a.map.lower() == MINED_ROUTE_MAP
            route = MP51_SEAL_ROUTE if mined_ok else None
            A.sh.log(f"RUN BANNER map={a.map} "
                     f"route={'mined(' + MINED_ROUTE_MAP + ')' if mined_ok else 'direct'} "
                     f"route_file={route_path if watched_endgame else '-'} rounds={a.rounds} "
                     f"auto_swap={a.auto_swap} "
                     f"engage3d={a.engage} dy_tol={a.engage_dy} "
                     f"pos={'actor' if A.tail.actor_ingame() else 'camera-reconstruction'} "
                     f"health={'armed@+0x%x' % a.health_offset if a.health_offset is not None else 'disarmed'} "
                     f"alive={'@+0x%x' % a.alive_offset if a.alive_offset is not None else 'disarmed'}")
            spawns = {}
            for tag, c in (("A", A), ("B", B)):
                rows = c.tail.ingame()
                if rows:
                    spawns[tag] = (rows[0][1], rows[0][3])
            first_actor = {tag: (c.tail.actor_ingame()[0][1:4] if c.tail.actor_ingame() else None)
                           for tag, c in (("A", A), ("B", B))}
            health = None
            if a.health_offset is not None:
                health = a.health_offset           # 0 is a valid offset; every test is `is None`
                for c in (A, B):
                    c.tail.watch_offset = health
                A.sh.log(f"kill readout: health word armed at ACTOR+0x{health:x} (found through "
                         f"the block whose word 0 is {ACTOR_VTABLE:#x}, never through an item "
                         f"index), dead range {a.health_range}")
            else:
                A.sh.log("kill readout: health word NOT armed (no confirmed offset) -- the run "
                         "reads the round end from the position records and the Medius log, and "
                         "the actor block is logged for offline confirmation")
            lo, hi = (float(v) for v in a.health_range.split(":"))
            if a.alive_offset is not None:
                for c in (A, B):
                    c.tail.alive_offset = a.alive_offset
            watch = KillWatch({"A": A.tail, "B": B.tail}, spawns, health=health,
                              health_range=(lo, hi), alive=a.alive_offset)
            watch.start()
            t_gameplay = time.time()
            # Sprint 5 Task 5: both instances' starvation, live (the engagement's other-side-moves rule reads it)
            starv = StarvationWatch({"A": A.tail, "B": B.tail}, A.sh.log) if watched_endgame else None
            if starv is not None:
                starv.start()
            file_spawns = {t: map_spawn(tag=t, path=route_path) for t in "AB"
                           if route_path and map_spawn(tag=t, path=route_path)}
            rounds_out = []
            is_kill_any = [False]
            ctl = tuple({vc.CONTROLLABLE: "yes", vc.NO_DATA: vc.NO_DATA}.get(control_sides[t].status, "no")
                        for t in ("A", "B"))

            def play_round(n, mover):
                t_round = time.time()
                round_value = online_ladder.round_count(A.tail)[0]
                duel = Duel()
                sideA = Side("A", A.sh, A.tail, route=route if n == 1 else None)
                sideB = Side("B", B.sh, B.tail, route=None)   # B's half of the map has no mined track
                if n > 1:
                    watch.rearm()
                    mpw.rearm(t_round)
                    if starv is not None:
                        starv.new_round(t_round)
                stale_shots, missing_shots, kill_shots = [], [], {"done": False}
                if n == 1 and watched_endgame:
                    # rung 0's reported rx pulse table (A3/A4), both sides at once, before anybody walks
                    tt = [threading.Thread(target=lambda sd=sd: rung0_tables.__setitem__(sd.tag, rx_pulse_table(sd)))
                          for sd in (sideA, sideB)]
                    for t in tt:
                        t.start()
                    for t in tt:
                        t.join()
                live_spawns = first_actor if n == 1 else {
                    tag: (c.tail.actor_latest()[1:4] if c.tail.actor_latest() else None) for tag, c in (("A", A), ("B", B))}

                def round_fired():
                    ev = watch.fired
                    return ev if ev and ev["t"] >= t_round - 1.0 else None

                def signal_seen(ev):
                    A.sh.log(f"KILL/ROUND-END SIGNAL round={n} {ev['kind']} on {ev['tag']} at "
                             f"T+{ev['t'] - t_gameplay:.1f}s {json.dumps(ev['detail'], default=float)}")
                    if not kill_shots["done"]:
                        kill_shots["done"] = True
                        for c in (A, B):
                            evidence_shot(c, f"kill_r{n}", stale_shots, A.sh.log, missing_shots)

                def monitor():
                    while not duel.stop.is_set():
                        ev = round_fired()
                        if ev:
                            signal_seen(ev)
                            duel.stop.set()
                            return
                        if starv is not None and starv.stop_reason:
                            A.sh.log(f"STARVATION-WATCH ends round {n} at T+{time.time() - t_gameplay:.1f}s: "
                                     f"{starv.stop_reason}")
                            duel.stop.set()
                            return
                        if mpw.stalled is not None:
                            A.sh.log(f"MOVE-PATH STALL on {mpw.stalled[0]} ends the run at "
                                     f"T+{time.time() - t_gameplay:.1f}s -- nothing after this can move, "
                                     f"so nothing after this is evidence")
                            duel.stop.set()
                            return
                        if mpw.freeze_nodata is not None:
                            A.sh.log(f"MOVE-PATH NO-DATA on {mpw.freeze_nodata[0]} ends the run at "
                                     f"T+{time.time() - t_gameplay:.1f}s -- a freeze longer than {FREEZE_MAX_S:g}s: "
                                     f"{mpw.freeze_nodata[1].detail}")
                            duel.stop.set()
                            return
                        if time.time() - t_round > a.kill_timeout:
                            A.sh.log(f"kill timeout: {a.kill_timeout}s elapsed in round {n} with no signal")
                            duel.stop.set()
                            return
                        time.sleep(0.25)

                mon = threading.Thread(target=monitor, daemon=True)
                mon.start()
                endgame = None
                if a.endgame == "cooperative":
                    endgame = endgame_cooperative({"A": sideA, "B": sideB}, duel, starv, A.sh.log, map_name=a.map,
                                                  fight_s=a.fight_seconds, mover=mover, route_path=route_path)
                elif a.endgame == "route":
                    endgame = endgame_route({"A": sideA, "B": sideB}, duel, starv, A.sh.log, a.map, mover=mover,
                                            fight_s=a.fight_seconds, route_path=route_path,
                                            route_join="nearest" if n == 1 else "start", spawns=file_spawns,
                                            live_spawns=live_spawns)
                threads = []
                for me, oth in (() if watched_endgame else ((sideA, sideB), (sideB, sideA))):
                    # arrive == engage in this mode: two separate thresholds would let both sides
                    # stop at `arrive` without ever setting contact, and then nobody would shoot.
                    t = threading.Thread(
                        target=lambda m=me, o=oth: setattr(
                            m, "result", approach(m, o, duel, a.engage, a.max_steps,
                                                  a.max_walk_seconds, engage=a.engage)))
                    t.start()
                    threads.append(t)
                for t in threads:
                    t.join()
                A.sh.log(f"approach done: A={sideA.result and sideA.result.get('reason')} "
                         f"best={sideA.result and sideA.result.get('best')} "
                         f"B={sideB.result and sideB.result.get('reason')} "
                         f"best={sideB.result and sideB.result.get('best')}")
                fights = {}
                # Sprint 5 Task 5: the gate reads the CURRENT paired distance -- not the run minimum, and not
                # min(each side's latest), which printed 166.76 against launch 3c's true 52.42.
                closest_now = duel.current_d3()
                near = closest_now is not None and closest_now <= a.engage * 2.5
                if watched_endgame:
                    pass
                elif (duel.contact.is_set() or near) and not duel.stop.is_set():
                    ft = []
                    for me, oth in ((sideA, sideB), (sideB, sideA)):
                        t = threading.Thread(
                            target=lambda m=me, o=oth: fights.__setitem__(
                                m.tag, engage_fight(m, o, duel, a.fight_seconds)))
                        t.start()
                        ft.append(t)
                    for t in ft:
                        t.join()
                else:
                    A.sh.log(f"no contact (current paired 3-D {closest_now}, run minimum {duel.best_dist()} at "
                             f"dy {duel.best_dy()}): the engagement phase is skipped -- there is nothing in front of "
                             f"either player to shoot at")
                duel.stop.set()
                mon.join(timeout=5.0)
                if watched_endgame and round_fired() is None and mpw.stalled is None and mpw.freeze_nodata is None:
                    # C2 (fix round): the engagement returning is not the round ending. Both sides stand neutral while
                    # the watches run on, until KillWatch fires (00:00, the round step, a kill) -- otherwise the next
                    # round's 45 s wait starts with ~90-145 s of round clock left and every launch plays 1-2 rounds.
                    A.sh.log(f"ROUND {n} engagement over at T+{time.time() - t_gameplay:.1f}s "
                             f"({endgame and endgame.get('stop_reason')}): both sides stand neutral until the round "
                             f"ends (by the clock string's remaining time + {online_ladder.ROUND_END_SLACK_S:g}s)")
                    ev_end, why_end = online_ladder.wait_round_end(
                        {"A": A.tail, "B": B.tail}, round_fired,
                        stop=lambda: ("move path stalled" if mpw.stalled is not None else
                                      "a freeze past FREEZE_MAX_S" if mpw.freeze_nodata is not None else None))
                    if ev_end:
                        signal_seen(ev_end)
                    else:
                        A.sh.log(f"ROUND {n} end not seen: {why_end}")
                t_end = time.time()
                for c in (A, B):
                    evidence_shot(c, f"final_r{n}", stale_shots, A.sh.log, missing_shots)
                closest = duel.best_dist()
                # An armed watch that never read a word is a FAILED instrument, not a quiet one: it
                # would report "health never moved" having never looked. §3.10 rule 3, applied to the
                # one instrument the acceptance test will depend on (result_verdict makes it a FAIL).
                watch_reads = {t: c.tail.watch_reads for t, c in (("A", A), ("B", B))}
                watch_misses = {t: c.tail.watch_misses for t, c in (("A", A), ("B", B))}
                watch_hist = {t: len(c.tail.watch_hist) for t, c in (("A", A), ("B", B))}
                if health is not None and min(watch_reads.values()) == 0:
                    A.sh.log(f"HEALTH WATCH BLIND: armed at ACTOR+0x{health:x} and read "
                             f"{watch_reads} values ({watch_misses} rows where no peeked block "
                             f"covered it). 'health never moved' from an instrument that never "
                             f"looked is not evidence -- widen PS2X_PEEK to cover that offset.")
                events = [e for e in watch.events if t_round - 1.0 <= e["t"] <= t_end + 1.0]
                fired = next((e for e in events if e.get("firing")), None)
                verdict, is_kill = result_verdict(fired, events, health is not None,
                                                  watch_reads, stale_shots=stale_shots,
                                                  stalled=mpw.stalled, missing_shots=missing_shots)
                # the LADDER line (brief Interfaces): contact by verdict_core over the round's rows, damage by spec
                # §5 Goal 5(d) -- victim = the stander in --endgame, either direction otherwise
                contact = ladder_contact(A.tail, B.tail, t_round, t_end)
                inside = lambda rows: [r for r in rows if t_round <= r[0] <= t_end]
                if health is None:
                    damage = "unarmed"
                else:
                    if watched_endgame:
                        shooter_c, victim_c = (A, B) if mover == "A" else (B, A)
                        pairs = [("victim", victim_c, shooter_c, sideA if mover == "A" else sideB)]
                    else:
                        pairs = [("B", B, A, sideA), ("A", A, B, sideB)]
                    verdicts_d = [damage_verdict(inside(v.tail.watch_hist) if v.tail.watch_reads else [],
                                                 inside(v.tail.actor_ingame()), inside(s.tail.actor_ingame()),
                                                 side.r1_times)
                                  for _, v, s, side in pairs]
                    damage = ("yes" if "yes" in verdicts_d else vc.NO_DATA if vc.NO_DATA in verdicts_d else "no")
                ralarms = starv.round_alarms(t_round, t_end) if starv is not None else None
                max_idle = {t: max((v for tt, _, v in c.tail.rets.get("NetIdle", []) if t_round <= tt <= t_end),
                                   default=None) for t, c in (("A", A), ("B", B))}
                lag_rows = {t: len(inside(c.tail.lag_rows)) for t, c in (("A", A), ("B", B))}
                c_rows = None if contact.status == vc.NO_DATA else contact.contact_rows
                c_ok = None if contact.status == vc.NO_DATA else contact.ok
                if endgame is not None and (endgame.get("stop_reason") or "").startswith(vc.NO_DATA) and not is_kill:
                    verdict = endgame["stop_reason"]    # a spawn mismatch, a freeze in a fire window: not scored
                elif endgame is not None and endgame.get("fire_teleport") and not is_kill:
                    ftp = endgame["fire_teleport"]
                    verdict = (f"NO-DATA teleport-in-fire-window side={ftp['tag']} step={ftp['step']:.1f}u -- an "
                               f"actor row jumped during a burst; the round is not scored")
                elif endgame is not None and endgame.get("teleport") and not is_kill:
                    tp = endgame["teleport"]
                    verdict = (f"FAIL teleport side={tp['tag']} during={tp['during']} step={tp['step']:.1f}u -- an "
                               f"actor row jumped > {TELEPORT_STEP_UNITS:g} units; the attempt was aborted")
                rung = ladder_rung(ctl, c_ok, damage)
                rung0_tok = None
                if n == 1 and watched_endgame:
                    # R68: rung 0 is recorded (round-1 LADDER line, the summary), never fatal; the rounds continue
                    ok0, why0, f0 = rung0_check(t_end)
                    A.sh.log("RUNG0 " + " ".join(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}"
                                                 for k, v in sorted(f0.items())) + f" -> {f0.get('status')}")
                    rung0_tok, lines0 = online_ladder.rung0_report(ok0, why0, f0, ident)
                    for ln in lines0:
                        A.sh.log(ln)
                ladder = ladder_line(
                    rung=rung, controllable=ctl, contact_rows=c_rows,
                    contact_s=None if c_ok is None else contact.contact_s, sampler_s=contact.sampler_period_s,
                    rows_read=contact.rows_read, damage=damage, kill="yes" if is_kill else "no",
                    starvation_alarms=None if ralarms is None else sum(1 for x in ralarms if x["cause"] == "starvation"),
                    alarms_cleared=None if ralarms is None else sum(
                        1 for x in ralarms if x["cause"] == "starvation" and x["t_clear"] is not None
                        and x["t_clear"] - (x["t_move"] if x["t_move"] is not None else x["t"]) <= ALARM_CLEAR_S),
                    max_idle_ms=(max_idle["A"], max_idle["B"]), lagflag_rows=(lag_rows["A"], lag_rows["B"]),
                    aim_iters=aim_iters_field((sideA if mover == "A" else sideB).aims,
                                              t0=endgame and endgame.get("t_fight")),
                    round_n=n, mover=mover,
                    bp_waits=tuple(online_ladder.bp_waits(inside(c.tail.bp_rows)) for c in (A, B)), rung0=rung0_tok)
                if fired is None:
                    obs = [e["kind"] for e in events if not e.get("firing")]
                    if obs:
                        A.sh.log(f"non-firing observations only: {obs} -- a MediusPlayerReport is a "
                                 f"periodic client stats report, not a round boundary; a respawn while "
                                 f"the valves are live is not a round end")
                sig = (f"signal={fired['kind']} on={fired['tag']} t=T+{fired['t'] - t_gameplay:.1f}s "
                       f"detail={json.dumps(fired['detail'], default=float)} " if fired else
                       f"(no signal in {a.kill_timeout}s) ")
                A.sh.log(f"RESULT round={n} {verdict} {ident} {sig}"
                         f"closest_3d={closest} dy_at_closest={duel.best_dy()} contact={duel.contact.is_set()} "
                         f"rows A={len(A.tail.ingame())} B={len(B.tail.ingame())} "
                         f"actor_rows A={len(A.tail.actor_ingame())} B={len(B.tail.actor_ingame())} "
                         f"health_watch={'disarmed' if health is None else 'armed'} "
                         f"reads={watch_reads} misses={watch_misses} changes={watch_hist} "
                         f"stale_shots={stale_shots} missing_shots={missing_shots}")
                is_kill_any[0] = is_kill_any[0] or is_kill
                fatal = None
                if mpw.stalled is not None or mpw.freeze_nodata is not None:
                    fatal = "move path stalled or frozen past FREEZE_MAX_S"
                elif not watched_endgame:
                    fatal = "converge mode plays one round"
                rounds_out.append({
                    "round": n, "mover": mover, "round_value": round_value, "t": [t_round, t_end], "verdict": verdict,
                    "rung0": rung0_tok,
                    "ladder": ladder, "rung": rung, "kill": is_kill, "closest_3d_units": closest,
                    "closest_dy": duel.best_dy(), "contact": vars(contact), "events": events, "fired": fired,
                    "stale_shots": stale_shots, "missing_shots": missing_shots, "fight": fights,
                    "approach_A": sideA.result, "approach_B": sideB.result, "alarms": ralarms,
                    "endgame": None if endgame is None else {k: v for k, v in endgame.items() if k != "approach"}})
                return online_ladder.RoundScore(n=n, mover=mover, rung=rung, verdict=verdict, kill=is_kill,
                                                line=ladder, fatal=fatal, rung0=rung0_tok)

            rung0_tables = {}

            def rung0_check(t_end):
                t0 = min((c.tail.actor_ingame()[0][0] for c in (A, B) if c.tail.actor_ingame()), default=t_gameplay)
                sides0, pauses0 = {}, []
                for tag, c in (("A", A), ("B", B)):
                    rt, steps, _, _ = tail_clock_state(c.tail)
                    pauses0 += vc.clock_pauses(rt, steps)
                    with c.tail._lock:                   # noqa: SLF001 - same module
                        calls = [(t, n_) for t, n_, _ in c.tail.calls.get(MOVE_SCALE_TRACE_NAME, [])]
                        clock_s = [(t, st["clock"]) for t, st in c.tail.round_rows
                                   if not isinstance(st.get("clock"), vc.NoData)]
                        bp = list(c.tail.bp_rows)
                    sides0[tag] = {"calls": calls, "clock": clock_s, "bp": bp}
                return online_ladder.rung0_verdict(sides0, pauses0, t0, t_end)

            def next_round(n):
                prev = rounds_out[-1]["round_value"] if rounds_out else None
                spawns_n = {t: first_actor.get(t) or (file_spawns or {}).get(t) for t in "AB"}
                info = {}
                ok, reason, actors = online_ladder.wait_next_round({"A": A.tail, "B": B.tail}, prev, spawns=spawns_n,
                                                                   info=info)
                steps_txt = " ".join(
                    f"{t}(step={'%.1f' % s['step'] if s['step'] else '?'} restart="
                    f"{'%.1f' % s['restart'] if s['restart'] else '?'} spawn_d="
                    f"{'%.1f' % s['spawn_d'] if s['spawn_d'] is not None else '?'})" for t, s in sorted(info.items()))
                if ok:
                    A.sh.log(f"ROUND {n} starts: mp_round_count moved past {prev}, the guest clocks restarted and ran "
                             f"{online_ladder.NEXT_ROUND_CLOCK_RUN_S:g}s, both sides at their spawns, actors re-found "
                             f"by vtable {ACTOR_VTABLE:#x} at "
                             + " ".join(f"{t}={v:#x}" if v else f"{t}=?" for t, v in sorted(actors.items()))
                             + f" {steps_txt}")
                return ok, (reason + f" {steps_txt}" if not ok else reason)

            history, ladder_stop = online_ladder.run_ladder(a.rounds if watched_endgame else 1, play_round, next_round,
                                                            A.sh.log, mover=a.mover, auto_swap=a.auto_swap)
            watch.stop()
            mpw.stop()
            if starv is not None:
                starv.stop()
                A.sh.log(starv.summary_line())
            for c in (A, B):
                for line in valve_report(c.tag, c.tail, valves_wanted):
                    A.sh.log(line)
            summary = {
                "control": {tag: sd.status for tag, sd in control_sides.items()},
                "move_path": mpw.history,
                "valves": {c.tag: valve_report(c.tag, c.tail, valves_wanted) for c in (A, B)},
                "rounds": rounds_out, "ladder_stop": ladder_stop,
                "actor_addr": {"A": A.tail.actor_addr, "B": B.tail.actor_addr},
                "t_gameplay": t_gameplay,
                "events": watch.events,
                "starvation": None if starv is None else starv.alarms,
                "peek_item_rows": {t: dict(c.tail.item_rows) for t, c in (("A", A), ("B", B))},
                "ingame_rows": {"A": len(A.tail.ingame()), "B": len(B.tail.ingame())},
            }
            with open(os.path.join(a.out, "converge.json"), "w") as fh:
                json.dump(summary, fh, indent=1, default=str)
            if not is_kill_any[0] and (a.until_kill or any(r["verdict"].startswith(("FAIL health", "FAIL teleport"))
                                                          for r in rounds_out)):
                failed = True
        if a.sweep:
            # Same-team kill probe: A rotates in place (right stick) and fires a burst at every
            # step; B stands where it spawned (a few metres from A when both are SEALs).
            for i in range(a.sweep):
                A.sh.hold(a.turn_key, a.sweep_hold)
                A.sh.hold("R1", 0.4)
                A.sh.hold("R1", 0.4)
                A.sh.shot(f"sweep{i:02d}")
                B.sh.shot(f"sweep{i:02d}")
    except L.LobbyFail as e:
        # R47: exit 4 -- a launch whose lobby failed played no round; the launch summary says so and nothing counts
        # toward the ladder's usable rounds or its stop rules
        if a.converge:
            record_lobby_fail(a.out, a.rounds if watched_endgame else 1, e,
                              A.sh.log if A.sh is not None else (lambda m: print(m, flush=True)), ident)
        raise
    finally:
        A.kill()
        B.kill()
        subprocess.run(["taskkill", "/F", "/IM", "socom2.exe"], capture_output=True)
    if failed and a.control_round:
        raise SystemExit("--control-round: the negative control did not hold (see RESULT CONTROL-ROUND)")
    if failed:
        raise SystemExit("--until-kill: no KILL was observed -- FAIL. (A round end on its own is "
                         "not a kill: the round clock ends rounds too, and the health word that "
                         "would attribute one is not confirmed. See the RESULT line.)")


if __name__ == "__main__":
    main()
