"""The gate's guest-value probe (Sprint 6 Task 1c): a handful of guest values read from a run's [peek] rows and
compared with console numbers on disk.

The title, transition and mission stages compare our runs with our own earlier runs, so they were blind to the 15-bit
rand(), the skeleton root decay and the soft-double chain (KNOWN §4 "the gate proves regression only"). This reads
values whose console numbers are already measured -- `scripts/parity/guest_probe_console.json` names each peek chain,
the console value, a tolerance and the source -- and reports them beside the mission verdict.

    python -m tools_py.parity.guest_probe <run.log> [scripts/parity/guest_probe_console.json] [--revision r0004]

`peek_spec(json, revision)` is the PS2X_PEEK the mission stage must launch with for every chain to be present. A
chain that never resolves is reported NO-DATA and counts as a failure: an instrument that reads nothing is not a
quiet one. Scalar values are the settled reading (median of the last quarter of rows that carried one), because the
root node decays over the first seconds (research/17 §4.1). `teleport_steps` counts consecutive-row actor position
steps > 30 units (research/25 §1.1).

EVERY GUEST ADDRESS HERE IS PER REVISION (Sprint 11 Task 19). They were r0001 literals -- `0x416054` in the chain
list, `*0x408c58+0x2e8` and `0x4365c0` in the console json, the actor vtable `0x6691a0` the position read keys on --
and on the r0004 build all four are somebody else's memory: logs/parity/gate/s11_r0004_reg2 read 0 rows of 479 and
the mission lane failed `GUEST PROBE FAILED: root_node_y` with all three probes NO-DATA. The table is
`tools_py/parity/guest_addresses.py` -- one column per revision, `address(name, revision)` the only way in, and the
one home verdict_core and sp_death_probe read their r0001 constants from too. A revision the table has no column
for raises, and so does an image, or a run log, that will not say which revision it is. Falling back to r0001 is
the one thing this must never do: an instrument reading another build's addresses does not present as a bad
address, it presents as silence -- or, worse, as a number.

AND SO IS THE LAYOUT (Sprint 11 Task 19, the move_scale lane). The address column alone was not enough:
s11_r0004_probe1 reached the right actor -- vtable 0x668b20, root_node_y 4.707, teleport_steps 0 -- and still failed
`move_scale ours=0 console=1`, because r0004's actor gained a word at +0x1334 and MoveScale sits at +0x136c there,
not +0x1368. `+0x1368` on r0004 is the field below it, and that field is 0. PROBE_OFFSETS is the layout column and
`offset(name, revision)` the only way in; `translate_chain` moves a `+0xNNN` displacement through it exactly as it
moves a bare address through PROBE_ADDRESSES. This was the fourth concern of the addresses report, arriving."""
import argparse
import json
import math
import os
import re
import statistics
import sys
from collections import namedtuple

from tools_py.parity import guest_addresses as ga
from tools_py.parity import sp_death_probe as sp
from tools_py.parity import verdict_core as vc

Result = namedtuple("Result", "name ours console tol ok detail")

# research/25 §1.1 measured teleports as steps > 30 units between 4 Hz rows, i.e. > 120 u/s; a run reads ~40 u/s
# (s6_probe's 8 s forward hold: 36-45 units per 1 s row). The row period comes from the guest clock (r0001
# 0x4365c0, float seconds) when the peek carries it, else DEFAULT_ROW_PERIOD_S -- the mission stage's
# PS2X_PC_SAMPLER=1.
TELEPORT_SPEED_UPS = 120.0
DEFAULT_ROW_PERIOD_S = 1.0

