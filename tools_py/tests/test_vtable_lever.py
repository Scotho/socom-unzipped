"""Sprint 12 Task 4 (7c) -- the `vtable-slot` lever (tools_py/vtable_lever).

The fixture is two little synthetic images, a "demo" and a "retail", each one segment holding a code
area (functions of arithmetic filler, ended `jr $ra; nop`) and a data area laid out the way Metrowerks
2.4.1 lays out C++ run-time type data (docs/research/51 section 0):

    "\\0Qualified::Name\\0"                      the RTTI name string
    RTTI object   [name string*, base list*]     base list = [base RTTI*, offset]... 0
    vtable        [RTTI*, 0 | -offset, slot...]  slots are function starts; a 0 word is pure virtual

The demo side carries an ELF-like symbol table (`functions`, `objects` with `__vt__`/`__RTTI__`), the
retail side a Ghidra-like table of FUN_ rows. Task 7's pairs are handed in as {demo addr: our addr}:
the lever never fingerprints, it aligns. No disc, no demo, no ELF on disk; synthetic words only.
"""
import contextlib
import csv
import io
import os
import tempfile
import types
import unittest

from tools_py import vtable_lever as vl


def addu(rd, rs, rt):
    return (rs << 21) | (rt << 16) | (rd << 11) | 0x21


JR_RA = (31 << 21) | 8


class Build:
    """One synthetic image: functions in a code area, strings / RTTI / vtables in a data area."""

    def __init__(self, code_base, data_base):
        self.code_base, self.data_base = code_base, data_base
        self.code, self.data = [], []
        self.funcs = []           # (start, end, name)
        self.objects = []         # (start, end, name) -- the demo's STT_OBJECTs

    def fn(self, name, size=0x40):
        start = self.code_base + 4 * len(self.code)
        n = size // 4
        self.code += [addu(2, 4, 5 + (len(self.funcs) % 3))] * (n - 2) + [JR_RA, 0]
        self.funcs.append((start, start + size, name))
        return start

    def _here(self):
        return self.data_base + 4 * len(self.data)

    def string(self, text):
        raw = b"\0" + text.encode() + b"\0"
        raw += b"\0" * (-len(raw) % 4)
        at = self._here() + 1
        self.data += [int.from_bytes(raw[i:i + 4], "little") for i in range(0, len(raw), 4)]
        return at

    def rtti(self, name_addr, bases=(), symbol=None):
        at = self._here()
        self.data += [name_addr, 0]
        if bases:
            self.data[-1] = self._here()
            for base, off in bases:
                self.data += [base, off & 0xFFFFFFFF]
            self.data.append(0)
        if symbol:
            self.objects.append((at, at + 8, symbol))
        return at

    def vtable(self, rtti, slots, off=0, symbol=None, secondary=None):
        """`secondary` = (offset, slots): a second header inside the same object, as the demo does."""
        at = self._here()
        self.data += [rtti, off & 0xFFFFFFFF] + list(slots)
        if secondary:
            soff, sslots = secondary
            self.data += [rtti, soff & 0xFFFFFFFF] + list(sslots)
        self.data += [0, 0]       # a gap word pair: not a function start, so the slot count stops
        if symbol:
            self.objects.append((at, self._here() - 8, symbol))
        return at

    def pad(self, words):
        self.data += [0x11111111] * words

    def segments(self):
        blob = b"".join(w.to_bytes(4, "little") for w in self.code)
        gap = self.data_base - (self.code_base + len(blob))
        assert gap >= 0
        blob += b"\0" * gap + b"".join((w & 0xFFFFFFFF).to_bytes(4, "little") for w in self.data)
        return [(self.code_base, blob)]

    def elf(self):
        return types.SimpleNamespace(segments=self.segments(), functions=sorted(self.funcs),
                                     objects=sorted(self.objects))


