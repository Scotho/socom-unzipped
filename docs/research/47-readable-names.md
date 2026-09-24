# 47. The readable-name scheme, proven over the four name sets

Date: 2026-09-24. Sprint 12 research wave, question 2 of the handoff's §4
(`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`). It tests the rules of the design's §1.2
(`docs/superpowers/specs/2026-09-24-sprint-12-the-readable-image-design.md`) and confirms or overturns each one.
Read-only: one ELF's `.symtab`, two proposals files, the csv, the toml, and the recompiler's C++ source. No game was
run and nothing under `recomp/` changed. Names, addresses and counts only. No game bytes appear here.

**The one-line answer: the §1.2 scheme works with six changes. Leading underscores become a `u` prefix instead of
being stripped. The overload suffix is the argument list where that splits the group and a six-hex hash where it
does not. One demo name at several addresses is kept only when the demo itself has it that often. `@n@` thunks,
`$` locals and `__op<type>` conversions get rules of their own. The cap is 87 characters, not 96. Hand names go
through the same rendering. With these rules the 894 non-auto names that would coexist in the csv give 0 sanitiser
alterations, 0 illegal or case-colliding filenames and 0 unresolved collisions, apart from 6 names over 22 rows
that are refused. Those 22 rows are 3 duplicated hand names, 2 cases where Task 7 and the toml disagree, and 1 toml
name placed at 8 addresses.** Two claims in §1.1/§1.2 are wrong about the recompiler (see "Where this overturns the
spec").

Every number below comes from one command, and each figure is tagged with the output section (§0 to §8) that
prints it:

```
python3 tools_py/research/symbols/readable_proof.py            # about 3 s; --list prints every list in full
```

Its inputs are `game/demo_scus_972_05/SCUS_972.05` (git-ignored), `game/demo_symbol_renames.csv`,
`game/demo_symbol_renames_7b.csv` (both git-ignored), `recomp/socom2_ghidra.csv`, `recomp/socom2_ghidra_r0004.csv`
(address range only) and `recomp/socom2.toml`. It writes nothing. The script holds a verbatim copy of the peer's
`readable()` sketch, called "sketch" below, and the final rule, R1–R12, which is listed at the end of this note.

## 0. The four sets

| set | what | size (§0) |
|---|---|---|
| **A** | the proposals' `Mangled` column | 485 (479 Task 7 + 6 Task 7b) |
| **B** | the demo's function names | 9,703 |
| **C** | the toml's `name@addr` entries | 656 addresses, 640 distinct names; `stubs` 223 (26 with a leading `_`), `untracked_stubs` 433 (234 with a leading `_`) |
| **D** | A + C + the csv's 113 non-`FUN_`/`thunk_FUN_` rows, merged by address (non-auto hand > proposal > toml > auto), **csv row starts only** | 936 addresses: 479 + 6 proposals, 70 hand, 339 toml, 42 auto |

- **The "113 hand names" are 70 hand names and 43 auto names** (§0). Measured with §1.3's own auto list
  (`FUN_ LAB_ thunk_FUN_ caseD_ sub_ entry`), 42 of the 113 are `caseD_*` and 1 is `entry`. The 113 is
  `ghidra_symbol_match.is_anonymous`'s count, which only excludes `FUN_`/`thunk_FUN_`.
- **41 toml addresses are not csv row starts** (§0), for example `sceCdInitEeCB@0x18ddf8`, `fclose@0x192ca8`,
  `_start@0x18011c` and `kCopy@0x1ac0d0` (§8). No name can be applied at those addresses unless a row is added first, so
  they are left out of D.
- Same address, different name: 2 (§0). At `0x1a3448`, Task 7 says `setD3_CHCR` and the toml says `setD4_CHCR`
  (Task 7 is kept). At `0x180008`, the toml's `_start` replaces the auto name `entry`. A and C give the same name to
  the same address 275 times (§0).

## 1. Distinct readable names and collisions before any suffix

Each cell is distinct names, then colliding names / functions (§1).

| set | sketch | final R1–R8 |
|---|---|---|
| A (485) | 483; 2 / 4 | 483; 2 / 4 (`C2DBitmapPoly_SetUV`, `CAiMapLoc_ctor`) |
| B (9,703) | 9,351; **255 / 607** | 8,524; **353 / 1,532** |
| C (656) | 640; 7 / 23 | 640; 7 / 23 |
| D (936) | 892; 11 / 32 | 892; 11 / 32 |

- The spec's "255 colliding names over 607 functions" is the **sketch's** figure. The sketch does not do what §1.2
  says: it keeps template arguments inside class-path components (`std___vector_pod_Ui_Q23std13allocator_Ui__`),
  and it never splits a free C++ function, so 881 `fn__F…` names keep their whole argument list (§7). Apply §1.2
  as written and B has **353 / 1,532**.
- Worst 12 under the final rendering for B (§1): `std_vector_deleter_dtor` 57,
  `Metrowerks_details_compressed_pair_imp_first` 56, `std_vector_deleter_clear` 55,
  `Metrowerks_details_compressed_pair_imp_swap` 54, `std_vector_imp_insert` 54, `std_vector_deleter_ctor` 49,
  `Metrowerks_details_compressed_pair_imp_ctor` 41, `std_vector_imp_erase` 33,
  `Metrowerks_details_compressed_pair_imp_second` 31, `std_vector_imp_resize` 30, `std_vector_imp_dtor` 27,
  `std_vector_dtor` 25. All of them are template instantiations of the standard library.
- D's 11 (§1): `std_exception_dtor` 8, `RFU116_SetSyscall` 5, `RFU091` 3, and 2 each for `AddDmacHandler`,
  `C2DBitmapPoly_SetUV`, `CAiMapLoc_ctor`, `sceCdDiskReady`, `setD3_CHCR`, `u_request_end`, `uu_sbprintf`,
  `uu_sprint`.

Rendering variants, colliding names / functions before any suffix (§1):

| variant | A | B | C | D |
|---|---|---|---|---|
| **U2** (chosen): leading `_`×k → `u`×k + `_` | 2/4 | 353/1,532 | 7/23 | 11/32 |
| U1: strip leading `_` | 2/4 | 383/1,592 | 9/27 | **18/46** |
| U3: any leading run → `u_` | 2/4 | 353/1,532 | 7/23 | 11/32 |
| template arguments kept (sanitised) | 2/4 | 245/529 | 7/23 | 11/32 |
| `_` runs not collapsed | 2/4 | 351/1,528 | 7/23 | 11/32 |

Stripping (U1) merges a name with its un-underscored twin 32 times in B and 7 times in D (§1): `_ExecOSD`/`ExecOSD`,
`_InitTLB`/`InitTLB`, `_LoadExecPS2`/`LoadExecPS2`, `_iSuspendThread`/`iSuspendThread`,
`_iWakeupThread`/`iWakeupThread`, `_printf`/`printf`, `_sceSifSendCmd`/`sceSifSendCmd`. The demo has both
spellings as separate functions (§1 lists them), so stripping loses a real distinction. U3 ties U2 today, but U2
is injective, so it is the one a test should pin.

## 2. The overload suffix, (i) against (ii)

(i) is the mangled argument list after `F`, sanitised and cut to 24. (ii) is six hex digits of SHA-1 of the whole
mangled name. Each is applied only to members of a group that still collides. **R9** applies (i) to a group when
(i) makes every member distinct, and (ii) to the whole group otherwise. Groups whose mangled names are all
identical are left to R10, because no suffix derived from the name can split them. "Left" below means colliding
names / functions (§2).

| set | (i) | (i) uncut | (ii) | (i)+tag | **R9** | mean added chars (i) / (ii) / R9 |
|---|---|---|---|---|---|---|
| A | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | **0 / 0** | 7.5 / 6.0 / 7.5 |
| B | 165 / 865 (147 distinct-mangled) | 135 / 750 (117) | 18 / 49 (0) | 98 / 364 (80) | **18 / 49 (0)** | 9.9 / 6.0 / 9.5 |
| C | 7 / 23 (0) | same | same | same | **7 / 23 (0)** | - |
| D | 9 / 28 (0) | same | same | same | **9 / 28 (0)** | 7.5 / 6.0 / 7.5 |

Every figure left after (ii) or R9 is an **identical mangled name at several addresses** (§2 residue), which §8 and
R10 deal with. Under R9, 208 groups in B are settled by (i) and 128 by (ii). In A and D both groups are settled by
(i) (§2).

Added-length distribution (§2): for (i) in B it is 1–4 chars: 808, 5–8: 58, 9–16: 114, 17–23: 179, cut at 24: 327.
For (ii) every suffix is 6. For R9 in B it is 1–4: 147, 5–8: 935, 9–16: 105, 17–23: 104, 24: 195. Removing the
cut only takes the distinct-mangled residue from 147 to 117, at a mean of 30 added characters, so the cut is not
what makes (i) fail. What does: template instantiations whose arguments are all `v` (`std_vector_deleter_dtor_v`
×57) and 19 const-only overloads (same base and arguments, one method `const`) (§2).

What a reader sees (§2):

| | (i) | (ii) |
|---|---|---|
| `SetUV__13C2DBitmapPolyFffff` | `C2DBitmapPoly_SetUV_ffff` | `C2DBitmapPoly_SetUV_0363b0` |
| `SetUV__13C2DBitmapPolyFffffffff` | `C2DBitmapPoly_SetUV_ffffffff` | `C2DBitmapPoly_SetUV_298fb8` |
| `__ct__9CAiMapLocFRC9CAiMapLoc` | `CAiMapLoc_ctor_RC9CAiMapLoc` | `CAiMapLoc_ctor_fdcffb` |
| `@24@72@__dt__Q23std39basic_istream<c,…>Fv` / `<w,…>` | both `…_thunk24_72_v`: **still collide** | `…_5faf5c` / `…_5a236c` |

**Decision:** use (i) wherever it splits the group, which covers both overload pairs in the names applied now
(D, §8: 4 names carry a suffix, all from (i)), and fall back to (ii) for the group when it does not. (i) alone
leaves 147 distinct-mangled groups in B, which later passes (vtable slots, templates) would hit. (ii) alone is
unique but gives the reader nothing. R9 keeps the spec's default and closes the gap, at a mean of 9.5 added
characters in B.

## 3. Length: the cut and SHA-1 rule

- After R9, **no rendered name in any set is over 87 characters**. The longest are 41 in A and D, 27 in C and 74 in
  B (`std_list_generic_iterator_op_conv_std_list_deleter_generic_iterator_342c93`) (§3). So the cut never fires
  today. Only the raw mangled names are long: 640 in B and 1 in A are over 96 once sanitised (§3).
- **The limit should be 87, not 96.** `getOutputPath` writes `<name>_0x<start>.cpp` and
  `clampFilenameLength(…, ".cpp", 100)` cuts the name part (`ps2_recompiler.cpp` 2111–2186). Both csvs' starts
  have at most 6 hex digits (`0x180008..0x669f40`, and `0x9f000..0x6699a8` for r0004), so the budget is
  100 − 4 − 3 − 6 = **87** (§3). With a 96 limit, a name of 88–96 characters would be cut in its filename but not
  in its identifier, and a grep for it would miss the file. R11 is therefore: over 87, keep the first 78, then `_`,
  then eight hex digits of SHA-1 of the mangled original (87 in total). The cut adds 0 collisions in any set (§3).

## 4. What the recompiler's sanitisers would alter

**There is no `sanitizeIdentifier`.** There are two `sanitizeFunctionName`s, and their rules differ. **The one
that runs on this image is makeName's** (`PS2Recompiler::sanitizeFunctionName`, `ps2_recompiler.cpp` 2190).
The code-generator copy is only the fallback for addresses that have an ELF symbol, and it never runs because the
retail ELF has no symbol table (research/46 §5). Both copies are measured below. The makeName path's count is the
live figure, in brackets:

| path | where | rules (applied after `sanitizeIdentifierBody`) |
|---|---|---|
| **makeName, live** (the identifier and the filename of every generated function; `_0x<start>` is appended afterwards at 1085–1107) | `ps2_recompiler.cpp` 2190–2208, body 49–80, reserved 36–47 | `main` → `ps2_main`; keyword **or** reserved (`__x`, `_X`) → `ps2_` + name; `_x` is left as it is |
| code generator (a variant that does not run here: the symbol-table fallback in `getFunctionName`) | `code_generator.cpp` 181–201, body 53–79, reserved 81–88 | `main` → `ps2_main`; keyword → `ps2_`; **any** leading `_` → `ps2` + name; reserved → `ps2_` |
| body (both) | | every character outside `[A-Za-z0-9_]` → `_`; a first character that is not a letter or `_` gets a `_` prefix |

The keyword set copied is all 92 entries of `kKeywords` (`code_generator.cpp` 35–47): `alignas alignof and and_eq
asm auto bitand bitor bool break case catch char char8_t char16_t char32_t class compl concept const consteval
constexpr constinit const_cast continue co_await co_return co_yield decltype default delete do double dynamic_cast
else enum explicit export extern false float for friend goto if inline int long mutable namespace new noexcept not
not_eq nullptr operator or or_eq private protected public register reinterpret_cast requires return short signed
sizeof static static_assert static_cast struct switch template this thread_local throw true try typedef typeid
typename union unsigned using virtual void volatile wchar_t while xor xor_eq`. The special case `main` is added
on top.

Names altered by either path, with the **live makeName path's** count in brackets (§4). The sketch figure for A,
31 live and 121 by either path, matches research/46's 31 and 121:

| set | raw names | sketch | final |
|---|---|---|---|
| A | 135 (46): leading `_` 89, reserved 43, non-identifier 9 | 121 (31) | **0** |
| B | 2,682 (2,330): non-identifier 1,602, reserved 1,358, leading `_` 396, `main` 1 | 784 (291) | **0** |
| C | 260 (97): leading `_` 163, reserved 97 | 252 (89) | **0** |
| D | 285 (127): leading `_` 158, reserved 124, non-identifier 9 | 263 (104) | **0** |

Examples by rule (§4): leading `_`: `_delete_vec__FPvPCci`, `_calloc_r`. Reserved: `__divdi3`, `__malloc_lock`,
`__TransferControl__FP…`. Non-identifier: `SetButtonState__Q221@unnamed@zui_skb_cpp@…`,
`swap__Q23std30vector<b,…>…`. `main`: `main`. No keyword ever occurs, and no leading digit survives rendering
(§7: `fn_` fires 0 times, `ps2_` once, on `main`). **Today's csv already has 9 hand names that the makeName path
rewrites** (`_Exit` → `ps2__Exit`, `_LoadExecPS2`, `_EnableIntc`, `_DisableIntc`, `_EnableDmac`, `_DisableDmac`,
`_StartThread`, `_ExecOSD`, `_InitTLB`) (§4).

The final rule is held to both paths, so it does not depend on which one runs. The fixes that bring every set to 0
are R5–R8. They also cover the three sketch outputs research/48 flagged: `__sinit_…` (R5), `_unnamed_…__` (R3 →
`anon_…`) and template class paths such as `std_vector_b_Q23std12allocator_b___swap` (R3 drops the arguments →
`std_vector_swap`, and R9 suffixes it only if it collides). The fixes are: `__sinit_<f>.cpp` → `sinit_<f>`; `@unnamed@<f>@` → `anon_<f>`; a
leading run of k underscores → `u`×k + `_` (`_delete_vec` → `u_delete_vec`, `__divdi3` → `uu_divdi3`); a leading
digit → `fn_`; a keyword or `main` → `ps2_` + name, which is exactly what the recompiler would print, so the csv
name and the output agree.

## 5. Windows filenames

Of the final names (§5): reserved device names (`CON PRN AUX NUL COM1-9 LPT1-9`, any case, with or without an
extension) **0** in every set; trailing dot or space **0**; illegal characters **0**. Case-only collisions: **0** in
A, C and D, and **4** in B: `CMission_FadeToEndMissionTick`/`CMission_fadeToEndMissionTick`,
`CMission_Tick`/`CMission_tick`, `Exit`/`exit`, `zrdr_findSTRING`/`zrdr_findstring`. These are real distinct
source names. When R9 compares names case-insensitively, (ii) splits all 4 and 0 remain (§5).

The recompiler's own file is `<name>_0x<start>.cpp`, so a device name can never be the stem and two case-variant
names never map to one file, because the address differs. The hazard exists only for a consumer that writes the
bare name. R9 compares case-insensitively anyway, which costs nothing today.

## 6. Templates

- Names with `<…>`: 1,305 in B, 2 in A and D, 0 in C (§6).
- Dropping template arguments from the class path and function name, as §1.2 says, is involved in 185 colliding
  base names over 1,164 functions in B. With arguments kept, B's base collisions would be 245 instead of 353 (§1,
  §6). **In A, C and D it causes 0 collisions** (§6).
