#!/usr/bin/env python
"""Print a parsed .rdr tree from a guest RAM dump (PS2X_RDRAM_DUMP=<file>:<seconds>).

Node = 8 bytes {u8 type, u8 pad, u16 count, u32 value}; type 1 int, 2 float, 3 string (value = char*),
4 list (value = node* array of `count` nodes).  Usage:
  python tools_py/rdr_tree.py <rdram.bin> <hex node address> [max depth]
"""
import struct, sys

def load(path):
    return open(path, 'rb').read()

def node(mem, a):
    t, _, n, v = struct.unpack_from('<BBHI', mem, a & 0x1ffffff)
    return t, n, v

def cstr(mem, a, limit=200):
    a &= 0x1ffffff
    e = mem.find(b'\0', a, a + limit)
    return mem[a:e if e >= 0 else a + limit].decode('latin-1')

def fmt(mem, a, depth=0, maxdepth=8, out=None, limit=4000):
    t, n, v = node(mem, a)
    pad = '  ' * depth
    if t == 1:
        out.append(f'{pad}[{a:08x}] int {struct.unpack("<i", struct.pack("<I", v))[0]}')
    elif t == 2:
        out.append(f'{pad}[{a:08x}] float {struct.unpack("<f", struct.pack("<I", v))[0]:g}')
    elif t == 3:
        out.append(f'{pad}[{a:08x}] str "{cstr(mem, v)}" @{v:08x}')
    elif t == 4:
        out.append(f'{pad}[{a:08x}] list n={n} @{v:08x}')
        if depth < maxdepth and v:
            for i in range(n):
                if len(out) > limit:
                    out.append(f'{pad}  ...'); break
                fmt(mem, v + i * 8, depth + 1, maxdepth, out, limit)
    else:
        out.append(f'{pad}[{a:08x}] type {t} n={n} v={v:08x}')
    return out

if __name__ == '__main__':
    mem = load(sys.argv[1])
    a = int(sys.argv[2], 16)
    md = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    print('\n'.join(fmt(mem, a, 0, md, [])))
