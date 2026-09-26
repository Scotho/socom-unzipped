"""Sprint 14 Task E3: the recompiler reference fixture's inputs, written deterministically.

The inputs mirror ps2xTest's Sprint 12 3b case ("display names come from the sidecar and change nothing but the
identifier", third_party/ps2recomp/ps2xTest/src/ps2_recompiler_tests.cpp): the ELF of
`writeMinimalMipsElfWithLongJalTarget` (eight MIPS words at 0x00100000 -- a `jal 0x00100010` and two `jr $ra`
returns), a Ghidra-shaped function map with two rows, a names sidecar with one row, and a toml in
recomp/socom2.toml's shape whose paths are relative to this directory. Nothing comes from the disc. The ELF is
laid out here, not by ELFIO, so its bytes are this file's own: an ELF header, one PT_LOAD program header, .text at
file offset 0x1000 (the segment's 0x1000 alignment against vaddr 0x00100000), .shstrtab, the section headers.

ps2_recomp resolves every path in the toml against the current directory, not the toml's, so it is run from a copy
of this directory (`output = "out/"`); `expected/` is that `out/` as the recompiler wrote it. The CI job
(`.github/workflows/linux.yml`, `recomp-ref`) and the regeneration command are in docs/DEVELOPING.md "Recompiler
reference".

Run: python tests/fixtures/recomp_ref/make_fixture.py   (rewrites the four inputs beside this file)
"""
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))

TEXT_ADDR = 0x00100000
TEXT_OFFSET = 0x1000
TEXT_WORDS = (
    0x0C040004,  # 0x00100000: jal 0x00100010
    0x00000000,  # nop
    0x03E00008,  # jr $ra
    0x00000000,  # nop
    0x00000000,  # 0x00100010: nop
    0x00000000,  # nop
    0x03E00008,  # jr $ra
    0x00000000,  # nop
)

FUNCTIONS_CSV = (
    "name,start,end,size\n"
    "FUN_00100000,0x00100000,0x00100010,0x10\n"
    "FUN_00100010,0x00100010,0x00100018,0x8\n"
)

NAMES_CSV = (
    "Address,Name,Mangled,Pass,Score,Evidence,Source,Date\n"
    "0x00100010,sceVu0MulMatrix,,test,1.00,\"a comma, inside quotes\",synthetic,\n"
)

TOML = (
    "# Sprint 14 Task E3: the recompiler reference fixture (tests/fixtures/recomp_ref/make_fixture.py writes it).\n"
    "# recomp/socom2.toml's shape; every path is relative to the directory ps2_recomp runs in (a copy of this one).\n"
    "[general]\n"
    "input = \"input.elf\"\n"
    "ghidra_output = \"functions.csv\"\n"
    "names = \"names.csv\"\n"
    "output = \"out/\"\n"
    "single_file_output = false\n"
    "patch_syscalls = false\n"
    "patch_cop0 = true\n"
    "patch_cache = true\n"
    "stubs = []\n"
    "skip = []\n"
)

EM_MIPS = 8
SHT_PROGBITS, SHT_STRTAB = 1, 3
SHF_ALLOC, SHF_EXECINSTR = 0x2, 0x4
PT_LOAD = 1
PF_X, PF_R = 0x1, 0x4


def elf_bytes():
    text = struct.pack("<%dI" % len(TEXT_WORDS), *TEXT_WORDS)
    shstrtab = b"\0.text\0.shstrtab\0"
    shstrtab_off = TEXT_OFFSET + len(text)
    shoff = (shstrtab_off + len(shstrtab) + 3) & ~3
    ehsize, phentsize, shentsize = 52, 32, 40
    header = b"\x7fELF" + bytes([1, 1, 1, 0]) + bytes(8)  # ELFCLASS32, little-endian, version 1, SYSV ABI
    header += struct.pack("<HHIIIIIHHHHHH", 2, EM_MIPS, 1, TEXT_ADDR, ehsize, shoff, 0,
                          ehsize, phentsize, 1, shentsize, 3, 2)
    phdr = struct.pack("<IIIIIIII", PT_LOAD, TEXT_OFFSET, TEXT_ADDR, TEXT_ADDR, len(text), len(text),
                       PF_R | PF_X, 0x1000)
    shdrs = bytes(shentsize)  # the null section
    shdrs += struct.pack("<IIIIIIIIII", 1, SHT_PROGBITS, SHF_ALLOC | SHF_EXECINSTR, TEXT_ADDR, TEXT_OFFSET,
                         len(text), 0, 0, 4, 0)
    shdrs += struct.pack("<IIIIIIIIII", 7, SHT_STRTAB, 0, 0, shstrtab_off, len(shstrtab), 0, 0, 1, 0)
    out = bytearray(header + phdr)
    out += bytes(TEXT_OFFSET - len(out))
    out += text + shstrtab
    out += bytes(shoff - len(out))
    out += shdrs
    return bytes(out)


def inputs():
    """File name -> the bytes this generator writes for it."""
    return {
        "input.elf": elf_bytes(),
        "functions.csv": FUNCTIONS_CSV.encode("ascii"),
        "names.csv": NAMES_CSV.encode("ascii"),
        "recomp_ref.toml": TOML.encode("ascii"),
    }


def main():
    for name, data in inputs().items():
        with open(os.path.join(HERE, name), "wb") as f:
            f.write(data)
        print("%s %d bytes" % (name, len(data)))


if __name__ == "__main__":
    main()