- After suffix (i), 145 template groups still collide in B. Adding a template tag (the argument words, e.g.
  `DrawFunc<11CDynGrenade>` → `CDynGrenade`) splits them down to 78 (§6). Examples left after (i)+tag:
  `begin__Q23std59basic_string<c,…>CFv` against the non-const `…Fv`, and the two
  `__use_facet<Q23std8ctype<c>>`/`<w>` (§6).
- **A tag is not needed for uniqueness.** R9's (ii) fallback settles every distinct-mangled template group, and
  the one template the sprint applies renders uniquely without it (`ai_DrawFunc`). The tag remains an optional
  readability add-on, and no rule should depend on it.

How the parts render (§6, §7): `reserve__Q23std59basic_string<c,…>FUi` → `std_basic_string_reserve`;
`__ct<PCv>__Q23std66allocator<…>F…` → `std_allocator_ctor`, where the sketch gives
`std_allocator_Q33std42__list_deleter_PCv_…___ct` because it looks up the operator before dropping the template
(3 names in B, §7); `DrawFunc<11CDynGrenade>__2aiF…` → `ai_DrawFunc`.

## 7. The special forms (set B)

| form | count (§7) | example → final (sketch) |
|---|---|---|
| anonymous namespace `@unnamed@<file>@` | 162 | `Advance__Q224@unnamed@zanim_menu_cpp@17CSelectedCharsItrFv` → `anon_zanim_menu_CSelectedCharsItr_Advance` (`_unnamed_zanim_menu_cpp__CSelectedCharsItr_Advance`) |
| this-adjusting thunk `@n@[m@]` (a leading `@` that is **not** a namespace) | 31 | `@272@__dt__10CZSealBodyFv` → `CZSealBody_dtor_thunk272`; `@8@72@__dt__…basic_ostream<c,…>Fv` → `std_basic_ostream_dtor_thunk8_72` |
| `__sinit` static initialiser | 149 | `__sinit_ent_main.cpp` → `sinit_ent_main`; bare `__sinit` → `sinit` |
| `$` locals | 17 | `__arraydtor$1955` → `arraydtor_1955`; `ReadBtnName__Q213CCtrlrConfigs23_$798fts_controller_cppFPCc` → `CCtrlrConfigs_local798_ReadBtnName`; `CPnt2D$1514c2dbitmap_poly_cpp` → `CPnt2D` |
| operator in the table | 1,061 | `__dt__8COurGameFv` → `COurGame_dtor` |
| conversion operator `__op<type>` (not in the table) | 7 | `__opUi__Q210Metrowerks12number<Ui,1>CFv` → `Metrowerks_number_op_conv_Ui` (`Metrowerks_number_Ui_1____opUi`) |
| `__defctor` (not in the table) | 1 | `zdb_DiIntersect_defctor` |
| `Q2` / `Q3` class paths | 1,611 / 251 | `…__Q33std59basic_string<…>9CharArrayFUi` → `std_basic_string_CharArray_reserve` |
| free C++ function `fn__F…` | 881 | `__dla__FPv` → `op_delete_array` (sketch: `__dla__FPv` unchanged) |
| plain C name | 2,855, of which 574 start with `_` | `_dpfgt` → `u_dpfgt`; `main` → `ps2_main` |