def world(extra=None):
    """(demo, retail, pairs): one class `zdb::CNode` with three virtuals; slot 1 is a Task 7 pair.

    `extra(d, r, pairs)` may add more to both images before they are frozen.
    """
    d, r = Build(0x100000, 0x140000), Build(0x200000, 0x280000)
    pairs = {}
    df = [d.fn("Draw__Q23zdb5CNodeFv", 0x80), d.fn("Tick__Q23zdb5CNodeFv", 0x60),
          d.fn("Kill__Q23zdb5CNodeFv", 0x100)]
    rf = [r.fn("FUN_%08x" % (0x200000), 0x80), None, None]
    rf[1] = r.fn("FUN_%08x" % (0x200080), 0x60)
    rf[2] = r.fn("FUN_%08x" % (0x2000e0), 0x100)
    pairs[df[1]] = rf[1]
    ds = d.string("zdb::CNode")
    drt = d.rtti(ds, symbol="__RTTI__Q23zdb5CNode")
    d.vtable(drt, df, symbol="__vt__Q23zdb5CNode")
    rs = r.string("zdb::CNode")
    rrt = r.rtti(rs)
    r.vtable(rrt, rf)
    if extra:
        extra(d, r, pairs)
    return d, r, pairs


def fix_rows(r):
    """The retail csv rows, with every placeholder name made to match its address."""
    return [(s, e, n if not n.startswith("FUN_") else "FUN_%08x" % s) for s, e, n in sorted(r.funcs)]


def run(d, r, pairs, **kw):
    rows = fix_rows(r)
    res = vl.resolve_classes(d.elf(), r.segments(), {s for s, _e, _n in rows})
    out = vl.propose(res, d.elf().functions, rows, pairs, **kw)
    return res, out


def by_addr(out):
    return {int(row["Address"], 16): row for row in out.rows}


