"""Undo a foreign two-word stub write baked into a decrypted overlay's text.

Why this exists
---------------
The r0004 overlay that `tools_py/decrypt_apache.py` recovers from the card's
`APACHE00.ZDB` carries two words that no compiler emitted.  At `0x002CC670`, in the
middle of the epilogue of the function that starts at `0x002CC5F0`, the image holds

    0x002cc668  daddu $v0, $s1, $zero
    0x002cc66c  ld    $ra, 0x20($sp)
    0x002cc670  jr    $ra              <- should be  lq $s1, 0x10($sp)
    0x002cc674  nop                    <- should be  lq $s0, 0x00($sp)
    0x002cc678  jr    $ra
    0x002cc67c  addiu $sp, $sp, 0x40

Two returns back to back, the first of them without restoring `$sp`: that is not code.
It is the `jr $ra` / `nop` pair of a *stub this function out* patch, and the r0004
capsule's own decoded write stack (`game/r0004/decoded/stack.txt`, tables at
`0x80031250` and `0x80031268`) names exactly those two addresses --
`0x002CC670 <- 0x03E00008`, `0x002CC674 <- 0x00000000` -- next to the same patch for the
r0004 layout at `0x002CF330`.  The address is a function *entry* in the r0001 layout;
in the r0004 layout the same two words land inside somebody else's epilogue, and the
two `lq` they replaced are the restores of `$s0` and `$s1`.

The consequence is not subtle: every call to `0x002CC5F0` returns with `$s0` and `$s1`
holding the callee's values.  `CButtonSpec::Clone` (`0x003A90E0`) calls it at
`0x003A9178` and then reads its `std::vector` member through `$s1` -- from a stranger --
and asks `operator new` for 111.5 MiB, which fails and reboots the title.

The repair is derived from the image, never from a table of addresses
---------------------------------------------------------------------
`find_repairs` looks for the impossible shape -- `jr $ra` + `nop` immediately followed by
another `jr $ra` -- then walks back to that frame's prologue, pairs every
`sq/sd $rX, K($sp)` with its `lq/ld $rX, K($sp)`, and only acts when

  * some saves have no restore at all,
  * the number of missing restores is exactly the two words the stub overwrote, and
  * the real return that follows restores `$sp` by the amount the prologue took.

The replacement words are then rebuilt from the frame's own saves, in save order.  A
frame whose restores are all present -- the ordinary `jr $ra; nop` of an early return
sitting in front of a later `jr $ra` -- is left alone; there are 65 such sites in the two
r0004 overlays and 0 repairs among them, and the r0001 overlays and the loader yield no
repair at all.
"""
import os
import struct
import sys
from dataclasses import dataclass

JR_RA = 0x03E00008
NOP = 0x00000000

_SQ, _SD = 0x1F, 0x3F          # opcodes of the stores a Metrowerks frame saves with
_LQ, _LD = 0x1E, 0x37          # and of their restores
_RESTORE_OF = {_SQ: _LQ, _SD: _LD}

_SP = 29                        # $sp
_ADDIU = 0x27BD0000             # addiu $sp, $sp, imm  (top half)

# The stub is a pair: the branch and its delay slot.
_STUB_WORDS = 2

# A frame's prologue is never far from its epilogue in this image; the bound keeps a
# scan that lost its footing from walking the whole segment backwards.
_MAX_FRAME_WORDS = 4096


@dataclass(frozen=True)
class Repair:
    """One word the repair rewrites, with everything needed to audit it."""
    address: int
    before: int
    after: int
    register: int
    slot: int
    function: int

    def describe(self):
        op = "lq" if (self.after >> 26) == _LQ else "ld"
        return (f"0x{self.address:08X}: 0x{self.before:08X} -> 0x{self.after:08X}"
                f"  ({op} $r{self.register}, 0x{self.slot:X}($sp) in the frame at 0x{self.function:08X})")


