#!/usr/bin/env python
"""Enumerate an overlay's static-constructor thunks from its MWo3 header and force each as an entry.

The r0004 gate finds these one at a time: the loader's `FUN_00182840(ctor_start, ctor_end)` walks a
table of `__sinit_*` thunk pointers and `jalr`s each one, so every thunk is a guest entry point that
no branch in the image names. A thunk the function map does not have is a
`[guest-branch:missing-target] kind=IndirectCall op=JALR` at runtime, one round of the loop per
address. The table's bounds are in the overlay header, so all of them can be had at once.

The `MWo3` header is 0x80 bytes at the front of the image and the image loads verbatim at
`load`, so file offset 0 is guest address `load`:

    +0x00  magic 'MWo3'          +0x10  bss size
    +0x04  version               +0x18  ctor table begin   <- this
    +0x08  load address          +0x1c  ctor table end     <- and this
    +0x0c  text size             +0x20  name

The table is an array of 32-bit guest addresses. r0001: 125 thunks in FTSCore (0x404d10..0x404f04,
first thunk 0x3fd680) and 16 in ZSealEtc (0x6690e0..0x669120). r0004 moved both tables:
0x4315a0..0x431798 (126) and 0x668a60..0x668aa0 (16). The thunks live *after* rodata, inside the
"data" part of the image and past the header's text size, which is why the synthetic ELF keeps the
whole overlay executable (docs/research/05-code-package-and-harness.md, item 2).

Usage:
    python tools_py/find_ctor_thunks.py game/overlays_r0004/*.bin \\
        --csv recomp/socom2_ghidra_r0004.csv --extras recomp/extra_functions_r0004.txt
    ... --append recomp/extra_functions_r0004.txt --header '# --- overlay ctor thunks (...) ---'
"""
import argparse
import collections
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools_py.find_data_entries import is_sane_instruction, load_known, load_rows

MAGIC = b"MWo3"
HEADER_SIZE = 0x80

Header = collections.namedtuple(
    "Header", "version load text_size data_size bss_size ctor_begin ctor_end name")


def read_header(data):
    """The MWo3 header, or ValueError saying which field is wrong.

    Nothing here trusts the image: a truncated or mis-decrypted overlay must fail loudly rather
    than hand back a table of addresses read from the middle of a texture.
    """
    if len(data) < HEADER_SIZE:
        raise ValueError("image is %d bytes, shorter than the 0x80-byte MWo3 header" % len(data))
    if data[:4] != MAGIC:
        raise ValueError("not an MWo3 overlay: magic is %r" % data[:4])

    version, load, text_size, data_size, bss_size, ctor_begin, ctor_end = struct.unpack_from(
        "<7I", data, 4)
    name = data[0x20:0x30].split(b"\0", 1)[0].decode("ascii", "replace")

    if ctor_end < ctor_begin:
        raise ValueError("ctor table ends (0x%x) before it begins (0x%x)" % (ctor_end, ctor_begin))
    if (ctor_end - ctor_begin) % 4:
        raise ValueError("ctor table [0x%x,0x%x) is not a whole number of words"
                         % (ctor_begin, ctor_end))
    if ctor_begin % 4:
        raise ValueError("ctor table begins unaligned at 0x%x" % ctor_begin)
    if ctor_begin < load or ctor_end > load + len(data):
        raise ValueError("ctor table [0x%x,0x%x) is outside the image [0x%x,0x%x)"
                         % (ctor_begin, ctor_end, load, load + len(data)))

    return Header(version, load, text_size, data_size, bss_size, ctor_begin, ctor_end, name)


