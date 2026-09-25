#!/usr/bin/env python
"""Minimal VU0/VU1 micro-program disassembler.

Run: python -m tools_py.vu1dis <dump.bin|code.bin> [--start 0xPC] [--count N] [--raw]
  dump.bin  = logs/vu1dump/vu1_prog_N.bin written by PS2X_VU1_DUMP (16-byte header + 16 KB code + ...)
  --raw     = the file is bare micro code
Prints "addr: upper-insn | lower-insn" per 64-bit pair, with the E/M/D/T/I bits as suffixes.
"""
import argparse
import struct
import sys

DEST = "xyzw"


def dest(i):
    d = (i >> 21) & 0xF
    return "".join(DEST[k] for k in range(4) if d & (8 >> k))


def bc(i):
    return DEST[i & 3]


def ft(i): return (i >> 16) & 0x1F
def fs(i): return (i >> 11) & 0x1F
def fd(i): return (i >> 6) & 0x1F
def it(i): return (i >> 16) & 0xF
def is_(i): return (i >> 11) & 0xF
def id_(i): return (i >> 6) & 0xF


def imm11(i):
    v = i & 0x7FF
    return v - 0x800 if v & 0x400 else v


def imm15(i):
    v = (i & 0x7FF) | (((i >> 21) & 0xF) << 11)
    return v


UPPER_BC = {0: "ADD", 1: "SUB", 2: "MADD", 3: "MSUB", 4: "MAX", 5: "MINI", 6: "MUL"}
UPPER_SIMPLE = {0x1C: "MULq", 0x1D: "MAXi", 0x1E: "MULi", 0x1F: "MINIi", 0x20: "ADDq", 0x21: "MADDq", 0x22: "ADDi",
                0x23: "MADDi", 0x24: "SUBq", 0x25: "MSUBq", 0x26: "SUBi", 0x27: "MSUBi", 0x28: "ADD", 0x29: "MADD",
                0x2A: "MUL", 0x2B: "MAX", 0x2C: "SUB", 0x2D: "MSUB", 0x2E: "OPMSUB", 0x2F: "MINI"}
SPECIAL_BC = {0: "ADDA", 1: "SUBA", 2: "MADDA", 3: "MSUBA", 6: "MULA"}
SPECIAL = {0x10: "ITOF0", 0x11: "ITOF4", 0x12: "ITOF12", 0x13: "ITOF15", 0x14: "FTOI0", 0x15: "FTOI4", 0x16: "FTOI12",
           0x17: "FTOI15", 0x1C: "MULAq", 0x1D: "ABS", 0x1E: "MULAi", 0x1F: "CLIP", 0x20: "ADDAq", 0x21: "MADDAq",
           0x22: "ADDAi", 0x23: "MADDAi", 0x24: "SUBAq", 0x25: "MSUBAq", 0x26: "SUBAi", 0x27: "MSUBAi", 0x28: "ADDA",
           0x29: "MADDA", 0x2A: "MULA", 0x2B: "NOP", 0x2C: "SUBA", 0x2D: "MSUBA", 0x2E: "OPMULA", 0x2F: "NOP"}


def dis_upper(i):
    op = i & 0x3F
    d = dest(i)
    if op < 0x1C:
        name = UPPER_BC[op >> 2] + bc(i)
        return f"{name}.{d} vf{fd(i)}, vf{fs(i)}, vf{ft(i)}{bc(i)}"
    if op < 0x3C:
        name = UPPER_SIMPLE[op]
        if name.endswith("q") or name.endswith("i"):
            src = "Q" if name.endswith("q") else "I"
            return f"{name}.{d} vf{fd(i)}, vf{fs(i)}, {src}"
        return f"{name}.{d} vf{fd(i)}, vf{fs(i)}, vf{ft(i)}"
    sub = ((i >> 6) & 0x1F) << 2 | (op & 3)
    if sub < 0x10 or 0x18 <= sub < 0x1C:
        name = SPECIAL_BC[sub >> 2] + bc(i)
        return f"{name}.{d} ACC, vf{fs(i)}, vf{ft(i)}{bc(i)}"
    name = SPECIAL.get(sub, f"UPPER?{sub:02x}")
    if name.startswith("ITOF") or name.startswith("FTOI") or name == "ABS":
        return f"{name}.{d} vf{ft(i)}, vf{fs(i)}"
    if name == "CLIP":
        return f"CLIPw.xyz vf{fs(i)}, vf{ft(i)}w"
    if name == "NOP":
        return "NOP"
    if name.endswith("q") or name.endswith("i"):
        src = "Q" if name.endswith("q") else "I"
        return f"{name}.{d} ACC, vf{fs(i)}, {src}"
    return f"{name}.{d} ACC, vf{fs(i)}, vf{ft(i)}"


