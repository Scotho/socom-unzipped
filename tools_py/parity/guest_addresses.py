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
import sys

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
# ... and the same derivation once the online and trace tables below exist: a column added to any of the
# three must not leave the others' callers offering a shorter list (review F10, the same trap).


# ---------------------------------------------------------------------------
# THE ONLINE HARNESS'S INSTRUMENTS (Sprint 11 Task 19, the r0004 online lane).
#
# `scripts/parity/env.sh` carried these as r0001 literals -- one PS2X_PEEK string of 573 characters and
# one PS2X_CALL_TRACE of two addresses -- and EVERY online script sources it: the ladder, the mixed-match
# legs, the control round. `s11_r0004_round1` is what that costs. Two r0004 clients logged in against the
# hosted Horizon, one hosted Frostfire, the other found it and joined, both went READY and played the round
# to its clock (1511 and 1491 in-game `[peek]` rows, both HUD clocks reading 05:29 in the hold captures) --
# and the round scored `RESULT NO-DATA`, because every chain in the spec pointed at somebody else's memory
# and the call trace never fired. A wrong address here does not present as an error. It presents as silence,
# or as a number.
#
# Every r0004 value below was DERIVED, not assumed: `python -m tools_py.data_via_twin <addr>`, the lui/lo
# twin scan, with votes counted only from functions `game/r0004/match.json` places by evidence
# (`identity`/`exact`/`hash+callees`/`relinked-body`; `seed+delta` says where to look, not what was found).
# `tools_py/tests/test_data_via_twin.py` re-derives every one of them from the two images.
#
#   net_game            0x437ce8 -> 0x004446f8   CZNetGame and its valves. 151 materialising sites, 29 of
#                                                them evidence-twinned, UNANIMOUS. (+0xca10 -- the same
#                                                delta guest_clock moves by, which is how the header's
#                                                comment already knew this one's shape.) 22 distinct
#                                                referrer FUNCTIONS -- the unit the rule below counts.
#   mission_abort_valve 0x43668c -> 0x0044309c   the pause-menu abort valve (research/21 R5). 5 sites, 5
#                                                twinned in 4 functions, unanimous.
#   mp_flag_word        0x45a0c0 -> 0x0045d480   the word whose byte 1 is DAT_0045a0c1, R6's snap-back
#                                                context. 344 sites, 175 twinned in 98 functions,
#                                                unanimous -- the widest evidence in this table.
#   input_enable        0x3df1b0 -> 0x0040a378   DAT_003df1b0, "player input enabled" (research/21 R4).
#                                                6 sites, 5 twinned in 4 functions, unanimous.
#   r7_flag             0x45a1c8 -> 0x0045d58c   research/21 R7 (its byte at 0x45a1ca). 3 sites and only
#                                                **ONE** evidence-twinned referrer function: see
#                                                UNCONFIRMED below.
#   clock_string        0x408f10 -> 0x004358d0   the HUD round-clock string "MM:SS" (research/19 F2).
#                                                2 sites, 2 twinned, unanimous -- but both inside ONE
#                                                function (FUN_001f6b60 forms it twice), so by the rule
#                                                below it is a single referrer and it is CORROBORATED,
#                                                not confirmed by count. Review F3.
ONLINE_ADDRESSES = {
    "net_game": {"r0001": 0x00437CE8, "r0004": 0x004446F8},
    "mission_abort_valve": {"r0001": 0x0043668C, "r0004": 0x0044309C},
    "mp_flag_word": {"r0001": 0x0045A0C0, "r0004": 0x0045D480},
    "input_enable": {"r0001": 0x003DF1B0, "r0004": 0x0040A378},
    "r7_flag": {"r0001": 0x0045A1C8, "r0004": 0x0045D58C},
    "clock_string": {"r0001": 0x00408F10, "r0004": 0x004358D0},
}

