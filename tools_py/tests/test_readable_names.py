"""Sprint 12 Task 1 -- the readable-name renderer (tools_py/readable_names.py; research/47 R1-R12, S12-R14).

One test per rule of research/47's "The recommended rule set", each on the note's own example names, plus
the S12-R14 amendment to R6 (strip a leading underscore run the live sanitiser would rewrite; fall back to
research/47's `u`xk spelling only on a case-insensitive collision), the replicas of the recompiler's two
sanitisers against expectations read off the C++, and the final invariant. Names only: no test reads game/.
"""
import hashlib
import unittest

from tools_py import readable_names as rn


def sha(mangled, n):
    return hashlib.sha1(mangled.encode()).hexdigest()[:n]


class Rules(unittest.TestCase):
    def test_r1_thunks(self):
        self.assertEqual(rn.readable("@272@__dt__10CZSealBodyFv"), "CZSealBody_dtor_thunk272")
        self.assertEqual(rn.readable("@8@72@__dt__Q23std39basic_ostream<c,Q23std14char_traits<c>>Fv"),
                         "std_basic_ostream_dtor_thunk8_72")

    def test_r2_split(self):
        self.assertEqual(rn.readable("__end__catch"), "end_catch")          # plain: the tail does not parse
        self.assertEqual(rn.readable("foo__bar"), "foo_bar")
        self.assertEqual(rn.readable("Mul__5CQuatCFPC5CQuatP5CQuat"), "CQuat_Mul")
        self.assertEqual(rn.readable("sceCdRead"), "sceCdRead")

    def test_r3_class_path(self):
        self.assertEqual(rn.readable("__ct__Q23zdb5CNodeFv"), "zdb_CNode_ctor")
        self.assertEqual(rn.readable("swap__Q23std30vector<b,Q23std12allocator<b>>Fv"), "std_vector_swap")
        self.assertEqual(rn.readable("Advance__Q224@unnamed@zanim_menu_cpp@17CSelectedCharsItrFv"),
                         "anon_zanim_menu_CSelectedCharsItr_Advance")
        self.assertEqual(rn.readable("ReadBtnName__Q213CCtrlrConfigs23_$798fts_controller_cppFPCc"),
                         "CCtrlrConfigs_local798_ReadBtnName")

    def test_r4_function_part(self):
        self.assertEqual(rn.readable("__pl__6CPnt3DCFRC6CPnt3D"), "CPnt3D_op_add")
        self.assertEqual(rn.readable("__dla__FPv"), "op_delete_array")
        self.assertEqual(rn.readable("__opf__6RfloatCFv"), "Rfloat_op_conv_f")
        self.assertEqual(rn.readable("__opUi__Q210Metrowerks12number<Ui,1>CFv"), "Metrowerks_number_op_conv_Ui")
        self.assertEqual(rn.readable("DrawFunc<11CDynGrenade>__2aiFQ22ai9LINE_TYPEffUi11CDynGrenade"),
                         "ai_DrawFunc")
        self.assertEqual(rn.readable("__defctor__Q23zdb11DiIntersectFv"), "zdb_DiIntersect_defctor")

    def test_r5_plain_forms(self):
        self.assertEqual(rn.readable("__sinit_ent_main.cpp"), "sinit_ent_main")
        self.assertEqual(rn.readable("__sinit"), "sinit")
        self.assertEqual(rn.readable("__arraydtor$1955"), "arraydtor_1955")

    def test_r6_leading_underscores(self):
        # research/47's u x k spelling, used by render only as the S12-R14 collision fallback
        got = rn.render(["_Exit", "Exit", "__divdi3", "divdi3", "_delete_vec"])
        self.assertEqual(got.names, {"_Exit": "u_Exit", "Exit": "Exit", "__divdi3": "uu_divdi3",
                                     "divdi3": "divdi3", "_delete_vec": "_delete_vec"})

    def test_r7_sanitise(self):
        self.assertEqual(rn.readable("a.b-c__"), "a_b_c")
        self.assertEqual(rn.readable("x$$y"), "x_y")

    def test_r8_guards(self):
        self.assertEqual(rn.readable("main"), "ps2_main")
        self.assertEqual(rn.readable("delete"), "ps2_delete")
        self.assertEqual(rn.readable("3dsInit"), "fn_3dsInit")

    def test_r9_overloads(self):
        got = rn.render(["SetUV__13C2DBitmapPolyFffff", "SetUV__13C2DBitmapPolyFffffffff",
                         "Draw__13C2DBitmapPolyFv",
                         "__ct__9CAiMapLocFRC9CAiMapLoc", "__ct__9CAiMapLocFUiUiUi"])
        self.assertEqual(got.names["SetUV__13C2DBitmapPolyFffff"], "C2DBitmapPoly_SetUV_ffff")
        self.assertEqual(got.names["SetUV__13C2DBitmapPolyFffffffff"], "C2DBitmapPoly_SetUV_ffffffff")
        self.assertEqual(got.names["Draw__13C2DBitmapPolyFv"], "C2DBitmapPoly_Draw")      # no collision
        self.assertEqual(got.names["__ct__9CAiMapLocFRC9CAiMapLoc"], "CAiMapLoc_ctor_RC9CAiMapLoc")
        self.assertEqual(got.names["__ct__9CAiMapLocFUiUiUi"], "CAiMapLoc_ctor_UiUiUi")
        # case-insensitive, and (i) cannot split `v`/`v`: (ii) for the whole group
        tick, Tick = "tick__8CMissionFv", "Tick__8CMissionFv"
        got = rn.render([Tick, tick])
        self.assertEqual(got.names, {Tick: "CMission_Tick_" + sha(Tick, 6), tick: "CMission_tick_" + sha(tick, 6)})
        self.assertEqual(rn.overload_suffix("SetUV__13C2DBitmapPolyFffff", "args"), "ffff")
        self.assertEqual(rn.overload_suffix(Tick, "hash"), sha(Tick, 6))
        # never a name in `taken`, case-insensitively
        self.assertEqual(rn.render(["Foo__3BarFi"], taken=["bar_foo"]).names, {"Foo__3BarFi": "Bar_Foo_i"})

    def test_r10_one_name_several_addresses(self):
        got = rn.render(["_request_end", "_request_end"], demo_counts={"_request_end": 2})
        self.assertEqual(got.names, {"_request_end": "_request_end"})
        self.assertEqual(got.counts["_request_end"], 2)
        exc = "__dt__Q23std9exceptionFv"
        got = rn.render([exc] * 8, demo_counts={exc: 1})
        self.assertEqual(got.names, {})
        self.assertIn("R10", got.refused[exc])
        self.assertEqual(rn.render([exc] * 8, demo_counts={exc: 8}).names, {exc: "std_exception_dtor"})

    def test_r11_length(self):
        long = "x" * 90
        got = rn.render([long, "y" * 87]).names
        self.assertEqual(got[long], "x" * 78 + "_" + sha(long, 8))
        self.assertEqual(len(got[long]), 87)
        self.assertEqual(got["y" * 87], "y" * 87)

    def test_r12_scope(self):
        self.assertEqual(rn.readable("FUN_12345678"), "FUN_12345678")       # never rendered
        got = rn.render(["_FUN_12345678", "FUN_00181234", "caseD_6"])
        self.assertEqual(got.names, {})
        self.assertIn("R12", got.refused["_FUN_12345678"])                  # renders into the placeholder space
        self.assertIn("R12", got.refused["FUN_00181234"])
        self.assertIsNotNone(rn.is_legal("thunk_EXT_FUN_09481d98"))