Operators seen (§7): `__dt` 537, `__ct` 446, `__as` 34, `__vc` 19, `__pp` 7, `__ml` 4, `__eq` 2, `__pl` 2, and
`__dla __dl __nwa __nw __cl __mi __apl __lt __rf __ne __defctor` once each. 20 of the table's 38 entries never
occur. No `Q_<nn>_` form (ten or more components) occurs. The spec's phrase "`@` becomes `anon_`" covers only the
162 namespace names. Applied literally to the 31 thunks, it would call a `this`-adjusting entry an anonymous
namespace.

## 8. The proof over D

With R1–R12 over D's 894 non-auto names (§8):

- **Sanitiser alterations 0**, over 87 characters 0, device names 0, trailing dot or space 0, illegal characters 0,
  case-only collisions 0, and 0 names that render into the auto-name namespace.
- 4 names carry a suffix, all from (i): `C2DBitmapPoly_SetUV_ffff`/`_ffffffff`, `CAiMapLoc_ctor_UiUiUi`,
  `CAiMapLoc_ctor_RC9CAiMapLoc`.
- After R9, 9 names over 28 addresses still collide, and each is one mangled name at several addresses. **R10**
  keeps an identical name at k addresses when the demo holds it at least k times (a C `static` defined in several
  files). It keeps 3 names over 6 rows: `u_request_end`, `uu_sbprintf` and `uu_sprint`, each twice in the demo and
  twice in D. It **refuses 6 names over 22 rows**:

