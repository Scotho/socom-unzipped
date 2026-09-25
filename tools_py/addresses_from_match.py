"""Sprint 11 Task 19: print the r0004 column of `runtime/socom2_addresses.h` from match.json.

`tools_py/address_matcher.py` says which r0004 address each r0001 function landed on, and how it knows.
This turns that report into the C++ column, so supporting the revision after r0004 is a re-run of two
commands rather than a second afternoon of hand lookups:

    python -m tools_py.address_matcher game/overlays/socom2_game.elf recomp/socom2_ghidra.csv \\
        game/overlays_r0004/socom2_game_r0004.elf recomp/socom2_ghidra_r0004.raw.csv \\
        --seed 0x180008=0x180008 --out game/r0004/match.json
    python -m tools_py.addresses_from_match game/r0004/match.json --revision r0004

**A field is filled from evidence or not at all.** Only the three methods that name what was proved --
`identity` (the function did not move), `exact` (a globally unique fingerprint on both sides) and
`hash+callees` (the candidates that share a fingerprint, narrowed to one by the calls it makes) -- fill
a field. `seed+delta` does not, by default: a delta says where to look, not what was found, and the
report has to be able to say which fields rest on it (`--accept seed+delta` opts in). Everything else
prints `0u` -- UNAVAILABLE -- and the runtime's install guards skip that override with a log line.
**Never the r0001 address.** A wrong address in the column is not a bad address: it is a crash
somewhere else entirely, hours later.

The matcher places *functions*. The table's DATA fields (a pointer the runtime reads, the two static
constructor tables, the build stamp) are not functions, so they never come from match.json; they print
UNAVAILABLE unless the caller supplies them with `--override <field>=<addr>:<how>`, which is how an
address established by other evidence -- the build banner found in the image, an address the r0004
capsule's own second patch table names, a data address read out of a twinned function at the same
instruction offset -- enters the column with a record of where it came from.
"""
import argparse
import json
import sys
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

# The lowest address the overlays occupy; below it is the boot loader, which is the same binary in
# every pressing of the game and whose addresses stay literal at their call sites.
OVERLAY_BASE = 0x001D5600

# What the matcher is allowed to fill a field with, by default.
#
# `relinked-body` (address_matcher.py's fourth pass, e92691a) is in this list because it proves the
# same thing the others do -- the same instruction stream, with only relocations differing -- and it is
# what places most of this table: ten of the kR0004 fields established by hand on 2026-09-23 come back
# from it unchanged. Leaving it out would zero ten addresses that are right, the next time anyone
# regenerates the column. What it does NOT prove on its own is which of several candidates sharing a
# masked hash is the one, so the matcher records its tie-breaker ("unique", "callees", "string") and
# this tool carries that into the column: `relinked-body (unique)` and `relinked-body (string)` are not
# the same claim, and a reader deciding whether to trust a line needs to see which was made.
#
# `seed+delta` is still not here: a delta says where to look, not what was found.
ACCEPT = ("identity", "exact", "hash+callees", "relinked-body")


class Field(NamedTuple):
    name: str          # the Table member, in the header's order
    a: int             # its r0001 address
    data: bool         # True for a field that is data, not a function: the matcher never places it
    note: str


