"""The engagement ladder's round loop and stop rules (Sprint 5 Amendment A: A1 per-round stop rules, A2 `--rounds N`).

One lobby success carries several rounds: a clock round end or a kill keeps the actor block and resets both players to
their spawns (docs/HAZARDS.md harness, launch 8c: mp_round_count steps ~5.4 s after the clock reads 00:00, the guest clock stands still
~5.5 s and the players reset at its restart). So a ladder launch plays up to N rounds; each is scored on its own
(`LADDER round=<n> ...`), round 1 carrying the controllable precondition and rung 0, rounds 2..N engaging only.

PURE orchestration: `run_ladder` takes the round player and the round-transition waiter as callables, so the stop
rules and the loop are tested without a game; `online_match_ours.main` supplies the live ones. `wait_next_round`
reads the tails only.

Stop rules per USABLE round (A1): three usable rounds at rung 1 without rung 2 -> `SWAP-MOVER` (with --auto-swap the
next rounds swap the mover once; otherwise the ladder stops); two usable rounds at rung 2 without rung 3 ->
`DAMAGE-PATH-DECISION` (the ladder stops engaging; the grenade option is a later flag). A round whose verdict is
NO-DATA (a freeze or teleport in a fire window, a spawn mismatch, a watch NO-DATA) is not usable.
"""
import math
import time
from dataclasses import dataclass, field

from . import verdict_core as vc

LADDER_ROUNDS_DEFAULT = 4
SWAP_AFTER_RUNG1_ROUNDS = 3
DECIDE_AFTER_RUNG2_ROUNDS = 2
NEXT_ROUND_TIMEOUT_S = 120.0     # from a round's end to the next round's first live rows: 8c took ~11 s (00:00 ->
                                 # step 5.4 s -> clock restart and reset 5.5 s later), but s6_ladder5 (2026-09-15, a
                                 # round ended on its CLOCK, two instances on a loaded host) restarted 05:59 only ~130
                                 # sampler rows after 00:00 and the 45 s wait gave up first -- the round was fine, the
                                 # wait was short. A round is 6 min; two minutes of waiting costs nothing it would not
                                 # cost anyway
NEXT_ROUND_POLL_S = 0.25
NEXT_ROUND_CLOCK_RUN_S = 1.0     # the guest clock must advance past its frozen value for this long AFTER the restart
NEXT_ROUND_SPAWN_UNITS = 20.0    # ... and each side's newest actor row must be this close (ground) to its spawn
NEXT_ROUND_FRESH_S = 1.0         # ... and that row no older than this
NEXT_ROUND_STALL_SEEN_S = 3.0    # a boundary stall starts within this of the step (8c: on the step's own row); a clock
                                 # that ran on through it for this long had no boundary stall to wait for
NEXT_ROUND_STALL_S = 1.0         # the boundary stall: the guest clock standing this long (vc.FREEZE_STALL_S)
ROUND_END_SLACK_S = 20.0         # after an engagement, the round end is waited for the clock string's remaining time
                                 # plus this (from the string's newest change, so a freeze extends the wait)
ROUND_END_FALLBACK_S = 420.0     # ... or this long when no clock string was read at all (a round is ~6 min)
ROUND_END_POLL_S = 0.25
SWAP_MOVER = "SWAP-MOVER"
DAMAGE_PATH_DECISION = "DAMAGE-PATH-DECISION"
LOBBY_FAIL = "LOBBY-FAIL"        # R47: online_login_ours exits 4 with `RESULT LOBBY-FAIL <class>` -- a launch that never
                                 # reached a round: no round is played, usable or counted toward the stop rules


@dataclass
class RoundScore:
    n: int
    mover: str
    rung: object = 0                 # 0..3, or vc.NO_DATA when contact was NO-DATA on a controllable pair
    verdict: str = vc.NO_DATA        # the round's RESULT word(s): PASS / FAIL ... / NO-DATA ...
    kill: bool = False
    line: str = ""                   # the LADDER round=<n> ... line
    fatal: object = None             # a reason that ends the ladder after this round (a move-path stall, ...)
    fields: dict = field(default_factory=dict)
    rung0: str = None                # round 1: "PASS" | "FAIL <reason>" | "NO-DATA <reason>" (R68: recorded, never fatal)

    @property
    def rung_n(self):
        return self.rung if isinstance(self.rung, int) else 0

    @property
    def usable(self):
        return isinstance(self.rung, int) and self.rung >= 1 and not self.verdict.startswith(vc.NO_DATA)


