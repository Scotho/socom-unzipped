"""Closed-loop dry run of the approach loop against a SIMULATED world -- no match, no game.

The world writes `[peek] @416054` rows and `MoveScale f12=1.0` rows into temp logs at 4 Hz, exactly
as the exe does, and the REAL `RunLogTail` reads them; the fake `Shell.pad` applies the stick state
to the simulated player. So the thing under test is the shipped loop, not a copy of it.

Every scenario deliberately MISMATCHES the world's turn response against the harness constants, so
each correction overshoots or undershoots and the loop has to recover by re-measuring -- which is
what the real game does (research/18 §3.13: RMS 18 deg on an open-loop turn, and one wtb2 turn that
asked for -72 deg and delivered -16).

    python -m tools_py.parity.sim_walk_to_b [open|maze|caps|converge|route|stack|watch|nocontrol|movepath|
                                             endgame|endgame-negative|endgame-rule|engage-route|
                                             engage-route-starved|engage-route-swap|engage-route-teleport|all]

Sprint 5 Task 5 added the engagement's own world (`endgame`): a TWO-SIDED STARVATION MODEL (`Net`: each
side's idle ms is reset only by the OTHER side's traffic -- translation always, rotation iff
`rotation_feeds`, firing iff `firing_feeds`; the scale clamp((5000 - (idle - 1500)) * 0.001, 0, 1) on
translation AND rotation; ng+0xde at idle >= 4501; `[ret] NetIdle #n v0=` and `MoveScale #n f12=` rows),
TWO FLOORS (`TwoFloorTerrain`: y 100 and a ledge at y 142 reached by one ramp), the actor matrix at
+0x80..+0xbc (heading lagging the true facing after a turn), partial-deflection sticks with a yaw dead zone,
a lead and a WRONG gain, and a ticking round clock. `rotation_feeds` / `firing_feeds` default False until
Task 5 Step 1 measures them live; re-run these scenarios with the measured values afterwards.

The per-scenario step counts and wall times this prints are ILLUSTRATIVE, not constants: the
simulation is wall-clock timed and varies run to run (one `maze` took 14 steps / 102 s and another
29 / 206 s on the same code). What is asserted is the OUTCOME -- arrival, the cap, the signal --
and, for `converge`, that the distance the loop REPORTS tracks the simulated truth.

Task 7 wrote this in a scratch directory and lost it. It lives next to the harness now.
"""
import math
import os
import struct
import sys
import tempfile
import threading
import time

from . import online_login_ours as L
from . import online_match_ours as M
from . import verdict_core as vc


def _w(v):
    return f"{struct.unpack('<I', struct.pack('<f', v))[0]:08x}({v:g})"


def _name_words(text):
    raw = (text.encode("ascii") + b"\0" * 12)[:12]
    return struct.unpack("<III", raw)


def state_items(actor_addr, alive=1, round_count=0, game_over=0, clock="05:00"):
    """The Sprint 5 state items as the exe prints them under launch 1's PS2X_PEEK: actor+0xF78 (the
    alive byte is its byte 2), mp_round_count and mp_game_over (value item + name-bytes item printed
    at the name pointer, research/21 §2.2) and the clock string."""
    parts = [f"@{actor_addr + 0xF78:x}: {(alive & 0xFF) << 16:08x}(0)"]
    for name, value_addr, name_ptr, value in (("mp_round_count", 0x694C48, 0x006B7F30, round_count),
                                              ("mp_game_over", 0x694C20, 0x006B7F20, game_over)):
        parts.append(f"@{value_addr:x}: {name_ptr:08x}(0) {0x00010000 | (value & 0xFFFF):08x}(0)")
        parts.append(f"@{name_ptr:x}: " + " ".join(f"{w:08x}(0)" for w in _name_words(name)))
    w0, w1 = struct.unpack("<II", (clock.encode("ascii") + b"\0" * 8)[:8])
    parts.append(f"@408f10: {w0:08x}(0) {w1:08x}(0)")
    return " ".join(parts)


# The instrument environment the sim's MovePathWatch runs under: launch 1's shape (research/21 §6.1).
SIM_ENV = {"PS2X_CALL_TRACE": "0x553dc0:MoveScale,0x30cd80:NetIdle", "PS2X_CALL_TRACE_EVERY": "10",
           "PS2X_PEEK": "0x416054:3,*0x408c58:64,*0x408c58+0xF78:24,*0x437ce8+0x0c*:2,"
                        "*0x437ce8+0x10*:2,*0x437ce8+0x0c**:3,*0x437ce8+0x10**:3,0x408f10:2"}


def matrix_words(facing_deg):
    """actor +0x80..+0xbc (block words 32..47) for a walk facing: theta = facing + 90 deg (research/22 §4)."""
    th = math.radians(facing_deg + 90.0)
    w = ["00000000(0)"] * 16
    w[0], w[2] = _w(math.cos(th)), _w(math.sin(th))
    w[5] = _w(1.0)
    w[8], w[10] = _w(-math.sin(th)), _w(math.cos(th))
    w[15] = _w(1.0)
    return w


def peek_line(cx, cy, cz, actor=None, actor_addr=0x01794000, matrix_facing=None):
    """The camera record, and -- as the exe writes it when the actor chain resolves -- the ACTOR
    block beside it, with the class vtable in word 0 and the true position in words 7/8/9.

    The loop prefers the actor read, so the simulation has to provide it or it would be testing the
    fallback. It is also what makes the simulation able to CATCH the measurement bug: on the
    committed code this file reported a best separation of 40.3 against a simulated ground truth of
    64.3 (and 23.4 vs 30.7, and 157.6 vs 204.7) in a world with no vertical dimension at all, which
    can only be the camera+facing orbit reconstruction.
    """
    line = f"[peek] @416054: {_w(cx)} {_w(cy)} {_w(cz)}"
    if actor is not None:
        words = ["006691a0(9.41946e-39)"] + ["00000000(0)"] * 63
        for slot, v in zip(M.ACTOR_POS_WORDS, actor):
            words[slot] = _w(v)
        if matrix_facing is not None:
            words[32:48] = matrix_words(matrix_facing)
        line += f" @{actor_addr:x}: " + " ".join(words)
    return line


NG_ADDR = 0x869360                    # launch 3c's CZNetGame block (research/21 §8.2)


