"""BinDiff's demo1 -> r0001 function matches, joined to Task 7's 987 pairs (Sprint 12, research note 49).

Run from the repo root:

    python tools_py/research/symbols/bindiff_join.py <result.BinDiff> \
        [--prefix-csv game/bindiff/prefix_verdicts.csv] [--compare <proposals.csv> ...]

<result.BinDiff> is the SQLite file `bindiff demo1.BinExport r0001.BinExport` writes (the demo PRIMARY,
r0001 SECONDARY); docs/research/49-bindiff-crosscheck.md §1 has the commands that make both exports.
Read-only: it also reads the demo ELF, our ELF, recomp/socom2_ghidra.csv, recomp/socom2.toml and
game/demo_symbol_matches.json, and the only file it writes is the optional --prefix-csv (keep it under
game/, which is git-ignored). It prints names, addresses, counts and similarity scores -- never a byte.

What it prints, one block per section of note 49:

  [inputs]    the BinDiff file's summary (functions, pairs by matcher, whole-image similarity) and the
              987 pairs re-derived with `ghidra_symbol_match.match(prefix=True)` -- the only source of
              each pair's DEMO address -- checked identical to game/demo_symbol_matches.json.
  [§2 join]   each of the 987, by Task 7 pass: AGREE (BinDiff pairs the same demo function with the
              same function of ours), DISAGREE (BinDiff pairs the demo function with another of ours,
              or ours with another demo function), ABSENT (BinDiff pairs neither side); NEW = BinDiff
              pairs with both sides outside the 987; similarity quantiles per bucket.
  [§3 rate]   the 828 PROVED pairs (symbol_levers.proved_anchors) as truth. BinDiff never sees the 987,
              so every proved pair is held out by construction (research/45 §3's method, one block).
              agree / contradict / absent; a raw sweep over every matcher; then THE RULE -- a STRUCTURAL
              matcher (STRUCTURAL below), both bodies >= 64 B, size ratio >= 0.50, similarity >= t --
              with t* = the first 0.05 step above the largest similarity a contradicting pair reaches
              under the rule, and the sweep: contradictions, agreements, NEW pairs at each t.
  [§3 toml]   the same rule against recomp/socom2.toml's name@addr stub list, a truth set outside the
              987: BinDiff pairs on a toml-named address carry the toml's name or another.
  [§4 prefix] the 159 prologue-only pairs: verdict, and under the rule at t* confirmed / contradicted /
              unconfirmed; the 20 largest by demo size. --prefix-csv writes all 159.
  [§5 new]    the NEW pairs by our PT_LOAD, engine vs SDK (the class path of a copy of
              readable_names.readable), the twelve largest; then the same under the rule at t*.
  [§6 ceiling] the 7,595 demo functions whose exact fingerprint is absent from our image (research/44
              §6): BinDiff pairs on them, at >= 0.7, NEW on a FUN_ row, and under the rule at t*.
  [§7 levers] with --compare: per proposals file, how many of its rows BinDiff pairs under the rule
              with the same demo function or another, and how many of the rule's NEW pairs no file has.
"""
import argparse
import collections
import csv
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py import address_matcher as am  # noqa: E402
from tools_py import ghidra_symbol_match as gsm  # noqa: E402
from tools_py import symbol_levers as sl  # noqa: E402
from tools_py.elf_symbols import read_elf  # noqa: E402

DEMO = "game/demo_scus_972_05/SCUS_972.05"
OURS = "game/disc/socom2_game.elf"
CSV = "recomp/socom2_ghidra.csv"
MATCHES = "game/demo_symbol_matches.json"
TOML = "recomp/socom2.toml"
CUTS = (0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99, 1.0)
# BinDiff's matchers that compare a function's OWN flow graph (or its bytes). The others -- address
# sequence, call sequence, call reference, call-graph MD index, instruction count, string references,
# loop count -- place a function by its neighbours or by one scalar, which is position, not evidence
# about the body; research/45 already has a position pass with its own rule.
STRUCTURAL = frozenset((
    "function: hash matching",
    "function: edges flowgraph MD index",
    "function: MD index matching (flowgraph MD index, top down)",
    "function: MD index matching (flowgraph MD index, bottom up)",
    "function: prime signature matching",
    "function: relaxed MD index matching",
))
MIN_BODY = 64      # research/44 §2 hurdle 2
MIN_RATIO = 0.50   # research/45 §2 tier B