# THE CALL TRACE's two functions. Both were established by reading the two bodies, because neither could
# come from `match.json` alone:
#
#   move_scale_setter 0x553dc0 -> 0x005590e0   `SetMoveScale(actor*, float)`, sixteen instructions.
#                                              `match.json` marks r0001's `FUN_00553dc0` **`unresolved`** --
#                                              a body whose displacements moved is exactly a body the
#                                              matcher will not place. The masked-body evidence is
#                                              `task-19-move-report.md` ("r0001 0x00553dc0  r0004
#                                              0x005590e0"), and it reproduces word for word: the two
#                                              bodies are the SAME sixteen instructions and differ in
#                                              exactly two half-words, the `swc1` displacements
#                                              0x1368 -> 0x136c (PROBE_OFFSETS["move_scale"], above).
#   net_idle          0x30cd80 -> 0x0032a2b0   a two-word THUNK, `j <target>; nop`, which is why
#                                              `match.json` only ever had it as `seed+delta` (it calls it
#                                              `thunk_FUN_0030be80`). Confirmed here by its TARGET instead:
#                                              r0001's thunk jumps to 0x0030be80, r0004's to 0x00329230,
#                                              and `match.json` places 0x0030be80 -> 0x00329230
#                                              `relinked-body`, `tie: unique` -- accepted evidence. And the
#                                              thunk is unique on both sides: exactly one `j 0x30be80; nop`
#                                              in the whole r0001 image and exactly one `j 0x329230; nop`
#                                              in r0004, so there is no second thunk the trace could have
#                                              been meant to sit on.
TRACE_ADDRESSES = {
    "move_scale_setter": {"r0001": 0x00553DC0, "r0004": 0x005590E0},
    "net_idle": {"r0001": 0x0030CD80, "r0004": 0x0032A2B0},
}

# Values that rest on ONE evidence-twinned referrer FUNCTION. They are carried so the instrument keeps
# peeking what it has always peeked, and they are named here so that nothing SCORES on them: a single
# referrer is a claim, not the unanimity the rest of this table is built on.
# `tools_py/tests/test_online_instruments.py` holds the rule -- no scorer may key a verdict on one of
# these, by literal or by name -- and the way out is more evidence, not a promotion by silence.
#
# THE UNIT IS THE REFERRER FUNCTION, NOT THE SITE (review F3). One function that happens to materialise
# an address twice votes once: if its twinning were wrong, both of its "votes" would be wrong together,
# which is precisely the failure the unanimity argument is supposed to exclude. `clock_string` read as
# "2 sites, 2 twinned, unanimous" under the old site count and is one function.
UNCONFIRMED = frozenset({"r7_flag"})

# ... and the other side of that rule. A value with ONE twinned referrer function is unconfirmed UNLESS
# something else stands behind it, and "something else" has to be written down or it is just a habit.
CORROBORATED = {
    "camera_record": "one twinned referrer of its own, but its delta +0x2c9c0 is the one its neighbour "
                     "cameraHolder (0x415ff0, 0x64 below it) moves by over 60 unanimous twins; the "
                     "record's other three words (0x416050/58/5c) give the matching r0004 words, 0x416050 "
                     "from 4 twins; and the gate re-checks it at RUN TIME -- guest_probe's camera_orbit "
                     "measures its distance from the actor, which is why this is the one entry whose "
                     "being wrong would otherwise have no symptom",
    "clock_string": "two materialising sites, both in FUN_001f6b60, so one referrer function -- but the "
                    "value it names is ASCII and self-checking, and it was checked at RUN TIME across a "
                    "whole r0004 round: `s11_r0004_round2c` read '05:29', '04:16', '03:20', '02:24', "
                    "'01:27', '00:31' and the end-of-round '00:01'->'00:00' out of this address over "
                    "~2600 rows on each side, printable and counting down in step on both clients. A "
                    "wrong address here does not produce a plausible clock; it produces NoData or "
                    "unprintable bytes. Same kind of corroboration as camera_record's: a run, not a count",
}

REVISIONS = tuple(sorted({r for table in (PROBE_ADDRESSES, ONLINE_ADDRESSES, TRACE_ADDRESSES)
                          for col in table.values() for r in col}))


