"""Per-launch lobby summary from a two-instance drive log (Sprint 6 Task 2, research/28).

`python -m tools_py.parity.lobby_report logs/parity/drive_<name>.txt [...]` prints one row per launch and a
totals line: the table Task 2 Step 4's ten launches are judged by (>= 8/10 gameplay reached).

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
    base = os.path.basename(path)
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


def totals(summaries):
    n = len(summaries)
    gp = sum(1 for s in summaries if s["outcome"] == OUTCOME_GAMEPLAY)
    classes = Counter()
    for s in summaries:
        if s["outcome"] == OUTCOME_LOBBY_FAIL:
            classes[s["cls"]] += 1
        elif s["outcome"] == OUTCOME_RESULT:
            classes[f"result:{s['cls']}"] += 1
        elif s["outcome"] == OUTCOME_NONE:
            classes["none"] += 1
    per_class = " ".join(f"{c}={classes[c]}" for c in sorted(classes)) or "-"
    return f"TOTAL launches={n} gameplay={gp}/{n} classes: {per_class}"


def report(paths):
    """The rows and the totals line for the drive logs at `paths`."""
    out, summaries = [], []
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as f:
            s = summarise(f)
        summaries.append(s)
        out.append(row(launch_name(p), s))
    out.append(totals(summaries))
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m tools_py.parity.lobby_report <drive_log> [<drive_log>...]", file=sys.stderr)
        return 2
    for line in report(argv):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