def stop_rule(history):
    """history: the RoundScores since the last swap -> SWAP_MOVER | DAMAGE_PATH_DECISION | None."""
    usable = [r for r in history if r.usable]
    if any(r.rung >= 3 or r.kill for r in usable):
        return None
    if sum(1 for r in usable if r.rung == 2) >= DECIDE_AFTER_RUNG2_ROUNDS:
        return DAMAGE_PATH_DECISION
    if sum(1 for r in usable if r.rung == 1) >= SWAP_AFTER_RUNG1_ROUNDS and not any(r.rung >= 2 for r in usable):
        return SWAP_MOVER
    return None


def other(tag):
    return "B" if tag == "A" else "A"


def run_ladder(n_rounds, play_round, next_round, log, mover="A", auto_swap=False):
    """Play up to `n_rounds`: play_round(n, mover) -> RoundScore; next_round(n) -> (ok, reason) before rounds 2..N.
    Logs each round's LADDER line, the stop rule when one fires, and a final `LADDER-SUMMARY`. -> (history, stop)."""
    history, since, swapped, stop = [], 0, False, None
    for n in range(1, n_rounds + 1):
        if n > 1:
            ok, reason = next_round(n)
            if not ok:
                stop = f"no round {n}: {reason}"
                log(f"LADDER round={n} NO-DATA next-round -- {reason}")
                break
        score = play_round(n, mover)
        history.append(score)
        log(score.line)
        if score.fatal:
            stop = f"round {n}: {score.fatal}"
            break
        rule = stop_rule(history[since:])
        if rule == SWAP_MOVER:
            usable = [r.n for r in history[since:] if r.usable]
            if auto_swap and not swapped and n < n_rounds:
                log(f"{SWAP_MOVER} after usable rounds {usable} at rung 1 without rung 2 (mover {mover}): --auto-swap "
                    f"-- rounds {n + 1}.. walk {other(mover)} along the route file's routes.{other(mover)}, "
                    f"{mover} stands")
                mover, since, swapped = other(mover), len(history), True
            else:
                stop = f"{SWAP_MOVER} (usable rounds {usable} at rung 1 without rung 2)"
                log(f"{SWAP_MOVER} after usable rounds {usable} at rung 1 without rung 2 -- "
                    f"{'both movers tried; ' if swapped else ''}the ladder stops engaging "
                    f"({'rerun with --mover ' + other(mover) if not swapped else 'write up the closest approach'})")
                break
        elif rule == DAMAGE_PATH_DECISION:
            usable = [r.n for r in history if r.usable and r.rung == 2]
            stop = f"{DAMAGE_PATH_DECISION} (usable rounds {usable} at rung 2 without rung 3)"
            log(f"{DAMAGE_PATH_DECISION} after usable rounds {usable} at rung 2 without rung 3 -- the ladder stops "
                f"engaging: shots missing vs a damage path that does not write +0x1044 (plan Task 5 Step 4)")
            break
    usable = [r for r in history if r.usable]
    rung0 = next((r.rung0 for r in history if r.rung0), None)
    log(f"LADDER-SUMMARY rounds={len(history)}/{n_rounds} usable={len(usable)} "
        f"best_rung={max((r.rung_n for r in history), default=0)} kills={sum(1 for r in history if r.kill)} "
        f"rungs={','.join(str(r.rung) for r in history) or '-'} movers={','.join(r.mover for r in history) or '-'} "
        f"stop={stop or 'rounds done'}" + (f" RUNG0 {rung0}" if rung0 else ""))
    return history, stop


def lobby_fail_summary(n_rounds, cls, ident=""):
    """R47: the launch's LADDER-SUMMARY when the lobby failed (exit 4, `RESULT LOBBY-FAIL <class>`): zero rounds played,
    none usable, nothing toward the A1 stop rules (they count usable ROUNDS; a lobby failure is a launch, not a round)."""
    return (f"LADDER-SUMMARY rounds=0/{n_rounds} usable=0 best_rung=0 kills=0 rungs=- movers=- "
            f"stop={LOBBY_FAIL} {cls}" + (f" {ident}" if ident else ""))


