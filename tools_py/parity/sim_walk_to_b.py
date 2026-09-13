"""Closed-loop dry run of the approach loop against a SIMULATED world -- no match, no game.

The world writes `[peek] @416054` rows and `MoveScale f12=1.0` rows into temp logs at 4 Hz, exactly
as the exe does, and the REAL `RunLogTail` reads them; the fake `Shell.pad` applies the stick state
to the simulated player. So the thing under test is the shipped loop, not a copy of it.

Every scenario deliberately MISMATCHES the world's turn response against the harness constants, so
each correction overshoots or undershoots and the loop has to recover by re-measuring -- which is
what the real game does (research/18 §3.13: RMS 18 deg on an open-loop turn, and one wtb2 turn that
asked for -72 deg and delivered -16).

    python -m tools_py.parity.sim_walk_to_b [open|maze|caps|converge|route|stack|watch|all]

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

from . import online_match_ours as M


def _w(v):
    return f"{struct.unpack('<I', struct.pack('<f', v))[0]:08x}({v:g})"


def peek_line(cx, cy, cz, actor=None, actor_addr=0x01794000):
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
        line += f" @{actor_addr:x}: " + " ".join(words)
    return line


class World:
    """One simulated player. Truth is (x, z, facing); the log carries the camera record only."""

    def __init__(self, path, x, z, facing, walk_u_s, look_deg_s, radius, wall=None, height=None,
                 actor_addr=0x01794000):
        self.path, self.x, self.z, self.facing = path, x, z, facing
        self.walk, self.look, self.r, self.wall = walk_u_s, look_deg_s, radius, wall
        self.height = height or (lambda x, z: -131.0)
        self.actor_addr = actor_addr
        self.state = {}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.teleport_at = None          # (host time, x, z) -- a respawn, for the KillWatch test
        open(path, "w").close()
        threading.Thread(target=self._tick, daemon=True).start()

    def _try_move(self, heading_deg, dt=0.25):
        h = math.radians(heading_deg)
        nx = self.x + self.walk * dt * math.cos(h)
        nz = self.z + self.walk * dt * math.sin(h)
        if self.wall is None or not self.wall(nx, nz):
            self.x, self.z = nx, nz

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
                # EVERY translation is checked against the wall, not only the forward walk. The
                # original world blocked `W` and let `S`, `A` and `D` pass straight through, so
                # the loop's own unstick manoeuvre (a step back and a sidestep) could put the
                # player INSIDE solid geometry -- after which every forward move was blocked for
                # good. That is what made `maze` flaky: 14, 18, 23 and 29 steps on four runs, and
                # on a fifth a full 40-step budget spent pinned inside the wall at x~720, z~1300.
                if s.get("W"):
                    self._try_move(self.facing)
                if s.get("S"):
                    self._try_move(self.facing + 180.0)
                if s.get("L"):
                    self.facing = M.wrap_deg(self.facing + self.look * dt)
                if s.get("J"):
                    self.facing = M.wrap_deg(self.facing - self.look * dt)
                if s.get("D"):
                    self._try_move(self.facing - 90.0)
                if s.get("A"):
                    self._try_move(self.facing + 90.0)
                cx, cz = self.camera()
                y = self.height(self.x, self.z)
            n += 1
            with open(self.path, "a") as f:
                if n % 2 == 0:
                    f.write("[call] 400.0s MoveScale #1 a0=0x1 ra=0x595028 f12=1.0 f13=0.0 f14=1.0\n")
                f.write(peek_line(cx, y + 19.7, cz, actor=(self.x, y, self.z),
                                  actor_addr=self.actor_addr) + "\n")
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


def _worlds(label, ax, az, af, bx, bz, bf, wall=None, bwall=None, look_mismatch=0.78,
            aheight=None, bheight=None):
    # The logs are PER PROCESS. They used to be `sim_A_<label>.log` in the shared temp dir, so two
    # suites running at once -- which happened, because `pkill` is a no-op in Git Bash and the old
    # suite was never killed -- interleaved two simulated worlds into one log. The loop then read
    # rows from both, `open` walked 1240 units AWAY from its target after three identical green
    # runs, and the failure looked exactly like a regression in the code under test.
    d = tempfile.gettempdir()
    label = f"{label}_{os.getpid()}"
    wa = World(os.path.join(d, f"sim_A_{label}.log"), ax, az, af, M.WALK_UNITS_PER_S_LONG,
               M.LOOK_DEG_PER_S * M.LOOK_RIGHT_SIGN * look_mismatch, 27.0, wall, aheight,
               actor_addr=0x01794000)
    wb = World(os.path.join(d, f"sim_B_{label}.log"), bx, bz, bf, M.WALK_UNITS_PER_S_LONG,
               M.LOOK_DEG_PER_S * M.LOOK_RIGHT_SIGN / look_mismatch, 27.0, bwall, bheight,
               actor_addr=0x017a4000)
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
        # Assert the OUTCOME, not the final separation. `d` is the truth when both threads have
        # STOPPED, and the side that did not call contact can still be mid-burst when the other
        # one does -- one run ended 50.8 apart having correctly reported a best of 13.7. The
        # measurement accuracy is asserted in `converge`, and `open`/`maze` corroborate it
        # (reported 85.24 vs truth 85.24, 100.82 vs 100.82).
        assert any(r["reason"] in ("contact", "contact-other") for r in out.values()), out
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
        ran.append("stack")
    if which in ("watch", "all"):
        w = run_watch()
        assert w.fired and w.fired["kind"] == "respawn", w.events
        ran.append("watch")
    print("SIM OK " + " ".join(ran))


if __name__ == "__main__":
    main()
