"""Metrowerks (GNU v2 style) mangled name -> Class_Method, with the overload-collision census.
(Task 7 review, socom-pc-6c)

Run from the repo root:  python <this file>

Not a demangler: argument types are ignored on purpose, so overloads collide and are reported.
The class path is a single <len><Name> or a Q<n> nested list (Q23zdb5CNode -> zdb_CNode);
template arguments are dropped; the result is sanitised to [A-Za-z0-9_]. Names with no
class marker (sce*, libc, z* free functions) pass through sanitised.
"""
import collections
import csv
import os
import re
import sys

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py.elf_symbols import read_elf  # noqa: E402

DEMO = "game/demo_scus_972_05/SCUS_972.05"
RENAMES = "game/demo_symbol_renames.csv"

OPERATORS = {
    "__ct": "ctor", "__dt": "dtor", "__as": "op_assign",
    "__pl": "op_add", "__mi": "op_sub", "__ml": "op_mul", "__dv": "op_div", "__md": "op_mod",
    "__eq": "op_eq", "__ne": "op_ne", "__lt": "op_lt", "__gt": "op_gt", "__le": "op_le", "__ge": "op_ge",
    "__vc": "op_index", "__cl": "op_call", "__nw": "op_new", "__dl": "op_delete",
    "__nwa": "op_new_array", "__dla": "op_delete_array",
    "__aa": "op_and", "__oo": "op_or", "__er": "op_xor", "__ad": "op_bitand", "__or": "op_bitor",
    "__ls": "op_lsh", "__rs": "op_rsh", "__nt": "op_not", "__ng": "op_neg", "__co": "op_compl",
    "__pp": "op_inc", "__mm": "op_dec", "__rf": "op_deref", "__rm": "op_arrow",
    "__apl": "op_addassign", "__ami": "op_subassign", "__amu": "op_mulassign", "__adv": "op_divassign",
}
_SPLIT = re.compile(r"^(.*?)__(?:Q\d|\d+)")
_SAFE = re.compile(r"[^A-Za-z0-9_]")


def readable(mangled: str) -> str:
    """'Mul__5CQuatCFPC5CQuatP5CQuat' -> 'CQuat_Mul'; 'sceCdRead' -> 'sceCdRead'."""
    m = _SPLIT.match(mangled)
    if not m:
        return _SAFE.sub("_", mangled)
    fn = m.group(1)
    rest = mangled[len(fn) + 2:]
    fn = OPERATORS.get(fn, fn)
    fn = re.sub(r"<.*>", "", fn)
    classes = []
    q = re.match(r"Q(\d)", rest)
    if q:
        pos = q.end()
        for _ in range(int(q.group(1))):
            n = re.match(r"(\d+)", rest[pos:])
            if not n:
                break
            length = int(n.group(1))
            pos += n.end()
            classes.append(rest[pos:pos + length])
            pos += length
    else:
        n = re.match(r"(\d+)", rest)
        if n:
            length = int(n.group(1))
            classes.append(rest[n.end():n.end() + length])
    return _SAFE.sub("_", "_".join(classes + [fn]) if classes else fn)


def census(names, label):
    counts = collections.Counter(readable(n) for n in names)
    dups = {k: v for k, v in counts.items() if v > 1}
    print(f"{label}: {len(names)} names -> {len(counts)} distinct readable; "
          f"{len(dups)} colliding names covering {sum(dups.values())} functions")
    print("  worst:", sorted(dups.items(), key=lambda kv: -kv[1])[:12])
    return counts


def main() -> None:
    rows = list(csv.DictReader(open(RENAMES)))
    census([r["Mangled"] for r in rows], "479 proposals")
    demo_names = [name for _s, _e, name in read_elf(DEMO).functions]
    census(demo_names, "demo .symtab")
    classes = collections.Counter(
        readable(n).rsplit("_", 1)[0] for n in demo_names if re.search(r"__(Q\d|\d)", n))
    print(f"classes {len(classes)}; largest:", classes.most_common(30))
    for sample in ("Mul__5CQuatCFPC5CQuatP5CQuat", "__ct__7CPacketFP7CPacketUiUi",
                   "GetNodePos__10CZSealBodyFPCQ23zdb5CNodeR6CPnt3Db",
                   "DrawFunc<11CDynGrenade>__2aiFQ22ai9LINE_TYPEffUi11CDynGrenade",
                   "__pl__6CPnt3DCFRC6CPnt3D", "sceCdRead", "__sinit_ent_main.cpp"):
        print(f"  {sample} -> {readable(sample)}")


if __name__ == "__main__":
    main()