def rung0_report(ok, reason, fields, ident=""):
    """R68: rung 0 is RECORDED, never fatal. -> (token for the round-1 LADDER line and the summary, lines to log).
    PASS -> "PASS"; a failed bar -> "FAIL <reason>" and a `RUNG0 FAIL <reason>` line; a missing instrument (no GS stats
    rows at all, no MoveScale rows at all: fields['status'] NO-DATA) -> "NO-DATA <reason>" and
    `RESULT RUNG0-NO-DATA <reason>`. The rounds continue either way."""
    status = fields.get("status") or ("PASS" if ok else "FAIL")
    tail = f" {ident}" if ident else ""
    if status == "PASS":
        return "PASS", []
    if status == vc.NO_DATA:
        return f"{vc.NO_DATA} {reason}", [f"RESULT RUNG0-{vc.NO_DATA} {reason}{tail} -- the rounds continue (R68)"]
    return f"FAIL {reason}", [f"RUNG0 FAIL {reason}{tail} -- recorded; the rounds continue (R68)"]


def round_count(tail):
    """The newest identified mp_round_count and mp_game_over of a tail -> (round, game_over) (None when unread)."""
    with tail._lock:                                    # noqa: SLF001 - the harness's own tail
        rows = list(tail.round_rows[-40:])
    rc = go = None
    for _, st in rows:
        if not isinstance(st.get("mp_round_count"), vc.NoData):
            rc = st["mp_round_count"]
        if not isinstance(st.get("mp_game_over"), vc.NoData):
            go = st["mp_game_over"]
    return rc, go


def step_time(tail, start_round):
    """Host time of the first identified row after the last `start_round` row whose mp_round_count differs -> t | None."""
    with tail._lock:                                    # noqa: SLF001 - the harness's own tail
        rows = [(t, st["mp_round_count"]) for t, st in tail.round_rows
                if not isinstance(st.get("mp_round_count"), vc.NoData)]
    last = max((i for i, (_, v) in enumerate(rows) if v == start_round), default=-1)
    return next((t for t, v in rows[last + 1:] if v != start_round), None)


def clock_restart(rt, t_step):
    """The round boundary's guest-clock restart after an mp_round_count step at `t_step`. rt: [(t, 0x4365c0)].
    -> (frozen value, restart host time, running since restart s) | None while the boundary has not restarted.
    The boundary stall is the first run of equal values >= NEXT_ROUND_STALL_S starting within NEXT_ROUND_STALL_SEEN_S
    of the step (8c: 212.45 from 783.28 -- the step's own row -- to 788.88); the restart is the first row whose value
    differs from the frozen one; `running` is how long every later row kept ADVANCING past it (a second stall resets
    nothing but stops the count). A clock that ran through NEXT_ROUND_STALL_SEEN_S after the step with no such stall
    restarted at the step."""
    rows = sorted(r for r in rt if r[0] >= t_step - 0.5)
    i = 0
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1][1] == rows[i][1]:
            j += 1
        if rows[i][0] > t_step + NEXT_ROUND_STALL_SEEN_S:
            break
        if j == len(rows) - 1:
            return None                                  # a run still in progress near the step: cannot tell yet
        if rows[j][0] - rows[i][0] >= NEXT_ROUND_STALL_S:
            frozen, t_r = rows[i][1], rows[j + 1][0]
            return frozen, t_r, _advancing_run(rows[j + 1:], frozen, t_r)
        i = j + 1
    if not rows or rows[-1][0] < t_step + NEXT_ROUND_STALL_SEEN_S:
        return None                                      # too early to say the boundary had no stall
    base = next((v for t, v in reversed(rows) if t <= t_step), rows[0][1])
    return base, t_step, _advancing_run([r for r in rows if r[0] > t_step], base, t_step)


def _advancing_run(rows, frozen, t_r):
    """Seconds from `t_r` over which every row is past `frozen` and the clock advanced row on row (equal consecutive
    values under NEXT_ROUND_STALL_S are one 4 Hz sample, not a stall)."""
    last_t, last_v, since = t_r, None, t_r
    for t, v in rows:
        if v == frozen:
            return 0.0
        if last_v is not None and v == last_v:
            if t - since >= NEXT_ROUND_STALL_S:
                return 0.0                               # stalled again: not running
            continue
        if last_v is not None and v < last_v:
            return 0.0
        last_t, last_v, since = t, v, t
    return last_t - t_r


