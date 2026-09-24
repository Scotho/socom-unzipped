"""What the SOCOM 1 demo's DWARF1 `.debug` section holds, walked by ccc, and which of the raw guest field
offsets the parity tools and the hooks use have a SOCOM 1 name that SOCOM II's own code agrees with.
(Sprint 12 research wave, question 5; docs/research/50-ccc-dwarf1-types.md is the note it backs.)

Run from the repo root:   python tools_py/research/symbols/dwarf_types.py [section ...]

    sections:  census  types  units  offsets  age  missing   (default: all six, in that order)
    --write-types   also write the whole type list to game/demo_types.txt (git-ignored)
    --selfcheck     also walk the section with this file's own minimal DWARF1 reader and compare the
                    tag census with ccc's (the two must agree DIE for DIE)

The DWARF is decoded by ccc (chaoticgd, https://github.com/chaoticgd/ccc, main branch, built from source):
    $CCC_BIN symbols --section .debug dwarf game/demo_scus_972_05/SCUS_972.05
CCC_BIN defaults to /home/user/tools/ccc/build/stdump (ccc main at c025ca9, `cmake -B build && cmake
--build build`). The twin alignment needs numpy. ccc's `types`/`json` commands cannot be used on
this file (main prints `TAG_class_type support not yet implemented.` for every class; the `dwarf_types`
branch prints classes with no offsets and 27,742 `TODO: Type name.`), but its raw DIE dump is complete,
so this script reads that dump and builds the layouts itself.

What it prints, by section:
  census   DIE counts by tag; compile-unit DIEs vs translation units (a unit is one pc-less CU that holds
           the unit's types and data, followed by one CU per function); the source file per unit, by
           directory; subprograms, members, enums, locals and parameters.
  types    the distinct class layouts (a class_type DIE per unit, deduplicated on name + size + members),
           the 40 largest by member count, and the classes the project names by hand, with sizes.
  units    which translation unit each of research/44's 987 matched demo functions came from, where the
           .debug says so; the top 15 units by matched count; where the rest sit.
  offsets  for every raw field offset research/46 section 3 lists (the parity tools' and the hooks'): the
           demo's field at that offset in the candidate class (flattened through bases, nested members
           resolved), then SOCOM II's access pattern -- demo member functions twinned into r0001 and
           aligned instruction for instruction on the `this` register (the actor also through its
           constructor's store sequence, aligned between the two builds), r0001 functions using the
           displacement twinned back into the demo, the demo neighbours that share the shift, and the
           same uses followed into r0004 through game/r0004/match.json -- and a verdict. CZNetGame's
           valve slots are also checked by name against SOCOM II's own valve names (research/19 F2).
  age      the layout-age caveat: the twin finder's false-pair rate against research/44's pairs; for
           classes with a demo layout and >= 3 body-matched members, the fields the body-matched members
           use (unchanged by construction) and, through the edited members' twins, how many demo fields
           sit at the same offset in r0001 and how many moved; a control that runs the same alignment
           r0001 -> r0004.
  missing  the LPC-10 codec's units and their types, units with no class type of their own, and the
           classes with member functions in .symtab but no layout in .debug.

Read-only over its inputs; writes nothing but game/demo_types.txt (and only with --write-types). Prints
names, addresses, offsets and counts, never game bytes.
"""
import bisect
import collections
import json
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py.elf_symbols import read_elf  # noqa: E402

CCC_BIN = os.environ.get("CCC_BIN", "/home/user/tools/ccc/build/stdump")
DEMO = "game/demo_scus_972_05/SCUS_972.05"
R1_ELF, R1_CSV = "game/disc/socom2_game.elf", "recomp/socom2_ghidra.csv"
R4_ELF, R4_CSV = "game/overlays_r0004/socom2_game_r0004.elf", "recomp/socom2_ghidra_r0004.csv"
MATCHES = "game/demo_symbol_matches.json"
R4_MATCH = "game/r0004/match.json"
TYPES_OUT = "game/demo_types.txt"
BS = chr(92)

# --------------------------------------------------------------------------------------------------
# 1. ccc's raw DIE dump -> a tree
# --------------------------------------------------------------------------------------------------
LINE_RE = re.compile(r"^\s*([0-9a-f]+):\t(\t*)(\S+)(.*)$")


class Die:
    __slots__ = ("off", "depth", "tag", "attrs", "children", "parent", "cu")

    def __init__(self, off, depth, tag, attrs):
        self.off, self.depth, self.tag, self.attrs = off, depth, tag, attrs
        self.children, self.parent, self.cu = [], None, None

    @property
    def name(self):
        return self.attrs.get("name")


def split_attrs(s):
    """ccc prints `key=value` pairs separated by single spaces; a value is a quoted string, a braced group
    (nested braces allowed) with an optional `@offset` suffix, or a bare token."""
    out, i, n = {}, 0, len(s)
    while i < n:
        while i < n and s[i] == " ":
            i += 1
        if i >= n:
            break
        j = s.index("=", i)
        key = s[i:j]
        i = j + 1
        if i < n and s[i] == '"':
            k = s.index('"', i + 1)
            val, i = s[i + 1:k], k + 1
        elif i < n and s[i] == "{":
            depth, k = 0, i
            while True:
                if s[k] == "{":
                    depth += 1
                elif s[k] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            k += 1
            while k < n and s[k] != " ":  # the `@offset` suffix ccc gives unknown blocks
                k += 1
            val, i = s[i:k], k
        else:
            k = s.find(" ", i)
            k = n if k < 0 else k
            val, i = s[i:k], k
        out[key] = val
    return out


def ccc_dump():
    """Run ccc over the demo's .debug and return its text."""
    if not os.path.isfile(CCC_BIN):
        sys.exit("ccc not found at %s (set CCC_BIN; build: git clone https://github.com/chaoticgd/ccc && "
                 "cmake -B build && cmake --build build)" % CCC_BIN)
    return subprocess.run([CCC_BIN, "symbols", "--section", ".debug", "dwarf", DEMO],
                          check=True, capture_output=True, text=True, errors="replace").stdout


def parse_dump(text):
    """(top-level DIEs, {offset: Die}). Nesting is the dump's tab depth; each DIE records its top CU."""
    top, by_off, stack = [], {}, []
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        off, depth, tag = int(m.group(1), 16), len(m.group(2)), m.group(3)
        die = Die(off, depth, tag, split_attrs(m.group(4)))
        by_off[off] = die
        del stack[depth:]
        if stack:
            die.parent = stack[-1]
            stack[-1].children.append(die)
            die.cu = stack[0]
        else:
            top.append(die)
            die.cu = die
        stack.append(die)
    return top, by_off


# --------------------------------------------------------------------------------------------------
# 1b. an independent minimal DWARF 1.1 walker, used only by --selfcheck to confirm ccc's tag census
# --------------------------------------------------------------------------------------------------
TAG_NAMES = {0x01: "array_type", 0x02: "class_type", 0x03: "entry_point", 0x04: "enumeration_type",
             0x05: "formal_parameter", 0x06: "global_subroutine", 0x07: "global_variable",
             0x0a: "label", 0x0b: "lexical_block", 0x0c: "local_variable", 0x0d: "member",
             0x0f: "pointer_type", 0x10: "reference_type", 0x11: "compile_unit", 0x12: "string_type",
             0x13: "structure_type", 0x14: "subroutine", 0x15: "subroutine_type", 0x16: "typedef",
             0x17: "union_type", 0x18: "unspecified_parameters", 0x19: "variant", 0x1a: "common_block",
             0x1b: "common_inclusion", 0x1c: "inheritance", 0x1d: "inlined_subroutine", 0x1e: "module",
             0x1f: "ptr_to_member_type", 0x20: "set_type", 0x21: "subrange_type", 0x22: "with_stmt"}
FORM_SIZE = {0x1: 4, 0x2: 4, 0x5: 2, 0x6: 4, 0x7: 8}  # ADDR REF DATA2 DATA4 DATA8; BLOCK2/4, STRING below


def own_walk(debug):
    """Tag census by walking the DIE chain: 4-byte length, 2-byte tag, attributes (2-byte name whose low
    nibble is the form). A length under 8 is a null entry. Returns (Counter, first CU name)."""
    census, pos, first_cu = collections.Counter(), 0, None
    while pos + 4 <= len(debug):
        length = struct.unpack_from("<I", debug, pos)[0]
        if length < 8:
            pos += max(length, 4)
            continue
        tag = struct.unpack_from("<H", debug, pos + 4)[0]
        census[TAG_NAMES.get(tag, "tag_0x%x" % tag)] += 1
        if tag == 0x11 and first_cu is None:  # validate on the first compile unit's AT_name
            p, end = pos + 6, pos + length
            while p < end:
                at = struct.unpack_from("<H", debug, p)[0]
                p += 2
                form = at & 0xF
                if form == 0x8:
                    z = debug.index(b"\0", p)
                    if at == 0x0038:
                        first_cu = debug[p:z].decode("latin1")
                    p = z + 1
                elif form == 0x3:
                    p += 2 + struct.unpack_from("<H", debug, p)[0]
                elif form == 0x4:
                    p += 4 + struct.unpack_from("<I", debug, p)[0]
                else:
                    p += FORM_SIZE[form]
        pos += length
    return census, first_cu


