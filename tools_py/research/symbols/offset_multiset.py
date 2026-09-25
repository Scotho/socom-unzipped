"""Member-offset multisets as a looser body key (Sprint 12 research wave, question 9; research/54).

Run from the repo root:  python tools_py/research/symbols/offset_multiset.py [--csv game/offset_multiset_new.csv]

Read-only. Inputs: game/demo_scus_972_05/SCUS_972.05, game/disc/socom2_game.elf,
recomp/socom2_ghidra.csv. Task 7's 987 pairs are re-derived in-process by
`ghidra_symbol_match.match(prefix=True)` (research/44 command A's match, which carries the demo
address that game/demo_symbol_matches.json does not) and checked against that json's count.

For every function on both sides it takes each load/store (lb lbu lh lhu lw lwu lwl lwr ld ldl ldr lq
sb sh sw sd swl swr sdl sdr sq lwc1 ldc1 swc1 sdc1 lqc2 sqc2) with its signed 16-bit displacement and
drops the ones based on $sp, on $gp, on $zero, and on a register a `lui` (or a lui+addiu/ori pair)
put an address in -- the last is address_matcher's relinked-body mask, because such a displacement is
half a global's address and moves with the link. Three keys over what is left:

  K1 opdisp  the multiset of (opcode, displacement)
  K2 disp    the multiset of displacements alone
  K3 objptr  K1 restricted to accesses based on $a0, $v0 or $s0-$s7 (the `this`/object pointers)

It prints, in order (section numbers are research/54's):

  [1] the access census: how many accesses each exclusion removed, per side
  [2] per key: pairs unique both ways (one demo function and one of our rows wear the key image-wide),
      >= 3 accesses, both bodies >= 64 B; how many are beyond the 987; of those how many clear size
      ratio >= 0.50; agreement / contradiction with the 987 where they overlap, by Task 7 pass; the
      prologue-only pairs the key confirms; research/45's six 7b rows against the key
  [2b] link order as a key-independent check on the new pairs: `bracket` and `near` (64 KB) against
      the 987 (and the 987 plus the other new pairs), the truth rate from the 987 leave-one-out, a null
      from the same pairs with the demo side rotated, and the false-pair count those three imply
  [3] research/45 sec 3's holdout over the 828 PROVED pairs (3 folds, blocks of 8 and of 1), per key,
      for image-wide uniqueness and for uniqueness among the functions the kept anchors leave, with
      two tightenings: + equal masked 16-instruction prologue (7b's tier B key), + callee set agreeing
      through the kept anchors; then the pass as it would run (all 987 as anchors)
  [3b] seven candidate rules over the K1 new pairs, each scored by [2b]'s link-order test
  [4] where the new pairs land: per PT_LOAD of ours, engine-shaped or not (ghidra_symbol_match.
      is_engine), readable classes (readable() copied from readable_names.py), the twelve largest,
      with demo/our sizes -- for every new K1 pair (R1) and for the recommended rule (R7)
  [5] research/45 sec 6's 126 engine-shaped positional leads (recomputed: untiered positional
      candidates with an engine-shaped name) and all 528 positional candidates against the keys:
      unique pairing agreeing or contradicting, key equal, and the multiset-Jaccard rank of the
      positional partner in its gap and image-wide (and mutual best from our side)

About 25 seconds. `--csv PATH` also writes the recommended rule's (R7's) new pairs -- names, addresses, sizes and access
counts, no bytes -- to PATH, which must be under game/ (git-ignored).
"""
import argparse
import bisect
import collections
import csv
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py import address_matcher as am  # noqa: E402
from tools_py import ghidra_symbol_match as gsm  # noqa: E402
from tools_py import symbol_levers as sl  # noqa: E402
from tools_py.elf_symbols import read_elf  # noqa: E402

DEMO = "game/demo_scus_972_05/SCUS_972.05"
OURS_ELF = "game/disc/socom2_game.elf"
OURS_CSV = "recomp/socom2_ghidra.csv"
MATCHES = "game/demo_symbol_matches.json"

MNEMONIC = {0x1A: "ldl", 0x1B: "ldr", 0x1E: "lq", 0x1F: "sq", 0x20: "lb", 0x21: "lh", 0x22: "lwl",
            0x23: "lw", 0x24: "lbu", 0x25: "lhu", 0x26: "lwr", 0x27: "lwu", 0x28: "sb", 0x29: "sh",
            0x2A: "swl", 0x2B: "sw", 0x2C: "sdl", 0x2D: "sdr", 0x2E: "swr", 0x31: "lwc1",
            0x35: "ldc1", 0x36: "lqc2", 0x37: "ld", 0x39: "swc1", 0x3D: "sdc1", 0x3E: "sqc2",
            0x3F: "sd"}
SP, GP, ZERO = 29, 28, 0
OBJ_REGS = frozenset([2, 4] + list(range(16, 24)))      # $v0, $a0, $s0-$s7
KEYS = ("K1 opdisp", "K2 disp", "K3 objptr")
MIN_ACC, MIN_BODY, RATIO = 3, 64, 0.50


