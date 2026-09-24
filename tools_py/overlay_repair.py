"""Undo the r0004 capsule's baked-in stub writes in a decrypted overlay.

What is wrong with the image
----------------------------
At `0x002CC670`, in the middle of the epilogue of the function that starts at `0x002CC5F0`,
the r0004 overlay decrypted out of the card's `APACHE00.ZDB` holds

    002cc668  daddu $v0, $s1, $zero        002cc670  jr    $ra      <- 0x03E00008
    002cc66c  ld    $ra, 0x20($sp)         002cc674  nop             <- 0x00000000
                                           002cc678  jr    $ra
                                           002cc67c  addiu $sp, $sp, 0x40

Two returns back to back, the first without giving the frame back.  Every call to that function
therefore returns with `$s0`, `$s1` and `$sp` still holding the callee's own values, and
`CButtonSpec::Clone` at `0x003A90E0`, which calls it at `0x003A9178`, then reads its `std::vector`
member through `$s1` out of a stranger and asks `operator new` for 111.5 MiB.  That is the r0004
title reboot.

How this module decides -- the capsule's write stack, not a shape
-----------------------------------------------------------------
Nothing here looks for that shape.  An address is repaired only when **the r0004 capsule's own
decoded write stack says the capsule writes that exact word there and the image already holds it**.
`tools_py/r0004/capsule.py:find_pair_tables` parses the decoded stack into
`[(base, [(address, value), ...])]`; for r0004 it yields two tables,

    table at 80031250:  0x002CC670 <- 0x03E00008,  0x002CC674 <- 0x00000000
    table at 80031268:  0x002CF330 <- 0x03E00008,  0x002CF334 <- 0x00000000

which are one *stub this function out* patch per revision layout: the function the capsule wants
disabled sits at `0x002CC670` in r0001 and at `0x002CF330` in r0004.  Our image carries table 1's
effect and not table 2's (`0x002CF330` in it is an intact prologue), so exactly two words fire and
table 2 is a measured no-op.  Where the stack is not available -- every r0001 build -- there are no
candidate addresses at all and this module is the identity function by construction.

Where the replacement words come from
-------------------------------------
Not from a guess.  The function containing a fired address is located by its row in the revision's
own `socom2_ghidra_<rev>.csv`, and its **r0001 twin is found by a masked body hash**: for every
r0001 row, the two bodies are compared with the fired words masked out, and a twin is accepted only
when the rest of the body matches exactly.  (`game/r0004/match.json` has no row for `0x002CC5F0` --
the matcher could not place it *because* of these two words -- so the twin has to be found this
way.)  **That masked compare is the assertion**: byte-for-byte equality with the fired words zeroed,
over `max(this image's row, the twin's row)` bytes, so a twin shorter than the image's function
cannot match its prefix.  The twin's words at those offsets are then the replacement -- which makes
"the two bodies are identical after the substitution" an invariant that restates the compare, not a
second check.

As an independent cross-check the frame's own prologue is read: the saves it makes with
`sq/sd $rX, K($sp)` that no load off `$sp` of any width restores are re-derived as `lq/ld`
instructions, and they must agree with the twin's words.  The cross-check can veto a repair; it can
never supply one.

Anything unresolved refuses loudly (`RepairError`) rather than writing something plausible.
"""
import csv
import hashlib
import json
import os
import struct
import sys
from dataclasses import dataclass

_SQ, _SD = 0x1F, 0x3F           # the stores a Metrowerks frame saves a callee-saved register with
_LQ, _LD = 0x1E, 0x37           # and their restores
_RESTORE_OF = {_SQ: _LQ, _SD: _LD}
_LOADS_OFF_SP = (0x20, 0x21, 0x23, 0x24, 0x25, 0x27, 0x37, 0x1E)   # lb lh lw lbu lhu lwu ld lq

_SP = 29
_ADDIU_SP = 0x27BD              # addiu $sp, $sp, imm
_DADDIU_SP = 0x67BD             # daddiu $sp, $sp, imm