class ResolveTest(unittest.TestCase):
    def test_one_class_resolves_to_one_vtable_by_its_qualified_string(self):
        d, r, _p = world()
        res = vl.resolve_classes(d.elf(), r.segments(), {s for s, _e, _n in r.funcs})
        self.assertEqual(res.buckets["one"], 1)
        (vt,) = res.vtables
        self.assertEqual(vt.cls, "zdb::CNode")
        self.assertEqual(len(vt.demo_slots), 3)
        self.assertEqual(len(vt.our_slots), 3)

    def test_a_base_list_pointer_is_not_a_vtable_head(self):
        def extra(d, r, pairs):
            # a derived class whose RTTI base list points at CNode's RTTI object: in retail that word
            # is followed by the base offset (0) and then the list terminator, so it looks like a
            # vtable header [RTTI*, 0, ...] with no function slot, and the layout filter drops it.
            dd = d.fn("Draw__7CDerivedFv", 0x80)
            base_d = [a for a, _e, n in d.objects if n == "__RTTI__Q23zdb5CNode"][0]
            drt = d.rtti(d.string("CDerived"), bases=[(base_d, 0)], symbol="__RTTI__8CDerived")
            d.vtable(drt, [dd, dd + 0], symbol="__vt__8CDerived")
            rd = r.fn("FUN_x", 0x80)
            rrt_cnode = r.data_base + 4 * _index_of_rtti(r, "zdb::CNode")
            rrt = r.rtti(r.string("CDerived"), bases=[(rrt_cnode, 0)])
            r.vtable(rrt, [rd, rd])
        d, r, _p = world(extra)
        res = vl.resolve_classes(d.elf(), r.segments(), {s for s, _e, _n in r.funcs})
        self.assertEqual(res.buckets["one"], 2, res.buckets)
        self.assertEqual(res.buckets.get("several primaries", 0), 0)
        words_at_cnode = res.pointing.get("zdb::CNode")
        self.assertEqual(words_at_cnode, 2, "the vtable head and the base-list word both point at it")

    def test_a_word_1_that_is_neither_zero_nor_negative_is_not_a_vtable_head(self):
        def extra(d, r, pairs):
            # some other table whose first word happens to be CNode's RTTI address and whose second
            # is a positive count, followed by function pointers: not [RTTI*, 0 | -off, slots...]
            rrt_cnode = r.data_base + 4 * _index_of_rtti(r, "zdb::CNode")
            f = r.fn("FUN_x", 0x80)
            r.data += [rrt_cnode, 5, f, f, 0]
        d, r, _p = world(extra)
        res = vl.resolve_classes(d.elf(), r.segments(), {s for s, _e, _n in r.funcs})
        self.assertEqual(res.buckets["one"], 1, res.buckets)
        self.assertEqual(res.pointing["zdb::CNode"], 2)

    def test_a_pure_virtual_zero_slot_stops_the_count(self):
        def extra(d, r, pairs):
            d0, d2 = d.fn("A__5CPureFv", 0x80), d.fn("C__5CPureFv", 0x80)
            r0, r2 = r.fn("FUN_x", 0x80), r.fn("FUN_x", 0x80)
            d.vtable(d.rtti(d.string("CPure"), symbol="__RTTI__5CPure"), [d0, 0, d2],
                     symbol="__vt__5CPure")
            r.vtable(r.rtti(r.string("CPure")), [r0, 0, r2])
        d, r, pairs = world(extra)
        res, out = run(d, r, pairs)
        vt = [v for v in res.vtables if v.cls == "CPure"][0]
        self.assertEqual(len(vt.demo_slots), 1)
        self.assertEqual(len(vt.our_slots), 1)
        named = {row["Mangled"] for row in out.rows}
        self.assertIn("A__5CPureFv", named)
        self.assertNotIn("C__5CPureFv", named)

    def test_two_primaries_for_one_class_are_refused(self):
        def extra(d, r, pairs):
            d0, d1 = d.fn("A__6CTwiceFv", 0x80), d.fn("B__6CTwiceFv", 0x80)
            d.vtable(d.rtti(d.string("CTwice"), symbol="__RTTI__6CTwice"), [d0, d1],
                     symbol="__vt__6CTwice")
            r0, r1, r2 = r.fn("FUN_x", 0x80), r.fn("FUN_x", 0x80), r.fn("FUN_x", 0x80)
            r.vtable(r.rtti(r.string("CTwice")), [r0, r1])
            r.vtable(r.rtti(r.string("CTwice")), [r2, r0])
        d, r, pairs = world(extra)
        res, out = run(d, r, pairs)
        self.assertEqual(res.buckets["several primaries"], 1)
        self.assertFalse([v for v in res.vtables if v.cls == "CTwice"])

    def test_the_demo_secondary_pairs_with_the_retail_secondary_by_the_header_word(self):
        def extra(d, r, pairs):
            dp = [d.fn("P%d__4CTwoFv" % i, 0x80) for i in range(2)]
            dsec = [d.fn("S%d__4CTwoFv" % i, 0x80) for i in range(2)]
            d.vtable(d.rtti(d.string("CTwo"), symbol="__RTTI__4CTwo"), dp, symbol="__vt__4CTwo",
                     secondary=(-8, dsec))
            rp = [r.fn("FUN_x", 0x80) for _ in range(2)]
            rsec = [r.fn("FUN_x", 0x80) for _ in range(2)]
            rrt = r.rtti(r.string("CTwo"))
            r.vtable(rrt, rp)
            r.vtable(rrt, rsec, off=-8)
        d, r, pairs = world(extra)
        res, out = run(d, r, pairs)
        self.assertEqual(res.buckets["primary + secondary"], 1)
        parts = sorted(v.part for v in res.vtables if v.cls == "CTwo")
        self.assertEqual(parts, ["primary", "secondary"])
        names = {row["Mangled"] for row in out.rows}
        self.assertTrue({"P0__4CTwoFv", "S1__4CTwoFv"} <= names, names)

    def test_an_absent_class_is_counted(self):
        def extra(d, r, pairs):
            d0, d1 = d.fn("A__5CGoneFv", 0x80), d.fn("B__5CGoneFv", 0x80)
            d.vtable(d.rtti(d.string("CGone"), symbol="__RTTI__5CGone"), [d0, d1],
                     symbol="__vt__5CGone")
        d, r, _p = world(extra)
        res = vl.resolve_classes(d.elf(), r.segments(), {s for s, _e, _n in r.funcs})
        self.assertEqual(res.buckets["absent: no string"], 1)


def _index_of_rtti(build, text):
    """The data-word index of the RTTI object pointing at the string `text` in `build`."""
    raw = b"\0" + text.encode() + b"\0"
    blob = b"".join((w & 0xFFFFFFFF).to_bytes(4, "little") for w in build.data)
    at = build.data_base + blob.index(raw) + 1
    return next(i for i, w in enumerate(build.data) if w == at)