# --------------------------------------------------------------------------------------------------
# 2. types
# --------------------------------------------------------------------------------------------------
FUND_SIZE = {"char": 1, "signed_char": 1, "unsigned_char": 1, "short": 2, "signed_short": 2,
             "unsigned_short": 2, "integer": 4, "signed_integer": 4, "unsigned_integer": 4, "long": 4,
             "signed_long": 4, "unsigned_long": 4, "pointer": 4, "float": 4, "dbl_prec_float": 8,
             "long_long": 8, "signed_long_long": 8, "unsigned_long_long": 8, "int128": 16, "boolean": 1,
             "void": 0}
CONST_RE = re.compile(r"const\((0x[0-9a-f]+)\)")


def split_top(s, sep=","):
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


class Types:
    def __init__(self, by_off):
        self.by_off = by_off

    def ref(self, text):
        tag, _, off = text.partition("@")
        return self.by_off.get(int(off, 16)) if off else None

    def base_desc(self, text):
        """(description, size) of `fund` or `tag@off` or `{mod,...,base}`."""
        if text.startswith("{"):
            parts = split_top(text[1:-1])
            desc, size = self.base_desc(parts[-1])
            for mod in reversed(parts[:-1]):
                desc, size = desc + {"pointer_to": "*", "reference_to": "&"}.get(mod, " " + mod), 4
            return desc, size
        if "@" in text:
            die = self.ref(text)
            if die is None:
                return text, None
            if die.tag == "array_type":
                return self.array_desc(die)
            if die.tag == "subroutine_type":
                return "fn", None
            size = die.attrs.get("byte_size")
            return (die.name or text.split("@")[0]), (int(size, 16) if size else None)
        return text, FUND_SIZE.get(text)

    def array_desc(self, die):
        parts = split_top(die.attrs.get("subscr_data", "{}")[1:-1])
        dims = [p for p in parts if p.startswith("[")]
        desc, size = self.base_desc(parts[-1])
        for d in dims:
            _, lo, hi = d[1:-1].split(",")
            count = int(hi, 16) - int(lo, 16) + 1
            desc += "[%d]" % count
            size = size * count if size is not None else None
        return desc, size

    def type_of(self, die):
        a = die.attrs
        for key in ("fund_type", "user_def_type", "mod_fund_type", "mod_u_d_type"):
            if key in a:
                return self.base_desc(a[key])
        return "?", None

    @staticmethod
    def location(die):
        m = CONST_RE.search(die.attrs.get("location", ""))
        return int(m.group(1), 16) if m else None

    def direct(self, cls):
        """[(offset, name, type, size, bits)] for the class's own members (bases excluded)."""
        out = []
        for ch in cls.children:
            if ch.tag == "member":
                desc, size = self.type_of(ch)
                bits = None
                if "bit_size" in ch.attrs:
                    bits = (int(ch.attrs["bit_offset"], 16), int(ch.attrs["bit_size"], 16))
                out.append((self.location(ch), ch.name, desc, size, bits))
        return out

    def bases(self, cls):
        out = []
        for ch in cls.children:
            if ch.tag == "inheritance":
                base = self.ref(ch.attrs.get("user_def_type", ""))
                out.append((self.location(ch) or 0, base))
        return out

    def flat(self, cls, base=0, path="", depth=0):
        """The class's whole layout through its bases: [(offset, 'Class::field', type, size, bits)]."""
        out = []
        if depth > 12:
            return out
        for off, b in self.bases(cls):
            if b is not None:
                out += self.flat(b, base + off, path, depth + 1)
        for off, name, desc, size, bits in self.direct(cls):
            if off is not None:
                out.append((base + off, "%s::%s" % (cls.name, name), desc, size, bits))
        return sorted(out, key=lambda r: (r[0], r[4] or (0, 0)))


def type_die(t, member):
    """(class DIE, element size, count) for a member whose type is a class or an array of one."""
    a = member.attrs
    if "user_def_type" not in a:
        return None, None, None
    die = t.ref(a["user_def_type"])
    if die is None:
        return None, None, None
    if die.tag == "class_type":
        return die, int(die.attrs.get("byte_size", "0"), 16), 1
    if die.tag == "array_type":
        parts = split_top(die.attrs.get("subscr_data", "{}")[1:-1])
        elem = parts[-1]
        if "@" in elem and not elem.startswith("{"):
            e = t.ref(elem)
            if e is not None and e.tag == "class_type":
                count = 1
                for d in parts[:-1]:
                    _, lo, hi = d[1:-1].split(",")
                    count *= int(hi, 16) - int(lo, 16) + 1
                return e, int(e.attrs.get("byte_size", "0"), 16), count
    return None, None, None


def deep_name(t, cls, off, depth=0):
    """The leaf field at a byte offset, descending through bases, class members and arrays of classes:
    `_reent::_new` + 0x50 -> `_reent::_new._reent._rand_next`. None when nothing covers it."""
    if cls is None or depth > 8:
        return None
    for o, b in t.bases(cls):
        if b is not None and o <= off < o + int(b.attrs.get("byte_size", "0"), 16):
            r = deep_name(t, b, off - o, depth + 1)
            if r:
                return r
    best = None
    for ch in cls.children:
        if ch.tag != "member":
            continue
        o = t.location(ch)
        desc, size = t.type_of(ch)
        if o is None or size is None or not (o <= off < o + max(size, 1)):
            continue
        sub, esize, count = type_die(t, ch)
        name = "%s::%s" % (cls.name, ch.name)
        if sub is not None and esize:
            idx, rem = divmod(off - o, esize)
            inner = deep_name(t, sub, rem, depth + 1)
            label = name + ("[%d]" % idx if count > 1 else "")
            best = label + ("." + inner.split("::", 1)[-1] if inner else ("+%#x" % rem if rem else ""))
        else:
            best = name + ("+%#x" % (off - o) if off != o else "")
        if off == o or sub is not None:
            return best
    return best


def class_key(t, cls):
    return (cls.name, cls.attrs.get("byte_size"),
            tuple((o, n) for o, n, _, _, _ in t.direct(cls)),
            tuple((o, b.name if b else None) for o, b in t.bases(cls)))


def distinct_classes(top, t):
    """{name: [(die, units)]} -- one entry per distinct layout of that name."""
    seen, units = {}, collections.defaultdict(set)
    for cu in top:
        for d in cu.children:
            if d.tag == "class_type":
                k = class_key(t, d)
                seen.setdefault(k, d)
                units[k].add(cu.attrs.get("name"))
    out = collections.defaultdict(list)
    for k, d in seen.items():
        out[d.name].append((d, units[k]))
    return out


# --------------------------------------------------------------------------------------------------
# 3. instruction-level twins: displacement-free alignment and `this`-relative field uses
# --------------------------------------------------------------------------------------------------
from tools_py import address_matcher as AM  # noqa: E402

SP, GP, ZERO, A0 = 29, 28, 0, 4
MOVE_FUNCTS = (0x21, 0x25, 0x2D)                      # addu / or / daddu with $zero: a register copy
CALLER_SAVED = frozenset(list(range(1, 16)) + [24, 25, 31])


def mem_width(op):
    return {0x20: 1, 0x24: 1, 0x28: 1, 0x21: 2, 0x25: 2, 0x29: 2, 0x1E: 16, 0x1F: 16, 0x36: 16,
            0x3E: 16, 0x37: 8, 0x3F: 8, 0x35: 8, 0x3D: 8, 0x1A: 8, 0x1B: 8, 0x2C: 8, 0x2D: 8}.get(op, 4)