# ---- a copy of tools_py/research/symbols/readable_names.readable, returning the class path too ---------
_SPLIT = re.compile(r"^(.*?)__(?:Q\d|\d+)")
_SAFE = re.compile(r"[^A-Za-z0-9_]")


def class_path(mangled):
    """['zdb', 'CNode'] for a Metrowerks member, [] for a C / free function (readable()'s class parse)."""
    m = _SPLIT.match(mangled)
    if not m:
        return []
    rest = mangled[len(m.group(1)) + 2:]
    classes = []
    q = re.match(r"Q(\d)", rest)
    if q:
        pos = q.end()
        for _ in range(int(q.group(1))):
            n = re.match(r"(\d+)", rest[pos:])
            if not n:
                break
            pos += n.end()
            classes.append(rest[pos:pos + int(n.group(1))])
            pos += int(n.group(1))
    else:
        n = re.match(r"(\d+)", rest)
        if n:
            classes.append(rest[n.end():n.end() + int(n.group(1))])
    return [c for c in classes if c]


def readable(mangled):
    m = _SPLIT.match(mangled)
    if not m:
        return _SAFE.sub("_", mangled)
    fn = re.sub(r"<.*>", "", m.group(1))
    cls = class_path(mangled)
    return _SAFE.sub("_", "_".join(cls + [fn]) if cls else fn)


def kind(mangled):
    """engine-member (a class path), engine-free (a z*/hud* free function), sdk (everything else)."""
    if class_path(mangled):
        return "engine-member"
    if mangled.startswith(("z", "hud")):
        return "engine-free"
    return "sdk"


# ---- the BinDiff result ------------------------------------------------------------------------------
def load_bindiff(path):
    db = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    algo = dict(db.execute("SELECT id, name FROM functionalgorithm"))
    rows = db.execute("SELECT address1, address2, similarity, confidence, algorithm, name1, name2, "
                      "basicblocks, instructions FROM function").fetchall()
    meta = db.execute("SELECT similarity, confidence FROM metadata").fetchone()
    files = db.execute("SELECT filename, functions, libfunctions, basicblocks, instructions FROM file").fetchall()
    db.close()
    pairs = [dict(d=a1, o=a2, sim=s, conf=c, alg=algo.get(al, str(al)), name1=n1, name2=n2, bbs=bb, ins=ins)
             for a1, a2, s, c, al, n1, n2, bb, ins in rows]
    return pairs, meta, files


def is_hash_alg(alg):
    return "hash matching" in alg and "name" not in alg


