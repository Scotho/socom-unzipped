"""The gate's guest-value probe (Sprint 6 Task 1c): a handful of guest values read from a run's [peek] rows and
compared with console numbers on disk.

The title, transition and mission stages compare our runs with our own earlier runs, so they were blind to the 15-bit
rand(), the skeleton root decay and the soft-double chain (KNOWN §4 "the gate proves regression only"). This reads
values whose console numbers are already measured -- `scripts/parity/guest_probe_console.json` names each peek chain,
the console value, a tolerance and the source -- and reports them beside the mission verdict.

    python -m tools_py.parity.guest_probe <run.log> [scripts/parity/guest_probe_console.json]

`peek_spec(json)` is the PS2X_PEEK the mission stage must launch with for every chain to be present. A chain that
never resolves is reported NO-DATA and counts as a failure: an instrument that reads nothing is not a quiet one.
Scalar values are the settled reading (median of the last quarter of rows that carried one), because the root node
decays over the first seconds (research/17 §4.1). `teleport_steps` counts consecutive-row actor position steps > 30
units (research/25 §1.1)."""
import json
import math
import os
import statistics
import sys
from collections import namedtuple

from tools_py.parity import sp_death_probe as sp
from tools_py.parity import verdict_core as vc

Result = namedtuple("Result", "name ours console tol ok detail")

# research/25 §1.1 measured teleports as steps > 30 units between 4 Hz rows, i.e. > 120 u/s; a run reads ~40 u/s
# (s6_probe's 8 s forward hold: 36-45 units per 1 s row). The row period comes from the guest clock (0x4365c0,
# float seconds) when the peek carries it, else DEFAULT_ROW_PERIOD_S -- the mission stage's PS2X_PC_SAMPLER=1.
TELEPORT_SPEED_UPS = 120.0
DEFAULT_ROW_PERIOD_S = 1.0
GUEST_CLOCK = 0x4365C0
ROOT_NODE_OFF = 0x2E8
MOVE_SCALE_OFF = 0x1368


def load_console(path):
    with open(path) as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def peek_spec(console_json):
    chains = ["0x416054:3"]
    for v in load_console(console_json).values():
        for c in v["peek"].split(","):
            c = c.strip()
            if c and c not in chains:
                chains.append(c)
    return ",".join(chains)


def _rows(lines_or_path):
    if isinstance(lines_or_path, (str, os.PathLike)):
        with open(lines_or_path, "r", errors="replace") as f:
            lines = f.readlines()
    else:
        lines = lines_or_path
    return [sp.parse_peek_line(l) for l in lines if l.startswith("[peek]")]


def _actor_pos(items):
    a = sp.actor_addr(items)
    blk = sp.item_at(items, a) if a else None
    if blk and blk[0] == vc.ACTOR_VTABLE and len(blk) >= 10:
        x, y, z = (sp.f32(blk[k]) for k in vc.ACTOR_POS_WORDS)
        if x or y or z:
            return a, (x, y, z)
    return a, None


def _settled(values):
    if not values:
        return None
    tail = values[-max(1, len(values) // 4):]
    return float(statistics.median(tail))


def evaluate(lines_or_path, console_json):
    console = load_console(console_json)
    rows = _rows(lines_or_path)
    root, scale, positions = [], [], []
    for items in rows:
        a, pos = _actor_pos(items)
        if pos:
            clock_w = sp.word_at(items, GUEST_CLOCK)
            positions.append((pos, sp.f32(clock_w) if clock_w is not None else None))
        if not a:
            continue
        node = sp.word_at(items, a + ROOT_NODE_OFF)
        if node:
            w = sp.word_at(items, node + 4)
            if w is not None:
                root.append(sp.f32(w))
        w = sp.word_at(items, a + MOVE_SCALE_OFF)
        if w is not None:
            scale.append(sp.f32(w))
    steps = 0
    for (p, tp), (q, tq) in zip(positions, positions[1:]):
        dt = (tq - tp) if (tp is not None and tq is not None and tq > tp) else DEFAULT_ROW_PERIOD_S
        if math.dist(p, q) / dt > TELEPORT_SPEED_UPS:
            steps += 1
    measured = {"root_node_y": (_settled(root), len(root)),
                "move_scale": (_settled(scale), len(scale)),
                "teleport_steps": (steps if positions else None, len(positions))}
    out = []
    for name, spec in console.items():
        ours, n = measured.get(name, (None, 0))
        con, tol = spec["console"], spec["tol"]
        if ours is None:
            out.append(Result(name, None, con, tol, False, f"NO-DATA (0 reads of {len(rows)} rows)"))
            continue
        ok = abs(ours - con) <= tol
        out.append(Result(name, ours, con, tol, ok,
                          f"ours={ours:.5g} console={con:.5g} tol={tol:g} reads={n} of {len(rows)} rows"))
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    console_json = argv[1] if len(argv) > 1 else os.path.join("scripts", "parity", "guest_probe_console.json")
    results = evaluate(argv[0], console_json)
    for r in results:
        print(f"PROBE {r.name:15s} {'PASS' if r.ok else 'FAIL'} {r.detail}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
