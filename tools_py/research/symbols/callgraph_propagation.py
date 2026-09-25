"""Call-graph propagation from anchors: do callers and callees of placed pairs name the bodies between?

Sprint 12 research wave, question 7 (docs/research/52-callgraph-propagation.md). Read-only.

Run from the repo root:  python tools_py/research/symbols/callgraph_propagation.py [--holdout-folds 3]

Reads game/demo_scus_972_05/SCUS_972.05, game/disc/socom2_game.elf and recomp/socom2_ghidra.csv, and
re-derives Task 7's 987 pairs with `ghidra_symbol_match.match(prefix=True)` (the json on disk does not
carry demo addresses; the script checks the re-derived pairs against game/demo_symbol_matches.json).
Writes nothing. Prints, section by section:

  [1] both static call graphs (jal targets only): jal/jalr counts, where jal targets land, how many
      functions have zero static callers / zero callees on each side.
  [2] the keys: K_callee, K_caller, K_both for every unplaced function; how many are non-empty and
      how many are 'unique both ways' (image-wide census: exactly one demo function and exactly one
      of our functions in the WHOLE image wear the key, both unplaced).
  [3] yield beyond the 987 per key kind and per rule (raw; + body >= 64 B both sides; + size ratio
      >= 0.50; + |K| >= 2 / 3; the agree rule = the callee key AND the caller key each unique and
      naming the same pair).
  [4] the false-pair rate: research/45 sec 3's holdout over the 828 PROVED pairs (3 folds, blocks of
      8 and of 1), per key kind and rule: re-derived / wrong.
  [5] iteration to a fixed point for the zero-error rules, per round, plus the same iterated rule
      under the holdout.
  [6] research/45's 528 positional candidates (501 with no body evidence) against the call-graph
      pairs: confirmed / contradicted / silent, every contradiction by name with the toml's name for
      both rows and which side the size ratio favours.
  [7] independent checks on the real run, where the holdout cannot reach: recomp/socom2.toml's 656
      hand names, our 113 hand-named csv rows, and the link-order bracket (is our address between the
      our-images of the demo-order neighbouring anchors?) against its baseline on the 828.
  [8] research/53's string-set key (imported from string_correlator.py beside this file) against the
      call-graph pairs: agree / clash / silent, each clash by name with its K_callee.
  [9] the ORDERED rule (the union, iterated, a pair the link-order bracket calls 'outside' dropped):
      yield per round, iterated holdout, strings and toml checks, the identifier hurdles, and
      research/45's candidates again. This is the note's recommendation.

About two minutes. The union rule's name in the output is "callee|caller K>=2|both K>=3".

Names, addresses and counts only; no bytes are printed.
"""
import argparse
import bisect
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py import address_matcher as am  # noqa: E402
from tools_py import ghidra_symbol_match as gsm  # noqa: E402
from tools_py import symbol_levers as sl  # noqa: E402

DEMO = "game/demo_scus_972_05/SCUS_972.05"
OUR_ELF = "game/disc/socom2_game.elf"
OUR_CSV = "recomp/socom2_ghidra.csv"
MATCHES = "game/demo_symbol_matches.json"
TOML = "recomp/socom2.toml"
MIN_BODY = sl.MIN_BODY          # 64, note 44 hurdle 2
SIZE_RATIO = sl.SIZE_RATIO      # 0.50, research/45 tier B
KINDS = ("callee", "caller", "both")
JALR_FUNCT = 0x09


# ---- [1] the call graphs -------------------------------------------------------------------

class Graph:
    """Static call graph of one Side: jal targets that are function starts in the table."""

    def __init__(self, side: am.Side):
        self.side = side
        self.live = sorted(s for s in side.starts if side.fp[s] is not None)
        starts = side.starts
        self.callees = {s: set() for s in self.live}
        self.callers = {s: set() for s in self.live}
        self.stats = collections.Counter()
        ordered = sorted(starts)
        for s in self.live:
            body = side.body[s]
            for i in range(0, len(body) - 3, 4):
                w = int.from_bytes(body[i:i + 4], "little")
                if (w >> 26) == 0 and (w & 0x3F) == JALR_FUNCT:
                    self.stats["jalr"] += 1
            for t in side.calls[s]:
                self.stats["jal"] += 1
                if t in starts:
                    self.stats["jal to a function start"] += 1
                    if t in self.callers:
                        self.callees[s].add(t)
                        self.callers[t].add(s)
                else:
                    j = bisect.bisect_right(ordered, t) - 1
                    if j >= 0 and t < ordered[j] + side.size.get(ordered[j], 0):
                        self.stats["jal into a function body (not its start)"] += 1
                    else:
                        self.stats["jal outside every table row"] += 1

    def census(self, subset=None):
        pop = self.live if subset is None else [s for s in self.live if s in subset]
        return {"functions": len(pop),
                "zero static callers": sum(1 for s in pop if not self.callers[s]),
                "zero callees": sum(1 for s in pop if not self.callees[s]),
                "zero both (isolated)": sum(1 for s in pop if not self.callers[s] and not self.callees[s])}