# ---------------------------------------------------------------------------
# THE OTHER INSTRUMENTS' STATICS (Sprint 13 Task H6, audit harness-tools H20-H23).
#
# The audio poll, the motion-pack check, cam_poll's default spec and verdict_core's valve pointer mode
# carried these as r0001 literals where they were used, outside this table, and nothing refused them on an
# r0004 run (KNOWN.md §4's hazard exactly: the numbers come back, they are just somebody else's memory).
# `tools_py/tests/test_no_bare_guest_addresses.py` now refuses a new one anywhere under tools_py/parity.
#
# UNLIKE THE THREE TABLES ABOVE, A COLUMN HERE MAY BE MISSING. A value `data_via_twin` cannot place is not
# written down at all -- the r0004 cell is ABSENT, `address()` raises for it, and UNPLACED says
# why and what would settle it.
#
# UNPLACED IS NOT UNCONFIRMED. `UNCONFIRMED` (above) is a set of names whose value IS carried -- it rests
# on one twinned referrer, the instrument keeps peeking it, and no scorer may key a verdict on it.
# `UNPLACED` is a set of (name, revision) cells with NO value at all: nothing reads them, `address()`
# refuses them, and the reason is what it prints. A guessed number (the neighbour's delta, the object base plus r0001's
# displacement) is exactly what this table exists to keep out. So these names are NOT in `all_names()`,
# which promises every revision's column for every name (the online harness's tests iterate it on both
# columns); `instrument_names()` lists them.
#
# Every r0004 value below is `python -m tools_py.data_via_twin <r0001 addr>` against game/r0004/match.json
# (see the header): unanimous votes of evidence-twinned referrer FUNCTIONS, none split.
#
#   cue_route         0x49e150 -> 0x004a1510  11 sites, 8 twinned in 6 functions, unanimous (+0x33c0).
#   cue_manager_ptr   0x49e158 -> 0x004a1518  9 sites, 8 twinned in 4 functions, unanimous (+0x33c0).
#   music_globals     0x48e080 -> 0x00491440  26 sites, 26 twinned in 7 functions, unanimous (+0x33c0). The
#                                             block's other words move with it: 0x48e088 -> 0x491448 (19
#                                             twinned, 7 fns), 0x48e090 -> 0x491450 (14, 4), 0x48e0a0 ->
#                                             0x491460 (13, 4) -- the 14-word block read as one is whole.
#   music_off         0x3e0080 -> 0x0040b250  4 sites, 4 twinned in 4 functions, unanimous (+0x2b1d0 -- a
#                                             different region's delta from the block above).
#   music_tables      0x48e010 -> 0x004913d0  6 sites, 5 twinned in 4 functions, unanimous (+0x33c0); its
#                                             weight half 0x48e050 -> 0x491410 (8 twinned, 5 fns) agrees.
#   camera_ptr        0x488de8 -> 0x0048c1b8  14 sites, 14 twinned in 11 functions, unanimous (+0x33d0).
#                                             cam_poll's default spec reads 96 words from +0x120 of the
#                                             object it points at: that is a WINDOW, not one field, and
#                                             the camera object's layout on r0004 is not established.
#
# ... and the ones it CANNOT place, whose r0004 cell is absent (UNPLACED):
#
#   vagstore_base     0x48dc48                0 materialising sites: the game reaches it as +0x18 inside
#                                             the VAGSTORE object 0x48dc30, which the tool DOES place
#                                             (0x48dc30 -> 0x490ff0, 6 twinned in 5 functions, unanimous).
#                                             0x490ff0 + 0x18 is the obvious candidate and it is r0001's
#                                             displacement assumed, so it is not written here.
#   motion_pack_ptr   0x415e08                1 site, 0 evidence-twinned. It sits at +0xc8 of the pack
#   motion_pack_size  0x415e0c                object copy 0x415d40 (-> 0x442700, 4 twinned in 4 fns), so
#                                             base + 0xc8 / + 0xcc would be the candidates -- again a
#                                             displacement assumed, not a value placed.
#   valve_name.*      ten valve NAME POINTERS verdict_core's pointer mode compares against (research/21
#                     §2.1, OURS only: a PCSX2 run's differ). 0 sites each: they are above every PT_LOAD
#                     segment of the r0001 image (the last ends at 0x686f80), i.e. the heap, so no twin
#                     scan can place them and a different build's heap need not agree. The valves are
#                     identified by NAME BYTES everywhere that scores (verdict_core.row_valve); the pointer
#                     mode is r0001-only and refuses on anything else.
INSTRUMENT_ADDRESSES = {
    "cue_route": {"r0001": 0x0049E150, "r0004": 0x004A1510},
    "cue_manager_ptr": {"r0001": 0x0049E158, "r0004": 0x004A1518},
    "music_globals": {"r0001": 0x0048E080, "r0004": 0x00491440},
    "music_off": {"r0001": 0x003E0080, "r0004": 0x0040B250},
    "music_tables": {"r0001": 0x0048E010, "r0004": 0x004913D0},
    "vagstore_base": {"r0001": 0x0048DC48},
    "motion_pack_ptr": {"r0001": 0x00415E08},
    "motion_pack_size": {"r0001": 0x00415E0C},
    "camera_ptr": {"r0001": 0x00488DE8, "r0004": 0x0048C1B8},
    "valve_name.mp_round_count": {"r0001": 0x006B7F30},
    "valve_name.mp_game_over": {"r0001": 0x006B7F20},
    "valve_name.player_team": {"r0001": 0x006CC9FC},
    "valve_name.mp_major_game_state": {"r0001": 0x00694AE0},
    "valve_name.mp_minor_game_state": {"r0001": 0x00694B08},
    "valve_name.late_joiner": {"r0001": 0x006CCA14},
    "valve_name.aiteam_00": {"r0001": 0x006CCAD4},
    "valve_name.aiteam_08": {"r0001": 0x006CCAEC},
    "valve_name.total_mp_kills": {"r0001": 0x006B7F70},
    "valve_name.mission_abort": {"r0001": 0x006B7FB0},
}
_VALVE_NAME_WHY = ("a heap pointer (above every PT_LOAD segment of the image), so data_via_twin has no "
                   "materialising site to twin; verdict_core's pointer mode is r0001-only -- identify the "
                   "valve by its name bytes (verdict_core.row_valve) instead")
