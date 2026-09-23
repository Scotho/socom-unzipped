"""Decode the encrypted code stack inside PSRewired's r0004 patch capsule.

The capsule (`r0004v002.elf`) is a MIPS ELF packed with ps2-packer: one PT_LOAD whose first 0x18
bytes are the packer's stub header and whose remainder is a zlib stream that inflates to the raw
R5900 image loaded at 0x00100000. Inside that image sits one encrypted **code stack** -- the patch
body. This module turns it back into a plain list of memory writes.

The scheme, as reversed from the capsule's own apply routine (and cross-checked against the r0005
tooling in research/r0005-patch/):

    header  0x00  char version[8]     NUL-padded ASCII, e.g. "0000001"
            0x08  u32  length         ciphertext length in bytes, a multiple of 8
            0x0C  u32  reserved       zero
            0x10  u32  reserved       zero
            0x14  u8   ciphertext[length]
                       then a zero word: the terminator the apply routine stops on

    cipher  the ciphertext is a stream of 32-bit little-endian words XORed with an eight-word key
            that cycles once per word (so a pair costs two key steps, not one). The plaintext is
            (address, value) pairs; each is applied as a 32-bit store `*(u32*)address = value`.
            The stack ends at the first **ciphertext** word of zero in an address slot -- because
            the key cycles, that word does not decrypt to zero, which is why the terminator is
            tested before the XOR.

    key     **not in this repository, and never written into it.** The key is 32 bytes of the
            capsule's own image; the apply routine copies them to its stack frame before the loop.
            `locate_key()` finds them at run time by asking which 32-byte window of the image
            decrypts the stack's first pairs to addresses an EE store can reach -- so a later
            capsule that moved its key still works, and a capsule whose key cannot be found fails
            loudly instead of producing plausible nonsense. The same key is published by the
            patch's own authors in the r0005 "Patch Compiler" documentation, which is how the
            scheme was first recognised; this module does not carry that copy either.

The r0005 Patch Compiler's `update.dat` uses the same cipher behind a shorter, 8-byte header
(version string, four zeros) and carries no key of its own; point `--key-image` at the capsule to
read one of those. That path is how the scheme was validated before it was aimed at r0004.

Nothing in here reads or embeds game data. The capsule and its decoded outputs are git-ignored
(`game/r0004/`); the suite runs on synthetic stacks only.

Usage:
    python -m tools_py.r0004.capsule <capsule.elf|image.bin> --out <dir> [--elf <game.elf>]
writes `<dir>/stack.txt` (one `TYPE ADDRESS VALUE` per line) and `<dir>/summary.txt`.
"""
import argparse
import collections
import os
import struct
import sys
import zlib

KEY_BYTES = 32              # eight 32-bit key words
HEADER_SIZE = 0x14          # version[8] + length + two reserved words
SHORT_HEADER_SIZE = 0x08    # the r0005 update.dat shape
PACKER_STUB = 0x18          # ps2-packer's header before the zlib stream

# Classification windows (Task 19 Step 2). Addresses are masked to their physical form first, so
# kseg0/kseg1 aliases of the same RAM class the same way.
#
# PROVISIONAL: the two game-side bounds below are round numbers, not measured ones, and no write
# in the r0004 capsule has ever exercised them (all 491 are resident). GAME_TEXT_END in particular
# cuts through the r0001 image, whose loaded segments run to 0x00686F80. Pass `--elf <game ELF>`
# (or `windows=game_windows(...)`) and the real program headers are used instead; without it,
# `main` prints a warning the first time a write lands in a game-side class.
ADDR_MASK = 0x1FFFFFFF
GAME_TEXT_START = 0x00100000
GAME_TEXT_END = 0x00500000
RESIDENT_HIGH = 0x01CF0000  # at or above the packer's own load address: pasted blocks, not game

Packed = collections.namedtuple("Packed", "image load_vaddr entry")
GameWindows = collections.namedtuple("GameWindows", "base text end provisional")

PROVISIONAL_WINDOWS = GameWindows(GAME_TEXT_START, ((GAME_TEXT_START, GAME_TEXT_END),),
                                  RESIDENT_HIGH, True)