def wait_next_round(tails, start_round, clock=time.time, wait=time.sleep, timeout=NEXT_ROUND_TIMEOUT_S, spawns=None,
                    info=None):
    """Wait for the round after `start_round` (the mp_round_count value the finished round was played at) on every
    tail (C1, fix round -- 8c accepted the step at 783.5 s, 5.7 s before the clock restart and the reset to spawn):
      * mp_round_count moved past it (each tail's step time recorded);
      * the guest clock 0x4365c0 restarted past its frozen boundary value and kept advancing for
        NEXT_ROUND_CLOCK_RUN_S after the restart (clock_restart);
      * the newest actor row fresh (the actor re-found by its vtable) and within NEXT_ROUND_SPAWN_UNITS (ground) of the
        side's spawn OR of the other side's (close-out wave: the game may swap the sides' spawns between rounds)
        (`spawns` {tag: (x, y, z)}; a side without one cannot pass); info['spawns'] records same | swapped | mixed.
    mp_game_over != 0 ends the wait; an unread mp_round_count at round start is NO-DATA at once (no hang).
    -> (ok, reason, {tag: actor_addr}); `info` (a dict) receives {tag: {step, restart, running, pos, spawn_d}}."""
    info = {} if info is None else info
    if start_round is None:
        return False, f"{vc.NO_DATA} mp_round_count unread at round start -- the next round cannot be told", {}
    t_end = clock() + timeout
    while True:
        states, done = {}, True
        for tag, tail in tails.items():
            rc, go = round_count(tail)
            if go not in (None, 0):
                return False, f"mp_game_over={go} on {tag}: the match is over", {}
            st = info.setdefault(tag, {"step": None, "restart": None, "running": 0.0, "pos": None, "spawn_d": None})
            if st["step"] is None:
                st["step"] = step_time(tail, start_round)
            with tail._lock:                            # noqa: SLF001
                rt = [r for r in tail.round_time_rows if st["step"] is None or r[0] >= st["step"] - 1.0]
                actor = tail.actor_rows[-1] if tail.actor_rows else None
            now = clock()
            running = False
            if st["step"] is not None:
                rs = clock_restart(rt, st["step"])
                if rs is not None:
                    st["restart"], st["running"] = rs[1], rs[2]
                    running = rs[2] >= NEXT_ROUND_CLOCK_RUN_S and rt and now - rt[-1][0] <= NEXT_ROUND_FRESH_S
            fresh = actor is not None and now - actor[0] <= NEXT_ROUND_FRESH_S
            spawn = (spawns or {}).get(tag)
            if fresh:
                st["pos"] = actor[1:4]
                st["spawn_d"] = None if spawn is None else math.hypot(actor[1] - spawn[0], actor[3] - spawn[2])
                others = [(math.hypot(actor[1] - sp[0], actor[3] - sp[2]), o) for o, sp in sorted((spawns or {}).items())
                          if o != tag and sp is not None]
                st["other_d"], st["other"] = min(others) if (spawn is not None and others) else (None, None)
            own_ok = fresh and st["spawn_d"] is not None and st["spawn_d"] <= NEXT_ROUND_SPAWN_UNITS
            other_ok = (fresh and not own_ok and st.get("other_d") is not None
                        and st["other_d"] <= NEXT_ROUND_SPAWN_UNITS)
            st["at"] = "own" if own_ok else "other" if other_ok else None
            at_spawn = own_ok or other_ok
            states[tag] = (rc, st["step"] is not None, running, fresh, at_spawn, actor[4] if actor else None)
            done = done and st["step"] is not None and running and at_spawn
        if done:
            at = {info[tag]["at"] for tag in tails}
            info["spawns"] = "same" if at == {"own"} else "swapped" if at == {"other"} else "mixed"
            return True, "", {tag: s[5] for tag, s in states.items()}
        if clock() >= t_end:
            return False, ("timed out after %gs: " % timeout) + " ".join(
                f"{tag}(round={s[0]} stepped={s[1]} clock_running={s[2]} actor_fresh={s[3]} "
                f"at_spawn={s[4] if (spawns or {}).get(tag) else 'no-spawn'})"
                for tag, s in sorted(states.items())), {}
        wait(NEXT_ROUND_POLL_S)


