"""SASE, SOCOM II's voice codec: what the images say about it (research Q11, Sprint 12; read-only).

Run from the repo root:  python tools_py/research/symbols/sase_probe.py

Prints, section by section, every number docs/research/56-sase-codec.md cites, over the three SOCOM II
images (the Aug 18 2003 demo, r0001, r0004) with the SOCOM 1 demo as the LPC-10 contrast:

  [1] the source-path strings per image (address, unit), the `NellyNull` assert-token count and the
      version strings; then per unit the r0001 and r0004 functions that reference the unit's path
      (the __assert sites) and, for r0001, where game/r0004/match.json places each one.
  [2] the SASE code range, the externally called entry points and their callers, the reach and call
      depth of the encode and decode entries, the dead functions, the libc/libm stubs the codec calls.
  [3] the parameters: the immediates the codec-info function stores, the frame and capture constants
      of the game's wrappers, the packer's field loop, the voice object's rates.
  [4] the read-only tables the SASE code forms addresses of: address, a length bound, the access
      mnemonics, the reading unit. Addresses and lengths only -- no table byte is printed.
  [5] the builds compared: demo2 vs r0001 word by word (address immediates excepted), r0004 via
      match.json and its own path references; the LPC-10 probe of the demo (demo1's LPC-10 functions
      and three of its decoder-table windows searched for in each SOCOM II image -- counts only).

Nothing is written. Mnemonics and addresses only; the tables are described, never dumped.

    python tools_py/research/symbols/sase_probe.py --dis r0001 0x3106a0 0xa8

prints the mnemonics of one span (image demo1/demo2/r0001/r0004, hex address, byte length): the note's
per-function readings (the decode loop, the receive callback, the voice init) cite it this way.
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py.address_matcher import (Image, Side, _dest_reg, formed_addresses,  # noqa: E402
                                      load_functions, load_segments, mask_address_operands,
                                      relinked_fingerprint)
from tools_py.elf_symbols import read_elf  # noqa: E402

DEMO1 = "game/demo_scus_972_05/SCUS_972.05"
DEMO2 = "game/demo_scus_973_68/SCUS_973.68"
R1 = ("game/disc/socom2_game.elf", "recomp/socom2_ghidra.csv")
R4 = ("game/overlays_r0004/socom2_game_r0004.elf", "recomp/socom2_ghidra_r0004.csv")
MATCH = "game/r0004/match.json"

# The SASE code range of each Ghidra table: from BitPackC.c's one function (the first unit in link
# order) to the first function after the codec's hook setters, which is called from outside the codec
# (r0001: 0x256fd0 from 0x25a120; r0004: 0x257610 from 0x25a760). [2] re-checks both ends.
RANGE1 = (0x2484A0, 0x256FD0)
RANGE4 = (0x2484A0, 0x257610)
PATH = re.compile(rb"\.\./\.\./(?:Sase[A-Za-z]+|shared)/[ -~]*?\.c\x00")

# r0001 addresses the note names. Each is re-derived below from code, not trusted.
API = {
    0x24F888: "sase_encode_frame", 0x24F990: "sase_enc_create", 0x24FA30: "sase_enc_destroy",
    0x255A68: "sase_get_info", 0x255B68: "sase_decode_frame", 0x255BD0: "sase_dec_create",
    0x255C68: "sase_dec_destroy", 0x255CF8: "sase_dec_frame_done", 0x256F48: "sase_set_alloc_hook",
    0x256F68: "sase_set_free_hook", 0x24FAC0: "sase_set_vu0_mode (no caller)",
    0x252748: "sase_level_attach", 0x2527F8: "sase_level_detach", 0x2529C0: "sase_level_get_1c",
    0x252BA0: "sase_level_get_trend",
}
WRAP = {
    0x310830: "voice_codec_create", 0x3107D0: "voice_codec_destroy", 0x310750: "voice_codec_encode",
    0x3106A0: "voice_codec_decode", 0x3103D0: "voice_codec_level_trend", 0x30F990: "voice_net_fill_cb",
    0x30F7E0: "voice_net_recv_cb", 0x30FC70: "voice_net_describe", 0x3102E0: "voice_ctor",
    0x310080: "voice_init", 0x30FEF0: "voice_open_headset", 0x30EC10: "voice_tick",
    0x30F5F0: "voice_play_pcm",
}
STUB = {0x191440: "__assert", 0x195800: "memcpy", 0x196C20: "printf", 0x1B3470: "ceilf",
        0x1B3548: "cosf", 0x1B3720: "sinf", 0x1B3898: "pow", 0x1B38C8: "asinf", 0x1B38E0: "atan2f",
        0x1B38F8: "expf", 0x1B3910: "logf", 0x1B3928: "log10f", 0x1B3958: "sqrtf",
        0x1A0720: "fptodp", 0x1A0B58: "dpadd", 0x1A0BB0: "dpsub", 0x1A1100: "dpcmp", 0x1A12D8: "dptofp"}
LOADS = {0x20: "lb", 0x24: "lbu", 0x21: "lh", 0x25: "lhu", 0x23: "lw", 0x31: "lwc1", 0x37: "ld",
         0x1E: "lq", 0x28: "sb", 0x29: "sh", 0x2B: "sw", 0x39: "swc1", 0x3F: "sd"}


def words(code):
    for i in range(0, len(code) - 3, 4):
        yield i, int.from_bytes(code[i:i + 4], "little")


def branch_targets(code, start):
    """jal AND j targets outside the body: the codec tail-calls with j (0x255b68 -> 0x254ec8)."""
    out = set()
    for i, w in words(code):
        if (w >> 26) in (2, 3):
            t = ((start + i + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
            if not start <= t < start + len(code):
                out.add(t)
    return out


def path_strings(segments):
    out = {}
    for v, b in segments:
        for m in PATH.finditer(b):
            out[v + m.start()] = m.group()[:-1].decode()
    return out


def lui_site(segment, addr):
    """The address of the first lui whose pair (lui + addiu within 8 words) forms `addr`."""
    v, b = segment
    hi, lo = ((addr + 0x8000) >> 16) & 0xFFFF, addr & 0xFFFF
    for i, w in words(b):
        if (w >> 26) == 0x0F and (w & 0xFFFF) == hi:
            rt = (w >> 16) & 31
            for k in range(1, 9):
                w2 = int.from_bytes(b[i + 4 * k:i + 4 * k + 4], "little")
                if (w2 >> 26) == 0x09 and ((w2 >> 21) & 31) == rt and (w2 & 0xFFFF) == lo:
                    return v + i
    return None


def is_string(image, addr):
    return image.cstring(addr, 64, 4) is not None


def unit_of(side, lo, hi, paths):
    unit = {}
    for s in side.starts:
        if lo <= s < hi:
            for a in set(formed_addresses(side.body[s])):
                if a in paths:
                    unit[s] = paths[a].rsplit("/", 1)[1]
    return unit


def immediates_stored(code, start):
    """(register -> small immediate) then the stores of those registers: (store mnemonic, offset, value)."""
    regs, out = {}, []
    for i, w in words(code):
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op == 0x09 and rs == 0:
            regs[rt] = imm - 0x10000 if imm & 0x8000 else imm
            continue
        if op in (0x29, 0x2B, 0x3F) and rt in regs:
            out.append((LOADS[op], imm, regs[rt]))
        dest = _dest_reg(w)
        if dest is not None:
            regs.pop(dest, None)             # overwritten by anything else: no longer that immediate
    return out


def section1(img, sides, units):
    print("[1] strings and units")
    for tag, (segs, _side) in img.items():
        paths = path_strings(segs)
        sase = [p for p in paths.values() if "/Sase" in p]
        blob = b"".join(b for _v, b in segs)
        print(f"  {tag}: Sase paths {len(sase)} (SaseEncVad {sum('SaseEncVad' in p for p in sase)},"
              f" SaseDec {sum('SaseDec' in p for p in sase)}), shared paths"
              f" {sum('/shared/' in p for p in paths.values())}; 'NellyNull' occurrences"
              f" {blob.count(b'NellyNull')} in {len(re.findall(rb'[ -~]*NellyNull[ -~]*', blob))} strings; 'BSC.01.01.00' {blob.count(b'BSC.01.01.00')};"
              f" 'rt_lpc10 version' {blob.count(b'rt_lpc10 version')}; 'rt_lpc version'"
              f" {blob.count(b'rt_lpc version')}; rt_audio version"
              f" {re.findall(rb'rt_audio version: ([0-9.]+)', blob)}")
        for a in sorted(paths):
            print(f"      {a:#x}  {paths[a]}")
    match = json.load(open(MATCH))["matches"]
    r1, r4 = sides["r0001"], sides["r0004"]
    u1, u4 = units["r0001"], units["r0004"]
    print("  unit | r0001 functions (start/size) | r0004 by its own path refs | r0001's placed by match.json")
    for name in sorted(set(u1.values()) | set(u4.values()), key=str.lower):
        f1 = sorted(s for s, u in u1.items() if u == name)
        f4 = sorted(s for s, u in u4.items() if u == name)
        placed = [match.get("0x%08x" % s, {}).get("b") for s in f1]
        print(f"    {name:18s} r0001 {len(f1):2d} fn {sum(r1.size[s] for s in f1):5d} B |"
              f" r0004 {len(f4):2d} fn {sum(r4.size[s] for s in f4):5d} B |"
              f" placed {sum(p is not None for p in placed)}/{len(f1)}")
        print("        r0001: " + " ".join(f"{s:#x}/{r1.size[s]}" for s in f1))
        print("        r0004: " + " ".join(f"{s:#x}/{r4.size[s]}" for s in f4))


def section2(r1, u1):
    print("[2] call structure (r0001)")
    lo, hi = RANGE1
    fs = [s for s in sorted(r1.starts) if lo <= s < hi]
    graph = {s: branch_targets(r1.body[s], s) for s in r1.starts}
    callers = collections.defaultdict(set)
    for s, ts in graph.items():
        for t in ts:
            callers[t].add(s)
    print(f"  range {lo:#x}-{hi:#x}: {len(fs)} functions, {hi - lo} bytes; path-attributed {len(u1)}")
    first_out = min(s for s in r1.starts if s >= hi)
    print(f"  end check: {first_out:#x} called from {[hex(c) for c in sorted(callers[first_out])]},"
          f" from inside the range: {any(lo <= c < hi for c in callers[first_out])}")
    ext_in = {s: sorted(c for c in callers[s] if not lo <= c < hi) for s in fs}
    outside = sorted({c for s in fs for c in ext_in[s]})
    print(f"  distinct outside callers: {len(outside)}: {' '.join(hex(c) for c in outside)}")
    print("  functions called from outside the range (entry points) -> outside callers:")
    for s in fs:
        if ext_in[s]:
            print(f"    {s:#x} {r1.size[s]:4d} {API.get(s, u1.get(s, '')):28s} <- "
                  + " ".join(f"{c:#x}({WRAP.get(c, '')})" for c in ext_in[s]))
    for cb in (0x30F990, 0x30F7E0):
        makers = [hex(s) for s in r1.starts if cb in formed_addresses(r1.body[s])]
        print(f"  {WRAP[cb]} {cb:#x} has no direct caller; its address is formed in {makers}")
    for s in sorted(WRAP):
        into = sorted(t for t in graph.get(s, ()) if lo <= t < hi)
        print(f"  wrapper {s:#x} {WRAP[s]:24s} size {r1.size.get(s)} -> SASE {[hex(t) for t in into]}"
              f" <- {[hex(c) for c in sorted(callers[s])]}")
    sub = {s: {t for t in graph[s] if lo <= t < hi} for s in fs}

    def reach(e):
        seen, todo = set(), [e]
        while todo:
            s = todo.pop()
            if s not in seen:
                seen.add(s)
                todo += sub[s]
        return seen

    def depth(e, stack=frozenset()):
        return max((1 + depth(t, stack | {e}) for t in sub[e] if t not in stack), default=0)

    enc, dec = reach(0x24F888), reach(0x255B68)
    print(f"  encode_frame 0x24f888: reaches {len(enc)} functions, depth {depth(0x24F888)};"
          f" decode_frame 0x255b68: reaches {len(dec)}, depth {depth(0x255B68)}; shared {len(enc & dec)};"
          f" leaves {sum(1 for s in enc | dec if not sub[s])}")
    live = set()
    for s in fs:
        if ext_in[s]:
            live |= reach(s)
    dead = sorted(set(fs) - live)
    ptr = set()
    for v, b in r1.image.segments:
        for _i, w in words(b):
            if w in dead:
                ptr.add(w)
    print(f"  reached from the entry points: {len(live)}; unreached {len(dead)}"
          f" (of which named by a data word anywhere: {len(ptr)}): {' '.join(hex(s) for s in dead)}")
    stubs = collections.Counter()
    for s in fs:
        for t in graph[s]:
            if not lo <= t < hi:
                stubs[STUB.get(t, hex(t))] += 1
    print("  outside callees (call sites):", dict(sorted(stubs.items())))


def section3(r1):
    print("[3] parameters (r0001)")
    info = immediates_stored(r1.body[0x255A68], 0x255A68)
    print("  sase_get_info 0x255a68 stores (mnemonic, struct offset, immediate):",
          [(m, hex(o), v) for m, o, v in info])
    def has(body, op, rs, rt, imm):
        return any((w >> 26) == op and ((w >> 21) & 31) == rs and ((w >> 16) & 31) == rt and (w & 0xFFFF) == imm
                   for _i, w in words(body))

    c = r1.body[0x310830]
    print("  voice_codec_create 0x310830: info struct at sp+0x50 (addiu a0, sp, 0x50:", has(c, 0x09, 29, 4, 0x50),
          "); frame length from sp+0x8c = info+0x3c (addiu s0, sp, 0x8c:", has(c, 0x09, 29, 16, 0x8C),
          "); bits from sp+0xb0 = info+0x60 (ld v0, 0xb0(sp):", has(c, 0x37, 29, 2, 0xB0),
          ") -> bytes = bits/8 rounded up, packet buffer = bytes + 2")
    for fn, label in ((0x310750, "encode: memcpy length"), (0x3106A0, "decode: bytes per frame"),
                      (0x248FB0, "encoder analysis: PreProc/libsnd length")):
        body = r1.body[fn]
        found = sorted({(w & 0xFFFF) for _i, w in words(body) if (w >> 26) == 0x09 and ((w >> 21) & 31) == 0
                        and (w & 0xFFFF) in (0x8, 0xA0, 0x140)})
        print(f"  {label} ({fn:#x}): addiu-zero immediates among (8, 160, 320): {found}")
    fill = r1.body[0x30F990]
    print("  voice_net_fill_cb 0x30f990: slti 0x500 sites"
          f" {sum(1 for _i, w in words(fill) if (w >> 26) == 0x0A and (w & 0xFFFF) == 0x500)},"
          f" encode loop bound 4: {any((w >> 26) == 0x0A and (w & 0xFFFF) == 4 for _i, w in words(fill))},"
          f" gain clamp 0x14/0x65: {sum(1 for _i, w in words(fill) if (w >> 26) == 0x0A and (w & 0xFFFF) in (0x14, 0x65))}")
    ctor = immediates_stored(r1.body[0x3102E0], 0x3102E0)
    print("  voice_ctor 0x3102e0 stores into the headset format block:",
          [(hex(o), v) for m, o, v in ctor if 0x10BC <= o <= 0x10D8])
    pack = r1.body[0x24FAE8]
    print("  PackSC 0x24fae8: field loop start (addiu s1, zero, N):",
          [w & 0xFFFF for _i, w in words(pack) if (w >> 26) == 0x09 and ((w >> 21) & 31) == 0
           and ((w >> 16) & 31) == 17], "with bgezl (N+1 fields); lh from the width table")
    bp = r1.body[0x2484A0]
    print("  BitPackC 0x2484a0: 'slti ..9' (a field is at most 8 bits):",
          any((w >> 26) == 0x0A and (w & 0xFFFF) == 9 for _i, w in words(bp)))
    lvl = r1.body[0x252748]
    print("  sase_level_attach 0x252748: lui 0x45fa (8000.0f) present",
          any((w >> 26) == 0x0F and (w & 0xFFFF) == 0x45FA for _i, w in words(lvl)),
          "; frame 0xa0 present", any((w >> 26) == 0x09 and (w & 0xFFFF) == 0xA0 for _i, w in words(lvl)))
    mode = [hex(s) for s in r1.starts if any((w >> 26) == 0x2B and (w & 0xFFFF) == 0x1078
                                             for _i, w in words(r1.body[s]))]
    print("  sw ..0x1078 (the voice object's codec-mode word) sites:", mode)


def section4(r1, u1):
    print("[4] read-only tables the SASE code forms addresses of (r0001; lengths are bounds)")
    lo, hi = RANGE1
    fs = [s for s in sorted(r1.starts) if lo <= s < hi]
    paths = path_strings(r1.image.segments)
    info = collections.defaultdict(lambda: {"f": set(), "acc": collections.Counter(), "shift": collections.Counter()})
    formed = set(paths)
    bounds_of = {}
    for s in fs:
        bounds_of[s] = sorted({(w & 0xFFFF) for _i, w in words(r1.body[s])
                               if (w >> 26) in (0x0A, 0x0B) and 4 < (w & 0xFFFF) < 0x1000})
        high, derived, shifted = {}, {}, {}
        for _i, w in words(r1.body[s]):
            op, rs, rt, rd, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, w & 0xFFFF
            simm = imm - 0x10000 if imm & 0x8000 else imm
            if op == 0x0F:
                high[rt] = imm
                derived.pop(rt, None)
            elif op in (0x08, 0x09) and rs in high:
                a = ((high.pop(rs) << 16) + simm) & 0xFFFFFFFF
                derived[rt] = a
                formed.add(a)
                info[a]["f"].add(s)
            elif op in LOADS and rs in high:
                a = ((high[rs] << 16) + simm) & 0xFFFFFFFF
                formed.add(a)
                info[a]["f"].add(s)
                info[a]["acc"][LOADS[op]] += 1
            elif op in LOADS and rs in derived:
                info[derived[rs]]["acc"][LOADS[op]] += 1
            elif op == 0 and (w & 0x3F) in (0x21, 0x2D) and (rs in derived or rt in derived):
                base = derived.get(rs, derived.get(rt))
                index = rt if rs in derived else rs
                if index in shifted:
                    info[base]["shift"][shifted[index]] += 1
                derived[rd] = base
            elif op == 0 and (w & 0x3F) == 0 and w:
                shifted[rd] = (w >> 6) & 31
    bounds = sorted(formed)
    for a in sorted(info):
        if not 0x3D5000 <= a < 0x408480 or a in paths or is_string(r1.image, a):
            continue
        nxt = next((b for b in bounds if b > a), None)
        if nxt is None or nxt - a < 32:
            continue
        us = sorted({u1.get(f, "~%x" % f) for f in info[a]["f"]})
        slti = sorted({b for f in info[a]["f"] for b in bounds_of.get(f, ())})
        print(f"  {a:#x} len<={nxt - a:5d} access={dict(info[a]['acc'])} index-shift={dict(info[a]['shift'])}"
              f" slti-bounds-in-readers={slti} readers={us}")
    # libquan's spectral quantizer 0x24b028: two 6-pointer arrays (per sub-vector predictor matrices) and
    # the descriptors of its structured 2-D VQ stages. Pointers and the gaps between them only.
    def ptrs(a, n):
        b = r1.image.code(a, a + 4 * n)
        return [int.from_bytes(b[i:i + 4], "little") for i in range(0, len(b), 4)]

    for arr in (0x3DCFC8, 0x3DCFE0):
        p = ptrs(arr, 6)
        gaps = [p[i + 1] - p[i] for i in range(1, 5)]
        print(f"  libquan pointer array {arr:#x}: 6 words, first null {p[0] == 0}, targets"
              f" {[hex(x) for x in p[1:]]}, byte gaps {gaps}")
    for d in (0x3E8928, 0x3E8D78, 0x3E90D0, 0x3E93A8, 0x3E9638):
        p = [x for x in ptrs(d, 8) if 0x3D5000 <= x < 0x408480]
        print(f"  libquan stage descriptor {d:#x}: 8 words, {len(p)} pointers, gaps between them"
              f" {[p[i + 1] - p[i] for i in range(len(p) - 1)]}, last to descriptor {d - p[-1]}")
    sd = ptrs(0x1D5548, 2)
    print(f"  libquan plain-VQ codebook descriptor at 0x1d5548 (small data): entries {sd[0]}, pointer {sd[1]:#x}")
    print("  VU0 upload 0x252150: micro image 0x3d5980..0x3d6750 (memcpy length = end - start ="
          f" {0x3D6750 - 0x3D5980}), then a 0x7e0-byte block from 0x3eb088 by ld/sd to VU0 data 0x11004800")


def section5(img, sides, units):
    print("[5] builds compared")
    r1, r4 = sides["r0001"], sides["r0004"]
    lo, hi = RANGE1
    fs = [s for s in sorted(r1.starts) if lo <= s < hi]
    d2segs = img["demo2"][0]
    d2 = Image(d2segs)
    d2paths = path_strings(d2segs)
    delta = min(a for a, p in d2paths.items() if p.endswith("BitPackC.c"))
    r1paths = path_strings(r1.image.segments)
    rodelta = delta - min(a for a, p in r1paths.items() if p.endswith("BitPackC.c"))
    # the code delta: demo2's one BitPackC.c function against r0001's
    v2, b2 = d2segs[0]
    target = min(s for s, u in units["r0001"].items() if u == "BitPackC.c")
    r1path = min(a for a, p in r1paths.items() if p.endswith("BitPackC.c"))
    code_delta = lui_site(d2segs[0], delta) - lui_site((target, r1.body[target]), r1path)
    same, other, bad = 0, [], 0
    for s in fs:
        a = r1.body[s]
        b = d2.code(s + code_delta, s + code_delta + len(a))
        if relinked_fingerprint(b) == r1.relfp(s):
            same += 1
            continue
        other.append(s)
        for (i, x), (_j, y) in zip(words(a), words(b)):
            if x != y and (x >> 26) != (y >> 26):
                bad += 1
    print(f"  demo2: SASE code at r0001+{code_delta:#x} (rodata at +{rodelta:#x});"
          f" {same}/{len(fs)} functions relinked-identical, {len(other)} differ only in same-opcode words"
          f" (opcode mismatches: {bad}): {[hex(s) for s in other]}")
    d2info = immediates_stored(d2.code(0x255A68 + code_delta, 0x255A68 + code_delta + 0x100), 0)
    print("  demo2 sase_get_info immediates equal r0001's:",
          d2info == immediates_stored(r1.body[0x255A68], 0x255A68)[:len(d2info)])
    match = json.load(open(MATCH))["matches"]
    how = collections.Counter(match.get("0x%08x" % s, {}).get("how", "absent") for s in fs)
    lo4, hi4 = RANGE4
    fs4 = [s for s in sorted(r4.starts) if lo4 <= s < hi4]
    rel4 = collections.Counter(r4.relfp(s) for s in fs4)
    ident = sum(1 for s in fs if rel4.get(r1.relfp(s)))
    print(f"  r0004: range {lo4:#x}-{hi4:#x} {len(fs4)} functions {hi4 - lo4} bytes; of r0001's {len(fs)},"
          f" {ident} have a relinked-identical body in r0004's range (independent of match.json)")
    print(f"  match.json as it stands (it is regenerated by other work; summary {json.load(open(MATCH))['summary']}):"
          f" r0001's {len(fs)} placed as {dict(how)}")
    i4 = match["0x%08x" % 0x255A68]["b"]
    info4 = immediates_stored(r4.body[int(i4, 16)], int(i4, 16))
    print(f"  r0004 sase_get_info {i4}: immediates equal r0001's:",
          info4 == immediates_stored(r1.body[0x255A68], 0x255A68))
    # PackSC's width table in each build: the one non-string address PackSC forms; compared, never printed.
    def width_table(image, packsc):
        return next(a for a in formed_addresses(image.code(packsc, packsc + 252)) if not is_string(image, a))

    wt1 = width_table(r1.image, 0x24FAE8)
    wt4 = width_table(r4.image, min(s for s, u in units["r0004"].items() if u == "PackSC.c"))
    wt2 = width_table(d2, 0x24FAE8 + code_delta)
    t1 = r1.image.code(wt1, wt1 + 34)
    print(f"  PackSC width table (17 x 16-bit): r0001 {wt1:#x}, r0004 {wt4:#x}, demo2 {wt2:#x};"
          f" r0004 == r0001: {r4.image.code(wt4, wt4 + 34) == t1}, demo2 == r0001: {d2.code(wt2, wt2 + 34) == t1}")
    vu = r1.image.code(0x3D5980, 0x3D6750)
    print(f"  VU0 image (3,536 B) verbatim in demo2: {vu in b''.join(b for _v, b in d2segs)}")
    raw4 = open(R4[0], "rb").read()
    blk = r1.image.code(0x3E7968, 0x3E7968 + 20940)
    chunks = [blk[i:i + 64] for i in range(0, len(blk) - 64, 64) if blk[i:i + 64].count(0) <= 32]
    print(f"  r0001 SASE rodata block 0x3e7968 (+20940 B): {len(chunks)} 64-byte chunks,"
          f" {sum(c in raw4 for c in chunks)} found verbatim in r0004; VU0 image verbatim in r0004:"
          f" {r1.image.code(0x3D5980, 0x3D6750) in raw4}")
    for tag, (segs, _s) in img.items():
        for v, b in segs:
            m = re.search(rb"\.\./\.\./SaseEncVad/source/BitPackC\.c", b)
            if m:
                sw = b.find(b"SWSynth.c", m.start())
                end = b.find(b"*plSeed != 0", sw) + len(b"*plSeed != 0")
                print(f"  {tag}: SASE rodata block BitPackC.c path -> SWSynth's last assert: {end - m.start()} B")
    # LPC-10: demo1's functions and three windows of its decoder tables, searched for in each image
    e1 = read_elf(DEMO1)
    d1 = Image(load_segments(e1.data))
    lpc = [f for f in e1.functions if re.match(
        r"(lpc10_|voicin_|pitsyn_|analys_|bsynz_|chanwr_|chanrd_|dcbias_|decode_|encode_|energy_|hp100_|"
        r"invert_|irc2pc_|ivfilt_|lpfilt_|median_|mload_|onset_|placea_|placev_|preemp_|prepro_|random_|"
        r"rcchk_|synths_|tbdm_|vparms_|difmag_|dyptrk_|ham84_|deemp_|lpcini_|init_lpc|create_lpc)", f[2])]
    print(f"  demo1 LPC-10 functions: {len(lpc)}, {sum(e - s for s, e, _n in lpc)} bytes")
    dec = next(f for f in lpc if f[2].startswith("decode_"))
    wins = []
    for a in sorted(set(formed_addresses(d1.code(dec[0], dec[1])))):
        w = d1.code(a, a + 32)
        if len(w) == 32 and w.count(0) <= 16:
            wins.append(w)
    starts = sorted({((v2 + i + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
                     for i, w in words(b2) if (w >> 26) in (2, 3)})
    starts = [s for s in starts if v2 <= s < v2 + len(b2)]
    heads = set()
    for i in range(len(starts) - 1):
        if starts[i + 1] - starts[i] < 0x8000:
            heads.add(mask_address_operands(b2[starts[i] - v2:starts[i] - v2 + 48]))
    lpc_found = sum(mask_address_operands(d1.code(s, e))[:48] in heads for s, e, _n in lpc)
    sase_found = sum(mask_address_operands(r1.body[s])[:48] in heads for s in fs if r1.size[s] >= 48)
    print(f"  demo2 jal/j-partition: {len(starts)} starts; masked 48-byte heads matching demo1's LPC-10"
          f" functions {lpc_found}/{len(lpc)} (control: r0001 SASE functions >= 48 B matched"
          f" {sase_found}/{sum(r1.size[s] >= 48 for s in fs)})")
    for tag, (segs, _s) in img.items():
        blob = b"".join(b for _v, b in segs)
        print(f"  {tag}: demo1 decode_ data windows (32 B) found {sum(w in blob for w in wins)}/{len(wins)}")
    # demo2: the code that reads those windows
    lpcstr = v2 + b2.find(b"rt_lpc10 version")
    readers = []
    for i in range(len(starts) - 1):
        s, e = starts[i], starts[i + 1]
        if e - s < 0x4000 and any(lpcstr <= a < lpcstr + 0x1000 for a in formed_addresses(b2[s - v2:e - v2])):
            readers.append((s, e - s))
    print(f"  demo2: 'rt_lpc10 version' at {lpcstr:#x}; functions (jal/j partition) forming addresses in the"
          f" next 4 KB: {[(hex(s), n) for s, n in readers]}")
    def distinct_callees(image_code, start):
        return len(branch_targets(image_code, start))

    for dname in ("analys_", "synths_", "lpc10_encode", "lpc10_decode"):
        s, e, _n = next(f for f in lpc if f[2].startswith(dname))
        print(f"  demo1 {dname}: {e - s} B, {distinct_callees(d1.code(s, e), s)} distinct callees")
    for s in (0x487918, 0x4910B8, 0x48F1D8, 0x493600):
        i = starts.index(s)
        print(f"  demo2 {s:#x}: {starts[i + 1] - s} B, "
              f"{distinct_callees(b2[s - v2:starts[i + 1] - v2], s)} distinct callees")
    clus = [s for s in starts if 0x48F1D8 <= s < 0x496388]
    print(f"  demo2: partition functions in 0x48f1d8-0x496388: {len(clus)}, {0x496388 - 0x48F1D8} bytes")


def disassemble(tag, addr, length):
    """Mnemonics for a span, with the R5900 quadword loads/stores capstone does not know (lq/sq)."""
    import capstone
    path = {"demo2": DEMO2, "r0001": R1[0], "r0004": R4[0], "demo1": DEMO1}[tag]
    code = Image(load_segments(open(path, "rb").read())).code(addr, addr + length)
    md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS64 + capstone.CS_MODE_LITTLE_ENDIAN)
    for i, w in words(code):
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op in (0x1E, 0x1F):
            text = f"{'lq' if op == 0x1E else 'sq'} ${rt}, {imm - 0x10000 if imm & 0x8000 else imm:#x}(${rs})"
        else:
            got = list(md.disasm(code[i:i + 4], addr + i))
            text = f"{got[0].mnemonic} {got[0].op_str}" if got else "(r5900-only)"
        print(f"{addr + i:#x}: {text}")


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "--dis":
        disassemble(sys.argv[2], int(sys.argv[3], 16), int(sys.argv[4], 0))
        return
    segs2 = load_segments(open(DEMO2, "rb").read())
    s1 = Side(load_functions(R1[1]), load_segments(open(R1[0], "rb").read()))
    s4 = Side(load_functions(R4[1]), load_segments(open(R4[0], "rb").read()))
    img = {"demo2": (segs2, None), "r0001": (s1.image.segments, s1), "r0004": (s4.image.segments, s4)}
    sides = {"r0001": s1, "r0004": s4}
    units = {"r0001": unit_of(s1, *RANGE1, path_strings(s1.image.segments)),
             "r0004": unit_of(s4, *RANGE4, path_strings(s4.image.segments))}
    section1(img, sides, units)
    section2(s1, units["r0001"])
    section3(s1)
    section4(s1, units["r0001"])
    section5(img, sides, units)


if __name__ == "__main__":
    main()
