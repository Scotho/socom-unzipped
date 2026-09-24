"""One home for the guest addresses the parity instruments reach into the game with, and for the rule
that decides which revision's column to use (Sprint 11 Task 19, review F3/F6/F10/F11).

Every one of these was written as an r0001 literal at the place that used it -- `0x416054` in the gate
probe's chain list, `0x408c58` and `0x4365c0` inside `scripts/parity/guest_probe_console.json`, the actor
vtable `0x6691a0` that `verdict_core` keys a peeked block on. On the r0004 build all four are somebody
else's memory: `logs/parity/gate/s11_r0004_reg2` read 0 rows of 479 and the mission lane failed
`GUEST PROBE FAILED: root_node_y` with all three probes NO-DATA.

`PROBE_ADDRESSES` is one column per revision and `address(name, revision)` is the only way in. A revision
the table has no column for raises; so does an image, or a run log, that will not say which revision it
is. **Falling back to r0001 without evidence is the one thing this must not do** -- an instrument reading
another build's addresses does not present as a bad address, it presents as silence, or worse, as a
number. The single relaxation is `launch_revision(..., default_ok=True)`, which the pin collector asks
for by name and which says so in what it returns (see below).

This module is a LEAF: it imports nothing from `tools_py.parity`, so `verdict_core` and `sp_death_probe`
can read their r0001 constants out of it (they are the ladder's instruments, and the ladder runs on the
r0001 build) while `guest_probe` takes a revision. Before the review there were three copies of these
four numbers and nothing that would notice them drifting apart.

HOW THE r0004 COLUMN WAS ESTABLISHED. `tools_py/data_via_twin.py` -- the same `data-via-twin` method
`runtime/socom2_addresses.h` records for its own DATA fields, now a tool with a test rather than a
procedure in prose. Its control is `cameraHolder 0x415ff0`, whose committed r0004 value `0x4429b0` it
reproduces from 60 unanimous twinned referrers. To regenerate this column, value for value:

    python -m tools_py.data_via_twin --column
"""
import os
import re

# name -> revision -> address.
#
#   camera_record  0x416054 -> 0x00442a14   data-via-twin, 1 twinned referrer; +0x2c9c0, the delta its
#                                           neighbour cameraHolder (0x415ff0, +0x64 below it) moves by
#                                           over 60 unanimous twins. The record's other two words,
#                                           0x416058 and 0x41605c, give 0x00442a18 and 0x00442a1c, and
#                                           0x416050 gives 0x00442a10 from 4 twins: the whole record
#                                           moves together. The gate checks it at RUN TIME too -- the
#                                           camera_orbit probe (guest_probe) measures its distance from
#                                           the actor, because this is the one entry whose being wrong
#                                           would otherwise have no symptom.
#   player_actor   0x408c58 -> 0x00435618   data-via-twin, 15 twinned of 16 sites, unanimous. And it is
#                                           the seed tools_py/address_matcher.py's own usage line
#                                           already carries (`--seed 0x408c58=0x435618`).
#   guest_clock    0x4365c0 -> 0x00442fd0   data-via-twin, 50 twinned of 57 sites, unanimous (+0xca10 --
#                                           a different region from the three above, and the same delta
#                                           0x437ce8 moves by, 29 twins unanimous).
#   actor_vtable   0x6691a0 -> 0x00668b20   not a referenced address but a VALUE in word 0 of the actor
#                                           block, so it is placed by its CONTENTS: of its twelve slots,
#                                           four hold functions match.json places by evidence, and
#                                           exactly one place in the whole r0004 image holds those four
#                                           translated pointers at those four offsets. Its delta -0x680
#                                           is the one ctorTableZsealBegin (0x6690e0 -> 0x668a60) moves
#                                           by.
PROBE_ADDRESSES = {
    "camera_record": {"r0001": 0x00416054, "r0004": 0x00442A14},
    "player_actor": {"r0001": 0x00408C58, "r0004": 0x00435618},
    "guest_clock": {"r0001": 0x004365C0, "r0004": 0x00442FD0},
    "actor_vtable": {"r0001": 0x006691A0, "r0004": 0x00668B20},
}
# Derived, never hand-kept: a fifth column added above must not leave an error message naming four
# (review F10 -- the old hand-written tuple would have printed a list omitting the revision it had just
# accepted, and the suite iterated the same tuple, so nothing would have noticed).
REVISIONS = tuple(sorted({r for col in PROBE_ADDRESSES.values() for r in col}))