def _words(data):
    return list(struct.unpack_from("<%dI" % (len(data) // 4), data, 0))


def _frame_take(word):
    """The bytes an `addiu $sp,$sp,-N` prologue takes, or None."""
    if (word >> 16) != _ADDIU >> 16:
        return None
    imm = word & 0xFFFF
    return 0x10000 - imm if imm >= 0x8000 else None


def _frame_give(word):
    """The bytes an `addiu $sp,$sp,+N` epilogue gives back, or None."""
    if (word >> 16) != _ADDIU >> 16:
        return None
    imm = word & 0xFFFF
    return None if imm >= 0x8000 or imm == 0 else imm


def _stack_slot(word):
    """(opcode, rt, offset) when the word is a frame save or restore off $sp."""
    op = word >> 26
    if op not in (_SQ, _SD, _LQ, _LD):
        return None
    if ((word >> 21) & 31) != _SP:
        return None
    return op, (word >> 16) & 31, word & 0xFFFF


def find_repairs(data, base):
    """Every word `apply_repairs` would rewrite in `data`, which is loaded at `base`."""
    words = _words(data)
    repairs = []
    for i in range(len(words) - 3):
        if words[i] != JR_RA or words[i + 1] != NOP or words[i + 2] != JR_RA:
            continue
        if _frame_give(words[i + 3]) is None:
            # The return that follows must be the real one: it gives the frame back.
            continue
        start = None
        for j in range(i - 1, max(0, i - _MAX_FRAME_WORDS) - 1, -1):
            if _frame_take(words[j]) is not None:
                start = j
                break
        if start is None or _frame_take(words[start]) != _frame_give(words[i + 3]):
            continue
        saves, restores = [], set()
        for k in range(start, i + 3):
            slot = _stack_slot(words[k])
            if slot is None:
                continue
            op, rt, off = slot
            if op in _RESTORE_OF:
                saves.append((_RESTORE_OF[op], rt, off))
            else:
                restores.add((op, rt, off))
        missing = [s for s in saves if s not in restores]
        if len(missing) != _STUB_WORDS:
            continue
        for k, (op, rt, off) in enumerate(missing):
            repairs.append(Repair(address=base + (i + k) * 4,
                                  before=words[i + k],
                                  after=(op << 26) | (_SP << 21) | (rt << 16) | off,
                                  register=rt,
                                  slot=off,
                                  function=base + start * 4))
    return repairs


def apply_repairs(data, base):
    """`(repaired bytes, repairs)`; `data` is returned unchanged when there is nothing to do."""
    repairs = find_repairs(data, base)
    if not repairs:
        return data, repairs
    out = bytearray(data)
    for r in repairs:
        struct.pack_into("<I", out, r.address - base, r.after)
    return bytes(out), repairs


def _segments(path):
    """(vaddr, bytes, executable) for every PT_LOAD of an ELF, or the one MWo3 overlay."""
    with open(path, "rb") as fh:
        d = fh.read()
    if d[:4] == b"MWo3":
        load = struct.unpack_from("<I", d, 8)[0]
        return [(load, d, True)]
    e_phoff = struct.unpack_from("<I", d, 0x1C)[0]
    e_phnum = struct.unpack_from("<H", d, 0x2C)[0]
    out = []
    for i in range(e_phnum):
        p_type, p_off, p_va, _pa, p_filesz, _memsz, p_flags = struct.unpack_from("<7I", d, e_phoff + i * 32)
        if p_type == 1 and p_filesz:
            out.append((p_va, d[p_off:p_off + p_filesz], bool(p_flags & 1)))
    return out


def main(argv):
    """Report (never rewrite) what the repair would do to each file named."""
    if not argv:
        print("usage: python -m tools_py.overlay_repair <overlay.bin|image.elf> ...", file=sys.stderr)
        return 2
    total = 0
    for path in argv:
        for va, data, executable in _segments(path):
            if not executable:
                continue
            for r in find_repairs(data, va):
                total += 1
                print(f"{os.path.basename(path)}  {r.describe()}")
    print(f"{total} word(s) would be repaired")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