# ---- readable(), copied from tools_py/research/symbols/readable_names.py (the brief says copy) ----
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


def readable_class(mangled: str) -> Optional[str]:
    r = readable(mangled)
    return r.rsplit("_", 1)[0] if r != _SAFE.sub("_", mangled) and "_" in r else None


# ---- the accesses ----------------------------------------------------------------------------

def accesses(code: bytes, census: collections.Counter) -> List[Tuple[int, int, int]]:
    """[(opcode, base register, signed displacement)] kept for the keys; `census` counts every drop."""
    out = []
    holds: set = set()
    for i in range(0, len(code) - 3, 4):
        w = int.from_bytes(code[i:i + 4], "little")
        op = w >> 26
        rs, rt = (w >> 21) & 0x1F, (w >> 16) & 0x1F
        if op == am.LUI_OP:
            holds.add(rt)
            holds.discard(0)
            continue
        if op in am.LO_OPS and rs in holds:
            holds.add(rt)
            holds.discard(0)
            continue
        if op in MNEMONIC:
            disp = w & 0xFFFF
            disp = disp - 0x10000 if disp >= 0x8000 else disp
            census["all"] += 1
            if rs == SP:
                census["$sp"] += 1
            elif rs == GP:
                census["$gp"] += 1
            elif rs == ZERO:
                census["$zero"] += 1
            elif rs in holds:
                census["lui-formed (global)"] += 1
            else:
                census["kept"] += 1
                out.append((op, rs, disp))
        dest = am._dest_reg(w)
        if dest is not None:
            holds.discard(dest)
    return out


def keys_of(acc) -> Tuple[tuple, tuple, tuple]:
    k1 = tuple(sorted((op, d) for op, _r, d in acc))
    k2 = tuple(sorted(d for _op, _r, d in acc))
    k3 = tuple(sorted((op, d) for op, r, d in acc if r in OBJ_REGS))
    return k1, k2, k3


class Keyed:
    """One side: size, keys, access lists, prologue hash, callees, per function with bytes."""

    def __init__(self, side: am.Side):
        self.side = side
        self.census = collections.Counter()
        self.size, self.key, self.acc = {}, {}, {}
        for start in side.starts:
            body = side.body.get(start, b"")
            if not body:
                continue
            acc = accesses(body, self.census)
            self.size[start] = len(body)
            self.acc[start] = acc
            self.key[start] = keys_of(acc)
        self.count = [collections.Counter(k[i] for k in self.key.values()) for i in range(3)]
        self.by_key = [collections.defaultdict(list) for _ in range(3)]
        for start, k in self.key.items():
            for i in range(3):
                self.by_key[i][k[i]].append(start)
        self._pro = {}

    def prologue(self, start):
        if start not in self._pro:
            self._pro[start] = sl._prologue(self.side, start)
        return self._pro[start]


def eligible(ki, d, o, demo, ours) -> bool:
    k = demo.key[d][ki]
    return (len(k) >= MIN_ACC and demo.size[d] >= MIN_BODY and ours.size[o] >= MIN_BODY)


def ratio(a: int, b: int) -> float:
    return min(a, b) / max(a, b) if max(a, b) else 0.0


def unique_pairs(ki, demo: Keyed, ours: Keyed, pool_d=None, pool_o=None) -> Dict[int, int]:
    """{demo: ours} -- the key worn by exactly one function on each side (image-wide, or in the pools)."""
    if pool_d is None:
        dcount, ocount = demo.count[ki], ours.count[ki]
        dby, oby = demo.by_key[ki], ours.by_key[ki]
    else:
        dby, oby = collections.defaultdict(list), collections.defaultdict(list)
        for s in pool_d:
            if s in demo.key:
                dby[demo.key[s][ki]].append(s)
        for s in pool_o:
            if s in ours.key:
                oby[ours.key[s][ki]].append(s)
        dcount = {k: len(v) for k, v in dby.items()}
        ocount = {k: len(v) for k, v in oby.items()}
    out = {}
    for k, ds in dby.items():
        if dcount[k] == 1 and ocount.get(k, 0) == 1:
            d, o = ds[0], oby[k][0]
            if eligible(ki, d, o, demo, ours):
                out[d] = o
    return out


def callees_agree(d, o, demo: Keyed, ours: Keyed, anchor_map: Dict[int, int]) -> bool:
    """True when >= 1 demo callee is an anchor and every anchored callee maps into our callees."""
    mapped = [anchor_map[t] for t in demo.side.calls[d] if t in anchor_map]
    if not mapped:
        return False
    have = set(ours.side.calls[o])
    return all(t in have for t in mapped)


def tightened(pairs, how, demo, ours, anchor_map):
    if how == "":
        return dict(pairs)
    if how == "+prologue":
        return {d: o for d, o in pairs.items()
                if demo.prologue(d) is not None and demo.prologue(d) == ours.prologue(o)}
    if how == "+callees":
        return {d: o for d, o in pairs.items() if callees_agree(d, o, demo, ours, anchor_map)}
    raise ValueError(how)


