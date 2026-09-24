"""The demo's class inventory as an architecture map, and what the runtime's hooks touch (Sprint 12
research wave, question 10; docs/research/55-class-inventory.md).

Run from the repo root:  python tools_py/research/symbols/class_inventory.py

Read-only. It writes ONE git-ignored file, game/class_inventory.csv (names, addresses and counts only;
no game bytes), and prints, in this order:

  [1] the class census: demo FUNC names, members vs free functions, the class count by the class-path
      components (and readable_names.py's rsplit count beside it: the README quotes 1,212, the script
      prints 1,210 on today's inputs), and
      the top 40 classes by method count with known / placed (by pass) / proposed / unplaced;
  [2] the subsystem table: classes grouped by name-prefix convention, free functions by family, with
      methods / placed / proposed; then the .debug view: a CU-level DWARF1 walk (tag, AT_name,
      AT_low_pc/AT_high_pc only -- NOT the types walk Goal 5 owns) giving the compile units per source
      directory, the demo functions inside a CU's pc range, and, per directory, the classes whose name
      occurs inside that directory's CUs (debug_paths.py's string method, attributed to the enclosing CU);
      Also: the demo's __vt__ classes resolved in r0001 by the bare vs the qualified ("zdb::CNode") name,
      and how many located vtables sit on a csv FUN_ row;
  [2b] the UI script-binding table in both images (rows [id, command string, handler]): how many demo
      handlers are named UI<command>, how many r0001 commands the demo table also carries (a demo name
      for that r0001 handler by command string), agreement with Task 7 on the same addresses, and the
      network/lobby commands;
  [3] the hook targets: every function field of socom2_addresses.h (r0001 column), every address a
      replaceFunction call site in game_overrides_socom2.cpp reaches, the two bindAddressHandler
      targets, and tools_py/parity/guest_addresses.py's probe addresses, each with the Task 7 pair or
      proposal on it (else 'unnamed'), the Task 7b positional lead in its gap, the retail vtable slot it
      fills (RTTI chain; for CZSealBody also the functions that build its vtable pointer), the binding
      command that dispatches to it, the Task 7 anchors either side of it and the demo functions between
      their twins, our csv / toml name, and which research notes mention the address;
  [4] the online-and-voice classes: methods known / placed / proposed / unplaced, positional leads,
      vtable resolution;
  [5] the gap map: classes with >= 10 methods and 0 placed, with whether the class-name string exists
      in the demo and in r0001 (vtable_rtti.py's resolve), and the RTTI/vtable outcome.

Inputs (all git-ignored except the csv, the toml, the runtime sources and the notes):
game/demo_scus_972_05/SCUS_972.05, game/disc/socom2_game.elf, recomp/socom2_ghidra.csv,
recomp/socom2.toml, game/demo_symbol_matches.json, game/demo_symbol_renames.csv,
game/demo_symbol_renames_7b.csv, third_party/ps2recomp/ps2xRuntime/{include/runtime/socom2_addresses.h,
include/runtime/socom2_osk_prefill.h, include/runtime/socom2_chat.h, src/lib/game_overrides_socom2.cpp},
tools_py/parity/guest_addresses.py, docs/research/*.md. About 30-35 s (it re-runs Task 7's matcher once, with
--prefix, to get the demo address of each of the 987 pairs, and checks the result equals the json).
"""
import bisect
import collections
import csv
import glob
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py import address_matcher as am  # noqa: E402
from tools_py import ghidra_symbol_match as gsm  # noqa: E402
from tools_py import symbol_levers as sl  # noqa: E402
from tools_py.elf_symbols import read_elf  # noqa: E402
from tools_py.parity import guest_addresses as ga  # noqa: E402

sys.path.insert(0, os.path.join(os.getcwd(), "tools_py", "research", "symbols"))
from readable_names import readable as _readable  # noqa: E402  (the README's helper, imported, not copied)

DEMO = "game/demo_scus_972_05/SCUS_972.05"
OURS_ELF = "game/disc/socom2_game.elf"
OURS_CSV = "recomp/socom2_ghidra.csv"
TOML = "recomp/socom2.toml"
MATCHES = "game/demo_symbol_matches.json"
RENAMES = "game/demo_symbol_renames.csv"
RENAMES_7B = "game/demo_symbol_renames_7b.csv"
RT = "third_party/ps2recomp/ps2xRuntime/"
ADDR_H = RT + "include/runtime/socom2_addresses.h"
OSK_H = RT + "include/runtime/socom2_osk_prefill.h"
CHAT_H = RT + "include/runtime/socom2_chat.h"
OVERRIDES = RT + "src/lib/game_overrides_socom2.cpp"
OUT_CSV = "game/class_inventory.csv"
BS = chr(92)
PASSES = ("exact", "hash+callees", "relinked-body", "prefix", "prefix+size")


# ---- names ---------------------------------------------------------------------------------------

_SPLIT = re.compile(r"^(.*?)__(?:Q\d|\d+)")


def class_path(mangled):
    """The class path components of a Metrowerks member name, or None for a free function.
    'GetNodePos__10CZSealBodyF...' -> ('CZSealBody',); 'Foo__Q23zdb5CNodeF' -> ('zdb', 'CNode')."""
    m = _SPLIT.match(mangled)
    if not m:
        return None
    rest = mangled[len(m.group(1)) + 2:]
    q = re.match(r"Q(\d)", rest)
    count, pos = (int(q.group(1)), q.end()) if q else (1, 0)
    comps = []
    for _ in range(count):
        n = re.match(r"(\d+)", rest[pos:])
        if not n:
            break
        length = int(n.group(1))
        pos += n.end()
        comp = rest[pos:pos + length]
        if len(comp) != length:
            return None
        comps.append(comp)
        pos += length
    return tuple(comps) or None


def readme_class(mangled):
    """readable_names.py's own class key (rsplit of the readable name), for the 1,212 reconciliation."""
    return _readable(mangled).rsplit("_", 1)[0]


def class_subsystem(path):
    head = path[0]
    if head.startswith("CZOnline"):
        return "CZOnline*"
    if head.startswith("CZNet"):
        return "CZNet*"
    if head.startswith("CZ"):
        return "CZ* (other)"
    if head.startswith("CSeal"):
        return "CSeal*"
    if head.startswith("CAi"):
        return "CAi*"
    if head.startswith("C2D"):
        return "C2D*"
    if head.startswith("CUI"):
        return "CUI*"
    if head.startswith(("CNet", "CHNet")):
        return "CNet*"
    if head in ("std", "Metrowerks") or head.startswith(("__", "basic_", "ios", "locale")):
        return "std/Metrowerks (MSL)"
    if re.match(r"C[A-Z0-9]", head):
        return "C* (other)"
    if head.startswith("z"):
        return "z* namespaces"
    return "other classes/namespaces"


