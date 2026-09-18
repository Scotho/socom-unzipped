"""Per-launch lobby summary from a two-instance drive log (Sprint 6 Task 2, research/28).

`python -m tools_py.parity.lobby_report logs/parity/drive_<name>.txt [...]` prints one row per launch and a
totals line: the table Task 2 Step 4's ten launches are judged by (>= 8/10 gameplay reached).

With `--bar <fraction>` (Sprint 7 Task 2d) it adds `RATE <g>/<n> bar=<x.xx> PASS|FAIL` and exits 1 on FAIL,
so the bar is machine-checked rather than eyeballed:

    python -m tools_py.parity.lobby_report --bar 0.8 logs/parity/drive_s7_lobby_*.txt

Line grammar (tools_py/parity/online_login_ours.py, Shell.log): `<t>s <A|B>_<message>`; the time prefix is
absent on a few lines and the trailer (`mpexit=...`, `[run_detached] ...`, `--until-kill: ...`) carries no tag.
The messages read here:

    [lobby] <step> press=<btn> verified=<bool> attempt=<n>     one line per press (press_verified)
    LOBBY RESEND <step> attempt=<k>                            a re-send (verify_resend)
    RESULT LOBBY-FAIL <class>[ -- detail]                      the lobby failed (lobby_fail)
    LOBBY class=<class>                                        ok, or the failure class again
    liveness OK: ...                                           gameplay reached (pre-`LOBBY class=` logs too)
    RESULT <word> ...                                          any other engagement result (round=N PASS, NO-CONTROL...)
    screen <name> after <t>s                                   the coarse stage, for logs that predate [lobby] lines

Logs from before the [lobby] lines (the Sprint 5 ladders) report outcome and coarse stage only.
"""
import os
import re
import sys
from collections import Counter

TAGS = ("A", "B")
OUTCOME_GAMEPLAY = "gameplay"
OUTCOME_LOBBY_FAIL = "lobby-fail"
OUTCOME_RESULT = "result"
OUTCOME_NONE = "none"

_LINE = re.compile(r"^\s*(?:\d+(?:\.\d+)?s\s+)?([AB])_(.*)$")
_PRESS = re.compile(r"^\[lobby\] (\S+) press=(\S+) verified=(True|False) attempt=(\d+)\s*$")
_RESEND = re.compile(r"^LOBBY RESEND (\S+) attempt=(\d+)\s*$")
_LOBBY_FAIL = re.compile(r"^RESULT LOBBY-FAIL (\S+)(?: -- (.*))?$")
_RESULT = re.compile(r"^RESULT (\S+)")
_SCREEN = re.compile(r"^screen (\S+) after ")
_MPEXIT = re.compile(r"^mpexit=(\d+)")


def split_line(line):
    """('A'|'B', message) for a tagged drive-log line, else (None, stripped line)."""
    m = _LINE.match(line.rstrip("\r\n"))
    if m:
        return m.group(1), m.group(2)
    return None, line.strip()


def _instance():
    return {"presses": Counter(), "unverified": Counter(), "resends": Counter(),
            "last_stage": None, "last_screen": None, "results": [], "gameplay": False}


def summarise(lines):
    """Summarise one drive log's lines.

    Returns {"instances": {"A": {...}, "B": {...}}, "outcome", "cls", "ended_stage", "mpexit"} where each instance
    carries Counters `presses`, `unverified`, `resends` keyed by stage, `last_stage` (last [lobby] step or re-sent
    step), `last_screen` (last `screen <name>`), `results` (the RESULT words seen) and `gameplay`.
    outcome: "gameplay" (liveness OK / LOBBY class=ok on any instance), "lobby-fail" (cls = the class),
    "result" (cls = the first other RESULT word), or "none". ended_stage is the failing instance's last stage
    (or last screen) on a lobby failure, else the last stage seen on any instance."""
    inst = {t: _instance() for t in TAGS}
    fail_tag, fail_cls, mpexit = None, None, None
    last_tag_with_stage = None
    for raw in lines:
        tag, msg = split_line(raw)
        if tag is None:
            m = _MPEXIT.match(msg)
            if m:
                mpexit = int(m.group(1))
            continue
        me = inst[tag]
        m = _PRESS.match(msg)
        if m:
            step, verified = m.group(1), m.group(3) == "True"
            me["presses"][step] += 1
            if not verified:
                me["unverified"][step] += 1
            me["last_stage"] = step
            last_tag_with_stage = tag
            continue
        m = _RESEND.match(msg)
        if m:
            me["resends"][m.group(1)] += 1
            me["last_stage"] = m.group(1)
            last_tag_with_stage = tag
            continue
        m = _SCREEN.match(msg)
        if m:
            me["last_screen"] = m.group(1)
            continue
        if msg.startswith("liveness OK") or msg.startswith("LOBBY class=ok"):
            me["gameplay"] = True
            continue
        m = _LOBBY_FAIL.match(msg)
        if m:
            me["results"].append("LOBBY-FAIL")
            if fail_cls is None:
                fail_tag, fail_cls = tag, m.group(1)
            continue
        m = _RESULT.match(msg)
        if m:
            me["results"].append(m.group(1))

    if any(inst[t]["gameplay"] for t in TAGS):
        outcome, cls = OUTCOME_GAMEPLAY, "ok"
    elif fail_cls is not None:
        outcome, cls = OUTCOME_LOBBY_FAIL, fail_cls
    else:
        others = [r for t in TAGS for r in inst[t]["results"] if r != "LOBBY-FAIL"]
        outcome, cls = (OUTCOME_RESULT, others[0]) if others else (OUTCOME_NONE, None)

    if fail_tag is not None:
        ended = inst[fail_tag]["last_stage"] or inst[fail_tag]["last_screen"]
    elif last_tag_with_stage is not None:
        ended = inst[last_tag_with_stage]["last_stage"]
    else:
        ended = next((inst[t]["last_screen"] for t in TAGS if inst[t]["last_screen"]), None)
    return {"instances": inst, "outcome": outcome, "cls": cls, "ended_stage": ended, "mpexit": mpexit}