# Only these can be displaced by a stub pair in an epilogue: $s0-$s7, $gp, $fp, $ra.
_CALLEE_SAVED = frozenset(list(range(16, 24)) + [28, 30, 31])

# A window shorter than this is not enough body to identify a twin by.
_MIN_TWIN_WORDS = 6


class RepairError(RuntimeError):
    """A fired capsule write that could not be resolved. Never repaired silently."""


@dataclass(frozen=True)
class Repair:
    """One word the repair rewrites, with everything needed to audit it."""
    address: int
    before: int
    after: int
    function: int
    twin_function: int
    twin_bytes: int
    cross_check: str

    def describe(self):
        return (f"0x{self.address:08X}: 0x{self.before:08X} -> 0x{self.after:08X}"
                f"  (capsule stub in the function at 0x{self.function:08X}; from the r0001 twin at"
                f" 0x{self.twin_function:08X}, {self.twin_bytes} B, prologue cross-check {self.cross_check})")

    def as_dict(self):
        return {"address": f"0x{self.address:08X}",
                "before": f"0x{self.before:08X}",
                "after": f"0x{self.after:08X}",
                "function": f"0x{self.function:08X}",
                "twin_function": f"0x{self.twin_function:08X}",
                "twin_bytes": self.twin_bytes,
                "cross_check": self.cross_check}


# ---- images -------------------------------------------------------------------------------------

class Image:
    """Executable bytes addressed by guest address, with a text window per span."""

    def __init__(self, spans=()):
        # span: (base, data, text_start, text_end)
        self._spans = list(spans)

    def add(self, base, data, text_start=None, text_end=None):
        self._spans.append((base, data,
                            base if text_start is None else text_start,
                            base + len(data) if text_end is None else text_end))
        return self

    def in_text(self, address):
        return any(ts <= address < te for _b, _d, ts, te in self._spans)

    def word(self, address):
        for base, data, _ts, _te in self._spans:
            if base <= address < base + len(data) - 3:
                return struct.unpack_from("<I", data, address - base)[0]
        return None

    def body(self, address, length):
        """`length` bytes starting at `address`, or None when they are not all in one span."""
        for base, data, _ts, _te in self._spans:
            if base <= address and address + length <= base + len(data):
                return data[address - base:address - base + length]
        return None

    @classmethod
    def from_file(cls, path):
        """An ELF's executable PT_LOADs, or one MWo3 overlay (its header is loaded, its text follows)."""
        with open(path, "rb") as fh:
            d = fh.read()
        image = cls()
        if d[:4] == b"MWo3":
            load, text = struct.unpack_from("<2I", d, 8)
            return image.add(load, d, load + 0x80, load + 0x80 + text)
        e_phoff = struct.unpack_from("<I", d, 0x1C)[0]
        e_phnum = struct.unpack_from("<H", d, 0x2C)[0]
        for i in range(e_phnum):
            p_type, p_off, p_va, _pa, p_filesz, _memsz, p_flags = struct.unpack_from("<7I", d, e_phoff + i * 32)
            if p_type == 1 and p_filesz and (p_flags & 1):
                image.add(p_va, d[p_off:p_off + p_filesz])
        return image


# ---- the capsule's write stack and the function maps ---------------------------------------------

def read_stack(path):
    """`game/<rev>/decoded/stack.txt` as tools_py.r0004.capsule writes it: [(kind, address, value)]."""
    writes = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) != 3:
                continue
            writes.append((parts[0], int(parts[1], 16), int(parts[2], 16)))
    return writes


def stub_writes(writes):
    """The (address, value) pairs of every NUL-terminated pair table in the capsule's stack."""
    try:                                        # imported here: the repair is inert without a stack
        from tools_py.r0004 import capsule
    except ImportError:                         # make_overlay_elf.py run as a script from tools_py/
        from r0004 import capsule
    pairs = []
    for _base, entries in capsule.find_pair_tables(writes):
        pairs.extend(entries)
    return sorted(set(pairs))


def read_rows(path):
    """`recomp/socom2_ghidra*.csv` as a sorted [(start, end)]."""
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append((int(row["Start"], 16), int(row["End"], 16)))
    rows.sort()
    return rows


