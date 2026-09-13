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