# (name, revision) -> why that cell is absent, and what would fill it. `address()` puts this in its refusal.
# Not UNCONFIRMED (a carried value on thin evidence): an UNPLACED cell has no value to carry.
UNPLACED = {
    ("vagstore_base", "r0004"): "data_via_twin: 0 materialising sites (the game reaches it as +0x18 of "
                                "the VAGSTORE object 0x48dc30 -> 0x490ff0, which IS placed); the r0004 "
                                "displacement of that field is not established -- read the twin of "
                                "FUN_0034d480's store accessors to settle it",
    ("motion_pack_ptr", "r0004"): "data_via_twin: 1 materialising site, 0 evidence-twinned referrers "
                                  "(UNRESOLVED); +0xc8 of the pack object 0x415d40 -> 0x442700, whose "
                                  "r0004 layout is not established",
    ("motion_pack_size", "r0004"): "data_via_twin: 1 materialising site, 0 evidence-twinned referrers "
                                   "(UNRESOLVED); +0xcc of the pack object 0x415d40 -> 0x442700, whose "
                                   "r0004 layout is not established",
}
UNPLACED.update({(n, "r0004"): _VALVE_NAME_WHY for n in INSTRUMENT_ADDRESSES
                            if n.startswith("valve_name.")})


def _column_of(name):
    for table in (PROBE_ADDRESSES, ONLINE_ADDRESSES, TRACE_ADDRESSES, INSTRUMENT_ADDRESSES):
        if name in table:
            return table[name]
    return None


def all_names():
    """Every name of the three online/probe tables -- each has EVERY revision's column (the harness's
    tests iterate it on both). `instrument_names()` are the rest, whose columns may be absent."""
    return sorted(set(PROBE_ADDRESSES) | set(ONLINE_ADDRESSES) | set(TRACE_ADDRESSES))


def instrument_names():
    """The names of INSTRUMENT_ADDRESSES: the audio poll, the motion-pack check, cam_poll, the valve
    name pointers. A column here may be absent -- see UNPLACED."""
    return sorted(INSTRUMENT_ADDRESSES)


def address(name, revision):
    """This revision's address for one probe input. A name or a revision the table does not carry raises,
    naming what it does have -- never the other column's number. For a cell the table leaves absent on
    purpose, the refusal says why (UNPLACED)."""
    col = _column_of(name)
    if col is None:
        raise ValueError("guest addresses: no probe address called %r (have: %s)"
                         % (name, ", ".join(all_names() + instrument_names())))
    if revision not in col:
        why = UNPLACED.get((name, revision))
        raise ValueError("guest addresses: no %s address for revision %r -- this table has columns for "
                         "%s.%s Reading another revision's address is the defect this table exists to stop."
                         % (name, revision, ", ".join(sorted(col)),
                            (" UNPLACED on %s: %s." % (revision, why)) if why else ""))
    return col[revision]