def jaccard(a, b) -> float:
    ca, cb = collections.Counter(a), collections.Counter(b)
    inter = sum((ca & cb).values())
    union = sum((ca | cb).values())
    return inter / union if union else 0.0


NEAR = 0x10000      # 64 KB: "near" = within this of a neighbouring anchor's demo address, on its side


def order_check(pairs, ref, regions):
    """Counter over {bracket, near} x {yes, no} plus edge -- link order as a check on (demo, ours) pairs.

    Independent of every body key. `ref` is [(demo, ours)] reference pairs (the 987, or the 987 plus
    the other new pairs). For each pair take the two nearest reference pairs by OUR address inside our
    PT_LOAD, skipping any at the same our address (so a pair never vouches for itself). `bracket`: the
    demo address lies strictly between the two references' demo addresses. `near`: it lies within
    NEAR bytes of either reference's demo address, on that reference's side. `bracket` fails a true
    pair at a translation-unit boundary whose other reference is in another unit; `near` does not. Both
    are read against the truth (the 987, leave-one-out) and against a null (the demo side rotated).
    """
    per = []
    for lo, hi in regions:
        inside = sorted((o, d) for d, o in ref if lo <= o < hi)
        per.append((lo, hi, [o for o, _d in inside], [d for _o, d in inside]))
    out = collections.Counter()
    bad = []
    for d, o in pairs:
        for lo, hi, os_, ds_ in per:
            if not lo <= o < hi:
                continue
            i = bisect.bisect_left(os_, o)
            j = i
            while j < len(os_) and os_[j] == o:
                j += 1
            if i == 0 or j >= len(os_):
                out["edge"] += 1
                break
            dp, dn_ = ds_[i - 1], ds_[j]
            br = dp < d < dn_
            near = (dp < d <= dp + NEAR) or (dn_ - NEAR <= d < dn_)
            out["bracket yes" if br else "bracket no"] += 1
            out["near yes" if near else "near no"] += 1
            if not near:
                bad.append((d, o))
            break
        else:
            out["edge"] += 1
    return out, bad


def rate(c, test):
    y, n = c[test + " yes"], c[test + " no"]
    return y / (y + n) if y + n else 0.0


def null_rate(pairs, ref, regions, test, fractions=(0.2, 0.4, 0.6, 0.8)):
    """The same test on the same pairs with the demo side rotated by a large fraction of the list
    (sorted by our address), so each our row meets a demo function from elsewhere -- what a FALSE
    pairing scores. A rotation by one or two would pair a row with its neighbour's demo function,
    which sits near by construction; that is why the rotations are fractions."""
    pairs = sorted(pairs, key=lambda p: p[1])
    ds = [d for d, _o in pairs]
    rates = []
    for fr in fractions:
        r = int(len(ds) * fr)
        if r == 0:
            continue
        rot = [(ds[(k + r) % len(ds)], o) for k, (_d, o) in enumerate(pairs)]
        c, _b = order_check(rot, ref, regions)
        rates.append(rate(c, test))
    return sum(rates) / len(rates) if rates else 0.0


