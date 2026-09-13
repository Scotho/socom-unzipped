"""Closed-loop dry run of the approach loop against a SIMULATED world -- no match, no game.

The world writes `[peek] @416054` rows and `MoveScale f12=1.0` rows into temp logs at 4 Hz, exactly
as the exe does, and the REAL `RunLogTail` reads them; the fake `Shell.pad` applies the stick state
to the simulated player. So the thing under test is the shipped loop, not a copy of it.

Every scenario deliberately MISMATCHES the world's turn response against the harness constants, so
each correction overshoots or undershoots and the loop has to recover by re-measuring -- which is
what the real game does (research/18 §3.13: RMS 18 deg on an open-loop turn, and one wtb2 turn that
asked for -72 deg and delivered -16).

    python -m tools_py.parity.sim_walk_to_b [open|maze|caps|converge|route|watch|all]

Task 7 wrote this in a scratch directory and lost it. It lives next to the harness now.
"""
import math
import os
import struct
import sys
import tempfile
import threading
import time

from . import online_match_ours as M


def peek_line(x, y, z):
    def w(v):
        return f"{struct.unpack('<I', struct.pack('<f', v))[0]:08x}({v:g})"
    return f"[peek] @416054: {w(x)} {w(y)} {w(z)}"


class World:
    """One simulated player. Truth is (x, z, facing); the log carries the camera record only."""

    def __init__(self, path, x, z, facing, walk_u_s, look_deg_s, radius, wall=None):
        self.path, self.x, self.z, self.facing = path, x, z, facing
        self.walk, self.look, self.r, self.wall = walk_u_s, look_deg_s, radius, wall
        self.state = {}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.teleport_at = None          # (host time, x, z) -- a respawn, for the KillWatch test
        open(path, "w").close()
        threading.Thread(target=self._tick, daemon=True).start()

    def camera(self):
        h = math.radians(self.facing)
        return self.x - self.r * math.cos(h), self.z - self.r * math.sin(h)

    def _tick(self):
        dt, n = 0.25, 0
        while not self.stop.is_set():
            with self.lock:
                if self.teleport_at and time.time() >= self.teleport_at[0]:
                    self.x, self.z = self.teleport_at[1], self.teleport_at[2]
                    self.teleport_at = None
                s = dict(self.state)
                if s.get("W"):
                    h = math.radians(self.facing)
                    nx = self.x + self.walk * dt * math.cos(h)
                    nz = self.z + self.walk * dt * math.sin(h)
                    if self.wall is None or not self.wall(nx, nz):
                        self.x, self.z = nx, nz
                if s.get("S"):
                    h = math.radians(self.facing)
                    self.x -= self.walk * dt * math.cos(h)
                    self.z -= self.walk * dt * math.sin(h)
                if s.get("L"):
                    self.facing = M.wrap_deg(self.facing + self.look * dt)
                if s.get("J"):
                    self.facing = M.wrap_deg(self.facing - self.look * dt)
                if s.get("D"):
                    h = math.radians(self.facing - 90.0)
                    self.x += self.walk * dt * math.cos(h)
                    self.z += self.walk * dt * math.sin(h)
                if s.get("A"):
                    h = math.radians(self.facing + 90.0)
                    self.x += self.walk * dt * math.cos(h)
                    self.z += self.walk * dt * math.sin(h)
                cx, cz = self.camera()
            n += 1
            with open(self.path, "a") as f:
                if n % 2 == 0:
                    f.write("[call] 400.0s MoveScale #1 a0=0x1 ra=0x595028 f12=1.0 f13=0.0 f14=1.0\n")
                f.write(peek_line(cx, -131.0, cz) + "\n")
            time.sleep(dt)


class FakeShell:
    def __init__(self, world, tag):
        self.world, self.tag = world, tag

    def log(self, m):
        print(f"{self.tag}{m}", flush=True)

    def shot(self, label):
        pass

    def pad(self, seconds, buttons=(), sticks=()):
        with self.world.lock:
            self.world.state = {k.upper(): True for k in sticks}
        time.sleep(seconds)
        with self.world.lock:
            self.world.state = {}


class FakeClient:
    def __init__(self, sh):
        self.sh = sh


def _worlds(label, ax, az, af, bx, bz, bf, wall=None, bwall=None, look_mismatch=0.78):
    d = tempfile.gettempdir()
    wa = World(os.path.join(d, f"sim_A_{label}.log"), ax, az, af, M.WALK_UNITS_PER_S_LONG,
               M.LOOK_DEG_PER_S * M.LOOK_RIGHT_SIGN * look_mismatch, 27.0, wall)
    wb = World(os.path.join(d, f"sim_B_{label}.log"), bx, bz, bf, M.WALK_UNITS_PER_S_LONG,
               M.LOOK_DEG_PER_S * M.LOOK_RIGHT_SIGN / look_mismatch, 27.0, bwall)
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


def run_converge(label, route=None, wall=None, bwall=None, arrive=120.0, engage=45.0,
                 max_steps=40, max_seconds=290.0):
    """Both movers (what a match runs): A and B walk toward each other from the mp51 spawns."""
    ax, az = M.MP51_SEAL_SPAWN
    bx, bz = M.MP51_TERROR_SPAWN
    wa, wb, ta, tb = _worlds(label, ax, az, 20.0, bx, bz, 160.0, wall, bwall)
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
    true_d = math.hypot(wb.x - wa.x, wb.z - wa.z)
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


def run_watch(label="watch"):
    """The KillWatch's respawn signal: a player that teleports back to its spawn must fire."""
    ax, az = M.MP51_SEAL_SPAWN
    bx, bz = M.MP51_TERROR_SPAWN
    wa, wb, ta, tb = _worlds(label, ax, az, -60.0, bx, bz, 120.0)
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


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
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
        # of contact and then nobody shoots.
        out, d, _, _ = run_converge("converge", arrive=45.0, engage=45.0, max_seconds=290.0)
        assert d <= 70.0, d
        assert out["A"]["reason"] in ("contact", "contact-other", "arrived"), out["A"]["reason"]
        ran.append("converge")
    if which in ("route", "all"):
        # The shape of the real map: A's spawn bowl is walled in B's direction below z=1300 until
        # x>690, and B's half has a wall of its own. The mined corridor has to carry A out.
        out, d, _, _ = run_converge(
            "route", route=M.MP51_SEAL_ROUTE, arrive=45.0, engage=45.0, max_seconds=290.0,
            wall=lambda x, z: z < 1300.0 and x < 690.0,
            bwall=lambda x, z: z > 400.0 and x > 1200.0)
        assert d <= 70.0, d
        ran.append("route")
    if which in ("watch", "all"):
        w = run_watch()
        assert w.fired and w.fired["kind"] == "respawn", w.events
        ran.append("watch")
    print("SIM OK " + " ".join(ran))


if __name__ == "__main__":
    main()