# One entry per `uint32_t` member of `struct Table` in socom2_addresses.h, in the header's order --
# the printed column is an aggregate initialiser, so the order is load-bearing.
# test_addresses_from_match.py parses the header and fails if the two ever drift apart.
FIELDS: Tuple[Field, ...] = (
    Field("rtNetConfigInit", 0x00620648, False, "the RtNet config init the runtime replaces"),
    Field("packTrace", 0x0025A5D0, False, "the level loader's inner-file probe"),
    Field("cull", 0x00290C30, False, "the visibility cull"),
    Field("node", 0x00338480, False, "scene node walk 1"),
    Field("node2", 0x003389C0, False, "scene node walk 2"),
    Field("lod", 0x003B7B90, False, "the LOD selection"),
    Field("detail", 0x003B6E10, False, "the detail selection"),
    Field("camCfg", 0x002918B0, False, "the camera config record apply"),
    Field("defer", 0x003371B0, False, "the deferred draw enqueue"),
    Field("flush", 0x00336CB0, False, "the deferred draw flush"),
    Field("musicManager", 0x0034AFD0, False, "the per-frame music manager"),
    Field("cuePush", 0x0034B6C0, False, "the music cue push"),
    Field("cameraHolder", 0x00415FF0, True, "DATA: the camera holder pointer"),
    Field("versionString", 0x003E17E0, True, "DATA: the build banner that picks the column"),
    Field("oskOpen", 0x0038D770, False, "the keyboard's GetTextInput handler"),
    Field("oskOpenThunk", 0x002808D0, False, "the thunk the UI action table dispatches through"),
    Field("oskTextBuffer", 0x0049EC70, True, "DATA: the keyboard's initial-text buffer"),
    Field("chatFanoutRecv", 0x002F4EF0, False, "the chat receive fan-out"),
    Field("chatListRender", 0x002F5020, False, "the second reader of the same records"),
    Field("chatListHolders", 0x0044F568, True, "DATA: the holder list it renders from"),
    Field("dnasCheck", 0x002CC670, False, "the DNAS tick the runtime answers done"),
    Field("ctorTableFtsBegin", 0x00404D10, True, "DATA: FTSCore's static constructor table"),
    Field("ctorTableFtsEnd", 0x00404F04, True, "DATA"),
    Field("ctorTableZsealBegin", 0x006690E0, True, "DATA: ZSealEtc's static constructor table"),
    Field("ctorTableZsealEnd", 0x00669120, True, "DATA"),
    Field("netbExOpen", 0x002472C8, False, "libnetb_ex: open"),
    Field("netbExTcpRecv", 0x002474F8, False, "libnetb_ex: TCP receive"),
    Field("netbExTcpSend", 0x00247738, False, "libnetb_ex: TCP send"),
    Field("netbExUdpRecv", 0x00247D30, False, "libnetb_ex: UDP receive"),
    Field("netbExUdpSend", 0x00247FE8, False, "libnetb_ex: UDP send"),
    Field("netbExAvailable", 0x002479B8, False, "libnetb_ex: bytes available"),
    Field("netbExConnected", 0x00247BD8, False, "libnetb_ex: connected"),
    Field("netbExStartAsync", 0x00248350, False, "libnetb_ex: start async"),
    Field("netbExStartAsync2", 0x002483F8, False, "libnetb_ex: start async, second entry point"),
    Field("netbExDescriptorDma", 0x00247C98, False, "libnetb_ex: descriptor DMA helper"),
    Field("dnasRsaBlock", 0x0062B948, False, "libdnas2: RSA block transform"),
    Field("dnasSha1Hash", 0x0062EEC0, False, "libdnas2: SHA-1"),
    Field("dnasRc4SetKeyHash", 0x0062A638, False, "libdnas2: RC4 set key from hash"),
    Field("dnasRc4SetKey", 0x0062A5A8, False, "libdnas2: RC4 set key"),
    Field("dnasRc4Encrypt", 0x0062A720, False, "libdnas2: RC4 encrypt"),
    Field("dnasRc4Decrypt", 0x0062A7C8, False, "libdnas2: RC4 decrypt"),
)


class Row(NamedTuple):
    name: str
    a: int
    b: Optional[int]   # the r0004 address, or None -- UNAVAILABLE
    method: str        # what filled it, or why nothing did
    note: str

    @property
    def resolved(self) -> bool:
        return self.b is not None


def by_name(name: str) -> Field:
    for f in FIELDS:
        if f.name == name:
            return f
    raise KeyError(name)