def free_family(name, directory):
    if directory and "libpttclient" in directory:
        return "libpttclient (LPC-10 + PTT)"
    if name.startswith(("PTT_", "PTTServer_", "lpc10")):
        return "libpttclient (LPC-10 + PTT)"
    if name.startswith("rt_"):
        return "rt_* (free)"
    if "Medius" in name or name.startswith("cb"):
        return "Medius* client API + cb* callbacks (free)"
    if "DME" in name or "Dme" in name:
        return "DME* (free)"
    if name.startswith("sce") or name.startswith("_sce"):
        return "sce* (free)"
    if "Sase" in name:
        return "Sase* (free)"
    if name.startswith("hud"):
        return "hud* (free)"
    if re.match(r"z[A-Z]", name):
        return "z* (free)"
    if re.match(r"UI[A-Z]", name):
        return "UI* script bindings (free)"
    return "other free (libc, MSL, SDK, statics)"


# ---- images --------------------------------------------------------------------------------------

def find_all(segs, needle):
    out = []
    for va, data in segs:
        i = data.find(needle)
        while i >= 0:
            out.append(va + i)
            i = data.find(needle, i + 1)
    return out


def words_pointing(segs, target):
    return [a for a in find_all(segs, struct.pack("<I", target)) if a % 4 == 0]


def make_reader(segs):
    def rd(addr, n):
        for va, data in segs:
            if va <= addr and addr + n <= va + len(data):
                return data[addr - va:addr - va + n]
        return None
    return rd


def slots(rd, vt, fnset):
    out = []
    while True:
        b = rd(vt + 8 + len(out) * 4, 4)
        if not b or struct.unpack("<I", b)[0] not in fnset:
            return out
        out.append(struct.unpack("<I", b)[0])


def real_vtables(rd, vts, fnset):
    """The candidates that ARE vtables: at least one function start follows the two-word header. resolve()'s
    second hop also finds derived classes' RTTI objects (their base lists point at this RTTI), which
    vtable_rtti.py counts in its 'several' bucket; those have no function start at +8. Word 1 is not tested:
    it is 0 in a primary vtable and the this-adjustment in a secondary-base one (CZSealBody's 0x669210)."""
    return [v for v in vts if slots(rd, v, fnset)]


def binding_table(segs, names, probe):
    """[(row, string, function)] for the UI script-binding table that holds the row naming `probe` (a command
    string such as "NetCnfOpen"): rows are [id, string pointer, function pointer(, 0)], stride 12 in the demo
    and 16 in r0001 (research/11 sec 2a found the r0001 table at 0x3dd4d4). Walked both ways from the probe
    while the string word is a printable C string and the function word is a function start."""
    rd = make_reader(segs)

    def cstr(a):
        out = b""
        for i in range(64):
            b = rd(a + i, 1)
            if not b:
                return None
            if b == b"\x00":
                return out.decode("latin1") if out and all(32 < c < 127 for c in out) else None
            out += b
        return None

    def row(a):
        sp, fp = rd(a + 4, 4), rd(a + 8, 4)
        if not sp or not fp:
            return None
        st, fn = cstr(struct.unpack("<I", sp)[0]), struct.unpack("<I", fp)[0]
        return (a, st, fn) if st is not None and fn in names else None

    best = []
    for hit in find_all(segs, b"\x00" + probe.encode() + b"\x00"):
        for ptr in words_pointing(segs, hit + 1):
            for stride in (12, 16):
                a = ptr - 4
                while row(a - stride):
                    a -= stride
                rows = []
                while row(a):
                    rows.append(row(a))
                    a += stride
                if len(rows) > len(best):
                    best = rows
    return best


def forms_address(rd, start, end, target):
    """True when the body builds `target` with a lui/addiu (or lui/ori) pair on one register -- the way a
    constructor or destructor stores its class's vtable pointer (the README's 7c caveat on constructors)."""
    hi = {}
    for a in range(start, end, 4):
        w = rd(a, 4)
        if not w:
            return False
        ins = struct.unpack("<I", w)[0]
        op, rs, rt, imm = ins >> 26, (ins >> 21) & 31, (ins >> 16) & 31, ins & 0xFFFF
        if op == 0x0F:
            hi[rt] = imm << 16
        elif op in (0x09, 0x0D) and rs in hi:
            lo = imm - 0x10000 if (op == 0x09 and imm & 0x8000) else imm
            if ((hi[rs] + lo) if op == 0x09 else (hi[rs] | imm)) & 0xFFFFFFFF == target:
                return True
    return False


def resolve(segs, name):
    """vtable_rtti.py's chain: "\\0Name\\0" -> words pointing at it (RTTI) -> words pointing at those."""
    hits = find_all(segs, b"\x00" + name.encode() + b"\x00")
    rtti = [w for h in hits for w in words_pointing(segs, h + 1)]
    vts = [w for r in rtti for w in words_pointing(segs, r)]
    return hits, rtti, vts


# ---- the demo's .debug, compile-unit level only ---------------------------------------------------

def cu_walk(data, elf):
    """[(die_offset, name, low_pc, high_pc)] for every TAG_compile_unit (0x11) DIE, plus the section bytes.
    DWARF1: each DIE is u32 length, u16 tag, attributes (u16 name|form); a length < 8 is padding."""
    dbg = next(s for s in elf.sections if s.name == ".debug")
    d = data[dbg.offset:dbg.offset + dbg.size]
    out, pos = [], 0
    while pos + 4 <= len(d):
        length = struct.unpack_from("<I", d, pos)[0]
        if length < 8:
            pos += max(length, 4)
            continue
        if struct.unpack_from("<H", d, pos + 4)[0] == 0x11:
            attrs, p, end = {}, pos + 6, pos + length
            while p + 2 <= end:
                a = struct.unpack_from("<H", d, p)[0]
                p += 2
                form = a & 0xF
                if form in (1, 2, 6):
                    attrs[a] = struct.unpack_from("<I", d, p)[0]
                    p += 4
                elif form == 5:
                    p += 2
                elif form == 7:
                    p += 8
                elif form == 3:
                    p += 2 + struct.unpack_from("<H", d, p)[0]
                elif form == 4:
                    p += 4 + struct.unpack_from("<I", d, p)[0]
                elif form == 8:
                    e = d.index(b"\x00", p)
                    attrs[a] = d[p:e].decode("latin1")
                    p = e + 1
                else:
                    break
            out.append((pos, attrs.get(0x38), attrs.get(0x111), attrs.get(0x121)))
        pos += length
    return out, d, pos == len(d)