class Overlay(object):
    """One loaded overlay image, its header, and the thunks its ctor table names."""

    __slots__ = ("path", "data", "header", "thunks", "rejected")

    def __init__(self, path, data):
        self.path = path
        self.data = data
        self.header = read_header(data)
        self.thunks = []      # (address, index)
        self.rejected = []    # (address, index, reason)
        self._walk()

    @property
    def name(self):
        return self.header.name or os.path.basename(self.path)

    def word(self, address):
        offset = address - self.header.load
        if address % 4 or offset < 0 or offset > len(self.data) - 4:
            return None
        return struct.unpack_from("<I", self.data, offset)[0]

    def _walk(self):
        header = self.header
        count = (header.ctor_end - header.ctor_begin) // 4
        for index in range(count):
            address = struct.unpack_from(
                "<I", self.data, header.ctor_begin - header.load + index * 4)[0]
            reason = self._reject(address)
            if reason:
                self.rejected.append((address, index, reason))
            else:
                self.thunks.append((address, index))

    def _reject(self, address):
        if address == 0:
            return "null pointer"
        if address % 4:
            return "not 4-aligned"
        if not (self.header.load <= address <= self.header.load + len(self.data) - 4):
            return "outside the image [0x%x,0x%x)" % (self.header.load,
                                                      self.header.load + len(self.data))
        word = self.word(address)
        if word is None or not is_sane_instruction(word):
            return "does not decode as an instruction (0x%08x)" % (word or 0)
        return None


def load_overlay(path):
    with open(path, "rb") as f:
        return Overlay(path, f.read())


def scan(paths):
    """Every overlay's thunks, in table order, de-duplicated across overlays."""
    overlays = [load_overlay(path) for path in paths]
    found = collections.OrderedDict()
    for overlay in overlays:
        for address, index in overlay.thunks:
            found.setdefault(address, (overlay, index))
    return overlays, found


def classify(found, rows, known):
    """Split the thunks by what the map and the forced list already say about them.

    `row start` is the good case: the recompiler already emits a function there. `inside a row`
    means the address is covered but is not an entry, which the runtime cannot dispatch to; those
    and the uncovered ones are what has to be forced.
    """
    buckets = collections.OrderedDict(
        (key, []) for key in ("row start", "inside a row", "uncovered", "listed"))
    for address in found:
        if address in known:
            buckets["listed"].append(address)
        elif rows is not None and rows.is_start(address):
            buckets["row start"].append(address)
        elif rows is not None and rows.covers(address):
            buckets["inside a row"].append(address)
        else:
            buckets["uncovered"].append(address)
    return buckets


def missing(found, rows, known):
    """Thunks no forced list carries and no row starts: what a revision still needs."""
    out = []
    for address in found:
        if address in known:
            continue
        if rows is not None and rows.is_start(address):
            continue
        out.append(address)
    return sorted(out)


def comment(found, address):
    overlay, index = found[address]
    return "%s ctor thunk %d/%d (table 0x%x)" % (
        overlay.name, index, (overlay.header.ctor_end - overlay.header.ctor_begin) // 4,
        overlay.header.ctor_begin)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("overlay", nargs="+", help="MWo3 overlay images (ftscore.bin, zsealetc.bin)")
    parser.add_argument("--csv", default=None, help="the revision's function map")
    parser.add_argument("--extras", default=None, help="the revision's forced entry list")
    parser.add_argument("--append", default=None, help="append the missing addresses to this file")
    parser.add_argument("--header", default=None, help="header line to write above the block")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    overlays, found = scan(args.overlay)
    for overlay in overlays:
        print("%s: load 0x%x, ctor table [0x%x,0x%x), %d thunk(s), %d rejected"
              % (overlay.name, overlay.header.load, overlay.header.ctor_begin,
                 overlay.header.ctor_end, len(overlay.thunks), len(overlay.rejected)))
        for address, index, reason in overlay.rejected:
            print("    rejected 0x%08x (entry %d): %s" % (address, index, reason))

    rows = load_rows(args.csv) if args.csv else None
    known = load_known(args.extras)
    buckets = classify(found, rows, known)
    print("find_ctor_thunks: %d thunk(s); %s"
          % (len(found), ", ".join("%s=%d" % (k, len(v)) for k, v in buckets.items())))

    fresh = missing(found, rows, known)
    if not args.quiet:
        for address in fresh:
            print("0x%08x  # %s" % (address, comment(found, address)))

    if args.append and fresh:
        block = ""
        if args.header:
            block += args.header.rstrip("\n") + "\n"
        for address in fresh:
            block += "0x%08x  # %s\n" % (address, comment(found, address))
        with open(args.append, "a", encoding="utf-8", newline="\n") as f:
            f.write(block)
        print("appended %d address(es) to %s" % (len(fresh), args.append))
    return 0


if __name__ == "__main__":
    sys.exit(main())