def address(name, revision):
    """This revision's address for one probe input. A name or a revision the table does not carry raises,
    naming what it does have -- never the other column's number."""
    col = PROBE_ADDRESSES.get(name)
    if col is None:
        raise ValueError("guest addresses: no probe address called %r (have: %s)"
                         % (name, ", ".join(sorted(PROBE_ADDRESSES))))
    if revision not in col:
        raise ValueError("guest addresses: no %s address for revision %r -- this table has columns for "
                         "%s. Reading another revision's address is the defect this table exists to stop."
                         % (name, revision, ", ".join(sorted(col))))
    return col[revision]


# The build banner in the game image ("SOCOM 2 r0001 17:22:21 Oct 11 2003"): the same evidence
# socom2_addresses.h's selectFromImage() picks its column by, read here off the file instead of out of
# guest memory, because PS2X_PEEK has to be built BEFORE the launch. It occurs exactly once in each image.
BANNER_RE = re.compile(rb"SOCOM 2 (r\d{4}) ")
# ... and what the runtime says it INSTALLED, once it has run. Two wordings, and the difference matters:
# selectFromImage() prints "the image names itself rNNNN" only on the branch where a row's own stamp named
# that row's revision, and prints "... -- using rNNNN, every override address is an rNNNN address" on the
# two fallback branches (no row named itself; the version string names no revision). Both state the column
# the runtime installed, which is what a reader of the run needs; only the first is the image naming
# itself. `log_revision` accepts either and says which -- s11_open_gate reached the gate on the fallback
# branch, and a re-score of it must not be a failure (review F1).
LOG_NAMES_ITSELF_RE = re.compile(r"address table: the image names itself (r\d{4})")
LOG_USING_RE = re.compile(r"address table: .*-- using (r\d{4})")
GAME_ELF_ENV = "SOCOM_GAME_ELF"
DEFAULT_GAME_ELF = os.path.join("game", "disc", "socom2_game.elf")


# The struct field displacements the probes read inside the actor -- ALSO one column per revision
# (Sprint 11 Task 19, the move_scale lane). The r0001 column's `a relink does not move a struct field` was
# half true: r0004 is a rebuild, not a relink, and the actor object gained a word at +0x1334, so every
# field above it moved up by four.
#
#   root_node  0x2e8 -> 0x2e8   unchanged. 31 instructions with this displacement sit in functions
#                               match.json twins by evidence, and all 31 twins read 0x2e8. (The actor
#                               position words +0x1c/+0x20/+0x24 are the same story, 2755 twinned uses.)
#   move_scale 0x1368 -> 0x136c MOVED. r0001 has six register-relative uses of 0x1368 -- three `lwc1
#                               $f1, 0x1368($s2)` in FUN_00551ec0 (MoveScale multiplying the velocity
#                               triple at +0x23c/+0x240/+0x244), two `swc1 ..., 0x1368($a0)` in the
#                               clamping setter FUN_00553dc0, one `sw $v1, 0x1368($s0)` in the
#                               constructor FUN_00553ea0 -- and the r0004 image has exactly six uses of
#                               0x136c, in the three twin functions, same opcodes, same registers, and
#                               NONE of 0x1368 on those registers. Aligned instruction for instruction,
#                               FUN_00551ec0's twin agrees on 146 of 149 register-relative displacements
#                               and the three that differ are these. The r0004 constructor carries one
#                               extra store the r0001 one does not, `sw $zero, 0x1334($s0)`, immediately
#                               before the MoveScale store: that is the word that pushed the field up.
#
# match.json is SILENT on this: FUN_00551ec0, FUN_00553dc0 and FUN_00553ea0 are all `unresolved` there --
# a body whose displacements moved is exactly a body the matcher will not place -- which is why a
# twin-only scan reported "0x1368 has one twinned use site" and saw nothing.
#   actor_pos  0x1c  -> 0x1c    the position triple's first word, +0x1c/+0x20/+0x24 (verdict_core reads
#                               it as WORD INDICES 7/8/9 and derives them from this). 2755 twinned uses,
#                               all unchanged -- the same evidence root_node rests on.
PROBE_OFFSETS = {
    "root_node": {"r0001": 0x2E8, "r0004": 0x2E8},
    "move_scale": {"r0001": 0x1368, "r0004": 0x136C},
    "actor_pos": {"r0001": 0x1C, "r0004": 0x1C},
}


def offset(name, revision):
    """This revision's displacement for one actor field. Same contract as `address`: a name or a revision
    the table does not carry raises, and it never answers the other column's number. A field offset is
    data about the build, not a constant -- reading r0001's 0x1368 on r0004 does not present as an error,
    it presents as 0.0 (s11_r0004_probe1: move_scale ours=0 console=1, with the rest of the chain
    passing)."""
    col = PROBE_OFFSETS.get(name)
    if col is None:
        raise ValueError("guest_probe: no field offset called %r (have: %s)"
                         % (name, ", ".join(sorted(PROBE_OFFSETS))))
    if revision not in col:
        raise ValueError("guest_probe: no %s offset for revision %r -- this table has columns for %s. "
                         "Reading another revision's layout is the defect this table exists to stop."
                         % (name, revision, ", ".join(sorted(col))))
    return col[revision]