def directory_of(path):
    return path.rsplit(BS, 1)[0] if path and BS in path else (path or "?")


def short_dir(directory):
    if "Apps" + BS + "FTS" in directory:
        return "FTS"
    if "gamez" in directory:
        return "gamez" + BS + directory.rsplit(BS, 1)[1]
    if "libpttclient" in directory:
        return "libpttclient"
    if "libpttserver" in directory:
        return "libpttserver"
    if "Msl" in directory or "cw301" in directory or "CodeWarrior" in directory:
        return "MSL/CodeWarrior"
    if "sce" in directory:
        return "sce SDK"
    return directory


# ---- hooks ---------------------------------------------------------------------------------------

def table_r0001():
    """[(field, address, is_data)] from socom2_addresses.h's kR0001 initialiser, in struct order."""
    text = open(ADDR_H).read()
    struct_body = text[text.index("struct Table"):text.index("inline constexpr Table kR0001")]
    fields, data_fields = [], set()
    for line in struct_body.splitlines():
        m = re.match(r"\s*uint32_t (\w+);(.*)", line)
        if m:
            fields.append(m.group(1))
            if "DATA" in m.group(2) or m.group(1).startswith("ctorTable"):
                data_fields.add(m.group(1))
    consts = {}
    for path in (OSK_H, CHAT_H):
        for name, val in re.findall(r"constexpr uint32_t (k\w+Addr) = (0x[0-9a-fA-F]+)u", open(path).read()):
            consts[name] = int(val, 16)
    body = text[text.index("inline constexpr Table kR0001"):text.index("inline constexpr Table kR0004")]
    values = []
    for line in body.splitlines()[2:]:
        m = re.match(r"\s*(0x[0-9a-fA-F]+)u,", line)
        if m:
            values.append(int(m.group(1), 16))
            continue
        m = re.match(r"\s*socom2_\w+::(k\w+Addr),", line)
        if m:
            values.append(consts[m.group(1)])
    assert len(values) == len(fields), (len(values), len(fields))
    return [(f, v, f in data_fields) for f, v in zip(fields, values)]


def wrap_targets(table):
    """(call sites, [(address, how)], [(address, how)] bindAddressHandler) from game_overrides_socom2.cpp."""
    src = open(OVERRIDES).read()
    field = {f: v for f, v, _d in table}
    local = {}   # const uint32_t kX = socom2_addresses::current().field;
    for name, fld in re.findall(r"const uint32_t (\w+) = socom2_addresses::current\(\)\.(\w+);", src):
        local[name] = fld
    bind_fields = re.findall(r"\{addr\.(\w+), \"\w+\", [\w:]+\}", src)
    sites, out = 0, []
    for arg in re.findall(r"runtime\.replaceFunction\(([^,]+),", src):
        sites += 1
        arg = arg.strip()
        if arg.startswith("0x"):
            out.append((int(arg.rstrip("uU"), 16), "literal (boot loader)"))
        elif arg.startswith("addr.") and arg[5:] in field:
            out.append((field[arg[5:]], "table: " + arg[5:]))
        elif arg in local:
            out.append((field[local[arg]], "table: " + local[arg]))
        elif arg == "b.address":
            for f in bind_fields:
                if (field[f], "table: " + f) not in out:
                    out.append((field[f], "table: " + f))
        elif arg == "entry":
            out.append((field["oskOpenThunk"], "table: oskOpenThunk"))
            out.append((field["oskOpen"], "table: oskOpen"))
        elif arg == "addr":
            out.append((None, "PS2X_CALL_TRACE (any address, from the environment)"))
        else:
            out.append((None, "unresolved argument " + arg))
    handlers = []
    for arg in re.findall(r"bindAddressHandler\(runtime, ([^,]+),", src):
        arg = arg.strip()
        if arg.startswith("0x"):
            handlers.append((int(arg.rstrip("uU"), 16), "literal (boot loader), ret0"))
        elif arg.startswith("addr."):
            handlers.append((field[arg[5:]], "table: %s, ret0" % arg[5:]))
    return sites, out, handlers


def research_mentions(addr, notes):
    forms = [("0x%08x" % addr), ("0x%x" % addr), ("fun_%08x" % addr)]
    hits = []
    for path, text in notes:
        if any(re.search(re.escape(f) + r"(?![0-9a-f])", text) for f in forms):
            hits.append(os.path.basename(path).split("-")[0])
    return hits


# ---- main ----------------------------------------------------------------------------------------