def addresses(names, revision):
    """{name: address} for several names on one revision, refusing ALL of them if ANY is absent -- an
    instrument that reads a block of statics must not come up with some of them read in the wrong build.
    The refusal lists every absent name with its reason."""
    out, missing = {}, []
    for n in names:
        try:
            out[n] = address(n, revision)
        except ValueError as e:
            missing.append(str(e))
    if missing:
        raise ValueError("guest addresses: refusing %s -- %d of %d addresses have no %s column:\n  %s"
                         % (revision, len(missing), len(names), revision, "\n  ".join(missing)))
    return out


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

# What each PROBE_OFFSETS number IS, per revision (Sprint 12 Task 7, spec Goal 5, research/50 §4a). A name
# here is a SOCOM 1 field (the demo's DWARF1 layout, `Type::field`) that SOCOM II's OWN access pattern has
# confirmed at this offset, by research/50 §4's rule: two twin functions agree on the SOCOM 1 -> SOCOM II
# displacement, or at least half of the >= 2 demo neighbours share the shift. A SOCOM 1 offset alone is a
# hypothesis, never a value (R262: the actor's constructor moves all 133 demo fields it stores), so
# `socom1_offset` is provenance, and a named entry's number satisfies socom1_offset + shift == the value.
# Only `confirmed` and `shifted by N` carry a name; a `single-twin` field is a `candidate`, a
# `contradicted` one records what `contradicts` it, and every other entry is UNNAMED with the note's
# reason. The r0004 entries rest on the r0001 verdict plus research/50 D's r0001 -> r0004 follow of every
# use. These names are documentation for the reader, NEVER read by the harness: offset() answers from
# PROBE_OFFSETS alone, and a name changes no probe (the test pins both).
UNNAMED = "unnamed"
OFFSET_NAMES = {
    "root_node": {
        "r0001": {"name": "CZSealBody::m_root", "verdict": "shifted by +0x7c", "socom1_offset": 0x26C,
                  "note": "research/50 §4a",
                  "evidence": "the actor constructor's run of 25 body-part pointer stores (demo 0x26c m_root "
                              "... 0x2cc m_rtoe) lands at +0x7c; 8 of 11 demo neighbours share the shift"},
        "r0004": {"name": "CZSealBody::m_root", "verdict": "shifted by +0x7c", "socom1_offset": 0x26C,
                  "note": "research/50 §4a",
                  "evidence": "r0001's verdict, and all 26 twinned r0001 uses read 0x2e8 in r0004 (18 fns): "
                              "below the word r0004 inserted at 0x1334"},
    },
    "move_scale": {
        "r0001": {"name": UNNAMED, "verdict": "unknown", "socom1_offset": None, "note": "research/50 §4a",
                  "reason": "no demo twin: FUN_00551ec0, FUN_00553dc0 and FUN_00553ea0 have none (best "
                            "ratio 0.47) and the constructor has no aligned store; the position alone "
                            "suggests CZSealBody::m_jumpImpulse, which a clamped multiplier of the throttle "
                            "triple is not"},
        "r0004": {"name": UNNAMED, "verdict": "unknown", "socom1_offset": None, "note": "research/50 §4a",
                  "reason": "no demo twin (as r0001); the value is r0001's field moved +4 by the word r0004 "
                            "inserted at 0x1334 (all 6 uses -> 0x136c, KNOWN §4)"},
    },
    "actor_pos": {
        "r0001": {"name": UNNAMED, "verdict": "contradicted", "socom1_offset": None, "note": "research/50 §4a",
                  "contradicts": "CEntity::m_node, the demo field at 0x1c, which r0001 holds at 0x28 (8 "
                                 "uses); r0001's 0x1c-0x27 is 12 bytes SOCOM 1 does not have",
                  "reason": "new in SOCOM II: SOCOM 1 read the position through m_node"},
        "r0004": {"name": UNNAMED, "verdict": "contradicted", "socom1_offset": None, "note": "research/50 §4a",
                  "contradicts": "CEntity::m_node, as r0001 (738 uses of 0x1c unchanged in r0004, 393 fns)",
                  "reason": "new in SOCOM II: SOCOM 1 read the position through m_node"},
    },
}