class Body:
    """One function's instruction words, alignment tokens, and its memory accesses with the set of
    registers that alias `this` ($a0 at entry, followed through register copies, dropped at a call or
    any other write) at each one."""
    __slots__ = ("addr", "words", "tokens", "mem", "hist", "lea")

    def __init__(self, addr, code):
        self.addr = addr
        n = len(code) // 4
        self.words = struct.unpack("<%dI" % n, code[:n * 4])
        masked = struct.unpack("<%dI" % n, AM.mask_address_operands(code[:n * 4]))
        toks, mem, alias, clobber_after, lea = [], {}, {A0}, None, {}
        slots = set()                                  # $sp displacements that hold `this` (a spill)
        hist = collections.Counter()
        for i, w in enumerate(self.words):
            op = w >> 26
            if op == 0 or op == 0x1C:
                tok = w
                hist[(op << 6) | (w & 0x3F)] += 1
            elif op in AM.JUMP_OPS:
                tok = op << 26
                hist[op << 6] += 1
            else:
                tok = w & 0xFFFF0000                   # every immediate, displacement included, dropped
                hist[op << 6] += 1
            toks.append(tok)
            if op in AM.MEM_OPS:
                base = (w >> 21) & 0x1F
                disp = w & 0xFFFF
                disp = disp - 0x10000 if disp & 0x8000 else disp
                global_access = masked[i] != w or base in (GP, ZERO)
                if base != SP and not global_access:
                    mem[i] = (op, base, (w >> 16) & 0x1F, disp, base in alias)
            if op == 0x09 and ((w >> 21) & 0x1F) in alias and (w & 0xFFFF) < 0x8000:
                lea[i] = w & 0xFFFF                    # addiu rt, this, off: a member's address
            # the alias set, updated after this instruction
            if clobber_after == i:
                alias -= CALLER_SAVED
                clobber_after = None
            if op == 0 and (w & 0x3F) in MOVE_FUNCTS:
                rs, rt, rd = (w >> 21) & 0x1F, (w >> 16) & 0x1F, (w >> 11) & 0x1F
                src = rs if rt == ZERO else (rt if rs == ZERO else None)
                if src is not None and src in alias:
                    alias.add(rd)
                    continue
            if op in (0x2B, 0x3F, 0x1F) and ((w >> 21) & 0x1F) == SP:   # sw/sd/sq to the frame
                slot, rt = w & 0xFFFF, (w >> 16) & 0x1F
                if rt in alias:
                    slots.add(slot)
                else:
                    slots.discard(slot)
            if op in (0x23, 0x37, 0x1E) and ((w >> 21) & 0x1F) == SP and (w & 0xFFFF) in slots:
                alias.add((w >> 16) & 0x1F)            # a reload of the spilled `this`
                continue
            dest = AM._dest_reg(w)
            if dest is not None:
                alias.discard(dest)
            if op == AM.JAL or (op == 0 and (w & 0x3F) == 0x09):
                clobber_after = i + 1                  # the delay slot still sees the old registers
        self.tokens, self.mem, self.hist, self.lea = toks, mem, hist, lea


def image_bodies(elf_path, funcs):
    """{start: Body} for (start, end, name) rows."""
    img = AM.Image(AM.load_segments(open(elf_path, "rb").read()))
    out = {}
    for s, e, _ in funcs:
        code = img.code(s, e)
        if len(code) >= 8:
            out[s] = Body(s, code)
    return out


def csv_funcs(path):
    return AM.load_functions(path)


def align(a, b):
    """[(ia, ib)] instruction pairs in the displacement-free alignment, and its ratio."""
    import difflib
    sm = difflib.SequenceMatcher(None, a.tokens, b.tokens, autojunk=False)
    pairs = []
    for ia, ib, n in sm.get_matching_blocks():
        pairs += [(ia + k, ib + k) for k in range(n)]
    total = len(a.tokens) + len(b.tokens)
    return pairs, (2.0 * len(pairs) / total if total else 0.0)


def field_map(a, b, pairs, this_only=True):
    """[(disp_a, disp_b, op, width)] for aligned memory accesses on a `this`-aliased base register on
    both sides (or on any matching non-frame base register when this_only is False)."""
    out = []
    for ia, ib in pairs:
        ma, mb = a.mem.get(ia), b.mem.get(ib)
        if ma and mb and (not this_only or (ma[4] and mb[4])):
            out.append((ma[3], mb[3], ma[0], mem_width(ma[0])))
    return out


class TwinFinder:
    """The r0001 (or demo) function whose displacement-free instruction stream best aligns with a given
    body: an opcode-histogram prefilter (numpy cosine, sizes within 0.6x-1.6x), then difflib's ratio on
    the top ten. A twin is accepted at ratio >= MIN_RATIO and a margin >= MIN_MARGIN over the runner-up;
    both thresholds are measured against research/44's pairs (`twins` holdout, printed by `age`)."""
    MIN_RATIO, MIN_MARGIN, TOPK = 0.60, 0.10, 10

    def __init__(self, bodies):
        import numpy as np
        self.np = np
        self.bodies = list(bodies.values())
        self.sizes = np.array([len(b.tokens) for b in self.bodies])
        keys = sorted({k for b in self.bodies for k in b.hist})
        self.index = {k: i for i, k in enumerate(keys)}
        m = np.zeros((len(self.bodies), len(keys)), dtype=np.float32)
        for r, b in enumerate(self.bodies):
            for k, v in b.hist.items():
                m[r, self.index[k]] = v
        m /= np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)
        self.m = m

    def find(self, body, exclude=()):
        np = self.np
        v = np.zeros(self.m.shape[1], dtype=np.float32)
        for k, c in body.hist.items():
            if k in self.index:
                v[self.index[k]] = c
        v /= max(np.linalg.norm(v), 1e-9)
        n = len(body.tokens)
        ok = (self.sizes >= 0.6 * n) & (self.sizes <= 1.6 * n)
        cos = np.where(ok, self.m @ v, -1.0)
        top = np.argsort(-cos)[:self.TOPK]
        scored = []
        for r in top:
            if cos[r] <= 0:
                continue
            cand = self.bodies[r]
            if cand.addr in exclude:
                continue
            pairs, ratio = align(body, cand)
            scored.append((ratio, cand.addr, pairs))
        scored.sort(key=lambda x: -x[0])
        if not scored:
            return None, 0.0, 0.0, []
        best = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        return best[1], best[0], best[0] - second, best[2]

    def accept(self, ratio, margin):
        return ratio >= self.MIN_RATIO and margin >= self.MIN_MARGIN


def events(body):
    """The ordered `this`-relative stores and member-address computations of a body: [(token, disp)].
    A constructor initialises members in declaration order in both builds, so this sequence aligns
    across a recompile even where the instruction streams do not (the demo's zseal code spills `this`
    to the frame and reloads it per access; r0001's keeps it in a saved register)."""
    out = []
    for i in sorted(set(body.mem) | set(body.lea)):
        if i in body.lea:
            out.append((("L",), body.lea[i]))
        m = body.mem.get(i)
        if m and m[4] and m[0] in AM.STORE_OPS:
            out.append((("S", m[0], m[2] == ZERO), m[3]))
    return out


def event_map(a, b):
    """[(disp_a, disp_b)] from aligning the two event sequences on their tokens alone, and the ratio."""
    import difflib
    ea, eb = events(a), events(b)
    sm = difflib.SequenceMatcher(None, [t for t, _ in ea], [t for t, _ in eb], autojunk=False)
    out = []
    for ia, ib, n in sm.get_matching_blocks():
        out += [(ea[ia + k][1], eb[ib + k][1]) for k in range(n)]
    total = len(ea) + len(eb)
    return out, (2.0 * len(out) / total if total else 0.0)


# --------------------------------------------------------------------------------------------------
# 4. the inputs, loaded once and only when a section asks
# --------------------------------------------------------------------------------------------------
from functools import cached_property  # noqa: E402

MANGLED_RE = re.compile(r"^(.*?)__(Q\d|\d+)")


def member_class(name):
    """The innermost class of a Metrowerks-mangled member function (`Tick__10CZSealBodyFf` ->
    `CZSealBody`), or None for a free function."""
    m = MANGLED_RE.match(name)
    if not m:
        return None
    rest, classes, pos = name[len(m.group(1)) + 2:], [], 0
    q = re.match(r"Q(\d)", rest)
    if q:
        pos = q.end()
        for _ in range(int(q.group(1))):
            k = re.match(r"(\d+)", rest[pos:])
            if not k:
                return None
            n = int(k.group(1))
            pos += k.end()
            classes.append(rest[pos:pos + n])
            pos += n
    else:
        k = re.match(r"(\d+)", rest)
        n = int(k.group(1))
        classes.append(rest[k.end():k.end() + n])
        pos = k.end() + n
    tail = rest[pos:]
    return classes[-1] if tail.startswith(("F", "CF")) else None


BODY_PASSES = ("exact", "hash+callees", "relinked-body")