class S12R14(unittest.TestCase):
    def test_s12_r14_strip(self):
        for mangled, want in (("__divdi3", "divdi3"), ("__ieee754_acosf", "ieee754_acosf"), ("_Exit", "Exit"),
                              ("__sinit_ent_main.cpp", "sinit_ent_main"), ("_printf", "_printf"),
                              ("_delete_vec", "_delete_vec")):
            self.assertEqual(rn.readable(mangled), want, mangled)
        self.assertEqual(rn.render(["_Exit", "__divdi3", "_printf"]).names,
                         {"_Exit": "Exit", "__divdi3": "divdi3", "_printf": "_printf"})

    def test_s12_r14_collision_fallback(self):
        # only the stripped name falls back, and only when its stripped spelling meets another name
        got = rn.render(["_Exit", "Exit", "__ieee754_acosf"])
        self.assertEqual(got.names, {"_Exit": "u_Exit", "Exit": "Exit", "__ieee754_acosf": "ieee754_acosf"})
        self.assertEqual(rn.render(["_Exit"], taken=["exit"]).names, {"_Exit": "u_Exit"})
        self.assertEqual(rn.render(["_Exit", "__Exit"]).names, {"_Exit": "u_Exit", "__Exit": "uu_Exit"})


class Sanitisers(unittest.TestCase):
    """Expected outputs read off ps2_recompiler.cpp:36-79,2190 and code_generator.cpp:35-99,181."""

    def test_sanitize_recomp(self):
        for name, want in (("", ""), ("main", "ps2_main"), ("delete", "ps2_delete"), ("int", "ps2_int"),
                           ("__divdi3", "ps2___divdi3"), ("_Exit", "ps2__Exit"), ("_printf", "_printf"),
                           ("3dInit", "_3dInit"), ("foo.cpp", "foo_cpp"), ("a<b>", "a_b_"),
                           ("@272@x", "_272_x"), ("é", "ps2___"), ("Main", "Main"), ("_", "_"),
                           (".L1", "ps2__L1"), ("1", "_1"), ("ps2_main", "ps2_main")):
            self.assertEqual(rn.sanitize_recomp(name), want, repr(name))

    def test_sanitize_codegen(self):
        self.assertEqual(len(rn.KEYWORDS), 92)
        for name, want in (("", ""), ("main", "ps2_main"), ("delete", "ps2_delete"), ("int", "ps2_int"),
                           ("__divdi3", "ps2__divdi3"), ("_Exit", "ps2_Exit"), ("_printf", "ps2_printf"),
                           ("3dInit", "ps2_3dInit"), ("foo.cpp", "foo_cpp"), ("a<b>", "a_b_"),
                           ("é", "ps2__"), ("_", "ps2_"), (".L1", "ps2_L1"),
                           ("CPnt3D_op_add", "CPnt3D_op_add")):
            self.assertEqual(rn.sanitize_codegen(name), want, repr(name))