# camera_orbit (Task 19 review F7). camera_record is the one address in the table that the gate LAUNCHES
# and never READS, so a wrong r0004 value for it would have had no symptom at all -- while the other three
# announce themselves as NO-DATA. It is also the entry resting on the fewest twinned referrers (one). So
# the probe reads it: the camera record orbits the player, and the median ground distance between the two
# is a number with a known shape.
#
# Calibrated on what the gate itself measures, not on a target. Median |camera - actor| in the xz plane,
# over every row that carries both, across twelve archived r0001 mission stamps: 17.16 (s11_rtstate_gate)
# to 20.13 (s11_merge19_gate), and 19.35 on the r0004 lane s11_r0004_probe1 -- consistent with, and a
# little inside, the 24.9-unit steady orbit radius online_match_ours.CAMERA_ORBIT_RADIUS measured on the
# ladder. The band below is 7.5..31.5, roughly 1.6x outside that spread either way, and it rejects what a
# WRONG address reads: the five stamps that aimed r0001 chains at an r0004 image (s11_r0004_reg2 and
# friends) all measure 0.90, every row.
CAMERA_ORBIT_U = 19.5
CAMERA_ORBIT_TOL_U = 12.0
# THE GUEST ADDRESSES ARE NOT HERE. They are tools_py/parity/guest_addresses.py -- the one home this
# module, verdict_core and sp_death_probe all read them from, so the r0001 column cannot drift into three
# different values (Task 19 review F6). That module also owns the rule for deciding WHICH revision, and
# tools_py/data_via_twin.py regenerates its r0004 column from the two images. Re-exported here because
# gate.py and the suite reach for them through this module.
address = ga.address
offset = ga.offset
PROBE_ADDRESSES = ga.PROBE_ADDRESSES
PROBE_OFFSETS = ga.PROBE_OFFSETS
REVISIONS = ga.REVISIONS
BANNER_RE = ga.BANNER_RE
GAME_ELF_ENV = ga.GAME_ELF_ENV
DEFAULT_GAME_ELF = ga.DEFAULT_GAME_ELF
revision_of_image = ga.revision_of_image
launch_revision = ga.launch_revision
revision_of_peek_spec = ga.revision_of_peek_spec


def log_revision(lines):
    """The revision the runtime says it installed, off its own run log -- the name `evaluate` and the gate
    have always used. guest_addresses.log_revision returns (revision, how); this keeps the revision."""
    return ga.log_revision(lines)[0]


# The build banner in the game image ("SOCOM 2 r0001 17:22:21 Oct 11 2003"): the same evidence
# socom2_addresses.h's selectFromImage() picks its column by, read here off the file instead of out of guest
# memory, because PS2X_PEEK has to be built BEFORE the launch. It occurs exactly once in each image.
BANNER_RE = re.compile(rb"SOCOM 2 (r\d{4}) ")
# ... and what the runtime says it actually installed, once it has run. This is the stronger of the two for
# scoring a finished run: it is the column the overrides were installed with, not the column we expected.
LOG_REVISION_RE = re.compile(r"address table: the image names itself (r\d{4})")
GAME_ELF_ENV = "SOCOM_GAME_ELF"
DEFAULT_GAME_ELF = os.path.join("game", "disc", "socom2_game.elf")


def revision_of_image(path):
    """The revision of a game image, from its build banner. No banner, or more than one revision's worth,
    raises: an image that will not name itself is not an r0001 image."""
    with open(path, "rb") as f:
        found = sorted({m.group(1).decode() for m in BANNER_RE.finditer(f.read())})
    if len(found) != 1:
        raise ValueError("guest_probe: %s carries no single build banner (found %s) -- it cannot say which "
                         "revision's addresses to read" % (path, found or "none"))
    return found[0]


def launch_revision(env=None):
    """The revision of the image a launch would use: $SOCOM_GAME_ELF, else game/disc/socom2_game.elf. An
    image that is NAMED but absent or unreadable raises. The default path missing is not an error -- game/
    is git-ignored, so a bare clone has no image and no launch to make, and r0001 is the revision that path
    itself names (gate.collect_pins still hashes the launch environment there)."""
    env = os.environ if env is None else env
    named = env.get(GAME_ELF_ENV)
    path = named or DEFAULT_GAME_ELF
    if not os.path.isfile(path):
        if named:
            raise ValueError("guest_probe: %s names %s, which is not a file -- the probe cannot tell which "
                             "revision's addresses to read" % (GAME_ELF_ENV, named))
        return "r0001"
    return revision_of_image(path)


def log_revision(lines):
    """The revision the runtime says it installed, off its own run log
    (`[socom2] address table: the image names itself r0004 -- using the r0004 addresses`). A log that never
    says raises: the probe does not guess, and it never assumes r0001."""
    for line in lines:
        m = LOG_REVISION_RE.search(line)
        if m:
            return m.group(1)
    raise ValueError("guest_probe: the run log never says which revision the runtime installed "
                     "(no '[socom2] address table: the image names itself rNNNN' line), so the probe "
                     "cannot know which column to read -- pass one explicitly")