def _row_containing(rows, address):
    for start, end in rows:
        if start <= address < end:
            return start, end
    return None


# ---- what the answer depends on, and whether a sidecar is still current ----------------------------

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The code that decides, beside the data that decides: the pair tables come out of capsule.py, and
# both of the other two turn its answer into bytes on disk.
_MODULES = ("tools_py/overlay_repair.py", "tools_py/make_overlay_elf.py", "tools_py/r0004/capsule.py")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_digests(paths=None):
    """`{name: {path, sha256}}` for every input a repair's answer depends on.

    Recorded in the sidecar and compared on the next build: a re-decoded capsule stack, a corrected
    `find_pair_tables`, a rebuilt r0001 image or a new function map all change an answer that a
    merged ELF has already baked in, and an mtime comparison against two modules did not see any of
    them.
    """
    out = {}
    for name, path in sorted((paths or {}).items()):
        out[name] = {"path": path,
                     "sha256": sha256_file(path) if os.path.isfile(path) else None}
    for module in _MODULES:
        full = os.path.join(_ROOT, module)
        out[os.path.basename(module)] = {"path": module,
                                         "sha256": sha256_file(full) if os.path.isfile(full) else None}
    return out


def log_is_current(log_path, digests):
    """`(bool, reason)`: does `<elf>.repair.json` record exactly the inputs in hand?"""
    try:
        with open(log_path, "r", encoding="utf-8") as fh:
            recorded = json.load(fh)["sources"]
    except (OSError, ValueError, KeyError) as exc:
        return False, f"{os.path.basename(log_path)} could not be read ({exc.__class__.__name__})"
    if not isinstance(recorded, dict):
        return False, f"{os.path.basename(log_path)} records no table of sources"
    if set(recorded) != set(digests):
        missing = sorted(set(digests) - set(recorded)) + sorted(set(recorded) - set(digests))
        return False, f"the set of repair inputs changed ({', '.join(missing)})"
    for name, want in sorted(digests.items()):
        got = recorded.get(name)
        if not isinstance(got, dict) or got.get("sha256") != want["sha256"]:
            return False, f"{name} changed since the image was merged ({want['path']})"
    return True, f"all {len(digests)} repair inputs match the sha256 recorded beside the image"


# ---- the twin search ------------------------------------------------------------------------------

def _mask(body, offsets):
    out = bytearray(body)
    for o in offsets:
        out[o:o + 4] = b"\0\0\0\0"
    return bytes(out)


def _word(body, offset):
    return struct.unpack_from("<I", body, offset)[0]


def _find_twin(image, twin, start, offsets, twin_rows, row_length):
    """(twin_start, length, replacement words) for the function at `start`, from its r0001 twin.

    **The assertion is the masked compare**: a twin is accepted only when the two bodies are equal
    byte for byte with the fired words zeroed out, over
    `max(this image's row, the twin's row)` bytes. Taking the longer of the two is what stops a
    twin that is shorter than the image's function from matching its prefix; a twin whose row is
    shorter is still read (and must still match) out to the image row's end.
    """
    need = max(offsets) + 4
    head = image.word(start) if 0 not in offsets else None
    agreed = None
    matches = []
    for tstart, tend in twin_rows:
        length = max(row_length, tend - tstart)
        if length < need or length < _MIN_TWIN_WORDS * 4:
            continue
        if head is not None and twin.word(tstart) != head:   # cheap reject: the prologue word
            continue
        body = image.body(start, length)
        tbody = twin.body(tstart, length)
        if body is None or tbody is None:
            continue
        if _mask(body, offsets) != _mask(tbody, offsets):
            continue
        words = tuple(_word(tbody, o) for o in offsets)
        if agreed is None:
            agreed = words
        elif words != agreed:
            raise RepairError(
                f"the function at 0x{start:08X} matches several r0001 twins that disagree on the "
                f"replacement words: 0x{matches[0][0]:08X} says {['0x%08X' % w for w in agreed]}, "
                f"0x{tstart:08X} says {['0x%08X' % w for w in words]}")
        matches.append((tstart, length))
    if not matches:
        raise RepairError(
            f"no r0001 twin for the function at 0x{start:08X} (a masked body compare over "
            f"{len(twin_rows)} rows found none); refusing to invent {len(offsets)} word(s)")
    tstart, length = matches[0]
    # Restating the masked compare with the words put back: it cannot fail today, because `agreed` was
    # read out of the same `tbody` the compare matched. It stays a RepairError, not an assert, so that a
    # future change to how `agreed` is chosen refuses loudly instead of writing something (the module's
    # rule), and so `python -O` cannot strip it.
    repaired = bytearray(image.body(start, length))
    for o, w in zip(offsets, agreed):
        struct.pack_into("<I", repaired, o, w)
    if bytes(repaired) != twin.body(tstart, length):
        raise RepairError(
            f"0x{start:08X}: the repaired body does not equal the twin's at 0x{tstart:08X} after "
            f"substitution -- refusing to write (the masked compare and the substitution disagree)")
    return tstart, length, agreed


