"""Sprint 12 Task 14 -- the `ui-binding` lever (tools_py/ui_binding_lever; research/55 sec 4.2, S12-R15).

The fixture is a synthetic image pair: a code segment of tiny functions and a data segment holding the
command strings and a table of [id, string pointer, function pointer] rows (the demo's stride-12 shape) or
[id, string pointer, function pointer, 0] rows (r0001's stride 16). Every command string here is invented;
no game bytes, no disc, no demo, no ELF on disk.
"""
import csv
import os
import struct
import tempfile
import unittest

from tools_py import address_matcher as am
from tools_py import ui_binding_lever as ui

CODE = 0x100000
DATA = 0x200000
TABLE = DATA + 0x100
STRINGS = DATA + 0x1000
FSIZE = 0x10
DEMO_SIG = "__FP13C2DAnimCmdHdrPf"


def _word(w):
    return struct.pack("<I", w & 0xFFFFFFFF)


def build(commands, stride=12, names=None, bad_fn_row=None, gap_after=None):
    """(side, [function address per row]) for an image whose table binds `commands` in order.

    `names[i]` names row i's handler (default `FUN_<addr>`); `bad_fn_row` makes that row's function word
    point 4 bytes into its function (not a start); `gap_after` puts a zero row after that index."""
    n = len(commands)
    code = b"".join(_word(0x24020000 | i) + _word(0x03E00008) + _word(0) + _word(0) for i in range(n))
    funcs = []
    for i in range(n):
        start = CODE + i * FSIZE
        name = names[i] if names and names[i] else "FUN_%08x" % start
        funcs.append((start, start + FSIZE, name))
    strings = b""
    sptr = []
    for c in commands:
        sptr.append(STRINGS + len(strings))
        strings += c.encode("latin1") + b"\x00"
        while len(strings) % 4:
            strings += b"\x00"
    table = b""
    fptr = []
    for i in range(n):
        if gap_after is not None and i == gap_after + 1:
            table += b"\x00" * stride
        fn = CODE + i * FSIZE + (4 if i == bad_fn_row else 0)
        fptr.append(fn)
        row = _word(i + 1) + _word(sptr[i]) + _word(fn)
        table += row + b"\x00" * (stride - len(row))
    data = bytearray(0x1000 + len(strings))
    data[0x100:0x100 + len(table)] = table
    data[0x1000:] = strings
    return am.Side(funcs, [(CODE, code), (DATA, bytes(data))]), fptr


def cmds(n, stem="Zq"):
    return ["%sCommand%02d" % (stem, i) for i in range(n)]


class FindTables(unittest.TestCase):
    def test_a_run_is_found_with_its_row_start_and_stride(self):
        side, fptr = build(cmds(10))
        tables = ui.find_binding_tables(side)
        self.assertEqual(len(tables), 1)
        t = tables[0]
        self.assertEqual((t.addr, t.stride, len(t.rows)), (TABLE, 12, 10))
        self.assertEqual(t.rows[0].string, b"ZqCommand00")
        self.assertEqual([r.function for r in t.rows], fptr)

    def test_the_stride_16_shape_is_found(self):
        side, _ = build(cmds(9), stride=16)
        (t,) = ui.find_binding_tables(side)
        self.assertEqual((t.addr, t.stride, len(t.rows)), (TABLE, 16, 9))

    def test_a_run_shorter_than_eight_is_ignored(self):
        side, _ = build(cmds(7))
        self.assertEqual(ui.find_binding_tables(side), [])

    def test_a_function_word_that_is_not_a_start_ends_the_run(self):
        side, _ = build(cmds(12), bad_fn_row=8)
        (t,) = ui.find_binding_tables(side)
        self.assertEqual(len(t.rows), 8)
        self.assertEqual(t.rows[-1].string, b"ZqCommand07")

    def test_an_array_of_function_pointers_is_not_a_table(self):
        # a function start whose first bytes happen to read as a short C string is code, not a command
        n = 24                    # 23 (pointer, pointer) pairs: stride-8 runs of 12 and 11
        code = b"".join(b"g\x00\x00\x24" + _word(0x03E00008) + _word(0) + _word(0) for _ in range(n))
        funcs = [(CODE + i * FSIZE, CODE + (i + 1) * FSIZE, "FUN_%08x" % (CODE + i * FSIZE)) for i in range(n)]
        data = b"".join(_word(CODE + i * FSIZE) for i in range(n))
        side = am.Side(funcs, [(CODE, code), (DATA, data)])
        self.assertEqual(ui.find_binding_tables(side), [])

    def test_two_runs_split_by_a_zero_row(self):
        side, _ = build(cmds(20), gap_after=9)
        self.assertEqual(sorted(len(t.rows) for t in ui.find_binding_tables(side)), [10, 10])