class AlignTest(unittest.TestCase):
    def test_a_fixed_point_at_slot_1_and_equal_runs_propose_slots_0_and_2(self):
        d, r, pairs = world()
        _res, out = run(d, r, pairs)
        rows = by_addr(out)
        self.assertEqual(sorted(rows), [0x200000, 0x2000e0])
        self.assertEqual(rows[0x200000]["Mangled"], "Draw__Q23zdb5CNodeFv")
        self.assertEqual(rows[0x200000]["Slot"], "0")
        self.assertEqual(rows[0x200000]["FixedPoints"], "start..1:1")
        self.assertEqual(rows[0x2000e0]["Slot"], "2")
        self.assertEqual(rows[0x2000e0]["FixedPoints"], "1:1..end")
        self.assertEqual(rows[0x2000e0]["How"], "vtable-slot")
        self.assertEqual(rows[0x2000e0]["Score"], "0.75")
        self.assertEqual(rows[0x2000e0]["Class"], "zdb::CNode")

    def test_an_unequal_run_is_refused_and_counted(self):
        a = vl.align_slots([10, 11, 12, 13], [20, 21, 22, 23, 24], {11: 21})
        self.assertEqual(a.chain, [(1, 1)])
        named = [(p.di, p.rj) for p in a.slots]
        self.assertEqual(named, [(0, 0)])           # before the fixed point: 1 = 1
        self.assertEqual(a.unequal_slots, 2)        # after it: 2 demo slots against 3 retail

    def test_an_equal_count_vtable_with_no_fixed_point_is_named_whole(self):
        a = vl.align_slots([10, 11], [20, 21], {})
        self.assertEqual([(p.di, p.rj, p.fixed) for p in a.slots],
                         [(0, 0, "start..end"), (1, 1, "start..end")])
        self.assertEqual(vl.align_slots([10, 11], [20, 21], {}, reading="start").slots, [])

    def test_the_strict_reading_does_not_name_before_the_first_fixed_point(self):
        a = vl.align_slots([10, 11, 12], [20, 21, 22], {11: 21}, reading="strict")
        self.assertEqual([p.di for p in a.slots], [2])