| refused | rows | demo count | what it is |
|---|---|---|---|
| `AddDmacHandler` | hand 0x1a3830, 0x1a3840 | 1 | hand duplicate. The demo's order is `AddDmacHandler 16, AddDmacHandler2 16`, and ours at 0x1a3830/0x1a3840 is 16/16 (§8 positional hint), so 0x1a3840 is probably `AddDmacHandler2`. Both rows are 16 B (§8), below research/44's 64-byte body hurdle, so this is a candidate, not a proof |
| `RFU091` | hand 0x1ac108, 0x1acb80, 0x1acfa0 | 1 | hand-named after the syscall the stub makes, inside the kernel-patch copies |
| `RFU116_SetSyscall` | hand ×5 | 0 | same. In the first copy, the demo's sequence `Copy 16, kCopy 56, GetEntryAddress 16, setup 16, InitTLBFunctions 196` lines up with ours `FUN_001ac0c0 16, [56-byte gap = the toml's kCopy], RFU091 16, RFU116_SetSyscall 16, InitTLBFunctions 196` (§8). The demo's names would be `GetEntryAddress` (×3 in the demo) and `setup` (×5), which R10 would keep. Positional candidate only |
| `sceCdDiskReady` | Task 7 0x18ed78 (relinked-body 0.85), toml 0x18ef70 | 1 | **Task 7 and the toml disagree**: one demo name at two of our addresses, so one of them is wrong |
| `setD3_CHCR` | toml 0x1a30b8, Task 7 0x1a3448 (hash+callees 0.95) | 1 | **Task 7 and the toml disagree**, and the toml calls 0x1a3448 `setD4_CHCR`, a name the demo holds twice |
| `std_exception_dtor` | toml ×8 (`__dt__Q23std9exceptionFv`) | 1 | the toml's `untracked_stubs` gives one name to 8 separate 76-byte bodies |

So the answer to "zero collisions" is: **zero once the 22 rows are refused**, and the refusal is a finding rather
than a loss. Ten of the 22 are existing hand names that Task 1 has to respell, with the positional candidates
above. Four are real disagreements between two passes. Eight are a toml over-claim. Separately, the 42 auto
`caseD_*` rows repeat 13 names over 36 rows among themselves. They are exempt under R12 as placeholders
(§8).

**Hand names:** R6 respells 15 of the 70 (§8): `_Exit`, `_LoadExecPS2`, `_EnableIntc`, `_DisableIntc`,
`_EnableDmac`, `_DisableDmac`, `_iEnableIntc`, `_iDisableIntc`, `_iEnableDmac`, `_iDisableDmac`, `_StartThread`,
`_iWakeupThread`, `_iSuspendThread`, `_ExecOSD` and `_InitTLB` each become `u_…`. The recompiler already rewrites
9 of them to `ps2__…` (§4).

## The recommended rule set (what Task 1 implements and a test pins)

The input is a mangled or plain name. The output is the csv `Name`, and the sidecar keeps the input as
`Mangled`. Each rule has a test example that the command reproduces.

1. **R1: thunks.** A leading `@<n>@` or `@<n>@<m>@` is removed and `_thunk<n>` or `_thunk<n>_<m>` is appended to
   the rendered base. `@272@__dt__10CZSealBodyFv` → `CZSealBody_dtor_thunk272`.
2. **R2: the split.** Take the first `__` that is outside `<…>` and not at position 0, and whose tail parses as
   `F<args>`, or as a class path (`Q<d>` plus d length-prefixed components, or one `<len><name>`) followed by
   optional `C` and then `F<args>` or nothing. Anything that does not parse is a plain name.
   `__end__catch` → plain.
3. **R3: the class path.** Components are joined with `_`. Each component: template arguments are dropped;
   `@unnamed@<file>@` → `anon_<file without _cpp/_c>`; `<X>$<n><file>` → `X`, or `local<n>` when X is empty or
   `_`. `Q23zdb5CNode` → `zdb_CNode`.
4. **R4: the function part.** Template arguments are dropped first, then the operator table is applied (the
   sketch's 38 entries plus `__defctor` → `defctor`). `__op<type>` → `op_conv_<type words>`. A free function keeps
   its name. `__pl__6CPnt3DCFRC6CPnt3D` → `CPnt3D_op_add`, `__dla__FPv` → `op_delete_array`,
   `__opf__6RfloatCFv` → `Rfloat_op_conv_f`.
5. **R5: plain forms.** `__sinit_<f>.cpp` → `sinit_<f>`, bare `__sinit` → `sinit`, `<X>$<n>` → `<X without
   leading _>_<n>`. `__arraydtor$1955` → `arraydtor_1955`.
6. **R6: leading underscores.** A leading run of k underscores becomes `u`×k + `_`. It is injective and never
   meets an un-underscored twin. `_delete_vec` → `u_delete_vec`, `__divdi3` → `uu_divdi3`, `_Exit` → `u_Exit`.
7. **R7: sanitise.** Replace `[^A-Za-z0-9_]` with `_`, collapse runs of `_`, and strip trailing `_`.
8. **R8: guards.** A leading digit gets `fn_`. A C++ keyword (the 92 above) or `main` gets `ps2_`.
   `main` → `ps2_main`.
9. **R9: overloads.** Only for names that collide, **case-insensitively**, with another non-auto name in the csv.
   Per colliding group: append `_` plus (i), the sanitised argument list cut to 24, if that makes every member
   distinct. Otherwise append `_` plus (ii), six hex digits of SHA-1 of the mangled name, to every member. Repeat
   until nothing changes. `SetUV__13C2DBitmapPolyFffff` → `C2DBitmapPoly_SetUV_ffff`.
10. **R10: one name, several addresses.** When the mangled names are identical, the rows are kept unsuffixed only
    if the demo's `.symtab` holds that name at least as many times. Otherwise **every row is refused** (for a hand
    name, the row is flagged for respelling). `_request_end` ×2 is kept. `__dt__Q23std9exceptionFv` ×8 is refused.
11. **R11: length.** Over 87 characters, keep the first 78, then `_`, then eight hex digits of SHA-1 of the mangled
    original.
12. **R12: scope.** Auto names (`FUN_ LAB_ thunk_FUN_ caseD_ sub_ entry`, plus `thunk_EXT_FUN_` as proposed below)
    are never rendered and are exempt from R9/R10. No rendered name may match the auto pattern. Hand names go
    through R6–R8 and R9/R10 like every other name.

The test's invariant, over the csv after applying: every non-auto `Name` satisfies `sanitize_recomp(n) == n` and
`sanitize_codegen(n) == n`, has at most 87 characters, is not a device name, and is unique case-insensitively,
except for the R10 groups that were kept.

## Where this overturns the spec

1. **§1.1: "two rows with one sanitised spelling are two definitions of one symbol" is false.** `makeName`
   (`ps2_recompiler.cpp` 1083–1108) names every generated function `<name>_0x<start>`, and `getOutputPath` writes
   that same string as the file. Duplicate names cannot clash in the build. Uniqueness matters for readers, for
   grep and for `carry_names`.
2. **§1.1: "`sanitizeIdentifier` prefixes `ps2` to a leading underscore" describes only the code-generator
   fallback, which never runs on this image (research/46).** The live makeName path leaves `_x` alone and rewrites
   `__x`/`_X`. Both paths also rewrite `main`. R6–R8 satisfy both.
3. **§1.2 rule 2's "255 over 607" is the sketch's count.** The rule as written gives 353 / 1,532 in B (§1). The
   argument suffix alone does not make B unique (147 distinct-mangled groups left, §2). R9's hash fallback does.
4. **§1.2 rule 2's "a name that still collides is refused, both rows"** would also refuse C statics the demo itself
   holds twice. R10 keeps 3 such names over 6 rows in D (§8).
5. **§1.2 rule 3's 96 characters should be 87,** the recompiler's filename budget (§3).
6. **§1.2 rule 1's "`@` becomes `anon_`"** fits the 162 namespace names but not the 31 `@n@` thunks, and the
   operator table misses `__op<type>` (7) and `__defctor` (1) (§7).
7. **§1.3's "113 hand-named rows"** are 70 hand plus 43 auto (42 `caseD_`, 1 `entry`) by §1.3's own list (§0).
   Backfilling all 113 with `Pass=hand` would record 43 placeholders as names.
8. §1.1 names the analyzer's `importGhidraMap` as the csv reader. The recompiler reads the csv itself in
   `ElfParser::loadGhidraFunctionMap` (`elf_parser.cpp` 959). The name reaches `function.name` either way; the
   full map is research Q1's.

**Not answered here (stop rule):** whether the RFU hand names and `AddDmacHandler` at 0x1a3840 really are the
demo's `GetEntryAddress`/`setup`/`AddDmacHandler2`. The bodies are 16 B (§8), below research/44's 64-byte
hurdle, so only the positional pass under its own acceptance rule can decide. Also left open: which of
`sceCdDiskReady` 0x18ed78/0x18ef70 and `setD3_CHCR` 0x1a30b8/0x1a3448 is right, which needs the matcher's
evidence reviewed side by side.

## What this means for a task

| task | finding | what it changes |
|---|---|---|
| Task 1 (the applier) | R1–R12 give 0 sanitiser alterations, 0 filename hazards and 0 unresolved collisions over D, once 22 rows are refused (§8) | implement R1–R12 from the list above; pin the example pairs and the invariant; the sidecar keeps `Mangled` |
| Task 1 | the overload suffix is (i) where it splits the group, otherwise (ii) (§2) | R9, not (i) alone: (i) alone leaves 147 distinct-mangled groups in B that later passes would hit |
| Task 1 | the name cap is 87, the filename budget, not 96 (§3) | change `IDENT_LIMIT`-style checks to 87; nothing is over the cap today |
| Task 1, hand backfill | 70 hand plus 43 auto rows, not 113 hand; 15 hand names respelled by R6; 3 hand names duplicated over 10 rows (§0, §8) | backfill 70 as `hand`, treat `caseD_`/`entry` as auto; the respellings go in the sidecar; the duplicates need a ruling, with the positional candidates `AddDmacHandler2`, `GetEntryAddress`, `setup` |
| Task 1 / spec §1.3 | `thunk_EXT_FUN_09481d98` is a Ghidra auto name that embeds an address, and none of the auto lists has it (§0 hand list) | add `thunk_EXT_FUN_` to the auto pattern in `carry_names`, the sidecar audit and R12 |
| Goal 6 (toml stubs) | 41 toml addresses are not csv rows; the toml gives `__dt__Q23std9exceptionFv` to 8 addresses; `sceCdDiskReady` and `setD3_CHCR` disagree with Task 7 (§0, §8) | the toml pass applies only to csv starts, or adds rows; R10 refuses the 8; the two disagreements go to review before either name is applied |
| Goal 6 | stub handlers bind by address to the toml's own name (`ps2_recompiler.cpp` 768–791), not to the csv `Name` | the readable form (`uu_divdi3`) goes into the csv only; the toml's `stubs` selectors must keep their original spelling |
| Goal 3 / Task 7c, later passes | templates and const overloads are where (i) fails: in B, 128 groups need (ii) (§2) | vtable-slot names over templated classes will carry hash suffixes; a template tag is optional readability, not required |
| Q1 (name consumers) | two sanitiser paths with different rules; `main` rewritten; identifiers and files are `<name>_0x<start>` (§4, source) | the consumer map should record both paths and the address suffix |