def clock_string_deadline(clock_rows, slack=ROUND_END_SLACK_S):
    """[(t, 'MM:SS')] counting down -> host time by which the round must have ended: the newest string CHANGE's time +
    its remaining seconds + `slack` (None without a parseable string). A frozen string stops extending it."""
    prev, change = None, None
    for t, s in clock_rows:
        v = clock_seconds(s)
        if v is None:
            continue
        if prev is None or v != prev:
            change = (t, v)
        prev = v
    return None if change is None else change[0] + change[1] + slack


def wait_round_end(tails, fired, clock=time.time, wait=time.sleep, stop=None, slack=ROUND_END_SLACK_S,
                   fallback_s=ROUND_END_FALLBACK_S):
    """C2 (fix round): after the engagement returns, both sides stand neutral while the watches keep running, until
    `fired()` returns the round's KillWatch event (clock 00:00, the round step, a kill). The wait ends by the latest
    clock_string_deadline over the tails (remaining time + ROUND_END_SLACK_S), or `fallback_s` from now with no
    string read; `stop()` returning a reason ends it early (a move-path stall). -> (event | None, reason)."""
    t0 = clock()
    while True:
        ev = fired()
        if ev:
            return ev, ""
        why = stop() if stop is not None else None
        if why:
            return None, why
        deadlines = []
        for tail in tails.values():
            with tail._lock:                            # noqa: SLF001
                rows = [(t, st["clock"]) for t, st in tail.round_rows if not isinstance(st.get("clock"), vc.NoData)]
            d = clock_string_deadline(rows, slack)
            if d is not None:
                deadlines.append(d)
        deadline = max(deadlines) if deadlines else t0 + fallback_s
        if clock() >= deadline:
            return None, (f"no round end by the clock string's remaining time + {slack:g}s" if deadlines else
                          f"no round end and no clock string in {fallback_s:g}s")
        wait(ROUND_END_POLL_S)


# ---------------------------------------------------------------------------------------------
# Rung 0 (Amendment A4, R45): the runtime's own health in round 1, before the ladder can say anything about control
# ---------------------------------------------------------------------------------------------
# pass = MoveScale >= 17 calls/s over 60 s with both round clocks running, the clock string at real time (>= 0.95 of
# host time), and back-pressure waits not in the hundreds over that window (PS2X_GS_STATS=1 on both instances;
# PS2X_GS_MAX_PENDING_FRAMES=0 is the A/B knob). A RUNG0-FAIL ends the ladder: it names a runtime cause.
# R67 -- instrument parameters, not acceptance bars (plan Amendment A4): MoveScale >= 17/s over the first pause-free 60 s
# with both clocks running; clock-string rate >= 0.95; back-pressure waits < 100 per side in that window.
RUNG0_WINDOW_S = 60.0
RUNG0_MOVESCALE_MIN = 17.0       # calls/s (kill2 A 18.9, kill2 B 17.0, kill3 B 27.4; 8c under freezes 11.5)
RUNG0_CLOCK_RATE_MIN = 0.95
RUNG0_BP_WAITS_MAX = 100         # waits over the 60 s window, per instance ("not in the hundreds"): fail at >= this
RUNG0_INSTRUMENT_PARAMETERS = {"movescale_min_per_s": RUNG0_MOVESCALE_MIN, "window_s": RUNG0_WINDOW_S,
                               "clock_rate_min": RUNG0_CLOCK_RATE_MIN, "bp_waits_max": RUNG0_BP_WAITS_MAX}
RUNG0_PULSE_TABLE = (64, -64, 80, -80, 96, -96)
RUNG0_PULSE_S = 0.3


def clean_window(pauses, t0, t1, width=RUNG0_WINDOW_S):
    """The first [w0, w0 + width] inside [t0, t1] overlapping no pause (any side) -> (w0, w1) | None."""
    w0 = t0
    for p in sorted(pauses):
        if p[1] < w0:
            continue
        if p[0] >= w0 + width:
            break
        w0 = max(w0, p[1])
    return (w0, w0 + width) if w0 + width <= t1 else None


