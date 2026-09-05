"""Minimal PS2 VU1 microcode disassembler (control-flow oriented).

Usage: python tools_py/vu1dis.py logs/frames/vu1_code.bin [start_hex] [end_hex]

Each 64-bit instruction pair is printed as  ADDR  upper | lower  with the E/D/T/M/I bits. Lower
ops are decoded fully enough to follow control flow (branches, XTOP/XITOP/XGKICK, ILW/ISW/LQ/SQ,
integer ALU); upper ops are decoded for the common FMAC families. Unknown encodings print raw.
"""
import struct
import sys

DEST = lambda d: ''.join(c for c, b in zip('xyzw', (8, 4, 2, 1)) if d & b) or '-'
BC = 'xyzw'


def signed(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def dis_lower(lo, pc):
    op = (lo >> 25) & 0x7F
    dest = (lo >> 21) & 0xF
    it = (lo >> 16) & 0x1F
    is_ = (lo >> 11) & 0x1F
    id_ = (lo >> 6) & 0x1F
    imm11 = signed(lo & 0x7FF, 11)
    imm15 = ((lo >> 10) & 0x7800) | (lo & 0x7FF)
    target = pc + 8 + imm11 * 8
    if op == 0x40:
        funct = lo & 0x3F
        if funct < 0x3C:
            alu = {0x30: 'IADD', 0x31: 'ISUB', 0x32: 'IADDI', 0x34: 'IAND', 0x35: 'IOR'}.get(funct)
            if funct == 0x32:
                return f'IADDI vi{it}, vi{is_}, {signed(id_, 5)}'
            if alu:
                return f'{alu} vi{id_}, vi{is_}, vi{it}'
            return f'special.{funct:02x} {lo:08x}'
        f2 = (lo & 3) | ((lo >> 4) & 0x7C)
        table = {
            0x30: ('MOVE', 'f'), 0x31: ('MR32', 'f'), 0x34: ('LQI', 'lqi'), 0x35: ('SQI', 'sqi'),
            0x36: ('LQD', 'lqd'), 0x37: ('SQD', 'sqd'), 0x38: ('DIV', 'q'), 0x39: ('SQRT', 'q'),
            0x3A: ('RSQRT', 'q'), 0x3B: ('WAITQ', ''), 0x3C: ('MTIR', 'mtir'), 0x3D: ('MFIR', 'mfir'),
            0x3E: ('ILWR', 'ilwr'), 0x3F: ('ISWR', 'iswr'), 0x40: ('RNEXT', 'r'), 0x41: ('RGET', 'r'),
            0x42: ('RINIT', 'ri'), 0x43: ('RXOR', 'ri'), 0x64: ('MFP', 'mfp'), 0x68: ('XTOP', 'xt'),
            0x69: ('XITOP', 'xt'), 0x6C: ('XGKICK', 'xg'), 0x70: ('ESADD', 'e'), 0x71: ('ERSADD', 'e'),
            0x72: ('ELENG', 'e'), 0x73: ('ERLENG', 'e'), 0x74: ('EATANxy', 'e'), 0x75: ('EATANxz', 'e'),
            0x76: ('ESUM', 'e'), 0x78: ('ESQRT', 'e'), 0x79: ('ERSQRT', 'e'), 0x7A: ('ERCPR', 'e'),
            0x7B: ('WAITP', ''), 0x7C: ('ESIN', 'e'), 0x7D: ('EATAN', 'e'), 0x7E: ('EEXP', 'e'),
        }
        if f2 not in table:
            return f'special2.{f2:02x} {lo:08x}'
        name, kind = table[f2]
        if lo == 0x8000033C:
            return 'NOP'
        if kind == 'f':
            return f'{name}.{DEST(dest)} vf{it}, vf{is_}'
        if kind in ('lqi', 'lqd'):
            return f'{name}.{DEST(dest)} vf{it}, (vi{is_}{"++" if kind == "lqi" else "--"})'
        if kind in ('sqi', 'sqd'):
            return f'{name}.{DEST(dest)} vf{is_}, (vi{it}{"++" if kind == "sqi" else "--"})'
        if kind == 'q':
            fsf = (lo >> 21) & 3
            ftf = (lo >> 23) & 3
            return f'{name} Q, vf{is_}.{BC[fsf]}, vf{it}.{BC[ftf]}'
        if kind == 'mtir':
            return f'MTIR vi{it}, vf{is_}.{BC[(lo >> 21) & 3]}'
        if kind == 'mfir':
            return f'MFIR.{DEST(dest)} vf{it}, vi{is_}'
        if kind == 'ilwr':
            return f'ILWR.{DEST(dest)} vi{it}, (vi{is_})'
        if kind == 'iswr':
            return f'ISWR.{DEST(dest)} vi{it}, (vi{is_})'
        if kind == 'xt':
            return f'{name} vi{it}'
        if kind == 'xg':
            return f'XGKICK vi{is_}'
        if kind == 'mfp':
            return f'MFP.{DEST(dest)} vf{it}, P'
        if kind == 'e':
            return f'{name} P, vf{is_}'
        if kind == 'r':
            return f'{name}.{DEST(dest)} vf{it}, R'
        if kind == 'ri':
            return f'{name} R, vf{is_}.{BC[(lo >> 21) & 3]}'
        return name
    if op == 0x00:
        return f'LQ.{DEST(dest)} vf{it}, {imm11}(vi{is_})'
    if op == 0x01:
        return f'SQ.{DEST(dest)} vf{is_}, {imm11}(vi{it})'
    if op == 0x04:
        return f'ILW.{DEST(dest)} vi{it}, {imm11}(vi{is_})'
    if op == 0x05:
        return f'ISW.{DEST(dest)} vi{it}, {imm11}(vi{is_})'
    if op == 0x08:
        return f'IADDIU vi{it}, vi{is_}, {imm15}'
    if op == 0x09:
        return f'ISUBIU vi{it}, vi{is_}, {imm15}'
    if op == 0x10:
        return f'FCEQ vi1, {lo & 0xFFFFFF:#x}'
    if op == 0x11:
        return f'FCSET {lo & 0xFFFFFF:#x}'
    if op == 0x12:
        return f'FCAND vi1, {lo & 0xFFFFFF:#x}'
    if op == 0x13:
        return f'FCOR vi1, {lo & 0xFFFFFF:#x}'
    if op == 0x14:
        return f'FSEQ vi{it}, {lo & 0xFFF:#x}'
    if op == 0x15:
        return f'FSSET {lo & 0xFFF:#x}'
    if op == 0x16:
        return f'FSAND vi{it}, {lo & 0xFFF:#x}'
    if op == 0x17:
        return f'FSOR vi{it}, {lo & 0xFFF:#x}'
    if op == 0x18:
        return f'FMEQ vi{it}, vi{is_}'
    if op == 0x1A:
        return f'FMAND vi{it}, vi{is_}'
    if op == 0x1B:
        return f'FMOR vi{it}, vi{is_}'
    if op == 0x1C:
        return f'FCGET vi{it}'
    if op == 0x20:
        return f'B {target:#x}'
    if op == 0x21:
        return f'BAL vi{it}, {target:#x}'
    if op == 0x24:
        return f'JR vi{is_}'
    if op == 0x25:
        return f'JALR vi{it}, vi{is_}'
    if op == 0x28:
        return f'IBEQ vi{it}, vi{is_}, {target:#x}'
    if op == 0x29:
        return f'IBNE vi{it}, vi{is_}, {target:#x}'
    if op == 0x2C:
        return f'IBLTZ vi{is_}, {target:#x}'
    if op == 0x2D:
        return f'IBGTZ vi{is_}, {target:#x}'
    if op == 0x2E:
        return f'IBLEZ vi{is_}, {target:#x}'
    if op == 0x2F:
        return f'IBGEZ vi{is_}, {target:#x}'
    return f'lower.{op:02x} {lo:08x}'


def dis_upper(up):
    dest = (up >> 21) & 0xF
    ft = (up >> 16) & 0x1F
    fs = (up >> 11) & 0x1F
    fd = (up >> 6) & 0x1F
    funct = up & 0x3F
    bc = BC[up & 3]
    if funct < 0x30:
        fam = funct >> 2
        kind = funct & 3
        names = ['ADD', 'SUB', 'MADD', 'MSUB', 'MAX', 'MINI', 'MUL']
        if fam <= 6:
            return f'{names[fam]}{bc}.{DEST(dest)} vf{fd}, vf{fs}, vf{ft}.{bc}'
        table = {0x1C: 'MULq', 0x1D: 'MAXi', 0x1E: 'MULi', 0x1F: 'MINIi', 0x20: 'ADDq', 0x21: 'MADDq',
                 0x22: 'ADDi', 0x23: 'MADDi', 0x24: 'SUBq', 0x25: 'MSUBq', 0x26: 'SUBi', 0x27: 'MSUBi',
                 0x28: 'ADD', 0x29: 'MADD', 0x2A: 'MUL', 0x2B: 'MAX', 0x2C: 'SUB', 0x2D: 'MSUB', 0x2E: 'OPMSUB', 0x2F: 'MINI'}
        name = table.get(funct, f'upper.{funct:02x}')
        if funct >= 0x28:
            return f'{name}.{DEST(dest)} vf{fd}, vf{fs}, vf{ft}'
        return f'{name}.{DEST(dest)} vf{fd}, vf{fs}'
    f2 = (up & 3) | ((up >> 4) & 0x7C)
    table = {
        0x00: 'ADDAx', 0x01: 'ADDAy', 0x02: 'ADDAz', 0x03: 'ADDAw', 0x04: 'SUBAx', 0x05: 'SUBAy', 0x06: 'SUBAz', 0x07: 'SUBAw',
        0x08: 'MADDAx', 0x09: 'MADDAy', 0x0A: 'MADDAz', 0x0B: 'MADDAw', 0x0C: 'MSUBAx', 0x0D: 'MSUBAy', 0x0E: 'MSUBAz', 0x0F: 'MSUBAw',
        0x10: 'ITOF0', 0x11: 'ITOF4', 0x12: 'ITOF12', 0x13: 'ITOF15', 0x14: 'FTOI0', 0x15: 'FTOI4', 0x16: 'FTOI12', 0x17: 'FTOI15',
        0x18: 'MULAx', 0x19: 'MULAy', 0x1A: 'MULAz', 0x1B: 'MULAw', 0x1C: 'MULAq', 0x1D: 'ABS', 0x1E: 'MULAi', 0x1F: 'CLIP',
        0x20: 'ADDAq', 0x21: 'MADDAq', 0x22: 'ADDAi', 0x23: 'MADDAi', 0x24: 'SUBAq', 0x25: 'MSUBAq', 0x26: 'SUBAi', 0x27: 'MSUBAi',
        0x28: 'ADDA', 0x29: 'MADDA', 0x2A: 'MULA', 0x2B: 'NOP', 0x2C: 'SUBA', 0x2D: 'MSUBA', 0x2E: 'OPMULA', 0x2F: 'NOP',
    }
    name = table.get(f2, f'upper2.{f2:02x}')
    if name == 'NOP':
        return 'NOP'
    if name.startswith(('ITOF', 'FTOI', 'ABS')):
        return f'{name}.{DEST(dest)} vf{ft}, vf{fs}'
    return f'{name}.{DEST(dest)} vf{fs}, vf{ft}'


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    code = open(sys.argv[1], 'rb').read()
    start = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0
    end = int(sys.argv[3], 16) if len(sys.argv) > 3 else len(code)
    for pc in range(start, min(end, len(code)), 8):
        lo, up = struct.unpack_from('<II', code, pc)
        flags = ''.join(c for c, b in (('I', 1 << 31), ('E', 1 << 30), ('M', 1 << 29), ('D', 1 << 28), ('T', 1 << 27)) if up & b)
        if up & (1 << 31):  # I bit: lower word is an immediate
            lower = f'LOI {struct.unpack("<f", struct.pack("<I", lo))[0]:g} ({lo:08x})'
        else:
            lower = dis_lower(lo, pc)
        print(f'{pc:05x}  {flags:5s} {dis_upper(up & 0x07FFFFFF):40s} | {lower}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