def column(matches: Dict[str, dict],
           fields: Sequence[Field] = FIELDS,
           accept: Iterable[str] = ACCEPT,
           overrides: Optional[Dict[str, Tuple[int, str]]] = None) -> List[Row]:
    """One Row per Table member, in the header's order.

    `matches` is match.json's "matches" object: {"0xAAAAAAAA": {"b": "0xBBBBBBBB"|null, "how": ...}}.
    `overrides` are {field: (address, how)} pairs established by other evidence; each is checked
    against the overlay base, because a loader address in this column would be a mistake.
    """
    accept = tuple(accept)
    overrides = dict(overrides or {})
    unknown = set(overrides) - {f.name for f in fields}
    if unknown:
        raise ValueError("override names no Table field: %s" % ", ".join(sorted(unknown)))
    out: List[Row] = []
    for f in fields:
        if f.name in overrides:
            addr, how = overrides[f.name]
            if addr < OVERLAY_BASE:
                raise ValueError("%s: 0x%08x is below the overlay base (0x%08x) -- that is the loader"
                                 % (f.name, addr, OVERLAY_BASE))
            out.append(Row(f.name, f.a, addr, how, f.note))
            continue
        if f.data:
            out.append(Row(f.name, f.a, None, "data", f.note))
            continue
        entry = matches.get("0x%08x" % f.a)
        if entry is None:
            out.append(Row(f.name, f.a, None, "absent", f.note))
            continue
        how = entry.get("how", "unresolved")
        b = entry.get("b")
        if b is None:
            out.append(Row(f.name, f.a, None, how, f.note))
            continue
        b_addr = int(b, 16)
        if b_addr == f.a and how in ("exact", "hash+callees", "relinked-body", "seed+delta"):
            how = "identity"
        if how not in accept:
            out.append(Row(f.name, f.a, None, "rejected:%s" % how, f.note))
            continue
        # The tie-breaker is part of the claim, not decoration: it says what separated this candidate
        # from the others that shared its masked hash.
        tie = entry.get("tie")
        method = "%s (%s)" % (how, tie) if tie else how
        out.append(Row(f.name, f.a, b_addr, method, f.note))
    return out


def render(rows: Sequence[Row], revision: str) -> str:
    """The C++ aggregate initialiser for one Table, ready to paste into socom2_addresses.h."""
    width = max(len(r.name) for r in rows)
    lines = ["    inline constexpr Table k%s%s = {" % (revision[:1].upper(), revision[1:]),
             '        "%s",' % revision]
    for r in rows:
        value = "0x%08xu," % r.b if r.resolved else "0u,"
        if r.resolved:
            tail = "r0001 0x%08x  %s" % (r.a, r.method)
        else:
            tail = "UNAVAILABLE (%s) -- r0001 is 0x%08x and must not be used here" % (r.method, r.a)
        lines.append("        %-13s // %-*s  %s" % (value, width, r.name, tail))
    lines.append("    };")
    return "\n".join(lines) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("match", help="match.json from tools_py.address_matcher")
    ap.add_argument("--revision", default="r0004", help="the column's revision name (default r0004)")
    ap.add_argument("--accept", default="", metavar="HOW[,HOW]",
                    help="extra matcher methods allowed to fill a field (e.g. seed+delta)")
    ap.add_argument("--override", action="append", default=[], metavar="FIELD=ADDR:HOW",
                    help="a field established by other evidence, with how it was established")
    args = ap.parse_args(argv)

    with open(args.match) as fh:
        doc = json.load(fh)
    accept = ACCEPT + tuple(x for x in args.accept.split(",") if x)
    overrides = {}
    for spec in args.override:
        field, _, rest = spec.partition("=")
        addr, _, how = rest.partition(":")
        if not field or not addr:
            ap.error("--override wants FIELD=ADDR:HOW, got %r" % spec)
        overrides[field.strip()] = (int(addr, 16), how.strip() or "override")

    rows = column(doc.get("matches", {}), accept=accept, overrides=overrides)
    sys.stdout.write(render(rows, args.revision))
    got = [r for r in rows if r.resolved]
    sys.stderr.write("%d resolved, %d UNAVAILABLE, of %d fields\n"
                     % (len(got), len(rows) - len(got), len(rows)))
    for r in rows:
        if not r.resolved:
            sys.stderr.write("  UNAVAILABLE %-20s (%s)\n" % (r.name, r.method))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
