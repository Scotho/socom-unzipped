"""Sprint 11 Task 7 (U3): the function table of an ELF that still has its `.symtab`.

The SOCOM 1 demo (`SCUS_972.05`) was shipped with its Metrowerks debug build intact: a 350 KB `.symtab`
naming 9,703 functions with an address and a size each, and a 5 MB `.debug` section in Metrowerks'
own DWARF1-ish format. Step 3 of the task needs a name, a start and an end per function -- which is
exactly what the symbol table holds -- so nothing here touches `.debug`, and no Ghidra import is needed
to read it.

    from tools_py.elf_symbols import read_elf
    elf = read_elf("game/demo_scus_972_05/SCUS_972.05")
    elf.functions      # [(start, end, name)], sorted, the same shape as tools_py/address_matcher.Func
    elf.segments       # [(vaddr, bytes)] for every PT_LOAD -- what Image.of() wants
    elf.relocations()  # [(offset, type, symbol index)] from the SHT_REL sections, if any

A note on "relocatable": the demo keeps a `.relmain` section (SHT_REL, 115,142 entries) next to its code,
which is what a Metrowerks PS2 link leaves behind, but the file is still `ET_EXEC` with its `main`
section at 0x100000 and symbol values are absolute guest addresses. So the symbol addresses need no
bias. `.relmain` is still useful as a second opinion on which words carry an address -- see
`relocated_words()`, used to check the fingerprint's mask covers them.
"""
import os
import struct
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

STT_FUNC, STT_OBJECT = 2, 1
SHT_SYMTAB, SHT_STRTAB, SHT_REL = 2, 3, 9
PT_LOAD = 1


class Section(NamedTuple):
    name: str
    type: int
    flags: int
    addr: int
    offset: int
    size: int
    link: int
    info: int
    entsize: int


class Symbol(NamedTuple):
    name: str
    value: int
    size: int
    info: int
    shndx: int

    @property
    def kind(self) -> int:
        return self.info & 0xF