LOWER_OPS = {0x00: "LQ", 0x01: "SQ", 0x04: "ILW", 0x05: "ISW", 0x08: "IADDIU", 0x09: "ISUBIU", 0x10: "FCEQ",
             0x11: "FCSET", 0x12: "FCAND", 0x13: "FCOR", 0x14: "FSEQ", 0x15: "FSSET", 0x16: "FSAND", 0x17: "FSOR",
             0x18: "FMEQ", 0x1A: "FMAND", 0x1B: "FMOR", 0x1C: "FCGET", 0x20: "B", 0x21: "BAL", 0x24: "JR",
             0x25: "JALR", 0x28: "IBEQ", 0x29: "IBNE", 0x2C: "IBLTZ", 0x2D: "IBGTZ", 0x2E: "IBLEZ", 0x2F: "IBGEZ"}
LOWER_SPECIAL = {0x30: "IADD", 0x31: "ISUB", 0x32: "IADDI", 0x34: "IAND", 0x35: "IOR"}
LOWER_EXT = {0x30: "MOVE", 0x31: "MR32", 0x34: "LQI", 0x35: "SQI", 0x36: "LQD", 0x37: "SQD", 0x38: "DIV", 0x39: "SQRT",
             0x3A: "RSQRT", 0x3B: "WAITQ", 0x3C: "MTIR", 0x3D: "MFIR", 0x3E: "ILWR", 0x3F: "ISWR", 0x40: "RNEXT",
             0x41: "RGET", 0x42: "RINIT", 0x43: "RXOR", 0x64: "MFP", 0x68: "XTOP", 0x69: "XITOP", 0x6C: "XGKICK",
             0x70: "ESADD", 0x71: "ERSADD", 0x72: "ELENG", 0x73: "ERLENG", 0x74: "EATANxy", 0x75: "EATANxz",
             0x76: "ESUM", 0x78: "ERCPR", 0x79: "ESQRT", 0x7A: "ERSQRT", 0x7B: "WAITP", 0x7C: "ESIN", 0x7D: "EATAN",
             0x7E: "EEXP"}