# The floor matters: without it, a window of the ciphertext itself passes as a key, because
# c ^ c = 0 and address zero would otherwise look "plausible". 0x100 is below the lowest address
# any of these patches touches (the kernel syscall vector at 0x800002FC) and above zero.
TARGET_FLOOR = 0x100
TARGET_CEILING = 0x02000000


def _plausible_target(address):
    """Is `address` somewhere an EE patch could legitimately store a 32-bit word?"""
    if address % 4:
        return False
    if address >> 28 not in (0x0, 0x8, 0xA):
        return False
    return TARGET_FLOOR <= (address & ADDR_MASK) < TARGET_CEILING


# ---- 1. unpack ----------------------------------------------------------------------------------

def unpack(elf_bytes):
    """Inflate a ps2-packer capsule into its raw image. Returns a `Packed`."""
    if len(elf_bytes) < 0x34 or elf_bytes[:4] != b"\x7fELF":
        raise ValueError("not an ELF: no \\x7fELF magic")
    e_phoff = struct.unpack_from("<I", elf_bytes, 0x1C)[0]
    e_phentsize, e_phnum = struct.unpack_from("<HH", elf_bytes, 0x2A)
    if e_phentsize < 32:
        raise ValueError("program headers are %d bytes, too small for ELF32" % e_phentsize)
    why = []
    for i in range(e_phnum):
        p_type, p_offset, _va, _pa, p_filesz = struct.unpack_from(
            "<5I", elf_bytes, e_phoff + i * e_phentsize)
        if p_type != 1 or p_filesz <= PACKER_STUB:
            continue
        stub = elf_bytes[p_offset:p_offset + PACKER_STUB]
        entry, _flag, _memsz, _unk, load_vaddr, comp_len = struct.unpack("<6I", stub)
        payload = elf_bytes[p_offset + PACKER_STUB:p_offset + p_filesz]
        if comp_len and comp_len <= len(payload):
            payload = payload[:comp_len]
        try:
            image = zlib.decompressobj().decompress(payload)
        except zlib.error as exc:
            why.append("PT_LOAD %d: %s" % (i, exc))
            continue  # a capsule may carry an unpacked PT_LOAD before the packed one
        if not image:
            why.append("PT_LOAD %d inflated to nothing" % i)
            continue
        return Packed(image, load_vaddr, entry)
    raise ValueError("no ps2-packer zlib PT_LOAD found" + ("; " + "; ".join(why) if why else ""))


# ---- 2. locate the stack ------------------------------------------------------------------------

def _version_string(blob):
    """The 8-byte NUL-padded ASCII version field, or None if these bytes are not one."""
    if len(blob) < 8 or b"\0" not in blob:
        return None
    text, _, pad = blob.partition(b"\0")
    if not text or pad.strip(b"\0"):
        return None
    if not all(0x20 <= c < 0x7F for c in text):
        return None
    return text.decode("ascii")


def _ciphertext_length(blob, offset):
    """How far a stack at `offset` runs: to the first zero ciphertext address word."""
    n = 0
    while offset + n + 8 <= len(blob):
        if struct.unpack_from("<I", blob, offset + n)[0] == 0:
            break
        n += 8
    return n


def locate_stack(image):
    """Find the encrypted stack. Returns (ciphertext offset, length in bytes, version string).

    Structural only -- no key is needed or used, because the key is itself found by decrypting
    this stack. Every candidate in the image is collected: more than one is an error naming them
    all, rather than a silent choice of the first.
    """
    candidates = []
    mismatch = []
    for offset in range(0, max(0, len(image) - HEADER_SIZE), 4):
        version = _version_string(image[offset:offset + 8])
        if version is None:
            continue
        length, res0, res1 = struct.unpack_from("<III", image, offset + 8)
        if res0 or res1 or not length or length % 8:
            continue
        body = offset + HEADER_SIZE
        if length + 4 > len(image) - body:
            continue
        if struct.unpack_from("<I", image, body + length - 8)[0] == 0:
            continue  # the last pair must be a real pair, not the terminator
        if struct.unpack_from("<I", image, body + length)[0] != 0:
            mismatch.append((offset, version, length))
            continue
        candidates.append((body, length, version))

    if len(candidates) > 1:
        raise LookupError("ambiguous: %d code stacks in this image (%s) -- refusing to guess"
                          % (len(candidates),
                             ", ".join("+0x%X len %d version %r" % (b, n, v)
                                       for b, n, v in candidates)))
    if candidates:
        return candidates[0]

    # The r0005 Patch Compiler's update.dat: version string, four zeros, ciphertext, no length.
    version = _version_string(image[:8])
    if version is not None:
        length = _ciphertext_length(image, SHORT_HEADER_SIZE)
        if length >= 16:
            return SHORT_HEADER_SIZE, length, version

    if mismatch:
        raise LookupError("header at +0x%X (version %r) says %d ciphertext bytes, but the word "
                          "there is not the terminator -- the length field and the terminator "
                          "disagree" % mismatch[0])
    raise LookupError("no encrypted code stack found in this image")