def main() -> None:
    for p in (DEMO, OURS_ELF, OURS_CSV, MATCHES, RENAMES):
        if not os.path.exists(p):
            print("NO-DATA: missing %s (git-ignored; see docs/research/44-demo-symbols.md)" % p)
            return
    data = open(DEMO, "rb").read()
    demo = read_elf(DEMO)
    demo_rows = demo.functions
    demo_segs = demo.segments
    our_rows = am.load_functions(OURS_CSV)
    ours = read_elf(OURS_ELF)
    our_segs = ours.segments
    our_name = {s: n for s, _e, n in our_rows}
    our_fnset = set(our_name)
    demo_fnset = set(s for s, _e, _n in demo_rows)
    demo_name_at = {s: n for s, _e, n in demo_rows}
    demo_size_at = {s: e - s for s, e, _n in demo_rows}

    # Task 7's pairs, with their demo addresses (the json has names only)
    details = {}
    pairs = gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details, prefix=True)
    js = json.load(open(MATCHES))
    assert sorted((p["name"], int(p["addr"], 16)) for p in js["pairs"]) == sorted((n, a) for n, a, _s in pairs), \
        "the re-run matcher disagrees with game/demo_symbol_matches.json"
    pair_by_demo = {info["demo_addr"]: (addr, info["how"]) for (_n, addr), info in details.items()}
    pair_by_ours = {addr: (name, info["how"], info["demo_addr"]) for (name, addr), info in details.items()}
    proposals = {int(r["Address"], 16): r for r in csv.DictReader(open(RENAMES))}
    prop7b = {}
    if os.path.exists(RENAMES_7B):
        lines = [ln for ln in open(RENAMES_7B) if not ln.startswith("#")]
        prop7b = {int(r["Address"], 16): r for r in csv.DictReader(lines)}
    print("[1] inputs: demo FUNC %d; our rows %d; Task 7 pairs %d (re-run == json: yes); proposals %d; 7b %d"
          % (len(demo_rows), len(our_rows), len(pairs), len(proposals), len(prop7b)))

    # Task 7b positional leads (research/45 sec 6): every candidate in an equal-count anchor gap
    anchors = sl.anchors_from_details(details)
    dside = am.Side(demo_rows, demo_segs)
    oside = am.Side(our_rows, our_segs)
    regions = [(v, v + len(b)) for v, b in oside.image.segments]
    gaps = sl.anchor_gaps(anchors, sorted(oside.starts), sorted(dside.starts), regions,
                          {o for _d, o, _h in anchors}, {d for d, _o, _h in anchors})
    lead_by_ours = {o: d for g in gaps for o, d in g}
    lead_by_demo = {d: o for o, d in lead_by_ours.items()}
    print("    positional leads (research/45 lever 1 candidates, before any body rule): gaps %d, candidates %d"
          % (len(gaps), len(lead_by_ours)))

    # .debug, CU level
    cus, dbg, clean = cu_walk(data, demo)
    ranges = sorted((lo, hi, name) for _o, name, lo, hi in cus if lo is not None and hi is not None)
    lows = [r[0] for r in ranges]

    def cu_file(addr):
        i = bisect.bisect_right(lows, addr) - 1
        if i >= 0 and ranges[i][0] <= addr < ranges[i][1]:
            return ranges[i][2]
        return None

    # classes
    members = {}
    free = []
    for s, _e, n in demo_rows:
        path = class_path(n)
        if path:
            members.setdefault("::".join(path), []).append(s)
        else:
            free.append(s)
    readme_classes = collections.Counter(readme_class(n) for _s, _e, n in demo_rows
                                         if re.search(r"__(Q\d|\d)", n))
    print("    members %d, free %d; classes by class path %d (README rsplit method: %d)"
          % (sum(len(v) for v in members.values()), len(free), len(members), len(readme_classes)))
    print("    README's three, by class path vs rsplit: " + ", ".join(
        "%s %d/%d" % (c, len(members.get(c, [])), readme_classes.get(c, 0))
        for c in ("CZSealBody", "CSealCtrlAi", "CZKit", "CZOnlineLobby", "CNetCnf")))

    # class-name occurrences in .debug, attributed to the enclosing CU's directory
    cu_offsets = [o for o, _n, _l, _h in cus]
    cu_names = [n for _o, n, _l, _h in cus]
    tokens = collections.defaultdict(collections.Counter)   # class -> Counter(short dir)
    bare = collections.defaultdict(set)
    for cls in members:
        bare[cls.split("::")[-1]].add(cls)
    for m in re.finditer(rb"[A-Za-z_][A-Za-z0-9_<>,:]{2,}", dbg):
        tok = m.group(0).decode("latin1")
        hit = set()
        if tok in bare:
            hit |= bare[tok]
        elif "__" in tok:
            p = class_path(tok)
            if p and "::".join(p) in members:
                hit.add("::".join(p))
        if hit:
            i = bisect.bisect_right(cu_offsets, m.start()) - 1
            sd = short_dir(directory_of(cu_names[i])) if i >= 0 else "?"
            for c in hit:
                tokens[c][sd] += 1

    # per-class rows
    demo_vt = {}
    for start, end, name in demo.objects:
        if name.startswith("__vt__"):
            p = class_path("x__" + name[len("__vt__"):] + "F")  # reuse the class-path parser
            if p:
                demo_vt["::".join(p)] = (start, end - start)
    rd_demo = make_reader(demo_segs)
    rd_ours = make_reader(our_segs)
    rows = []
    for cls, addrs in members.items():
        path = tuple(cls.split("::"))
        placed = collections.Counter(pair_by_demo[a][1] for a in addrs if a in pair_by_demo)
        our_addrs = [pair_by_demo[a][0] for a in addrs if a in pair_by_demo]
        prop = sum(1 for o in our_addrs if o in proposals)
        p7b = sum(1 for r in prop7b.values() if class_path(r["Mangled"]) == path)
        leads = [a for a in addrs if a in lead_by_demo]
        dirs_fn = collections.Counter(short_dir(directory_of(cu_file(a))) for a in addrs if cu_file(a))
        name = cls   # qualified: Metrowerks' RTTI string for a nested class is "zdb::CNode", not "CNode"
        template = "<" in cls
        in_demo = bool(find_all(demo_segs, b"\x00" + name.encode() + b"\x00")) if not template else None
        hits, rtti, vts = resolve(our_segs, name) if not template else ([], [], [])
        vt = demo_vt.get(cls)
        dslots = vt[1] // 4 - 2 if vt else 0          # the __vt__ object's own size: [RTTI, 0, slots...]
        vts = real_vtables(rd_ours, vts, our_fnset)
        rslots = [len(slots(rd_ours, v, our_fnset)) for v in vts]
        unplaced = [a for a in addrs if a not in pair_by_demo]
        largest = max(unplaced, key=lambda a: demo_size_at[a]) if unplaced else None
        rows.append({
            "class": cls, "subsystem": class_subsystem(path), "methods": len(addrs),
            "placed": sum(placed.values()),
            **{"placed_" + k.replace("+", "_").replace("-", "_"): placed.get(k, 0) for k in PASSES},
            "proposed_479": prop, "proposed_7b": p7b, "unplaced": len(unplaced),
            "positional_leads": len(leads),
            "demo_vtable_slots": dslots if vt else "",
            "name_in_demo": "" if template else ("yes" if in_demo else "no"),
            "name_in_r0001": "" if template else ("yes" if hits else "no"),
            "r0001_vtables": "" if template else len(vts),
            "r0001_vtable_slots": "/".join(str(x) for x in rslots),
            "debug_dirs_by_pc": ";".join("%s:%d" % kv for kv in dirs_fn.most_common()),
            "debug_dirs_by_name": ";".join("%s:%d" % kv for kv in tokens.get(cls, collections.Counter()).most_common(4)),
            "largest_unplaced": demo_name_at[largest] if largest else "",
            "largest_unplaced_size": demo_size_at[largest] if largest else "",
        })
    rows.sort(key=lambda r: (-r["methods"], r["class"]))
    cols = list(rows[0].keys())
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print("    wrote %s: %d rows (one per class path), %d columns" % (OUT_CSV, len(rows), len(cols)))
    tot = collections.Counter()
    for r in rows:
        for k in ("methods", "placed", "proposed_479", "proposed_7b", "unplaced", "positional_leads"):
            tot[k] += r[k]
    print("    totals over classes: " + ", ".join("%s %d" % kv for kv in tot.items()))
    print("    classes with >=1 placed: %d; with >=1 proposed: %d; with 0 placed: %d"
          % (sum(1 for r in rows if r["placed"]), sum(1 for r in rows if r["proposed_479"]),
             sum(1 for r in rows if not r["placed"])))
    hist = collections.Counter()
    for r in rows:
        m = r["methods"]
        hist["1" if m == 1 else "2-4" if m < 5 else "5-9" if m < 10 else "10-49" if m < 50 else ">=50"] += 1
    print("    classes by method count: " + ", ".join("%s %d" % (k, hist[k]) for k in ("1", "2-4", "5-9", "10-49", ">=50")))
    print("\n    top 40 by method count: class | methods | placed (exact/h+c/relinked/prefix/prefix+size) | "
          "proposed 479 | 7b | unplaced | leads | demo vt slots | name in r0001 | r0001 vts (slots)")
    for r in rows[:40]:
        print("    %-28s %4d %4d (%d/%d/%d/%d/%d) %3d %d %4d %3d %4s %3s %s (%s)" % (
            r["class"][:28], r["methods"], r["placed"], r["placed_exact"], r["placed_hash_callees"],
            r["placed_relinked_body"], r["placed_prefix"], r["placed_prefix_size"], r["proposed_479"],
            r["proposed_7b"], r["unplaced"], r["positional_leads"], r["demo_vtable_slots"],
            r["name_in_r0001"], r["r0001_vtables"], r["r0001_vtable_slots"]))

    # [2] subsystems
    print("\n[2] subsystems by name prefix: subsystem | classes | methods | placed | proposed 479 | unplaced | leads")
    sub = collections.defaultdict(collections.Counter)
    for r in rows:
        s = sub[r["subsystem"]]
        s["classes"] += 1
        for k in ("methods", "placed", "proposed_479", "unplaced", "positional_leads"):
            s[k] += r[k]
    for name, s in sorted(sub.items(), key=lambda kv: -kv[1]["methods"]):
        print("    %-28s %4d %5d %4d %4d %5d %4d" % (name, s["classes"], s["methods"], s["placed"],
                                                   s["proposed_479"], s["unplaced"], s["positional_leads"]))
    print("    free-function families: family | functions | placed | proposed 479 | leads")
    fam = collections.defaultdict(collections.Counter)
    for a in free:
        f = free_family(demo_name_at[a], directory_of(cu_file(a)) if cu_file(a) else None)
        fam[f]["functions"] += 1
        if a in pair_by_demo:
            fam[f]["placed"] += 1
            if pair_by_demo[a][0] in proposals:
                fam[f]["proposed"] += 1
        if a in lead_by_demo:
            fam[f]["leads"] += 1
    for name, s in sorted(fam.items(), key=lambda kv: -kv[1]["functions"]):
        print("    %-36s %5d %4d %4d %4d" % (name, s["functions"], s["placed"], s["proposed"], s["leads"]))
    rt = collections.Counter()
    for a in free:
        n = demo_name_at[a]
        if n.startswith("rt_"):
            rt["_".join(n.split("_")[:2])] += 1
    print("    rt_* by second token: " + ", ".join("%s %d" % kv for kv in rt.most_common()))
    print("    demo names containing 'Sase': %d; starting 'rt_audio': %d; 'rt_lpc10' strings in the demo: %d"
          % (sum(1 for n in demo_name_at.values() if "Sase" in n),
             sum(1 for n in demo_name_at.values() if n.startswith("rt_audio")), data.count(b"rt_lpc10")))

    print("\n    .debug CU walk: %d compile-unit DIEs (walk ends exactly at the section end: %s), %d with a pc range; "
          "demo functions inside a CU range: %d of %d" % (
              len(cus), "yes" if clean else "NO", len(ranges),
              sum(1 for s, _e, _n in demo_rows if cu_file(s)), len(demo_rows)))
    per_dir = collections.defaultdict(lambda: [set(), 0, 0, 0, set()])
    for _o, name, lo, hi in cus:
        per_dir[short_dir(directory_of(name))][0].add(name)
    for s, _e, n in demo_rows:
        f = cu_file(s)
        if f:
            e = per_dir[short_dir(directory_of(f))]
            e[1] += 1
            if s in pair_by_demo:
                e[2] += 1
                if pair_by_demo[s][0] in proposals:
                    e[3] += 1
            p = class_path(n)
            if p:
                e[4].add("::".join(p))
    print("    by source directory: dir | source files (CU names) | functions in its pc ranges | placed | "
          "proposed | classes with a member in its ranges")
    for d_, e in sorted(per_dir.items(), key=lambda kv: -kv[1][1]):
        print("    %-18s %3d %4d %3d %3d %3d" % (d_, len(e[0]), e[1], e[2], e[3], len(e[4])))
    fts_files = collections.Counter()
    for s, _e, _n in demo_rows:
        f = cu_file(s)
        if f and short_dir(directory_of(f)) == "FTS":
            fts_files[f.rsplit(BS, 1)[1]] += 1
    print("    FTS files by functions in range: " + ", ".join("%s %d" % kv for kv in fts_files.most_common()))
    fts_classes = collections.Counter()
    for s, _e, n in demo_rows:
        f = cu_file(s)
        p = class_path(n)
        if f and p and short_dir(directory_of(f)) == "FTS":
            fts_classes["::".join(p)] += 1
    print("    classes with members in FTS pc ranges (top 25): "
          + ", ".join("%s %d" % kv for kv in fts_classes.most_common(25)))
    by_name_dir = collections.Counter()
    for cls, c in tokens.items():
        for d_ in c:
            by_name_dir[d_] += 1
    print("    classes whose name occurs inside a directory's CUs: "
          + ", ".join("%s %d" % kv for kv in by_name_dir.most_common()))
    print("    classes whose name occurs anywhere in .debug (as a bare name or a mangled member): %d of %d"
          % (sum(1 for c in tokens.values() if c), len(rows)))

    # the RTTI resolve by bare vs qualified name, over the demo's own __vt__ classes (vtable_rtti.py uses bare)
    vt_count = collections.Counter()
    for cls in demo_vt:
        if "<" in cls:
            vt_count["template"] += 1
            continue
        qv = real_vtables(rd_ours, resolve(our_segs, cls)[2], our_fnset)
        q = bool(qv)
        vt_count["r0001 vtables located (qualified)"] += len(qv)
        vt_count["r0001 vtables located (qualified) that sit on a csv FUN_ row (data exported as code)"] += sum(1 for v in qv if v in our_fnset)
        b_ = bool(real_vtables(rd_ours, resolve(our_segs, cls.split("::")[-1])[2], our_fnset))
        vt_count["nested" if "::" in cls else "top-level"] += 1
        vt_count["resolved, qualified name"] += q
        vt_count["resolved, bare name"] += b_
        vt_count["nested resolved only when qualified"] += q and not b_ and "::" in cls
    print("\n    demo __vt__ classes %d: %s" % (len(demo_vt), ", ".join("%s %d" % kv for kv in sorted(vt_count.items()))))

    # [2b] the UI script-binding table: a string-keyed name transfer (research/11 sec 2a found the r0001 table)
    demo_bind = binding_table(demo_segs, demo_name_at, "NetCnfOpen")
    our_bind = binding_table(our_segs, our_name, "NetCnfOpen")
    demo_by_string = {st: fn for _a, st, fn in demo_bind}
    ui_rule = sum(1 for _a, st, fn in demo_bind if demo_name_at[fn].startswith("UI" + st + "__"))
    shared = [(a, st, fn) for a, st, fn in our_bind if st in demo_by_string]
    agree = disagree = 0
    for _a, st, fn in shared:
        if fn in pair_by_ours:
            if pair_by_ours[fn][0] == demo_name_at[demo_by_string[st]]:
                agree += 1
            else:
                disagree += 1
    bind_by_ours = {fn: (st, demo_name_at[demo_by_string[st]] if st in demo_by_string else None) for _a, st, fn in our_bind}
    print("\n[2b] UI script-binding table: demo %d rows at 0x%x (function named UI<command>__...: %d; the rest "
          "anonymous-namespace On*/Execute* handlers); r0001 %d rows at 0x%x, %d distinct functions, %d still auto-named"
          % (len(demo_bind), demo_bind[0][0] if demo_bind else 0, ui_rule, len(our_bind),
             our_bind[0][0] if our_bind else 0, len({f for _a, _s, f in our_bind}),
             sum(1 for _a, _s, f in our_bind if our_name[f].startswith(("FUN_", "thunk_FUN_")))))
    print("    r0001 command strings also in the demo table: %d (-> a demo name for that r0001 function); of those, "
          "Task 7 pairs on the r0001 target: agree %d, disagree %d; r0001-only commands: %d"
          % (len(shared), agree, disagree, len(our_bind) - len(shared)))
    net_cmds = [(st, fn) for _a, st, fn in our_bind
                if re.search(r"Net|Lobby|Medius|Clan|Buddy|Chat|DNAS|Online|GameList|Ignore|Friend|Persona|Login|Register|Ladder|CareerStats", st)]
    print("    network/lobby commands in the r0001 table: %d, of which the demo table names %d: %s"
          % (len(net_cmds), sum(1 for st, _f in net_cmds if st in demo_by_string),
             ", ".join("%s@0x%x%s" % (st, fn, "" if st in demo_by_string else "*") for st, fn in net_cmds)))

    # [3] hooks
    notes = [(p, open(p, encoding="utf-8", errors="replace").read().lower())
             for p in sorted(glob.glob("docs/research/*.md")) if not p.endswith("55-class-inventory.md")]
    toml_names = {}
    for name, addr in re.findall(r'"([A-Za-z_0-9]+)@(0x[0-9a-fA-F]+)"', open(TOML).read()):
        toml_names.setdefault(int(addr, 16), name)
    # retail vtable slot map, from every demo __vt__ class's bare name
    slot_map = collections.defaultdict(list)
    for cls, (vstart, _size) in demo_vt.items():
        if "<" in cls:
            continue
        _h, _r, vts = resolve(our_segs, cls)
        vts = real_vtables(rd_ours, vts, our_fnset)
        dsl = [struct.unpack("<I", rd_demo(vstart + 8 + 4 * k, 4))[0] for k in range(_size // 4 - 2)]
        for v in vts:
            rs = slots(rd_ours, v, our_fnset)
            for k, fa in enumerate(rs):
                if len(rs) == len(dsl) and len(vts) == 1:
                    lead = "equal-count lead " + str(demo_name_at.get(dsl[k]))
                elif k < len(dsl):
                    lead = "demo slot %d is %s (counts differ: alignment unproven)" % (k, demo_name_at.get(dsl[k]))
                else:
                    lead = None
                slot_map[fa].append((cls, v, k, len(rs), len(dsl), len(vts), lead))

    anchor_ours = sorted((o, d) for d, o, _h in anchors)
    anchor_keys = [o for o, _d in anchor_ours]
    demo_starts = sorted(demo_name_at)
    our_starts = sorted(our_name)

    def context(addr):
        """The Task 7 anchors either side of `addr` in its PT_LOAD of ours, and what lies between their demo twins."""
        region = next(((lo, hi) for lo, hi in regions if lo <= addr < hi), None)
        if region is None:
            return None
        i = bisect.bisect_left(anchor_keys, addr)
        lo = next((anchor_ours[j] for j in range(i - 1, -1, -1) if region[0] <= anchor_ours[j][0] < addr), None)
        hi = next((anchor_ours[j] for j in range(i, len(anchor_ours)) if addr < anchor_ours[j][0] < region[1]), None)
        if not lo or not hi:
            return None
        ours_n = bisect.bisect_left(our_starts, hi[0]) - bisect.bisect_right(our_starts, lo[0])
        text = "between anchors %s@0x%x and %s@0x%x; ours %d functions between" % (
            demo_name_at[lo[1]], lo[0], demo_name_at[hi[1]], hi[0], ours_n)
        if lo[1] < hi[1]:
            span = demo_starts[bisect.bisect_right(demo_starts, lo[1]):bisect.bisect_left(demo_starts, hi[1])]
            text += ", demo %d (in order)" % len(span)
            if len(span) <= 12:
                text += ": " + ", ".join(demo_name_at[x] for x in span)
        else:
            text += ", the demo twins are out of order (no span)"
        return text

    def describe(addr):
        out = {}
        if addr in pair_by_ours:
            n, how, _d = pair_by_ours[addr]
            out["task7"] = "%s [%s%s]" % (n, how, ", proposed" if addr in proposals else "")
        elif addr in prop7b:
            out["task7"] = "%s [7b positional, proposed]" % prop7b[addr]["Mangled"]
        else:
            out["task7"] = "unnamed"
        if addr in lead_by_ours:
            d = lead_by_ours[addr]
            out["lead"] = "%s (demo %d B / ours %d B)" % (demo_name_at[d], demo_size_at[d], oside.size.get(addr, 0))
        ctx = context(addr) if addr not in pair_by_ours else None
        if ctx:
            out["context"] = ctx
        if addr in slot_map:
            out["vtable"] = "; ".join(
                "%s vt 0x%x slot %d of %d (demo %d%s)%s" % (c, v, k, n, dn, ", 1 of %d vts" % nv if nv > 1 else "",
                                                           " -> " + ld if ld else "")
                for c, v, k, n, dn, nv, ld in slot_map[addr])
        if addr in bind_by_ours:
            st, dname = bind_by_ours[addr]
            out["binding"] = "command %s -> demo %s" % (st, dname or "(r0001-only command)")
        out["ours"] = our_name.get(addr, "(no csv row)")
        if addr in toml_names:
            out["toml"] = toml_names[addr]
        m = research_mentions(addr, notes)
        if m:
            out["notes"] = ",".join(sorted(set(m)))
        return out

    def named_by_nothing(addr, dsc):
        return (dsc["task7"] == "unnamed" and "toml" not in dsc and "binding" not in dsc
                and our_name.get(addr, "FUN_").startswith(("FUN_", "thunk_FUN_")))

    table = table_r0001()
    fn_fields = [(f, v) for f, v, d in table if not d]
    print("\n[3] socom2_addresses.h: %d fields, %d DATA, %d function fields (r0001 column)"
          % (len(table), len(table) - len(fn_fields), len(fn_fields)))
    unnamed = nothing = 0
    for f, v in fn_fields:
        dsc = describe(v)
        unnamed += dsc["task7"] == "unnamed"
        nothing += named_by_nothing(v, dsc)
        print("    %-20s 0x%08x  %s" % (f, v, " | ".join("%s: %s" % kv for kv in dsc.items())))
    print("    function fields named by no Task 7 pair or proposal: %d of %d; by nothing on disk (no pair, "
          "proposal, toml name, binding-table command or hand name): %d" % (unnamed, len(fn_fields), nothing))
    sites, wraps, handlers = wrap_targets(table)
    fixed = sorted({a for a, _h in wraps if a is not None})
    print("    game_overrides_socom2.cpp: %d replaceFunction call sites -> %d fixed addresses (+ %d dynamic)"
          % (sites, len(fixed), sum(1 for a, _h in wraps if a is None)))
    unnamed_w = nothing_w = 0
    loader = [a for a in fixed if a < 0x1D5600]
    for a in fixed:
        how = next(h for x, h in wraps if x == a)
        dsc = describe(a)
        unnamed_w += dsc["task7"] == "unnamed"
        nothing_w += named_by_nothing(a, dsc)
        if how.startswith("literal"):
            print("    %-26s 0x%08x  %s" % (how[:26], a, " | ".join("%s: %s" % kv for kv in dsc.items())))
    print("    wrap addresses (loader literals %d, table fields %d): named by no Task 7 pair or proposal %d of %d; "
          "by nothing on disk %d" % (len(loader), len(fixed) - len(loader), unnamed_w, len(fixed), nothing_w))
    for a, how in handlers:
        print("    bindAddressHandler %-26s 0x%08x  %s" % (how, a, " | ".join("%s: %s" % kv for kv in describe(a).items())))
    print("    parity probes (guest_addresses.py, r0001):")
    for name, col in ga.PROBE_ADDRESSES.items():
        a = col["r0001"]
        dsc = describe(a)
        in_fn = a in our_fnset
        print("    %-14s 0x%08x  %s%s" % (name, a, "function start | " if in_fn else "data | ",
                                          " | ".join("%s: %s" % kv for kv in dsc.items())))
        if name == "actor_vtable":
            for cls in ("CZSealBody",):
                h, r, v = resolve(our_segs, cls)
                print("        RTTI chain %s: string %s, RTTI %s, vtables %s -> actor_vtable is %s's vtable: %s"
                      % (cls, [hex(x + 1) for x in h], [hex(x) for x in r], [hex(x) for x in v], cls,
                         "yes" if a in v else "no"))
                for vt_addr in real_vtables(rd_ours, v, our_fnset):
                    builders = [st for st, en, _n in our_rows if forms_address(rd_ours, st, en, vt_addr)]
                    print("        functions of ours that build 0x%x (vtable-pointer store: constructor/destructor "
                          "candidates): %d: %s" % (vt_addr, len(builders), ", ".join(
                              "0x%x%s" % (b, "[%s]" % pair_by_ours[b][0] if b in pair_by_ours else "") for b in builders)))
    probe_fns = sorted({int(x, 16) for x in re.findall(r"FUN_([0-9a-f]{8})", open("tools_py/parity/guest_addresses.py").read())})
    for a in probe_fns:
        print("    move_scale site 0x%08x  %s" % (a, " | ".join("%s: %s" % kv for kv in describe(a).items())))

    # [4] online and voice
    print("\n[4] online and voice classes: class | methods | placed | proposed 479 | 7b | unplaced | leads | "
          "demo vt slots | name in r0001 | r0001 vts (slots) | debug dirs")
    want = ("CZOnlineLobby", "CNetCnf", "CHNetCnf", "CZNetwork", "CZNetGame", "CZNetVoice", "CZSealState",
            "CZBombState", "CZGameState", "CZPersonaState", "CZGrenadeState", "CNetClock", "CPacket", "CPacketMsg",
            "CSealStats", "CZMPBombMapItem", "C2DMessage_Q", "C2DMessageString", "Headset")
    by_class = {r["class"]: r for r in rows}
    for c in want:
        r = by_class.get(c)
        if not r:
            print("    %-18s not in the demo" % c)
            continue
        print("    %-18s %4d %3d %3d %d %4d %3d %4s %3s %s (%s) %s" % (
            c, r["methods"], r["placed"], r["proposed_479"], r["proposed_7b"], r["unplaced"], r["positional_leads"],
            r["demo_vtable_slots"], r["name_in_r0001"], r["r0001_vtables"], r["r0001_vtable_slots"],
            r["debug_dirs_by_pc"] or r["debug_dirs_by_name"]))
    for label, pred in (("rt_msg_client_*", lambda n: n.startswith("rt_msg_client")),
                        ("rt_msg_* (all)", lambda n: n.startswith("rt_msg")),
                        ("rt_* (all)", lambda n: n.startswith("rt_")),
                        ("UINet*/UILobby*/UI*Clan* bindings", lambda n: re.match(r"UI(Net|Lobby|.*Clan|Medius)", n)),
                        ("PTT_/PTTServer_", lambda n: n.startswith(("PTT_", "PTTServer_"))),
                        ("libpttclient CU range (LPC-10 + PTT)",
                         None)):
        if pred is None:
            sel = [s for s, _e, _n in demo_rows if cu_file(s) and "libpttclient" in cu_file(s)]
        else:
            sel = [s for s, _e, n in demo_rows if pred(n)]
        pl = [s for s in sel if s in pair_by_demo]
        print("    %-38s %4d %3d %3d %4d leads %d%s" % (
            label, len(sel), len(pl), sum(1 for s in pl if pair_by_demo[s][0] in proposals),
            len(sel) - len(pl), sum(1 for s in sel if s in lead_by_demo),
            (" placed: " + ", ".join("%s@0x%x[%s]" % (demo_name_at[s], pair_by_demo[s][0], pair_by_demo[s][1])
                                      for s in pl[:8])) if pl and len(pl) <= 8 else ""))
    for c in ("CZOnlineLobby", "CNetCnf", "CZNetwork", "CZSealState", "CZBombState", "CZNetGame", "CZNetVoice"):
        addrs = members.get(c, [])
        pl = ["%s@0x%x[%s%s]" % (demo_name_at[a].split("__")[0] or demo_name_at[a], pair_by_demo[a][0], pair_by_demo[a][1],
                                  ",P" if pair_by_demo[a][0] in proposals else "") for a in addrs if a in pair_by_demo]
        ld = ["%s->0x%x" % (demo_name_at[a].split("__" + str(len(c)))[0], lead_by_demo[a]) for a in addrs if a in lead_by_demo]
        print("    %s placed: %s" % (c, ", ".join(pl) or "-"))
        if ld:
            print("    %s positional leads: %s" % (c, ", ".join(ld)))
    rtc = [(s, n) for s, _e, n in demo_rows if n.startswith("rt_msg_client")]
    print("    rt_msg_client placed: " + ", ".join("%s@0x%x[%s]" % (n, pair_by_demo[s][0], pair_by_demo[s][1])
                                                   for s, n in rtc if s in pair_by_demo))
    for label, path in (("demo", DEMO), ("r0001", OURS_ELF)):
        blob = open(path, "rb").read()
        print("    RTIME version strings in %s: %s" % (label, ", ".join(sorted(set(
            m.decode() for m in re.findall(rb"(rt_[a-z0-9_]+ version: [0-9.]+)", blob)))) or "none"))
        print("    RTIME CVS modules in %s: %s" % (label, ", ".join("%s %d" % kv for kv in sorted(collections.Counter(
            m.decode() for m in re.findall(rb"/projects/rtime/CVS/([A-Za-z0-9_]+)/", blob)).items())) or "none"))
    for label, needle in (("Sase in r0001", b"Sase"), ("SaseEncVad in r0001", b"SaseEncVad"),
                          ("SaseDec in r0001", b"SaseDec"), ("rt_audio in r0001", b"rt_audio"),
                          ("rt_audio in demo", None)):
        if needle is None:
            print("    %-22s %d" % (label, data.count(b"rt_audio")))
        else:
            print("    %-22s %d" % (label, sum(d.count(needle) for _v, d in our_segs)))

    # [5] gap map
    with_vt = [r for r in rows if r["r0001_vtables"] not in ("", 0)]
    equal = [r for r in with_vt if r["r0001_vtables"] == 1 and r["demo_vtable_slots"] != ""
             and str(r["demo_vtable_slots"]) == r["r0001_vtable_slots"]]
    print("\n[5] Goal 3's reach: classes with >= 1 r0001 vtable (qualified RTTI): %d, methods %d, unplaced %d; "
          "one vtable with demo slots == r0001 slots: %d (methods %d)" % (
              len(with_vt), sum(r["methods"] for r in with_vt), sum(r["unplaced"] for r in with_vt),
              len(equal), sum(r["methods"] for r in equal)))
    gap = [r for r in rows if r["methods"] >= 10 and r["placed"] == 0]
    print("[5] gap map: classes with >= 10 methods and 0 placed: %d (methods %d)"
          % (len(gap), sum(r["methods"] for r in gap)))
    kinds = collections.Counter()
    for r in gap:
        if r["name_in_r0001"] == "":
            k = "template (name check n/a)"
        elif r["name_in_r0001"] == "yes":
            k = "name in r0001 (class survives: edited bodies)" if r["r0001_vtables"] else "name in r0001, no vtable via RTTI"
        elif r["name_in_demo"] == "yes":
            k = "name in demo, absent in r0001 (dropped, renamed, or RTTI discarded)"
        else:
            k = "name in neither image (no RTTI string: non-virtual class) -- uninformative"
        kinds[k] += 1
        r["_kind"] = k
    for k, n in kinds.most_common():
        print("    %-72s %d" % (k, n))
    print("    class | methods | leads | demo vt slots | name demo/r0001 | r0001 vts (slots) | debug dirs | kind")
    for r in gap:
        print("    %-28s %4d %3d %4s %3s/%-3s %s (%s) %s | %s" % (
            r["class"][:28], r["methods"], r["positional_leads"], r["demo_vtable_slots"], r["name_in_demo"],
            r["name_in_r0001"], r["r0001_vtables"], r["r0001_vtable_slots"],
            r["debug_dirs_by_pc"] or r["debug_dirs_by_name"] or "-", r["_kind"]))


if __name__ == "__main__":
    main()