# The ladder's OTHER actor field offsets (sp_death_probe's HEALTH_OFFSET, ALIVE_OFFSET,
# DEATH_TIME_OFFSET, ANGVEL_OFFSET, verdict_core's ACTOR_STAMP_OFFSET) are deliberately NOT here: they are
# r0001 literals used only by the online ladder, which runs on the r0001 build, and no r0004 value for any
# of them has been established -- a column filled by assumption is the defect this table exists to stop.
# They join when somebody measures them, the way move_scale was measured.


_HEX_RE = re.compile(r"0[xX][0-9a-fA-F]+")
# actor_vtable is a VALUE read out of a row, never a chain, so it is not evidence about a PS2X_PEEK.
_CHAIN_NAMES = tuple(n for n in PROBE_ADDRESSES if n != "actor_vtable")


def revision_of_peek_spec(spec):
    """Which address column a `PS2X_PEEK` string is written in.

    This is the STRONGEST evidence there is about an archived run: the chains in PS2X_PEEK are literally
    the addresses the runtime printed its `[peek]` rows under, so they say how to read those rows -- more
    directly than the image's banner (which says what was launched) or the runtime's log line (which says
    which overrides were installed). Every gate stamp on disk records it, including the ones from before
    the runtime printed a revision line at all (review F1).

    Exactly one revision's probe addresses must appear, or it raises. An operator's wider spec is fine: it
    only has to carry this revision's probe addresses and none of another's.
    """
    lits = {int(m.group(0), 16) for m in _HEX_RE.finditer(spec)}
    found = sorted({rev for name in _CHAIN_NAMES for rev, a in PROBE_ADDRESSES[name].items() if a in lits})
    if len(found) != 1:
        raise ValueError("guest addresses: PS2X_PEEK %r carries the probe addresses of %s -- it does not "
                         "say which single column its rows are in"
                         % (spec, ("no revision" if not found else " and ".join(found))))
    return found[0]


def revision_of_image(path):
    """The revision of a game image, from its build banner. No banner, or more than one revision's worth,
    raises: an image that will not name itself is not an r0001 image."""
    with open(path, "rb") as f:
        found = sorted({m.group(1).decode() for m in BANNER_RE.finditer(f.read())})
    if len(found) != 1:
        raise ValueError("guest addresses: %s carries no single build banner (found %s) -- it cannot say "
                         "which revision's addresses to read" % (path, found or "none"))
    return found[0]


def launch_revision(env=None, default_ok=False):
    """The revision of the image a launch would use: `$SOCOM_GAME_ELF`, else `game/disc/socom2_game.elf`.

    The image is read, so the answer is always evidence -- except for one case, which the caller has to
    ask for by name. When the DEFAULT path is absent (`game/` is git-ignored: a bare clone has no image,
    and no launch to make either), `default_ok=True` answers `"r0001"` from the path's own name and
    `default_ok=False` raises. `gate.collect_pins` passes True, because hashing the launch environment on
    a checkout with no disc assets must work and cannot mislabel a launch that cannot happen; `run_gate`
    passes False, because a launch has an image. Review F3: the relaxation is now visible at the call
    site instead of hidden in here.
    """
    env = os.environ if env is None else env
    named = env.get(GAME_ELF_ENV)
    path = named or DEFAULT_GAME_ELF
    if not os.path.isfile(path):
        if named:
            raise ValueError("guest addresses: %s names %s, which is not a file -- the probe cannot tell "
                             "which revision's addresses to read" % (GAME_ELF_ENV, named))
        if default_ok:
            return "r0001"
        raise ValueError("guest addresses: %s is not there and %s is unset, so nothing has said which "
                         "revision this is" % (DEFAULT_GAME_ELF, GAME_ELF_ENV))
    return revision_of_image(path)


def log_revision(lines):
    """(revision, how) -- the address column the runtime says it INSTALLED, off its own run log. `how` is
    `"names itself"` when the image named its own revision, `"fallback"` when the runtime had to fall back
    and said which column it used instead. A log that says neither raises: the probe does not guess, and
    it never assumes r0001."""
    for line in lines:
        m = LOG_NAMES_ITSELF_RE.search(line)
        if m:
            return m.group(1), "names itself"
    for line in lines:
        m = LOG_USING_RE.search(line)
        if m:
            return m.group(1), "fallback"
    raise ValueError("guest addresses: the run log never says which revision the runtime installed "
                     "(no '[socom2] address table: ...' line), so the probe cannot know which column to "
                     "read -- pass one explicitly")
