"""Closed-loop dry run of the approach loop against a SIMULATED world -- no match, no game.

The world writes `[peek] @416054` rows and `MoveScale f12=1.0` rows into temp logs at 4 Hz, exactly
as the exe does, and the REAL `RunLogTail` reads them; the fake `Shell.pad` applies the stick state
to the simulated player. So the thing under test is the shipped loop, not a copy of it.

Every scenario deliberately MISMATCHES the world's turn response against the harness constants, so
each correction overshoots or undershoots and the loop has to recover by re-measuring -- which is
what the real game does (research/18 §3.13: RMS 18 deg on an open-loop turn, and one wtb2 turn that
asked for -72 deg and delivered -16).

    python -m tools_py.parity.sim_walk_to_b [open|maze|caps|converge|route|stack|watch|nocontrol|movepath|all]

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
                 actor_addr=0x01794000, ignores_pad=False, valves=True):
        self.path, self.x, self.z, self.facing = path, x, z, facing
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
                s = {} if self.ignores_pad else dict(self.state)
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
                if n % 2 == 0 and not self.movescale_stopped:
                    # #n advances as the exe's does at EVERY=10 (~19 calls/s -> ~1 line per 0.5 s)
                    self.move_n += 10
                    f.write(f"[call] {400.0 + n * dt:.1f}s MoveScale #{self.move_n} a0=0x1 "
                            f"ra=0x595028 f12=1.0 f13=0.0 f14=1.0\n")
                f.write(peek_line(cx, y + 19.7, cz, actor=(self.x, y, self.z),
                                  actor_addr=self.actor_addr)
                        + (" " + state_items(self.actor_addr) if self.valves else "") + "\n")
            time.sleep(dt)


class FakeShell:
    def __init__(self, world, tag):
        self.world, self.tag = world, tag

    def log(self, m):
        print(f"{self.tag}{m}", flush=True)

    def shot(self, label):
        pass

    def pad(self, seconds, buttons=(), sticks=(), abort=None):
        with self.world.lock:
            self.world.state = {k.upper(): True for k in sticks}
        if abort is None:
            time.sleep(seconds)
        else:
            abort.wait(seconds)
        with self.world.lock:
            self.world.state = {}


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
    print("SIM OK " + " ".join(ran))


if __name__ == "__main__":
    main()