class Ctx:
    @cached_property
    def dump(self):
        top, by_off = parse_dump(ccc_dump())
        return top, by_off

    @property
    def top(self):
        return self.dump[0]

    @property
    def by_off(self):
        return self.dump[1]

    @cached_property
    def types(self):
        return Types(self.by_off)

    @cached_property
    def classes(self):
        return distinct_classes(self.top, self.types)

    def layout(self, name):
        """The complete (byte_size > 0) layout of a class name, the one seen in the most units."""
        full = [(len(u), d) for d, u in self.classes.get(name, []) if int(d.attrs.get("byte_size", "0"), 16)]
        return max(full, key=lambda x: x[0])[1] if full else None

    @cached_property
    def units(self):
        """[(tu_head, [cu, ...])]: a pc-less compile unit opens a translation unit; the per-function
        CUs that follow belong to it. The assembler CU (crt0.s) stands alone."""
        out = []
        for cu in self.top:
            if "low_pc" not in cu.attrs or cu.attrs.get("language") == "ASSEMBLY" or not out:
                out.append((cu, []))
            else:
                out[-1][1].append(cu)
        return out

    @cached_property
    def pc_ranges(self):
        """sorted [(low, high, tu_name, cu_name, subprogram name)] for every per-function CU."""
        out = []
        for head, cus in self.units:
            for cu in cus:
                subs = [d for d in cu.children if d.tag in ("global_subroutine", "subroutine")]
                sub = subs[0] if subs else None
                out.append((int(cu.attrs["low_pc"], 16), int(cu.attrs["high_pc"], 16), head.name,
                            cu.name, sub.attrs.get("mangled_name", sub.name) if sub else None))
        return sorted(out)

    def unit_of(self, addr):
        r = self.pc_ranges
        i = bisect.bisect_right([x[0] for x in r], addr) - 1
        if i >= 0 and r[i][0] <= addr < r[i][1]:
            return r[i]
        return None

    @cached_property
    def demo(self):
        return read_elf(DEMO)

    @cached_property
    def dfuncs(self):
        return self.demo.functions

    @cached_property
    def dname(self):
        return {s: n for s, e, n in self.dfuncs}

    @cached_property
    def daddr(self):
        return {n: s for s, e, n in self.dfuncs}

    @cached_property
    def dB(self):
        return image_bodies(DEMO, self.dfuncs)

    @cached_property
    def r1B(self):
        return image_bodies(R1_ELF, csv_funcs(R1_CSV))

    @cached_property
    def r4B(self):
        return image_bodies(R4_ELF, csv_funcs(R4_CSV))

    @cached_property
    def pairs(self):
        """research/44's 987: [(demo start, r0001 start, how, name)]."""
        m = json.load(open(MATCHES))
        return [(self.daddr[p["name"]], int(p["addr"], 16), p["how"], p["name"])
                for p in m["pairs"] if p["name"] in self.daddr]

    @cached_property
    def truth(self):
        return {d: (r, h) for d, r, h, _ in self.pairs}

    @cached_property
    def r4match(self):
        m = json.load(open(R4_MATCH))["matches"]
        return {int(a, 16): int(v["b"], 16) for a, v in m.items() if v.get("b")}

    @cached_property
    def finder_r1(self):
        return TwinFinder(self.r1B)

    @cached_property
    def finder_demo(self):
        return TwinFinder(self.dB)

    @cached_property
    def finder_r4(self):
        return TwinFinder(self.r4B)

    def twin_r1(self, dstart):
        """(r0001 start, how, ratio, aligned pairs) for a demo function, or None: research/44's pair
        when there is one, else an accepted TwinFinder twin."""
        A = self.dB.get(dstart)
        if A is None:
            return None
        truth = self.truth
        if dstart in truth and truth[dstart][0] in self.r1B:
            r, how = truth[dstart]
            pairs, ratio = align(A, self.r1B[r])
            return r, how, ratio, pairs
        if len(A.tokens) < 16:
            return None
        r, ratio, margin, pairs = self.finder_r1.find(A)
        if r is None or not self.finder_r1.accept(ratio, margin):
            return None
        return r, "twin", ratio, pairs

    def twin_r4(self, r1start):
        """(r0004 start, how, pairs) for an r0001 function: match.json, else an accepted twin."""
        B = self.r1B.get(r1start)
        if B is None:
            return None
        if r1start in self.r4match and self.r4match[r1start] in self.r4B:
            b = self.r4match[r1start]
            return b, "match.json", align(B, self.r4B[b])[0]
        if len(B.tokens) < 16:
            return None
        b, ratio, margin, pairs = self.finder_r4.find(B)
        if b is None or not self.finder_r4.accept(ratio, margin):
            return None
        return b, "twin", pairs


def fmt(x):
    return "%#x" % x if isinstance(x, int) else str(x)


# --------------------------------------------------------------------------------------------------
# section: census
# --------------------------------------------------------------------------------------------------
SRC_EXT = (".cpp", ".c", ".h", ".s")


def section_census(ctx, selfcheck=False):
    print("== census: what the demo's .debug holds (ccc main, `symbols --section .debug dwarf`)")
    sec = ctx.demo.section(".debug")
    line = ctx.demo.section(".line")
    print(".debug %d bytes, .line %d bytes" % (sec.size, line.size if line else 0))
    tags = collections.Counter(d.tag for d in ctx.by_off.values())
    print("DIEs %d; by tag: %s" % (sum(tags.values()), ", ".join("%s %d" % kv for kv in tags.most_common())))
    if selfcheck:
        data = ctx.demo.data[sec.offset:sec.offset + sec.size]
        own, first = own_walk(data)
        diff = {k: (own[k], tags[k]) for k in set(own) | set(tags) if own[k] != tags[k]}
        print("selfcheck: own DWARF1 walker %d DIEs, first compile unit %r, differences from ccc: %s"
              % (sum(own.values()), first, diff or "none"))
    cus = ctx.top
    heads = [h for h, _ in ctx.units]
    fn_cus = [cu for _, c in ctx.units for cu in c]
    names = {cu.name for cu in cus}
    print("compile-unit DIEs %d = %d translation units (%d opened by a pc-less CU that holds the unit's "
          "types and data, plus the assembler's %s) + %d per-function CUs"
          % (len(cus), len(heads), sum(1 for h in heads if "low_pc" not in h.attrs),
             ", ".join(h.name for h in heads if h.attrs.get("language") == "ASSEMBLY"), len(fn_cus)))
    print("producers: %s" % dict(collections.Counter(cu.attrs.get("producer") for cu in cus)))
    print("distinct CU names %d, of which with a source extension (.cpp .c .h .s) %d"
          % (len(names), sum(1 for n in names if n.lower().endswith(SRC_EXT))))
    noext = sorted(n for n in names if not n.lower().endswith(SRC_EXT))
    print("names without a source extension %d: %s" % (len(noext), " ".join(n.rsplit(BS, 1)[-1] for n in noext)))
    own_name = sum(1 for h, c in ctx.units for cu in c if cu.name == h.name)
    print("per-function CUs named after their own unit %d, after a header or another file %d"
          % (own_name, len(fn_cus) - own_name))
    other = collections.Counter(cu.name for h, c in ctx.units for cu in c if cu.name != h.name)
    print("  the files those %d name, by count: %s"
          % (sum(other.values()), ", ".join("%s %d" % (n.rsplit(BS, 2)[-2] + BS + n.rsplit(BS, 1)[-1]
                                                        if n.count(BS) >= 2 else n, k)
                                           for n, k in other.most_common())))
    tu_dirs = collections.Counter(h.name.rsplit(BS, 1)[0] for h in heads)
    print("translation units by directory:")
    for d, n in tu_dirs.most_common():
        print("  %3d  %s" % (n, d))
    subs = [d for d in ctx.by_off.values() if d.tag in ("global_subroutine", "subroutine")]
    print("subprograms %d (global_subroutine %d, subroutine %d), with a pc range %d; per-function CUs with "
          "exactly one subprogram %d" % (len(subs), tags["global_subroutine"], tags["subroutine"],
                                         sum(1 for d in subs if "low_pc" in d.attrs),
                                         sum(1 for cu in fn_cus if sum(1 for d in cu.children
                                             if d.tag in ("global_subroutine", "subroutine")) == 1)))
    print("demo .symtab functions %d, of which the start of a subprogram DIE %d"
          % (len(ctx.dfuncs), len({s for s, _, _ in ctx.dfuncs} & {int(d.attrs["low_pc"], 16) for d in subs
                                                                    if "low_pc" in d.attrs})))
    print("class_type %d, structure_type %d (anonymous RTTI/vtable records, no members), members %d, "
          "inheritance %d, enumeration_type %d, typedef %d, array_type %d, subroutine_type %d"
          % (tags["class_type"], tags["structure_type"], tags["member"], tags["inheritance"],
             tags["enumeration_type"], tags["typedef"], tags["array_type"], tags["subroutine_type"]))
    print("locals %d, parameters %d, lexical blocks %d, global variables %d"
          % (tags["local_variable"], tags["formal_parameter"], tags["lexical_block"], tags["global_variable"]))
    unknown = collections.Counter(k for d in ctx.by_off.values() for k in d.attrs if k.startswith("unknown("))
    print("vendor (Metrowerks) attributes ccc prints as unknown: %s" % dict(unknown))


# --------------------------------------------------------------------------------------------------
# section: types
# --------------------------------------------------------------------------------------------------
HAND_NAMED = ("CZSealBody", "CEntity", "CBody", "CMission", "CPnt3D", "CQuat", "CMatrix", "CPacket",
              "CZNetwork", "CZNetGame", "CZOnlineLobby", "CNetCnf", "CZAnimMain", "CHUD", "CAiMap",
              "CSealCtrl", "CSealCtrlAi", "CZKit", "CGame", "COurGame", "CCamera", "CAppCamera")
NET_RE = re.compile(r"Chat|Lobby|GameList|Net|Medius|Msg|Packet", re.I)