def quantiles(xs):
    if not xs:
        return "n=0"
    xs = sorted(xs)
    q = lambda p: xs[min(len(xs) - 1, int(p * (len(xs) - 1) + 0.5))]  # noqa: E731
    return "n=%d min %.3f p10 %.3f p25 %.3f median %.3f p75 %.3f max %.3f" % (
        len(xs), xs[0], q(0.10), q(0.25), q(0.50), q(0.75), xs[-1])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bindiff", help="the .BinDiff SQLite result (demo primary, r0001 secondary)")
    ap.add_argument("--prefix-csv", help="write the 159 prefix verdicts here (under game/)")
    ap.add_argument("--compare", nargs="*", default=[],
                    help="other levers' proposal files (Address, Mangled[, DemoAddr] columns): [§7] counts, per file, "
                         "whether BinDiff's pair under the rule names the same demo function")
    args = ap.parse_args(argv)

    bd, meta, files = load_bindiff(args.bindiff)
    by_d = {p["d"]: p for p in bd}
    by_o = {p["o"]: p for p in bd}
    print("[inputs]")
    for f in files:
        print("  file %s: functions %d (library %d), basic blocks %d, instructions %d" % f)
    print("  BinDiff whole-image similarity %.4f, confidence %.4f" % meta)
    print("  matched function pairs %d; by algorithm:" % len(bd))
    for alg, n in collections.Counter(p["alg"] for p in bd).most_common():
        print("    %5d  %s" % (n, alg))

    demo_rows, demo_segs = gsm.load_demo(DEMO)
    our_rows, our_segs = gsm.load_ours(OURS, CSV)
    details = {}
    gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details, prefix=True)
    anchors = sl.anchors_from_details(details)
    proved = sl.proved_anchors(anchors)
    demo_size = {s: e - s for s, e, _n in demo_rows}
    demo_name = {s: n for s, e, n in demo_rows}
    name_count = collections.Counter(n for _s, _e, n in demo_rows)
    our_size = {s: e - s for s, e, _n in our_rows}
    our_name = {s: n for s, e, n in our_rows}
    with open(MATCHES) as fh:
        saved = {(p["name"], int(p["addr"], 16), p["how"]) for p in json.load(fh)["pairs"]}
    mine = {(n, o, info["how"]) for (n, o), info in details.items()}
    print("  Task 7 pairs re-derived %d (by pass %s); identical to %s: %s; proved %d" % (
        len(anchors), dict(sorted(collections.Counter(h for _d, _o, h in anchors).items())), MATCHES,
        mine == saved, len(proved)))

    placed_d = {d for d, _o, _h in anchors}
    placed_o = {o for _d, o, _h in anchors}

    def verdict(d, o):
        a, b = by_d.get(d), by_o.get(o)
        if a and a["o"] == o:
            return "agree", a
        against = [p for p in (a, b) if p is not None]
        if against:
            return "disagree", max(against, key=lambda p: p["sim"])
        return "absent", None

    def body_ok(p):
        ds, os_ = demo_size.get(p["d"], 0), our_size.get(p["o"], 0)
        return min(ds, os_) >= MIN_BODY and min(ds, os_) / max(ds, os_) >= MIN_RATIO

    def rule(p, t):
        """THE RULE this note measures: a structural matcher, both bodies >= 64 B, ratio >= 0.50, sim >= t."""
        return p is not None and p["alg"] in STRUCTURAL and body_ok(p) and p["sim"] >= t

    # ---- §2 -------------------------------------------------------------------------------------------
    print("\n[§2 join] the 987 by Task 7 pass: agree / disagree / absent")
    rows = []
    for d, o, how in anchors:
        v, p = verdict(d, o)
        rows.append(dict(d=d, o=o, how=how, v=v, p=p))
    passes = sorted({r["how"] for r in rows})
    print("  %-14s %5s %6s %9s %7s" % ("pass", "pairs", "agree", "disagree", "absent"))
    for how in passes + ["all"]:
        sub = [r for r in rows if how == "all" or r["how"] == how]
        c = collections.Counter(r["v"] for r in sub)
        print("  %-14s %5d %6d %9d %7d" % (how, len(sub), c["agree"], c["disagree"], c["absent"]))
    dis_kind = collections.Counter()
    for r in rows:
        if r["v"] == "disagree":
            a, b = by_d.get(r["d"]), by_o.get(r["o"])
            dis_kind["demo function paired elsewhere" if a and a["o"] != r["o"] else "our function paired with another demo function"] += 1
    print("  disagree, by side:", dict(dis_kind))
    for v in ("agree", "disagree"):
        for how in passes:
            print("  similarity, %-8s %-14s %s" % (v, how, quantiles([r["p"]["sim"] for r in rows if r["v"] == v and r["how"] == how])))
    new = [p for p in bd if p["d"] not in placed_d and p["o"] not in placed_o]
    elsewhere = [p for p in bd if (p["d"] in placed_d) != (p["o"] in placed_o)]
    print("  NEW (both sides outside the 987): %d; %s" % (len(new), quantiles([p["sim"] for p in new])))
    print("  one side inside the 987, the other not (counted above as disagree): %d" % len(elsewhere))
    print("  NEW by algorithm:", dict(collections.Counter(p["alg"] for p in new).most_common()))

    # ---- §3 -------------------------------------------------------------------------------------------
    print("\n[§3 rate] the 828 proved pairs as truth (BinDiff never saw them: all held out)")
    pr = [r for r in rows if r["d"] in proved]
    c = collections.Counter(r["v"] for r in pr)
    print("  proved %d: agree %d, contradict %d, absent %d" % (len(pr), c["agree"], c["disagree"], c["absent"]))
    for how in sorted({r["how"] for r in pr}):
        cc = collections.Counter(r["v"] for r in pr if r["how"] == how)
        print("    %-14s agree %d, contradict %d, absent %d" % (how, cc["agree"], cc["disagree"], cc["absent"]))
    agree_alg = collections.Counter("byte hash" if is_hash_alg(r["p"]["alg"]) else "any other matcher"
                                    for r in pr if r["v"] == "agree")
    print("  agreements by BinDiff algorithm class:", dict(agree_alg))
    contra = [r for r in pr if r["v"] == "disagree"]
    for r in sorted(contra, key=lambda r: -r["p"]["sim"]):
        p = r["p"]
        print("    contradiction: %s demo 0x%08x -> ours 0x%08x (%s, %d B); BinDiff pairs 0x%08x -> 0x%08x "
              "sim %.3f conf %.3f %s" % (demo_name[r["d"]], r["d"], r["o"], r["how"], our_size.get(r["o"], 0),
                                          p["d"], p["o"], p["sim"], p["conf"], p["alg"]))
    worst = max((r["p"]["sim"] for r in contra), default=None)
    worst_struct = max((r["p"]["sim"] for r in contra if not is_hash_alg(r["p"]["alg"])), default=None)
    print("  largest contradicting similarity: %s (excluding the byte-hash matcher: %s)" % (
        "none" if worst is None else "%.4f" % worst, "none" if worst_struct is None else "%.4f" % worst_struct))

    print("  raw sweep, every matcher: at sim >= t   contradict / agree (not byte hash) on the 828 | NEW / NEW clearing 64 B and ratio 0.50 / of those on FUN_")
    for t in CUTS:
        cn = sum(1 for r in contra if r["p"]["sim"] >= t)
        ag = [r for r in pr if r["v"] == "agree" and r["p"]["sim"] >= t]
        ags = sum(1 for r in ag if not is_hash_alg(r["p"]["alg"]))
        nw = [p for p in new if p["sim"] >= t]
        nc = [p for p in nw if body_ok(p)]
        nf = [p for p in nc if gsm.is_anonymous(our_name.get(p["o"], ""))]
        print("    t=%.2f   %3d / %3d (%3d)   | %4d / %4d / %4d" % (t, cn, len(ag), ags, len(nw), len(nc), len(nf)))

    # The contradictions a pair CLEARING THE RULE makes, as a function of t. A contradiction is counted
    # per BinDiff pair (one BinDiff pair can contradict two proved pairs, once from each side).
    cpairs = {}
    for r in contra:
        for q in (by_d.get(r["d"]), by_o.get(r["o"])):
            if q is not None and not (q["d"] == r["d"] and q["o"] == r["o"]):
                cpairs[(q["d"], q["o"])] = q
    struct_worst = max((q["sim"] for q in cpairs.values() if rule(q, 0.0)), default=0.0)
    t_star = min(1.0, (int(struct_worst * 20 + 1e-9) + 1) / 20.0)
    print("  THE RULE: structural matcher, both bodies >= %d B, ratio >= %.2f, similarity >= t" % (MIN_BODY, MIN_RATIO))
    print("    contradicting BinDiff pairs %d; clearing the rule at t=0: %d; the largest similarity among those %.4f"
          % (len(cpairs), sum(1 for q in cpairs.values() if rule(q, 0.0)), struct_worst))
    for q in sorted((q for q in cpairs.values() if rule(q, 0.0)), key=lambda q: -q["sim"])[:5]:
        print("      %s demo 0x%08x -> ours 0x%08x (ours %s) sim %.4f conf %.4f %s" % (
            demo_name.get(q["d"], "?"), q["d"], q["o"], our_name.get(q["o"], "?"), q["sim"], q["conf"], q["alg"]))
    print("    t* = the first 0.05 step above it = %.2f" % t_star)
    print("    sweep under the rule: t  contradict / agree on the 828 (of which sim < 1.0) | NEW")
    for t in sorted(set(CUTS) | {t_star}):
        cn = sum(1 for q in cpairs.values() if rule(q, t))
        ag = [r for r in pr if r["v"] == "agree" and rule(r["p"], t)]
        print("      t=%.2f   %3d / %3d (%3d)   | %4d" % (t, cn, len(ag), sum(1 for r in ag if r["p"]["sim"] < 1.0),
                                                    sum(1 for p in new if rule(p, t))))
    ag = [r for r in pr if r["v"] == "agree" and rule(r["p"], t_star)]
    print("    at t*: agreements by algorithm %s" % dict(collections.Counter(r["p"]["alg"] for r in ag).most_common()))
    print("    at t*: agreements by Task 7 pass %s" % dict(collections.Counter(r["how"] for r in ag).most_common()))

    # A second truth set outside the 987: recomp/socom2.toml's name@addr stub list (the project's own
    # hand names, mostly the Sony SDK and libc). A BinDiff pair on a toml-named address of ours either
    # carries the demo function of that name or it does not.
    with open(TOML) as fh:
        tnames = {int(a, 16): n for n, a in re.findall(r'"([^"@]+)@0x([0-9A-Fa-f]+)"', fh.read())}
    print("\n[§3 toml] BinDiff pairs on the toml's %d name@addr addresses (a truth set outside the 987)" % len(tnames))
    for label, pool in (("all", bd), ("NEW (outside the 987)", new)):
        on = [p for p in pool if p["o"] in tnames]
        same = [p for p in on if demo_name.get(p["d"]) == tnames[p["o"]]]
        print("  %-22s on toml addresses %4d: same name %4d, other name %4d" % (label, len(on), len(same), len(on) - len(same)))
        for t in (0.0, 0.7, 0.9, t_star):
            onr = [p for p in on if rule(p, t)]
            sr = [p for p in onr if demo_name.get(p["d"]) == tnames[p["o"]]]
            print("    under the rule at t=%.2f: %d, same %d (similarity < 1.0: %d), other %d" % (
                t, len(onr), len(sr), sum(1 for p in sr if p["sim"] < 1.0), len(onr) - len(sr)))
    for p in sorted(bd, key=lambda p: -p["sim"]):
        if p["o"] in tnames and demo_name.get(p["d"]) != tnames[p["o"]] and rule(p, 0.0):
            print("    other name under the rule: toml %s @0x%08x, BinDiff demo %s sim %.4f %s" % (
                tnames[p["o"]], p["o"], demo_name.get(p["d"], "?"), p["sim"], p["alg"]))
    for d, o, how in anchors:
        if o in tnames and tnames[o] != demo_name[d]:
            v, p = verdict(d, o)
            print("    Task 7 against the toml: %s @0x%08x is %s in the toml (%s); BinDiff: %s%s" % (
                demo_name[d], o, tnames[o], how, v,
                "" if p is None else " (demo %s -> 0x%08x, sim %.4f, %s)" % (demo_name.get(p["d"], "?"), p["o"], p["sim"], p["alg"])))

    # ---- §4 -------------------------------------------------------------------------------------------
    print("\n[§4 prefix] the 159 prologue-only pairs")
    pf = [r for r in rows if r["how"].startswith("prefix")]
    c = collections.Counter(r["v"] for r in pf)
    print("  %d: agree %d, disagree %d, absent %d" % (len(pf), c["agree"], c["disagree"], c["absent"]))
    for how in ("prefix", "prefix+size"):
        cc = collections.Counter(r["v"] for r in pf if r["how"] == how)
        print("    %-12s agree %d, disagree %d, absent %d" % (how, cc["agree"], cc["disagree"], cc["absent"]))
    eng = [r for r in pf if gsm.is_engine(demo_name[r["d"]])]
    ce = collections.Counter(r["v"] for r in eng)
    print("  engine (gsm.is_engine) %d: agree %d, disagree %d, absent %d" % (len(eng), ce["agree"], ce["disagree"], ce["absent"]))
    print("  agree similarity: %s" % quantiles([r["p"]["sim"] for r in pf if r["v"] == "agree"]))
    print("  agree by BinDiff algorithm:", dict(collections.Counter(r["p"]["alg"] for r in pf if r["v"] == "agree").most_common()))
    for t in CUTS:
        print("    agree at sim >= %.2f: %d (engine %d)" % (
            t, sum(1 for r in pf if r["v"] == "agree" and r["p"]["sim"] >= t),
            sum(1 for r in eng if r["v"] == "agree" and r["p"]["sim"] >= t)))
    def rule_verdict(r):
        if r["v"] == "agree" and rule(r["p"], t_star):
            return "confirmed"
        if r["v"] == "disagree" and rule(r["p"], t_star):
            return "contradicted"
        return "unconfirmed"

    rv = collections.Counter(rule_verdict(r) for r in pf)
    print("  under the rule at t*=%.2f: %s; engine %s" % (t_star, dict(rv), dict(collections.Counter(rule_verdict(r) for r in eng))))
    for r in sorted(pf, key=lambda r: -demo_size[r["d"]]):
        if rule_verdict(r) != "unconfirmed":
            print("    %-12s %-60s demo %5d B ours 0x%08x %5d B sim %.4f conf %.4f %s" % (
                rule_verdict(r), demo_name[r["d"]][:60], demo_size[r["d"]], r["o"], our_size.get(r["o"], 0),
                r["p"]["sim"], r["p"]["conf"], r["p"]["alg"]))
    out = []
    for r in sorted(pf, key=lambda r: (-demo_size[r["d"]], r["o"])):
        p = r["p"]
        out.append(dict(demo_name=demo_name[r["d"]], readable=readable(demo_name[r["d"]]),
                        demo_addr="0x%08x" % r["d"], our_addr="0x%08x" % r["o"], task7_pass=r["how"],
                        demo_size=demo_size[r["d"]], our_size=our_size.get(r["o"], 0),
                        engine=int(gsm.is_engine(demo_name[r["d"]])), verdict=r["v"], rule_verdict=rule_verdict(r),
                        similarity="" if p is None else "%.4f" % p["sim"],
                        confidence="" if p is None else "%.4f" % p["conf"],
                        algorithm="" if p is None else p["alg"],
                        bindiff_demo="" if p is None else "0x%08x" % p["d"],
                        bindiff_ours="" if p is None else "0x%08x" % p["o"]))
    print("  the 20 largest (demo size, research/44 §4's order):")
    for x in out[:20]:
        print("    %-60s ours %s demo %5d B ours %5d B  %-11s %-8s sim %-6s conf %-6s %s%s" % (
            x["demo_name"][:60], x["our_addr"], x["demo_size"], x["our_size"], x["task7_pass"], x["verdict"], x["similarity"],
            x["confidence"], x["algorithm"],
            "" if x["verdict"] != "disagree" else "  (BinDiff: %s -> %s)" % (x["bindiff_demo"], x["bindiff_ours"])))
    if args.prefix_csv:
        with open(args.prefix_csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(out)
        print("  wrote %d rows to %s" % (len(out), args.prefix_csv))

    # ---- §5 -------------------------------------------------------------------------------------------
    print("\n[§5 new] BinDiff pairs outside the 987: %d" % len(new))
    segs = sorted((v, v + len(data)) for v, data in read_elf(OURS).segments)
    for lo, hi in segs:
        sub = [p for p in new if lo <= p["o"] < hi]
        k = collections.Counter(kind(demo_name.get(p["d"], "")) for p in sub)
        print("  0x%06x-0x%06x %5d  (engine-member %d, engine-free %d, sdk %d)" % (
            lo, hi, len(sub), k["engine-member"], k["engine-free"], k["sdk"]))
    k = collections.Counter(kind(demo_name.get(p["d"], "")) for p in new)
    print("  all: engine-member %d, engine-free %d, sdk %d" % (k["engine-member"], k["engine-free"], k["sdk"]))
    nc = [p for p in new if body_ok(p)]
    print("  clearing body >= 64 B both sides and size ratio >= 0.50: %d (on FUN_ rows %d)" % (
        len(nc), sum(1 for p in nc if gsm.is_anonymous(our_name.get(p["o"], "")))))
    print("  the twelve largest (demo size), any similarity:")
    for p in sorted(new, key=lambda p: -demo_size.get(p["d"], 0))[:12]:
        n = demo_name.get(p["d"], "?")
        print("    %-58s demo 0x%08x %5d B -> ours 0x%08x %5d B  sim %.3f conf %.3f  %s" % (
            n[:58], p["d"], demo_size.get(p["d"], 0), p["o"], our_size.get(p["o"], 0), p["sim"], p["conf"], p["alg"]))
    nr = [p for p in new if rule(p, t_star)]
    print("  NEW under the rule at t*=%.2f: %d (similarity < 1.0: %d; on FUN_ rows %d; demo name unique in the demo %d)" % (
        t_star, len(nr), sum(1 for p in nr if p["sim"] < 1.0), sum(1 for p in nr if gsm.is_anonymous(our_name.get(p["o"], ""))),
        sum(1 for p in nr if name_count[demo_name.get(p["d"], "")] == 1)))
    for lo, hi in segs:
        sub = [p for p in nr if lo <= p["o"] < hi]
        k = collections.Counter(kind(demo_name.get(p["d"], "")) for p in sub)
        print("    0x%06x-0x%06x %4d  (engine-member %d, engine-free %d, sdk %d)" % (
            lo, hi, len(sub), k["engine-member"], k["engine-free"], k["sdk"]))
    print("    by algorithm:", dict(collections.Counter(p["alg"] for p in nr).most_common()))
    print("  the twelve largest under the rule (demo size):")
    for p in sorted(nr, key=lambda p: -demo_size.get(p["d"], 0))[:12]:
        n = demo_name.get(p["d"], "?")
        print("    %-58s demo 0x%08x %5d B -> ours 0x%08x %5d B  sim %.3f conf %.3f  %s" % (
            n[:58], p["d"], demo_size.get(p["d"], 0), p["o"], our_size.get(p["o"], 0), p["sim"], p["conf"], p["alg"]))

    # ---- §6 -------------------------------------------------------------------------------------------
    print("\n[§6 ceiling] the demo functions whose exact fingerprint is absent from our image")
    demo_funcs, dsegs = gsm._split(demo_rows, demo_segs)
    our_funcs, osegs = gsm._split(our_rows, our_segs)
    a, b = am.Side(demo_funcs, dsegs), am.Side(our_funcs, osegs)
    absent = {s for s in a.starts if not (a.fp[s] and b.by_fp.get(a.fp[s]))}
    print("  absent-bucket demo functions %d (research/44 §6: 7,595)" % len(absent))
    hit = [p for p in bd if p["d"] in absent]
    hi7 = [p for p in hit if p["sim"] >= 0.7]
    fun = [p for p in hi7 if gsm.is_anonymous(our_name.get(p["o"], "")) and p["o"] not in placed_o
           and p["d"] not in placed_d]
    print("  BinDiff pairs on them: %d; at sim >= 0.7: %d; of those NEW (neither side in the 987) on a FUN_ row: %d" % (
        len(hit), len(hi7), len(fun)))
    s6 = [p for p in hit if p["o"] not in placed_o and p["d"] not in placed_d
          and gsm.is_anonymous(our_name.get(p["o"], "")) and rule(p, t_star)]
    print("  under the rule at t*=%.2f: %d NEW on FUN_ rows (engine %d, similarity < 1.0: %d) -- %.2f %% of the %d" % (
        t_star, len(s6), sum(1 for p in s6 if kind(demo_name.get(p["d"], "")) != "sdk"),
        sum(1 for p in s6 if p["sim"] < 1.0), 100.0 * len(s6) / len(absent), len(absent)))
    for t in CUTS:
        s = [p for p in hit if p["sim"] >= t and p["o"] not in placed_o and p["d"] not in placed_d
             and gsm.is_anonymous(our_name.get(p["o"], ""))]
        print("    sim >= %.2f: new on FUN_ %d, clearing 64 B / ratio 0.50 %d, engine %d" % (
            t, len(s), sum(1 for p in s if body_ok(p)), sum(1 for p in s if body_ok(p) and kind(demo_name.get(p["d"], "")) != "sdk")))
    # ---- §7 -------------------------------------------------------------------------------------------
    if args.compare:
        print("\n[§7 levers] the other levers' proposals against BinDiff under the rule at t*=%.2f" % t_star)
        rule_o = {p["o"]: p for p in bd if rule(p, t_star)}
        proposed = set()
        for path in args.compare:
            with open(path, newline="") as fh:
                rows7 = [r for r in csv.DictReader(line for line in fh if not line.startswith("#"))]
            same = other = nopair = unkeyed = 0
            others = []
            for r in rows7:
                o = int(r["Address"], 16)
                proposed.add(o)
                da = r.get("DemoAddr") or ""
                mangled = r.get("Mangled") or ""
                if not da and not mangled:
                    unkeyed += 1
                    continue
                p = rule_o.get(o)
                if p is None:
                    nopair += 1
                elif (da and int(da, 16) == p["d"]) or (not da and demo_name.get(p["d"]) == mangled):
                    same += 1
                else:
                    other += 1
                    others.append("%s@0x%08x vs BinDiff %s (sim %.3f)" % (mangled or "?", o, demo_name.get(p["d"], "?"), p["sim"]))
            print("  %-52s rows %4d: BinDiff under the rule same %4d, other %3d, no rule pair %4d, no demo key %d" % (
                path, len(rows7), same, other, nopair, unkeyed))
            for x in others[:6]:
                print("      other: " + x)
        nr = [p for p in new if rule(p, t_star)]
        print("  the rule's %d NEW pairs: proposed by some file %d, by none (BinDiff-only) %d" % (
            len(nr), sum(1 for p in nr if p["o"] in proposed), sum(1 for p in nr if p["o"] not in proposed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
