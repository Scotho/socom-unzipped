"""Statically decrypt the self-encrypting code blocks of SOCOM II's DNAS.BIN overlay.

libdnas2 protects ~130 small code blocks: each protected function starts with
    if (flag == 0) DECRYPT(start, size ^ key, key, flags)
and ends with the matching re-encrypt call.  The cipher is a chain of up to 7
word-wise 32-bit transforms (xor / rotate / byte-swap ...) selected by nibbles of
a descriptor derived from `key`; words listed in a per-block skip table (linker
relocations) are left alone.  Four copies of the decryptor exist in the overlay.

We do not re-implement the transforms: we run each variant's *core* routine
under Unicorn on unpatched memory (it is plain 32-bit MIPS) with parameters we
compute ourselves from the key tables in the file.

Output: game/disc/OVERLAY/REL/DNAS.dec.bin (same layout as DNAS.BIN, code blocks
in plaintext) and a JSON side file describing the blocks.
"""
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from ee_unicorn import EE

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join(HERE, '..', 'game', 'disc')
ANALYSIS = os.path.join(HERE, '..', 'game', 'analysis')
BASE = 0x4c5380
DECRYPTORS = (0x4ee9e8, 0x52b9d0, 0x53a358, 0x5412a0)


def load_decomp():
    src = open(os.path.join(ANALYSIS, 'DNAS.BIN.decomp.c')).read()
    out = {}
    for f in re.split(r'(?m)^// ---- ', src)[1:]:
        m = re.match(r'(\S+) @ ([0-9a-f]+)', f)
        out[m.group(1)] = f
    return out


def discover_variants(decomp):
    """For each decryptor: (key table address, decrypt core address)."""
    variants = {}
    for dec in DECRYPTORS:
        body = decomp[f'FUN_{dec:08x}']
        kt_fn = re.search(r'(FUN_[0-9a-f]+)\(param_4 >> 1', body).group(1)
        core_fn = re.search(r'(FUN_[0-9a-f]+)\(param_1,iVar3 \+ param_2', body).group(1)
        kt_body = decomp[kt_fn]
        kt_addr = int(re.search(r'DAT_00([0-9a-f]{6})', kt_body).group(1), 16)
        variants[dec] = dict(keytab=kt_addr, core=int(core_fn[4:], 16), keytab_fn=int(kt_fn[4:], 16))
    return variants


def const_reg(d, off, reg):
    lo = None
    for back in range(4, 48, 4):
        w = struct.unpack_from('<I', d, off - back)[0]
        if (w >> 26) == 9 and ((w >> 21) & 0x1f) == reg and ((w >> 16) & 0x1f) == reg and lo is None:
            lo = struct.unpack('<h', struct.pack('<H', w & 0xffff))[0]
        elif (w >> 26) == 0x0f and ((w >> 16) & 0x1f) == reg and lo is not None:
            return (((w & 0xffff) << 16) + lo) & 0xffffffff
    return None


def find_blocks(d, text_off, text_size):
    """[(start, size, key, flags, decryptor)] from the decrypt-entry call sites."""
    jals = {0x0c000000 | (a >> 2): a for a in DECRYPTORS}
    blocks = []
    for off in range(text_off, text_off + text_size, 4):
        w = struct.unpack_from('<I', d, off)[0]
        if w not in jals:
            continue
        slot = struct.unpack_from('<I', d, off + 4)[0]
        if (slot >> 26) != 0x23 or ((slot >> 16) & 0x1f) != 6 or (slot & 0xffff) != 4:
            continue
        a0 = const_reg(d, off, 4)
        if a0 is None:
            continue
        flag = a0 - 0x14
        key, flags, sk = struct.unpack_from('<III', d, flag + 4 - BASE)
        blocks.append((a0, sk ^ key, key, flags, jals[w]))
    return sorted(set(blocks))


def skip_list(d, keytab, flags):
    """Mirror FUN_00541378: returns (base_delta, count, list_addr) or None."""
    ident = flags >> 1
    if ident == 0:
        return None
    n = struct.unpack_from('<i', d, keytab - BASE)[0]
    entries = keytab + 4
    for i in range(n):
        eid, eoff = struct.unpack_from('<II', d, entries + i * 8 - BASE)
        if (eid >> 1) == ident:
            p = entries + eoff + n * 8
            delta, count = struct.unpack_from('<II', d, p - BASE)
            return delta, count, p + 8
    return None


def main():
    d = open(os.path.join(GAME, 'OVERLAY', 'REL', 'DNAS.BIN'), 'rb').read()
    text = struct.unpack_from('<I', d, 0x0c)[0]
    decomp = load_decomp()
    variants = discover_variants(decomp)
    for dec, v in variants.items():
        print(f"decryptor {dec:#x}: keytab {v['keytab']:#x} core {v['core']:#x}")
    blocks = find_blocks(d, 0x80, text)
    print(f"{len(blocks)} blocks")

    ee = EE()
    ee.write(BASE, d)                     # unpatched: the cipher code is plain MIPS
    ee.write(BASE + len(d), bytes(struct.unpack_from('<I', d, 0x14)[0]))
    SP = 0x01fe0000
    out = bytearray(d)
    meta = []
    for start, size, key, flags, dec in blocks:
        v = variants[dec]
        sl = skip_list(d, v['keytab'], flags)
        if sl is None:
            delta, count, lst = 0, 0, 0
        else:
            delta, count, lst = sl
        # fresh copy of the block in guest memory, then run the core routine
        ee.write(start, d[start - BASE:start - BASE + size])
        ee.call(v['core'], (start, start + size, start - delta, key, count, lst), sp=SP)
        plain = ee.read(start, size)
        out[start - BASE:start - BASE + size] = plain
        meta.append(dict(start=start, size=size, key=key, flags=flags, decryptor=dec,
                         skip=(count, lst)))
    open(os.path.join(GAME, 'OVERLAY', 'REL', 'DNAS.dec.bin'), 'wb').write(out)
    json.dump(meta, open(os.path.join(GAME, 'OVERLAY', 'REL', 'DNAS.blocks.json'), 'w'), indent=1)
    # sanity: how many words in the decrypted blocks decode as valid MIPS?
    from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS64, CS_MODE_LITTLE_ENDIAN
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS64 | CS_MODE_LITTLE_ENDIAN)
    total = bad = 0
    for start, size, *_ in blocks:
        for off in range(0, size, 4):
            w = struct.unpack_from('<I', out, start - BASE + off)[0]
            total += 1
            if not list(md.disasm(struct.pack('<I', w), start + off)) and not EE._needs_emulation(w):
                bad += 1
    print(f"decrypted {total} words, {bad} undecodable")
    print("block 0x53c4b4:", [hex(struct.unpack_from('<I', out, 0x53c4b4 - BASE + i)[0]) for i in range(0, 0x34, 4)])


if __name__ == '__main__':
    main()
