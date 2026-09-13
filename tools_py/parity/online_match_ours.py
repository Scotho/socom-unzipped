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
import json
import math
import os
import re
import struct
import subprocess
import threading
import time

import numpy as np

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

    def _state_row(self, t, items):
        """Alive byte, round valves + clock string and per-valve identification counts, from one
        `[peek]` row's items (all of them, the camera record included)."""
        alive = vc.row_actor_field(items, self.alive_offset, "u8")
        actor = next((a for a, w in items if w and w[0] == ACTOR_VTABLE), None)
        valves = {name: vc.row_valve(items, name) for name in vc.VALVES}
        state = {name: valves[name] for name in vc.ROUND_VALVES}
        state["clock"] = vc.row_clock_string(items)
        with self._lock:
            self.latest_items = items
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

    def set_facing(self, tag, f):
        with self._lock:
            self.facing[tag] = f

    def get_facing(self, tag):
        with self._lock:
            return self.facing.get(tag)

    def set_dist(self, tag, d):
        with self._lock:
            self.dist[tag] = d

    def best_dist(self):
        with self._lock:
            v = [d for d in self.dist.values() if d is not None]
        return min(v) if v else None


class Side:
    """One instance as the approach loop sees it."""

    def __init__(self, tag, sh, tail, route=None):
        self.tag, self.sh, self.tail, self.route = tag, sh, tail, route
        self.turn_gain = 1.0
        self.best_3d = None          # the 2-D best flatters a stack; keep the honest one too
        self.spawn = None
        self.result = None


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

    def _add(self, kind, tag, detail, firing=None):
        ev = {"kind": kind, "tag": tag, "t": self.clock(), "detail": detail,
              "firing": (kind in self.FIRING) if firing is None else firing}
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
                                               "to": [b[1], b[3]], "fallback": fallback},
                              firing=fallback)
                elif (self._away[tag] and spawn is not None
                      and math.hypot(b[1] - spawn[0], b[3] - spawn[1]) <= RESPAWN_RADIUS):
                    self._away[tag] = False
                    fallback = not self.round_live(tag)
                    self._add("respawn", tag, {"back_at_spawn": [b[1], b[3]],
                                               "spawn": list(spawn), "fallback": fallback},
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


def assert_controllable(side, tail, sh, clock=time.time, wait=time.sleep,
                        max_holds=vc.PRECONDITION_MAX_HOLDS, max_attempts=PRECONDITION_MAX_ATTEMPTS):
    """Up to `max_holds` decisive 2 s forward holds on ACTOR rows, each preceded by 10+ s of fully
    neutral pad and, after the first, a 90 deg turn; each scored by vc.score_control (the spec's one
    bar). The side is CONTROLLABLE as soon as ANY hold passes, NO-CONTROL when every decisive hold
    failed, NO-DATA when none was decisive. Returns vc.SideControl.

    Pad timing is the harness's own write times (host clock); actor rows are host-timestamped on
    arrival by RunLogTail, i.e. up to one sampler period + the poll late. Blind: a half-decayed
    movement scale that still covers 40 units; motion in the wrong direction; a neutral-window drift
    that stays under 5 units because the player is frozen (hence the 40). The camera record
    0x416054 is never read here (kill3 B: it froze while the actor walked 67 units)."""
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
                v = vc.ControlVerdict(False, v.net_units, v.snapback_units, v.drift_units, vc.NO_DATA,
                                      f"scale {lo_s} < 1.0 around the hold (starved, not a control "
                                      f"verdict); was FAIL: {v.reason}", v.hold)
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
        t = threading.Thread(target=lambda tg=tag, cl=c: sides.__setitem__(
            tg, assert_controllable(tg, cl.tail, cl.sh)))
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
        self._stop_ev = threading.Event()

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
            v = vc.score_move_path(calls, alive, rounds, now)
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
    ap.add_argument("--no-route", action="store_true",
                    help="ignore the mined corridor and walk the straight line (the Task 7 policy)")
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
        refusals = move_path_preconditions(os.environ, alive_offset=(a.alive_offset if a.alive_offset is not None
                                                                     else vc.ACTOR_ALIVE_OFFSET))
        refusals += health_peek_problems(os.environ.get("PS2X_PEEK", ""), a.health_offset)
        if refusals:
            for prob in refusals:
                print(f"MOVE-PATH WATCH REFUSES: {prob}", flush=True)
            print("RESULT NO-DATA move-path watch (not launched)", flush=True)
            raise SystemExit(2)
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
            liveA = wait_ingame(A.tail, A.sh)
            liveB = wait_ingame(B.tail, B.sh)
            A.sh.log(f"in-game peek rows A={len(A.tail.ingame())} B={len(B.tail.ingame())} "
                     f"(log lines A={A.tail.lines} B={B.tail.lines})")
            if not (liveA and liveB):
                raise SystemExit("liveness check failed: the run never reached gameplay -- discard it")
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
                A.sh.log(f"RESULT {control if code == 3 else 'NO-DATA control'} -- the match is not "
                         f"spent: {why}")
                with open(os.path.join(a.out, "control.json"), "w") as fh:
                    json.dump({"result": control,
                               "sides": {tag: {"status": sd.status,
                                               "holds": [vars(v) for v in sd.holds]}
                                         for tag, sd in control_sides.items()},
                               "move_path": mpw.history}, fh, indent=1, default=str)
                raise SystemExit(code)
            # Task 8 (S3): BOTH sides close, then fight, and a KillWatch decides when it is over.
            duel = Duel()
            # The mined corridor is map-specific (research/18 §4.5). On any other map it would
            # steer along a route that does not exist, so it is dropped and the banner says so.
            mined_ok = (not a.no_route) and a.map.lower() == MINED_ROUTE_MAP
            route = MP51_SEAL_ROUTE if mined_ok else None
            A.sh.log(f"RUN BANNER map={a.map} "
                     f"route={'mined(' + MINED_ROUTE_MAP + ')' if mined_ok else 'direct'} "
                     f"engage3d={a.engage} dy_tol={a.engage_dy} "
                     f"pos={'actor' if A.tail.actor_ingame() else 'camera-reconstruction'} "
                     f"health={'armed@+0x%x' % a.health_offset if a.health_offset is not None else 'disarmed'} "
                     f"alive={'@+0x%x' % a.alive_offset if a.alive_offset is not None else 'disarmed'}")
            sideA = Side("A", A.sh, A.tail, route=route)
            sideB = Side("B", B.sh, B.tail, route=None)   # B's half of the map has no mined track
            spawns = {}
            for tag, c in (("A", A), ("B", B)):
                rows = c.tail.ingame()
                if rows:
                    spawns[tag] = (rows[0][1], rows[0][3])
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
            kill_shots = {"done": False}

            stale_shots = []
            missing_shots = []

            def monitor():
                while not duel.stop.is_set():
                    if watch.fired:
                        ev = watch.fired
                        A.sh.log(f"KILL/ROUND-END SIGNAL {ev['kind']} on {ev['tag']} at "
                                 f"T+{ev['t'] - t_gameplay:.1f}s {json.dumps(ev['detail'], default=float)}")
                        if not kill_shots["done"]:
                            kill_shots["done"] = True
                            for c in (A, B):
                                evidence_shot(c, "kill", stale_shots, A.sh.log, missing_shots)
                        duel.stop.set()
                        return
                    if mpw.stalled is not None:
                        A.sh.log(f"MOVE-PATH STALL on {mpw.stalled[0]} ends the run at "
                                 f"T+{time.time() - t_gameplay:.1f}s -- nothing after this can move, "
                                 f"so nothing after this is evidence")
                        duel.stop.set()
                        return
                    if time.time() - t_gameplay > a.kill_timeout:
                        A.sh.log(f"kill timeout: {a.kill_timeout}s elapsed with no signal")
                        duel.stop.set()
                        return
                    time.sleep(0.25)

            mon = threading.Thread(target=monitor, daemon=True)
            mon.start()
            threads = []
            for me, oth in ((sideA, sideB), (sideB, sideA)):
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
            closest_now = duel.best_dist()
            near = closest_now is not None and closest_now <= a.engage * 2.5
            if (duel.contact.is_set() or near) and not duel.stop.is_set():
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
                A.sh.log(f"no contact (closest {closest_now}): the engagement phase is skipped "
                         f"-- there is nothing in front of either player to shoot at")
            duel.stop.set()
            mon.join(timeout=5.0)
            watch.stop()
            mpw.stop()
            for c in (A, B):
                evidence_shot(c, "final", stale_shots, A.sh.log, missing_shots)
            for c in (A, B):
                for line in valve_report(c.tag, c.tail, valves_wanted):
                    A.sh.log(line)
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
            verdict, is_kill = result_verdict(watch.fired, watch.events, health is not None,
                                              watch_reads, stale_shots=stale_shots,
                                              stalled=mpw.stalled, missing_shots=missing_shots)
            ra, rb = A.tail.latest(max_age=1e9), B.tail.latest(max_age=1e9)
            summary = {
                "control": {tag: sd.status for tag, sd in control_sides.items()},
                "move_path": mpw.history,
                "valves": {c.tag: valve_report(c.tag, c.tail, valves_wanted) for c in (A, B)},
                "stale_shots": stale_shots,
                "missing_shots": missing_shots,
                "verdict": verdict,
                "contact": duel.contact.is_set(),
                "closest_3d_units": closest,
                "best_3d_per_side": {"A": sideA.best_3d, "B": sideB.best_3d},
                "actor_rows": {"A": len(A.tail.actor_ingame()), "B": len(B.tail.actor_ingame())},
                "health_watch": {"armed_offset": health, "reads": watch_reads,
                                 "misses": watch_misses, "changes": watch_hist},
                "actor_addr": {"A": A.tail.actor_addr, "B": B.tail.actor_addr},
                "final_records": {"A": ra, "B": rb},
                "final_dy": (rb[2] - ra[2]) if (ra and rb) else None,
                "best_3d": {"A": sideA.best_3d, "B": sideB.best_3d},
                "approach_A": sideA.result, "approach_B": sideB.result,
                "fight": fights,
                "fired": watch.fired,
                "events": watch.events,
                "t_gameplay": t_gameplay,
                "peek_item_rows": {t: dict(c.tail.item_rows) for t, c in (("A", A), ("B", B))},
                "ingame_rows": {"A": len(A.tail.ingame()), "B": len(B.tail.ingame())},
            }
            with open(os.path.join(a.out, "converge.json"), "w") as fh:
                json.dump(summary, fh, indent=1, default=str)
            # One line, and it names the signal. research/18 §3.10: an instrument that emits zero
            # rows is a failed run, so the row counts are on the same line. PASS is reserved for a
            # signal only a KILL produces (result_verdict): `round` and `respawn` end rounds, and a
            # round ends on its clock too.
            ev = watch.fired
            if ev is None:
                obs = [e["kind"] for e in watch.events if not e.get("firing")]
                if obs:
                    A.sh.log(f"non-firing observations only: {obs} -- a MediusPlayerReport is a "
                             f"periodic client stats report, not a round boundary; a respawn while "
                             f"the valves are live is not a round end")
            sig = (f"signal={ev['kind']} on={ev['tag']} t=T+{ev['t'] - t_gameplay:.1f}s "
                   f"detail={json.dumps(ev['detail'], default=float)} " if ev else
                   f"(no signal in {a.kill_timeout}s) ")
            A.sh.log(f"RESULT {verdict} {sig}"
                     f"closest_3d={closest} contact={duel.contact.is_set()} "
                     f"rows A={len(A.tail.ingame())} B={len(B.tail.ingame())} "
                     f"actor_rows A={len(A.tail.actor_ingame())} B={len(B.tail.actor_ingame())} "
                     f"health_watch={'disarmed' if health is None else 'armed'} "
                     f"reads={watch_reads} misses={watch_misses} changes={watch_hist} "
                     f"stale_shots={stale_shots} missing_shots={missing_shots}")
            if not is_kill and (a.until_kill or verdict.startswith("FAIL health")):
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
    finally:
        A.kill()
        B.kill()
        subprocess.run(["taskkill", "/F", "/IM", "socom2.exe"], capture_output=True)
    if failed:
        raise SystemExit("--until-kill: no KILL was observed -- FAIL. (A round end on its own is "
                         "not a kill: the round clock ends rounds too, and the health word that "
                         "would attribute one is not confirmed. See the RESULT line.)")


if __name__ == "__main__":
    main()