class Elf(NamedTuple):
    data: bytes
    e_type: int
    e_machine: int
    entry: int
    sections: List[Section]
    segments: List[Tuple[int, bytes]]
    symbols: List[Symbol]

    @property
    def functions(self) -> List[Tuple[int, int, str]]:
        """(start, end, name) for every sized, NAMED STT_FUNC symbol, sorted, duplicate addresses
        dropped.

        A zero-size FUNC symbol has no body to fingerprint, so it is left out rather than emitted with
        an empty range: an empty body would hash to the FNV basis and file every one of them under a
        single value. The demo happens to have none, which is itself worth knowing.
        """
        seen: Dict[int, Tuple[int, int, str]] = {}
        for s in self.symbols:
            if s.kind != STT_FUNC or s.size <= 0 or not s.name:
                continue
            seen.setdefault(s.value, (s.value, s.value + s.size, s.name))
        return sorted(seen.values())

    @property
    def objects(self) -> List[Tuple[int, int, str]]:
        """The same for STT_OBJECT -- the named globals that have a size.

        Two different measurements live here and they must not be conflated: the demo's `.symtab`
        holds **10,182 STT_OBJECT entries**, of which **10,179 are sized** and therefore appear below.
        `main()` prints both, which is where §1 of `docs/research/44-demo-symbols.md` gets them. A
        zero-size global has no extent to attach a name to, exactly as a zero-size FUNC has no body.
        These are the obvious next lever after the functions: a named global names a data structure.
        """
        out = [(s.value, s.value + s.size, s.name) for s in self.symbols
               if s.kind == STT_OBJECT and s.size > 0 and s.name]
        return sorted(out)

    def census(self) -> Dict[str, int]:
        """{symbols, func_entries, object_entries} -- the RAW symbol table counts, unfiltered."""
        return {"symbols": len(self.symbols),
                "func_entries": sum(1 for s in self.symbols if s.kind == STT_FUNC),
                "object_entries": sum(1 for s in self.symbols if s.kind == STT_OBJECT)}

    def section(self, name: str) -> Optional[Section]:
        for s in self.sections:
            if s.name == name:
                return s
        return None

    def relocations(self) -> List[Tuple[int, int, int]]:
        """(r_offset, r_type, r_symbol) from every SHT_REL section, in file order.

        `r_symbol` indexes `symbols`, which is why `parse_elf` keeps unnamed and section symbols as
        placeholder entries: dropping them would silently shift every index past the first hole.
        """
        out = []
        for sec in self.sections:
            if sec.type != SHT_REL or sec.entsize != 8:
                continue
            for i in range(sec.size // 8):
                off, info = _unpack("<II", self.data, sec.offset + i * 8,
                                    "%s entry %d" % (sec.name or "rel", i))
                out.append((off, info & 0xFF, info >> 8))
        return out

    def relocated_words(self) -> set:
        """The guest addresses of the words a relocation touches.

        `r_offset` in a linked Metrowerks image is already the guest address of the word (it lands
        inside the loaded range), so this is a set of addresses, aligned down to the instruction.
        Containment is tested per segment, not against the global lowest/highest: our own image has
        four PT_LOADs with gaps between them (0x100000, 0x1D5000, 0x1E7000, 0x4C5380), and a global
        bound would count those gaps as loaded.
        """
        def loaded(addr: int) -> bool:
            return any(v <= addr < v + len(d) for v, d in self.segments)

        return {off & ~3 for off, _t, _s in self.relocations() if loaded(off)}


def _unpack(fmt: str, data: bytes, offset: int, what: str):
    """`struct.unpack_from`, but a short read is a ValueError that says which table ran out.

    `struct.error` is NOT a subclass of ValueError, so an `except ValueError` around a parse does not
    catch it and a truncated file comes out as a traceback. Every unpack in this module goes through
    here so that a malformed ELF is one sentence, whoever is reading it.
    """
    width = struct.calcsize(fmt)
    if offset < 0 or offset + width > len(data):
        raise ValueError("%s: %d bytes at 0x%x run past the end of the %d-byte file"
                         % (what, width, offset, len(data)))
    return struct.unpack_from(fmt, data, offset)


def _cstr(data: bytes, base: int, offset: int, what: str = "string table") -> str:
    start = base + offset
    end = data.find(b"\x00", start) if 0 <= start <= len(data) else -1
    if end < 0:
        raise ValueError("%s: entry at 0x%x+0x%x is not a NUL-terminated string inside the "
                         "%d-byte file" % (what, base, offset, len(data)))
    return data[start:end].decode("latin-1")


def parse_elf(data: bytes) -> Elf:
    """Parse a little-endian ELF32 far enough to hand back its sections, PT_LOADs and symbols.

    Every way this can fail on a malformed file is a `ValueError` naming the table that ran out --
    never a `struct.error` or an `IndexError`. `main()` and `ghidra_symbol_match.main()` both turn
    that into one line and exit 2.
    """
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF file")
    if data[4] != 1 or data[5] != 1:
        raise ValueError("expected a little-endian ELF32")
    e_type, e_machine = _unpack("<HH", data, 16, "ELF header")
    entry, phoff, shoff = _unpack("<III", data, 24, "ELF header")
    phentsize, phnum, shentsize, shnum, shstrndx = _unpack("<HHHHH", data, 42, "ELF header")

    raw = [_unpack("<10I", data, shoff + i * shentsize, "section header %d" % i)
           for i in range(shnum)]
    if shnum and shstrndx >= shnum:
        raise ValueError("section header table: e_shstrndx %d is past the %d section headers"
                         % (shstrndx, shnum))
    shstr = raw[shstrndx][4] if shnum else 0
    sections = [Section(_cstr(data, shstr, r[0], "section name table"),
                        r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[9]) for r in raw]

    segments = []
    for i in range(phnum):
        p_type, off, vaddr, _paddr, filesz = _unpack("<5I", data, phoff + i * phentsize,
                                                     "program header %d" % i)
        if p_type == PT_LOAD and filesz:
            if off + filesz > len(data):
                raise ValueError("program header %d: %d bytes at 0x%x run past the end of the "
                                 "%d-byte file" % (i, filesz, off, len(data)))
            segments.append((vaddr, data[off:off + filesz]))

    symbols: List[Symbol] = []
    for sec in sections:
        if sec.type != SHT_SYMTAB or sec.entsize != 16:
            continue
        if sec.link >= len(sections):
            raise ValueError("%s: sh_link %d is past the %d section headers"
                             % (sec.name or "symbol table", sec.link, len(sections)))
        strtab = sections[sec.link].offset
        for i in range(sec.size // 16):
            st_name, st_value, st_size, st_info, _other, st_shndx = _unpack(
                "<IIIBBH", data, sec.offset + i * 16, "%s entry %d" % (sec.name or "symtab", i))
            # Every entry is kept, named or not: a relocation's `r_symbol` is an INDEX into this
            # list, and dropping the unnamed and section symbols would shift every index past the
            # first hole. `functions` and `objects` do the filtering instead.
            symbols.append(Symbol(_cstr(data, strtab, st_name, "%s string table" % (sec.name or "")),
                                  st_value, st_size, st_info, st_shndx))
    return Elf(data, e_type, e_machine, entry, sections, sorted(segments), symbols)


def read_elf(path: str) -> Elf:
    with open(path, "rb") as fh:
        return parse_elf(fh.read())


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="summarise an ELF's sections and symbol table")
    ap.add_argument("elf")
    ap.add_argument("--limit", type=int, default=20, help="how many of the largest functions to print")
    args = ap.parse_args(list(argv) if argv is not None else None)
    if not os.path.exists(args.elf):
        print("NO-DATA: missing %s" % args.elf)
        return 2
    try:
        elf = read_elf(args.elf)
    except ValueError as exc:
        print("NO-DATA: %s: %s" % (args.elf, exc))
        return 2
    print("type %d machine %d entry 0x%08x" % (elf.e_type, elf.e_machine, elf.entry))
    for s in elf.sections:
        if s.name:
            print("  %-12s type %-10d addr 0x%08x size %d" % (s.name, s.type, s.addr, s.size))
    funcs = elf.functions
    census = elf.census()
    print("%d symbol table entries: %d STT_FUNC (%d sized and named), %d STT_OBJECT (%d sized and "
          "named); %d relocations"
          % (census["symbols"], census["func_entries"], len(funcs),
             census["object_entries"], len(elf.objects), len(elf.relocations())))
    for start, end, name in sorted(funcs, key=lambda f: f[1] - f[0], reverse=True)[:args.limit]:
        print("  0x%08x %7d  %s" % (start, end - start, name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