def launch_name(path):
    # The log paths in a report are whatever the host that ran the launch wrote -- a Windows path
    # ("C:\\x\\detached_s6_ladder1.txt") is read back on Linux too (a shared report, the CI ring), and
    # posixpath.basename would hand back the whole string. Split on BOTH separators, always.
    base = path.replace("\\", "/").rsplit("/", 1)[-1]
    if base.endswith(".txt"):
        base = base[:-4]
    for prefix in ("drive_", "detached_"):
        if base.startswith(prefix):
            return base[len(prefix):]
    return base


def _stage_counts(summary, key):
    """'A:stage=n B:stage=n' for the Counter `key`, '-' when empty."""
    parts = []
    for t in TAGS:
        c = summary["instances"][t][key]
        parts.extend(f"{t}:{stage}={c[stage]}" for stage in sorted(c))
    return " ".join(parts) if parts else "-"


def row(name, summary):
    ended = summary["ended_stage"] or "-"
    return (f"{name:<28} {summary['outcome']:<10} {summary['cls'] or '-':<24} ended={ended:<28} "
            f"resends={_stage_counts(summary, 'resends')} unverified={_stage_counts(summary, 'unverified')}")


def rate(summaries):
    """(gameplay, total, classes) over `summaries`: the launches that reached gameplay, how many there were,
    and a Counter of the failure class of every miss -- the lobby class on a lobby failure, `result:<word>`
    for any other RESULT, `none` for a launch that produced no verdict at all."""
    classes = Counter()
    for s in summaries:
        if s["outcome"] == OUTCOME_LOBBY_FAIL:
            classes[s["cls"]] += 1
        elif s["outcome"] == OUTCOME_RESULT:
            classes[f"result:{s['cls']}"] += 1
        elif s["outcome"] == OUTCOME_NONE:
            classes["none"] += 1
    gameplay = sum(1 for s in summaries if s["outcome"] == OUTCOME_GAMEPLAY)
    return gameplay, len(summaries), classes


def totals(summaries):
    gp, n, classes = rate(summaries)
    per_class = " ".join(f"{c}={classes[c]}" for c in sorted(classes)) or "-"
    return f"TOTAL launches={n} gameplay={gp}/{n} classes: {per_class}"


def summarise_paths(paths):
    """[(launch name, summary)] for the drive logs at `paths`."""
    named = []
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as f:
            named.append((launch_name(p), summarise(f)))
    return named


def report(paths):
    """The rows and the totals line for the drive logs at `paths`."""
    named = summarise_paths(paths)
    return [row(name, s) for name, s in named] + [totals([s for _, s in named])]


def rate_line(summaries, bar):
    """('RATE <g>/<n> bar=<x.xx> PASS|FAIL', passed): the bar is a fraction of the launches, PASS when g/n >= bar."""
    g, n, _ = rate(summaries)
    passed = n > 0 and g >= bar * n - 1e-9
    return f"RATE {g}/{n} bar={bar:.2f} {'PASS' if passed else 'FAIL'}", passed


USAGE = "usage: python -m tools_py.parity.lobby_report [--bar <fraction>] <drive_log> [<drive_log>...]"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    bar, paths, i = None, [], 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--bar" or arg.startswith("--bar="):
            value = arg.split("=", 1)[1] if "=" in arg else (argv[i + 1] if i + 1 < len(argv) else None)
            try:
                bar = float(value)
            except (TypeError, ValueError):
                print(f"--bar wants a fraction of the launches, e.g. --bar 0.8 (got {value!r})", file=sys.stderr)
                return 2
            i += 1 if "=" in arg else 2
            continue
        paths.append(arg)
        i += 1
    if not paths:
        print(USAGE, file=sys.stderr)
        return 2
    named = summarise_paths(paths)
    summaries = [s for _, s in named]
    for name, s in named:
        print(row(name, s))
    print(totals(summaries))
    if bar is None:
        return 0
    line, passed = rate_line(summaries, bar)
    print(line)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