# ---- 3. locate the key, then decrypt ------------------------------------------------------------

def _looks_right(ciphertext, key, pairs):
    """Do the first `pairs` pairs decrypt to addresses an EE store could reach?"""
    nkey = len(key) // 4
    seen = 0
    for i in range(pairs):
        if i * 8 + 8 > len(ciphertext):
            break
        raw = struct.unpack_from("<I", ciphertext, i * 8)[0]
        if raw == 0:
            break
        kw = struct.unpack_from("<I", key, ((i * 2) % nkey) * 4)[0]
        if not _plausible_target(raw ^ kw):
            return False
        seen += 1
    return seen > 0


def locate_key(key_source, ciphertext, pairs=8, key_len=KEY_BYTES, exclude=None):
    """Find the stack's key inside an image. Returns (key bytes, [offsets it was found at]).

    The key is never a constant here. `key_source` is scanned for a `key_len`-byte window that
    decrypts the stack's first `pairs` pairs to plausible store addresses. Two *different* keys
    matching, or none at all, both raise -- a decode must never proceed on a guess.

    `exclude` is a (start, end) byte range of `key_source` the key cannot be in, and the caller
    must pass the stack's own ciphertext there. The reason is not tidiness: any window of the
    ciphertext one key-period apart from its start "decrypts" the stack to the XOR of two of its
    own plaintext addresses, which -- since they are all addresses in the same few ranges -- looks
    entirely plausible. The key is data the stack is decrypted *with*, never part of it.
    """
    hits = []
    for offset in range(0, max(0, len(key_source) - key_len + 1), 4):
        if exclude and offset < exclude[1] and offset + key_len > exclude[0]:
            continue
        candidate = key_source[offset:offset + key_len]
        if _looks_right(ciphertext, candidate, pairs):
            hits.append((offset, candidate))
    distinct = {candidate for _, candidate in hits}
    if not distinct:
        raise LookupError("no %d-byte key in this image decrypts the stack -- the key moved, the "
                          "cipher changed, or this is not a key source for this stack" % key_len)
    if len(distinct) > 1:
        raise LookupError("ambiguous: %d different keys at offsets %s decrypt the stack -- "
                          "refusing to guess"
                          % (len(distinct), ", ".join("+0x%X" % o for o, _ in hits)))
    return hits[0][1], [offset for offset, _ in hits]


def decrypt_stack(blob, key):
    """Turn a ciphertext stack into `[(type, address, value), ...]`.

    `type` is always "w": the capsule applies every entry as one 32-bit store.
    """
    if not key or len(key) % 4:
        raise ValueError("key must be a non-empty whole number of 32-bit words")
    nkey = len(key) // 4
    writes = []
    pos = 0
    while pos + 4 <= len(blob):
        raw_address = struct.unpack_from("<I", blob, pos)[0]
        if raw_address == 0:
            break
        if pos + 8 > len(blob):
            raise ValueError("stack is truncated: %d bytes left in a pair at +0x%X"
                             % (len(blob) - pos, pos))
        raw_value = struct.unpack_from("<I", blob, pos + 4)[0]
        wi = pos // 4
        ka = struct.unpack_from("<I", key, (wi % nkey) * 4)[0]
        kv = struct.unpack_from("<I", key, ((wi + 1) % nkey) * 4)[0]
        address = raw_address ^ ka
        value = raw_value ^ kv
        if not _plausible_target(address):
            raise ValueError("pair %d decrypts to address %08X, which no EE store can reach -- "
                             "wrong key, wrong offset, or a by-pair key schedule"
                             % (len(writes), address))
        writes.append(("w", address, value))
        pos += 8
    return writes


