"""Sprint 10 Goal 1 -- "it stays up": the scheduled ladder's ledger.

A scheduled job runs the engagement ladder against the hosted server in windows the owner is away, and every run
becomes one record here: its outcome (the ladder contract: KILL, NO-KILL, NO-DATA, NO-CONTROL, LOBBY-FAIL <class>,
CRASH, PIN-FAIL), the rounds asked and played, the usable rounds, the kills, the best rung, the pinned harness
commit, the exe's sha256, and the server. The three rates the spec asks for are computed over the ledger:
lobby rate (runs that reached a round / runs), round-start rate (usable rounds / rounds played), kill rate (kills /
usable rounds). The bar: seven consecutive runs with no LOBBY-FAIL and no CRASH.

    python -m tools_py.parity.ladder_ledger add <run_dir> <server>     # read <run_dir>.done + <run_dir>/drive.log, append
    python -m tools_py.parity.ladder_ledger render                     # logs/ladder/ledger.jsonl -> docs/LADDER.md
"""
import datetime as _dt
import json
import os
import re
import sys
from typing import Dict, List, Optional

LEDGER = os.path.join("logs", "ladder", "ledger.jsonl")
TABLE = os.path.join("docs", "LADDER.md")
BAR = 7

_DONE = re.compile(r"^done (\d+) mpexit=(\d+) (\S+)(?: (\S+))?.*?harness=(\S+).*?sha256=(\S+)", re.M)
_SUMMARY = re.compile(r"A_LADDER-SUMMARY rounds=(\d+)/(\d+) usable=(\d+) best_rung=(\S+) kills=(\d+)")
_LOBBY = re.compile(r"A_LOBBY class=(\S+)")
_OUTCOMES_WITH_CLASS = {"LOBBY-FAIL"}


def read_run(run_dir: str, server: str) -> Dict:
    stamp = os.path.basename(run_dir.rstrip("/\\"))
    # Where the ladder really writes (scripts/parity/ladder_frostfire.sh): the done marker at logs/<stamp>.done, a
    # level above the run's logs/parity/<stamp>/, and the drive log at logs/parity/drive_<stamp>.txt beside the run
    # directory. The first scheduled run (ladder_20260920_043246) was ledgered UNKNOWN 0/0 because this reader
    # looked only next to and inside the run directory; both places are read, the run's own first.
    parent = os.path.dirname(run_dir.rstrip("/\\"))
    done_candidates = [run_dir + ".done", os.path.join(os.path.dirname(parent), stamp + ".done")]
    drive_candidates = [os.path.join(run_dir, "drive.log"), os.path.join(parent, "drive_" + stamp + ".txt")]
    done_text = next((open(p, encoding="utf-8", errors="replace").read() for p in done_candidates if os.path.exists(p)), "")
    drive = next((open(p, encoding="utf-8", errors="replace").read() for p in drive_candidates if os.path.exists(p)), "")
    rec = {"stamp": stamp, "server": server, "when": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "rc": None, "outcome": "UNKNOWN", "lobby_class": None, "rounds": 0, "rounds_asked": 0, "usable": 0, "kills": 0,
           "best_rung": None, "harness": None, "exe_sha256": None}
    m = _DONE.search(done_text)
    if m:
        rec["rc"] = int(m.group(1))
        rec["outcome"] = m.group(3)
        if m.group(3) in _OUTCOMES_WITH_CLASS and m.group(4) and "=" not in m.group(4):
            rec["lobby_class"] = m.group(4)
        rec["harness"] = m.group(5)
        rec["exe_sha256"] = m.group(6)
    m = _SUMMARY.search(drive)
    if m:
        rec["rounds"], rec["rounds_asked"], rec["usable"], rec["kills"] = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(5))
        rec["best_rung"] = None if m.group(4) in ("None", "-") else int(m.group(4))
    m = _LOBBY.search(drive)
    if m and rec["outcome"] == "LOBBY-FAIL":
        rec["lobby_class"] = m.group(1)
    return rec


def append(path: str, rec: Dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def load(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def rates(runs: List[Dict]) -> Dict:
    n = len(runs)
    reached = sum(1 for r in runs if r.get("outcome") not in ("LOBBY-FAIL", "CRASH", "PIN-FAIL", "UNKNOWN") and r.get("rounds", 0) > 0)
    rounds = sum(r.get("rounds", 0) for r in runs)
    usable = sum(r.get("usable", 0) for r in runs)
    kills = sum(r.get("kills", 0) for r in runs)
    streak = 0
    for r in reversed(runs):
        if r.get("outcome") in ("LOBBY-FAIL", "CRASH", "PIN-FAIL", "UNKNOWN"):
            break
        streak += 1
    return {"runs": n, "lobby_rate": (reached / n) if n else 0.0, "round_start_rate": (usable / rounds) if rounds else 0.0,
            "kill_rate": (kills / usable) if usable else 0.0, "consecutive_clean": streak, "bar": BAR}


def render(runs: List[Dict]) -> str:
    r = rates(runs)
    lines = ["# The ladder, scheduled -- Sprint 10 Goal 1, \"it stays up\"", "",
             "One row per scheduled run of the engagement ladder against the hosted server (two instances on this host, in "
             "windows the owner is away). Written by `tools_py/parity/ladder_ledger.py` from `logs/ladder/ledger.jsonl`; a "
             "person commits it. The bar: **%d consecutive runs with no LOBBY-FAIL and no CRASH.**" % BAR, "",
             f"**Runs:** {r['runs']}  **Lobby rate:** {r['lobby_rate']:.0%}  **Round-start rate:** {r['round_start_rate']:.0%}  "
             f"**Kill rate:** {r['kill_rate']:.0%}  **Clean streak:** {r['consecutive_clean']} of {BAR}", "",
             "| when (UTC) | run | outcome | rounds | usable | kills | best rung | harness | exe sha256 | server |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for x in runs:
        out = x.get("outcome", "?") + (f" {x['lobby_class']}" if x.get("lobby_class") else "")
        lines.append(f"| {x.get('when','')} | `{x.get('stamp','')}` | {out} | {x.get('rounds',0)}/{x.get('rounds_asked',0)} | "
                     f"{x.get('usable',0)} | {x.get('kills',0)} | {x.get('best_rung') if x.get('best_rung') is not None else '-'} | "
                     f"`{(x.get('harness') or '')[:8]}` | `{(x.get('exe_sha256') or '')[:8]}` | {x.get('server','')} |")
    return "\n".join(lines) + "\n"


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[-2:]); return 2
    if argv[1] == "add":
        rec = read_run(argv[2], argv[3] if len(argv) > 3 else "?")
        append(LEDGER, rec)
        print(json.dumps(rec, sort_keys=True))
        open(TABLE, "w", encoding="utf-8", newline="").write(render(load(LEDGER)))
        return 0
    if argv[1] == "render":
        open(TABLE, "w", encoding="utf-8", newline="").write(render(load(LEDGER)))
        print(open(TABLE, encoding="utf-8").read())
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