def section_types(ctx, write=False):
    print("== types: class layouts")
    t, cl = ctx.types, ctx.classes
    layouts = [(n, d, u) for n, v in cl.items() for d, u in v]
    complete = [(n, d, u) for n, d, u in layouts if int(d.attrs.get("byte_size", "0"), 16) > 0]
    names_complete = {n for n, _, _ in complete}
    print("class_type DIEs %d -> distinct names %d, distinct layouts %d; complete (byte_size > 0) layouts %d "
          "under %d names; names only ever declared (size 0) %d; names with more than one complete layout %d"
          % (sum(1 for d in ctx.by_off.values() if d.tag == "class_type"), len(cl), len(layouts),
             len(complete), len(names_complete), len(set(cl) - names_complete),
             sum(1 for n in names_complete if sum(1 for m, _, _ in complete if m == n) > 1)))
    multi = sorted({n for n in names_complete if sum(1 for m, _, _ in complete if m == n) > 1})
    print("  the names with more than one complete layout (sizes): %s"
          % "; ".join("%s %s" % (n, ",".join(d.attrs["byte_size"] for m, d, _ in complete if m == n)) for n in multi))
    if write:
        with open(TYPES_OUT, "w") as f:
            f.write("# The SOCOM 1 demo's class layouts from its DWARF1 .debug (ccc raw dump; "
                    "tools_py/research/symbols/dwarf_types.py --write-types). Offsets are SOCOM 1's.\n")
            for n, d, u in sorted(complete, key=lambda x: (x[0] or "", x[1].off)):
                f.write("%s size=%s members=%d flat=%d bases=%s units=%d\n"
                        % (n, d.attrs["byte_size"], len(t.direct(d)), len(t.flat(d)),
                           ",".join("%s@%s" % (b.name if b else "?", fmt(o)) for o, b in t.bases(d)) or "-",
                           len(u)))
                for off, name, desc, size, bits in t.flat(d):
                    f.write("  %s %s %s%s\n" % (fmt(off), name, desc,
                                                " bits %d:%d" % bits if bits else ""))
        print("wrote %s: %d layouts" % (TYPES_OUT, len(complete)))
    print("the 40 largest by own member count (name, size, own members, flattened through bases, bases):")
    best = {}
    for n, d, u in complete:
        k = len(t.direct(d))
        if n not in best or k > best[n][0]:
            best[n] = (k, d)
    for n, (k, d) in sorted(best.items(), key=lambda x: -x[1][0])[:40]:
        print("  %-28s %8s %4d %4d  %s" % (n, d.attrs["byte_size"], k, len(t.flat(d)),
                                          ",".join(b.name for _, b in t.bases(d) if b) or "-"))
    print("classes the project names by hand, and every Chat/Lobby/GameList/Net/Medius/Msg/Packet name:")
    want = list(HAND_NAMED) + sorted(n for n in cl if n and NET_RE.search(n) and n not in HAND_NAMED)
    for n in want:
        d = ctx.layout(n)
        if d is None:
            print("  %-28s no layout in .debug%s" % (n, " (declared only)" if n in cl else ""))
        else:
            print("  %-28s %8s own %d flat %d" % (n, d.attrs["byte_size"], len(t.direct(d)), len(t.flat(d))))


# --------------------------------------------------------------------------------------------------
# section: units
# --------------------------------------------------------------------------------------------------
def section_units(ctx):
    print("== units: which translation unit research/44's matched demo functions came from")
    starts = [s for s, _, _ in ctx.dfuncs]
    cov = [ctx.unit_of(s) for s in starts]
    print("demo functions %d; inside a per-function CU's pc range %d" % (len(starts), sum(1 for c in cov if c)))
    lo = min(r[0] for r in ctx.pc_ranges)
    hi = max(r[1] for r in ctx.pc_ranges)
    print("pc ranges span %s-%s" % (fmt(lo), fmt(hi)))
    pairs = ctx.pairs
    got = [(d, r, h, n, ctx.unit_of(d)) for d, r, h, n in pairs]
    inside = [g for g in got if g[4]]
    print("matched pairs %d; with a compile unit %d; distinct units contributing %d"
          % (len(pairs), len(inside), len({g[4][2] for g in inside})))
    by_unit = collections.Counter(g[4][2] for g in inside)
    print("top 15 units by matched count (unit, matched, of which body-matched):")
    for u, n in by_unit.most_common(15):
        print("  %3d %3d  %s" % (n, sum(1 for g in inside if g[4][2] == u and g[2] in BODY_PASSES), u))
    hdr = sum(1 for g in inside if g[4][3] != g[4][2])
    print("of the matched-with-unit, whose own CU names a header (an inline emitted into that unit) %d" % hdr)
    # where the rest are: bracketed by two covered functions of one unit (link order), or outside
    idx = {s: i for i, s in enumerate(starts)}
    bracket = collections.Counter()
    for d, r, h, n, u in got:
        if u:
            continue
        i = idx[d]
        prev = next((cov[j] for j in range(i - 1, -1, -1) if cov[j]), None)
        nxt = next((cov[j] for j in range(i + 1, len(cov)) if cov[j]), None)
        if prev and nxt and prev[2] == nxt[2]:
            bracket["between two functions of one unit"] += 1
        elif lo <= d < hi:
            bracket["inside the covered span, between units"] += 1
        else:
            bracket["outside the covered span"] += 1
    print("matched pairs with no compile unit, by position: %s" % dict(bracket))
    # the class-name clustering against the units
    cls_units = collections.defaultdict(collections.Counter)
    for d, r, h, n, u in inside:
        c = member_class(n)
        if c:
            cls_units[c][u[2].rsplit(BS, 1)[-1]] += 1
    print("matched members with a unit, by class (class: unit counts):")
    for c, cnt in sorted(cls_units.items(), key=lambda x: -sum(x[1].values()))[:15]:
        print("  %-24s %s" % (c, dict(cnt)))


# --------------------------------------------------------------------------------------------------
# section: offsets
# --------------------------------------------------------------------------------------------------
ACTOR_CLASSES = ("CZSealBody", "CEntity", "CBody")
# (name, r0001 displacement, where the tools use it)
ACTOR_PROBES = (
    ("actor_pos (x of x,y,z)", 0x1C, "guest_addresses.PROBE_OFFSETS; verdict_core ACTOR_POS_WORDS"),
    ("ANGVEL_OFFSET", 0x48, "sp_death_probe"),
    ("QUAT_OFFSET", 0x70, "sp_death_probe"),
    ("MATRIX_OFFSET (row 0)", 0x80, "sp_death_probe"),
    ("matrix row 2 x", 0xA0, "sp_death_probe; online_match_ours"),
    ("matrix row 2 z", 0xA8, "sp_death_probe; online_match_ours"),
    ("team word", 0xC8, "verdict_replay"),
    ("turn axis / MoveScale triple", 0x23C, "sp_death_probe comment; guest_addresses comment"),
    ("root_node", 0x2E8, "guest_addresses.PROBE_OFFSETS"),
    ("R6 peek base (ground hit)", 0x400, "verdict_core"),
    ("ACTOR_STAMP_OFFSET", 0x420, "verdict_core"),
    ("alive word", 0xF78, "verdict_replay"),
    ("ALIVE_OFFSET (byte)", 0xF7A, "sp_death_probe; verdict_core ACTOR_ALIVE_OFFSET"),
    ("DEATH_TIME_OFFSET", 0xFB4, "sp_death_probe"),
    ("HEALTH_OFFSET", 0x1044, "sp_death_probe; online_match_ours"),
    ("r0004's inserted word", 0x1334, "guest_addresses comment (r0004)"),
    ("move_scale", 0x1368, "guest_addresses.PROBE_OFFSETS"),
)
# (class whose layout names the offsets, demo classes whose member functions are twinned with `this` on
#  that class, demo free functions twinned on any base register, [(label, r0001 displacement, where)])
GENERIC_ROWS = (
    ("CZNetGame", ("CZNetGame",), (), (
        ("valve mp_round_count", 0x0C, "verdict_core VALVES"),
        ("valve mp_game_over", 0x10, "verdict_core VALVES"),
        ("valve player_team", 0x14, "verdict_core VALVES"),
        ("valve mp_major_game_state", 0x20, "verdict_core VALVES"),
        ("valve mp_minor_game_state", 0x24, "verdict_core VALVES"),
        ("valve late_joiner", 0x2C, "verdict_core VALVES"),
        ("valve aiteam_00", 0x58, "verdict_core VALVES"),
        ("valve aiteam_08", 0x5C, "verdict_core VALVES"),
        ("valve total_mp_kills", 0x70, "verdict_core VALVES"),
        ("NG_LAG_FLAG_OFFSET (byte)", 0xDE, "verdict_core"),
        ("peek split", 0x100, "verdict_core"),
        ("NG_FINGERPRINT_WORD (50.0f)", 0x118, "verdict_core"))),
    ("CCamera", ("CCamera",), (), (
        ("camera LOD scale pair", 0x2C8, "game_overrides_socom2.cpp (cull/camcfg trace)"),
        ("camera LOD base scale", 0x2CC, "game_overrides_socom2.cpp (camcfg trace)"),
        ("camera 4x4", 0x330, "game_overrides_socom2.cpp (cull trace)"),
        ("camera plane mask", 0x564, "game_overrides_socom2.cpp (cull trace)"))),
    ("CNode", ("CNode",), (), (
        ("node flags", 0x5C, "game_overrides_socom2.cpp (node trace)"),
        ("node flags byte", 0x5D, "game_overrides_socom2.cpp (node trace)"),
        ("component presence", 0x88, "game_overrides_socom2.cpp (node trace)"),
        ("component data", 0x8C, "game_overrides_socom2.cpp (node trace)"),
        ("fade/scale float", 0x9C, "game_overrides_socom2.cpp (node trace)"))),
    ("_reent", (), ("rand", "srand"), (
        ("newlib _reent rand state", 0xA8, "game_overrides_socom2.cpp (loader)"),)),
)
RECORD_SHAPES = (
    ("chat record: name char[32] at 0x1c, type 0x3c, message char[64] at 0x40, 0x80 bytes",
     ((0x1C, r"char\[32\]"), (0x40, r"char\[64\]")), "socom2_chat.h"),
    ("OSK argument block: Purpose char[64] at 0x10, SkbName char[32] at 0x58, 0xAC bytes",
     ((0x10, r"char\[64\]"), (0x58, r"char\[32\]")), "socom2_osk_prefill.h"),
)
HOOK_FUNCS = (("chatFanoutRecv", 0x2F4EF0), ("chatListRender", 0x2F5020), ("oskOpen", 0x38D770),
              ("the lag-flag setter", 0x594CF0), ("MoveScale setter", 0x553DC0),
              ("MoveScale user", 0x551EC0), ("angvel writer", 0x550EF0), ("stamp writer", 0x5B0420))