# ---- 4. classify --------------------------------------------------------------------------------

def _merge(ranges):
    out = []
    for start, end in sorted(ranges):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return tuple((a, b) for a, b in out)


def game_windows(elf_bytes):
    """Derive the game's text and loaded extent from a game ELF's program headers.

    Beats the provisional constants: the text window becomes the union of the executable PT_LOADs
    rather than a round number that cuts the image in half.
    """
    if len(elf_bytes) < 0x34 or elf_bytes[:4] != b"\x7fELF":
        raise ValueError("not an ELF: no \\x7fELF magic")
    e_phoff = struct.unpack_from("<I", elf_bytes, 0x1C)[0]
    e_phentsize, e_phnum = struct.unpack_from("<HH", elf_bytes, 0x2A)
    loads, text = [], []
    for i in range(e_phnum):
        p_type, _off, p_vaddr, _pa, _fsz, p_memsz, p_flags, _al = struct.unpack_from(
            "<8I", elf_bytes, e_phoff + i * e_phentsize)
        if p_type != 1 or not p_memsz:
            continue
        loads.append((p_vaddr, p_vaddr + p_memsz))
        if p_flags & 1:
            text.append((p_vaddr, p_vaddr + p_memsz))
    if not loads:
        raise ValueError("this ELF has no loadable segment")
    if not text:
        text = list(loads)
    return GameWindows(min(a for a, _ in loads), _merge(text), max(b for _, b in loads), False)


def classify(writes, windows=PROVISIONAL_WINDOWS):
    """Split writes into {data, code_patch, resident} per Task 19 Step 2.

    resident   -- a pasted block: kernel/low RAM below the game's image, or at/above where the
                  capsule itself loads. These are the patch's own functions and variables.
    code_patch -- a store into the game's text (a changed instruction, or a jump into resident
                  code).
    data       -- a constant into the rest of game memory.

    With the default `windows` the two game-side bounds are provisional -- see the note on the
    module constants. Pass `game_windows(<game ELF bytes>)` for measured ones.
    """
    out = {"data": [], "code_patch": [], "resident": []}
    for entry in writes:
        masked = entry[1] & ADDR_MASK
        if masked < windows.base or masked >= windows.end:
            out["resident"].append(entry)
        elif any(start <= masked < end for start, end in windows.text):
            out["code_patch"].append(entry)
        else:
            out["data"].append(entry)
    return out


# ---- 5. the tables the resident code applies indirectly -----------------------------------------

def find_pair_tables(writes, min_entries=1):
    """Find NUL-terminated (address, value) tables inside the resident blocks.

    The capsule's resident code does not patch the game from the stack: it carries its own little
    tables and walks them once the game is up. Each is a run of 8-byte entries whose first word is
    a game address, ended by a zero word. A table is 8-byte aligned and its targets are
    instruction-aligned; that is what keeps a stray string or constant out of the list.

    This is **pattern-matching, not proof**: those two alignment constraints are the only thing
    separating a real table from a run of constants, so false positives and false negatives are
    both possible. Confirm a table by disassembling the resident code that loads its address.
    Returns `[(base, [(address, value), ...]), ...]`.
    """
    mem = {}
    for _t, address, value in writes:
        mem[address] = value
    tables = []
    covered = set()
    for base in sorted(mem):
        if base in covered or base % 8:
            continue
        entries = []
        pos = base
        while pos in mem and mem[pos] != 0 and pos + 4 in mem:
            target = mem[pos]
            if not (GAME_TEXT_START <= target < 0x02000000) or target % 4:
                break
            entries.append((target, mem[pos + 4]))
            pos += 8
        terminated = pos in mem and mem[pos] == 0
        if len(entries) >= min_entries and terminated:
            tables.append((base, entries))
            for k in range(base, pos + 8, 4):
                covered.add(k)
    return tables