# The ladder's OTHER actor field offsets (sp_death_probe's HEALTH_OFFSET, ALIVE_OFFSET,
# DEATH_TIME_OFFSET, ANGVEL_OFFSET, verdict_core's ACTOR_STAMP_OFFSET) are deliberately NOT here: they are
# r0001 literals used only by the online ladder, which runs on the r0001 build, and no r0004 value for any
# of them has been established -- a column filled by assumption is the defect this table exists to stop.
# They join when somebody measures them, the way move_scale was measured.


# ---------------------------------------------------------------------------
# The two instrument strings `scripts/parity/env.sh` exports, as TEMPLATES over the names above. The
# r0001 render must be byte-identical to the literal env.sh carried before this existed -- an online run's
# rows are read by these very chains, and a changed r0001 spec would silently re-cut every archived
# comparison. `tools_py/tests/test_online_instruments.py` pins both r0001 strings character for character.
#
# What the block reads, in its own order: the camera-orbit record; the actor block, the snap-back pair
# (+0x420 inside +0x400:12), +0x174, the alive byte (+0xF7A inside +0xF78:24) and health (+0x1044:8);
# CZNetGame and its nine valves twice over (the pointer pair, then the name bytes behind it, which is how
# a valve is identified -- name pointers are platform-specific); the mission-abort valve; the round clock
# and the four single-word globals; the clock string; and the actor pointer itself.
#
# Offsets are LITERAL: they are displacements inside an object, not addresses, and the ones this block
# uses all sit below the word r0004 inserted at +0x1334 (PROBE_OFFSETS' note), so they do not move. The
# exception is move_scale, which no PS2X_PEEK item reads -- the probe reads it, through `offset()`.
PEEK_TEMPLATE = (
    "{camera_record}:3,"
    "*{player_actor}:64,*{player_actor}+0xc0*:32,*{player_actor}+0x400:12,*{player_actor}+0x174:1,"
    "*{player_actor}+0xF78:24,*{player_actor}+0x1044:8,"
    "*{net_game}:64,*{net_game}+0x100:21,"
    "*{net_game}+0x0c*:2,*{net_game}+0x10*:2,*{net_game}+0x14*:2,*{net_game}+0x20*:2,*{net_game}+0x24*:2,"
    "*{net_game}+0x2c*:2,*{net_game}+0x58*:2,*{net_game}+0x5c*:2,*{net_game}+0x70*:2,"
    "*{mission_abort_valve}:2,"
    "{guest_clock}:1,{mp_flag_word}:1,{input_enable}:1,{r7_flag}:1,"
    "*{net_game}+0x0c**:3,*{net_game}+0x10**:3,*{net_game}+0x14**:3,*{net_game}+0x20**:3,"
    "*{net_game}+0x24**:3,*{net_game}+0x2c**:3,*{net_game}+0x58**:3,*{net_game}+0x5c**:3,"
    "*{net_game}+0x70**:3,*{mission_abort_valve}*:3,"
    "{clock_string}:2,{player_actor}:4"
)
CALL_TRACE_TEMPLATE = "{move_scale_setter}:MoveScale,{net_idle}:NetIdle"

# The three mixed-match legs (scripts/parity/mixed_match.sh, mixed_match2.sh, mixed_match2_leg2.sh) each
# carried this narrower block as an r0001 literal and exported it OVER env.sh's -- a hard assignment, so
# env.sh's render did not reach them (review F2). It is the block above without the nine CZNetGame valve
# pairs and their name-bytes items and without the mission-abort valve: a leg watches positions, health
# and the clocks, not the round valves. Rendered from the same names, so there is still one home.
PEEK_MIXED_TEMPLATE = (
    "{camera_record}:3,"
    "*{player_actor}:64,*{player_actor}+0xc0*:32,*{player_actor}+0x400:12,*{player_actor}+0x174:1,"
    "*{player_actor}+0xF78:24,*{player_actor}+0x1044:8,"
    "*{net_game}:64,*{net_game}+0x100:21,"
    "{guest_clock}:1,{clock_string}:2,{player_actor}:4"
)
# name -> (template, whether the emitted assignment OVERRIDES what is already in the environment).
# "online" keeps `VAR="${VAR:-...}"`: the operator's own spec wins, and sourcing env.sh twice is
# harmless. "mixed" is a hard assignment, because that is what the three legs have always done -- they
# deliberately replace env.sh's wider block with their own narrower one.
PEEK_PROFILES = {"online": (PEEK_TEMPLATE, False), "mixed": (PEEK_MIXED_TEMPLATE, True)}
# Every name a template reaches for, so a typo in one is a KeyError here and not a silent empty field.
_TEMPLATE_NAMES = ("camera_record", "player_actor", "net_game", "mission_abort_valve", "guest_clock",
                   "mp_flag_word", "input_enable", "r7_flag", "clock_string",
                   "move_scale_setter", "net_idle")


