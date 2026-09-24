"""Wrap decrypted Metrowerks `MWo3` overlay dumps (and the boot ELF's own
segment) into a single synthetic MIPS ELF so that PS2Recomp / Ghidra can
consume them as one image.

Usage:
    python make_overlay_elf.py out.elf SCUS_972.75 ftscore.bin zsealetc.bin [DNAS.BIN]

Each overlay contributes one PT_LOAD (RWX) at its header load address; text
and data come from the file, bss is memsz - filesz.  Overlays that overlap
(DNAS vs zsealetc at 0x4c5380) cannot share one image: pass only one of them.

Every executable segment goes through tools_py/overlay_repair.py on the way in: the
r0004 overlay carries a foreign `jr $ra; nop` stub pair inside one function's epilogue,
over the two `lq` that restore $s0 and $s1 (see that module's header).  Pass
--no-repair to write the segments exactly as they were decrypted.
"""
import struct
import sys

try:
    from tools_py import overlay_repair
except ImportError:                                     # run as a script from tools_py/
    import overlay_repair


def mwo3_info(d):
    assert d[:4] == b'MWo3', "not an MWo3 overlay"
    ver, load, text, data, bss, ctor0, ctor1 = struct.unpack_from('<7I', d, 4)
    name = d[0x20:0x40].split(b'\0')[0].decode(errors='replace')
    return dict(load=load, text=text, data=data, bss=bss, ctor=(ctor0, ctor1), name=name, filesz=len(d),
                memsz=len(d) + bss)


def elf_segments(d):
    e_entry, e_phoff = struct.unpack_from('<II', d, 0x18)
    e_phnum = struct.unpack_from('<H', d, 0x2c)[0]
    segs = []
    for i in range(e_phnum):
        p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags = struct.unpack_from('<IIIIIII', d, e_phoff + i * 32)
        if p_type == 1 and p_filesz:
            segs.append((p_vaddr, d[p_offset:p_offset + p_filesz], p_memsz))
    return e_entry, segs


def build(out, elf_path, overlay_paths, loader_text_end=None, repair=True):
    """Segments get accurate flags so recompilers do not treat data as code:
    loader: [vaddr, loader_text_end) R-X, rest RW-;  overlay: header+text R-X, data+bss RW-."""
    elf = open(elf_path, 'rb').read()
    entry, segs = elf_segments(elf)
    loads = []
    for va, data, memsz in segs:
        if loader_text_end and va < loader_text_end < va + len(data):
            cut = loader_text_end - va
            loads.append((va, data[:cut], cut, 5, 'boot.text'))
            loads.append((va + cut, data[cut:], memsz - cut, 6, 'boot.data'))
        else:
            loads.append((va, data, memsz, 7, 'boot'))
    for p in overlay_paths:
        d = open(p, 'rb').read()
        info = mwo3_info(d)
        # Metrowerks places static-constructor code (__sinit_*) after rodata inside the "data"
        # part of the overlay, so the whole file image must stay executable.
        loads.append((info['load'], d, info['memsz'], 7, info['name']))
        print(f"{p}: {info['name']} @ {info['load']:#x} text {info['text']:#x} data {info['data']:#x} bss {info['bss']:#x}")
    loads.sort(key=lambda x: x[0])
    if repair:
        repaired_loads = []
        for va, data, memsz, flags, name in loads:
            if flags & 1:                                # executable: a stub write can hide in it
                data, repairs = overlay_repair.apply_repairs(data, va)
                for r in repairs:
                    print(f"repair {name}: {r.describe()}")
            repaired_loads.append((va, data, memsz, flags, name))
        loads = repaired_loads
    for (a, d1, m1, f1, n1), (b, d2, m2, f2, n2) in zip(loads, loads[1:]):
        if a + m1 > b:
            raise SystemExit(f"overlapping images {n1} and {n2}")
    phnum = len(loads)
    ehsize, phentsize = 52, 32
    off = ehsize + phentsize * phnum
    off = (off + 0xfff) & ~0xfff
    body = bytearray()
    phdrs = []
    for va, data, memsz, flags, name in loads:
        phdrs.append((1, off + len(body), va, va, len(data), memsz, flags, 0x1000))
        body += data
        body += bytes((-len(body)) % 16)
    hdr = bytearray(bytes.fromhex('7f454c46010101') + bytes(9))
    hdr += struct.pack('<HHIIIIIHHHHHH', 2, 8, 1, entry, ehsize, 0, 0x20924001, ehsize, phentsize, phnum, 0, 0, 0)
    for ph in phdrs:
        hdr += struct.pack('<8I', *ph)
    hdr += bytes(off - len(hdr))
    with open(out, 'wb') as f:
        f.write(hdr + body)
    print(f"wrote {out}: {phnum} segments, entry {entry:#x}")


if __name__ == '__main__':
    args = sys.argv[1:]
    lte = None
    repair = True
    while args and args[0].startswith('--'):
        if args[0].startswith('--loader-text-end='):
            lte = int(args.pop(0).split('=')[1], 16)
        elif args[0] == '--no-repair':
            args.pop(0)
            repair = False
        else:
            raise SystemExit(f"unknown option {args[0]}")
    build(args[0], args[1], args[2:], lte, repair)