def false_estimate(p_obs, p_true, p_null, n):
    """f*n where p_obs = (1-f) p_true + f p_null -- the false pairs the link-order rates imply."""
    if p_true <= p_null:
        return float("nan")
    f = max(0.0, (p_true - p_obs) / (p_true - p_null))
    return f * n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--csv", help="write the recommended pass's new pairs here (under game/)")
    args = ap.parse_args()
    for p in (DEMO, OURS_ELF, OURS_CSV):
        if not os.path.exists(p):
            print("NO-DATA: missing", p)
            return 2
    if args.csv and not os.path.abspath(args.csv).startswith(os.path.abspath("game") + os.sep):
        print("NO-DATA: --csv must be under game/ (git-ignored)")
        return 2

    demo_rows, demo_segs = gsm.load_demo(DEMO)
    our_rows, our_segs = gsm.load_ours(OURS_ELF, OURS_CSV)
    details: Dict = {}
    pairs987 = gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details, prefix=True)
    anchors = sl.anchors_from_details(details)            # [(demo, ours, how)]
    proved = sl.proved_anchors(anchors)
    json_n = json.load(open(MATCHES))["matched"] if os.path.exists(MATCHES) else None
    print("Task 7 re-derived: %d pairs (%s says %s), %d PROVED, %d prologue-only"
          % (len(pairs987), MATCHES, json_n, len(proved), len(anchors) - len(proved)))
    how_of_d = {d: h for d, _o, h in anchors}
    t7_d2o = {d: o for d, o, _h in anchors}
    t7_o2d = {o: d for d, o, _h in anchors}

    demo = Keyed(am.Side(demo_rows, demo_segs))
    ours = Keyed(am.Side(our_rows, our_segs))
    dname = demo.side.name
    oname = ours.side.name

    # [1] census ---------------------------------------------------------------------------
    print("\n[1] load/store census (functions with bytes: demo %d, ours %d)" % (len(demo.key), len(ours.key)))
    for label, k in (("demo", demo), ("ours", ours)):
        c = k.census
        zrows = []
        for st, body in k.side.body.items():
            n = sum(1 for i in range(0, len(body) - 3, 4)
                    if (int.from_bytes(body[i:i + 4], "little") >> 26) in MNEMONIC
                    and (int.from_bytes(body[i:i + 4], "little") >> 21) & 0x1F == ZERO)
            if n:
                zrows.append((n, k.side.size[st], st))
        zrows.sort(reverse=True)
        if zrows:
            print("  %s: rows with a $zero-based access %d; the five heaviest (count, size, addr): %s"
                  % (label, len(zrows), ", ".join("%d/%d B/0x%08x" % z for z in zrows[:5])))
        print("  %s: accesses %d; dropped $sp %d, $gp %d, $zero %d, lui-formed %d; kept %d"
              % (label, c["all"], c["$sp"], c["$gp"], c["$zero"], c["lui-formed (global)"], c["kept"]))
        for ki, kn in enumerate(KEYS):
            nontriv = sum(1 for s, key in k.key.items() if len(key[ki]) >= MIN_ACC and k.size[s] >= MIN_BODY)
            uniq = sum(1 for s, key in k.key.items()
                       if len(key[ki]) >= MIN_ACC and k.size[s] >= MIN_BODY and k.count[ki][key[ki]] == 1)
            print("    %-10s functions >=64 B with >=3 accesses %5d, of which key unique on this side %5d"
                  % (kn, nontriv, uniq))

    # [2] the pairs ------------------------------------------------------------------------
    print("\n[2] unique both ways (image-wide), >= %d accesses, both bodies >= %d B" % (MIN_ACC, MIN_BODY))
    image_pairs = {}
    for ki, kn in enumerate(KEYS):
        pairs = unique_pairs(ki, demo, ours)
        image_pairs[ki] = pairs
        agree = collections.Counter()
        contra = []
        new = []
        for d, o in sorted(pairs.items()):
            if d in t7_d2o or o in t7_o2d:
                if t7_d2o.get(d) == o:
                    agree[how_of_d[d]] += 1
                else:
                    contra.append((d, o))
            else:
                new.append((d, o))
        new_r = [(d, o) for d, o in new if ratio(demo.size[d], ours.size[o]) >= RATIO]
        new_anon = [(d, o) for d, o in new_r if gsm.is_anonymous(oname[o])]
        print("  %s: pairs %d; overlap the 987: agree %d (%s), contradict %d; beyond the 987 %d, "
              "of which ratio >= %.2f %d (our row still FUN_ %d)"
              % (kn, len(pairs), sum(agree.values()),
                 ", ".join("%s %d" % kv for kv in sorted(agree.items())), len(contra), len(new),
                 RATIO, len(new_r), len(new_anon)))
        for d, o in contra:
            od, do = t7_d2o.get(d), t7_o2d.get(o)
            print("    CONTRADICTION demo 0x%08x %s (%d B, %d acc) -> ours 0x%08x (%d B); Task 7 has demo->%s "
                  "[%s], ours<-%s [%s]"
                  % (d, dname[d], demo.size[d], len(demo.key[d][ki]), o, ours.size[o],
                     "0x%08x" % od if od else "-", how_of_d.get(d, "-"),
                     ("0x%08x %s" % (do, dname[do])) if do else "-", how_of_d.get(do, "-") if do else "-"))
    conf = sorted((d for d, o in image_pairs[0].items()
                   if t7_d2o.get(d) == o and how_of_d[d].startswith("prefix")), key=lambda d: -demo.size[d])
    print("  K1 confirms %d of the 159 prologue-only pairs (engine-shaped %d); the largest 12 (our addr, "
          "demo/our size, accesses, pass, name):" % (len(conf), sum(1 for d in conf if gsm.is_engine(dname[d]))))
    for d in conf[:12]:
        o = t7_d2o[d]
        print("    0x%08x %5d/%5d %3d acc %-11s %s" % (o, demo.size[d], ours.size[o], len(demo.key[d][0]),
                                                       how_of_d[d], dname[d]))
    r7b = "game/demo_symbol_renames_7b.csv"
    if os.path.exists(r7b):
        rows7b = [r for r in csv.DictReader(l for l in open(r7b) if not l.startswith("#"))]
        verdict = collections.Counter()
        for r in rows7b:
            d, o = int(r["DemoAddr"], 16), int(r["Address"], 16)
            up = image_pairs[0].get(d)
            rev = [dd for dd, oo in image_pairs[0].items() if oo == o]
            verdict["agree" if up == o else ("contradict" if up is not None or rev else "silent")] += 1
        print("  %s (%d rows) against K1: %s" % (r7b, len(rows7b), ", ".join("%s %d" % kv for kv in sorted(verdict.items()))))

    # [2b] link order as an independent check on the pairs -------------------------------------
    regions0 = sorted((v, v + len(dd)) for v, dd in ours.side.image.segments)
    ref987 = [(d, o) for d, o, _h in anchors]
    print("\n[2b] link order as an independent check (the two nearest reference pairs by our address, "
          "per PT_LOAD): bracket = demo address strictly between theirs; near = within %d KB of one, "
          "on its side" % (NEAR // 1024))
    base = {}
    for label, sel in (("828 PROVED", lambda h: not h.startswith("prefix")),
                       ("159 prologue", lambda h: h.startswith("prefix"))):
        sub = [(d, o) for d, o, h in anchors if sel(h)]
        c, _b = order_check(sub, ref987, regions0)
        base[label] = c
        print("  truth, ref = the other 986, %-13s bracket %4d/%4d (%.1f%%, null %.1f%%)  near %4d/%4d "
              "(%.1f%%, null %.1f%%)  edge %d"
              % (label, c["bracket yes"], c["bracket yes"] + c["bracket no"], 100 * rate(c, "bracket"),
                 100 * null_rate(sub, ref987, regions0, "bracket"),
                 c["near yes"], c["near yes"] + c["near no"], 100 * rate(c, "near"),
                 100 * null_rate(sub, ref987, regions0, "near"), c["edge"]))
    p_true = {t: rate(base["159 prologue"], t) for t in ("bracket", "near")}
    print("  (est. false below: p_obs = (1-f) p_true + f p_null, p_true = the 159 prologue pairs' rate "
          "-- the edited-routine population the new pairs are drawn from)")
    for ki, kn in enumerate(KEYS):
        new = [(d, o) for d, o in image_pairs[ki].items()
               if d not in t7_d2o and o not in t7_o2d and ratio(demo.size[d], ours.size[o]) >= RATIO]
        groups = [("alone", new)]
        for how in ("+prologue", "+callees"):
            groups.append((how, sorted(tightened(dict(new), how, demo, ours, t7_d2o).items())))
        for lo_a, hi_a in ((3, 5), (6, 10), (11, 20), (21, 10 ** 6)):
            groups.append(("acc %d-%s" % (lo_a, hi_a if hi_a < 10 ** 6 else "up"),
                           [(d, o) for d, o in new if lo_a <= len(demo.key[d][ki]) <= hi_a]))
        print("  %s:" % kn)
        for refname, ref in (("ref 987", ref987), ("ref 987+new", ref987 + list(new))):
            for label, sub in groups:
                if refname != "ref 987" and label != "alone" and not label.startswith("acc"):
                    continue
                c, _bad = order_check(sub, ref, regions0)
                line = []
                for t in ("bracket", "near"):
                    nd = c[t + " yes"] + c[t + " no"]
                    pn = null_rate(sub, ref, regions0, t)
                    est = false_estimate(rate(c, t), p_true[t], pn, nd)
                    line.append("%s %3d/%3d (%.1f%%, null %.1f%%, est. false %.0f)"
                                % (t, c[t + " yes"], nd, 100 * rate(c, t), 100 * pn, est))
                print("    %-11s %-10s n %4d  %s" % (refname, label, len(sub), "  ".join(line)))
        if ki == 0:
            c, bad = order_check(sorted(new), ref987 + list(new), regions0)
            print("    %s new pairs NOT near a reference (ref 987+new), all (our addr, demo addr, sizes, "
                  "accesses, prologue, callees, name):" % kn)
            for d, o in sorted(bad, key=lambda p: -demo.size[p[0]]):
                print("      0x%08x demo 0x%08x %5d/%5d %3d acc pro %-3s cal %-3s %s"
                      % (o, d, demo.size[d], ours.size[o], len(demo.key[d][ki]),
                         "yes" if demo.prologue(d) is not None and demo.prologue(d) == ours.prologue(o) else "no",
                         "yes" if callees_agree(d, o, demo, ours, t7_d2o) else "no", dname[d][:90]))

    # [3] holdout --------------------------------------------------------------------------
    print("\n[3] holdout over the %d PROVED pairs (research/45 sec 3: 3 folds; the 159 prologue pairs "
          "stay anchors); re-derived = a pair touching a held-out function; wrong = not Task 7's pair"
          % len(proved))
    pp = sorted((o, d) for d, o, _h in anchors)
    truth_o = {o: d for o, d in pp}
    truth_d = {d: o for o, d in pp}
    elig = [i for i, (_o, d) in enumerate(pp) if d in proved]
    all_d, all_o = set(demo.key), set(ours.key)
    results = {}
    for block in (8, 1):
        for scope in ("image-wide", "pool"):
            for ki, kn in enumerate(KEYS):
                for how in ("", "+prologue", "+callees"):
                    got = bad = 0
                    for phase in range(3):
                        hold_i = {elig[j] for j in range(len(elig)) if (j // block) % 3 == phase}
                        held_o = {pp[i][0] for i in hold_i}
                        held_d = {pp[i][1] for i in hold_i}
                        kept = {pp[i][1]: pp[i][0] for i in range(len(pp)) if i not in hold_i}
                        if scope == "image-wide":
                            pairs = image_pairs[ki]
                        else:
                            pairs = unique_pairs(ki, demo, ours, all_d - set(kept),
                                                 all_o - set(kept.values()))
                        pairs = tightened(pairs, how, demo, ours, kept)
                        for d, o in pairs.items():
                            if d in held_d or o in held_o:
                                got += 1
                                bad += int(truth_d.get(d) != o or truth_o.get(o) != d)
                    results[(block, scope, ki, how)] = (got, bad)
            print("  block %d, uniqueness %s:" % (block, scope))
            for ki, kn in enumerate(KEYS):
                print("    %-10s " % kn + "   ".join(
                    "%-9s %4d re-derived %2d wrong" % (how or "alone", *results[(block, scope, ki, how)])
                    for how in ("", "+prologue", "+callees")))

    # the production-shaped pass: uniqueness among what the 987 leave, all 987 as anchors
    print("\n  the pass as it would run (all 987 as anchors; pool = functions they leave):")
    prod = {}
    for ki, kn in enumerate(KEYS):
        pool_pairs = unique_pairs(ki, demo, ours, all_d - set(t7_d2o), all_o - set(t7_o2d))
        for how in ("", "+prologue", "+callees"):
            p = tightened(pool_pairs, how, demo, ours, t7_d2o)
            pr = {d: o for d, o in p.items() if ratio(demo.size[d], ours.size[o]) >= RATIO}
            prod[(ki, how)] = pr
            print("    %-10s %-9s pairs %4d, ratio >= %.2f %4d, of which engine-shaped %d"
                  % (kn, how or "alone", len(p), RATIO, len(pr),
                     sum(1 for d in pr if gsm.is_engine(dname[d]))))
    # image-wide pairs beyond the 987 under each tightening
    print("\n  image-wide pairs beyond the 987 (ratio >= %.2f) under each tightening:" % RATIO)
    for ki, kn in enumerate(KEYS):
        base = {d: o for d, o in image_pairs[ki].items()
                if d not in t7_d2o and o not in t7_o2d and ratio(demo.size[d], ours.size[o]) >= RATIO}
        print("    %-10s " % kn + ", ".join(
            "%s %d" % (how or "alone", len(tightened(base, how, demo, ours, t7_d2o)))
            for how in ("", "+prologue", "+callees")))

    # [3b] candidate rules, scored by link order (the holdout cannot tell them apart) -------------
    new1 = {d: o for d, o in image_pairs[0].items()
            if d not in t7_d2o and o not in t7_o2d and ratio(demo.size[d], ours.size[o]) >= RATIO}
    pro_ok = {d for d, o in new1.items() if demo.prologue(d) is not None and demo.prologue(d) == ours.prologue(o)}
    cal_ok = {d for d, o in new1.items() if callees_agree(d, o, demo, ours, t7_d2o)}
    nacc = {d: len(demo.key[d][0]) for d in new1}
    rules = [
        ("R1 K1, >=3 accesses", lambda d: True),
        ("R2 K1, >=6 accesses", lambda d: nacc[d] >= 6),
        ("R3 K1, >=11 accesses", lambda d: nacc[d] >= 11),
        ("R4 K1 + callees", lambda d: d in cal_ok),
        ("R5 K1 + prologue", lambda d: d in pro_ok),
        ("R6 K1 + (callees or prologue)", lambda d: d in cal_ok or d in pro_ok),
        ("R7 K1, >=11 acc, or callees/prologue", lambda d: nacc[d] >= 11 or d in cal_ok or d in pro_ok),
    ]
    print("\n[3b] candidate rules over the K1 image-wide pairs beyond the 987 (ratio >= %.2f), scored by "
          "link order (near test; p_true %.1f%% from the 159 prologue pairs)" % (RATIO, 100 * p_true["near"]))
    rule_sets = {}
    for label, pred in rules:
        sub = sorted((d, o) for d, o in new1.items() if pred(d))
        rule_sets[label] = sub
        eng = sum(1 for d, _o in sub if gsm.is_engine(dname[d]))
        parts = []
        for refname, ref in (("ref 987", ref987), ("ref 987+rule", ref987 + sub)):
            c, bad = order_check(sub, ref, regions0)
            nd = c["near yes"] + c["near no"]
            pn = null_rate(sub, ref, regions0, "near")
            parts.append("%s near %3d/%3d (%.1f%%, null %.1f%%, est. false %.1f)"
                         % (refname, c["near yes"], nd, 100 * rate(c, "near"), 100 * pn,
                            false_estimate(rate(c, "near"), p_true["near"], pn, nd)))
        print("  %-38s pairs %4d (engine-shaped %3d)  %s" % (label, len(sub), eng, "  ".join(parts)))
    for label in ("R7 K1, >=11 acc, or callees/prologue",):
        sub = rule_sets[label]
        c, bad = order_check(sub, ref987 + sub, regions0)
        print("  %s: not near a reference (ref 987+rule), all:" % label)
        for d, o in sorted(bad, key=lambda p: -demo.size[p[0]]):
            print("      0x%08x demo 0x%08x %5d/%5d %3d acc pro %-3s cal %-3s %s"
                  % (o, d, demo.size[d], ours.size[o], nacc[d], "yes" if d in pro_ok else "no",
                     "yes" if d in cal_ok else "no", dname[d][:90]))

    # [4] where the new pairs land -------------------------------------------------------------
    regions = sorted((v, v + len(d)) for v, d in ours.side.image.segments)
    for ki in (1, 2):
        new = [(d, o) for d, o in image_pairs[ki].items()
               if d not in t7_d2o and o not in t7_o2d and ratio(demo.size[d], ours.size[o]) >= RATIO]
        print("\n[4] %s: %d new pairs; per PT_LOAD of ours: %s" % (KEYS[ki], len(new), ", ".join(
            "0x%06x %d" % (lo, sum(1 for _d, o in new if lo <= o < hi)) for lo, hi in regions)))
    for label, new in (("K1 R1 (all new, ratio >= 0.50)", sorted((d, o) for d, o in new1.items())),
                       ("K1 R7 (the recommended rule)", rule_sets["R7 K1, >=11 acc, or callees/prologue"])):
        print("\n[4] %s: %d new pairs, per PT_LOAD of ours:" % (label, len(new)))
        for lo, hi in regions:
            inside = [(d, o) for d, o in new if lo <= o < hi]
            eng = sum(1 for d, _o in inside if gsm.is_engine(dname[d]))
            print("    0x%06x-0x%06x %4d  (engine-shaped %d, not engine-shaped %d)"
                  % (lo, hi, len(inside), eng, len(inside) - eng))
        eng = [(d, o) for d, o in new if gsm.is_engine(dname[d])]
        cls = collections.Counter(readable_class(dname[d]) or "(free function)" for d, _o in eng)
        print("    engine-shaped %d, not engine-shaped %d; engine readable classes (%d distinct): %s"
              % (len(eng), len(new) - len(eng), len(cls),
                 ", ".join("%s %d" % kv for kv in cls.most_common(15))))
        print("    of these, prologue equal %d, callees agree %d, either %d, neither %d"
              % (sum(1 for d, _o in new if d in pro_ok), sum(1 for d, _o in new if d in cal_ok),
                 sum(1 for d, _o in new if d in pro_ok or d in cal_ok),
                 sum(1 for d, _o in new if not (d in pro_ok or d in cal_ok))))
        for title, sel in (("twelve largest", new), ("twelve largest engine-shaped", eng)):
            print("    %s (by demo size): our addr, demo/our size, accesses, prologue, callees, readable [name]" % title)
            for d, o in sorted(sel, key=lambda p: -demo.size[p[0]])[:12]:
                print("      0x%08x %5d/%5d %3d acc  pro %-3s cal %-3s %s  [%s]"
                      % (o, demo.size[d], ours.size[o], nacc[d], "yes" if d in pro_ok else "no",
                         "yes" if d in cal_ok else "no", readable(dname[d]), dname[d][:80]))

    # [5] the 126 positional leads ---------------------------------------------------------
    gaps = sl.anchor_gaps(anchors, sorted(ours.side.starts), sorted(demo.side.starts), regions,
                          set(t7_o2d), set(t7_d2o))
    leads = []
    for gap in gaps:
        for o, d in gap:
            if sl._tier(demo.side, d, ours.side, o) is None and gsm.is_engine(dname[d]):
                leads.append((o, d, gap))
    print("\n[5] research/45 sec 6 leads recomputed: %d gaps, %d engine-shaped untiered candidates"
          % (len(gaps), len(leads)))
    allcand = [(o, d) for gap in gaps for o, d in gap]
    agree = {ki: 0 for ki in range(3)}
    contra = {ki: [] for ki in range(3)}
    for o, d in allcand:
        for ki in range(3):
            up = image_pairs[ki].get(d)
            rev = [dd for dd, oo in image_pairs[ki].items() if oo == o]
            if up == o:
                agree[ki] += 1
            elif up is not None or rev:
                contra[ki].append((o, d, up, rev[0] if rev else None))
    print("  all %d positional candidates (any tier, any name) against the unique-both-ways keys:" % len(allcand))
    gap_of = {o: gap for gap in gaps for o, _d in gap}
    for gap in {id(gap_of[o]): gap_of[o] for ki in range(3) for o, _d, _u, _r in contra[ki]}.values():
        print("    a gap holding contradictions: %d functions, ours 0x%08x-0x%08x, demo 0x%08x-0x%08x; "
              "first demo names: %s" % (len(gap), gap[0][0], gap[-1][0], gap[0][1], gap[-1][1],
                                        ", ".join(dname[d] for _o, d in gap[:4])))
    for ki in range(3):
        print("    %-10s agrees %d, contradicts %d" % (KEYS[ki], agree[ki], len(contra[ki])))
        for o, d, up, rd in contra[ki]:
            if up:
                print("      %-34s demo %5d B %3d acc: position -> ours 0x%08x %5d B %3d acc; key -> ours "
                      "0x%08x %5d B %3d acc" % (dname[d][:34], demo.size[d], len(demo.key[d][0]), o, ours.size[o],
                                                len(ours.key[o][0]), up, ours.size[up], len(ours.key[up][0])))
            else:
                print("      %-34s position -> ours 0x%08x, whose key belongs to demo %s"
                      % (dname[d][:34], o, dname[rd][:40]))
    # inverted index over our K1 keys for an image-wide Jaccard rank
    k1_ours = {s: collections.Counter(k[0]) for s, k in ours.key.items()}
    k1_demo = {s: collections.Counter(k[0]) for s, k in demo.key.items()}
    tally = collections.Counter()
    rows = []
    for o, d, gap in leads:
        if d not in demo.key or o not in ours.key:
            tally["no bytes"] += 1
            continue
        kd, ko = demo.key[d], ours.key[o]
        verdict = []
        for ki in range(3):
            if kd[ki] == ko[ki] and len(kd[ki]) >= MIN_ACC:
                verdict.append("equal")
            else:
                verdict.append("-")
            up = image_pairs[ki].get(d)
            if up is not None:
                tally["%s unique pairing %s" % (KEYS[ki], "agrees" if up == o else "contradicts")] += 1
                if up != o:
                    print("  %s CONTRADICTS lead 0x%08x %s: the key pairs it with ours 0x%08x (%d B, %s)"
                          % (KEYS[ki], o, dname[d], up, ours.size[up], oname[up]))
        tally["K1 key equal (>=3 acc)"] += verdict[0] == "equal"
        tally["K2 key equal (>=3 acc)"] += verdict[1] == "equal"
        tally["K3 key equal (>=3 acc)"] += verdict[2] == "equal"
        j = jaccard(kd[0], ko[0])
        sib = [jaccard(kd[0], ours.key[x][0]) for x, _dd in gap if x != o and x in ours.key]
        rank_gap = 1 + sum(1 for s in sib if s > j)
        cd = collections.Counter(kd[0])
        better = ties = 0
        for x, cx in k1_ours.items():
            if x == o:
                continue
            inter = sum((cd & cx).values())
            union = sum((cd | cx).values())
            if union and inter / union > j:
                better += 1
            elif union and inter / union == j:
                ties += 1
        rank_img = 1 + better
        tally["partner strictly 1st image-wide by K1 Jaccard (no tie)"] += (rank_img == 1 and ties == 0 and j > 0)
        co = collections.Counter(ko[0])
        rbetter = rties = 0
        if rank_img == 1 and ties == 0 and j > 0:
            for x, cx in k1_demo.items():
                if x == d:
                    continue
                inter = sum((co & cx).values())
                union = sum((co | cx).values())
                if union and inter / union > j:
                    rbetter += 1
                elif union and inter / union == j:
                    rties += 1
            mutual = rbetter == 0 and rties == 0
            tally["mutual strict best by K1 Jaccard (both images)"] += mutual
            tally["mutual strict best, J >= 0.5"] += mutual and j >= 0.5
        tally["partner ranks 1st in its gap by K1 Jaccard"] += (rank_gap == 1 and len(gap) > 1)
        tally["gap of more than one"] += len(gap) > 1
        tally["partner ranks 1st image-wide by K1 Jaccard"] += rank_img == 1
        tally["partner in image-wide top 10 by K1 Jaccard"] += rank_img <= 10
        rows.append((demo.size[d], o, ours.size[o], len(gap), len(kd[0]), len(ko[0]), j, rank_gap,
                     rank_img, verdict, dname[d]))
    for k in sorted(tally):
        print("  %-48s %d" % (k, tally[k]))
    js = sorted(r[6] for r in rows)
    if js:
        print("  K1 Jaccard of the positional partner: min %.2f, median %.2f, max %.2f; >= 0.5: %d; "
              "0: %d" % (js[0], js[len(js) // 2], js[-1], sum(1 for x in js if x >= 0.5),
                         sum(1 for x in js if x == 0)))
    print("  the twelve largest (research/45 sec 6's list) and ToQuat: our addr, demo/our size, gap, "
          "acc demo/ours, K1 Jaccard, rank in gap, rank image-wide, keys equal K1/K2/K3, name")
    shown = sorted(rows, key=lambda r: -r[0])[:12]
    shown += [r for r in rows if r[10].startswith("ToQuat__7CMatrix") and r not in shown]
    for r in shown:
        print("    0x%08x %5d/%5d gap %2d acc %3d/%3d J %.2f gap-rank %d image-rank %5d keys %s %s"
              % (r[1], r[0], r[2], r[3], r[4], r[5], r[6], r[7], r[8], "/".join(r[9]), r[10]))

    if args.csv:
        best = {d: o for d, o in rule_sets["R7 K1, >=11 acc, or callees/prologue"]}
        with open(args.csv, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["OurAddr", "Current", "DemoAddr", "DemoName", "Readable", "DemoSize", "OurSize",
                        "Accesses", "Engine"])
            for d, o in sorted(best.items(), key=lambda p: p[1]):
                w.writerow(["0x%08x" % o, oname[o], "0x%08x" % d, dname[d], readable(dname[d]),
                            demo.size[d], ours.size[o], len(demo.key[d][0]), int(gsm.is_engine(dname[d]))])
        # names, addresses and counts only -- no bytes (the brief's rule e)
        print("\nwrote", args.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
