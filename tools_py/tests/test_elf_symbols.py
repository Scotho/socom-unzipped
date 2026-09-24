"""Sprint 11 Task 7 (U3) -- reading a function table out of an ELF symbol table.

The real input is the SOCOM 1 demo, which is git-ignored and 10 MB; this builds the smallest ELF32 that
has the same shape -- one PT_LOAD, a `.symtab` with a FUNC, an OBJECT, a zero-size FUNC and a duplicate,
and a SHT_REL section -- so the suite runs with no disc and no demo present.
"""
import os
import struct
import unittest

from tools_py.elf_symbols import main, parse_elf

CODE = bytes(range(0x40))
VADDR = 0x00100000
STT_OBJECT, STT_FUNC = 1, 2


def _shdr(name, type_, flags, addr, offset, size, link=0, info=0, entsize=0):
    return struct.pack("<10I", name, type_, flags, addr, offset, size, link, info, 4, entsize)


def _sym(name, value, size, info, shndx):
    return struct.pack("<IIIBBH", name, value, size, info, 0, shndx)


def tiny_elf():
    """A little-endian ELF32 with one loadable section, a symbol table and a relocation table."""
    shstr = b"\0.shstrtab\0.strtab\0.symtab\0main\0.relmain\0"
    names = {n: shstr.index(b"\0" + n.encode() + b"\0") + 1
             for n in (".shstrtab", ".strtab", ".symtab", "main", ".relmain")}
    strtab = b"\0funcA\0objB\0stub\0twin\0"
    soff = {n: strtab.index(b"\0" + n.encode() + b"\0") + 1 for n in ("funcA", "objB", "stub", "twin")}
    symtab = b"".join([
        _sym(0, 0, 0, 0, 0),
        _sym(soff["funcA"], VADDR, 0x20, STT_FUNC, 1),
        _sym(soff["objB"], 0x00200000, 4, STT_OBJECT, 1),
        _sym(soff["stub"], VADDR + 0x30, 0, STT_FUNC, 1),          # zero size -- no body to hash
        _sym(soff["twin"], VADDR, 0x20, STT_FUNC, 1),              # same address as funcA
    ])
    rel = struct.pack("<II", VADDR + 4, (1 << 8) | 5) + struct.pack("<II", VADDR + 0x100, (1 << 8) | 6)

    off = 52 + 32                                                   # ehdr + one phdr
    blobs = [CODE, shstr, strtab, symtab, rel]
    offs = []
    for blob in blobs:
        offs.append(off)
        off += len(blob)
    sh_off = off

    sections = b"".join([
        _shdr(0, 0, 0, 0, 0, 0),
        _shdr(names["main"], 1, 7, VADDR, offs[0], len(CODE)),
        _shdr(names[".shstrtab"], 3, 0, 0, offs[1], len(shstr)),
        _shdr(names[".strtab"], 3, 0, 0, offs[2], len(strtab)),
        _shdr(names[".symtab"], 2, 0, 0, offs[3], len(symtab), link=3, entsize=16),
        _shdr(names[".relmain"], 9, 0, 0, offs[4], len(rel), link=4, entsize=8),
    ])
    ehdr = bytearray(52)
    ehdr[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HHI", ehdr, 16, 2, 8, 1)                     # ET_EXEC, EM_MIPS
    struct.pack_into("<III", ehdr, 24, VADDR + 0x10, 52, sh_off)    # entry, phoff, shoff
    struct.pack_into("<HHHHHH", ehdr, 40, 52, 32, 1, 40, 6, 2)
    phdr = struct.pack("<8I", 1, offs[0], VADDR, VADDR, len(CODE), len(CODE) + 0x100, 5, 16)
    return bytes(ehdr) + phdr + b"".join(blobs) + sections


class ElfSymbolsTest(unittest.TestCase):
    def setUp(self):
        self.elf = parse_elf(tiny_elf())

    def test_header_and_segments(self):
        self.assertEqual(self.elf.e_type, 2)
        self.assertEqual(self.elf.e_machine, 8)
        self.assertEqual(self.elf.entry, VADDR + 0x10)
        self.assertEqual(self.elf.segments, [(VADDR, CODE)])

    def test_sections_are_named(self):
        self.assertEqual([s.name for s in self.elf.sections][1:],
                         ["main", ".shstrtab", ".strtab", ".symtab", ".relmain"])
        self.assertEqual(self.elf.section("main").addr, VADDR)
        self.assertIsNone(self.elf.section(".debug"))

    def test_functions_are_start_end_name(self):
        self.assertEqual(self.elf.functions, [(VADDR, VADDR + 0x20, "funcA")])

    def test_zero_size_function_is_left_out(self):
        self.assertNotIn("stub", [f[2] for f in self.elf.functions])

    def test_duplicate_address_keeps_the_first(self):
        self.assertEqual(len(self.elf.functions), 1)
        self.assertEqual(self.elf.functions[0][2], "funcA")

    def test_objects_are_separate(self):
        self.assertEqual(self.elf.objects, [(0x00200000, 0x00200004, "objB")])

    def test_relocations_and_their_words(self):
        self.assertEqual(self.elf.relocations(),
                         [(VADDR + 4, 5, 1), (VADDR + 0x100, 6, 1)])
        # The second one is past the loaded bytes, so it is not a word of the image.
        self.assertEqual(self.elf.relocated_words(), {VADDR + 4})

    def test_unnamed_symbols_are_kept_so_relocation_indices_stay_aligned(self):
        # The null symbol is entry 0 and `funcA` is entry 1; a relocation whose r_info names symbol 1
        # has to find `funcA` there. Dropping unnamed entries would slide every index down by one.
        self.assertEqual(self.elf.symbols[0].name, "")
        self.assertEqual(self.elf.symbols[1].name, "funcA")
        index = self.elf.relocations()[0][2]
        self.assertEqual(self.elf.symbols[index].name, "funcA")

    def test_a_relocation_in_a_gap_between_segments_is_not_a_loaded_word(self):
        # Our own image has four PT_LOADs with gaps; a global lowest/highest bound would count the
        # gaps as loaded. Two segments here, with the second relocation in the hole between them.
        elf = parse_elf(tiny_elf())
        two = elf._replace(segments=[(VADDR, CODE), (VADDR + 0x200, CODE)])
        self.assertEqual(two.relocated_words(), {VADDR + 4})

    # ---- a malformed file is a ValueError that names the table, never a struct.error ----------
    #
    # `struct.error` is NOT a subclass of ValueError, so an `except ValueError` around a parse does
    # not catch it: before this, a truncated ELF came out of `main()` as a traceback. Each of the
    # three tests below asserts the exact type AND the message, because a test that accepts
    # `Exception` passes on the very error it was written to rule out.

    def _shdr_offset(self, raw, name):
        """Where section `name`'s 40-byte header starts in the file."""
        e_shoff = struct.unpack_from("<I", bytes(raw), 32)[0]
        index = [s.name for s in parse_elf(bytes(raw)).sections].index(name)
        return e_shoff + index * 40

    def test_a_truncated_section_header_table_names_the_section_header(self):
        raw = bytearray(tiny_elf())
        del raw[-20:]                       # the last 40-byte section header is now half there
        with self.assertRaises(ValueError) as caught:
            parse_elf(bytes(raw))
        self.assertIn("section header", str(caught.exception))
        self.assertIn("run past the end", str(caught.exception))
        self.assertNotIsInstance(caught.exception, struct.error)

    def test_a_truncated_symbol_table_names_the_entry(self):
        raw = bytearray(tiny_elf())
        # Point .symtab at the last eight bytes of the file: entry 0 needs sixteen.
        struct.pack_into("<I", raw, self._shdr_offset(raw, ".symtab") + 16, len(raw) - 8)
        with self.assertRaises(ValueError) as caught:
            parse_elf(bytes(raw))
        self.assertIn(".symtab entry 0", str(caught.exception))
        self.assertIn("run past the end", str(caught.exception))

    def test_a_string_offset_past_the_file_names_the_string_table(self):
        raw = bytearray(tiny_elf())
        symtab = [s for s in parse_elf(bytes(raw)).sections if s.name == ".symtab"][0]
        struct.pack_into("<I", raw, symtab.offset + 16, 0xFFFFFF)     # funcA's st_name
        with self.assertRaises(ValueError) as caught:
            parse_elf(bytes(raw))
        self.assertIn("string table", str(caught.exception))
        self.assertIn("NUL-terminated", str(caught.exception))

    def test_a_truncated_file_reaches_main_as_one_sentence(self):
        import contextlib
        import io as _io
        import tempfile
        raw = bytearray(tiny_elf())
        del raw[-20:]
        with tempfile.NamedTemporaryFile(suffix=".elf", delete=False) as fh:
            fh.write(bytes(raw))
            path = fh.name
        self.addCleanup(os.unlink, path)
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([path])
        self.assertEqual(code, 2)
        self.assertIn("NO-DATA:", out.getvalue())
        self.assertIn("section header", out.getvalue())

    def test_the_census_separates_the_raw_counts_from_the_sized_ones(self):
        # 4 real entries + the null one; `stub` is a zero-size FUNC, `twin` duplicates funcA.
        census = self.elf.census()
        self.assertEqual(census["symbols"], 5)
        self.assertEqual(census["func_entries"], 3)          # funcA, stub, twin
        self.assertEqual(census["object_entries"], 1)
        self.assertEqual(len(self.elf.functions), 1)         # sized, named, de-duplicated
        self.assertEqual(len(self.elf.objects), 1)

    def test_main_reports_a_missing_file_and_exits_2(self):
        import contextlib
        import io as _io
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["no-such-file.elf"])
        self.assertEqual(code, 2)
        self.assertIn("NO-DATA: missing", out.getvalue())

    def test_main_reports_a_non_elf_and_exits_2(self):
        import contextlib
        import io as _io
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".elf", delete=False) as fh:
            fh.write(b"MZ" + bytes(64))
            path = fh.name
        self.addCleanup(os.unlink, path)
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([path])
        self.assertEqual(code, 2)
        self.assertIn("NO-DATA:", out.getvalue())

    def test_rejects_a_non_elf(self):
        with self.assertRaises(ValueError):
            parse_elf(b"MZ" + bytes(64))



class HeaderTooShortTest(unittest.TestCase):
    """A file that begins with the ELF magic and ends five bytes later is a truncation, not an ELF: it must be
    the same ValueError sentence as every other short read, never an IndexError (Task 7 re-review 2, N5)."""

    def test_five_bytes_with_the_magic_is_a_sentence(self):
        from tools_py.elf_symbols import parse_elf
        with self.assertRaises(ValueError) as cm:
            parse_elf(b"\x7fELF\x01")
        self.assertIn("truncated ELF header", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