class HurdleTest(unittest.TestCase):
    def test_a_shared_body_named_alike_by_two_vtables_is_admitted(self):
        def extra(d, r, pairs):
            base = d.fn("Update__5CBaseFv", 0x80)
            a1, b1 = d.fn("Own__2CAFv", 0x80), d.fn("Own__2CBFv", 0x80)
            d.vtable(d.rtti(d.string("CA"), symbol="__RTTI__2CA"), [base, a1], symbol="__vt__2CA")
            d.vtable(d.rtti(d.string("CB"), symbol="__RTTI__2CB"), [base, b1], symbol="__vt__2CB")
            rbase, ra, rb = r.fn("FUN_x", 0x80), r.fn("FUN_x", 0x80), r.fn("FUN_x", 0x80)
            r.vtable(r.rtti(r.string("CA")), [rbase, ra])
            r.vtable(r.rtti(r.string("CB")), [rbase, rb])
        d, r, pairs = world(extra)
        _res, out = run(d, r, pairs)
        row = [x for x in out.rows if x["Mangled"] == "Update__5CBaseFv"]
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0]["Class"], "CA|CB")

    def test_a_shared_body_named_differently_is_refused(self):
        def extra(d, r, pairs):
            a0, b0 = d.fn("Update__2CAFv", 0x80), d.fn("Update__2CBFv", 0x80)
            d.vtable(d.rtti(d.string("CA"), symbol="__RTTI__2CA"), [a0, a0 + 0], symbol="__vt__2CA")
            d.vtable(d.rtti(d.string("CB"), symbol="__RTTI__2CB"), [b0, b0 + 0], symbol="__vt__2CB")
            rs = r.fn("FUN_x", 0x80)
            r.vtable(r.rtti(r.string("CA")), [rs, rs])
            r.vtable(r.rtti(r.string("CB")), [rs, rs])
        d, r, pairs = world(extra)
        _res, out = run(d, r, pairs)
        self.assertFalse([x for x in out.rows if x["Mangled"].startswith("Update__")])
        self.assertEqual(out.refused["shared body named differently"], 1)

    def test_a_shared_body_only_one_vtable_names_is_refused(self):
        def extra(d, r, pairs):
            a0, a1 = d.fn("X__2CAFv", 0x80), d.fn("Y__2CAFv", 0x80)
            d.vtable(d.rtti(d.string("CA"), symbol="__RTTI__2CA"), [a0, a1], symbol="__vt__2CA")
            rs, r1, r2 = r.fn("FUN_x", 0x80), r.fn("FUN_x", 0x80), r.fn("FUN_x", 0x80)
            r.vtable(r.rtti(r.string("CA")), [rs, r1])
            r.vtable(r.rtti(r.string("CNew")), [rs, r2])       # a retail-only class shares it
        d, r, pairs = world(extra)
        _res, out = run(d, r, pairs)
        self.assertNotIn("X__2CAFv", {x["Mangled"] for x in out.rows})
        self.assertIn("Y__2CAFv", {x["Mangled"] for x in out.rows})
        self.assertEqual(out.refused["shared body, one vtable names it"], 1)

    def test_a_target_already_named_in_a_task7_file_is_skipped_and_the_agreement_counted(self):
        d, r, pairs = world()
        _res, out = run(d, r, pairs, named_files={0x200000: "Draw__Q23zdb5CNodeFv"},
                        task7={0x200000: ("Draw__Q23zdb5CNodeFv", "exact"),
                               0x200080: ("Tick__Q23zdb5CNodeFv", "exact")})
        self.assertNotIn(0x200000, by_addr(out))
        self.assertEqual(out.refused["already named (Task 7 / 7b file)"], 1)
        self.assertEqual(out.checks["Task 7 / 7b file: same name"], 1)

    def test_a_disagreement_with_a_task7_pair_is_refused_and_reported(self):
        d, r, pairs = world()
        _res, out = run(d, r, pairs, task7={0x2000e0: ("Other__Q23zdb5CNodeFv", "prefix")})
        self.assertNotIn(0x2000e0, by_addr(out))
        self.assertEqual(out.refused["contradicts a Task 7 pair"], 1)
        self.assertEqual(len(out.findings), 1)
        self.assertIn("Other__Q23zdb5CNodeFv", out.findings[0])

    def test_a_prefix_pair_the_slot_confirms_is_admitted_and_counted(self):
        d, r, pairs = world()
        _res, out = run(d, r, pairs, task7={0x2000e0: ("Kill__Q23zdb5CNodeFv", "prefix")})
        self.assertIn(0x2000e0, by_addr(out))
        self.assertEqual(out.checks["Task 7 pair not in the files, same name (prefix)"], 1)
        self.assertEqual(out.checks["written: confirms a Task 7 prefix pair (S12-R3)"], 1)

    def test_a_row_that_is_not_a_placeholder_is_refused(self):
        d, r, pairs = world()
        rows = [(s, e, "hand_named" if s == 0x200000 else "FUN_%08x" % s) for s, e, _n in r.funcs]
        res = vl.resolve_classes(d.elf(), r.segments(), {s for s, _e, _n in rows})
        out = vl.propose(res, d.elf().functions, rows, pairs)
        self.assertNotIn(0x200000, by_addr(out))
        self.assertEqual(out.refused["our row already named (csv)"], 1)

    def test_a_body_under_64_bytes_is_refused(self):
        def extra(d, r, pairs):
            d0, d1 = d.fn("Big__6CSmallFv", 0x80), d.fn("Tiny__6CSmallFv", 0x20)
            r0, r1 = r.fn("FUN_x", 0x80), r.fn("FUN_x", 0x20)
            d.vtable(d.rtti(d.string("CSmall"), symbol="__RTTI__6CSmall"), [d0, d1],
                     symbol="__vt__6CSmall")
            r.vtable(r.rtti(r.string("CSmall")), [r0, r1])
        d, r, pairs = world(extra)
        _res, out = run(d, r, pairs)
        names = {x["Mangled"] for x in out.rows}
        self.assertIn("Big__6CSmallFv", names)
        self.assertNotIn("Tiny__6CSmallFv", names)
        self.assertEqual(out.refused["body under 64 bytes"], 1)

    def test_a_size_ratio_under_half_is_refused(self):
        def extra(d, r, pairs):
            d0, d1 = d.fn("Big__6CRatioFv", 0x80), d.fn("Grew__6CRatioFv", 0x40)
            r0, r1 = r.fn("FUN_x", 0x80), r.fn("FUN_x", 0x100)
            d.vtable(d.rtti(d.string("CRatio"), symbol="__RTTI__6CRatio"), [d0, d1],
                     symbol="__vt__6CRatio")
            r.vtable(r.rtti(r.string("CRatio")), [r0, r1])
        d, r, pairs = world(extra)
        _res, out = run(d, r, pairs)
        self.assertNotIn("Grew__6CRatioFv", {x["Mangled"] for x in out.rows})
        self.assertEqual(out.refused["size ratio under 0.50"], 1)

    def test_an_identifier_already_spent_is_refused(self):
        d, r, pairs = world()
        _res, out = run(d, r, pairs, taken=["Draw__Q23zdb5CNodeFv"])
        self.assertNotIn(0x200000, by_addr(out))
        self.assertEqual(out.refused["identifier already spent or collides"], 1)

    def test_the_proposed_column_is_a_legal_identifier(self):
        def extra(d, r, pairs):
            d0, d1 = d.fn("F__Q23std8ctype<c>Fv", 0x80), d.fn("G__Q23std8ctype<c>Fv", 0x80)
            d.vtable(d.rtti(d.string("std::ctype<char>"), symbol="__RTTI__Q23std8ctype<c>"),
                     [d0, d1], symbol="__vt__Q23std8ctype<c>")
            r0, r1 = r.fn("FUN_x", 0x80), r.fn("FUN_x", 0x80)
            r.vtable(r.rtti(r.string("std::ctype<char>")), [r0, r1])
        d, r, pairs = world(extra)
        _res, out = run(d, r, pairs)
        row = [x for x in out.rows if x["Mangled"] == "F__Q23std8ctype<c>Fv"][0]
        self.assertEqual(row["Proposed"], "F__Q23std8ctype_c_Fv")
        self.assertEqual(row["Class"], "std::ctype<char>")