def dis_lower(i, pc):
    op = (i >> 25) & 0x7F
    d = dest(i)
    if op == 0x40:
        low = i & 0x3F
        if low < 0x3C:
            name = LOWER_SPECIAL.get(low, f"LOW?{low:02x}")
            if name == "IADDI":
                v = (i >> 6) & 0x1F
                v = v - 32 if v & 0x10 else v
                return f"IADDI vi{it(i)}, vi{is_(i)}, {v}"
            return f"{name} vi{id_(i)}, vi{is_(i)}, vi{it(i)}"
        ext = ((i >> 6) & 0x1F) << 2 | (low & 3)
        name = LOWER_EXT.get(ext, f"EXT?{ext:02x}")
        fsf = DEST[(i >> 21) & 3]
        ftf = DEST[(i >> 23) & 3]
        if name in ("DIV", "RSQRT"):
            return f"{name} Q, vf{fs(i)}{fsf}, vf{ft(i)}{ftf}"
        if name == "SQRT":
            return f"SQRT Q, vf{ft(i)}{ftf}"
        if name in ("MOVE", "MR32"):
            return f"{name}.{d} vf{ft(i)}, vf{fs(i)}"
        if name in ("LQI", "LQD"):
            return f"{name}.{d} vf{ft(i)}, (vi{is_(i)}{'++' if name == 'LQI' else '--'})"
        if name in ("SQI", "SQD"):
            return f"{name}.{d} vf{fs(i)}, (vi{it(i)}{'++' if name == 'SQI' else '--'})"
        if name == "MTIR":
            return f"MTIR vi{it(i)}, vf{fs(i)}{fsf}"
        if name == "MFIR":
            return f"MFIR.{d} vf{ft(i)}, vi{is_(i)}"
        if name == "ILWR":
            return f"ILWR.{d} vi{it(i)}, (vi{is_(i)})"
        if name == "ISWR":
            return f"ISWR.{d} vi{it(i)}, (vi{is_(i)})"
        if name in ("XTOP", "XITOP"):
            return f"{name} vi{it(i)}"
        if name == "XGKICK":
            return f"XGKICK vi{is_(i)}"
        if name in ("RNEXT", "RGET"):
            return f"{name}.{d} vf{ft(i)}, R"
        if name in ("RINIT", "RXOR"):
            return f"{name} R, vf{fs(i)}{fsf}"
        if name == "MFP":
            return f"MFP.{d} vf{ft(i)}, P"
        if name in ("WAITQ", "WAITP"):
            return name
        if name in ("ESADD", "ERSADD", "ELENG", "ERLENG", "ESUM"):
            return f"{name} P, vf{fs(i)}"
        if name in ("EATANxy", "EATANxz"):
            return f"{name} P, vf{fs(i)}"
        return f"{name} P, vf{fs(i)}{fsf}"
    name = LOWER_OPS.get(op, f"LOW?{op:02x}")
    if name in ("LQ", "SQ"):
        v = imm11(i)
        if name == "LQ":
            return f"LQ.{d} vf{ft(i)}, {v}(vi{is_(i)})"
        return f"SQ.{d} vf{fs(i)}, {v}(vi{it(i)})"
    if name in ("ILW", "ISW"):
        return f"{name}.{d} vi{it(i)}, {imm11(i)}(vi{is_(i)})"
    if name in ("IADDIU", "ISUBIU"):
        return f"{name} vi{it(i)}, vi{is_(i)}, {imm15(i)}"
    if name in ("FCEQ", "FCSET", "FCAND", "FCOR"):
        return f"{name} vi1, 0x{i & 0xFFFFFF:06x}"
    if name in ("FSEQ", "FSSET", "FSAND", "FSOR"):
        return f"{name} vi{it(i)}, 0x{(i & 0x7FF) | (((i >> 21) & 1) << 11):03x}"
    if name in ("FMEQ", "FMAND", "FMOR"):
        return f"{name} vi{it(i)}, vi{is_(i)}"
    if name == "FCGET":
        return f"FCGET vi{it(i)}"
    if name in ("B", "BAL"):
        target = (pc + 8 + imm11(i) * 8) & 0x3FFF
        return f"{name} {'vi' + str(it(i)) + ', ' if name == 'BAL' else ''}0x{target:x}"
    if name in ("JR", "JALR"):
        return f"{name} {'vi' + str(it(i)) + ', ' if name == 'JALR' else ''}vi{is_(i)}"
    target = (pc + 8 + imm11(i) * 8) & 0x3FFF
    if name in ("IBEQ", "IBNE"):
        return f"{name} vi{it(i)}, vi{is_(i)}, 0x{target:x}"
    return f"{name} vi{is_(i)}, 0x{target:x}"


def disassemble(code, start=0, count=None, base=0):
    n = len(code) // 8
    out = []
    end = n if count is None else min(n, start // 8 + count)
    for k in range(start // 8, end):
        lo, up = struct.unpack_from("<II", code, k * 8)
        pc = k * 8
        flags = "".join(f for f, bit in (("I", 31), ("E", 30), ("M", 29), ("D", 28), ("T", 27)) if up & (1 << bit))
        if up & 0x80000000:
            lower = f"LOI {struct.unpack('<f', struct.pack('<I', lo))[0]:g} (0x{lo:08x})"
        else:
            lower = dis_lower(lo, pc)
        out.append(f"{pc:04x}: {dis_upper(up & 0x07FFFFFF):<40s} | {lower:<40s} {flags}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--start", default="0")
    ap.add_argument("--count", type=int, default=None)
    ap.add_argument("--raw", action="store_true")
    a = ap.parse_args()
    data = open(a.file, "rb").read()
    if a.raw:
        code = data
    else:
        pc, top, itop, codeSize = struct.unpack_from("<IIII", data, 0)
        code = data[16:16 + 0x4000]
        print(f"# start pc=0x{pc:x} top=0x{top:x} itop=0x{itop:x} codeSize=0x{codeSize:x}")
    start = int(a.start, 0)
    for line in disassemble(code, start, a.count):
        print(line)


if __name__ == "__main__":
    main()