def ng_items(lagflag):
    """`*0x437ce8:64` and `*0x437ce8+0x100:21` as launch 1 split them: ng+0xde in the first, the +0x118 = 50.0f
    fingerprint in the second (verdict_core.ng_lagflag_rows finds the block by content)."""
    ng = ["00000000(0)"] * 64
    ng[vc.NG_LAG_FLAG_OFFSET // 4] = f"{(lagflag & 0xFF) << (8 * (vc.NG_LAG_FLAG_OFFSET % 4)):08x}(0)"
    tail = ["00000000(0)"] * 21
    tail[(0x118 - 0x100) // 4] = f"{vc.NG_FINGERPRINT_VALUE:08x}(50)"
    return f"@{NG_ADDR:x}: " + " ".join(ng) + f" @{NG_ADDR + 0x100:x}: " + " ".join(tail)


class Net:
    """The two-sided starvation model (KNOWN §4, research/21 §9.8): side X's idle ms is the time since the
    OTHER side's last traffic. Translation always counts; rotation iff `rotation_feeds`; firing iff
    `firing_feeds` -- both False until Task 5 Step 1 measures them. `enabled=False` holds every idle at 0 (a
    scripted pre-roll that is history, not the scenario)."""

    TAGS = ("A", "B")

    def __init__(self, rotation_feeds=False, firing_feeds=False, t0=None, keepalive=False):
        self.rotation_feeds, self.firing_feeds, self.t0 = rotation_feeds, firing_feeds, t0
        # keepalive: a running (unfrozen) instance feeds the other with no traffic at all -- launch 3c's pair stood
        # ~48 s still at f12 = 1.0 (NetIdle <= 1547 ms). False is the pessimistic translation-only model.
        self.keepalive = keepalive
        self.last = {}
        self.max_idle = {}
        self.enabled = True
        self.lock = threading.Lock()

    @staticmethod
    def scale(idle_ms):
        """FUN_00594cf0's movement scale: 1.0 up to 5500 ms idle, 0.0 from 6500 (research/18 §3.12)."""
        return max(0.0, min(1.0, (5000 - (idle_ms - 1500)) * 0.001))

    @staticmethod
    def lagflag(idle_ms):
        return 1 if idle_ms >= 4501 else 0

    @staticmethod
    def other(tag):
        return "B" if tag == "A" else "A"

    def tick(self, tag, t, translated=False, rotated=False, fired=False):
        with self.lock:
            if self.t0 is None:
                self.t0 = t
            sent = (self.keepalive or translated or (rotated and self.rotation_feeds)
                    or (fired and self.firing_feeds))
            if sent:
                self.last[tag] = t
            return sent

    def idle_ms(self, tag, t):
        with self.lock:
            if self.t0 is None:
                self.t0 = t
            if not self.enabled:
                return 0
            ms = max(0, int(round((t - self.last.get(self.other(tag), self.t0)) * 1000.0)))
            self.max_idle[tag] = max(self.max_idle.get(tag, 0), ms)
            return ms

    def restart(self, t):
        """Enable the model from host time t with both sides just heard from, and forget the maxima."""
        with self.lock:
            self.t0 = t
            self.last = {tag: t for tag in self.TAGS}
            self.max_idle = {}
            self.enabled = True


class TwoFloorTerrain:
    """Frostfire's shape in miniature (KNOWN §4: floors at y ~100 and ~142). The lower floor is everywhere; a
    LEDGE at y 142 covers x 600-800, z 600-780 and is reached only by a RAMP (x 670-750, z 480-600, y rising
    100 -> 142 northward). A lower-floor walker passes UNDER the ledge; the ramp is a solid wedge from its sides
    and from under the ledge; the ledge has railings (leaving it anywhere but down the ramp is blocked)."""

    LOWER_Y, UPPER_Y = 100.0, 142.0
    LEDGE = (600.0, 800.0, 600.0, 780.0)
    RAMP = (670.0, 750.0, 480.0, 600.0)

    def in_ledge(self, x, z):
        x0, x1, z0, z1 = self.LEDGE
        return x0 <= x <= x1 and z0 <= z <= z1

    def in_ramp(self, x, z):
        x0, x1, z0, z1 = self.RAMP
        return x0 <= x <= x1 and z0 <= z < z1

    def step(self, floor, x, z, nx, nz):
        """-> (allowed, floor after the step)."""
        rx0, rx1, rz0, rz1 = self.RAMP
        if floor == "lower":
            if self.in_ramp(nx, nz):
                return (True, "ramp") if (not self.in_ramp(x, z) and z < rz0) else (False, floor)
            return True, "lower"
        if floor == "ramp":
            if self.in_ramp(nx, nz):
                return True, "ramp"
            if self.in_ledge(nx, nz) and nz >= rz1:
                return True, "upper"
            if nz < rz0 and rx0 <= nx <= rx1:
                return True, "lower"
            return False, floor
        if self.in_ledge(nx, nz):
            return True, "upper"
        if self.in_ramp(nx, nz):
            return True, "ramp"
        return False, floor

    def y(self, floor, x, z):
        if floor == "lower":
            return self.LOWER_Y
        if floor == "upper":
            return self.UPPER_Y
        f = max(0.0, min(1.0, (z - self.RAMP[2]) / (self.RAMP[3] - self.RAMP[2])))
        return self.LOWER_Y + (self.UPPER_Y - self.LOWER_Y) * f


class World:
    """One simulated player. Truth is (x, z, facing); the log carries the camera record only."""

    def __init__(self, path, x, z, facing, walk_u_s, look_deg_s, radius, wall=None, height=None,
                 actor_addr=0x01794000, ignores_pad=False, valves=True, terrain=None, floor="lower",
                 net=None, tag=None, yaw=None, move_dz=0, tick_clock=False, back_u_s=None):
        self.path, self.x, self.z, self.facing = path, x, z, facing
        # Task 5: the engagement world. `yaw` = (gain, dead zone, lead s): rx turns at the harness's OWN table
        # times a WRONG gain, nothing inside the dead zone, nothing for the first `lead` s of a hold (None: the
        # legacy constant look rate). `move_dz`: left-stick dead zone, speed linear above it. The actor matrix
        # heading `mf` lags the facing after a turn (halving each row, snapping inside 0.5 deg).
        self.terrain, self.floor, self.net, self.tag = terrain, floor, net, tag
        self.yaw, self.move_dz, self.tick_clock = yaw, move_dz, tick_clock
        self.back = walk_u_s if back_u_s is None else back_u_s   # legacy worlds walk back at the forward rate
        self.mf = facing
        self.axes, self.buttons = {}, set()
        self.rx_hold_t = None
        self.round_t = 0.0
        self.frozen_until = None
        self.teleport_by = None          # (host time, dx, dz): a relative jump (the teleport-abort scenario)
        self.idle = 0
        self.scale = 1.0
        self.netidle_n = 0
        self.hist = []                   # (t, x, y, z, facing, mf, scale, idle, floor)
        self.valves = valves             # write the alive/valve/clock items (launch 1's PS2X_PEEK)
        # nocontrol: the player ignores the pad (frost1/launch 1c: rows keep coming, nothing moves)
        self.ignores_pad = ignores_pad
        # movepath: MoveScale stops being logged while the rows keep coming (launch 1c's R6 stop)
        self.movescale_stopped = False
        self.move_n = 0
        self.walk, self.look, self.r, self.wall = walk_u_s, look_deg_s, radius, wall
        self.height = height or (lambda x, z: -131.0)
        self.actor_addr = actor_addr
        self.state = {}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.teleport_at = None          # (host time, x, z) -- a respawn, for the KillWatch test
        open(path, "w").close()
        threading.Thread(target=self._tick, daemon=True).start()

    def _try_move(self, heading_deg, dt=0.25, speed=None):
        h = math.radians(heading_deg)
        speed = self.walk if speed is None else speed
        nx = self.x + speed * dt * math.cos(h)
        nz = self.z + speed * dt * math.sin(h)
        if self.wall is not None and self.wall(nx, nz):
            return
        if self.terrain is not None:
            ok, floor = self.terrain.step(self.floor, self.x, self.z, nx, nz)
            if not ok:
                return
            self.floor = floor
        self.x, self.z = nx, nz

    def y(self):
        return self.terrain.y(self.floor, self.x, self.z) if self.terrain else self.height(self.x, self.z)

    def _axis(self, dev):
        """Stick deflection (-128..127 from neutral) -> signed speed fraction with the move dead zone."""
        f = max(0.0, min(1.0, (abs(dev) - self.move_dz) / (127.0 - self.move_dz)))
        return math.copysign(f, dev) if f else 0.0

    def camera(self):
        h = math.radians(self.facing)
        return self.x - self.r * math.cos(h), self.z - self.r * math.sin(h)

    # Physics runs in SUBSTEPS per 0.25 s row. On whole 0.25 s ticks a 0.4 s strafe leg covered one tick or two
    # depending on its phase, so an alternating oscillation random-walked by a leg's length (Task 5 endgame:
    # the victim's centre wandered +-3 units at 13 units of range and forced re-aims the real game would not).
    SUBSTEPS = 5

    def _step(self, now, sdt, row):
        """One physics substep of `sdt` s (lock held). `row`: this substep ends a 0.25 s row -- the matrix lag, the
        round clock and the truth history advance per row."""
        if self.teleport_at and now >= self.teleport_at[0]:
            self.x, self.z = self.teleport_at[1], self.teleport_at[2]
            self.teleport_at = None
        if self.teleport_by and now >= self.teleport_by[0]:
            self.x, self.z = self.x + self.teleport_by[1], self.z + self.teleport_by[2]
            self.teleport_by = None
        frozen = self.frozen_until is not None and now < self.frozen_until
        # the pad: legacy key holds (`state`) and the injected axes/buttons (FakeShell.pad)
        ax = {"rx": 0x80, "ry": 0x80, "lx": 0x80, "ly": 0x80}
        buttons = set()
        if not (self.ignores_pad or frozen):
            for k, on in self.state.items():
                if on:
                    name, value = L.PAD_AXIS[k.upper()]
                    ax[name] = value
            ax.update(self.axes)
            buttons = set(self.buttons)
        if self.net is not None and not frozen:
            self.idle = self.net.idle_ms(self.tag, now)
            self.scale = Net.scale(self.idle)
        x0, z0, f0 = self.x, self.z, self.facing
        if not frozen:
            # EVERY translation is checked against the wall, not only the forward walk. The
            # original world blocked `W` and let `S`, `A` and `D` pass straight through, so
            # the loop's own unstick manoeuvre (a step back and a sidestep) could put the
            # player INSIDE solid geometry -- after which every forward move was blocked for
            # good. That is what made `maze` flaky: 14, 18, 23 and 29 steps on four runs, and
            # on a fifth a full 40-step budget spent pinned inside the wall at x~720, z~1300.
            fwd = self._axis(0x80 - ax["ly"])
            if fwd:
                self._try_move(self.facing if fwd > 0 else self.facing + 180.0, dt=sdt,
                               speed=(self.walk if fwd > 0 else self.back) * abs(fwd) * self.scale)
            dev = ax["rx"] - 0x80
            if dev and self.rx_hold_t is None:
                self.rx_hold_t = now
            elif not dev:
                self.rx_hold_t = None
            if self.yaw is None:
                rate = self.look * max(-1.0, min(1.0, dev / 127.0))
            else:
                gain, dz, lead = self.yaw
                rate = 0.0
                if abs(dev) > dz and now - self.rx_hold_t >= lead - 1e-6:
                    rate = math.copysign(M.yaw_rate_deg_s(abs(dev)), dev) * gain
            if rate:
                self.facing = M.wrap_deg(self.facing + rate * self.scale * sdt)
            lat = self._axis(ax["lx"] - 0x80)
            if lat:
                self._try_move(self.facing - 90.0 if lat > 0 else self.facing + 90.0, dt=sdt,
                               speed=self.walk * abs(lat) * self.scale)
            if row:
                d = M.wrap_deg(self.facing - self.mf)
                self.mf = self.facing if abs(d) < 0.5 else M.wrap_deg(self.mf + 0.5 * d)
                if self.tick_clock:
                    self.round_t += sdt * self.SUBSTEPS
            if self.net is not None:
                self.net.tick(self.tag, now,
                              translated=math.hypot(self.x - x0, self.z - z0) > 1e-6,
                              rotated=abs(M.wrap_deg(self.facing - f0)) > 1e-6,
                              fired="R1" in buttons)
        if row:
            self.hist.append((now, self.x, self.y(), self.z, self.facing, self.mf, self.scale, self.idle,
                              self.floor))
        return frozen

    def _tick(self):
        dt, n = 0.25, 0
        sdt = dt / self.SUBSTEPS
        next_t = time.time()
        while not self.stop.is_set():
            for sub in range(self.SUBSTEPS):
                with self.lock:
                    frozen = self._step(time.time(), sdt, sub == self.SUBSTEPS - 1)
                next_t += sdt
                time.sleep(max(0.0, next_t - time.time()))
            with self.lock:
                cx, cz = self.camera()
                y = self.y()
                scale, idle, mf, round_t = self.scale, self.idle, self.mf, self.round_t
            n += 1
            with open(self.path, "a") as f:
                if n % 2 == 0 and not self.movescale_stopped and not frozen:
                    # #n advances as the exe's does at EVERY=10 (~19 calls/s -> ~1 line per 0.5 s)
                    self.move_n += 10
                    f12 = "1.0" if scale == 1.0 else f"{scale:.3f}"
                    f.write(f"[call] {400.0 + n * dt:.1f}s MoveScale #{self.move_n} a0=0x1 "
                            f"ra=0x595028 f12={f12} f13=0.0 f14=1.0\n")
                    if self.net is not None:
                        self.netidle_n += 10
                        f.write(f"[call] {400.0 + n * dt:.1f}s NetIdle #{self.netidle_n} a0=0x45a0c0 "
                                f"ra=0x594f88 f12=0.0\n[ret] NetIdle #{self.netidle_n} v0=0x{idle:x} f0=0.6\n")
                extra = ""
                if self.valves:
                    left = max(0, 359 - int(round_t)) if self.tick_clock else None
                    extra = " " + (state_items(self.actor_addr) if left is None else
                                   state_items(self.actor_addr, clock=f"{left // 60:02d}:{left % 60:02d}"))
                if self.tick_clock:
                    extra += f" @4365c0: {_w(round_t)}"
                if self.net is not None:
                    extra += " " + ng_items(Net.lagflag(idle))
                f.write(peek_line(cx, y + 19.7, cz, actor=(self.x, y, self.z), actor_addr=self.actor_addr,
                                  matrix_facing=mf if self.yaw is not None else None) + extra + "\n")


class FakeShell:
    def __init__(self, world, tag):
        self.world, self.tag = world, tag
        self.lines = []

    def log(self, m):
        self.lines.append(m)
        print(f"{self.tag}{m}", flush=True)

    def shot(self, label):
        pass

    def pad(self, seconds, buttons=(), sticks=(), axes=None, abort=None):
        ax = L.pad_axes(sticks, axes)
        with self.world.lock:
            self.world.state = {}
            self.world.axes, self.world.buttons = ax, {b.upper() for b in buttons}
        if abort is None:
            time.sleep(seconds)
        else:
            abort.wait(seconds)
        with self.world.lock:
            self.world.state = {}
            self.world.axes, self.world.buttons = {}, set()


class FakeClient:
    def __init__(self, sh):
        self.sh = sh


def _worlds(label, ax, az, af, bx, bz, bf, wall=None, bwall=None, look_mismatch=0.78,
            aheight=None, bheight=None, a_ignores=False, b_ignores=False, valves=True):
    # The logs are PER PROCESS. They used to be `sim_A_<label>.log` in the shared temp dir, so two
    # suites running at once -- which happened, because `pkill` is a no-op in Git Bash and the old
    # suite was never killed -- interleaved two simulated worlds into one log. The loop then read
    # rows from both, `open` walked 1240 units AWAY from its target after three identical green
    # runs, and the failure looked exactly like a regression in the code under test.
    d = tempfile.gettempdir()
    label = f"{label}_{os.getpid()}"
    wa = World(os.path.join(d, f"sim_A_{label}.log"), ax, az, af, M.WALK_UNITS_PER_S_LONG,
               M.LOOK_DEG_PER_S * M.LOOK_RIGHT_SIGN * look_mismatch, 27.0, wall, aheight,
               actor_addr=0x01794000, ignores_pad=a_ignores, valves=valves)
    wb = World(os.path.join(d, f"sim_B_{label}.log"), bx, bz, bf, M.WALK_UNITS_PER_S_LONG,
               M.LOOK_DEG_PER_S * M.LOOK_RIGHT_SIGN / look_mismatch, 27.0, bwall, bheight,
               actor_addr=0x017a4000, ignores_pad=b_ignores, valves=valves)
    ta, tb = M.RunLogTail(wa.path), M.RunLogTail(wb.path)
    ta.start()
    tb.start()
    time.sleep(1.0)
    return wa, wb, ta, tb


def run(label, ax, az, af, bx, bz, bf, wall=None, arrive=120.0, max_steps=40, max_seconds=290.0):
    """One mover (the Task 7 shape): A walks to a parked B."""
    wa, wb, ta, tb = _worlds(label, ax, az, af, bx, bz, bf, wall)
    A, B = FakeClient(FakeShell(wa, "A_")), FakeClient(FakeShell(wb, "B_"))
    t0 = time.time()
    r = M.walk_to_b(A, B, ta, tb, arrive, max_steps, max_seconds, shots=False)
    true_d = math.hypot(wb.x - wa.x, wb.z - wa.z)
    print(f"\n== {label}: ok={r['ok']} reason={r['reason']} steps={r['steps']} "
          f"reported_best={r.get('best')} TRUE final distance={true_d:.2f} "
          f"wall={time.time() - t0:.0f}s")
    for w in (wa, wb):
        w.stop.set()
    ta.stop()
    tb.stop()
    return r, true_d


def run_converge(label, route=None, wall=None, bwall=None, arrive=22.0, engage=22.0,
                 max_steps=40, max_seconds=290.0, aheight=None, bheight=None):
    """Both movers (what a match runs): A and B walk toward each other from the mp51 spawns."""
    ax, az = M.MP51_SEAL_SPAWN
    bx, bz = M.MP51_TERROR_SPAWN
    wa, wb, ta, tb = _worlds(label, ax, az, 20.0, bx, bz, 160.0, wall, bwall,
                             aheight=aheight, bheight=bheight)
    duel = M.Duel()
    sideA = M.Side("A", FakeShell(wa, "A_"), ta, route=route)
    sideB = M.Side("B", FakeShell(wb, "B_"), tb, route=None)
    t0 = time.time()
    out = {}
    ts = []
    for me, oth in ((sideA, sideB), (sideB, sideA)):
        t = threading.Thread(target=lambda m=me, o=oth: out.__setitem__(
            m.tag, M.approach(m, o, duel, arrive, max_steps, max_seconds, shots=False,
                              engage=engage)))
        t.start()
        ts.append(t)
    for t in ts:
        t.join()
    ay, by = wa.height(wa.x, wa.z), wb.height(wb.x, wb.z)
    true_d = math.dist((wa.x, ay, wa.z), (wb.x, by, wb.z))
    walked = {}
    for tag, r in out.items():
        walked[tag] = sum((s.get("walk") or {}).get("dist") or 0.0 for s in r["track"])
    start_d = math.hypot(bx - ax, bz - az)
    closed = start_d - true_d
    print(f"\n== {label}: A={out['A']['reason']}/{out['A']['steps']} steps "
          f"B={out['B']['reason']}/{out['B']['steps']} steps  reported best="
          f"{min(out['A'].get('best') or 1e9, out['B'].get('best') or 1e9):.1f}  "
          f"TRUE final distance={true_d:.2f}  start={start_d:.1f}  "
          f"walked A={walked['A']:.0f} B={walked['B']:.0f}  "
          f"efficiency={100.0 * closed / max(walked['A'] + walked['B'], 1e-6):.1f}%  "
          f"wall={time.time() - t0:.0f}s")
    for w in (wa, wb):
        w.stop.set()
    ta.stop()
    tb.stop()
    return out, true_d, walked, closed


def run_watch(label="watch", valves=True):
    """The KillWatch's respawn signal: a player that teleports back to its spawn. With the round
    valves peeked it is recorded and does NOT fire; without them it is the fallback and fires."""
    ax, az = M.MP51_SEAL_SPAWN
    bx, bz = M.MP51_TERROR_SPAWN
    wa, wb, ta, tb = _worlds(label, ax, az, -60.0, bx, bz, 120.0, valves=valves)
    sha = FakeShell(wa, "A_")
    time.sleep(1.5)
    spawns = {"A": (ta.ingame()[0][1], ta.ingame()[0][3]),
              "B": (tb.ingame()[0][1], tb.ingame()[0][3])}
    watch = M.KillWatch({"A": ta, "B": tb}, spawns, server_log=os.path.join(
        tempfile.gettempdir(), "sim_no_such_server.log"))
    watch.start()
    # Walk A well away from its spawn, then teleport it back: a death on a one-life round.
    with wa.lock:
        wa.state = {"W": True}
    time.sleep(9.0)
    with wa.lock:
        wa.state = {}
    time.sleep(1.0)
    moved = math.hypot(wa.x - ax, wa.z - az)
    with wa.lock:
        wa.teleport_at = (time.time(), ax, az)
    time.sleep(2.5)
    watch.stop()
    for w in (wa, wb):
        w.stop.set()
    ta.stop()
    tb.stop()
    sha.log(f"walked {moved:.0f} units away, then teleported back; fired={watch.fired}")
    print(f"\n== {label}: fired={watch.fired and watch.fired['kind']} "
          f"events={[e['kind'] for e in watch.events]}")
    return watch


def run_nocontrol(label="nocontrol", a_ignores=False, b_ignores=True):
    """The controllable precondition on both instances at once, as main() runs it, against players
    that ignore the pad. Returns (result, sides, wall seconds)."""
    ax, az = M.MP51_SEAL_SPAWN
    bx, bz = M.MP51_TERROR_SPAWN
    wa, wb, ta, tb = _worlds(label, ax, az, 20.0, bx, bz, 160.0, a_ignores=a_ignores, b_ignores=b_ignores)
    clients = {"A": FakeClient(FakeShell(wa, f"A_{label}_")), "B": FakeClient(FakeShell(wb, f"B_{label}_"))}
    clients["A"].tail, clients["B"].tail = ta, tb
    t0 = time.time()
    result, sides = M.run_precondition(clients)
    wall = time.time() - t0
    for w in (wa, wb):
        w.stop.set()
    ta.stop()
    tb.stop()
    print(f"\n== {label}: RESULT {result} exit={M.control_exit_code(result)} "
          + " ".join(f"{t}={sd.status}/{[v.status for v in sd.holds]}" for t, sd in sorted(sides.items()))
          + f" wall={wall:.0f}s")
    return result, sides, wall


def run_movepath(label="movepath"):
    """MovePathWatch on both instances: A's MoveScale stops being logged while its rows keep coming
    (launch 1c's shape); B's keeps advancing. A must read `stalled`, B `ok`."""
    ax, az = M.MP51_SEAL_SPAWN
    bx, bz = M.MP51_TERROR_SPAWN
    wa, wb, ta, tb = _worlds(label, ax, az, 20.0, bx, bz, 160.0)
    shl = FakeShell(wa, "W_")
    watch = M.MovePathWatch({"A": ta, "B": tb}, shl.log, env=SIM_ENV)
    watch.start()
    time.sleep(3.0)
    t_stop = time.time()
    with wa.lock:
        wa.movescale_stopped = True
    deadline = t_stop + M.vc.MOVE_STALL_S + 6.0
    while watch.stalled is None and time.time() < deadline:
        time.sleep(0.25)
    verdicts = watch.check()
    watch.stop()
    for w in (wa, wb):
        w.stop.set()
    ta.stop()
    tb.stop()
    after = None if watch.stalled is None else watch.stalled[2] - t_stop
    print(f"\n== {label}: stalled={watch.stalled and watch.stalled[0]} after {after if after is None else round(after, 1)}s "
          f"A={verdicts['A'].status} B={verdicts['B'].status}")
    return watch, verdicts, after



# ---------------------------------------------------------------------------------------------
# Sprint 5 Task 5 Step 2: the endgame
# ---------------------------------------------------------------------------------------------
# Geometry (TwoFloorTerrain): B, the victim, spawns on the ledge and stands there (strafe-oscillating in this opt-in
# mode); A, the shooter, spawns on the lower floor and walks this world's own recorded route (SIM_ROUTES, below) up
# the ramp, then closes. The lines that follow describe the first version, which mined the ramp from a B pre-roll:
# B, the victim, walks up the ramp in a scripted pre-roll -- so the run's own rows
# hold a floor transition -- and parks on the ledge at y 142, ~90 units in from its edges. A, the shooter,
# starts on the lower floor to the south-east; the straight line from A to B passes UNDER the ledge, so a
# level-blind approach ends stacked at dy 42 (launch 3c's picture) and only the floor route reaches contact.
# The world's yaw response is the harness's table x ENDGAME_YAW_GAIN with a larger dead zone and a shorter
# lead than the harness assumes; the sticks have a dead zone of their own.
ENDGAME_YAW = (0.65, 56, 0.30)                 # world gain vs the table, dead zone |rx-0x80|, lead s
ENDGAME_MOVE_DZ = 40                           # |lx-0x80| below which the stick does not translate
ENDGAME_FIGHT_S = 30.0                         # >= 8 s of aim-and-fire standing needs ~25 s of fight
ENDGAME_MAX_IDLE_MS = 5500                     # the assertion: neither side's idle ever exceeds this
ENDGAME_MIN_STANDING_S = 8.0                   # the scenario is only a test if the shooter stood this long
ENDGAME_MIN_CONTACT_ROWS = 20


def _truth_at(hist, t):
    best = None
    for r in hist:
        if r[0] <= t:
            best = r
        else:
            break
    return best


def truth_contact_run(wa, wb, gate3d=vc.CONTACT_3D_MAX_UNITS, gate_dy=vc.CONTACT_DY_MAX_UNITS, scale_min=0.99):
    """Longest run of consecutive A ticks with the TRUE pair inside the gate AND both true scales >= scale_min."""
    run = best = 0
    hb = list(wb.hist)
    tb = [r[0] for r in hb]
    import bisect
    for r in list(wa.hist):
        k = bisect.bisect_left(tb, r[0])
        cand = [j for j in (k - 1, k) if 0 <= j < len(hb) and abs(tb[j] - r[0]) <= 0.5]
        ok = False
        if cand:
            b = hb[min(cand, key=lambda j: abs(tb[j] - r[0]))]
            ok = (math.dist(r[1:4], b[1:4]) <= gate3d and abs(r[2] - b[2]) <= gate_dy
                  and r[6] >= scale_min and b[6] >= scale_min)
        run = run + 1 if ok else 0
        best = max(best, run)
    return best


def truth_band_seconds(wa, wb, band3d=45.0, band_dy=10.0, scale_min=0.99):
    """Amendment A's contact on TRUTH: the longest stretch (seconds, over A's 4 Hz truth rows paired with B's nearest
    within 0.5 s) with the pair on one floor (|dy| <= band_dy), inside 3-D band3d, and both true scales >= scale_min."""
    import bisect
    hb = list(wb.hist)
    tb = [r[0] for r in hb]
    best, start, prev_t = 0.0, None, None
    for r in list(wa.hist):
        k = bisect.bisect_left(tb, r[0])
        cand = [j for j in (k - 1, k) if 0 <= j < len(hb) and abs(tb[j] - r[0]) <= 0.5]
        ok = False
        if cand:
            b = hb[min(cand, key=lambda j: abs(tb[j] - r[0]))]
            ok = (math.dist(r[1:4], b[1:4]) <= band3d and abs(r[2] - b[2]) <= band_dy
                  and r[6] >= scale_min and b[6] >= scale_min)
        if ok:
            start = r[0] if start is None else start
            best = max(best, r[0] - start)
        else:
            start = None
    return best


def run_endgame(label="endgame", rotation_feeds=False, firing_feeds=False, micro_strafe=True, rule=True,
                fight_s=ENDGAME_FIGHT_S):
    """The Task 5 engagement against the two-sided starvation model. Returns a dict of what was measured."""
    terrain = TwoFloorTerrain()
    net = Net(rotation_feeds=rotation_feeds, firing_feeds=firing_feeds)
    d = tempfile.gettempdir()
    tag = f"{label}_{os.getpid()}"
    kw = dict(terrain=terrain, net=net, yaw=ENDGAME_YAW, move_dz=ENDGAME_MOVE_DZ, tick_clock=True,
              back_u_s=M.WALK_BACK_UNITS_PER_S)
    ax_, az_, af_, afl = ROUTE_A_START
    bx_, bz_, bf_, bfl = ROUTE_B_START
    wa = World(os.path.join(d, f"sim_A_{tag}.log"), ax_, az_, af_, M.WALK_UNITS_PER_S_LONG,
               M.LOOK_DEG_PER_S, 27.0, actor_addr=0x01794000, tag="A", floor=afl, **kw)
    wb = World(os.path.join(d, f"sim_B_{tag}.log"), bx_, bz_, bf_, M.WALK_UNITS_PER_S_LONG,
               M.LOOK_DEG_PER_S, 27.0, actor_addr=0x017a4000, tag="B", floor=bfl, **kw)
    ta, tb = M.RunLogTail(wa.path), M.RunLogTail(wb.path)
    ta.start()
    tb.start()
    sha, shb = FakeShell(wa, "A_"), FakeShell(wb, "B_")
    time.sleep(1.5)
    t_start = time.time()
    net.restart(t_start)
    lines = []

    def log(m):
        lines.append(m)
        print(f"W_{m}", flush=True)
    sideA, sideB = M.Side("A", sha, ta), M.Side("B", shb, tb)
    duel = M.Duel()
    watch = M.StarvationWatch({"A": ta, "B": tb}, log)
    watch.start()
    out = M.endgame_cooperative({"A": sideA, "B": sideB}, duel, watch, log, route=SIM_ROUTES["A"], fight_s=fight_s,
                                micro_strafe=micro_strafe, rule=rule)
    time.sleep(1.5)                            # the rows of the final strafe arrive; open alarms can clear
    watch.check()
    watch.stop()
    contact = M.ladder_contact(ta, tb)
    truth_run = truth_contact_run(wa, wb)
    aim = sideA.aims[-1] if sideA.aims else None
    aim_truth = None
    if aim and aim["reads"]:
        # the TRUE error of the final aim: the shooter's true facing and position at its last read, against the
        # victim's true oscillation centre over the window the harness averaged (ending when the aim started)
        t_e = aim["reads"][-1]["t"]
        me = _truth_at(wa.hist, t_e)
        vict = [r for r in wb.hist if aim["t0"] - M.OSC_CENTRE_WINDOW_S <= r[0] <= aim["t0"]]
        if me and vict:
            cx = sum(r[1] for r in vict) / len(vict)
            cz = sum(r[3] for r in vict) / len(vict)
            aim_truth = M.wrap_deg(math.degrees(math.atan2(cz - me[3], cx - me[1])) - me[4])
    floors_a = [r[8] for r in wa.hist]
    standing = [s for s in out["standing"] if s is not None]
    res = {
        "label": label, "rotation_feeds": rotation_feeds, "firing_feeds": firing_feeds,
        "micro_strafe": micro_strafe, "rule": rule, "out": out,
        "max_idle": dict(net.max_idle), "watch_max_idle": watch.max_idle_ms(),
        "alarms": [dict(a) for a in watch.alarms], "alarms_n": watch.starvation_alarms(),
        "alarms_cleared": watch.alarms_cleared(), "watch_stop": watch.stop_reason,
        "contact_rows": contact.contact_rows, "contact_status": contact.status, "rows_read": contact.rows_read,
        "closest": duel.best_dist(), "closest_dy": duel.best_dy(), "truth_contact_rows": truth_run,
        "aim_err_after": aim and aim["err_after"], "aim_truth": aim_truth,
        "standing_total": sum(standing), "standing_max": max(standing, default=0.0),
        "a_reached_upper": "upper" in floors_a, "route_ok": bool(out["route"] and out["route"]["ok"]),
        "aim_teleports": sideA.aim_teleports, "bursts": out["bursts"], "micro_strafes": out["micro_strafes"],
        "rule_moves": len(out["rule_moves"]), "stop_reason": out["stop_reason"],
    }
    print(f"\n== {label}: rotation_feeds={rotation_feeds} firing_feeds={firing_feeds} micro_strafe={micro_strafe} "
          f"rule={rule} stop={res['stop_reason']!r} watch_stop={res['watch_stop']!r}\n"
          f"   max idle ms (truth) A={res['max_idle'].get('A')} B={res['max_idle'].get('B')} "
          f"(NetIdle rows A={res['watch_max_idle'].get('A')} B={res['watch_max_idle'].get('B')}); "
          f"starvation alarms={res['alarms_n']} cleared<=3s={res['alarms_cleared']} "
          f"causes={[a['cause'] for a in res['alarms']]}\n"
          f"   contact rows (verdict_core)={res['contact_rows']} ({res['contact_status']}, rows read "
          f"{res['rows_read']}), truth rows in gate with both scales>=0.99={truth_run}; closest paired "
          f"{res['closest']} dy {res['closest_dy']}\n"
          f"   final aim err={res['aim_err_after']} truth={aim_truth}; shooter standing total="
          f"{res['standing_total']:.1f}s max window={res['standing_max']:.1f}s; bursts={res['bursts']} "
          f"micro_strafes={res['micro_strafes']} rule_moves={res['rule_moves']} teleports={res['aim_teleports']}; "
          f"A route={out['route'] and out['route']['reason']} reached upper={res['a_reached_upper']}")
    for w in (wa, wb):
        w.stop.set()
    ta.stop()
    tb.stop()
    return res


def _captured(sh):
    return getattr(sh, "lines", [])


def assert_endgame_ok(r):
    assert r["stop_reason"] is None and r["watch_stop"] is None, (r["stop_reason"], r["watch_stop"])
    for side in ("A", "B"):
        assert r["max_idle"].get(side, 0) <= ENDGAME_MAX_IDLE_MS, ("idle", side, r["max_idle"])
    for a in r["alarms"]:
        if a["cause"] == "starvation" and a["t"] <= r["out"]["t_end"] - M.ALARM_CLEAR_S:   # see assert_route_ok
            ref = a["t_move"] if a["t_move"] is not None else a["t"]
            assert a["t_clear"] is not None and a["t_clear"] - ref <= M.ALARM_CLEAR_S, ("alarm not cleared", a)
    assert r["contact_rows"] >= ENDGAME_MIN_CONTACT_ROWS, ("contact rows", r["contact_rows"])
    assert r["truth_contact_rows"] >= ENDGAME_MIN_CONTACT_ROWS, ("truth contact rows", r["truth_contact_rows"])
    assert r["aim_err_after"] is not None and abs(r["aim_err_after"]) <= M.AIM_TOL_DEG, r["aim_err_after"]
    assert r["aim_truth"] is not None and abs(r["aim_truth"]) <= M.AIM_TOL_DEG, r["aim_truth"]
    assert r["a_reached_upper"] and r["route_ok"], (r["a_reached_upper"], r["route_ok"])
    assert r["standing_total"] >= ENDGAME_MIN_STANDING_S, r["standing_total"]



# ---------------------------------------------------------------------------------------------
# The DEFAULT engagement (--endgame route): the stander stands at its spawn, the mover follows a route to its floor,
# closes, aims with pulses and fires. Same two-floor world; the route is this world's own table.
# ---------------------------------------------------------------------------------------------
SIM_ROUTES = {
    "A": [(950.0, 350.0), (875.0, 385.0), (800.0, 420.0), (710.0, 440.0), (710.0, 520.0), (710.0, 580.0),
          (710.0, 620.0)],
    "B": [(700.0, 690.0), (710.0, 620.0), (710.0, 580.0), (710.0, 520.0), (710.0, 440.0), (800.0, 420.0),
          (875.0, 385.0)],
}
ROUTE_A_START = (950.0, 350.0, 135.0, "lower")
ROUTE_B_START = (700.0, 690.0, -90.0, "upper")
ROUTE_FIGHT_S = 25.0
ROUTE_MIN_BAND_S = 5.0            # Amendment A spec §5.1: contact is >= 5.0 s of qualifying time (band, both scales)
# Under the PESSIMISTIC model (a still side starves its partner) with Amendment A's reaction -- answered only once a
# side is starved -- a stander's idle can pass 5500 ms for a moment: the alarm is read at >= 4000 ms off a 0.5 s NetIdle
# row, and the mover finishes its current pulse (<= 0.6 s) first. Observed 4550 / 5301 / 5700 ms over three runs. The
# bar for that stress case is NO DEADLOCK: the scale never reaches 0.0 (idle < 6500 ms) and every answerable alarm
# clears. Launch 3c's evidence is that standing still does not starve at all (the keepalive runs).
ROUTE_STARVED_MAX_IDLE_MS = 6500


def run_route_engagement(label, mover="A", keepalive=True, teleport_after_s=None, fight_s=ROUTE_FIGHT_S):
    terrain = TwoFloorTerrain()
    net = Net(keepalive=keepalive)
    d = tempfile.gettempdir()
    tag = f"{label}_{os.getpid()}"
    kw = dict(terrain=terrain, net=net, yaw=ENDGAME_YAW, move_dz=ENDGAME_MOVE_DZ, tick_clock=True,
              back_u_s=M.WALK_BACK_UNITS_PER_S)
    ax_, az_, af_, afl = ROUTE_A_START
    bx_, bz_, bf_, bfl = ROUTE_B_START
    wa = World(os.path.join(d, f"sim_A_{tag}.log"), ax_, az_, af_, M.WALK_UNITS_PER_S_LONG, M.LOOK_DEG_PER_S, 27.0,
               actor_addr=0x01794000, tag="A", floor=afl, **kw)
    wb = World(os.path.join(d, f"sim_B_{tag}.log"), bx_, bz_, bf_, M.WALK_UNITS_PER_S_LONG, M.LOOK_DEG_PER_S, 27.0,
               actor_addr=0x017a4000, tag="B", floor=bfl, **kw)
    ta, tb = M.RunLogTail(wa.path), M.RunLogTail(wb.path)
    ta.start()
    tb.start()
    time.sleep(1.5)
    t_start = time.time()
    net.restart(t_start)
    mw = wa if mover == "A" else wb
    if teleport_after_s is not None:
        mw.teleport_by = (t_start + teleport_after_s, 120.0, 0.0)
    lines = []

    def log(m):
        lines.append(m)
        print(f"W_{m}", flush=True)
    sides = {"A": M.Side("A", FakeShell(wa, "A_"), ta), "B": M.Side("B", FakeShell(wb, "B_"), tb)}
    duel = M.Duel()
    watch = M.StarvationWatch({"A": ta, "B": tb}, log)
    watch.start()
    out = M.endgame_route(sides, duel, watch, log, "sim-twofloor", mover=mover, route=SIM_ROUTES[mover],
                          fight_s=fight_s)
    time.sleep(1.5)
    watch.check()
    watch.stop()
    contact = M.ladder_contact(ta, tb)
    shooter = sides[mover]
    aim = next((a for a in reversed(shooter.aims) if a["reads"] and a["err_after"] is not None
                and abs(a["err_after"]) <= M.AIM_TOL_DEG), None)
    aim_truth = None
    if aim:
        # the TRUE error of the last in-tolerance aim against the target it was GIVEN (the stander's newest row when
        # the aim began): the stander may move between aims (reactions), which is target staleness, not aim error
        t_e = aim["reads"][-1]["t"]
        me = _truth_at(mw.hist, t_e)
        tx, tz = aim["target"]
        if me:
            aim_truth = M.wrap_deg(math.degrees(math.atan2(tz - me[3], tx - me[1])) - me[4])
    band_s = truth_band_seconds(wa, wb)
    res = {"label": label, "out": out, "contact_rows": contact.contact_rows, "rows_read": contact.rows_read,
           "band_s": band_s,
           "max_idle": dict(net.max_idle), "alarms": [dict(a) for a in watch.alarms],
           "alarms_n": watch.starvation_alarms(), "watch_stop": watch.stop_reason, "aim_truth": aim_truth,
           "aim_err": aim and aim["err_after"], "closest": duel.best_dist(), "closest_dy": duel.best_dy(),
           "mover_floor_end": mw.floor}
    print(f"\n== {label}: mover={mover} keepalive={keepalive} stop={out['stop_reason']!r} watch_stop={watch.stop_reason!r} "
          f"route={out['route'] and out['route']['reason']}/{out['route'] and out['route']['legs']} legs "
          f"close={out['close'] and out['close']['reason']} bursts={out['bursts']} reactions={len(out['rule_moves'])} "
          f"teleport={out['teleport']}\n"
          f"   in the engagement band (truth, |dy|<=10, 3-D<=45, both scales>=0.99) {band_s:.1f}s; contact rows "
          f"(verdict_core's 22-unit gate)={contact.contact_rows} (rows read {contact.rows_read}); closest paired "
          f"{res['closest']} dy {res['closest_dy']}; max idle ms A={net.max_idle.get('A')} B={net.max_idle.get('B')}; "
          f"alarms={res['alarms_n']} causes={[a['cause'] for a in res['alarms']]}; last in-tolerance aim "
          f"err={res['aim_err']} truth={aim_truth}; mover ends on {mw.floor}")
    for w in (wa, wb):
        w.stop.set()
    ta.stop()
    tb.stop()
    return res


def assert_route_ok(r, want_reactions=False, max_idle_ms=ENDGAME_MAX_IDLE_MS):
    o = r["out"]
    assert o["stop_reason"] is None and r["watch_stop"] is None, (o["stop_reason"], r["watch_stop"])
    assert o["route"]["ok"] and o["close"]["ok"], (o["route"], o["close"])
    assert o["teleport"] is None, o["teleport"]
    assert r["band_s"] >= ROUTE_MIN_BAND_S, ("time in the engagement band", r["band_s"])
    assert o["bursts"] >= 1, o["bursts"]
    assert r["aim_truth"] is not None and abs(r["aim_truth"]) <= M.AIM_TOL_DEG, (r["aim_err"], r["aim_truth"])
    for side in ("A", "B"):
        assert r["max_idle"].get(side, 0) < max_idle_ms, ("idle", side, r["max_idle"])
    for a in r["alarms"]:
        # an alarm opened within ALARM_CLEAR_S of the engagement's end could not be answered before the movers
        # stopped (all2 run of engage-route-starved: one opened as the 25 s fight ended); every earlier one must clear
        if a["cause"] == "starvation" and a["t"] <= o["t_end"] - M.ALARM_CLEAR_S:
            ref = a["t_move"] if a["t_move"] is not None else a["t"]
            assert a["t_clear"] is not None and a["t_clear"] - ref <= M.ALARM_CLEAR_S, ("alarm not cleared", a)
    if want_reactions:
        assert len(o["rule_moves"]) >= 1, "the pessimistic model raised no reaction -- it exercised nothing"


SCENARIOS = ("open", "maze", "caps", "converge", "route", "stack", "watch", "nocontrol", "movepath", "endgame",
             "endgame-negative", "endgame-rule", "engage-route", "engage-route-starved",
             "engage-route-swap", "engage-route-teleport")


def main():
    """One scenario by name, or `all`: every scenario in its own try, failures collected and listed at the end (a
    parked flake -- R26's stack/route step cap -- no longer hides every scenario after it)."""
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which != "all":
        print("SIM OK " + " ".join(_run(which)))
        return
    ran, failed = [], []
    for name in SCENARIOS:
        try:
            ran += _run(name)
        except AssertionError as e:
            failed.append(name)
            print(f"SIM FAIL {name}: {str(e)[:400]}", flush=True)
    print("SIM OK " + " ".join(ran))
    if failed:
        print("SIM FAILED " + " ".join(failed))
        sys.exit(1)


def _run(which):
    ran = []
    if which in ("open", "all"):
        r, d = run("open", 540.0, 1480.0, 20.0, 900.0, 700.0, -160.0)
        assert r["ok"] and d <= 140.0, (r["reason"], d)
        ran.append("open")
    if which in ("maze", "all"):
        # A is walled off in B's direction: it must go east past x=750 before it can head south.
        r, d = run("maze", 540.0, 1480.0, 20.0, 900.0, 700.0, -160.0,
                   wall=lambda x, z: z < 1400.0 and x < 750.0, max_seconds=400.0)
        assert r["ok"] and d <= 140.0, (r["reason"], d)
        ran.append("maze")
    if which in ("caps", "all"):
        r, d = run("caps", 540.0, 1480.0, 20.0, 900.0, 700.0, -160.0,
                   wall=lambda x, z: x > 700.0, max_steps=6, max_seconds=120.0)
        assert not r["ok"] and r["reason"] in ("step-cap", "time-cap"), r["reason"]
        ran.append("caps")
    if which in ("converge", "all"):
        # arrive == engage, as the match runs it: two thresholds would let both sides stop short
        # of contact and then nobody shoots. The assertion is tight now BECAUSE the loop reads the
        # actor's own position instead of reconstructing it from camera + facing; on the old code
        # this scenario reported 40.3 against a ground truth of 64.3.
        out, d, _, _ = run_converge("converge", arrive=22.0, engage=22.0, max_seconds=290.0)
        last = [t["d3"] for r in out.values() for t in r["track"][-1:] if t.get("d3") is not None]
        rep_last = min(last) if last else float("inf")
        print(f"   converge: last reported 3-D {rep_last:.1f} vs simulated truth {d:.1f} "
              f"(outcomes A={out['A']['reason']} B={out['B']['reason']})")
        # OUTCOME: the 1526-unit map is closed to within two engage radii. Not "contact", on
        # purpose: with an HONEST 22-unit gate the endgame sometimes spends its step budget
        # circling at 25-30 units -- one run of this very scenario did -- and that is a real
        # property of the loop for Sprint 5 to know about, not a flake to paper over.
        assert d <= 45.0, d
        # MEASUREMENT: what the loop last reported tracks the truth. The two are not sampled at the
        # same instant (a burst can follow the last reading), so the bound is one burst, not zero;
        # on the old camera+facing reconstruction this gap was 24 to 47 units in a FLAT world.
        assert abs(rep_last - d) <= 25.0, (rep_last, d)
        assert out["A"]["reason"] in ("contact", "contact-other", "arrived"), out["A"]["reason"]
        ran.append("converge")
    if which in ("route", "all"):
        # The shape of the real map: A's spawn bowl is walled in B's direction below z=1300 until
        # x>690, and B's half has a wall of its own. The mined corridor has to carry A out.
        out, d, _, _ = run_converge(
            "route", route=M.MP51_SEAL_ROUTE, arrive=22.0, engage=22.0, max_seconds=290.0,
            wall=lambda x, z: z < 1300.0 and x < 690.0,
            bwall=lambda x, z: z > 400.0 and x > 1200.0)
        # Tight again. This assertion was loosened to "contact was reached" because the side that
        # did not call contact could still be mid-burst when the other one did (one run ended 50.8
        # apart having correctly reported 13.7). That race is now REMOVED rather than tolerated:
        # every approach hold is released the moment either side calls contact.
        assert any(r["reason"] in ("contact", "contact-other") for r in out.values()), out
        assert d <= 45.0, d
        ran.append("route")
    if which in ("stack", "all"):
        # The kill2 failure, as a test. A's ground falls away as it walks south -- the mined
        # corridor is a descent, y 184.8 -> -4.5 -- while B stays at one height, so a ground-plane
        # loop walks A UNDER B and calls it contact. The loop must refuse and climb back up its own
        # breadcrumb trail to B's height instead.
        out, d, _, _ = run_converge(
            "stack", arrive=22.0, engage=22.0, max_seconds=290.0,
            aheight=lambda x, z: -131.0 + max(0.0, min(140.0, (z - 700.0) * 0.18)),
            bheight=lambda x, z: -71.0)
        trk = out["A"]["track"]
        d3s = [t["d3"] for t in trk if t.get("d3") is not None]
        stacked = [t for t in trk if t.get("target_name") == "level"]
        print(f"   stack: A min reported 3-D {min(d3s):.1f}, simulated truth {d:.1f}, "
              f"{len(stacked)} of {len(trk)} steps steered to a same-height breadcrumb, "
              f"final |dy| {abs(trk[-1]['dy']):.1f}")
        assert any(r["reason"] in ("contact", "contact-other") for r in out.values()), out
        assert d <= 45.0, d                              # same race, same fix, same bound
        ran.append("stack")
    if which in ("watch", "all"):
        w = run_watch()
        # The sim's worlds peek the round valves, so a teleport while they are live is only an
        # observation (Sprint 5 Task 3: respawn is the fallback round-end signal, never a PASS).
        assert w.fired is None, w.events
        assert any(e["kind"] == "respawn" and not e["firing"] for e in w.events), w.events
        ran.append("watch")
    if which in ("watch", "watch-fallback", "all"):
        w = run_watch("watch_fallback", valves=False)
        assert w.fired and w.fired["kind"] == "respawn" and w.fired["detail"]["fallback"], w.events
        ran.append("watch-fallback")
    if which in ("nocontrol", "all"):
        # Both at once, as main() runs them: A controllable, B ignores the pad -> NO-CONTROL side=B
        # within 4 holds (~4 x (1.3 + 11.5 + 2 + 2.5) s); then both ignore it -> NO-CONTROL, exit 3.
        result, sides, wall = run_nocontrol("nocontrol_B", a_ignores=False, b_ignores=True)
        assert result == "NO-CONTROL side=B", result
        assert sides["A"].holds[0].status == "PASS", sides["A"].holds
        assert [v.status for v in sides["B"].holds] == ["FAIL"] * 4, sides["B"].holds
        assert all(v.drift_units is not None for v in sides["B"].holds), [v.reason for v in sides["B"].holds]
        assert wall <= 4 * (M.turn_hold_seconds(M.PRECONDITION_TURN_DEG) + M.PRECONDITION_NEUTRAL_S
                            + M.PRECONDITION_HOLD_S + M.PRECONDITION_SETTLE_S) + 10.0, wall
        result, sides, _ = run_nocontrol("nocontrol_AB", a_ignores=True, b_ignores=True)
        assert result == "NO-CONTROL" and M.control_exit_code(result) == 3, result
        ran.append("nocontrol")
    if which in ("movepath", "all"):
        watch, verdicts, after = run_movepath()
        assert watch.stalled is not None and watch.stalled[0] == "A", watch.history
        assert verdicts["B"].status == "ok", verdicts["B"]
        assert M.vc.MOVE_STALL_S - 1.0 <= after <= M.vc.MOVE_STALL_S + 3.0, after
        ran.append("movepath")
    if which in ("endgame", "all"):
        r = run_endgame("endgame")
        assert_endgame_ok(r)
        ran.append("endgame")
    if which in ("endgame-negative", "all"):
        # The identical scenario with the other-side-moves rule AND the shooter's micro-strafe removed must starve
        # the victim past 5500 ms -- whether or not rotation feeds the counter (Step 1 has not measured it).
        for rot in (False, True):
            r = run_endgame(f"endgame_negative_rot{int(rot)}", rotation_feeds=rot, micro_strafe=False, rule=False)
            assert r["out"]["t_fight"] is not None, "the negative run never reached the fight -- it proves nothing"
            assert r["max_idle"].get("B", 0) > ENDGAME_MAX_IDLE_MS, ("negative did not starve B", rot, r["max_idle"])
        ran.append("endgame-negative")
    if which in ("endgame-rule", "all"):
        # The rule alone (micro-strafe removed): every victim alarm must be answered by the shooter moving and clear.
        r = run_endgame("endgame_rule_only", micro_strafe=False, rule=True)
        assert r["out"]["t_fight"] is not None
        assert r["alarms_n"] >= 1 and r["rule_moves"] >= 1, "the rule-only run moved nobody on a rule -- it exercised nothing"
        for a in r["alarms"]:
            if a["cause"] == "starvation":
                # an approach-phase alarm is cleared by the approach's own next walk (no rule move, t_move None)
                ref = a["t_move"] if a["t_move"] is not None else a["t"]
                assert a["t_clear"] is not None and a["t_clear"] - ref <= M.ALARM_CLEAR_S, a
        for side in ("A", "B"):
            assert r["max_idle"].get(side, 0) <= ENDGAME_MAX_IDLE_MS, ("rule-only idle", side, r["max_idle"])
        ran.append("endgame-rule")
    if which in ("engage-route", "all"):
        # the DEFAULT engagement, launch 3c's world: a still pair does not starve (keepalive)
        assert_route_ok(run_route_engagement("route_keepalive", keepalive=True))
        ran.append("engage-route")
    if which in ("engage-route-starved", "all"):
        # ... and under the pessimistic translation-only model the StarvationWatch reaction has to keep both fed
        assert_route_ok(run_route_engagement("route_starved", keepalive=False), want_reactions=True,
                        max_idle_ms=ROUTE_STARVED_MAX_IDLE_MS)
        ran.append("engage-route-starved")
    if which in ("engage-route-swap", "all"):
        # --mover B: B walks its route down to A's floor and shoots; A stands
        assert_route_ok(run_route_engagement("route_swap", mover="B", keepalive=True))
        ran.append("engage-route-swap")
    if which in ("engage-route-teleport", "all"):
        r = run_route_engagement("route_teleport", keepalive=True, teleport_after_s=8.0)
        assert r["out"]["teleport"] is not None and r["out"]["stop_reason"].startswith("teleport"), r["out"]
        assert r["out"]["teleport"]["during"] in ("walk", "aim"), r["out"]["teleport"]
        assert r["out"]["bursts"] == 0, "the aborted attempt went on to fire"
        ran.append("engage-route-teleport")
    return ran


if __name__ == "__main__":
    main()