def _render(template, revision):
    return template.format(**{n: "0x%x" % address(n, revision) for n in _TEMPLATE_NAMES})


def peek_spec(revision, profile="online"):
    """`PS2X_PEEK` in this revision's addresses. `profile` picks the block: "online" (the full one every
    online script gets) or "mixed" (the three mixed-match legs' narrower one)."""
    try:
        template, _override = PEEK_PROFILES[profile]
    except KeyError:
        raise ValueError("guest addresses: no PS2X_PEEK profile called %r (have: %s)"
                         % (profile, ", ".join(sorted(PEEK_PROFILES)))) from None
    return _render(template, revision)


def call_trace_spec(revision):
    """`PS2X_CALL_TRACE` for the online harness, in this revision's addresses."""
    return _render(CALL_TRACE_TEMPLATE, revision)


def instrument_env_lines(revision, elf, profile="online"):
    """The lines a harness script evals. On the "online" profile each is `VAR="${VAR:-<spec>}"`, so
    whatever the operator already exported still wins and sourcing env.sh twice is still harmless -- the
    two properties the literal exports had, kept. The "mixed" profile assigns PS2X_PEEK outright and
    emits no call trace, which is exactly what the three legs' hard `export PS2X_PEEK=...` did."""
    _template, override = PEEK_PROFILES[profile]
    spec = peek_spec(revision, profile)
    lines = ["# instruments: %s, %s profile, from %s" % (revision, profile, elf)]
    if override:
        lines.append('PS2X_PEEK="%s"' % spec)
        return lines
    lines.append('PS2X_PEEK="${PS2X_PEEK:-%s}"' % spec)
    lines.append('PS2X_CALL_TRACE="${PS2X_CALL_TRACE:-%s}"' % call_trace_spec(revision))
    return lines


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


def main(argv=None):
    """`python -m tools_py.parity.guest_addresses --env` -- the shell lines scripts/parity/env.sh evals.

    The column is chosen exactly the way `gate.launch_env` chooses its own: the build banner in the image
    `$SOCOM_GAME_ELF` names. `default_ok=True` is `gate.collect_pins`' relaxation and it is here for the
    same reason -- with no `$SOCOM_GAME_ELF` and no image at the default path (a bare clone: `game/` is
    git-ignored) there is no launch to mislabel, and sourcing env.sh must still work. A `$SOCOM_GAME_ELF`
    that names a missing file, or an image that will not name its revision, still refuses.
    """
    import argparse
    ap = argparse.ArgumentParser(prog="tools_py.parity.guest_addresses",
                                 description="the online harness's per-revision instrument addresses")
    ap.add_argument("--env", action="store_true", help="the shell lines scripts/parity/env.sh evals")
    ap.add_argument("--revision", choices=sorted(REVISIONS),
                    help="the column, instead of reading it off the image a launch would use")
    ap.add_argument("--profile", choices=sorted(PEEK_PROFILES), default="online",
                    help="which PS2X_PEEK block: online (every online script) or mixed (the legs')")
    a = ap.parse_args(argv)
    if not a.env:
        ap.error("nothing to print: --env is the only output this has")
    elf = os.environ.get(GAME_ELF_ENV) or DEFAULT_GAME_ELF
    # The RENDER is inside the try as well as the detection (review F1). `address()` raises for a
    # revision this table has no column for, and r0002 and r0003 are real SOCOM II revisions: an image
    # banner naming one used to reach the operator as a traceback from the very command env.sh's refusal
    # message tells them to run. It is fail-safe either way -- nothing launches -- but the one refusal a
    # reader ever meets has to be the sentence.
    try:
        revision = a.revision or launch_revision(default_ok=True)
        lines = instrument_env_lines(revision, "--revision" if a.revision else elf, a.profile)
    except (ValueError, OSError) as e:
        # A sentence on stderr, not a traceback: env.sh's caller reads this, and the shell prints
        # nothing else useful about a failed command substitution.
        sys.stderr.write("%s\n" % e)
        return 2
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
