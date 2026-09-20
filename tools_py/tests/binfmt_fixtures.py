"""Sprint 9 Goal 2: the smallest PE and ELF files that carry an import list -- so the packaging tests can
build a fake dist/ whose executables really import what the test says, on any host, with no toolchain."""
import struct


def tiny_pe(imports):
    """A PE32+ image with one section holding an import directory that names `imports`. Not runnable."""
    table_len = 20 * (len(imports) + 1)
    names, offsets = b"", []
    for name in imports:
        offsets.append(table_len + len(names))
        names += name.encode("ascii") + b"\0"
    body = b"".join(struct.pack("<IIIII", 0, 0, 0, 0x1000 + off, 0) for off in offsets) + b"\0" * 20 + names
    dos = bytearray(64)
    dos[:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 64)
    coff = struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, 240, 0x22)
    opt = bytearray(240)
    struct.pack_into("<H", opt, 0, 0x20B)
    struct.pack_into("<I", opt, 108, 16)
    struct.pack_into("<II", opt, 112 + 8, 0x1000, table_len)
    section = b".idata\0\0" + struct.pack("<IIII", len(body), 0x1000, len(body), 0x200) + b"\0" * 16
    head = bytes(dos) + b"PE\0\0" + coff + bytes(opt) + section
    return head + b"\0" * (0x200 - len(head)) + body


def tiny_elf(needed):
    """A 64-bit little-endian ELF with a .dynstr and a .dynamic section naming `needed`. Not runnable."""
    strtab, offsets = b"\0", []
    for name in needed:
        offsets.append(len(strtab))
        strtab += name.encode("ascii") + b"\0"
    dynamic = b"".join(struct.pack("<qQ", 1, off) for off in offsets) + struct.pack("<qQ", 0, 0)
    str_off = 64
    dyn_off = str_off + len(strtab)
    sh_off = dyn_off + len(dynamic)

    def header(kind, offset, size, link=0):
        return struct.pack("<IIQQQQIIQQ", 0, kind, 0, 0, offset, size, link, 0, 1, 0)

    sections = header(0, 0, 0) + header(3, str_off, len(strtab)) + header(6, dyn_off, len(dynamic), link=1)
    ehdr = bytearray(64)
    ehdr[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", ehdr, 16, 3, 62, 1)
    struct.pack_into("<Q", ehdr, 0x28, sh_off)
    struct.pack_into("<HHHHHH", ehdr, 0x34, 64, 0, 0, 64, 3, 0)
    return bytes(ehdr) + strtab + dynamic + sections
