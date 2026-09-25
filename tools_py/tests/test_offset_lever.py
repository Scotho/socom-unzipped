"""Sprint 12 Task 13 -- the `offset-multiset` lever (tools_py/offset_lever; research/54, S12-R12).

The fixtures are two little images of hand-assembled MIPS, the demo and ours, laid out function by
function at different bases. The routine under test is a body of loads and stores through `$a0` (an
object's fields) with chosen displacements; the anchors are pure register arithmetic and are handed to
the pass as Task 7's pairs, the way `anchors_from_details` hands over the real 987. No disc, no demo,
no ELF on disk.
"""
import collections
import csv
import os
import tempfile
import unittest

from tools_py import address_matcher as am
from tools_py import offset_lever as ol
from tools_py import symbol_levers as sl


# ---- the same tiny assembler the Task 7 and 7b suites use ---------------------------------

def lui(rt, imm):        return (0x0F << 26) | (rt << 16) | (imm & 0xFFFF)
def addiu(rt, rs, imm):  return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def lw(rt, base, imm):   return (0x23 << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def sw(rt, base, imm):   return (0x2B << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def lh(rt, base, imm):   return (0x21 << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def addu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x21
def subu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x23
def xor(rd, rs, rt):     return (rs << 21) | (rt << 16) | (rd << 11) | 0x26
def mult(rs, rt):        return (rs << 21) | (rt << 16) | 0x18
def jal(target):         return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)
def jr_ra():             return (31 << 21) | 8
NOP = 0

ZERO, AT, V0, A0, A1, T0, S0, GP, SP = 0, 1, 2, 4, 5, 8, 16, 28, 29
LW, SW, LH = 0x23, 0x2B, 0x21
DEMO_BASE, OUR_BASE = 0x00140000, 0x00280000
SLOT = 0x80                                   # every function 128 bytes unless a test says otherwise

TWELVE = [0x10 + 4 * i for i in range(12)]    # a 12-access key: over the >= 11 tightening
FIVE = [0x104, 0x10c, 0x118, 0x124, 0x130]    # a 5-access key: needs callees or a prologue


def _blob(words):
    return b"".join((w & 0xFFFFFFFF).to_bytes(4, "little") for w in words)


def _fill(words, size):
    out = list(words)
    while len(out) < size // 4 - 2:
        out.append(addu(T0, T0, V0))
    assert len(out) <= size // 4 - 2, "body does not fit its slot"
    return out + [jr_ra(), NOP]


def anchor(salt):
    """Pure register arithmetic: no load or store, so its offset key is empty."""
    return [addu(V0, A0, A1), subu(V0, V0, A0), xor(A1, V0, A0), mult(V0, A1 + salt % 3),
            addu(V0, V0, A1), subu(A0, A1, V0), xor(S0, S0, A0 + salt % 5)]


def fields(disps, head=(), calls=()):
    """`head`, then a load or a store through `$a0` at each displacement, then `jal` to each call."""
    body = list(head)
    for i, d in enumerate(disps):
        body.append(lw(V0, A0, d) if i % 2 == 0 else sw(V0, A0, d))
    for target in calls:
        body += [jal(target), NOP]
    return body


DIFFERENT_HEAD = [xor(T0, T0, A1), subu(S0, S0, T0)]   # arithmetic only: moves the prologue, not the key


def build(base, order, bodies, sizes=None, name_of=None):
    """(Side, {name: address}). `bodies` maps a name to a callable taking {name: address}."""
    sizes = sizes or {}
    addr, cursor = {}, base
    for name in order:
        addr[name] = cursor
        cursor += sizes.get(name, SLOT)
    rows, blob = [], b""
    for name in order:
        size = sizes.get(name, SLOT)
        blob += _blob(_fill(bodies[name](addr), size))
        label = name_of(name, addr[name]) if name_of else name
        rows.append((addr[name], addr[name] + size, label))
    return am.Side(rows, [(base, blob)]), addr


def our_name(name, address):
    return "FUN_%08x" % address


class World:
    """A demo and an our image, with the anchors named `anc*` handed over as Task 7's pairs."""

    def __init__(self, demo_order, our_order, demo_bodies, our_bodies, how=None,
                 demo_sizes=None, our_sizes=None, our_names=None):
        for order, bodies in ((demo_order, demo_bodies), (our_order, our_bodies)):
            for name in order:
                if name.startswith("anc"):
                    salt = int(name[3:])
                    bodies.setdefault(name, lambda a, s=salt: anchor(s))
        self.demo, self.d = build(DEMO_BASE, demo_order, demo_bodies, demo_sizes)
        namer = our_names or our_name
        self.ours, self.o = build(OUR_BASE, our_order, our_bodies, our_sizes, namer)
        how = how or {}
        self.anchors = sorted((self.d[n], self.o[n], how.get(n, "exact"))
                              for n in demo_order if n.startswith("anc") or n in how)
        self.details = {(n, self.o[n]): {"how": how.get(n, "exact"), "size": SLOT, "demo_addr": self.d[n]}
                        for n in demo_order if n.startswith("anc") or n in how}

    def run(self):
        return ol.offset_pass(self.demo, self.ours, self.anchors)


def simple(demo_x, our_x, **kw):
    """anc0, X, anc1 on both sides: X lies between its anchors in both builds."""
    order = ["anc0", "X", "anc1", "anc2"]
    return World(order, list(order), {"X": demo_x}, {"X": our_x}, **kw)


class AccessKeyTest(unittest.TestCase):
    def side(self, words):
        return am.Side([(0x1000, 0x1000 + 4 * len(words), "f")], [(0x1000, _blob(words))])

    def test_it_keeps_object_accesses_and_drops_sp_gp_zero_and_lui_formed_ones(self):
        words = [lw(V0, SP, 0x10), sw(V0, GP, -0x7ff0), lw(V0, ZERO, 0x30),
                 lui(AT, 0x0050), lw(V0, AT, 0x40),                          # a global: lui-formed
                 lui(T0, 0x0050), addiu(T0, T0, 0x120), sw(V0, T0, 0x8),     # lui + addiu: still one
                 lw(V0, A0, 0x18), sw(V0, A0, 0x1c), lh(V0, A0, -8),          # kept: object fields
                 addu(AT, A0, A1), lw(V0, AT, 0x44),                          # AT rewritten: kept
                 jr_ra(), NOP]
        census = collections.Counter()
        key = ol.access_key(self.side(words), 0x1000, 0x1000 + 4 * len(words), census)
        self.assertEqual(key, tuple(sorted([(LW, 0x18), (SW, 0x1c), (LH, -8), (LW, 0x44)])))
        self.assertEqual(census["$sp"], 1)
        self.assertEqual(census["$gp"], 1)
        self.assertEqual(census["$zero"], 1)
        self.assertEqual(census["lui-formed"], 2)
        self.assertEqual(census["kept"], 4)

    def test_the_key_is_a_multiset(self):
        words = [lw(V0, A0, 0x18), lw(T0, A1, 0x18), sw(V0, S0, 0x18), jr_ra(), NOP]
        key = ol.access_key(self.side(words), 0x1000, 0x1000 + 4 * len(words))
        self.assertEqual(key, ((LW, 0x18), (LW, 0x18), (SW, 0x18)))


class OffsetPassTest(unittest.TestCase):
    def test_a_unique_key_pairs(self):
        w = simple(lambda a: fields(TWELVE), lambda a: fields(TWELVE, head=DIFFERENT_HEAD))
        found, census = w.run()
        self.assertEqual([(c.demo_addr, c.our_addr) for c in found], [(w.d["X"], w.o["X"])])
        c = found[0]
        self.assertEqual(c.how, "offset-multiset")
        self.assertEqual(c.score, 0.75)
        self.assertEqual(c.accesses, 12)
        self.assertEqual(c.order, "between")
        self.assertEqual(c.evidence, "offset multiset unique both sides, 12 accesses, ratio 1.00")
        self.assertEqual(census["proposed"], 1)

    def test_a_key_two_of_our_functions_share_does_not_pair(self):
        order = ["anc0", "X", "anc1", "anc2"]
        w = World(order, ["anc0", "X", "Y", "anc1", "anc2"], {"X": lambda a: fields(TWELVE)},
                  {"X": lambda a: fields(TWELVE), "Y": lambda a: fields(TWELVE, head=DIFFERENT_HEAD)})
        found, census = w.run()
        self.assertEqual(found, [])
        self.assertEqual(census["key not unique both ways"], 1)

    def test_sp_and_gp_accesses_are_dropped(self):
        demo_x = lambda a: fields(TWELVE, head=[lw(V0, SP, 0x10), sw(V0, GP, -0x7ff0)])
        our_x = lambda a: fields(TWELVE, head=[lw(V0, SP, 0x58), sw(V0, SP, 0x60), lw(V0, GP, -0x6000)])
        found, _census = simple(demo_x, our_x).run()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].accesses, 12)

    def test_a_lui_formed_base_is_dropped(self):
        demo_x = lambda a: fields(TWELVE, head=[lui(AT, 0x0050), lw(V0, AT, 0x0120)])
        our_x = lambda a: fields(TWELVE, head=[lui(AT, 0x0061), lw(V0, AT, -0x5f00),
                                               lui(T0, 0x0061), addiu(T0, T0, 0x44), sw(V0, T0, 4)])
        found, _census = simple(demo_x, our_x).run()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].accesses, 12)

    def test_under_three_accesses_is_refused(self):
        body = lambda a: fields([0x18, 0x1c])              # equal bodies: prologue equal, still refused
        found, census = simple(body, body).run()
        self.assertEqual(found, [])
        self.assertEqual(census["under 3 accesses"], 1)

    def test_eleven_accesses_carry_it_alone(self):
        eleven = TWELVE[:11]
        found, _c = simple(lambda a: fields(eleven), lambda a: fields(eleven, head=DIFFERENT_HEAD)).run()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].evidence, "offset multiset unique both sides, 11 accesses, ratio 1.00")

    def test_five_accesses_alone_are_refused(self):
        found, census = simple(lambda a: fields(FIVE), lambda a: fields(FIVE, head=DIFFERENT_HEAD)).run()
        self.assertEqual(found, [])
        self.assertEqual(census["no tightening (< 11 accesses, callees, prologue)"], 1)

    def test_five_accesses_pass_when_the_callees_agree(self):
        w = simple(lambda a: fields(FIVE, calls=[a["anc2"]]),
                   lambda a: fields(FIVE, head=DIFFERENT_HEAD, calls=[a["anc2"]]))
        found, _c = w.run()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].evidence,
                         "offset multiset unique both sides, 5 accesses, ratio 1.00 + callees")

    def test_five_accesses_are_refused_when_a_callee_maps_elsewhere(self):
        w = simple(lambda a: fields(FIVE, calls=[a["anc2"]]),
                   lambda a: fields(FIVE, head=DIFFERENT_HEAD, calls=[a["anc0"]]))
        found, _c = w.run()
        self.assertEqual(found, [])

    def test_five_accesses_pass_when_the_masked_prologues_are_equal(self):
        found, _c = simple(lambda a: fields(FIVE), lambda a: fields(FIVE)).run()
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].evidence.endswith("ratio 1.00 + prologue"), found[0].evidence)

    def test_a_size_ratio_under_one_half_is_refused(self):
        order = ["anc0", "X", "anc1", "anc2"]
        w = World(order, list(order), {"X": lambda a: fields(TWELVE)}, {"X": lambda a: fields(TWELVE)},
                  our_sizes={"X": 0x200})
        found, census = w.run()
        self.assertEqual(found, [])
        self.assertEqual(census["size ratio under 0.50"], 1)

    def test_a_body_under_64_bytes_is_refused(self):
        order = ["anc0", "X", "anc1", "anc2"]
        w = World(order, list(order), {"X": lambda a: fields(TWELVE[:6])},
                  {"X": lambda a: fields(TWELVE[:6])}, demo_sizes={"X": 0x20}, our_sizes={"X": 0x20})
        found, census = w.run()
        self.assertEqual(found, [])
        self.assertEqual(census["body under 64 bytes"], 1)

    def test_a_task_7_pair_is_not_proposed_again(self):
        w = simple(lambda a: fields(TWELVE), lambda a: fields(TWELVE), how={"X": "relinked-body"})
        found, census = w.run()
        self.assertEqual(found, [])
        self.assertEqual(census["one of Task 7's pairs"], 1)

    def test_a_named_row_of_ours_is_refused(self):
        order = ["anc0", "X", "anc1", "anc2"]
        w = World(order, list(order), {"X": lambda a: fields(TWELVE)}, {"X": lambda a: fields(TWELVE)},
                  our_names=lambda n, a: "CZSealBody_Tick" if n == "X" else our_name(n, a))
        found, census = w.run()
        self.assertEqual(found, [])
        self.assertEqual(census["our row already named"], 1)

    def test_an_outside_pair_is_found_with_its_order_verdict(self):
        # demo: anc0 anc1 anc2 X; ours: anc0 X anc1 anc2 -- X's demo address is past both flanks
        w = World(["anc0", "anc1", "anc2", "X"], ["anc0", "X", "anc1", "anc2"],
                  {"X": lambda a: fields(TWELVE)}, {"X": lambda a: fields(TWELVE)})
        found, _census = w.run()
        self.assertEqual([c.order for c in found], ["outside"])


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "demo_symbol_renames_offsets.csv")

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, path):
        with open(path) as fh:
            lines = fh.read().splitlines()
        header = [l for l in lines if l.startswith("#")]
        rows = list(csv.DictReader(l for l in lines if not l.startswith("#")))
        return header, rows

    def outside_world(self):
        return World(["anc0", "anc1", "anc2", "X", "anc3", "Y", "anc4"],
                     ["anc0", "X", "anc1", "anc2", "anc3", "Y", "anc4"],
                     {"X": lambda a: fields(TWELVE), "Y": lambda a: fields([d + 0x400 for d in TWELVE])},
                     {"X": lambda a: fields(TWELVE), "Y": lambda a: fields([d + 0x400 for d in TWELVE])})

    def test_an_outside_row_goes_to_the_loose_file(self):
        w = self.outside_world()
        found, _census = w.run()
        rows, _held = ol.proposals(found, {})
        written = ol.write_split(self.path, rows, ["the header"])
        loose = sl.loose_path(self.path)
        self.assertEqual(written, {self.path: 1, loose: 1})
        _h, strict_rows = self.read(self.path)
        _h, loose_rows = self.read(loose)
        self.assertEqual([r["Address"] for r in strict_rows], ["0x%08x" % w.o["Y"]])
        self.assertEqual([(r["Address"], r["Order"]) for r in loose_rows], [("0x%08x" % w.o["X"], "outside")])

    def test_the_strict_path_refuses_an_outside_row(self):
        found, _c = self.outside_world().run()
        rows, _held = ol.proposals(found, {})
        with self.assertRaises(ValueError):
            ol.write_proposals(self.path, rows, ["h"])

    def test_the_header_carries_the_rule(self):
        found, census = simple(lambda a: fields(TWELVE), lambda a: fields(TWELVE)).run()
        rows, held = ol.proposals(found, {})
        ol.write_split(self.path, rows, ol.header(self.path, census, held, {}, anchors_note="Anchors: 3"))
        header, rows = self.read(self.path)
        text = " ".join(l[2:] for l in header)
        self.assertIn(ol.OFFSET_RULE, text)
        self.assertIn("link order", text)
        self.assertIn("blind to this key by construction", text)
        self.assertEqual(rows[0]["How"], "offset-multiset")
        self.assertEqual(rows[0]["Score"], "0.75")
        self.assertEqual(rows[0]["Proposed"], "X")
        self.assertEqual(rows[0]["Mangled"], "X")

    def test_a_name_another_file_spends_at_another_address_is_refused(self):
        found, _c = simple(lambda a: fields(TWELVE), lambda a: fields(TWELVE)).run()
        rows, held = ol.proposals(found, {"X": {0x00123450: ["demo_symbol_renames_7b.csv"]}})
        self.assertEqual(rows, [])
        self.assertEqual(held["identifier already proposed at another address"], 1)

    def test_the_same_name_at_the_same_address_in_another_file_is_kept_and_counted(self):
        w = simple(lambda a: fields(TWELVE), lambda a: fields(TWELVE))
        found, _c = w.run()
        rows, held = ol.proposals(found, {"X": {w.o["X"]: ["demo_symbol_renames_strings.csv"]}})
        self.assertEqual(len(rows), 1)
        self.assertEqual(held["agrees with another file (kept)"], 1)

    def test_two_candidates_with_one_identifier_are_both_refused(self):
        found, _c = self.outside_world().run()
        clash = [c._replace(demo_name="Same") for c in found]
        rows, held = ol.proposals(clash, {})
        self.assertEqual(rows, [])
        self.assertEqual(held["identifier collides inside this pass"], 2)

    def test_other_files_are_read_for_their_names(self):
        other = os.path.join(self.tmp.name, "demo_symbol_renames_7b.csv")
        with open(other, "w") as fh:
            fh.write("# a header\nAddress,Current,Proposed,Mangled\n0x00100000,FUN_00100000,foo,foo\n")
        taken = ol.other_proposals([other, self.path])
        self.assertEqual(taken, {"foo": {0x00100000: ["demo_symbol_renames_7b.csv"]}})