NOTE_FIELDS = (0x4, 0x14, 0x94, 0xB0, 0xB4, 0xC0, 0xC4, 0xDC, 0xDD, 0x320, 0x32C, 0x33C, 0x340, 0x360,
               0x37C, 0xE54, 0xE58, 0xEA0, 0xEA4, 0xEA8, 0xFD4)
DEMO_CTOR, R1_CTOR = "__ct__10CZSealBodyFPQ23zdb5CNodeP14CCharacterType", 0x553EA0


def field_name(layout, x):
    """'Class::field' (or 'Class::field+0xN' inside it) at a flattened offset, or None."""
    best = None
    for off, name, desc, size, bits in layout:
        if off == x:
            return name, desc
        if off < x < off + (size or 0):
            best = ("%s+%#x" % (name, x - off), desc)
    return best if best else (None, None)


def actor_observations(ctx):
    """[(demo_flat_offset, r0001_flat_offset, source)] for the actor, from three sources: (1) every
    demo CZSealBody/CEntity/CBody member function with an r0001 twin, aligned instruction for
    instruction, `this`-relative on both sides; (2) the two constructors' store sequences aligned
    (events); (3) filled in by `reverse_probe` for each probe."""
    obs = []
    ctor_d = ctx.daddr[DEMO_CTOR]
    em, ratio = event_map(ctx.dB[ctor_d], ctx.r1B[R1_CTOR])
    # the CBody sub-object: the demo stores the secondary vtable at the CBody base; the majority r0001
    # displacement that store aligns with is r0001's CBody base
    t = ctx.types
    zs = ctx.layout("CZSealBody")
    demo_cbody = dict((b.name, o) for o, b in t.bases(zs) if b).get("CBody")
    r1_cbody = collections.Counter(y for x, y in em if x == demo_cbody).most_common(1)[0][0]
    base = {"CZSealBody": (0, 0), "CEntity": (0, 0), "CBody": (demo_cbody, r1_cbody)}
    for x, y in em:
        obs.append((x, y, "ctor"))
    n_twins = collections.Counter()
    for s, e, n in ctx.dfuncs:
        c = member_class(n)
        if c not in ACTOR_CLASSES or n == DEMO_CTOR:
            continue
        tw = ctx.twin_r1(s)
        if not tw:
            continue
        r, how, rr, pairs = tw
        n_twins[(c, "research/44" if how != "twin" else "twin")] += 1
        bd, br = base[c]
        for x, y, op, w in field_map(ctx.dB[s], ctx.r1B[r], pairs):
            obs.append((x + bd, y + br, "twin:" + n))
    return obs, ratio, len(em), base, n_twins


def reverse_probe(ctx, disp, classes):
    """For r0001 functions using `disp` on a `this`-aliased register: their demo twins, and the demo
    displacement at the aligned instruction when the twin is a member of one of `classes`."""
    users = [b for b in ctx.r1B.values() if any(m[3] == disp and m[4] for m in b.mem.values())]
    out = []
    for B in users[:600]:
        if len(B.tokens) < 16:
            continue
        a, ratio, margin, pairs = ctx.finder_demo.find(B)
        if a is None or not ctx.finder_demo.accept(ratio, margin):
            continue
        c = member_class(ctx.dname[a])
        if c not in classes:
            continue
        A = ctx.dB[a]
        for ib, ia in pairs:
            mb, ma = B.mem.get(ib), A.mem.get(ia)
            if mb and ma and mb[3] == disp and mb[4] and ma[4]:
                out.append((ma[3], disp, "reverse:" + ctx.dname[a], c))
    return len(users), out


def r4_evidence(ctx, disp, limit=400):
    """r0001 uses of `disp` on a `this`-aliased register, followed into r0004 through match.json (or an
    accepted twin for the functions it leaves unresolved): Counter of the r0004 displacement."""
    cnt, funcs = collections.Counter(), 0
    users = [b for b in ctx.r1B.values() if any(m[3] == disp and m[4] for m in b.mem.values())]
    for B in users[:limit]:
        tw = ctx.twin_r4(B.addr)
        if not tw:
            continue
        b, how, pairs = tw
        C = ctx.r4B[b]
        hit = False
        for ia, ib in pairs:
            ma, mb = B.mem.get(ia), C.mem.get(ib)
            if ma and mb and ma[3] == disp and ma[4]:
                cnt[mb[3]] += 1
                hit = True
        funcs += hit
    return len(users), funcs, cnt


def verdict(disp, cands, fns, block):
    """cands: Counter of SOCOM 1 offsets aligned with `disp`; fns: {offset: set of twin functions};
    block: (neighbours sharing the shift, neighbours seen). A shift is reported when two twin functions
    agree on it or most of the demo neighbours share it; one function alone is a candidate only."""
    if not cands:
        return "unknown (no aligned SOCOM 1 use)"
    x = cands.most_common(1)[0][0]
    shift = disp - x
    what = "confirmed, unchanged" if shift == 0 else "shifted by %+#x" % shift
    agree, total = block
    if len(fns.get(x, ())) >= 2 or (total >= 2 and agree * 2 >= total):
        return what
    return "single-twin candidate (%s; neighbours %d of %d agree)" % (what, agree, total)


# SOCOM II's own names for the CZNetGame valve slots, read back out of both images (research/19 F2's table;
# verdict_core.VALVES carries nine of them). ng+off -> valve name.
R1_VALVES = {0x00: "mp_max_rounds", 0x04: "mp_half_rounds", 0x08: "mp_max_round_time", 0x0C: "mp_round_count",
             0x10: "mp_game_over", 0x14: "player_team", 0x20: "mp_major_game_state",
             0x24: "mp_minor_game_state", 0x2C: "late_joiner", 0x44: "player_join_count",
             0x48: "player_ready_count", 0x58: "aiteam_00", 0x5C: "aiteam_08", 0x64: "mp_allow_respawn",
             0x68: "mp_spectator", 0x70: "total_mp_kills", 0x74: "seals_team_score", 0x78: "terrs_team_score"}


def _tokens(name):
    words = re.findall(r"[A-Z]?[a-z]+|[0-9]+|[A-Z]+(?![a-z])", name)
    return {w.lower().rstrip("s") if len(w) > 3 else w.lower() for w in words} - {"mp", "m", "p", "valve"}


def valve_name_check(ctx):
    """Each SOCOM II valve name against the demo's m_p*Valve fields: the demo field whose name words
    contain all of the SOCOM II name's words (fewest extra words wins), and the shift that implies."""
    t = ctx.types
    valves = [(o, n) for o, n, d, sz, b in t.flat(ctx.layout("CZNetGame")) if n.endswith("Valve")]
    print("CZNetGame valve slots by name (SOCOM II names read from the images, research/19 F2):")
    shifts = collections.Counter()
    for off, name in sorted(R1_VALVES.items()):
        want = _tokens(name)
        best = None
        for o, n in valves:
            have = _tokens(n.split("::")[-1][3:])
            if want <= have and (best is None or len(have) < len(best[2])):
                best = (o, n, have)
        if best:
            shifts[off - best[0]] += 1
            print("  r0001 %-5s %-20s <- demo %-5s %-40s %+#x" % (fmt(off), name, fmt(best[0]), best[1], off - best[0]))
        else:
            print("  r0001 %-5s %-20s <- no demo valve of that name (new in SOCOM II)" % (fmt(off), name))
    print("  shifts by name: %s" % ", ".join("%+#x x%d" % kv for kv in sorted(shifts.items())))