# ---- [2] the keys ----------------------------------------------------------------------------

def make_keys(dg: Graph, og: Graph, anchors):
    """{kind: (demo {addr: key}, ours {addr: key})} over EVERY live function, keys in demo addresses."""
    d_set = {d for d, _o in anchors}
    o2d = {o: d for d, o in anchors}
    out = {}
    kd_ce = {s: frozenset(t for t in dg.callees[s] if t in d_set) for s in dg.live}
    ko_ce = {s: frozenset(o2d[t] for t in og.callees[s] if t in o2d) for s in og.live}
    kd_cr = {s: frozenset(c for c in dg.callers[s] if c in d_set) for s in dg.live}
    ko_cr = {s: frozenset(o2d[c] for c in og.callers[s] if c in o2d) for s in og.live}
    out["callee"] = (kd_ce, ko_ce)
    out["caller"] = (kd_cr, ko_cr)
    out["both"] = ({s: (kd_cr[s], kd_ce[s]) for s in dg.live}, {s: (ko_cr[s], ko_ce[s]) for s in og.live})
    return out


def ksize(kind, key) -> int:
    return len(key[0]) + len(key[1]) if kind == "both" else len(key)


def unique_pairs(kind, kd, ko, un_d, un_o, scope="image"):
    """{demo addr: our addr} -- keys worn by exactly one function on each side, both unplaced.

    scope "image": the census counts every live function (anchors too) -- research/45's bar.
    scope "unplaced": the census counts unplaced functions only -- the looser reading, for contrast.
    """
    cd, co = collections.defaultdict(list), collections.defaultdict(list)
    for s, k in kd.items():
        if ksize(kind, k) and (scope == "image" or s in un_d):
            cd[k].append(s)
    for s, k in ko.items():
        if ksize(kind, k) and (scope == "image" or s in un_o):
            co[k].append(s)
    out = {}
    for k, ds in cd.items():
        os_ = co.get(k)
        if len(ds) == 1 and os_ is not None and len(os_) == 1 and ds[0] in un_d and os_[0] in un_o:
            out[ds[0]] = (os_[0], ksize(kind, k))
    return out


def ratio(a, b):
    return min(a, b) / max(a, b) if max(a, b) else 0.0


RULES = ("raw", "+body64", "+body64+ratio", "+body64+ratio+K>=2", "+body64+ratio+K>=3")


def rule_ok(rule, demo, ours, d, o, k):
    if rule == "raw":
        return True
    ds, os_ = demo.size.get(d, 0), ours.size.get(o, 0)
    if ds < MIN_BODY or os_ < MIN_BODY:
        return False
    if rule == "+body64":
        return True
    if ratio(ds, os_) < SIZE_RATIO:
        return False
    if rule == "+body64+ratio":
        return True
    return k >= (2 if rule.endswith("K>=2") else 3)


def derive(keys, demo, ours, un_d, un_o, scope="image"):
    """{(kind, rule): {d: o}} including the 'agree' kind (callee-unique AND caller-unique, same pair)."""
    raw = {kind: unique_pairs(kind, keys[kind][0], keys[kind][1], un_d, un_o, scope) for kind in KINDS}
    out = {}
    for kind in KINDS:
        for rule in RULES:
            out[(kind, rule)] = {d: o for d, (o, k) in raw[kind].items() if rule_ok(rule, demo, ours, d, o, k)}
    ce, cr = raw["callee"], raw["caller"]
    agree = {d: (ce[d][0], ce[d][1] + cr[d][1]) for d in ce if d in cr and cr[d][0] == ce[d][0]}
    for rule in RULES:
        out[("agree", rule)] = {d: o for d, (o, k) in agree.items() if rule_ok(rule, demo, ours, d, o, k)}
    out[UNION] = merge([out[kr] for kr in UNION_PARTS])
    return out


def merge(parts):
    """The union of several {d: o} maps; any demo or our function claimed two ways is dropped whole."""
    by_d, by_o = collections.defaultdict(set), collections.defaultdict(set)
    for part in parts:
        for d, o in part.items():
            by_d[d].add(o)
            by_o[o].add(d)
    return {d: next(iter(os_)) for d, os_ in by_d.items()
            if len(os_) == 1 and len(by_o[next(iter(os_))]) == 1}


ALL_KINDS = KINDS + ("agree",)
# The union of the three rules that are at 0 wrong in both holdouts at their loosest (section [4]).
UNION_PARTS = (("callee", "+body64+ratio"), ("caller", "+body64+ratio+K>=2"), ("both", "+body64+ratio+K>=3"))
UNION = ("union", "callee|caller K>=2|both K>=3")


# ---- [4] the holdout -------------------------------------------------------------------------

