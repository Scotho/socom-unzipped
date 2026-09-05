"""Map disc LBNs to file names (ISO9660) and annotate a run log's CD reads.

Usage:
  python tools_py/iso_lbn.py <image.iso> list                 # dump path -> lbn/size
  python tools_py/iso_lbn.py <image.iso> lookup <lbn> [...]   # resolve LBNs
  python tools_py/iso_lbn.py <image.iso> log <run.log>        # sequence of files touched by the
                                                              # `lbn=0x...` reads in a run log

Reads by LBN are how the SOCOM II engine loads everything (it builds its own TOC from the ISO), so
this is the cheapest way to see which screen assets (.zed/.rdr/.pss) a run reached.
"""
import re
import struct
import sys

SECTOR = 2048


def read_sector(f, lbn, count=1):
    f.seek(lbn * SECTOR)
    return f.read(count * SECTOR)


def parse_dir(f, extent, size, path, out):
    data = read_sector(f, extent, (size + SECTOR - 1) // SECTOR)[:size]
    pos = 0
    while pos < len(data):
        length = data[pos]
        if length == 0:
            pos = (pos // SECTOR + 1) * SECTOR  # skip to the next sector
            continue
        rec = data[pos:pos + length]
        ext = struct.unpack_from('<I', rec, 2)[0]
        sz = struct.unpack_from('<I', rec, 10)[0]
        flags = rec[25]
        name_len = rec[32]
        name = rec[33:33 + name_len]
        pos += length
        if name in (b'\x00', b'\x01'):
            continue
        name = name.decode('ascii', 'replace').split(';')[0]
        full = path + '/' + name
        if flags & 2:
            parse_dir(f, ext, sz, full, out)
        else:
            out.append((ext, sz, full))


def load(image):
    f = open(image, 'rb')
    pvd = read_sector(f, 16)
    assert pvd[1:6] == b'CD001', 'not an ISO9660 image'
    root = pvd[156:156 + 34]
    ext = struct.unpack_from('<I', root, 2)[0]
    sz = struct.unpack_from('<I', root, 10)[0]
    out = []
    parse_dir(f, ext, sz, '', out)
    out.sort()
    return out


def lookup(files, lbn):
    for ext, sz, name in files:
        if ext <= lbn < ext + max(1, (sz + SECTOR - 1) // SECTOR):
            return name, lbn - ext
    return None, 0


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    files = load(sys.argv[1])
    cmd = sys.argv[2]
    if cmd == 'list':
        for ext, sz, name in files:
            print(f'{ext:#09x} {sz:9d} {name}')
    elif cmd == 'lookup':
        for arg in sys.argv[3:]:
            lbn = int(arg, 0)
            name, off = lookup(files, lbn)
            print(f'{lbn:#x}: {name} +{off} sectors' if name else f'{lbn:#x}: (no file)')
    elif cmd == 'log':
        last = None
        count = 0
        for line in open(sys.argv[3], errors='replace'):
            m = re.search(r'lbn=(0x[0-9a-fA-F]+)', line)
            if not m:
                continue
            name, _ = lookup(files, int(m.group(1), 16))
            if name != last:
                if last is not None:
                    print(f'{last}  x{count}')
                last, count = name, 0
            count += 1
        if last is not None:
            print(f'{last}  x{count}')
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