# ---- the prologue cross-check ----------------------------------------------------------------------

def _frame_delta(word):
    """(+/-N) when the word adjusts $sp, else None. `daddiu $sp` counts (F3)."""
    if (word >> 16) not in (_ADDIU_SP, _DADDIU_SP):
        return None
    imm = word & 0xFFFF
    return imm - 0x10000 if imm >= 0x8000 else imm


def _stack_slot(word):
    op = word >> 26
    if ((word >> 21) & 31) != _SP:
        return None
    return op, (word >> 16) & 31, word & 0xFFFF


def implied_restores(body, offsets):
    """The `lq/ld` a frame's own prologue implies are missing, or None when it cannot be read.

    A save counts as restored when *any* load off `$sp` touches its slot, whatever its width: a
    64-bit spill reloaded with `lw` is a well-formed frame, not a missing restore.
    """
    if not body or _frame_delta(_word(body, 0)) is None or _frame_delta(_word(body, 0)) >= 0:
        return None
    saves, loaded_slots = [], set()
    masked = set(offsets)
    for off in range(0, len(body) - 3, 4):
        if off in masked:
            continue
        slot = _stack_slot(_word(body, off))
        if slot is None:
            continue
        op, rt, imm = slot
        if op in _RESTORE_OF:
            entry = (_RESTORE_OF[op], rt, imm)
            if entry not in saves:                       # de-duplicate (F2)
                saves.append(entry)
        elif op in _LOADS_OFF_SP:
            loaded_slots.add(imm)
    missing = [s for s in saves if s[2] not in loaded_slots]
    if any(rt not in _CALLEE_SAVED for _op, rt, _imm in missing):
        return None
    return [(op << 26) | (_SP << 21) | (rt << 16) | imm for op, rt, imm in missing]


# ---- the plan -------------------------------------------------------------------------------------

def plan_repairs(image, writes, twin=None, rows=None, twin_rows=None):
    """([Repair], [note]) for `image`. With no capsule writes this is ([], [])."""
    notes = []
    fired = []
    for address, value in writes or ():
        if not image.in_text(address):
            continue                                     # another segment's business, or data (F4)
        current = image.word(address)
        if current != value:
            notes.append(f"0x{address:08X}: image holds 0x{current:08X}, the capsule writes "
                         f"0x{value:08X} -- not baked in, no-op")
            continue
        fired.append(address)
    if not fired:
        return [], notes
    if twin is None or rows is None or twin_rows is None:
        raise RepairError(
            f"{len(fired)} capsule stub write(s) are baked into this image "
            f"({', '.join('0x%08X' % a for a in fired)}) but no twin image / function rows were "
            f"given to resolve them")

    groups = {}
    for address in fired:
        row = _row_containing(rows, address)
        if row is None:
            raise RepairError(f"0x{address:08X} is a baked-in capsule stub write but no row of the "
                              f"revision's function map contains it")
        groups.setdefault(row, []).append(address)

    repairs = []
    for (start, end), addresses in sorted(groups.items()):
        offsets = sorted(a - start for a in addresses)
        tstart, length, words = _find_twin(image, twin, start, offsets, twin_rows, end - start)
        implied = implied_restores(image.body(start, length), offsets)
        if implied is None:
            cross_check = "unavailable"
            notes.append(f"0x{start:08X}: the frame's prologue could not be read; the twin is the "
                         f"only source for this repair")
        elif sorted(implied) == sorted(words):
            cross_check = "agrees"
        else:
            raise RepairError(
                f"the frame at 0x{start:08X} implies {['0x%08X' % w for w in implied]} but its "
                f"r0001 twin at 0x{tstart:08X} holds {['0x%08X' % w for w in words]}; refusing")
        for offset, word in zip(offsets, words):
            repairs.append(Repair(address=start + offset,
                                  before=image.word(start + offset),
                                  after=word,
                                  function=start,
                                  twin_function=tstart,
                                  twin_bytes=length,
                                  cross_check=cross_check))
    return repairs, notes


