#!/usr/bin/env python3
"""Print the VU1 dispatcher header counts (TOP+2.z / TOP+2.w) of a set of program dumps.

The native dispatcher at entry pc 0x1b50 bounds every handler's loop with these two words --
TOP+2.z is the vertex count and TOP+2.w the triangle/primitive count -- and refuses a list whose
header is outside kMaxVertices / kMaxTriangles
(third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/socom2_dispatch_0x1b50.cpp). This scan is how
the margin those constants keep is documented from data rather than asserted.

    python -m tools_py.vu1_headers logs/vu1dump2/*.bin
    python -m tools_py.vu1_headers --all-entries logs/vu1dump3/*.bin

With --set-vertices / --set-triangles and --out it also writes a patched COPY of each dump, which
is how the ceilings' refusal path is tested: a dump whose TOP+2.z says 300 must be handed back
whole and still match an exact golden of the patched dump.

    python -m tools_py.vu1_headers --set-vertices 300 --out logs/vu1clamp \
        tests/fixtures/vu1/dispatch_0x1b50/vu1dump4_prog_11.bin

Dump layout (vu1_replay.cpp): uint32 startPc, top, itop, codeSize; 16 KB code; 16 KB data;
int32 vi[16]; float vf[32][4]. Words are read the way the microcode's ILW reads them: the low
16 bits of the word, sign-extended.
"""

import argparse
import glob
import os
import struct
import sys

HEADER_BYTES = 16
CODE_BYTES = 16 * 1024
DATA_BYTES = 16 * 1024
DISPATCH_ENTRY_PC = 0x1B50


def data_address(qword):
    """Vu1Gen::dataAddress: qword * 16, wrapped inside the 16 KB of VU1 data memory."""
    return (qword * 16) & 0x3FFF


def ilw(data, qword, component):
    """ILW <comp>: low 16 bits of one word of a qword, sign-extended."""
    off = data_address(qword) + component * 4
    (word,) = struct.unpack_from("<I", data, off)
    value = word & 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def patch_ilw(blob, qword, component, value):
    """Write the low 16 bits of one word of a data qword, leaving the high half alone -- ILW only
    ever reads the low half, so this is the smallest edit that changes what a handler loops on."""
    off = HEADER_BYTES + CODE_BYTES + data_address(qword) + component * 4
    (word,) = struct.unpack_from("<I", blob, off)
    word = (word & 0xFFFF0000) | (value & 0xFFFF)
    struct.pack_into("<I", blob, off, word)


def read_dump(path):
    with open(path, "rb") as handle:
        blob = handle.read()
    if len(blob) < HEADER_BYTES + CODE_BYTES + DATA_BYTES:
        raise ValueError("%s: too short to be a VU1 dump (%d bytes)" % (path, len(blob)))
    start_pc, top, itop, code_size = struct.unpack_from("<4I", blob, 0)
    data = blob[HEADER_BYTES + CODE_BYTES:HEADER_BYTES + CODE_BYTES + DATA_BYTES]
    return start_pc, top & 0x3FF, itop, code_size, data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dumps", nargs="+", help="vu1_prog_N.bin files (globs allowed)")
    parser.add_argument("--all-entries", action="store_true",
                        help="include dumps whose start pc is not 0x1b50 (skipped by default)")
    parser.add_argument("--quiet", action="store_true", help="print only the summary line")
    parser.add_argument("--set-vertices", type=int, default=None,
                        help="write a patched copy of each dump with TOP+2.z set to this")
    parser.add_argument("--set-triangles", type=int, default=None,
                        help="write a patched copy of each dump with TOP+2.w set to this")
    parser.add_argument("--out", default=None,
                        help="directory the patched copies go in (required with --set-*)")
    args = parser.parse_args(argv)
    patching = args.set_vertices is not None or args.set_triangles is not None
    if patching and not args.out:
        parser.error("--set-vertices / --set-triangles need --out")

    paths = []
    for pattern in args.dumps:
        expanded = sorted(glob.glob(pattern))
        paths.extend(expanded if expanded else [pattern])

    max_vertices = max_triangles = -1
    max_vertices_at = max_triangles_at = None
    scanned = skipped = 0
    for path in paths:
        try:
            start_pc, top, _itop, _code_size, data = read_dump(path)
        except (OSError, ValueError) as exc:
            print("SKIP %s (%s)" % (path, exc), file=sys.stderr)
            skipped += 1
            continue
        if start_pc != DISPATCH_ENTRY_PC and not args.all_entries:
            skipped += 1
            continue
        vertices = ilw(data, top + 2, 2)
        triangles = ilw(data, top + 2, 3)
        scanned += 1
        if vertices > max_vertices:
            max_vertices, max_vertices_at = vertices, path
        if triangles > max_triangles:
            max_triangles, max_triangles_at = triangles, path
        if not args.quiet:
            print("%s top=0x%03x startpc=0x%04x vertices=%d triangles=%d"
                  % (path, top, start_pc, vertices, triangles))
        if patching:
            os.makedirs(args.out, exist_ok=True)
            with open(path, "rb") as handle:
                blob = bytearray(handle.read())
            if args.set_vertices is not None:
                patch_ilw(blob, top + 2, 2, args.set_vertices)
            if args.set_triangles is not None:
                patch_ilw(blob, top + 2, 3, args.set_triangles)
            out_path = os.path.join(args.out, os.path.basename(path))
            with open(out_path, "wb") as handle:
                handle.write(blob)
            print("  -> %s vertices=%d triangles=%d"
                  % (out_path,
                     args.set_vertices if args.set_vertices is not None else vertices,
                     args.set_triangles if args.set_triangles is not None else triangles))

    if scanned == 0:
        print("no dumps scanned (%d skipped)" % skipped)
        return 1
    print("MAXIMA over %d dump(s) (%d skipped): vertices=%d (%s) triangles=%d (%s)"
          % (scanned, skipped, max_vertices, max_vertices_at, max_triangles, max_triangles_at))
    return 0


if __name__ == "__main__":
    sys.exit(main())
