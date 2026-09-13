"""The engagement ladder's round loop and stop rules (Sprint 5 Amendment A: A1 per-round stop rules, A2 `--rounds N`).

One lobby success carries several rounds: a clock round end or a kill keeps the actor block and resets both players to
their spawns (KNOWN §4, launch 8c: mp_round_count steps ~5.4 s after the clock reads 00:00, the guest clock stands still
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
import time
from dataclasses import dataclass, field

from . import verdict_core as vc

LADDER_ROUNDS_DEFAULT = 4
SWAP_AFTER_RUNG1_ROUNDS = 3
DECIDE_AFTER_RUNG2_ROUNDS = 2
NEXT_ROUND_TIMEOUT_S = 45.0      # from a round's end to the next round's first live rows: 8c took ~11 s (00:00 ->
                                 # step 5.4 s -> clock restart and reset 5.5 s later)
NEXT_ROUND_POLL_S = 0.25
NEXT_ROUND_CLOCK_RUN_S = 1.0     # the guest clock must advance again for this long after the step
SWAP_MOVER = "SWAP-MOVER"
DAMAGE_PATH_DECISION = "DAMAGE-PATH-DECISION"


@dataclass
class RoundScore:
    n: int
    mover: str
    rung: int = 0
    verdict: str = vc.NO_DATA        # the round's RESULT word(s): PASS / FAIL ... / NO-DATA ...
    kill: bool = False
    line: str = ""                   # the LADDER round=<n> ... line
    fatal: object = None             # a reason that ends the ladder after this round (RUNG0-FAIL, a stall, ...)
    fields: dict = field(default_factory=dict)

    @property
    def usable(self):
        return self.rung >= 1 and not self.verdict.startswith(vc.NO_DATA)


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
                log(f"{SWAP_MOVER} after usable rounds {usable} at rung 1 without rung 2: --auto-swap -- rounds "
                    f"{n + 1}.. walk {other(mover)} (B descends via ~(652, 1230))")
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
    log(f"LADDER-SUMMARY rounds={len(history)}/{n_rounds} usable={len(usable)} "
        f"best_rung={max((r.rung for r in history), default=0)} kills={sum(1 for r in history if r.kill)} "
        f"rungs={','.join(str(r.rung) for r in history) or '-'} movers={','.join(r.mover for r in history) or '-'} "
        f"stop={stop or 'rounds done'}")
    return history, stop


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


def wait_next_round(tails, start_round, clock=time.time, wait=time.sleep, timeout=NEXT_ROUND_TIMEOUT_S):
    """Wait for the round after `start_round` (the mp_round_count value the finished round was played at) on every
    tail: mp_round_count moved past it, the guest clock 0x4365c0 advanced again for NEXT_ROUND_CLOCK_RUN_S after that,
    and a fresh actor row (the actor re-found by its vtable). -> (ok, reason, {tag: actor_addr})."""
    t_end = clock() + timeout
    while True:
        states, done = {}, True
        for tag, tail in tails.items():
            rc, go = round_count(tail)
            if go not in (None, 0):
                return False, f"mp_game_over={go} on {tag}: the match is over", {}
            with tail._lock:                            # noqa: SLF001
                rt = list(tail.round_time_rows[-16:])
                actor = tail.actor_rows[-1] if tail.actor_rows else None
            now = clock()
            stepped = rc is not None and start_round is not None and rc != start_round
            running = len(rt) >= 2 and rt[-1][1] != rt[0][1] and rt[-1][0] - rt[0][0] >= NEXT_ROUND_CLOCK_RUN_S and \
                len({v for t, v in rt if t >= now - NEXT_ROUND_CLOCK_RUN_S - 0.5}) >= 2
            fresh = actor is not None and now - actor[0] <= 1.0
            states[tag] = (rc, stepped, running, fresh, actor[4] if actor else None)
            done = done and stepped and running and fresh
        if done:
            return True, "", {tag: s[4] for tag, s in states.items()}
        if clock() >= t_end:
            return False, ("timed out after %gs: " % timeout) + " ".join(
                f"{tag}(round={s[0]} stepped={s[1]} clock_running={s[2]} actor_fresh={s[3]})"
                for tag, s in sorted(states.items())), {}
        wait(NEXT_ROUND_POLL_S)


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


def _clock_seconds(s):
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
        v = _clock_seconds(s)
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
    fields = {}
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
    return not problems, "; ".join(problems), fields
