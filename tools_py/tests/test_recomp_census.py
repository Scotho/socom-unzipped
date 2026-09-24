"""tools_py/recomp_census.py on synthetic output directories and logs (Sprint 12 Task 3a).

The fake files copy the shapes ps2xRecomp emits (function_emitter.cpp generateFunction for a recompiled
function, ps2_recompiler.cpp generateOutput for a stub, recompiler_reporter.cpp printSummary for the log);
no generated game code is read.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest

from tools_py import recomp_census as rc

SIG = "(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime)"


def code_file(csv_name, identifier, start, end):
    return ('#include <stdexcept>\n#include "ps2_runtime_macros.h"\n#include "ps2_runtime.h"\n'
            '#include "ps2_recompiled_functions.h"\n#include "ps2_recompiled_stubs.h"\n\n'
            '#include "ps2_syscalls.h"\n#include "ps2_stubs.h"\n\n#ifdef PS2_FUNCTION_LOG_TRACKER\n'
            '#include "ps2_log.h"\n#endif\n\n'
            "// Function: %s\n// Address: 0x%x - 0x%x\n"
            "void %s%s {\n#ifdef PS2_FUNCTION_LOG_TRACKER\n    PS_LOG_ENTRY(\"%s\");\n#endif\n\n"
            "    ctx->pc = 0x%xu;\n\n}\n" % (csv_name, start, end, identifier, SIG, identifier, start))


def stub_file(identifier, target):
    return ('#include "ps2_runtime.h"\n#include "ps2_syscalls.h"\n#include "ps2_stubs.h"\n#ifdef _DEBUG\n'
            '#include "ps2_log.h"\n#endif\n\n'
            "void %s%s {\n#ifdef _DEBUG\n    PS_LOG_ENTRY(\"%s\");\n#endif\n"
            "    ctx->pc = getRegU32(ctx, 31);\n    ps2_stubs::%s(rdram, ctx, runtime); \n}\n"
            % (identifier, SIG, identifier, target))


REGISTER = ('#include "ps2_runtime.h"\n#include "ps2_recompiled_functions.h"\n\n'
            "void registerAllFunctions(PS2Runtime &runtime)\n{\n}\n")
HEADER = ("#ifndef PS2_RECOMPILED_FUNCTIONS_H\n#define PS2_RECOMPILED_FUNCTIONS_H\n\n"
          "void FUN_00100000_0x100000%s;\n\n#endif // PS2_RECOMPILED_FUNCTIONS_H\n" % SIG)

LOG_HEAD = ("[recompiler] parsing config\n[recompiler] recompiling 4 functions\n"
            "\n========== PS2Recomp report ==========\nUnmapped continuations: %d\nUnhandled instructions: %d\n"
            "\nEvents:\n  [info] config - Parsing toml file: socom2.toml\n")
UNHANDLED = ("  [error] unhandled-instruction function=%s addr=0x%x - Unhandled opcode: 0x13 raw=0x4d6c6c61\n")
UNMAPPED = ("  [warning] unmapped-continuation function=%s addr=0x%x - call-return 0x%x of 0x%x lies in no "
            "recompiled function; nothing can resume there\n")
LOG_TAIL = "======================================\nRecompilation completed successfully\n"


def write_run(root, files, unhandled=(), unmapped=()):
    out = os.path.join(root, "output")
    os.makedirs(out)
    for name, text in files.items():
        with open(os.path.join(out, name), "w") as fh:
            fh.write(text)
    log = os.path.join(root, "recomp_run.log")
    with open(log, "w") as fh:
        fh.write(LOG_HEAD % (len(unmapped), len(unhandled)))
        for fn, addr in unhandled:
            fh.write(UNHANDLED % (fn, addr))
        for fn, addr in unmapped:
            fh.write(UNMAPPED % (fn, addr, addr, addr - 8))
        fh.write(LOG_TAIL)
    return out, log


# run A: a FUN_ row, a JAL-scan sub_ row (decoded past its csv End), a named row, a stub, and a
# long name whose FILE name was clamped (the identifier must come from the void line).
LONG = "CZSealBody_" + "x" * 90
FILES_A = {
    "FUN_00100000_0x100000.cpp": code_file("FUN_00100000", "FUN_00100000_0x100000", 0x100000, 0x100040),
    "sub_00100040_0x100040.cpp": code_file("sub_00100040", "sub_00100040_0x100040", 0x100040, 0x100100),
    "thunk_FUN_00100100_0x100100.cpp": code_file("thunk_FUN_00100100", "thunk_FUN_00100100_0x100100",
                                                 0x100100, 0x100108),
    "entry_0x100108.cpp": code_file("entry", "entry_0x100108", 0x100108, 0x100110),
    "FUN_00100200_0x100200.cpp": stub_file("FUN_00100200_0x100200", "sceCdRead"),
    "CZSealBody_xxxx_0x100300.cpp": code_file(LONG, LONG + "_0x100300", 0x100300, 0x100320),
    "caseD_4_0x100400.cpp": code_file("caseD_4", "caseD_4_0x100400", 0x100400, 0x100410),
    "register_functions.cpp": REGISTER,
    "ps2_recompiled_functions.h": HEADER,
    "ps2_recompiled_stubs.h": "#pragma once\n",
}
UNHANDLED_A = [("FUN_00100000", 0x100010)]
UNMAPPED_A = [("sub_00100040", 0x1000f8)]

# run B: sub_00100040 renamed to a real name (its End moves in by 8), caseD_4 dropped, one new unmapped.
FILES_B = dict(FILES_A)
del FILES_B["sub_00100040_0x100040.cpp"], FILES_B["caseD_4_0x100400.cpp"]
FILES_B["CSealFoo_Update_0x100040.cpp"] = code_file("CSealFoo::Update", "CSealFoo_Update_0x100040",
                                                    0x100040, 0x1000f8)
UNMAPPED_B = UNMAPPED_A + [("CSealFoo_Update", 0x1000f8 + 4)]


class CensusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a = rc.census(*write_run(os.path.join(self.tmp.name, "a"), FILES_A, UNHANDLED_A, UNMAPPED_A))
        self.b = rc.census(*write_run(os.path.join(self.tmp.name, "b"), FILES_B, UNHANDLED_A, UNMAPPED_B))

    def tearDown(self):
        self.tmp.cleanup()

    def test_counts(self):
        a = self.a
        self.assertEqual(a["files"], 10)
        self.assertEqual(a["functions"], 7)
        self.assertEqual(a["classes"], {"FUN_": 2, "sub_": 1, "thunk_": 1, "caseD_": 1, "entry": 1, "other": 1})
        self.assertEqual(a["named"], 4)
        self.assertEqual(a["stubs"], 1)
        self.assertEqual((a["unhandled"], a["unmapped"]), (1, 1))
        self.assertEqual(a["unhandled_addrs"], [0x100010])
        self.assertEqual(a["unmapped_addrs"], [0x1000f8])
        self.assertEqual(a["duplicate_starts"], [])

    def test_extents(self):
        e = self.a["extents"]
        self.assertEqual(e[0x100040]["end"], 0x100100)
        self.assertEqual(e[0x100040]["csv_name"], "sub_00100040")
        self.assertEqual(e[0x100108]["identifier"], "entry_0x100108")
        self.assertEqual(e[0x100300]["identifier"], LONG + "_0x100300")      # not the clamped filename
        self.assertEqual(e[0x100300]["file"], "CZSealBody_xxxx_0x100300.cpp")
        stub = e[0x100200]
        self.assertEqual((stub["kind"], stub["end"], stub["csv_name"], stub["stub_target"]),
                         ("stub", None, None, "ps2_stubs::sceCdRead"))
        self.assertEqual(self.b["extents"][0x100040]["csv_name"], "CSealFoo::Update")

    def test_digest_is_order_and_path_independent(self):
        again = rc.census(*write_run(os.path.join(self.tmp.name, "a2"), FILES_A))
        self.assertEqual(again["extents_sha256"], self.a["extents_sha256"])
        self.assertNotEqual(self.b["extents_sha256"], self.a["extents_sha256"])

    def test_diff(self):
        d = rc.diff(self.a, self.b)
        self.assertEqual(d["renamed"], [(0x100040, "sub_00100040_0x100040", "CSealFoo_Update_0x100040")])
        self.assertEqual(d["extents_changed"], [(0x100040, 0x100100, 0x1000f8)])
        self.assertEqual(d["only_in_a"], [0x100400])
        self.assertEqual(d["only_in_b"], [])
        self.assertEqual(d["unmapped"], {"a": 1, "b": 2, "delta": 1, "appeared": [0x1000fc], "vanished": []})
        self.assertEqual(d["unhandled"]["delta"], 0)
        self.assertEqual(d["unhandled"]["appeared"], [])
        self.assertEqual(d["files"], (10, 9))
        self.assertFalse(d["r11_ok"])
        self.assertTrue(rc.diff(self.a, self.a)["r11_ok"])

    def test_json_round_trip_and_cli(self):
        ja, jb = os.path.join(self.tmp.name, "a.json"), os.path.join(self.tmp.name, "b.json")
        root_a = os.path.join(self.tmp.name, "a")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc.main([os.path.join(root_a, "output"), os.path.join(root_a, "recomp_run.log"), "--json", ja])
        self.assertIn("recomp: 10 files, unhandled=1, unmapped=1;", buf.getvalue())
        self.assertIn("FUN_=2 sub_=1 named=4", buf.getvalue())
        with open(jb, "w") as fh:
            json.dump(rc.to_json(self.b), fh)
        self.assertEqual(rc.load(ja)["extents"], self.a["extents"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc.main(["--diff", ja, jb])
        out = buf.getvalue()
        self.assertIn("renamed: 1", out)
        self.assertIn("0x100040 sub_00100040_0x100040 -> CSealFoo_Update_0x100040", out)
        self.assertIn("extents_changed: 1", out)
        self.assertIn("only_in_a: 1", out)
        self.assertIn("unmapped: 1 -> 2 (delta +1), appeared 1, vanished 0", out)
        self.assertIn("S12-R11 (no function dropped, no new unmapped/unhandled): FAIL", out)


if __name__ == "__main__":
    unittest.main()