def holdout_folds(pairs987, proved, folds, block):
    """Yield (kept anchors [(d, o)], held [(o, d)]) exactly as symbol_levers.holdout splits them."""
    pp = sorted((o, d) for d, o in pairs987)
    eligible = [i for i, (_o, d) in enumerate(pp) if d in proved]
    for phase in range(folds):
        hold_i = {eligible[j] for j in range(len(eligible)) if (j // block) % folds == phase}
        held = [pp[i] for i in sorted(hold_i)]
        keep = [(d, o) for i, (o, d) in enumerate(pp) if i not in hold_i]
        yield keep, held


def score(derived, held):
    """(re-derived, wrong): pairs that touch a held-out function on EITHER side, checked against truth."""
    truth_o = {o: d for o, d in held}
    truth_d = {d: o for o, d in held}
    got = bad = 0
    for d, o in derived.items():
        if d in truth_d or o in truth_o:
            got += 1
            bad += int(truth_d.get(d) != o)
    return got, bad


def iterate(dg, og, demo, ours, anchors, live_d, live_o, kind, rule, max_rounds=20, regions=None):
    """[new pairs per round] until nothing new: each round's pairs join the anchors.

    With `regions`, a pair whose link-order bracket (section [7]'s `Bracket`, over the anchors of
    that round) says `outside` is dropped: the ORDERED rule of section [9].
    """
    anchors = list(anchors)
    rounds = []
    for _ in range(max_rounds):
        placed_d = {d for d, _o in anchors}
        placed_o = {o for _d, o in anchors}
        un_d, un_o = live_d - placed_d, live_o - placed_o
        keys = make_keys(dg, og, anchors)
        new = derive(keys, demo, ours, un_d, un_o)[(kind, rule)]
        if regions is not None:
            br = Bracket(anchors, regions, live_o)
            new = {d: o for d, o in new.items() if order_verdict(br, d, o) != "outside"}
        if not new:
            break
        rounds.append(dict(new))
        anchors += list(new.items())
    return rounds


# ---- [7] independent checks on the real run ----------------------------------------------------

def toml_names(path=TOML):
    """{our addr: name} from recomp/socom2.toml's stub list ("name@0xADDR"); an address named twice
    keeps every name it carries."""
    out = collections.defaultdict(set)
    if os.path.exists(path):
        for n, a in re.findall(r'"([^"@]+)@0x([0-9A-Fa-f]+)"', open(path).read()):
            out[int(a, 16)].add(n)
    return out


def toml_check(pairs, demo, tn):
    """(our addr the toml names, of those the toml's name is the demo's, the disagreements)."""
    named = [(d, o) for d, o in pairs.items() if o in tn]
    same = [(d, o) for d, o in named if demo.name[d] in tn[o]]
    return len(named), len(same), [(d, o) for d, o in named if demo.name[d] not in tn[o]]


class Bracket:
    """Link-order check: is our address between the our-images of the demo-order neighbours?"""

    def __init__(self, anchors, regions, our_live):
        self.rows = sorted(anchors)                  # (d, o) by demo address
        self.ds = [d for d, _o in self.rows]
        self.regions = regions
        self.our_live = sorted(our_live)

    def region(self, o):
        for lo, hi in self.regions:
            if lo <= o < hi:
                return lo
        return None

    def check(self, d, o, skip=None):
        """(consistent, chance): chance = share of our region's functions inside the bracket."""
        i = bisect.bisect_left(self.ds, d)
        prev = [r for r in self.rows[max(0, i - 12):i] if r[0] != skip]
        nxt = [r for r in self.rows[i:i + 12] if r[0] != skip and r[0] != d]
        reg = self.region(o)
        prev = [r for r in prev if self.region(r[1]) == reg]
        nxt = [r for r in nxt if self.region(r[1]) == reg]
        if not prev or not nxt:
            return None
        lo_o, hi_o = prev[-1][1], nxt[0][1]
        lo_r = [r for r in self.regions if r[0] == reg][0]
        inside = bisect.bisect_left(self.our_live, max(lo_o, hi_o)) - bisect.bisect_right(self.our_live, min(lo_o, hi_o))
        total = bisect.bisect_left(self.our_live, lo_r[1]) - bisect.bisect_left(self.our_live, lo_r[0])
        return (lo_o < o < hi_o), (inside / total if total and lo_o < hi_o else 0.0)


def order_verdict(br, d, o):
    """'between', 'outside', or 'unknown' (no same-region demo-order neighbour on one side)."""
    got = br.check(d, o)
    return "unknown" if got is None else ("between" if got[0] else "outside")


def bracket_rate(br, pairs, skip_self=False):
    ok = n = 0
    chance = 0.0
    for d, o in pairs.items():
        got = br.check(d, o, skip=d if skip_self else None)
        if got is None:
            continue
        n += 1
        ok += int(got[0])
        chance += got[1]
    return ok, n, (chance / n if n else 0.0)


def hw_addrs(side, addr):
    """The hardware-register addresses (0x1000_0000..0x1200_FFFF) a body forms -- addresses, not bytes."""
    return sorted({a for a in am.formed_addresses(side.body.get(addr, b"")) if 0x10000000 <= a < 0x12010000})


# ---- main ------------------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--holdout-folds", type=int, default=3)
    args = ap.parse_args(argv)
    for p in (DEMO, OUR_ELF, OUR_CSV):
        if not os.path.exists(p):
            print("NO-DATA: missing %s" % p)
            return 2

    demo_rows, demo_segs = gsm.load_demo(DEMO)
    our_rows, our_segs = gsm.load_ours(OUR_ELF, OUR_CSV)
    details = {}
    gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details, prefix=True)
    anchors3 = sl.anchors_from_details(details)
    proved = sl.proved_anchors(anchors3)
    pairs987 = [(d, o) for d, o, _h in anchors3]
    how_of = {d: h for d, _o, h in anchors3}
    print("anchors: %d Task 7 pairs (%s); proved %d"
          % (len(anchors3), ", ".join("%s %d" % kv for kv in sorted(sl.anchor_composition(anchors3).items())),
             len(proved)))
    if os.path.exists(MATCHES):
        on_disk = {(p["name"], int(p["addr"], 16)) for p in json.load(open(MATCHES))["pairs"]}
        print("  agree with %s: %d of %d" % (MATCHES, len(on_disk & set(details)), len(on_disk)))

    demo = am.Side(demo_rows, demo_segs)
    ours = am.Side(our_rows, our_segs)
    dg, og = Graph(demo), Graph(ours)
    live_d, live_o = set(dg.live), set(og.live)
    placed_d = {d for d, _o in pairs987}
    placed_o = {o for _d, o in pairs987}
    un_d, un_o = live_d - placed_d, live_o - placed_o
    anon = {s for s in og.live if gsm.is_anonymous(ours.name[s])}
    regions = [(v, v + len(dd)) for v, dd in ours.image.segments]

    print("\n[1] call graphs (jal only; a jalr through a register is invisible)")
    for label, g in (("demo", dg), ("ours", og)):
        print("  %s: %s" % (label, ", ".join("%s %d" % kv for kv in sorted(g.stats.items()))))
        print("  %s all live:  %s" % (label, ", ".join("%s %d" % kv for kv in g.census().items())))
        sub = un_d if g is dg else un_o
        print("  %s unplaced:  %s" % (label, ", ".join("%s %d" % kv for kv in g.census(sub).items())))
    print("  our unplaced rows still FUN_/thunk_FUN_: %d (of %d unplaced)" % (len(un_o & anon), len(un_o)))

    keys = make_keys(dg, og, pairs987)
    print("\n[2] keys over the unplaced (987 anchors)")
    for kind in KINDS:
        kd, ko = keys[kind]
        ne_d = sum(1 for s in un_d if ksize(kind, kd[s]))
        ne_o = sum(1 for s in un_o if ksize(kind, ko[s]))
        img = unique_pairs(kind, kd, ko, un_d, un_o, "image")
        loose = unique_pairs(kind, kd, ko, un_d, un_o, "unplaced")
        print("  K_%-6s non-empty: demo %d of %d, ours %d of %d; unique both ways: image-wide %d pairs, "
              "unplaced-only census %d pairs" % (kind, ne_d, len(un_d), ne_o, len(un_o), len(img), len(loose)))

    real = derive(keys, demo, ours, un_d, un_o)
    print("\n[3] yield beyond the 987 (image-wide uniqueness; 'our FUN_' = our row still anonymous)")
    for kind in ALL_KINDS:
        for rule in RULES:
            got = real[(kind, rule)]
            print("  %-6s %-22s %5d pairs, our FUN_ %d" % (kind, rule, len(got),
                                                         sum(1 for o in got.values() if o in anon)))
    got = real[UNION]
    print("  %-6s %-22s %5d pairs, our FUN_ %d" % (UNION[0], UNION[1], len(got),
                                                 sum(1 for o in got.values() if o in anon)))
    ce, cr, bo = real[("callee", "raw")], real[("caller", "raw")], real[("both", "raw")]
    print("  overlap (raw): caller pairs not in callee %d; both pairs in neither callee nor caller %d; "
          "callee vs caller name a demo function two ways %d"
          % (len(set(cr) - set(ce)), len(set(bo) - set(ce) - set(cr)),
             sum(1 for d in set(ce) & set(cr) if ce[d] != cr[d])))
    for kr in UNION_PARTS:
        others = set()
        for kr2 in UNION_PARTS:
            if kr2 != kr:
                others |= set(real[kr2])
        print("  in the union, only %s %s: %d" % (kr[0], kr[1], len(set(real[kr]) - others)))

    report = [(k, r) for k in ALL_KINDS for r in RULES] + [UNION]
    print("\n[4] holdout over the %d proved pairs (research/45 sec 3; a pair counts when either side "
          "is held out; wrong = not Task 7's answer)" % len(proved))
    hold_tbl, wrongs = {}, {}
    for block in (8, 1):
        tally = collections.defaultdict(lambda: [0, 0])
        for keep, held in holdout_folds(pairs987, proved, args.holdout_folds, block):
            kp_d = {d for d, _o in keep}
            kp_o = {o for _d, o in keep}
            der = derive(make_keys(dg, og, keep), demo, ours, live_d - kp_d, live_o - kp_o)
            truth_d = {d: o for o, d in held}
            truth_o = {o: d for o, d in held}
            for key in report:
                g, b = score(der[key], held)
                tally[key][0] += g
                tally[key][1] += b
                for d, o in der[key].items():
                    if (d in truth_d or o in truth_o) and truth_d.get(d) != o:
                        wrongs.setdefault((d, o), (truth_o.get(o), truth_d.get(d), set()))[2].add((block, key[0]))
        hold_tbl[block] = tally
        print("  folds %d, blocks of %d:" % (args.holdout_folds, block))
        for kind in ALL_KINDS:
            print("    %-6s " % kind + "; ".join("%s %d/%d wrong" % (rule, tally[(kind, rule)][0], tally[(kind, rule)][1])
                                                  for rule in RULES))
        print("    %-6s %s %d/%d wrong" % (UNION[0], UNION[1], tally[UNION][0], tally[UNION][1]))
    print("  every 'wrong' pair, with the hardware-register addresses each body forms:")
    for (d, o), (t_d, t_o, where) in sorted(wrongs.items()):
        print("    demo %s @0x%06x %s -> ours 0x%08x %s; Task 7 pairs our 0x%08x with %s (%s)%s; in %s"
              % (demo.name[d], d, [hex(a) for a in hw_addrs(demo, d)], o, [hex(a) for a in hw_addrs(ours, o)],
                 o, demo.name.get(t_d, "-") if t_d else "nothing held",
                 how_of.get(t_d, "-") if t_d else "-",
                 "" if t_o is None else "; Task 7 pairs this demo function with 0x%08x" % t_o,
                 ", ".join("block %d %s" % w for w in sorted(where))))
        if t_d:
            print("      Task 7's demo partner %s @0x%06x forms %s" % (demo.name[t_d], t_d,
                                                                  [hex(a) for a in hw_addrs(demo, t_d)]))
        print("      K_caller at the 987: demo {%s}; ours {%s}"
              % (", ".join(sorted(demo.name[x] for x in keys["caller"][0][d])),
                 ", ".join(sorted(demo.name[x] for x in keys["caller"][1][o]))))

    print("\n[5] iteration to a fixed point (each round's pairs join the anchors)")
    zero = [kr for kr in report
            if all(hold_tbl[b][kr][1] == 0 and hold_tbl[b][kr][0] > 0 for b in (8, 1))]
    print("  rules at 0 wrong in both holdouts: %s" % ", ".join("%s %s" % kr for kr in zero))
    iter_rules = [("callee", "+body64+ratio"), ("callee", "+body64+ratio+K>=2"),
                  ("caller", "+body64+ratio+K>=2"), ("both", "+body64+ratio+K>=3"),
                  ("agree", "+body64+ratio"), UNION]
    final = {}
    for kind, rule in iter_rules:
        rounds = iterate(dg, og, demo, ours, pairs987, live_d, live_o, kind, rule)
        allp = {}
        for r in rounds:
            allp.update(r)
        final[(kind, rule)] = allp
        print("  %-6s %-26s rounds %d, per round %s, total %d, our FUN_ %d"
              % (kind, rule, len(rounds), [len(r) for r in rounds], len(allp),
                 sum(1 for o in allp.values() if o in anon)))
        for block in (8, 1):
            g = b = 0
            per_round = collections.Counter()
            for keep, held in holdout_folds(pairs987, proved, args.holdout_folds, block):
                rr = iterate(dg, og, demo, ours, keep, live_d, live_o, kind, rule)
                for i, r in enumerate(rr):
                    gg, bb = score(r, held)
                    g, b = g + gg, b + bb
                    per_round[i + 1] += gg
            print("      iterated holdout, blocks of %d: %d re-derived, %d wrong; re-derived per round %s"
                  % (block, g, b, dict(sorted((k, v) for k, v in per_round.items() if v))))
    up = final[UNION]
    eng = sum(1 for d in up if gsm.is_engine(demo.name[d]))
    names = collections.Counter(demo.name[d] for d in up)
    t7names = {n for n, _a in details}
    print("  union at its fixed point: engine-shaped names %d, SDK/runtime/other %d; demo names on two "
          "of the union's pairs %d; names already carried by one of the 987 %d"
          % (eng, len(up) - eng, sum(1 for n, c in names.items() if c > 1),
             sum(1 for d in up if demo.name[d] in t7names)))
    for lo, hi in regions:
        print("    lands in 0x%06x-0x%06x: %d" % (lo, hi, sum(1 for o in up.values() if lo <= o < hi)))
    top = sorted(up.items(), key=lambda kv: -demo.size[kv[0]])[:15]
    print("  the union's 15 largest (demo size / our size):")
    for d, o in top:
        print("    0x%08x %5d/%5d  %s" % (o, demo.size[d], ours.size[o], demo.name[d]))

    print("\n[6] research/45's positional candidates against the call-graph pairs")
    gaps = sl.anchor_gaps(anchors3, sorted(ours.starts), sorted(demo.starts), regions, placed_o, placed_d)
    cands = [(o, d, sl._tier(demo, d, ours, o), len(gap)) for gap in gaps for o, d in gap]
    none = [(o, d) for o, d, t, _g in cands if t is None]
    tiered = [(o, d) for o, d, t, _g in cands if t is not None]
    gap_of = {(o, d): g for o, d, _t, g in cands}
    pos6, _c = sl.positional(demo_rows, demo_segs, our_rows, our_segs, anchors3, gsm.PREFIX_WORDS)
    six = [(c.our_addr, c.demo_addr) for c in pos6]
    print("  gaps %d, candidates %d, no body evidence %d, tiered %d, research/45 proposals %d"
          % (len(gaps), len(cands), len(none), len(tiered), len(six)))
    compare = [((k, "raw"), real[(k, "raw")]) for k in ALL_KINDS]
    compare += [(("%s iterated" % kr[0], kr[1]), p) for kr, p in final.items()]
    contras = {}
    for (kind, rule), got in compare:
        rev = {o: d for d, o in got.items()}
        for label, group in (("no-evidence", none), ("tiered", tiered), ("45's six", six)):
            conf = contra = silent = 0
            for o, d in group:
                if got.get(d) == o:
                    conf += 1
                elif (d in got and got[d] != o) or (o in rev and rev[o] != d):
                    contra += 1
                    contras.setdefault((o, d), set()).add("%s %s" % (kind, rule))
                else:
                    silent += 1
            print("  %-16s %-26s %-11s confirm %d, contradict %d, silent %d"
                  % (kind, rule, label, conf, contra, silent))
    tn = toml_names()
    print("  every contradiction (positional pair; the call-graph pair instead; the toml's name):")
    for (o, d), who in sorted(contras.items()):
        other_o = {p[d] for _kr, p in compare if d in p and p[d] != o}
        other_d = {dd for _kr, p in compare for dd, oo in p.items() if oo == o and dd != d}
        print("    positional %s @0x%06x -> 0x%08x (%d/%d B, gap %d); call graph puts it at %s, puts %s at 0x%08x; "
              "toml: 0x%08x=%s%s; by %s"
              % (demo.name[d], d, o, demo.size[d], ours.size[o], gap_of[(o, d)],
                 ", ".join("0x%08x (%d B)" % (x, ours.size[x]) for x in sorted(other_o)) or "-",
                 ", ".join(demo.name[x] for x in sorted(other_d)) or "nothing", o, o,
                 "/".join(sorted(tn.get(o, ()))) or "-",
                 "".join("; toml: 0x%08x=%s" % (x, "/".join(sorted(tn.get(x, ())) or ["-"])) for x in sorted(other_o)),
                 ", ".join(sorted(who))))
    better = collections.Counter()
    for (o, d), who in contras.items():
        for x in {p[d] for _kr, p in compare if d in p and p[d] != o}:
            rp, rc = ratio(demo.size[d], ours.size[o]), ratio(demo.size[d], ours.size[x])
            ruled = any("iterated" in w for w in who)
            better[("size ratio favours the call graph" if rc > rp else "size ratio favours position",
                    "a rule's pair" if ruled else "raw key only")] += 1
    print("  contradictions where the call graph names another our row for the demo function: "
          + ", ".join("%s (%s) %d" % (k[0], k[1], v) for k, v in sorted(better.items())))

    print("\n[7] independent checks on the real run (not the holdout)")
    n, same, diff = toml_check({d: o for d, o in pairs987}, demo, tn)
    print("  toml (recomp/socom2.toml, %d named addresses) vs Task 7's 987: named %d, same name %d, differ %d"
          % (len(tn), n, same, len(diff)))
    for d, o in diff:
        print("    differs: 0x%08x Task 7 %s (%s), toml %s" % (o, demo.name[d], how_of[d], "/".join(sorted(tn[o]))))
    br = Bracket(pairs987, regions, live_o)
    ok, m, ch = bracket_rate(br, {d: o for d, o in pairs987 if d in proved}, skip_self=True)
    print("  link-order bracket, baseline: the 828 proved pairs, each against the other anchors: %d of %d "
          "inside (%.1f%%); chance %.2f%%" % (ok, m, 100.0 * ok / m if m else 0, 100 * ch))
    for kr in [(k, "raw") for k in ALL_KINDS] + [("callee", "+body64+ratio"), ("caller", "+body64+ratio"),
                                                 ("both", "+body64+ratio"), UNION]:
        p = real[kr]
        n, same, diff = toml_check(p, demo, tn)
        ok, m, ch = bracket_rate(br, p)
        print("  %-6s %-26s pairs %4d; toml names %d: same %d, differ %d; bracket %d of %d inside "
              "(%.1f%%), chance %.2f%%" % (kr[0], kr[1], len(p), n, same, len(diff), ok, m,
                                          100.0 * ok / m if m else 0, 100 * ch))
    for kind in ("callee", "caller", "both"):
        hand = [(d, o) for d, o in real[(kind, "raw")].items() if o not in anon]
        same = [(d, o) for d, o in hand if demo.name[d] == ours.name[o]]
        diff = [(d, o) for d, o in hand if demo.name[d] != ours.name[o]]
        print("  %-6s raw on our hand-named rows: %d; same name %d; differ %d, of which raw bytes identical %d%s"
              % (kind, len(hand), len(same), len(diff), sum(1 for d, o in diff if demo.body[d] == ours.body[o]),
                 "".join("; 0x%08x ours %s / demo %s" % (o, ours.name[o], demo.name[d]) for d, o in diff)))
    rounds = iterate(dg, og, demo, ours, pairs987, live_d, live_o, *UNION)
    print("  union, bracket per round against the 987: " + "; ".join(
        "round %d %d/%d" % ((i + 1,) + bracket_rate(br, r)[:2]) for i, r in enumerate(rounds)))
    grown, parts = list(pairs987), []
    for i, r in enumerate(rounds):
        parts.append("round %d %d/%d" % ((i + 1,) + bracket_rate(Bracket(grown, regions, live_o), r)[:2]))
        grown += list(r.items())
    print("  union, bracket per round against the 987 + every earlier round: " + "; ".join(parts))
    ok, m, _ch = bracket_rate(Bracket(grown, regions, live_o), {d: o for d, o in pairs987 if d in proved},
                             skip_self=True)
    print("  the 828 proved pairs bracketed by the 987 + the union's %d: %d of %d inside (%.1f%%)"
          % (len(grown) - len(pairs987), ok, m, 100.0 * ok / m if m else 0))
    for kr, p in final.items():
        n, same, diff = toml_check(p, demo, tn)
        ok, m, ch = bracket_rate(br, p)
        print("  %-6s %-26s iterated, pairs %4d; toml names %d: same %d, differ %d; bracket %d of %d inside "
              "(%.1f%%), chance %.2f%%" % (kr[0], kr[1], len(p), n, same, len(diff), ok, m,
                                          100.0 * ok / m if m else 0, 100 * ch))
        for d, o in diff:
            print("    differs: 0x%08x call graph %s, toml %s" % (o, demo.name[d], "/".join(sorted(tn[o]))))

    print("\n[8] cross-check against research/53's string-set key (evidence that never reads a jal)")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import string_correlator as sc
    except ImportError:
        print("  NO-DATA: tools_py/research/symbols/string_correlator.py is not on disk")
        return 0
    refs_d = {a: sc.refs_of(demo, a) for a in live_d}
    refs_o = {a: sc.refs_of(ours, a) for a in live_o}
    shared = {x for v in refs_d.values() for x in v} & {x for v in refs_o.values() for x in v}
    kd, ko = sc.build_keys(demo, refs_d, shared), sc.build_keys(ours, refs_o, shared)
    strings = {d: o for d, o in sc.pair_unique(kd["set"], ko["set"], un_d, un_o).items()
               if sc.size_ok(demo, ours, d, o, True)}
    print("  string-set pairs over the unplaced, >= 64 B, ratio >= 0.50 (research/53's R0): %d" % len(strings))
    s_rev = {o: d for d, o in strings.items()}
    views = [(kr, real[kr]) for kr in [("callee", "+body64+ratio"), ("caller", "+body64+ratio"),
                                       ("both", "+body64+ratio"), UNION]]
    views += [(("%s iterated" % kr[0], kr[1]), p) for kr, p in final.items() if kr in (UNION,)]
    for (kind, rule), p in views:
        same = sum(1 for d, o in p.items() if strings.get(d) == o)
        clash = [(d, o) for d, o in p.items()
                 if (d in strings and strings[d] != o) or (o in s_rev and s_rev[o] != d)]
        print("  %-16s %-26s pairs %4d; also a string pair %d; clash %d; strings silent %d"
              % (kind, rule, len(p), same, len(clash), len(p) - same - len(clash)))
        for d, o in clash:
            print("    clash: call graph %s -> 0x%08x (%d/%d B); strings put it at %s, put %s there"
                  % (demo.name[d], o, demo.size[d], ours.size[o],
                     "0x%08x (%d B)" % (strings[d], ours.size[strings[d]]) if d in strings else "-",
                     demo.name[s_rev[o]] if o in s_rev else "nothing"))
    union = final[UNION]
    both_new = {d for d in union if d not in strings}
    print("  the union at its fixed point adds %d pairs research/53's R0 does not have; R0 has %d the union "
          "does not" % (len(both_new), sum(1 for d in strings if d not in union)))
    grown = list(pairs987)
    for i, r in enumerate(iterate(dg, og, demo, ours, pairs987, live_d, live_o, *UNION)):
        ks, b2 = make_keys(dg, og, grown), Bracket(grown, regions, live_o)
        for d, o in sorted(r.items()):
            if (d in strings and strings[d] != o) or (o in s_rev and s_rev[o] != d):
                print("    clash in round %d: %s K_callee {%s}, K_caller {%s}; link order %s"
                      % (i + 1, demo.name[d], ", ".join(sorted(demo.name[x] for x in ks["callee"][0][d])),
                         ", ".join(sorted(demo.name[x] for x in ks["caller"][0][d])), order_verdict(b2, d, o)))
        grown += list(r.items())

    print("\n[9] the ORDERED rule: the union, iterated, dropping any pair the link-order bracket (over "
          "that round's anchors) says is outside")
    for kind, rule in (UNION, ("callee", "+body64+ratio"), ("both", "+body64+ratio+K>=3"),
                       ("both", "+body64+ratio")):
        rr = iterate(dg, og, demo, ours, pairs987, live_d, live_o, kind, rule, regions=regions)
        allp = {}
        for r in rr:
            allp.update(r)
        hold = []
        for block in (8, 1):
            g = b = 0
            for keep, held in holdout_folds(pairs987, proved, args.holdout_folds, block):
                q = {}
                for r in iterate(dg, og, demo, ours, keep, live_d, live_o, kind, rule, regions=regions):
                    q.update(r)
                gg, bb = score(q, held)
                g, b = g + gg, b + bb
            hold.append("blocks of %d %d/%d wrong" % (block, g, b))
        same = sum(1 for d, o in allp.items() if strings.get(d) == o)
        clash = sum(1 for d, o in allp.items()
                    if (d in strings and strings[d] != o) or (o in s_rev and s_rev[o] != d))
        n, tsame, tdiff = toml_check(allp, demo, tn)
        tdiff_txt = "".join(" (0x%08x %s / toml %s)" % (o, demo.name[d], "/".join(sorted(tn[o]))) for d, o in tdiff)
        print("  %-6s %-26s ordered: rounds %d, per round %s, total %d; iterated holdout %s; strings "
              "agree %d, clash %d; toml names %d: same %d, differ %d%s"
              % (kind, rule, len(rr), [len(r) for r in rr], len(allp), "; ".join(hold), same, clash,
                 n, tsame, len(tdiff), tdiff_txt))
        if (kind, rule) != UNION:
            continue
        ordered = allp
        grown, verdicts = list(pairs987), collections.Counter()
        for i, r in enumerate(rr):
            b2 = Bracket(grown, regions, live_o)
            verdicts.update(("round 1" if i == 0 else "rounds 2+", order_verdict(b2, d, o)) for d, o in r.items())
            grown += list(r.items())
        print("    link-order verdicts of the kept pairs, each against its own round's anchors: %s"
              % ", ".join("%s %s %d" % (k[0], k[1], v) for k, v in sorted(verdicts.items())))
        r1 = rr[0]
        later = {d: o for r in rr[1:] for d, o in r.items()}
        for label, part in (("round 1", r1), ("rounds 2+", later)):
            n, tsame, tdiff = toml_check(part, demo, tn)
            print("    %-9s %4d pairs; strings agree %d; toml same %d of %d; engine-shaped %d"
                  % (label, len(part), sum(1 for d, o in part.items() if strings.get(d) == o), tsame, n,
                     sum(1 for d in part if gsm.is_engine(demo.name[d]))))
        eng = sum(1 for d in ordered if gsm.is_engine(demo.name[d]))
        print("    engine-shaped names %d, other %d; our FUN_ %d; hand-named rows 0 by construction: %d"
              % (eng, len(ordered) - eng, sum(1 for o in ordered.values() if o in anon),
                 sum(1 for o in ordered.values() if o not in anon)))
        for lo, hi in regions:
            print("    lands in 0x%06x-0x%06x: %d" % (lo, hi, sum(1 for o in ordered.values() if lo <= o < hi)))
        names = collections.Counter(demo.name[d] for d in ordered)
        idents = collections.Counter(gsm.c_identifier(demo.name[d]) for d in ordered)
        t7ids = {gsm.c_identifier(n) for n, _a in details}
        print("    demo names on two pairs %d (%s); identifiers colliding within the rule %d; identifiers "
              "colliding with the 987's %d; our rows the toml names %d"
              % (sum(1 for c in names.values() if c > 1),
                 ", ".join(n for n, c in names.items() if c > 1), sum(1 for c in idents.values() if c > 1),
                 sum(1 for d in ordered if gsm.c_identifier(demo.name[d]) in t7ids),
                 sum(1 for o in ordered.values() if o in tn)))
        rev = {o: d for d, o in ordered.items()}
        for label, group in (("no-evidence", none), ("tiered", tiered), ("45's six", six)):
            conf = sum(1 for o, d in group if ordered.get(d) == o)
            contra = sum(1 for o, d in group if ordered.get(d) not in (None, o) or rev.get(o) not in (None, d))
            print("    research/45 %-11s confirm %d, contradict %d, silent %d"
                  % (label, conf, contra, len(group) - conf - contra))
    return 0


if __name__ == "__main__":
    sys.exit(main())