class Invariant(unittest.TestCase):
    def test_is_legal(self):
        self.assertIsNone(rn.is_legal("CPnt3D_op_add"))
        self.assertIsNone(rn.is_legal("_printf"))           # S12-R14/R19: the live path keeps `_x`
        self.assertIn("live sanitiser", rn.is_legal("__printf"))   # the live path rewrites `__x`
        for bad in ("CON", "nul", "Com1", "LPT9", "__divdi3", "_Exit", "main", "a.b", "x" * 88, "", "FUN_00181234"):
            self.assertIsNotNone(rn.is_legal(bad), bad)
        self.assertIsNone(rn.is_legal("CONSOLE"))

    def test_device_names_refused(self):
        got = rn.render(["CON", "aux", "COM1", "CONSOLE"])
        self.assertEqual(got.names, {"CONSOLE": "CONSOLE"})
        for m in ("CON", "aux", "COM1"):
            self.assertIn("device", got.refused[m])

    def test_render_outputs_hold_the_invariant(self):
        names = ["SetUV__13C2DBitmapPolyFffff", "SetUV__13C2DBitmapPolyFffffffff", "_Exit", "Exit", "main",
                 "Tick__8CMissionFv", "tick__8CMissionFv", "__sinit_ent_main.cpp", "x" * 120, "_printf"]
        got = rn.render(names, taken=["C2DBitmapPoly_SetUV_ffff_x"])
        self.assertEqual(set(got.names) | set(got.refused), set(names))
        outs = list(got.names.values())
        self.assertEqual(len({n.lower() for n in outs}), len(outs))
        for n in outs:
            self.assertIsNone(rn.is_legal(n), n)


if __name__ == "__main__":
    unittest.main()