def table(pairs, base=TABLE, fbase=CODE):
    """A Table straight from [(command, handler name)]; handler addresses are fbase + 16 * i."""
    rows = tuple(ui.Row(base + 4 + 12 * i, c.encode("latin1"), fbase + FSIZE * i, n)
                 for i, (c, n) in enumerate(pairs))
    return ui.Table(base, 12, 4, rows)


def ours(commands, names=None):
    return table([(c, (names or {}).get(c) or "FUN_%08x" % (0x300000 + FSIZE * i))
                  for i, c in enumerate(commands)], base=0x400000, fbase=0x300000)


def addr_of(t, command):
    return next(r.function for r in t.rows if r.string == command.encode())


class Join(unittest.TestCase):
    def setUp(self):
        self.demo = table([("ZqAlpha", "UIZqAlpha" + DEMO_SIG), ("ZqBravo", "UIZqBravo" + DEMO_SIG),
                           ("ZqAnon", "OnZqAnon__24@unnamed@zq_menu_cpp@FP13C2DAnimCmdHdrPf")])

    def test_a_joined_row_proposes_the_demo_name(self):
        our = ours(["ZqBravo", "ZqAlpha"])
        res = ui.join(self.demo, our)
        by = {r["Address"]: r for r in res.rows}
        row = by["0x%08x" % addr_of(our, "ZqAlpha")]
        self.assertEqual(row["Pass"], "ui-binding")
        self.assertEqual(row["Score"], "0.90")
        self.assertEqual(row["Mangled"], "UIZqAlpha" + DEMO_SIG)
        self.assertEqual(row["Proposed"], "UIZqAlpha" + DEMO_SIG)
        self.assertEqual(row["Evidence"], "binding table row: command ZqAlpha -> demo UIZqAlpha" + DEMO_SIG)
        self.assertEqual(row["DemoAddr"], "0x%08x" % addr_of(self.demo, "ZqAlpha"))
        self.assertEqual(res.census["joined"], 2)
        self.assertEqual(res.derived, [])

    def test_an_anonymous_namespace_demo_handler_still_proposes_and_is_counted_apart(self):
        res = ui.join(self.demo, ours(["ZqAnon", "ZqAlpha"]))
        self.assertEqual(len(res.rows), 2)
        self.assertEqual(res.census["proposed from an anonymous-namespace demo handler"], 1)
        anon = [r for r in res.rows if "@unnamed@" in r["Mangled"]][0]
        self.assertNotIn("@", anon["Proposed"])

    def test_a_command_not_unique_on_either_side_is_refused_and_counted(self):
        demo = table(list(self.demo_pairs()) + [("ZqAlpha", "UIZqAlphaTwo" + DEMO_SIG)])
        res = ui.join(demo, ours(["ZqAlpha", "ZqBravo", "ZqBravo"]))
        self.assertEqual(res.rows, [])
        self.assertEqual(res.derived, [])
        self.assertEqual(res.held["command not unique in the demo table"], 1)
        self.assertEqual(res.held["command not unique in our table"], 2)

    def demo_pairs(self):
        return [(r.string.decode(), r.name) for r in self.demo.rows]

    def test_a_one_side_only_command_gets_a_derived_name(self):
        our = ours(["ZqAlpha", "ZqOnly-One"])
        res = ui.join(self.demo, our)
        self.assertEqual(len(res.rows), 1)
        (d,) = res.derived
        self.assertEqual(d["Address"], "0x%08x" % addr_of(our, "ZqOnly-One"))
        self.assertEqual(d["Proposed"], "UIZqOnly_One")          # sanitised through c_identifier
        self.assertEqual(d["Pass"], "ui-binding-derived")
        self.assertEqual(d["Score"], "0.80")
        self.assertEqual(d["Mangled"], "")
        self.assertEqual(d["Evidence"], "derived from the command string ZqOnly-One; no demo counterpart")

    def test_a_handler_already_named_is_refused(self):
        res = ui.join(self.demo, ours(["ZqAlpha", "ZqNew"], names={"ZqAlpha": "HandNamed", "ZqNew": "Other"}))
        self.assertEqual((res.rows, res.derived), ([], []))
        self.assertEqual(res.held["our handler is already named"], 2)

    def test_a_sidecar_name_counts_as_already_named(self):
        our = ours(["ZqAlpha"])
        res = ui.join(self.demo, our, named={addr_of(our, "ZqAlpha"): "FromSidecar"})
        self.assertEqual(res.rows, [])
        self.assertEqual(res.held["our handler is already named"], 1)

    def test_task7_agreement_and_disagreement(self):
        our = ours(["ZqAlpha", "ZqBravo"])
        a, b = addr_of(our, "ZqAlpha"), addr_of(our, "ZqBravo")
        task7 = {a: (addr_of(self.demo, "ZqAlpha"), "UIZqAlpha" + DEMO_SIG),
                 b: (addr_of(self.demo, "ZqAlpha"), "UIZqAlpha" + DEMO_SIG)}
        res = ui.join(self.demo, our, task7=task7)
        self.assertEqual(res.census["Task 7 agrees"], 1)
        self.assertEqual(res.census["Task 7 disagrees"], 1)
        self.assertEqual([r["Address"] for r in res.rows], ["0x%08x" % a])
        self.assertEqual(res.held["disagrees with a Task 7 pair"], 1)
        self.assertTrue(any("0x%08x" % b in f for f in res.findings))

    def test_a_derived_name_on_a_task7_pair_is_a_disagreement(self):
        our = ours(["ZqAlpha", "ZqOnly"])
        o = addr_of(our, "ZqOnly")
        res = ui.join(self.demo, our, task7={o: (addr_of(self.demo, "ZqBravo"), "UIZqBravo" + DEMO_SIG)})
        self.assertEqual(res.derived, [])
        self.assertEqual(res.census["Task 7 disagrees"], 1)
        self.assertEqual(res.held["disagrees with a Task 7 pair"], 1)
        self.assertTrue(any("0x%08x" % o in f and "ZqOnly" in f for f in res.findings))

    def test_a_derived_name_task7_also_gives_agrees(self):
        our = ours(["ZqOnly"])
        o = addr_of(our, "ZqOnly")
        res = ui.join(self.demo, our, task7={o: (0x1d0000, "UIZqOnly" + DEMO_SIG)})
        self.assertEqual(len(res.derived), 1)
        self.assertEqual(res.census["Task 7 agrees"], 1)

    def test_a_task7_pair_on_a_held_address_does_not_block_the_join(self):
        our = ours(["ZqAlpha", "ZqOnly"])
        a, o = addr_of(our, "ZqAlpha"), addr_of(our, "ZqOnly")
        wrong = {o: (addr_of(self.demo, "ZqAlpha"), "UIZqAlpha" + DEMO_SIG)}   # a wrong anchor on ZqOnly
        res = ui.join(self.demo, our, task7=wrong, holds={o: "UIZqAlpha" + DEMO_SIG})
        self.assertEqual([r["Address"] for r in res.rows], ["0x%08x" % a])
        self.assertEqual([r["Address"] for r in res.derived], ["0x%08x" % o])
        self.assertEqual(res.census["Task 7 pair overridden by a hold"], 2)
        self.assertNotIn("Task 7 disagrees", res.census)
        self.assertEqual(res.held, {})

    def test_an_identifier_spent_elsewhere_is_refused_and_reported(self):
        our = ours(["ZqAlpha", "ZqBravo"])
        a = addr_of(our, "ZqAlpha")
        others = [(0x123450, "UIZqAlpha" + DEMO_SIG, "other.csv"),     # same name, another address
                  (addr_of(our, "ZqBravo"), "UIZqBravo" + DEMO_SIG, "other.csv")]  # the same pair: agrees
        res = ui.join(self.demo, our, others=others)
        self.assertEqual([r["Address"] for r in res.rows], ["0x%08x" % addr_of(our, "ZqBravo")])
        self.assertEqual(res.held["identifier spent in another proposals file"], 1)
        self.assertEqual(res.census["agrees with another proposals file"], 1)
        self.assertEqual(res.census["agrees with other.csv"], 1)
        self.assertTrue(any("other.csv" in c and "0x%08x" % a in c for c in res.collisions))

    def test_two_proposals_that_sanitise_alike_are_both_refused(self):
        our = ours(["ZqX-Y", "ZqX_Y"])
        res = ui.join(self.demo, our)
        self.assertEqual(res.derived, [])
        self.assertEqual(res.held["identifier collides after sanitising"], 2)


class Header(unittest.TestCase):
    def test_the_header_carries_the_rule_the_tables_and_the_counts(self):
        demo = table([("ZqAlpha", "UIZqAlpha" + DEMO_SIG)])
        our = ours(["ZqAlpha", "ZqOnly"])
        res = ui.join(demo, our)
        lines = ui.header("game/x.csv", demo, our, res)
        text = "\n".join(lines)
        self.assertIn(ui.UI_BINDING_RULE, text.replace("\n", " "))
        self.assertIn("0x%08x" % TABLE, text)
        self.assertIn("0x00400000", text)
        self.assertIn("ui-binding 1", text)
        self.assertIn("ui-binding-derived 1", text)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.csv")
            ui.write_proposals(path, res.rows, lines)
            with open(path) as fh:
                body = fh.read()
            self.assertTrue(body.startswith("# "))
            got = list(csv.DictReader(ln for ln in body.splitlines() if not ln.startswith("#")))
            self.assertEqual(len(got), 1)
            self.assertEqual(list(got[0]), ui.COLUMNS)


if __name__ == "__main__":
    unittest.main()