class PrefixOffsetsTest(unittest.TestCase):
    def world(self, our_disps):
        order = ["anc0", "X", "anc1", "Z", "anc2"]
        return World(order, list(order),
                     {"X": lambda a: fields(TWELVE), "Z": lambda a: fields(FIVE)},
                     {"X": lambda a: fields(our_disps, head=DIFFERENT_HEAD),
                      "Z": lambda a: fields(FIVE, head=DIFFERENT_HEAD)},
                     how={"X": "prefix", "Z": "exact"})

    def test_a_prefix_pair_with_an_equal_unique_key_is_proposed(self):
        w = self.world(TWELVE)
        found, census = ol.prefix_offsets(w.demo, w.ours, w.details)
        self.assertEqual([(c.demo_addr, c.our_addr) for c in found], [(w.d["X"], w.o["X"])])
        self.assertEqual(found[0].how, "prefix+offsets")
        self.assertEqual(found[0].score, 0.80)
        self.assertEqual(found[0].evidence,
                         "prologue unique both sides + offset multiset unique both sides, 12 accesses")
        self.assertEqual(census["prologue pairs"], 1)

    def test_a_prefix_pair_whose_keys_differ_is_not(self):
        w = self.world(TWELVE[:-1] + [0x7f0])
        found, census = ol.prefix_offsets(w.demo, w.ours, w.details)
        self.assertEqual(found, [])
        self.assertEqual(census["key differs or not unique both ways"], 1)

    def test_it_writes_the_prefix_file(self):
        w = self.world(TWELVE)
        found, census = ol.prefix_offsets(w.demo, w.ours, w.details)
        rows, held = ol.proposals(found, {})
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "demo_symbol_renames_prefix_offsets.csv")
            ol.write_proposals(path, rows, ol.prefix_header(path, census, held))
            with open(path) as fh:
                text = fh.read()
        self.assertIn(ol.PREFIX_OFFSETS_RULE, text)
        self.assertIn(",prefix+offsets,", text)
        self.assertIn(",0.80,", text)

    def test_an_outside_prefix_pair_is_judged_without_itself_and_goes_loose(self):
        w = World(["anc0", "anc1", "anc2", "X"], ["anc0", "X", "anc1", "anc2"],
                  {"X": lambda a: fields(TWELVE)}, {"X": lambda a: fields(TWELVE, head=DIFFERENT_HEAD)},
                  how={"X": "prefix+size"})
        found, census = ol.prefix_offsets(w.demo, w.ours, w.details)
        self.assertEqual([c.order for c in found], ["outside"])
        rows, held = ol.proposals(found, {})
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "demo_symbol_renames_prefix_offsets.csv")
            written = ol.write_split(path, rows, ol.prefix_header(path, census, held))
        self.assertEqual(written, {path: 0, sl.loose_path(path): 1})


if __name__ == "__main__":
    unittest.main()