_HEX_RE = re.compile(r"(\+?)(0[xX][0-9a-fA-F]+)")
_BY_R0001 = {col["r0001"]: name for name, col in PROBE_ADDRESSES.items()}
_FIELD_BY_R0001 = {col["r0001"]: name for name, col in PROBE_OFFSETS.items()}


def _translate_token(match, revision):
    plus, literal = match.group(1), match.group(2)
    value = int(literal, 16)
    if plus:                                    # `+0x2e8` -- a displacement inside the object
        name = _FIELD_BY_R0001.get(value)
        return "+0x%x" % offset(name, revision) if name else match.group(0)
    name = _BY_R0001.get(value)                 # a bare literal -- a guest address
    return "0x%x" % address(name, revision) if name else match.group(0)


def translate_chain(chain, revision):
    """One PS2X_PEEK chain in `revision`'s numbers. A bare hex literal that is an r0001 PROBE ADDRESS
    moves to that revision's address column; a literal written as `+0xNNN` is a field displacement inside
    the object and moves to that revision's LAYOUT column (PROBE_OFFSETS). Both halves are needed: on
    r0004 `*0x408c58+0x2e8` keeps its 0x2e8 and `*0x408c58+0x1368` becomes `+0x136c`, because r0004's
    actor gained a word below MoveScale. Anything the two tables do not name is left exactly as it is."""
    return _HEX_RE.sub(lambda m: _translate_token(m, revision), chain)


def load_console(path):
    with open(path) as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def peek_spec(console_json, revision):
    """The PS2X_PEEK the mission stage launches with, in `revision`'s addresses. The console json stays
    written in r0001's (it is a pinned file, and the console numbers were measured against that build);
    the translation happens here, on the way out."""
    chains = ["0x%x:3" % address("camera_record", revision)]
    for v in load_console(console_json).values():
        for c in v["peek"].split(","):
            c = translate_chain(c.strip(), revision)
            if c and c not in chains:
                chains.append(c)
    return ",".join(chains)


def _lines(lines_or_path):
    if isinstance(lines_or_path, (str, os.PathLike)):
        with open(lines_or_path, "r", errors="replace") as f:
            return f.readlines()
    return list(lines_or_path)


def _rows(lines):
    return [sp.parse_peek_line(l) for l in lines if l.startswith("[peek]")]


def _actor_pos(items, actor_static, vtable):
    """The actor base and its position. The base is sp_death_probe.actor_addr -- the same selection rule
    the ladder uses (the static's word 0, else the item whose word 0 is the vtable), given this revision's
    pair instead of r0001's, rather than a second copy of the rule here (Task 19 review F11)."""
    a = sp.actor_addr(items, actor_static, vtable)
    blk = sp.item_at(items, a) if a else None
    if blk and blk[0] == vtable and len(blk) >= 10:
        x, y, z = (sp.f32(blk[k]) for k in vc.ACTOR_POS_WORDS)
        if x or y or z:
            return a, (x, y, z)
    return a, None


# The at-rest window (s6_gamepad2, 2026-09-16): the root node holds the bind pose (11.484) for the first ~40 rows,
# then drops to the at-rest value (5.504) when gameplay starts, and later poses -- a muzzle-up hold, walking -- move it
# (5.031 in that run's tail). The console number research/17 measured is the at-rest value, so the scalar is read from
# the first REST_WINDOW_ROWS rows after the value first departs from its initial plateau by more than REST_DEPART,
# skipping REST_SETTLE_ROWS; a value that never departs (a short log) falls back to the median of what there is.
REST_DEPART = 0.5
REST_SETTLE_ROWS = 1
REST_WINDOW_ROWS = 6
# s6_water_state / s6_clut / s6_lum8 (2026-09-16): the root node can also DECAY over ~25 rows (11.48 -> 10.98 -> ...
# -> 5.5) rather than step, with stalls of up to eight identical rows on the way down (the 1 Hz sampler over a slow
# blend): a window opened at the departure read 10.407, one opened at the first quiet stretch read 10.732. The node
# decays DOWN to rest and only later holds raise it, so the rest value is the LOWEST sustained plateau after the
# departure: the REST_WINDOW_ROWS-row window with the smallest median among those whose spread is under
# REST_SETTLE_SPREAD. A series with no such window falls back to the departure-based window.
REST_SETTLE_SPREAD = 0.3