def generic_rows(ctx, cls, members, frees, rows):
    """The offsets table for one class other than the actor: forward twins of its demo member functions
    (`this` on both sides) and of named free functions (any matching base register), reverse twins for
    each displacement, r0004 through match.json."""
    t = ctx.types
    lay = ctx.layout(cls)
    flat = t.flat(lay)
    obs, listing = [], []
    for s, e, n in ctx.dfuncs:
        free = n in frees
        if not free and member_class(n) not in members:
            continue
        tw = ctx.twin_r1(s)
        if not tw and free and s in ctx.dB:
            # a body under the twin finder's floor: take the r0001 function whose relinked fingerprint
            # (address immediates and global displacements masked, field displacements kept) is the
            # same, when exactly one is
            fp = AM.relinked_fingerprint(struct.pack("<%dI" % len(ctx.dB[s].words), *ctx.dB[s].words))
            same = [b for b in ctx.r1B.values()
                    if len(b.words) == len(ctx.dB[s].words)
                    and AM.relinked_fingerprint(struct.pack("<%dI" % len(b.words), *b.words)) == fp]
            if len(same) == 1:
                tw = (same[0].addr, "relinked-fingerprint", 1.0, align(ctx.dB[s], same[0])[0])
            else:
                listing.append("    %s: %d instructions, under the twin finder's floor; r0001 bodies with its "
                               "relinked fingerprint: %d" % (n, len(ctx.dB[s].words), len(same)))
        if not tw:
            continue
        r, how, rr, pairs = tw
        fm = [(x, y) for x, y, op, w in field_map(ctx.dB[s], ctx.r1B[r], pairs, this_only=not free)]
        obs += [(x, y, n) for x, y in fm]
        listing.append("    %s -> r0001 %s (%s, ratio %.2f): %s"
                       % (n, fmt(r), how, rr, " ".join("%s>%s" % (fmt(x), fmt(y)) for x, y in sorted(set(fm)))))
    by_x = collections.defaultdict(collections.Counter)
    for x, y, n in obs:
        by_x[x][y] += 1
    majority = {x: c.most_common(1)[0][0] for x, c in by_x.items()}
    print("%s: demo size %s, %d fields flattened; twinned functions %d, aligned uses %d; most common shifts %s"
          % (cls, lay.attrs["byte_size"], len(flat), len({n for _, _, n in obs}), len(obs),
             ", ".join("%+#x x%d" % kv for kv in collections.Counter(y - x for x, y, _ in obs).most_common(5))))
    print("  the twinned functions and their aligned displacements (demo>r0001):")
    for line in listing:
        print(line)
    for label, disp, where in rows:
        naive = deep_name(t, lay, disp)
        cands = collections.Counter(x for x, y, _ in obs if y == disp)
        fns = collections.defaultdict(set)
        for x, y, n in obs:
            if y == disp:
                fns[x].add(n)
        users, rev = reverse_probe(ctx, disp, members) if members else (0, [])
        for x, y, src, c in rev:
            cands[x] += 1
            fns[x].add(src.split(":", 1)[-1])
        if cands:
            x0 = cands.most_common(1)[0][0]
            near = [k for k in majority if k != x0 and abs(k - x0) <= 0x20]
            blk = (sum(1 for k in near if majority[k] - k == disp - x0), len(near))
        else:
            x0, blk = None, (0, 0)
        n4, f4, c4 = r4_evidence(ctx, disp)
        print("  %-30s r0001 %-6s | same offset in the demo: %s | aligned: %s | r0004: %d unchanged, %d moved "
              "(%d fns) | %s"
              % (label, fmt(disp), naive,
                 ", ".join("%s @%s %d/%d" % (deep_name(t, lay, x), fmt(x), v, len(fns[x]))
                           for x, v in cands.most_common(3)) or "-",
                 c4[disp], sum(c4.values()) - c4[disp], f4, verdict(disp, cands, fns, blk)))
        if disp in majority:
            print("      the demo field at %s is at %s in r0001 (%d uses)"
                  % (fmt(disp), fmt(majority[disp]), sum(by_x[disp].values())))


def section_offsets(ctx):
    print("== offsets: the raw field offsets the parity tools and hooks use, against the demo's types")
    t = ctx.types
    zs = ctx.layout("CZSealBody")
    flat = t.flat(zs)
    obs, ctor_ratio, ctor_n, base, n_twins = actor_observations(ctx)
    print("actor = CZSealBody (r0001 vtable 0x6691a0, research/44 addendum 2): demo size %s, %d fields "
          "flattened through %s" % (zs.attrs["byte_size"], len(flat),
                                    ", ".join("%s@%s" % (b.name, fmt(o)) for o, b in t.bases(zs) if b)))
    print("constructor events aligned (demo %s vs r0001 %s): %d pairs, ratio %.3f; CBody base demo %s -> "
          "r0001 %s" % (DEMO_CTOR, fmt(R1_CTOR), ctor_n, ctor_ratio, fmt(base["CBody"][0]), fmt(base["CBody"][1])))
    print("actor member twins: %s" % dict(n_twins))
    by_x = collections.defaultdict(collections.Counter)
    for x, y, src in obs:
        by_x[x][y] += 1
    majority = {x: c.most_common(1)[0][0] for x, c in by_x.items()}

    def block(x, disp):
        near = [k for k in majority if k != x and abs(k - x) <= 0x20]
        return sum(1 for k in near if majority[k] - k == disp - x), len(near)

    print("%-30s %-7s %-34s %-40s %-24s %s" % ("probe", "r0001", "demo field at the same offset",
                                                 "SOCOM 1 field that aligns with it", "r0004", "verdict"))
    def fn_of(src):
        return src.split(":", 1)[-1]

    for label, disp, where in ACTOR_PROBES:
        naive, ndesc = deep_name(t, zs, disp), ""
        cands = collections.Counter(x for x, y, src in obs if y == disp)
        fns = collections.defaultdict(set)
        for x, y, src in obs:
            if y == disp:
                fns[x].add(fn_of(src))
        users, rev = reverse_probe(ctx, disp, ACTOR_CLASSES)
        for x, y, src, c in rev:
            cands[x] += 1
            fns[x].add(fn_of(src))
        srcs = collections.Counter(src.split(":")[0] for x, y, src in obs if y == disp)
        srcs.update("reverse" for _ in rev)
        if cands:
            x = cands.most_common(1)[0][0]
            name, desc = deep_name(t, zs, x), field_name(flat, x)[1]
            cand = "%s %s @%s (%s)" % (name, desc, fmt(x), ", ".join("%s %d" % kv for kv in srcs.items()))
            blk = block(x, disp)
        else:
            cand, blk = "-", (0, 0)
        n4, f4, c4 = r4_evidence(ctx, disp)
        r4 = ", ".join("%s x%d" % (fmt(k), v) for k, v in c4.most_common(3)) or "-"
        print("%-30s %-7s %-34s %-40s %-24s %s" % (label, fmt(disp), "%s %s" % (naive, ndesc or ""), cand,
                                                     "%s (%d fns)" % (r4, f4), verdict(disp, cands, fns, blk)))
        print("    used in r0001 by %d functions on a this-register; r0004: %d uses unchanged, %d moved; demo "
              "neighbours within 0x20 sharing the shift: %d of %d; aligned candidates (uses / twin functions): %s"
              % (users, c4[disp], sum(c4.values()) - c4[disp], blk[0], blk[1],
                 ", ".join("%s %d/%d [%s]" % (fmt(k), v, len(fns[k]), " ".join(sorted(fns[k])))
                           for k, v in cands.most_common(6)) or "-"))
        if disp in majority:
            print("    the demo field AT %s (%s) is at %s in r0001 (%d uses)"
                  % (fmt(disp), naive, fmt(majority[disp]), sum(by_x[disp].values())))
        near = sorted((majority[x], x) for x in majority if abs(majority[x] - disp) <= 0x10 and x != disp)
        print("    r0001 neighbourhood named by the map: %s"
              % (", ".join("%s=%s(demo %s) x%d" % (fmt(y), field_name(flat, x)[0], fmt(x), by_x[x][y])
                           for y, x in near) or "-"))
    print("the actor's shift map, as runs of one shift over the demo offsets (majority per offset, "
          "offsets seen at least twice):")
    runs, cur = [], None
    for x in sorted(k for k in majority if sum(by_x[k].values()) >= 2):
        s = majority[x] - x
        if cur and cur[2] == s:
            cur[1] = x
            cur[3] += 1
        else:
            cur = [x, x, s, 1]
            runs.append(cur)
    for a, b, s, n in runs:
        if n >= 2:
            print("  demo %s-%s -> %+#x (%d offsets): %s .. %s" % (fmt(a), fmt(b), s, n,
                                                                   field_name(flat, a)[0], field_name(flat, b)[0]))
    print("the constructor's runs: consecutive aligned stores with one shift, 3 or more (in store order; the "
          "CBody base computation the constructor repeats between member inits is skipped):")
    ctor = [(x, y) for x, y, src in obs if src == "ctor" and x != base["CBody"][0]]
    i = 0
    while i < len(ctor):
        j = i
        while j + 1 < len(ctor) and ctor[j + 1][1] - ctor[j + 1][0] == ctor[i][1] - ctor[i][0]:
            j += 1
        if j - i + 1 >= 3:
            print("  %2d stores %+#x: demo %s (%s) .. %s (%s) -> r0001 %s .. %s"
                  % (j - i + 1, ctor[i][1] - ctor[i][0], fmt(ctor[i][0]), field_name(flat, ctor[i][0])[0],
                     fmt(ctor[j][0]), field_name(flat, ctor[j][0])[0], fmt(ctor[i][1]), fmt(ctor[j][1])))
        i = j + 1
    print("demo fields this note cites, and where the map puts them in r0001 (all observations):")
    for x in NOTE_FIELDS:
        seen = by_x.get(x)
        print("  demo %-6s %-44s -> %s" % (fmt(x), deep_name(t, zs, x),
                                             ", ".join("%s x%d" % (fmt(y), v) for y, v in seen.most_common())
                                             if seen else "not seen"))
    for cls, members, frees, rows in GENERIC_ROWS:
        generic_rows(ctx, cls, members, frees, rows)
        if cls == "CZNetGame":
            valve_name_check(ctx)
    # record shapes
    for label, shape, where in RECORD_SHAPES:
        hits = []
        for n, v in ctx.classes.items():
            for d, u in v:
                if not int(d.attrs.get("byte_size", "0"), 16):
                    continue
                f = t.flat(d)
                if all(any(r[0] == off and re.search(p, r[2]) for r in f) for off, p in shape):
                    hits.append(n)
        print("%s (%s): demo layouts with that shape: %s" % (label, where, hits or "none"))
    print("the hook and probe functions, reverse-searched for a demo twin:")
    for label, a in HOOK_FUNCS:
        B = ctx.r1B.get(a)
        got, ratio, margin, _ = ctx.finder_demo.find(B)
        print("  %-22s %s: best %s %s ratio %.2f margin %.2f -> %s"
              % (label, fmt(a), fmt(got), ctx.dname.get(got), ratio, margin,
                 "accepted" if ctx.finder_demo.accept(ratio, margin) else "no twin"))


