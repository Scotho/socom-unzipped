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
the mission lane failed `GUEST PROBE FAILED: root_node_y` with all three probes NO-DATA. PROBE_ADDRESSES below is
one column per revision and `address(name, revision)` is the only way in; a revision the table has no column for
raises, and so does an image or a run log that will not say which revision it is. Falling back to r0001 is the one
thing this must never do: an instrument reading another build's addresses does not present as a bad address, it
presents as silence -- or, worse, as a number."""
import json
import math
import os
import re
import statistics
import sys
from collections import namedtuple

from tools_py.parity import sp_death_probe as sp
from tools_py.parity import verdict_core as vc

Result = namedtuple("Result", "name ours console tol ok detail")

# research/25 §1.1 measured teleports as steps > 30 units between 4 Hz rows, i.e. > 120 u/s; a run reads ~40 u/s
# (s6_probe's 8 s forward hold: 36-45 units per 1 s row). The row period comes from the guest clock (r0001
# 0x4365c0, float seconds) when the peek carries it, else DEFAULT_ROW_PERIOD_S -- the mission stage's
# PS2X_PC_SAMPLER=1.
TELEPORT_SPEED_UPS = 120.0
DEFAULT_ROW_PERIOD_S = 1.0
ROOT_NODE_OFF = 0x2E8
MOVE_SCALE_OFF = 0x1368

# The four guest addresses the probes reach in with, one column per revision.
#
# The r0004 column was established the way runtime/socom2_addresses.h's data fields were -- `data-via-twin`:
# every r0001 function that materialises the address with a lui/lo pair, kept when match.json
# (game/r0004/match.json) places its r0004 twin by evidence (identity/exact/hash+callees/relinked-body), read at
# the SAME instruction offset in the twin's body. The control is cameraHolder 0x415ff0, whose committed r0004
# value 0x4429b0 the same procedure reproduces from 60 twinned referrers, unanimously.
#
#   camera_record  0x416054 -> 0x00442a14   1 twinned referrer; +0x2c9c0, the delta its neighbour cameraHolder
#                                           (0x415ff0, +0x64 below it) moves by over 60 unanimous twins. The
#                                           record's other two words, 0x416058 and 0x41605c, give 0x00442a18 and
#                                           0x00442a1c: the three the chain reads move together.
#   player_actor   0x408c58 -> 0x00435618   15 twinned referrers of 16 sites, unanimous. Independently, it is
#                                           the seed tools_py/address_matcher.py's own usage line carries
#                                           (`--seed 0x408c58=0x435618`).
#   guest_clock    0x4365c0 -> 0x00442fd0   50 twinned referrers of 57 sites, unanimous (+0xca10 -- a different
#                                           region from the three above, and the same delta 0x437ce8 moves by).
#   actor_vtable   0x6691a0 -> 0x00668b20   not a referenced address but a VALUE in word 0 of the actor block,
#                                           so it is placed by its CONTENTS: of its twelve slots, four are
#                                           functions match.json places by evidence, and exactly one place in
#                                           the whole r0004 image holds those four translated pointers at those
#                                           four offsets. Its delta, -0x680, is the one ctorTableZsealBegin
#                                           (0x6690e0 -> 0x668a60) moves by.
REVISIONS = ("r0001", "r0004")
PROBE_ADDRESSES = {
    "camera_record": {"r0001": 0x00416054, "r0004": 0x00442A14},
    "player_actor": {"r0001": 0x00408C58, "r0004": 0x00435618},
    "guest_clock": {"r0001": 0x004365C0, "r0004": 0x00442FD0},
    "actor_vtable": {"r0001": 0x006691A0, "r0004": 0x00668B20},
}


def address(name, revision):
    """This revision's address for one probe input. A name or a revision the table does not carry is a
    ValueError naming what it does have -- never the other column's number."""
    col = PROBE_ADDRESSES.get(name)
    if col is None:
        raise ValueError("guest_probe: no probe address called %r (have: %s)"
                         % (name, ", ".join(sorted(PROBE_ADDRESSES))))
    if revision not in col:
        raise ValueError("guest_probe: no %s address for revision %r -- this table has columns for %s. "
                         "Reading another revision's address is the defect this table exists to stop."
                         % (name, revision, ", ".join(REVISIONS)))
    return col[revision]


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


_HEX_RE = re.compile(r"0[xX][0-9a-fA-F]+")
_BY_R0001 = {col["r0001"]: name for name, col in PROBE_ADDRESSES.items()}


def translate_chain(chain, revision):
    """One PS2X_PEEK chain, with every literal that is an r0001 PROBE ADDRESS moved to `revision`'s column.
    A hex literal that is not one of those is left exactly as it is -- `*0x408c58+0x2e8` carries a field
    offset inside the actor, and a relink does not move a struct field."""
    return _HEX_RE.sub(lambda m: ("0x%x" % address(_BY_R0001[int(m.group(0), 16)], revision))
                       if int(m.group(0), 16) in _BY_R0001 else m.group(0), chain)


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


def _actor_addr(items, actor_static, vtable):
    """The actor base: this revision's actor static, word 0 (robust when the block's own word 0 changes at
    death), else the item whose word 0 is this revision's actor vtable. sp_death_probe.actor_addr does the
    same thing on r0001's two literals -- the online ladder's build -- which is why this one is here."""
    s = sp.item_at(items, actor_static)
    if s and s[0]:
        return s[0]
    return next((a for a, w in items if w and w[0] == vtable), None)


def _actor_pos(items, actor_static, vtable):
    a = _actor_addr(items, actor_static, vtable)
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
    rows = _rows(lines)
    root, scale, positions = [], [], []
    for items in rows:
        a, pos = _actor_pos(items, actor_static, vtable)
        if pos:
            clock_w = sp.word_at(items, clock)
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
            out.append(Result(name, None, con, tol, False,
                              f"NO-DATA (0 reads of {len(rows)} rows, {revision} addresses)"))
            continue
        ok = abs(ours - con) <= tol
        out.append(Result(name, ours, con, tol, ok,
                          f"ours={ours:.5g} console={con:.5g} tol={tol:g} reads={n} of {len(rows)} rows "
                          f"({revision} addresses)"))
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    revision = None
    if "--revision" in argv:
        i = argv.index("--revision")
        revision = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    console_json = argv[1] if len(argv) > 1 else os.path.join("scripts", "parity", "guest_probe_console.json")
    results = evaluate(argv[0], console_json, revision)
    for r in results:
        print(f"PROBE {r.name:15s} {'PASS' if r.ok else 'FAIL'} {r.detail}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