def _settled(values):
    if not values:
        return None
    first = values[0]
    depart = next((i for i, v in enumerate(values) if abs(v - first) > REST_DEPART), None)
    if depart is None:
        return float(statistics.median(values))
    best = None
    for i in range(depart, len(values) - REST_WINDOW_ROWS + 1):
        window = values[i: i + REST_WINDOW_ROWS]
        if max(window) - min(window) < REST_SETTLE_SPREAD:
            med = float(statistics.median(window))
            if best is None or med < best:
                best = med
    if best is not None:
        return best
    window = values[depart + REST_SETTLE_ROWS: depart + REST_SETTLE_ROWS + REST_WINDOW_ROWS]
    return float(statistics.median(window or values[depart:]))


def evaluate(lines_or_path, console_json, revision=None):
    """`revision` is which address column to read the rows with. Left out, it is the one the RUNTIME says
    it installed, off the same log (`log_revision`) -- not the one we meant to launch, and never r0001 by
    default: a log that will not say raises, and gate.probe_lines turns that into a NO-DATA the mission
    stage fails on."""
    console = load_console(console_json)
    lines = _lines(lines_or_path)
    revision = revision or log_revision(lines)
    actor_static = address("player_actor", revision)
    vtable = address("actor_vtable", revision)
    clock = address("guest_clock", revision)
    root_node_off = offset("root_node", revision)
    move_scale_off = offset("move_scale", revision)
    camera = address("camera_record", revision)
    rows = _rows(lines)
    root, scale, positions, orbit = [], [], [], []
    for items in rows:
        a, pos = _actor_pos(items, actor_static, vtable)
        if pos:
            clock_w = sp.word_at(items, clock)
            positions.append((pos, sp.f32(clock_w) if clock_w is not None else None))
            cam = sp.item_at(items, camera)
            if cam and len(cam) >= 3:
                cx, _cy, cz = (sp.f32(cam[k]) for k in range(3))
                if cx or cz:
                    orbit.append(math.dist((pos[0], pos[2]), (cx, cz)))
        if not a:
            continue
        node = sp.word_at(items, a + root_node_off)
        if node:
            w = sp.word_at(items, node + 4)
            if w is not None:
                root.append(sp.f32(w))
        w = sp.word_at(items, a + move_scale_off)
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
    # camera_orbit's console number is a code constant, not a row of guest_probe_console.json: the json is
    # a PINNED file (every gate compares its sha256), and a probe that exists to check an ADDRESS does not
    # need to move the standard every stage is measured against.
    checks = list(console.items()) + [("camera_orbit", {"console": CAMERA_ORBIT_U, "tol": CAMERA_ORBIT_TOL_U})]
    measured["camera_orbit"] = (float(statistics.median(orbit)) if orbit else None, len(orbit))
    for name, spec in checks:
        ours, n = measured.get(name, (None, 0))
        con, tol = spec["console"], spec["tol"]
        if ours is None:
            out.append(Result(name, None, con, tol, False,
                              f"NO-DATA (0 reads of {len(rows)} rows, {revision} addresses)"))
            continue
        ok = abs(ours - con) <= tol
        out.append(Result(name, ours, con, tol, ok,
                          f"ours={ours:.5g} console={con:.5g} tol={tol:g} reads={n} of {len(rows)} rows "
                          f"({revision} addresses)"))
    return out


def main(argv=None):
    # argparse rather than the hand-rolled flag scan this had: `--revision` last on the line used to read
    # argv[i + 1] unguarded and raise IndexError (Task 19 review F10).
    ap = argparse.ArgumentParser(prog="tools_py.parity.guest_probe",
                                 description=__doc__.splitlines()[0])
    ap.add_argument("run_log", help="the game's run log (the [peek] rows)")
    ap.add_argument("console_json", nargs="?", default=os.path.join("scripts", "parity", "guest_probe_console.json"))
    ap.add_argument("--revision", choices=sorted(REVISIONS),
                    help="the address column to read the rows with (default: what the run log says the "
                         "runtime installed)")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    results = evaluate(args.run_log, args.console_json, args.revision)
    for r in results:
        print(f"PROBE {r.name:15s} {'PASS' if r.ok else 'FAIL'} {r.detail}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