def movescale_rate(calls, w0, w1):
    """MoveScale calls/s over [w0, w1] from the logged #n (1 line in EVERY): (last #n - first #n) / their time span."""
    inside = [(t, n) for t, n in calls if w0 <= t <= w1]
    if len(inside) < 2 or inside[-1][0] - inside[0][0] < 0.5 * (w1 - w0):
        return None
    return (inside[-1][1] - inside[0][1]) / (inside[-1][0] - inside[0][0])


def clock_seconds(s):
    """'MM:SS' -> whole seconds, or None (unparseable). Public (R70): online_match_ours.route_clock_remaining_s reads
    the round clock the same way the C2 wait (wait_round_end / clock_string_deadline, below) does."""
    try:
        m, sec = s.split(":")
        return int(m) * 60 + int(sec)
    except (ValueError, AttributeError):
        return None


def clock_string_rate(clock_rows, w0, w1):
    """Real-time rate of the round clock string (MM:SS, counting down) over [w0, w1]: seconds it counted between its
    first and last CHANGE inside the window / the host seconds between those changes. None without two changes."""
    changes, prev = [], None
    for t, s in clock_rows:
        v = clock_seconds(s)
        if v is None:
            continue
        if prev is not None and v != prev[1] and w0 <= t <= w1:
            changes.append((t, v))
        prev = (t, v)
    if len(changes) < 2 or changes[-1][0] - changes[0][0] <= 0:
        return None
    return (changes[0][1] - changes[-1][1]) / (changes[-1][0] - changes[0][0])


def bp_waits(bp_rows, w0=None, w1=None):
    """Sum of `[gs-gl stats] backpressure ... waits=` over the window -> int | None (no stats rows)."""
    inside = [r for r in bp_rows if (w0 is None or r[0] >= w0) and (w1 is None or r[0] <= w1)]
    return sum(r[1] for r in inside) if inside else None


def rung0_verdict(sides, pauses, t0, t1):
    """sides: {tag: {"calls": [(t, n)], "clock": [(t, 'MM:SS')], "bp": [(t, waits, wait_ms, timeouts)]}} on one host
    clock; pauses: every pause of every side. -> (ok, reason, fields). A side without a clock string (the joiner may
    have none) is not judged on it; the host's must exist."""
    fields = {"status": "FAIL"}
    blind = ([f"[gs-gl stats] {tag} no rows at all (PS2X_GS_STATS=1?)" for tag in sorted(sides) if not sides[tag]["bp"]]
             + [f"MoveScale {tag} no rows at all" for tag in sorted(sides) if not sides[tag]["calls"]])
    if blind:                                    # R68: a missing instrument is NO-DATA, not a failed bar
        fields["status"] = vc.NO_DATA
        return False, "; ".join(blind), fields
    win = clean_window(pauses, t0, t1)
    if win is None:
        return False, f"no {RUNG0_WINDOW_S:g} s window with both round clocks running in [{t0:.1f}, {t1:.1f}]", fields
    fields["window"] = win
    problems = []
    for tag in sorted(sides):
        s = sides[tag]
        rate = movescale_rate(s["calls"], *win)
        fields[f"movescale_{tag}"] = rate
        if rate is None:
            problems.append(f"MoveScale {tag} NO-DATA")
        elif rate < RUNG0_MOVESCALE_MIN:
            problems.append(f"MoveScale {tag} {rate:.1f}/s < {RUNG0_MOVESCALE_MIN:g}")
        crate = clock_string_rate(s["clock"], *win)
        fields[f"clock_rate_{tag}"] = crate
        if crate is None and tag == "A":
            problems.append("clock string A NO-DATA")
        elif crate is not None and crate < RUNG0_CLOCK_RATE_MIN:
            problems.append(f"clock string {tag} {crate:.2f} < {RUNG0_CLOCK_RATE_MIN:g}")
        waits = bp_waits(s["bp"], *win)
        fields[f"bp_waits_{tag}"] = waits
        if waits is None:
            problems.append(f"[gs-gl stats] {tag} NO-DATA (PS2X_GS_STATS=1?)")
        elif waits >= RUNG0_BP_WAITS_MAX:
            problems.append(f"back-pressure waits {tag} {waits} >= {RUNG0_BP_WAITS_MAX}")
    fields["status"] = "FAIL" if problems else "PASS"
    return not problems, "; ".join(problems), fields