# ---- the command --------------------------------------------------------------------------------

def _runs(entries):
    """Contiguous 4-byte-stepped address runs, in stack order."""
    runs = []
    for _t, address, _v in entries:
        if runs and address == runs[-1][1] + 4:
            runs[-1][1] = address
            runs[-1][2] += 1
        else:
            runs.append([address, address, 1])
    return runs


def _load_image(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw[:4] == b"\x7fELF":
        packed = unpack(raw)
        return packed.image, packed.load_vaddr, packed.entry
    return raw, None, None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tools_py.r0004.capsule", description=__doc__.split("\n")[0])
    ap.add_argument("capsule", help="the packed capsule ELF, or an already-unpacked raw image")
    ap.add_argument("--out", help="output directory (default: <capsule dir>/decoded)")
    ap.add_argument("--key-image", help="where to look for the key (default: the capsule itself); "
                                        "needed for a stack that carries no key, such as the "
                                        "r0005 update.dat")
    ap.add_argument("--elf", help="a game ELF whose program headers give the real text/data "
                                  "boundary; without it the game-side classes are provisional")
    args = ap.parse_args(argv)

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.capsule)), "decoded")
    try:
        image, load_vaddr, entry = _load_image(args.capsule)
        offset, length, version = locate_stack(image)
        ciphertext = image[offset:offset + length]
        key_source = image
        if args.key_image:
            key_source, _lv, _e = _load_image(args.key_image)
        if key_source is image:
            exclude = (offset, offset + length)
        else:
            try:  # a separate key image has a stack of its own; it is not key material either
                key_offset, key_length, _v = locate_stack(key_source)
                exclude = (key_offset, key_offset + key_length)
            except LookupError:
                exclude = None
        key, key_offsets = locate_key(key_source, ciphertext, exclude=exclude)
        writes = decrypt_stack(ciphertext, key)
        windows = PROVISIONAL_WINDOWS
        if args.elf:
            with open(args.elf, "rb") as fh:
                windows = game_windows(fh.read())
    except (ValueError, LookupError, OSError) as exc:
        sys.stderr.write("%s: %s\n" % (args.capsule, exc))
        return 1

    classes = classify(writes, windows)
    tables = find_pair_tables(writes)
    os.makedirs(out, exist_ok=True)

    with open(os.path.join(out, "stack.txt"), "w", newline="\n") as fh:
        for kind, address, value in writes:
            fh.write("%s %08X %08X\n" % (kind, address, value))

    lines = ["r0004 capsule code stack"]
    if load_vaddr is not None:
        lines.append("image loads at %08X, entry %08X" % (load_vaddr, entry))
    lines.append("version %s" % version)
    lines.append("stack at image+0x%X, %d bytes ciphertext" % (offset, length))
    lines.append("key %d bytes, found at %s"
                 % (len(key), ", ".join("+0x%X" % o for o in key_offsets)))
    lines.append("game windows %s: text %s, loaded to %08X"
                 % ("PROVISIONAL (no --elf)" if windows.provisional else "from " + args.elf,
                    " ".join("%08X-%08X" % r for r in windows.text), windows.end))
    lines.append("writes %d" % len(writes))
    for name in ("resident", "code_patch", "data"):
        entries = classes[name]
        lines.append("%s %d" % (name, len(entries)))
        for first, last, count in _runs(entries):
            lines.append("    %08X-%08X  %d" % (first, last, count))
    lines.append("indirect pair tables %d" % len(tables))
    for base, entries in tables:
        lines.append("    table at %08X: %d entries, targets %08X-%08X"
                     % (base, len(entries), min(a for a, _ in entries),
                        max(a for a, _ in entries)))
    text = "\n".join(lines) + "\n"
    with open(os.path.join(out, "summary.txt"), "w", newline="\n") as fh:
        fh.write(text)
    sys.stdout.write(text)
    if windows.provisional and (classes["code_patch"] or classes["data"]):
        sys.stdout.write("WARNING: %d write(s) landed in a game-side class whose bounds are "
                         "provisional round numbers. Re-run with --elf <game ELF> before trusting "
                         "the code_patch/data split.\n"
                         % (len(classes["code_patch"]) + len(classes["data"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