class HoldsTest(unittest.TestCase):
    def test_a_held_fixed_point_is_ignored_and_a_held_target_refused(self):
        d, r, pairs = world()
        # holding the fixed point's DEMO address (0x100080) leaves CNode with no fixed point: equal
        # counts, so it is named whole -- slot 1 becomes a proposal; slot 0's target is held, refused
        _res, out = run(d, r, pairs, held={0x100080, 0x200000})
        rows = by_addr(out)
        self.assertEqual(sorted(rows), [0x200080, 0x2000e0])
        self.assertEqual(rows[0x2000e0]["FixedPoints"], "start..end")
        self.assertEqual(out.refused["held"], 1)
        self.assertEqual(out.census["fixed points"], 0)
        res = vl.resolve_classes(d.elf(), r.segments(), {s for s, _e, _n in r.funcs})
        self.assertEqual(vl.holdout(res.vtables, pairs, held={0x200080})["fixed points"], 0)


class HoldoutTest(unittest.TestCase):
    def test_leave_one_out_re_derives_the_fixed_point(self):
        d, r, pairs = world()
        res = vl.resolve_classes(d.elf(), r.segments(), {s for s, _e, _n in r.funcs})
        got = vl.holdout(res.vtables, pairs)
        self.assertEqual((got["fixed points"], got["reached"], got["right"], got["wrong"]),
                         (1, 1, 1, 0))

    def test_the_wrong_counter_counts(self):
        # demo [a, X, b, c], retail [a', b', X', c']: X is a fixed point at (1, 2), c at (3, 3).
        # Dropping X leaves an equal run start..3:3 of three slots, which puts X at 1: wrong.
        vt = vl.ResolvedVtable("C", "primary", 0, (1, 2, 3, 4), 0, (11, 13, 12, 14), "__vt__1C")
        got = vl.holdout([vt], {2: 12, 4: 14})
        self.assertEqual(got["wrong"], 1)


class FileTest(unittest.TestCase):
    def test_the_header_carries_the_rule_and_the_columns_are_the_briefs(self):
        d, r, pairs = world()
        _res, out = run(d, r, pairs)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "renames_7c.csv")
            vl.write_proposals_7c(path, out.rows, ["holdout: 1 fixed points, 1 right, 0 wrong"])
            with open(path) as fh:
                text = fh.read()
        header = [line for line in text.splitlines() if line.startswith("#")]
        self.assertIn(vl.VTABLE_RULE.split(". ")[0], " ".join(h[2:] for h in header))
        self.assertIn("# holdout: 1 fixed points, 1 right, 0 wrong", header)
        body = list(csv.DictReader(line for line in text.splitlines() if not line.startswith("#")))
        self.assertEqual(list(body[0].keys()), vl.PROPOSAL_COLUMNS_7C)
        self.assertEqual(vl.PROPOSAL_COLUMNS_7C,
                         ["Address", "Current", "Proposed", "Mangled", "Score", "How", "Size",
                          "Class", "Slot", "FixedPoints", "DemoAddr", "DemoSize", "OurSize", "Ratio"])

    def test_the_cli_says_no_data_without_its_inputs(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = vl.main(["/nonexistent/a", "/nonexistent/b", "/nonexistent/c",
                            "/nonexistent/d", "--out", "/nonexistent/x.csv"])
        self.assertEqual(code, 2)
        self.assertIn("NO-DATA: missing /nonexistent/d", out.getvalue())


if __name__ == "__main__":
    unittest.main()