def apply_repairs(data, base, writes=None, twin=None, rows=None, twin_rows=None,
                  text_start=None, text_end=None):
    """`(repaired bytes, repairs, notes)` for one segment loaded at `base`."""
    image = Image().add(base, data, text_start, text_end)
    repairs, notes = plan_repairs(image, writes, twin, rows, twin_rows)
    if not repairs:
        return data, repairs, notes
    out = bytearray(data)
    for r in repairs:
        struct.pack_into("<I", out, r.address - base, r.after)
    return bytes(out), repairs, notes


def write_log(path, repairs, notes, sources):
    """The durable provenance beside a built image; returns its sha256."""
    payload = {"image": os.path.basename(path)[:-len(".repair.json")]
                        if path.endswith(".repair.json") else os.path.basename(path),
               "sources": sources,
               "repairs": [r.as_dict() for r in repairs],
               "notes": list(notes)}
    blob = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    with open(path, "wb") as fh:
        fh.write(blob)
    return hashlib.sha256(blob).hexdigest()


# ---- the command ------------------------------------------------------------------------------------

def main(argv):
    """Report (never rewrite) what the repair would do to an image, or test a sidecar's freshness."""
    import argparse
    ap = argparse.ArgumentParser(prog="tools_py.overlay_repair", description=__doc__.split("\n")[0])
    ap.add_argument("image", nargs="?", help="the overlay (MWo3) or merged ELF to examine")
    ap.add_argument("--check", metavar="REPAIR_JSON",
                    help="instead of examining an image, say whether that <elf>.repair.json was "
                         "written from the inputs named here (exit 0 current, 1 stale)")
    ap.add_argument("--stub-writes", help="game/<rev>/decoded/stack.txt (without it: nothing to do)")
    ap.add_argument("--twin", help="the r0001 image the replacement words come from")
    ap.add_argument("--rows", help="recomp/socom2_ghidra_<rev>.csv")
    ap.add_argument("--twin-rows", help="recomp/socom2_ghidra.csv")
    args = ap.parse_args(argv)

    named = {name: path for name, path in (("stub-writes", args.stub_writes), ("twin", args.twin),
                                           ("rows", args.rows), ("twin-rows", args.twin_rows))
             if path}
    if args.check:
        current, why = log_is_current(args.check, source_digests(named))
        print(("current: " if current else "stale: ") + why)
        return 0 if current else 1
    if not args.image:
        ap.error("an image to examine, or --check <elf>.repair.json")

    image = Image.from_file(args.image)
    writes = stub_writes(read_stack(args.stub_writes)) if args.stub_writes else []
    twin = Image.from_file(args.twin) if args.twin else None
    rows = read_rows(args.rows) if args.rows else None
    twin_rows = read_rows(args.twin_rows) if args.twin_rows else None
    try:
        repairs, notes = plan_repairs(image, writes, twin, rows, twin_rows)
    except RepairError as exc:
        sys.stderr.write(f"{args.image}: {exc}\n")
        return 1
    for note in notes:
        print(f"note {note}")
    for r in repairs:
        print(f"{os.path.basename(args.image)}  {r.describe()}")
    print(f"{len(repairs)} word(s) would be repaired from {len(writes)} capsule stub write(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