# --------------------------------------------------------------------------------------------------
# section: age
# --------------------------------------------------------------------------------------------------
def section_age(ctx):
    print("== age: how much of a SOCOM 1 layout survives into SOCOM II")
    # the twin finder's false-pair rate, against research/44's pairs as truth
    res = collections.Counter()
    for d, r, how, n in ctx.pairs:
        A = ctx.dB.get(d)
        if A is None or r not in ctx.r1B or len(A.tokens) < 16:
            continue
        got, ratio, margin, _ = ctx.finder_r1.find(A)
        if ctx.finder_r1.accept(ratio, margin):
            res[("edited" if how.startswith("prefix") else "body", got == r)] += 1
    for kind in ("body", "edited"):
        ok, bad = res[(kind, True)], res[(kind, False)]
        print("twin finder holdout (%s pairs, >= 16 instructions): accepted %d, right %d, wrong %d"
              % ("body-matched" if kind == "body" else "prefix", ok + bad, ok, bad))
    body_cnt = collections.Counter(member_class(n) for d, r, h, n in ctx.pairs if h in BODY_PASSES)
    classes = sorted(c for c, k in body_cnt.items() if c and k >= 3 and ctx.layout(c) is not None)
    print("classes with a demo layout and >= 3 body-matched members: %d: %s" % (len(classes), " ".join(classes)))
    print("per class: body-matched members and the distinct demo fields they use (unchanged by construction) |"
          " edited members twinned (prefix pairs + twin finder), the distinct demo fields they use, how many "
          "sit at the same offset in r0001 and how many moved (majority per field) | control: the same "
          "alignment r0001 -> r0004 on the same r0001 functions, fields unchanged / moved")
    tot = collections.Counter()
    for c in classes:
        offs = {o for o, *_ in ctx.types.flat(ctx.layout(c))}
        body_fields = set()
        edited = collections.defaultdict(collections.Counter)
        control = collections.defaultdict(collections.Counter)
        n_body = n_edit = 0
        for s_, e_, n in ctx.dfuncs:
            if member_class(n) != c:
                continue
            tw = ctx.twin_r1(s_)
            if not tw:
                continue
            r, how, ratio, pairs = tw
            fm = [(x, y) for x, y, op, w in field_map(ctx.dB[s_], ctx.r1B[r], pairs) if x in offs]
            if how in BODY_PASSES:
                n_body += 1
                body_fields.update(x for x, y in fm)
            else:
                n_edit += 1
                for x, y in fm:
                    edited[x][y] += 1
            t4 = ctx.twin_r4(r)
            if t4:
                b, _, p4 = t4
                B, C = ctx.r1B[r], ctx.r4B[b]
                for x, y, op, w in field_map(B, C, p4):
                    control[x][y] += 1
        unch = sum(1 for x, cn in edited.items() if cn.most_common(1)[0][0] == x)
        cun = sum(1 for x, cn in control.items() if cn.most_common(1)[0][0] == x)
        tot.update(body=len(body_fields), fields=len(edited), unchanged=unch, shifted=len(edited) - unch,
                   cfields=len(control), cunchanged=cun)
        print("  %-16s %7s | %2d body, %3d fields | %3d edited, %3d fields, %3d same, %3d moved | control %3d / %d"
              % (c, ctx.layout(c).attrs["byte_size"], n_body, len(body_fields), n_edit, len(edited), unch,
                 len(edited) - unch, cun, len(control) - cun))
    print("total: body-matched fields %d (unchanged by construction); through edited twins %d fields: same "
          "offset %d, moved %d; control r0001 -> r0004: %d fields, same %d, moved %d"
          % (tot["body"], tot["fields"], tot["unchanged"], tot["shifted"], tot["cfields"], tot["cunchanged"],
             tot["cfields"] - tot["cunchanged"]))
    obs, ratio, n, base, _ = actor_observations(ctx)
    ctor = [(x, y) for x, y, s in obs if s == "ctor"]
    zs_offs = {o for o, *_ in ctx.types.flat(ctx.layout("CZSealBody"))}
    distinct = {}
    for x, y in ctor:
        if x in zs_offs:
            distinct.setdefault(x, collections.Counter())[y] += 1
    unch = sum(1 for x, cn in distinct.items() if cn.most_common(1)[0][0] == x)
    print("CZSealBody through its constructor (%d aligned stores): demo fields %d, unchanged %d, shifted %d"
          % (len(ctor), len(distinct), unch, len(distinct) - unch))


# --------------------------------------------------------------------------------------------------
# section: missing
# --------------------------------------------------------------------------------------------------
def section_missing(ctx):
    print("== missing: what the .debug does not cover")
    per_tu = []
    for head, cus in ctx.units:
        per_tu.append((head.name, sum(1 for d in head.children if d.tag == "class_type"),
                       sum(1 for d in head.children if d.tag == "enumeration_type"), len(cus)))
    lpc = [p for p in per_tu if "libpttclient" in p[0] and p[0].lower().endswith(".c")]
    print("LPC-10 units (libpttclient *.c): %d; class types %d, enums %d, functions %d"
          % (len(lpc), sum(p[1] for p in lpc), sum(p[2] for p in lpc), sum(p[3] for p in lpc)))
    lpc_names = {d.name for head, cus in ctx.units if "libpttclient" in head.name and head.name.lower().endswith(".c")
                 for d in head.children if d.tag == "class_type"}
    print("  distinct LPC-10 type names %d: %s" % (len(lpc_names), " ".join(sorted(n for n in lpc_names if n))[:400]))
    rest = [p for p in per_tu if p not in lpc]
    print("other units: %d; with no class type of their own %d: %s"
          % (len(rest), sum(1 for p in rest if p[1] == 0), [p[0].rsplit(BS, 1)[-1] for p in rest if p[1] == 0]))
    methods = collections.Counter(member_class(n) for s, e, n in ctx.dfuncs)
    methods.pop(None, None)
    # a qualifier that never has a layout and names only namespaces' free functions: std, ai, the
    # anonymous namespaces; the DWARF names a template instance by its bare name, so look that up
    for ns in [c for c in methods if c == "std" or c == "ai" or c.startswith("@unnamed@")]:
        methods.pop(ns)
    bare = lambda c: c.split("<", 1)[0]  # noqa: E731
    have = {n for n in methods if ctx.layout(bare(n)) is not None}
    exact = {n for n in methods if "<" not in n and ctx.layout(n) is not None}
    print("classes with member functions in .symtab %d (std, ai and anonymous namespaces left out): with a "
          "complete layout under the same name %d, template instances whose bare name has a layout %d, "
          "without a layout %d (of which templates %d)"
          % (len(methods), len(exact), len(have) - len(exact), len(methods) - len(have),
             sum(1 for n in methods if n not in have and "<" in n)))
    print("the 25 largest without a layout (class, methods, name as a string in the demo file):")
    data = ctx.demo.data
    for c, k in [(c, k) for c, k in methods.most_common() if c not in have][:25]:
        print("  %-28s %4d %s" % (c, k, "string" if c.encode() in data else "-"))
    for c in ("CZOnlineLobby", "CNetCnf", "CPacket", "CZNetwork", "CZNetGame"):
        print("  %-28s methods %4d layout %s" % (c, methods.get(c, 0),
                                                 ctx.layout(c).attrs["byte_size"] if ctx.layout(c) else "none"))


SECTIONS = {"census": section_census, "types": section_types, "units": section_units,
            "offsets": section_offsets, "age": section_age, "missing": section_missing}


def main(argv):
    flags = {a for a in argv if a.startswith("--")}
    wanted = [a for a in argv if not a.startswith("--")] or list(SECTIONS)
    ctx = Ctx()
    for name in wanted:
        if name == "census":
            section_census(ctx, "--selfcheck" in flags)
        elif name == "types":
            section_types(ctx, "--write-types" in flags)
        else:
            SECTIONS[name](ctx)
        print()


if __name__ == "__main__":
    main(sys.argv[1:])
